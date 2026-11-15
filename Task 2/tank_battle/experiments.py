"""Compares Minimax, Alpha-Beta, Heuristic Minimax and Heuristic Alpha-Beta.

Fairness: every configuration gets the same scenarios, the same action order at the root,
the same rules and (where it is a limit that applies) the same depth or the same time.
A configuration that would be far too slow at some depth is skipped and reported as such.
"""
from __future__ import annotations

import csv
import os
import platform
import random
import statistics
from typing import Callable, Dict, List, Sequence, Tuple

from .maps import BUILTIN_MAPS
from .model import Action, Bullet, Direction, GameState
from .rules import GameRules
from .search import AdversarialSearch, SearchConfig, SearchResult


def machine_description() -> str:
    return (f"{platform.platform()} | {platform.machine()} {platform.processor()} "
            f"| Python {platform.python_version()}")


class ResultTable:
    def __init__(self, columns: Sequence[str]) -> None:
        self.columns = list(columns)
        self.rows: List[List[object]] = []

    def add(self, *values: object) -> None:
        self.rows.append(list(values))

    @staticmethod
    def _text(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    def __str__(self) -> str:
        cells = [self.columns] + [[self._text(v) for v in row] for row in self.rows]
        widths = [max(len(row[i]) for row in cells) for i in range(len(self.columns))]
        lines = [" | ".join(text.rjust(w) for text, w in zip(row, widths)) for row in cells]
        lines.insert(1, "-+-".join("-" * w for w in widths))
        return "\n".join(lines)

    def save_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.columns)
            writer.writerows([[self._text(v) for v in row] for row in self.rows])


class ScenarioLibrary:
    """The fixed positions all configurations are measured on."""

    @staticmethod
    def _after_random_play(map_name: str, seed: int, cycles: int) -> GameState:
        rng = random.Random(seed)
        state = BUILTIN_MAPS[map_name].create_state()
        for _ in range(cycles):
            following = GameRules.step(state, rng.choice(list(Action)), rng.choice(list(Action)))
            if GameRules.outcome(following) is not None:
                break
            state = following
        return state

    @staticmethod
    def _endgame() -> GameState:
        """Low health and bullets in flight, so that terminal states lie inside the horizon."""
        state = BUILTIN_MAPS["Duel"].create_state()
        tank0, tank1 = state.tanks
        base0, base1 = state.bases
        return state.replace(
            tanks=(tank0._replace(x=3, y=4, hp=2, facing=int(Direction.DOWN)),
                   tank1._replace(x=3, y=2, hp=2, facing=int(Direction.UP))),
            bases=(base0._replace(hp=2), base1._replace(hp=2)),
            bullets=(Bullet(1, 2, 5, int(Direction.RIGHT)),),
            walls={},
        )

    @classmethod
    def all(cls) -> Dict[str, GameState]:
        scenarios = {f"{name} opening": game_map.create_state() for name, game_map in BUILTIN_MAPS.items()}
        scenarios["Crossroads midgame"] = cls._after_random_play("Crossroads", seed=21, cycles=25)
        scenarios["Fortress midgame"] = cls._after_random_play("Fortress", seed=22, cycles=25)
        scenarios["Duel endgame"] = cls._endgame()
        return scenarios


def unpruned_nodes(depth: int) -> int:
    """Nodes in the full tree when no terminal state is reached (6 actions per ply)."""
    return 1 + sum(36 ** level * 42 for level in range(depth))


class FixedDepthExperiment:
    """Same scenario and same depth: pruning must change the work but never the answer."""

    def __init__(self, depths: Sequence[int] = (1, 2, 3, 4, 5, 6), repeats: int = 3,
                 max_full_tree_nodes: int = 3_000_000) -> None:
        self.depths = depths
        self.repeats = repeats
        self.max_full_tree_nodes = max_full_tree_nodes

    def _measure(self, config: SearchConfig, state: GameState, depth: int) -> Tuple[SearchResult, float]:
        repeats = self.repeats if unpruned_nodes(depth) < 100_000 else 1
        results = [AdversarialSearch(config).search(state, 0, depth) for _ in range(repeats)]
        return results[-1], statistics.median(r.seconds for r in results) * 1000

    def run(self, on_progress: Callable[[str], None] = lambda text: None) -> ResultTable:
        table = ResultTable(["scenario", "configuration", "depth_cycles", "plies", "time_ms", "nodes",
                             "expansions", "evaluations", "cutoffs", "ebf", "value", "action"])
        for scenario, state in ScenarioLibrary.all().items():
            on_progress(scenario)
            for depth in self.depths:
                answers: Dict[bool, Tuple[float, Action]] = {}
                for config in SearchConfig.required_four():
                    if not config.alpha_beta and unpruned_nodes(depth) > self.max_full_tree_nodes:
                        table.add(scenario, config.name, depth, 2 * depth, "skipped", unpruned_nodes(depth),
                                  "-", "-", "-", "-", "-", "-")
                        continue
                    result, milliseconds = self._measure(config, state, depth)
                    stats = result.stats
                    table.add(scenario, config.name, depth, 2 * depth, milliseconds, stats.nodes, stats.expansions,
                              stats.evaluations, stats.cutoffs, stats.nodes ** (1 / (2 * depth)),
                              result.value, result.action.name)
                    answer = (result.value, result.action)
                    # Each pruned configuration must agree with its unpruned twin.
                    if config.heuristic in answers and answers[config.heuristic] != answer:
                        raise AssertionError(f"{config.name} disagrees with its twin on {scenario}, depth {depth}")
                    answers[config.heuristic] = answer
        return table


class FixedTimeExperiment:
    """Same scenario and same time: how deep does each configuration get?"""

    def __init__(self, limits: Sequence[float] = (0.05, 0.1, 0.2, 0.5, 1.0), repeats: int = 3) -> None:
        self.limits = limits
        self.repeats = repeats

    def run(self, on_progress: Callable[[str], None] = lambda text: None) -> ResultTable:
        table = ResultTable(["time_limit_ms", "configuration", "median_depth_cycles", "mean_depth_cycles",
                             "max_depth_cycles", "mean_nodes", "mean_nodes_per_ms", "mean_table_hits"])
        scenarios = ScenarioLibrary.all()
        for limit in self.limits:
            on_progress(f"{limit * 1000:.0f} ms")
            for config in SearchConfig.required_four() + [SearchConfig.optimized()]:
                depths, nodes, rates, hits = [], [], [], []
                for state in scenarios.values():
                    for _ in range(self.repeats):
                        result = AdversarialSearch(config).iterative_deepening(state, 0, limit)
                        depths.append(result.depth)
                        nodes.append(result.stats.nodes)
                        rates.append(result.stats.nodes / (result.seconds * 1000))
                        hits.append(result.stats.table_hits)
                table.add(limit * 1000, config.name, statistics.median(depths), statistics.mean(depths), max(depths),
                          statistics.mean(nodes), statistics.mean(rates), statistics.mean(hits))
        return table
