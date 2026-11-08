"""Loads algorithms written by other groups from plain Python files.

A plugin file offers one or both of:

    class MyAgent(Agent): ...            # a subclass with a no-argument constructor
    def choose_action(observation): ...  # takes a plain dict, returns an action name

The function form needs nothing from this project, so a group can adapt its own code in
a few lines. A broken file is reported in the interface and never stops the game.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence

from .agents import Agent, builtin_agent_factories
from .model import Action, GameState


class FunctionAgent(Agent):
    """Adapts a `choose_action(observation) -> action` function to the Agent interface."""

    def __init__(self, function: Callable[[dict], object], name: str) -> None:
        super().__init__()
        self._function = function
        self.name = name

    def choose_action(self, state: GameState, player: int) -> Action:
        return self._function(state.to_observation(player))  # the runner validates the answer


@dataclass
class PluginCatalog:
    """Agents found in plugin files, plus the reason each failed file was rejected."""

    factories: Dict[str, Callable[[], Agent]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)


class PluginLoader:
    @staticmethod
    def _load_module(path: str):
        # A unique module name lets two groups use the same file name.
        digest = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:10]
        module_name = f"tank_battle_plugin_{digest}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot read {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        # Let the plugin import helper files that sit next to it.
        folder = os.path.dirname(os.path.abspath(path))
        if folder not in sys.path:
            sys.path.insert(0, folder)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def load_file(cls, path: str) -> Dict[str, Callable[[], Agent]]:
        """Agents defined in one file. Raises if the file is broken or offers no agent."""
        stem = os.path.splitext(os.path.basename(path))[0]
        module = cls._load_module(path)
        factories: Dict[str, Callable[[], Agent]] = {}

        for class_name, member in inspect.getmembers(module, inspect.isclass):
            if issubclass(member, Agent) and member is not Agent and member.__module__ == module.__name__:
                # A name starting with "_" marks a helper class that is not meant to play.
                if not inspect.isabstract(member) and not class_name.startswith("_"):
                    label = f"{stem}: {getattr(member, 'name', member.__name__)}"
                    factories[label] = member

        function = getattr(module, "choose_action", None)
        if callable(function):
            label = getattr(module, "AGENT_NAME", stem)
            factories[str(label)] = lambda f=function, n=str(label): FunctionAgent(f, n)

        if not factories:
            raise ImportError("no Agent subclass and no choose_action(observation) function found")
        return factories

    @classmethod
    def discover(cls, directory: str) -> PluginCatalog:
        """Load every .py file of a folder, keeping going past broken ones."""
        catalog = PluginCatalog()
        if not os.path.isdir(directory):
            return catalog
        for filename in sorted(os.listdir(directory)):
            if filename.endswith(".py") and not filename.startswith("_"):
                path = os.path.join(directory, filename)
                try:
                    catalog.factories.update(cls.load_file(path))
                except BaseException as error:  # any failure in foreign code, even SystemExit
                    if isinstance(error, KeyboardInterrupt):
                        raise
                    last_line = traceback.format_exception_only(type(error), error)[-1].strip()
                    catalog.errors[filename] = last_line
        return catalog


class AgentCatalog:
    """Every agent the game can use: built-in ones, a plugin folder and explicit files."""

    def __init__(self, plugin_directory: str, extra_files: Sequence[str] = ()) -> None:
        self.plugin_directory = plugin_directory
        self.extra_files = list(extra_files)
        self._builtin = builtin_agent_factories()
        self._plugins: Dict[str, Callable[[], Agent]] = {}
        self.errors: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Read the plugin folder again, so a group's file can be added while the game is open."""
        catalog = PluginLoader.discover(self.plugin_directory)
        self._plugins = catalog.factories
        self.errors = catalog.errors
        for path in self.extra_files:
            self.add_file(path)

    def add_file(self, path: str) -> List[str]:
        """Load one file outside the plugin folder; returns the names of the agents it offers."""
        factories = PluginLoader.load_file(path)
        self._plugins.update(factories)
        if path not in self.extra_files:
            self.extra_files.append(path)
        return list(factories)

    def names(self) -> List[str]:
        return list(self._builtin) + self.plugin_names()

    def plugin_names(self) -> List[str]:
        return list(self._plugins)

    def create(self, name: str) -> Agent:
        factory = self._plugins.get(name) or self._builtin.get(name)
        if factory is None:
            raise KeyError(f"unknown agent '{name}'. Available: {', '.join(self.names())}")
        return factory()
