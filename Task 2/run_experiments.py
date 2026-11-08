"""Reproduces the Task 2 experiments (run from the `Task 2` folder).

    python run_experiments.py               # everything (the strength part takes the longest)
    python run_experiments.py --only depth  # or: time, ablation, tournament, strength, strength_time, depth_value
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor

from tank_battle.experiments import (
    SPARRING_PARTNERS,
    AgentRecipe,
    FixedDepthExperiment,
    FixedTimeExperiment,
    OpeningBook,
    OptimizationAblation,
    ResultTable,
    StrengthExperiment,
    TournamentExperiment,
    duel,
    machine_description,
    previous_version,
)
from tank_battle.maps import BUILTIN_MAPS, random_map
from tank_battle.search import SearchConfig

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
TOURNAMENT_MAPS = ("Duel", "Bunkers", "Crossroads", "Fortress")


def progress(text: str) -> None:
    print(f"  ... {text}", flush=True)


def report(title: str, table, filename: str) -> None:
    print(f"\n=== {title} ===\n{table}")
    table.save_csv(os.path.join(RESULTS_DIR, filename))


def held_out_openings():
    """Openings on random maps that run_tuning.py never used."""
    return OpeningBook.generate(120, seed=7000, maps=[random_map(seed) for seed in range(1000, 1060)])


def run_strength_time() -> None:
    """The new controller against the previous version, both with the same time per decision.

    Unlike the fixed-depth games, these depend on speed: a faster search goes deeper.
    """
    limit = 0.05
    candidate = AgentRecipe("New controller", SearchConfig.optimized(), time_limit=limit)
    # Few workers: with a time limit, games running side by side must not slow each other down.
    with ProcessPoolExecutor(max_workers=4) as pool:
        table = StrengthExperiment(candidate, (previous_version(time_limit=limit),), held_out_openings(),
                                   pool).run(progress)
    report(f"Strength on held-out random maps, both at {limit * 1000:.0f} ms per decision", table, "strength_time.csv")


def run_depth_value() -> None:
    """Does searching deeper win more games, and does the time the optimizations save turn into wins?

    Same held-out openings as the strength experiment, both sides of each.
    """
    openings = held_out_openings()
    optimized, plain = SearchConfig.optimized(), SearchConfig.heuristic_alpha_beta()
    table = ResultTable(["player", "opponent", "games", "wins", "draws", "losses", "score_pct", "mean_cycles"])

    def play(first: AgentRecipe, second: AgentRecipe, pool) -> None:
        progress(f"{first.label} vs {second.label}")
        result = duel(first, second, openings, pool)
        table.add(first.label, second.label, result.games, result.wins, result.draws, result.losses,
                  100.0 * result.score, result.mean_cycles)

    with ProcessPoolExecutor() as pool:  # fixed depth: games may run side by side
        for deep in (2, 3, 4, 5):
            play(AgentRecipe(f"Optimized, depth {deep}", optimized, depth=deep),
                 AgentRecipe(f"Optimized, depth {deep - 1}", optimized, depth=deep - 1), pool)
        for depth in (2, 3):
            play(AgentRecipe(f"Optimized, depth {depth}", optimized, depth=depth),
                 AgentRecipe(f"Heuristic Alpha-Beta, depth {depth}", plain, depth=depth), pool)
    limit = 0.05
    with ProcessPoolExecutor(max_workers=4) as pool:  # timed games must not slow each other down
        timed = {config.name: AgentRecipe(f"{config.name}, {limit * 1000:.0f} ms", config, time_limit=limit)
                 for config in (optimized, plain, SearchConfig.heuristic_minimax())}
        play(timed[plain.name], AgentRecipe("Heuristic Alpha-Beta, depth 3", plain, depth=3), pool)
        play(timed[optimized.name], timed[plain.name], pool)
        play(timed[optimized.name], timed["Heuristic Minimax"], pool)
        play(timed[plain.name], timed["Heuristic Minimax"], pool)
    report("Does depth win games? (held-out random maps)", table, "depth_value.csv")


def run_strength() -> None:
    """The new controller against the previous version and the sparring partners.

    None of these random maps were used by run_tuning.py, so a good score here means the
    improvement carries over to positions the tuning never saw. The built-in maps are
    reported separately: five of them were used in an early tuning attempt.
    """
    held_out = held_out_openings()
    built_in = OpeningBook.generate(70, seed=7001, maps=list(BUILTIN_MAPS))
    with ProcessPoolExecutor() as pool:  # fixed depth, so games may run side by side
        for depth in (2, 3, 4):
            candidate = AgentRecipe("New controller", SearchConfig.optimized(), depth=depth)
            opponents = (previous_version(depth=depth),) + SPARRING_PARTNERS
            table = StrengthExperiment(candidate, opponents, held_out, pool).run(progress)
            report(f"Strength on held-out random maps, both at depth {depth} cycles", table,
                   f"strength_depth{depth}.csv")
            table = StrengthExperiment(previous_version(depth=depth), SPARRING_PARTNERS, held_out, pool).run(progress)
            report(f"For comparison: the previous version on the same maps, depth {depth}", table,
                   f"strength_previous_depth{depth}.csv")
        candidate = AgentRecipe("New controller", SearchConfig.optimized(), depth=3)
        opponents = (previous_version(depth=3),) + SPARRING_PARTNERS
        table = StrengthExperiment(candidate, opponents, built_in, pool).run(progress)
        report("Strength on the built-in maps, both at depth 3 cycles", table, "strength_builtin.csv")
    run_strength_time()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["depth", "time", "ablation", "tournament", "strength", "strength_time",
                                           "depth_value"])
    args = parser.parse_args()
    print(f"Measured on: {machine_description()}")

    if args.only in (None, "strength"):
        run_strength()
    if args.only == "strength_time":
        run_strength_time()
    if args.only in (None, "depth_value"):
        run_depth_value()

    if args.only in (None, "depth"):
        report("Fixed depth", FixedDepthExperiment().run(progress), "fixed_depth.csv")
    if args.only in (None, "time"):
        report("Fixed time", FixedTimeExperiment().run(progress), "fixed_time.csv")
    if args.only in (None, "ablation"):
        report("What each optimization saves (fixed depth)", OptimizationAblation().run(progress), "ablation.csv")
    if args.only in (None, "tournament"):
        pairs, standing = TournamentExperiment.equal_depth(2, TOURNAMENT_MAPS).run(progress)
        report("Tournament, equal depth (2 cycles): pairs", pairs, "tournament_depth_pairs.csv")
        report("Tournament, equal depth (2 cycles): standing", standing, "tournament_depth_standing.csv")
        pairs, standing = TournamentExperiment.equal_time(0.02, TOURNAMENT_MAPS).run(progress)
        report("Tournament, equal time (20 ms per decision): pairs", pairs, "tournament_time_pairs.csv")
        report("Tournament, equal time (20 ms per decision): standing", standing, "tournament_time_standing.csv")


if __name__ == "__main__":
    main()
