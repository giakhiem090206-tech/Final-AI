"""Compares Minimax, Alpha-Beta, Heuristic Minimax and Heuristic Alpha-Beta.

Fairness: every configuration gets the same scenarios, the same action order at the root,
the same rules and (where it is a limit that applies) the same depth or the same time.
A configuration that would be far too slow at some depth is skipped and reported as such.
"""
from __future__ import annotations

import csv
import importlib.util
import itertools
import os
import platform
import random
import statistics
from collections import Counter
from concurrent.futures import Executor
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .agents import Agent, RandomAgent, SearchAgent
from .evaluation import HeuristicEvaluator, RaceEvaluator, RaceWeights
from .maps import BUILTIN_MAPS
from .model import DRAW, Action, Bullet, Direction, GameState
from .rules import GameRules
from .search import AdversarialSearch, SearchConfig, SearchResult
from .session import HeadlessMatch


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


class OptimizationAblation:
    """What each optimization of the real controller saves, one at a time and all together.

    Every configuration searches the same scenarios to the same depth. None of these
    optimizations may change the value found at the root, only the work done to find it,
    so the values are checked against the plain Heuristic Alpha-Beta.
    """

    def __init__(self, depths: Sequence[int] = (4, 5), repeats: int = 3) -> None:
        self.depths = depths
        self.repeats = repeats

    @staticmethod
    def configurations() -> List[SearchConfig]:
        base = SearchConfig.heuristic_alpha_beta()
        return [
            base,
            replace(base, name="+ skip duplicate actions", action_pruning=True),
            replace(base, name="+ move ordering", move_ordering=True),
            replace(base, name="+ transposition table", transposition_table=True),
            replace(SearchConfig.optimized(), name="all three"),
        ]

    def run(self, on_progress: Callable[[str], None] = lambda text: None) -> ResultTable:
        table = ResultTable(["depth_cycles", "configuration", "total_ms", "total_nodes", "total_evaluations",
                             "nodes_vs_plain", "time_vs_plain", "same_root_values"])
        scenarios = ScenarioLibrary.all()
        for depth in self.depths:
            on_progress(f"depth {depth}")
            plain_values: Optional[List[float]] = None
            plain_nodes = plain_ms = 0.0
            for config in self.configurations():
                milliseconds, nodes, evaluations, values = 0.0, 0, 0, []
                for state in scenarios.values():
                    runs = [AdversarialSearch(config).search(state, 0, depth) for _ in range(self.repeats)]
                    milliseconds += statistics.median(r.seconds for r in runs) * 1000
                    nodes += runs[-1].stats.nodes
                    evaluations += runs[-1].stats.evaluations
                    values.append(round(runs[-1].value, 9))
                if plain_values is None:
                    plain_values, plain_nodes, plain_ms = values, nodes, milliseconds
                table.add(depth, config.name, milliseconds, nodes, evaluations, nodes / plain_nodes,
                          milliseconds / plain_ms, values == plain_values)
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


class OpeningBook:
    """Varied starting positions, reached by a few random moves on a fair map.

    The built-in maps are mirror-symmetric, so two equal agents starting from the initial
    position always draw and reveal nothing. Each opening is played from both sides, which
    cancels any advantage the random moves gave to one side.
    """

    @staticmethod
    def generate(count: int, seed: int, maps: Sequence[object], max_cycles: int = 150) -> List[GameState]:
        """`maps` holds GameMap objects or names of built-in maps; they are used in turn."""
        rng = random.Random(seed)
        openings = []
        for index in range(count):
            game_map = maps[index % len(maps)]
            if isinstance(game_map, str):
                game_map = BUILTIN_MAPS[game_map]
            state = game_map.create_state(max_cycles)
            for _ in range(rng.randint(2, 10)):
                following = GameRules.step(state, rng.choice(list(Action)), rng.choice(list(Action)))
                if GameRules.outcome(following) is not None:
                    break
                state = following
            openings.append(state.replace(cycle=0))
        return openings


@dataclass(frozen=True)
class AgentRecipe:
    """How to build an agent, in a form that can be sent to a worker process."""

    label: str
    config: Optional[SearchConfig] = None
    basic_evaluator: bool = False
    weights: Tuple[Tuple[str, float], ...] = ()  # overrides of the RaceWeights defaults
    depth: Optional[int] = None
    time_limit: Optional[float] = None
    sparring_class: Optional[str] = None  # a class in plugins/sparring_partners.py

    def build(self) -> Agent:
        if self.sparring_class is not None:
            return _sparring_module().__dict__[self.sparring_class]()
        evaluator = HeuristicEvaluator() if self.basic_evaluator else RaceEvaluator(RaceWeights(**dict(self.weights)))
        return SearchAgent(self.config, depth=self.depth, time_limit=self.time_limit, evaluator=evaluator)


def _sparring_module():
    """The sparring partners live with the plugins, to serve also as examples for other groups."""
    global _SPARRING
    if _SPARRING is None:
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugins")
        spec = importlib.util.spec_from_file_location("sparring_partners", os.path.join(folder, "sparring_partners.py"))
        _SPARRING = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_SPARRING)
    return _SPARRING


_SPARRING = None
SPARRING_PARTNERS = tuple(AgentRecipe(name, sparring_class=name) for name in ("Rusher", "Hunter", "Turret", "Dodger"))


def previous_version(depth: Optional[int] = None, time_limit: Optional[float] = None) -> AgentRecipe:
    """The controller before the improvements: first evaluator, no defence against going in circles."""
    config = replace(SearchConfig.optimized(), repetition_penalty=0.0)
    return AgentRecipe("Previous version", config, basic_evaluator=True, depth=depth, time_limit=time_limit)


def _play_game(task: Tuple[GameState, AgentRecipe, AgentRecipe, bool]) -> Tuple[float, int, bool]:
    """One game; returns the first recipe's score, the length, and whether it hit the cycle limit."""
    state, first, second, first_plays_p1 = task
    players = (first, second) if first_plays_p1 else (second, first)
    result = HeadlessMatch(state, (players[0].build(), players[1].build())).play()
    stalled = result.cycles >= state.max_cycles
    if result.outcome == DRAW:
        return 0.5, result.cycles, stalled
    return (1.0 if result.outcome == (0 if first_plays_p1 else 1) else 0.0), result.cycles, stalled


@dataclass
class DuelScore:
    wins: int
    draws: int
    losses: int
    mean_cycles: float
    stalled: int

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def score(self) -> float:
        return (self.wins + 0.5 * self.draws) / self.games


def duel(first: AgentRecipe, second: AgentRecipe, openings: Sequence[GameState], pool: Optional[Executor] = None) -> DuelScore:
    """Plays every opening from both sides. Fixed-depth games can safely run in parallel."""
    tasks = [(state, first, second, side) for state in openings for side in (True, False)]
    results = list(pool.map(_play_game, tasks, chunksize=4)) if pool is not None else [_play_game(t) for t in tasks]
    return DuelScore(
        wins=sum(r[0] == 1.0 for r in results),
        draws=sum(r[0] == 0.5 for r in results),
        losses=sum(r[0] == 0.0 for r in results),
        mean_cycles=statistics.mean(r[1] for r in results),
        stalled=sum(r[2] for r in results),
    )


class StrengthExperiment:
    """Is the new controller actually better? It plays the previous version and every sparring
    partner, on maps and openings that were not used to tune its weights."""

    def __init__(self, candidate: AgentRecipe, opponents: Sequence[AgentRecipe], openings: Sequence[GameState],
                 pool: Optional[Executor] = None) -> None:
        self.candidate = candidate
        self.opponents = opponents
        self.openings = openings
        self.pool = pool

    def run(self, on_progress: Callable[[str], None] = lambda text: None) -> ResultTable:
        table = ResultTable(["player", "opponent", "games", "wins", "draws", "losses", "score_pct",
                             "mean_cycles", "stalled"])
        for opponent in self.opponents:
            on_progress(f"{self.candidate.label} vs {opponent.label}")
            result = duel(self.candidate, opponent, self.openings, self.pool)
            table.add(self.candidate.label, opponent.label, result.games, result.wins, result.draws, result.losses,
                      100.0 * result.score, result.mean_cycles, result.stalled)
        return table


@dataclass
class _Competitor:
    name: str
    make: Callable[[int], Agent]


class TournamentExperiment:
    """Round robin: does the extra search and knowledge actually win games?

    Every pairing plays each map from both sides, so a side advantage cancels out. The
    seed breaks ties at the root, which is the only randomness in these agents.
    """

    def __init__(self, competitors: List[_Competitor], maps: Sequence[str], seeds: int = 2,
                 max_cycles: int = 120) -> None:
        self.competitors = competitors
        self.maps = maps
        self.seeds = seeds
        self.max_cycles = max_cycles

    @classmethod
    def equal_depth(cls, depth: int, maps: Sequence[str], seeds: int = 2) -> "TournamentExperiment":
        competitors = [
            _Competitor(config.name, lambda seed, c=config: SearchAgent(c, depth=depth, seed=seed))
            for config in SearchConfig.required_four()
        ]
        competitors.append(_Competitor(RandomAgent.name, lambda seed: RandomAgent(seed)))
        return cls(competitors, maps, seeds)

    @classmethod
    def equal_time(cls, limit: float, maps: Sequence[str], seeds: int = 2) -> "TournamentExperiment":
        competitors = [
            _Competitor(config.name, lambda seed, c=config: SearchAgent(c, time_limit=limit, seed=seed))
            for config in SearchConfig.required_four() + [SearchConfig.optimized()]
        ]
        return cls(competitors, maps, seeds)

    def run(self, on_progress: Callable[[str], None] = lambda text: None) -> Tuple[ResultTable, ResultTable]:
        pair_table = ResultTable(["player", "opponent", "games", "wins", "draws", "losses", "mean_cycles"])
        totals: Dict[str, Counter] = {c.name: Counter() for c in self.competitors}
        for first, second in itertools.combinations(self.competitors, 2):
            on_progress(f"{first.name} vs {second.name}")
            tally: Counter = Counter()
            cycles: List[int] = []
            for map_name, seed in itertools.product(self.maps, range(self.seeds)):
                for swapped in (False, True):
                    players = (second, first) if swapped else (first, second)
                    agents = (players[0].make(seed), players[1].make(seed + 1000))
                    state = BUILTIN_MAPS[map_name].create_state(self.max_cycles)
                    result = HeadlessMatch(state, agents).play()
                    cycles.append(result.cycles)
                    if result.outcome == DRAW:
                        tally["draws"] += 1
                    elif players[result.outcome] is first:
                        tally["wins"] += 1
                    else:
                        tally["losses"] += 1
            games = sum(tally.values())
            pair_table.add(first.name, second.name, games, tally["wins"], tally["draws"], tally["losses"],
                           statistics.mean(cycles))
            totals[first.name].update(wins=tally["wins"], draws=tally["draws"], losses=tally["losses"])
            totals[second.name].update(wins=tally["losses"], draws=tally["draws"], losses=tally["wins"])

        standing = ResultTable(["player", "games", "wins", "draws", "losses", "score_pct"])
        ranked = sorted(totals.items(), key=lambda item: -(item[1]["wins"] + 0.5 * item[1]["draws"]))
        for name, tally in ranked:
            games = tally["wins"] + tally["draws"] + tally["losses"]
            score = 100.0 * (tally["wins"] + 0.5 * tally["draws"]) / games if games else 0.0
            standing.add(name, games, tally["wins"], tally["draws"], tally["losses"], score)
        return pair_table, standing
