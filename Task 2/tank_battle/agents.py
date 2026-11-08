"""Agents: anything that can choose a tank action. Other groups' code plugs in here."""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from .evaluation import Evaluator
from .model import Action, GameState
from .search import AdversarialSearch, SearchConfig


class Agent(ABC):
    """The contract every controller honours, whether ours or another group's.

    A subclass implements `choose_action`. It may read `self.time_limit` (seconds per
    decision) and fill `self.last_info` with figures for the interface to display.
    """

    name = "Agent"

    def __init__(self) -> None:
        self.time_limit: Optional[float] = None
        self.last_info: Dict[str, object] = {}

    def reset(self, player: int) -> None:
        """Called once before each game."""

    @abstractmethod
    def choose_action(self, state: GameState, player: int) -> Action:
        """Return the action for this cycle. `state` is a private copy."""


class RandomAgent(Agent):
    name = "Random"

    def __init__(self, seed: Optional[int] = None) -> None:
        super().__init__()
        self._rng = random.Random(seed)

    def choose_action(self, state: GameState, player: int) -> Action:
        return self._rng.choice(list(Action))


class SearchAgent(Agent):
    """Controls a tank by adversarial search.

    With `depth` set it always searches that many cycles; otherwise it deepens until
    `time_limit` runs out. `seed` makes it choose at random among equally good actions.
    """

    DEFAULT_TIME_LIMIT = 0.2

    def __init__(self, config: SearchConfig, depth: Optional[int] = None,
                 time_limit: Optional[float] = None, seed: Optional[int] = None,
                 evaluator: Optional[Evaluator] = None) -> None:
        super().__init__()
        self.name = config.name
        self.config = config
        self.depth = depth
        self.time_limit = time_limit
        self._seed = seed
        self._rng = random.Random(seed) if seed is not None else None
        self._search = AdversarialSearch(config, evaluator)

    def reset(self, player: int) -> None:
        self._search.reset()
        if self._seed is not None:
            self._rng = random.Random(self._seed)

    def choose_action(self, state: GameState, player: int) -> Action:
        if self.config.repetition_penalty:
            self._search.record_position(state, player)
        if self.depth is not None:
            result = self._search.search(state, player, self.depth, self._rng)
        else:
            limit = self.time_limit if self.time_limit is not None else self.DEFAULT_TIME_LIMIT
            result = self._search.iterative_deepening(state, player, limit, rng=self._rng)
        self.last_info = {
            "depth": result.depth,
            "nodes": result.stats.nodes,
            "cutoffs": result.stats.cutoffs,
            "value": result.value,
            "search_seconds": result.seconds,
        }
        if self.config.transposition_table:
            self.last_info["plan"] = self._search.principal_variation(state, player, result.action)
        return result.action


def builtin_agent_factories() -> Dict[str, Callable[[], Agent]]:
    """Agents offered by the interface, by display name."""
    factories: Dict[str, Callable[[], Agent]] = {}
    for make_config in (SearchConfig.optimized, SearchConfig.heuristic_alpha_beta,
                        SearchConfig.heuristic_minimax, SearchConfig.alpha_beta_search,
                        SearchConfig.minimax):
        config = make_config()
        # Blind configurations see only ties; the seed stops them repeating one action forever.
        seed = None if config.heuristic else 7
        factories[config.name] = lambda c=config, s=seed: SearchAgent(c, seed=s)
    factories[RandomAgent.name] = RandomAgent
    return factories


def builtin_agent_names() -> List[str]:
    return list(builtin_agent_factories())
