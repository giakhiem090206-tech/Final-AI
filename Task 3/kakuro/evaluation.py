"""Evaluates the solver's correctness, stability and effectiveness."""
from __future__ import annotations

import csv
import os
import platform
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from typing import List, NamedTuple, Sequence, Tuple

from .csp import KakuroCSP
from .generator import BoardGenerator
from .puzzle import STATEMENT_PUZZLES, KakuroPuzzle, SolutionChecker, load_builtin
from .solver import (
    PROPAGATE_FC, PROPAGATE_MAC, PROPAGATE_NONE, VAL_ASCENDING, VAL_LCV, VAR_DOM_WDEG, VAR_MRV, VAR_MRV_DEGREE,
    VAR_STATIC, BacktrackingSolver, SolverConfig,
)

COMPARED_CONFIGS = [
    SolverConfig(PROPAGATE_NONE, VAR_STATIC, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_MRV, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_MRV_DEGREE, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_MRV_DEGREE, VAL_LCV),
    SolverConfig(PROPAGATE_FC, VAR_DOM_WDEG, VAL_ASCENDING),
    SolverConfig(PROPAGATE_MAC, VAR_STATIC, VAL_ASCENDING),
    SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_LCV),
    SolverConfig(PROPAGATE_MAC, VAR_DOM_WDEG, VAL_ASCENDING),
]


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
        return f"{value:.2f}" if isinstance(value, float) else str(value)

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


class _HardBoardJob(NamedTuple):
    height: int
    density: float
    seed: int
    config: SolverConfig
    time_limit: float


def _solve_generated_board(job: _HardBoardJob) -> Tuple[str, str, float, int, int]:
    """Runs in a worker process. The board is built from its seed, so all configurations get the same one."""
    puzzle = BoardGenerator(job.height, job.height, job.density, job.seed).generate()
    result = BacktrackingSolver(KakuroCSP(puzzle), job.config, time_limit=job.time_limit).solve()
    if result.solution is not None and not SolutionChecker(puzzle).is_valid(result.solution):
        raise AssertionError(f"invalid solution from {job.config.name} on seed {job.seed}")
    return job.config.name, result.status, result.seconds, result.stats.backtracks, result.stats.restarts


class HardBoardEvaluation:
    """Which techniques matter when propagation alone is not enough?

    The two boards of the statement are solved by MAC with no search at all, so they cannot
    separate the heuristics. Larger random boards can. Random boards usually have several
    solutions, so this measures finding one, and it also tests whether LCV helps there.
    """

    CONFIGS = (
        SolverConfig(PROPAGATE_FC, VAR_MRV_DEGREE, VAL_ASCENDING),
        SolverConfig(PROPAGATE_FC, VAR_DOM_WDEG, VAL_ASCENDING),
        SolverConfig(PROPAGATE_MAC, VAR_STATIC, VAL_ASCENDING),
        SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_ASCENDING),
        SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_LCV),
        SolverConfig(PROPAGATE_MAC, VAR_DOM_WDEG, VAL_ASCENDING),
        SolverConfig(PROPAGATE_MAC, VAR_DOM_WDEG, VAL_LCV),
        SolverConfig(PROPAGATE_MAC, VAR_DOM_WDEG, VAL_ASCENDING, restarts=True),
    )

    def __init__(self, sizes: Sequence[int] = (13, 16, 20), seeds: int = 24, density: float = 0.25,
                 time_limit: float = 10.0, workers: int = 4) -> None:
        self.sizes = sizes
        self.seeds = seeds
        self.density = density
        self.time_limit = time_limit
        self.workers = workers

    def run(self, on_progress=lambda text: None) -> ResultTable:
        table = ResultTable(["size", "configuration", "boards", "solved", "ms_median", "ms_mean", "backtrack_mean",
                             "restarts_mean"])
        with ProcessPoolExecutor(max_workers=self.workers) as pool:
            for size in self.sizes:
                on_progress(f"{size} x {size}")
                jobs = [_HardBoardJob(size, self.density, seed, config, self.time_limit)
                        for config in self.CONFIGS for seed in range(self.seeds)]
                outcomes = list(pool.map(_solve_generated_board, jobs, chunksize=2))
                for config in self.CONFIGS:
                    rows = [o for o in outcomes if o[0] == config.name]
                    table.add(size, config.name, len(rows), sum(o[1] == "solved" for o in rows),
                              statistics.median(o[2] for o in rows) * 1000, statistics.mean(o[2] for o in rows) * 1000,
                              statistics.mean(o[3] for o in rows), statistics.mean(o[4] for o in rows))
        return table


class CorrectnessEvaluation:
    """Is the answer right? Checked outside the solver and by searching exhaustively."""

    def run(self) -> ResultTable:
        table = ResultTable(["check", "puzzle", "result"])
        for name in STATEMENT_PUZZLES:
            puzzle = load_builtin(name)
            checker = SolutionChecker(puzzle)
            result = BacktrackingSolver(KakuroCSP(puzzle)).solve()
            table.add("independent checker finds no broken rule", name, not checker.problems(result.solution))
            exhaustive = BacktrackingSolver(KakuroCSP(puzzle)).solve(max_solutions=1000)
            table.add("number of solutions (exhaustive search)", name, len(exhaustive.solutions))
            answers = {tuple(BacktrackingSolver(KakuroCSP(puzzle), c).solve().solution) for c in COMPARED_CONFIGS}
            table.add("all configurations give the same solution", name, len(answers) == 1)
            table.add("search state fully restored after exhaustive search", name,
                      self._restored(puzzle))
            table.add("boards with one clue raised are reported unsatisfiable", name, self._rejects_wrong_clues(puzzle))
        return table

    @staticmethod
    def _restored(puzzle: KakuroPuzzle) -> bool:
        csp = KakuroCSP(puzzle)
        solver = BacktrackingSolver(csp)
        solver.solve(max_solutions=1000)
        after_root = BacktrackingSolver(csp)
        after_root.solve(max_solutions=0)  # stops right after the initial propagation
        return solver.assignment == [0] * csp.num_variables and solver.domains == after_root.domains

    @staticmethod
    def _rejects_wrong_clues(puzzle: KakuroPuzzle) -> str:
        """Raising one clue breaks the equality of the across and down totals, so no solution can exist."""
        rejected = total = 0
        for (r, c), clue in sorted(puzzle.clues.items()):
            if clue.across is None:
                continue
            old = f"{clue.down if clue.down is not None else ''}\\{clue.across}"
            new = f"{clue.down if clue.down is not None else ''}\\{clue.across + 1}"
            rows = [list(row) for row in puzzle.grid]
            if rows[r][c] != old:
                continue
            rows[r][c] = new
            try:
                changed = KakuroPuzzle("changed", "\n".join(" ".join(row) for row in rows))
            except ValueError:
                # The clue is impossible for its length: rejected even before the search.
                rejected += 1
                total += 1
                continue
            total += 1
            rejected += BacktrackingSolver(KakuroCSP(changed)).solve().status == "unsatisfiable"
        return f"{rejected} of {total}"


class EffectivenessEvaluation:
    """How much work does each technique save? Same puzzle, same fixed tie-breaking."""

    def __init__(self, repeats: int = 15, time_limit: float = 60.0) -> None:
        self.repeats = repeats
        self.time_limit = time_limit

    def run(self) -> ResultTable:
        table = ResultTable(["puzzle", "configuration", "status", "median_ms", "assignments", "branch_points",
                             "backtracks", "revisions", "digits_pruned", "max_depth", "valid"])
        for name in STATEMENT_PUZZLES:
            puzzle = load_builtin(name)
            checker = SolutionChecker(puzzle)
            for config in COMPARED_CONFIGS:
                results = [
                    BacktrackingSolver(KakuroCSP(puzzle), config, time_limit=self.time_limit).solve()
                    for _ in range(self.repeats)
                ]
                last = results[-1]
                stats = last.stats
                table.add(name, config.name, last.status, statistics.median(r.seconds for r in results) * 1000,
                          stats.assignments, stats.branch_points, stats.backtracks, stats.revisions,
                          stats.pruned_values, stats.max_depth,
                          last.solution is not None and checker.is_valid(last.solution))
        return table


class StabilityEvaluation:
    """Does the solver depend on luck? Each run shuffles value order and breaks ties at random.

    With a fixed variable order the order itself is random in each run. A row-by-row order
    happens to suit Kakuro, so this shows what that luck is worth and how much the
    propagation and heuristics protect the solver from a poor order.
    """

    def __init__(self, seeds: int = 30, time_limit: float = 5.0) -> None:
        self.seeds = seeds
        self.time_limit = time_limit

    def run(self, on_progress=lambda text: None) -> ResultTable:
        table = ResultTable(["puzzle", "configuration", "runs", "solved", "distinct_solutions", "ms_mean", "ms_std",
                             "ms_max", "assign_mean", "assign_std", "assign_max", "backtrack_mean", "backtrack_max"])
        for name in STATEMENT_PUZZLES:
            puzzle = load_builtin(name)
            checker = SolutionChecker(puzzle)
            for config in COMPARED_CONFIGS:
                on_progress(f"{name}: {config.name}")
                milliseconds, assignments, backtracks = [], [], []
                solved = 0
                solutions = set()
                for seed in range(self.seeds):
                    solver = BacktrackingSolver(KakuroCSP(puzzle), config, rng=random.Random(seed),
                                                time_limit=self.time_limit)
                    result = solver.solve()
                    milliseconds.append(result.seconds * 1000)
                    assignments.append(result.stats.assignments)
                    backtracks.append(result.stats.backtracks)
                    if result.solution is not None:
                        if not checker.is_valid(result.solution):
                            raise AssertionError(f"invalid solution from {config.name}")
                        solved += 1
                        solutions.add(tuple(result.solution))
                table.add(name, config.name, self.seeds, solved, len(solutions),
                          statistics.mean(milliseconds), statistics.pstdev(milliseconds), max(milliseconds),
                          statistics.mean(assignments), statistics.pstdev(assignments), max(assignments),
                          statistics.mean(backtracks), max(backtracks))
        return table
