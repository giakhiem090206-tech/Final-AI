"""Entry point for Task 2 (run from the `Task 2` folder).

    python main.py                                   open the menu
    python main.py --p1 "Heuristic Alpha-Beta" --p2 plugins/example_function_agent.py --map Bunkers
    python main.py --headless --p1 NAME --p2 FILE.py --games 8    match without a window
    python main.py --list                            list available agents and maps
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Optional, Sequence

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)  # lets plugin files import tank_battle from anywhere

from tank_battle.maps import BUILTIN_MAPS, GameMap
from tank_battle.model import DRAW
from tank_battle.plugins import AgentCatalog
from tank_battle.session import HeadlessMatch

PLUGIN_DIR = os.path.join(PROJECT_DIR, "plugins")


def resolve_agent(catalog: AgentCatalog, reference: str) -> str:
    """A reference is an agent name, or the path of a Python file offering at least one agent."""
    if reference.endswith(".py"):
        return catalog.add_file(reference)[0]
    return reference


def resolve_map(args: argparse.Namespace) -> GameMap:
    if args.map_file:
        return GameMap.from_file(args.map_file, os.path.basename(args.map_file))
    return BUILTIN_MAPS[args.map]


def run_headless(args: argparse.Namespace, catalog: AgentCatalog, first: str, second: str) -> None:
    game_map = resolve_map(args)
    tally: Counter = Counter()
    faults = {first: 0, second: 0}
    for game in range(args.games):
        names = (second, first) if game % 2 else (first, second)  # alternate sides
        agents = (catalog.create(names[0]), catalog.create(names[1]))
        result = HeadlessMatch(game_map.create_state(), agents, args.time_limit).play()
        winner = "draw" if result.outcome == DRAW else names[result.outcome]
        tally[winner] += 1
        faults[names[0]] += result.records[0].faults
        faults[names[1]] += result.records[1].faults
        print(f"Game {game + 1}: P1={names[0]} P2={names[1]} -> {winner} in {result.cycles} cycles")
    print(f"\nTotals over {args.games} games on {game_map.name}:")
    for name in (first, second, "draw"):
        print(f"  {name}: {tally[name]}")
    print(f"Faults (crash, invalid action or timeout): {faults}")


def run_gui(args: argparse.Namespace, catalog: AgentCatalog, first: Optional[str], second: Optional[str]) -> None:
    from tank_battle.gui import TankBattleApp

    app = TankBattleApp(catalog)
    if first and second:
        app.start_game(first, second, resolve_map(args), args.time_limit)
    app.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Turn-based Tank Battle")
    parser.add_argument("--p1", help="agent name, or path of a plugin .py file")
    parser.add_argument("--p2", help="agent name, or path of a plugin .py file")
    parser.add_argument("--map", choices=list(BUILTIN_MAPS), default="Corridors")
    parser.add_argument("--map-file", help="load a map from a text file instead")
    parser.add_argument("--time-limit", type=float, default=0.2, help="seconds per decision (default 0.2)")
    parser.add_argument("--headless", action="store_true", help="no window, print the results")
    parser.add_argument("--games", type=int, default=2, help="number of headless games")
    parser.add_argument("--list", action="store_true", help="list agents and maps, then exit")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    catalog = AgentCatalog(PLUGIN_DIR)

    if args.list:
        print("Agents:", *(f"  {name}" for name in catalog.names()), sep="\n")
        print("Maps:", *(f"  {name}" for name in BUILTIN_MAPS), sep="\n")
        for filename, reason in catalog.errors.items():
            print(f"Could not load plugin {filename}: {reason}")
        return

    first = resolve_agent(catalog, args.p1) if args.p1 else None
    second = resolve_agent(catalog, args.p2) if args.p2 else None
    if args.headless:
        if not (first and second):
            parser.error("--headless needs both --p1 and --p2")
        run_headless(args, catalog, first, second)
    else:
        run_gui(args, catalog, first, second)


if __name__ == "__main__":
    main()
