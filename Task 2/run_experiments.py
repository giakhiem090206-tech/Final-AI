"""Reproduces the Task 2 experiments (run from the `Task 2` folder).

    python run_experiments.py               # both experiments
    python run_experiments.py --only depth  # the four configurations at the same depth
    python run_experiments.py --only time   # the four configurations with the same time per decision
"""
from __future__ import annotations

import argparse
import os

from tank_battle.experiments import FixedDepthExperiment, FixedTimeExperiment, machine_description

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def progress(text: str) -> None:
    print(f"  ... {text}", flush=True)


def report(title: str, table, filename: str) -> None:
    print(f"\n=== {title} ===\n{table}")
    table.save_csv(os.path.join(RESULTS_DIR, filename))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["depth", "time"])
    args = parser.parse_args()
    print(f"Measured on: {machine_description()}")
    if args.only in (None, "depth"):
        report("Fixed depth", FixedDepthExperiment().run(progress), "fixed_depth.csv")
    if args.only in (None, "time"):
        report("Fixed time", FixedTimeExperiment().run(progress), "fixed_time.csv")


if __name__ == "__main__":
    main()
