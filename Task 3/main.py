"""Entry point for Task 3 (run from the `Task 3` folder).

    python main.py                                 open the visualizer
    python main.py --file board.txt                add a board from a text file to the visualizer
    python main.py --solve "Complex (9x9)"         solve in the terminal, without a window
"""
from __future__ import annotations

import argparse
from typing import Optional, Sequence

from kakuro.csp import KakuroCSP
from kakuro.puzzle import BUILTIN_PUZZLES, KakuroPuzzle, SolutionChecker, load_builtin, load_file
from kakuro.solver import BacktrackingSolver


def render_solution(puzzle: KakuroPuzzle, values: Sequence[int]) -> str:
    lines = []
    for r in range(puzzle.height):
        cells = [str(values[puzzle.cell_index(r, c)]) if puzzle.is_white(r, c) else "#" for c in range(puzzle.width)]
        lines.append(" ".join(cells))
    return "\n".join(lines)


def solve_in_terminal(puzzle: KakuroPuzzle) -> None:
    result = BacktrackingSolver(KakuroCSP(puzzle)).solve()
    stats = result.stats
    print(f"{puzzle.name}: {result.status}")
    print(f"{result.seconds * 1000:.2f} ms, {stats.assignments} assignments, {stats.backtracks} backtracks, "
          f"{stats.revisions} revisions")
    if result.solution is not None:
        print(render_solution(puzzle, result.solution))
        print(f"Independent check: {SolutionChecker(puzzle).problems(result.solution) or 'all rules satisfied'}")
        # Looking for a second solution makes the search finish and undo everything it tried.
        count = len(BacktrackingSolver(KakuroCSP(puzzle)).solve(max_solutions=2).solutions)
        print("Unique solution" if count == 1 else "This board has more than one solution")


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Kakuro CSP solver and visualizer")
    parser.add_argument("--solve", choices=list(BUILTIN_PUZZLES), help="solve a built-in board in the terminal")
    parser.add_argument("--file", help="a board in a text file (see kakuro/puzzle.py for the format)")
    parser.add_argument("--no-gui", action="store_true", help="with --file: solve in the terminal")
    args = parser.parse_args(argv)

    if args.solve:
        solve_in_terminal(load_builtin(args.solve))
        return
    if args.file and args.no_gui:
        solve_in_terminal(load_file(args.file))
        return

    from kakuro.gui import VisualizerApp

    puzzles = {name: load_builtin(name) for name in BUILTIN_PUZZLES}
    if args.file:
        puzzle = load_file(args.file)
        puzzles[puzzle.name] = puzzle
    VisualizerApp(puzzles).run()


if __name__ == "__main__":
    main()
