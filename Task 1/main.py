"""Command-line entry point for Task 1 (run from the `Task 1` folder).

    python main.py sat --n 8
    python main.py sat --n 200 --encoding sequential
    python main.py minconflicts --n 8 --selector tabu --seed 0
    python main.py experiment-sat
    python main.py experiment-encoding
    python main.py experiment-minconflicts
"""
from __future__ import annotations

import argparse
import os
from typing import Optional, Sequence

from nqueens.encoding import AT_MOST_ONE_ENCODINGS
from nqueens.experiments import MinConflictsExperiment, SatExperiment, machine_description
from nqueens.min_conflicts import (
    MinConflictsSolver,
    MostConflictedSelector,
    MostConflictedTabuSelector,
    RandomConflictedSelector,
)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
SELECTORS = {
    "standard": RandomConflictedSelector,
    "most-conflicted": MostConflictedSelector,
    "tabu": MostConflictedTabuSelector,
}


def show_board(placement, limit: int = 40) -> None:
    if placement.n <= limit:
        print(placement.render())
    print(f"Independent check (no attacking pair): {placement.is_solution()}")


def run_sat(args: argparse.Namespace) -> None:
    from nqueens.sat_solver import Glucose3QueensSolver

    result = Glucose3QueensSolver(AT_MOST_ONE_ENCODINGS[args.encoding]()).solve(args.n)
    print(f"N={result.n}: {'SAT' if result.satisfiable else 'UNSAT'}, "
          f"{result.num_variables} variables, {result.num_clauses} clauses")
    print(f"encode {result.encode_seconds * 1000:.2f} ms, load {result.load_seconds * 1000:.2f} ms, "
          f"solve {result.solve_seconds * 1000:.2f} ms")
    if result.placement is not None:
        show_board(result.placement)


def run_min_conflicts(args: argparse.Namespace) -> None:
    solver = MinConflictsSolver(SELECTORS[args.selector](), max_steps=args.max_steps)
    result = solver.solve_with_restarts(args.n, args.seed)
    print(f"N={result.n} [{result.selector}]: solved={result.solved}, steps={result.steps}, "
          f"{result.seconds * 1000:.2f} ms, remaining conflicts={result.remaining_conflicts}")
    if result.placement is not None:
        show_board(result.placement)


def report(table, filename: str) -> None:
    print(table)
    path = os.path.join(RESULTS_DIR, filename)
    table.save_csv(path)
    print(f"\nSaved to {path}\nMeasured on: {machine_description()}")


def run_sat_experiment(args: argparse.Namespace) -> None:
    sizes = args.sizes or SatExperiment.DEFAULT_SIZES
    table = SatExperiment(sizes, args.repeats).run(lambda n: print(f"  running N={n}", flush=True))
    report(table, "sat_experiment.csv")


def run_encoding_experiment(args: argparse.Namespace) -> None:
    from nqueens.experiments import EncodingExperiment

    sizes = args.sizes or EncodingExperiment.DEFAULT_SIZES
    table = EncodingExperiment(sizes, args.repeats).run(lambda n: print(f"  running N={n}", flush=True))
    report(table, "encoding_experiment.csv")


def run_min_conflicts_experiment(args: argparse.Namespace) -> None:
    sizes = args.sizes or MinConflictsExperiment.DEFAULT_SIZES
    table = MinConflictsExperiment(sizes, args.seeds).run(
        lambda n: print(f"  running N={n}", flush=True)
    )
    report(table, "min_conflicts_experiment.csv")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N-Queens: Glucose3 and Min-Conflicts")
    commands = parser.add_subparsers(dest="command", required=True)

    sat = commands.add_parser("sat", help="solve one board with Glucose3")
    sat.add_argument("--n", type=int, default=8)
    sat.add_argument("--encoding", choices=sorted(AT_MOST_ONE_ENCODINGS), default="pairwise")
    sat.set_defaults(handler=run_sat)

    local = commands.add_parser("minconflicts", help="solve one board with Min-Conflicts")
    local.add_argument("--n", type=int, default=8)
    local.add_argument("--selector", choices=sorted(SELECTORS), default="tabu")
    local.add_argument("--seed", type=int, default=0)
    local.add_argument("--max-steps", type=int, default=None)
    local.set_defaults(handler=run_min_conflicts)

    sat_exp = commands.add_parser("experiment-sat", help="clauses and time for increasing N")
    sat_exp.add_argument("--sizes", type=int, nargs="+")
    sat_exp.add_argument("--repeats", type=int, default=3)
    sat_exp.set_defaults(handler=run_sat_experiment)

    encoding_exp = commands.add_parser("experiment-encoding", help="pairwise vs sequential counter")
    encoding_exp.add_argument("--sizes", type=int, nargs="+")
    encoding_exp.add_argument("--repeats", type=int, default=3)
    encoding_exp.set_defaults(handler=run_encoding_experiment)

    local_exp = commands.add_parser("experiment-minconflicts", help="heuristic vs standard")
    local_exp.add_argument("--sizes", type=int, nargs="+")
    local_exp.add_argument("--seeds", type=int, default=100)
    local_exp.set_defaults(handler=run_min_conflicts_experiment)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
