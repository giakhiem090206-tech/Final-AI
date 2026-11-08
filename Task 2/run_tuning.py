"""Tunes the evaluation weights by hill climbing on game results (run from the `Task 2` folder).

    python run_tuning.py --iterations 80

A candidate changes one or two weights at random and is kept if it scores better against
the previous version and the sparring partners.

The tuning plays on random maps. A first attempt on five fixed maps reached a high score
there and then lost to the previous version on two maps it had not seen: it had learned
those five maps. run_experiments.py reports on random maps from other seeds and on the
built-in maps, so the published strength is not a measure of memorising the tuning games.
"""
from __future__ import annotations

import argparse
import dataclasses
import random
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Sequence

from tank_battle.evaluation import RaceWeights
from tank_battle.experiments import SPARRING_PARTNERS, AgentRecipe, OpeningBook, duel, previous_version
from tank_battle.maps import random_map
from tank_battle.search import SearchConfig

TUNING_MAP_SEEDS = range(0, 60)  # the experiments use seeds from 1000 on
TUNED = tuple(field.name for field in dataclasses.fields(RaceWeights))
SEARCHED = TUNED + ("repetition_penalty",)
DEPTH = 2


def recipe(values: Dict[str, float]) -> AgentRecipe:
    weights = tuple((name, values[name]) for name in TUNED)
    config = dataclasses.replace(SearchConfig.optimized(), repetition_penalty=values["repetition_penalty"])
    return AgentRecipe("candidate", config, weights=weights, depth=DEPTH)


def objective(values: Dict[str, float], opponents: Sequence[AgentRecipe], openings, pool) -> float:
    """Mean score over the opponents, so one easy opponent cannot hide a weakness to another."""
    scores = [duel(recipe(values), opponent, openings, pool).score for opponent in opponents]
    return sum(scores) / len(scores)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--openings", type=int, default=60)
    parser.add_argument("--seed", type=int, default=1000)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    openings = OpeningBook.generate(args.openings, args.seed, [random_map(seed) for seed in TUNING_MAP_SEEDS])
    opponents = (previous_version(depth=DEPTH),) + SPARRING_PARTNERS
    current = dataclasses.asdict(RaceWeights())
    current["repetition_penalty"] = SearchConfig.optimized().repetition_penalty

    start = time.time()
    with ProcessPoolExecutor() as pool:
        best = objective(current, opponents, openings, pool)
        print(f"start: score {best:.4f}", flush=True)
        for iteration in range(1, args.iterations + 1):
            candidate = dict(current)
            for name in rng.sample(SEARCHED, rng.choice((1, 1, 2))):
                factor = rng.choice((0.5, 0.67, 0.8, 1.25, 1.5, 2.0))
                candidate[name] = round(candidate[name] * factor, 3)
            score = objective(candidate, opponents, openings, pool)
            if score > best:
                best, current = score, candidate
                print(f"{iteration:>3} [{time.time() - start:6.0f}s] improved to {best:.4f}: {current}", flush=True)
            elif iteration % 10 == 0:
                print(f"{iteration:>3} [{time.time() - start:6.0f}s] best so far {best:.4f}", flush=True)
    print(f"\nBest score {best:.4f}\n{current}")


if __name__ == "__main__":
    main()
