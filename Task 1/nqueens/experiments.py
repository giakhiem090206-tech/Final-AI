"""Experiments behind requirements 2 (Glucose3) and 3 (Min-Conflicts heuristic)."""
from __future__ import annotations

import csv
import os
import platform
import statistics
from typing import Callable, Dict, List, Sequence

from .encoding import CnfEncoder, PairwiseEncoding, SequentialCounterEncoding
from .min_conflicts import (
    MinConflictsResult,
    MinConflictsSolver,
    MostConflictedSelector,
    MostConflictedTabuSelector,
    RandomConflictedSelector,
    VariableSelector,
)
from .sat_solver import Glucose3QueensSolver, SatResult


def machine_description() -> str:
    """Where the numbers were measured; timings only mean something with this attached."""
    return (
        f"{platform.platform()} | {platform.machine()} {platform.processor()} "
        f"| Python {platform.python_version()}"
    )


class ResultTable:
    """Rows with named columns, printable as a table and exportable as CSV."""

    def __init__(self, columns: Sequence[str]) -> None:
        self.columns = list(columns)
        self.rows: List[List[object]] = []

    def add(self, *values: object) -> None:
        self.rows.append(list(values))

    @staticmethod
    def _text(value: object) -> str:
        return f"{value:.3f}" if isinstance(value, float) else str(value)

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


class SatExperiment:
    """Clause count and running time of Glucose3 for increasing N."""

    DEFAULT_SIZES = (4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120)

    def __init__(self, sizes: Sequence[int] = DEFAULT_SIZES, repeats: int = 3) -> None:
        self.sizes = sizes
        self.repeats = repeats
        self.solver = Glucose3QueensSolver()

    def run(self, on_row: Callable[[int], None] = lambda n: None) -> ResultTable:
        table = ResultTable(
            ["N", "variables", "clauses", "formula_N3", "encode_ms", "load_ms", "solve_ms",
             "total_ms", "conflicts", "decisions", "valid"]
        )
        for n in self.sizes:
            on_row(n)
            results: List[SatResult] = [self.solver.solve(n) for _ in range(self.repeats)]
            last = results[-1]

            def median_ms(pick: Callable[[SatResult], float]) -> float:
                return statistics.median(pick(r) for r in results) * 1000

            table.add(
                n, last.num_variables, last.num_clauses, CnfEncoder.expected_clause_count(n),
                median_ms(lambda r: r.encode_seconds), median_ms(lambda r: r.load_seconds),
                median_ms(lambda r: r.solve_seconds), median_ms(lambda r: r.total_seconds),
                last.conflicts, last.decisions,
                all(r.placement is not None and r.placement.is_solution() for r in results),
            )
        return table


class EncodingExperiment:
    """Pairwise against sequential-counter AtMostOne: formula size and running time.

    Pairwise is skipped above `pairwise_limit`, where its clause lists alone would need
    gigabytes of memory.
    """

    DEFAULT_SIZES = (8, 16, 32, 64, 100, 120, 150, 200, 300)

    def __init__(self, sizes: Sequence[int] = DEFAULT_SIZES, repeats: int = 3, pairwise_limit: int = 120) -> None:
        self.sizes = sizes
        self.repeats = repeats
        self.pairwise_limit = pairwise_limit

    def run(self, on_row: Callable[[int], None] = lambda n: None) -> ResultTable:
        table = ResultTable(["N", "encoding", "variables", "clauses", "encode_ms", "load_ms", "solve_ms", "total_ms",
                             "conflicts", "valid"])
        for n in self.sizes:
            on_row(n)
            for encoding_class in (PairwiseEncoding, SequentialCounterEncoding):
                if encoding_class is PairwiseEncoding and n > self.pairwise_limit:
                    table.add(n, encoding_class.name, "skipped", CnfEncoder.expected_clause_count(n),
                              "-", "-", "-", "-", "-", "-")
                    continue
                solver = Glucose3QueensSolver(encoding_class())
                results = [solver.solve(n) for _ in range(self.repeats)]
                last = results[-1]

                def median_ms(pick: Callable[[SatResult], float]) -> float:
                    return statistics.median(pick(r) for r in results) * 1000

                table.add(n, encoding_class.name, last.num_variables, last.num_clauses,
                          median_ms(lambda r: r.encode_seconds), median_ms(lambda r: r.load_seconds),
                          median_ms(lambda r: r.solve_seconds), median_ms(lambda r: r.total_seconds),
                          last.conflicts,
                          all(r.placement is not None and r.placement.is_solution() for r in results))
        return table


class MinConflictsExperiment:
    """Paired comparison of variable-selection strategies.

    For each N and seed every strategy starts from the same initial assignment, so
    differences come from the strategy rather than from a lucky start. The order of
    the strategies rotates with the seed so no strategy always runs first.
    """

    DEFAULT_SIZES = (8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096)
    BASELINE = RandomConflictedSelector.name
    PROPOSED = MostConflictedTabuSelector.name

    def __init__(self, sizes: Sequence[int] = DEFAULT_SIZES, seeds: int = 100) -> None:
        self.sizes = sizes
        self.seeds = seeds
        self.factories: List[Callable[[], VariableSelector]] = [
            RandomConflictedSelector,
            MostConflictedSelector,
            MostConflictedTabuSelector,
        ]

    def _collect(self, n: int) -> Dict[str, List[MinConflictsResult]]:
        collected: Dict[str, List[MinConflictsResult]] = {}
        count = len(self.factories)
        for seed in range(self.seeds):
            for offset in range(count):
                selector = self.factories[(seed + offset) % count]()
                result = MinConflictsSolver(selector).solve(n, seed)
                if result.solved and not result.placement.is_solution():
                    raise AssertionError(f"invalid solution from {selector.name}, N={n}, seed={seed}")
                collected.setdefault(selector.name, []).append(result)  # in seed order
        return collected

    def run(self, on_row: Callable[[int], None] = lambda n: None) -> ResultTable:
        table = ResultTable(
            ["N", "selector", "success_pct", "steps_mean", "steps_median", "steps_std",
             "ms_mean", "ms_median", "fewer_steps_than_standard_pct"]
        )
        for n in self.sizes:
            on_row(n)
            collected = self._collect(n)
            baseline = collected[self.BASELINE]
            for name, results in collected.items():
                steps = [r.steps for r in results]
                milliseconds = [r.seconds * 1000 for r in results]
                if name == self.BASELINE:
                    wins: object = "-"
                else:
                    better = sum(r.steps < b.steps for r, b in zip(results, baseline))
                    wins = 100.0 * better / len(results)
                table.add(
                    n, name, 100.0 * sum(r.solved for r in results) / len(results),
                    statistics.mean(steps), statistics.median(steps),
                    statistics.pstdev(steps), statistics.mean(milliseconds),
                    statistics.median(milliseconds), wins,
                )
        return table
