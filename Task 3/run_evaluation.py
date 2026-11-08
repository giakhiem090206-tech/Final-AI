"""Reproduces the Task 3 evaluation (run from the `Task 3` folder).

    python run_evaluation.py
"""
from __future__ import annotations

import os

from kakuro.evaluation import (
    CorrectnessEvaluation,
    EffectivenessEvaluation,
    HardBoardEvaluation,
    StabilityEvaluation,
    machine_description,
)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def report(title: str, table, filename: str) -> None:
    print(f"\n=== {title} ===\n{table}")
    table.save_csv(os.path.join(RESULTS_DIR, filename))


def main() -> None:
    print(f"Measured on: {machine_description()}")
    report("Correctness", CorrectnessEvaluation().run(), "correctness.csv")
    report("Effectiveness", EffectivenessEvaluation().run(), "effectiveness.csv")
    report("Stability", StabilityEvaluation().run(lambda text: print(f"  ... {text}", flush=True)), "stability.csv")
    report("Hard random boards", HardBoardEvaluation().run(lambda text: print(f"  ... {text}", flush=True)), "hard_boards.csv")


if __name__ == "__main__":
    main()
