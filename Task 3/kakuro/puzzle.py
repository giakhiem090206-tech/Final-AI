"""Reading and checking Kakuro boards.

A board is text with one token per cell, separated by spaces:

    X        black cell without a clue
    .        white cell to fill in
    D\\A      clue cell: D is the sum of the white cells below it, A of those to its right.
             Either side may be left empty, as in `21\\` (down only) or `\\12` (across only).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple


class PuzzleError(ValueError):
    """The text does not describe a well-formed Kakuro board."""


ACROSS, DOWN = "across", "down"


@dataclass(frozen=True)
class ClueCell:
    row: int
    col: int
    down: Optional[int]
    across: Optional[int]


@dataclass(frozen=True)
class Run:
    """A maximal group of white cells governed by one clue."""

    index: int
    direction: str
    clue: int
    cells: Tuple[int, ...]  # variable indices
    start: Tuple[int, int]  # (row, col) of the clue cell

    @property
    def label(self) -> str:
        return f"{self.direction} r{self.start[0] + 1}c{self.start[1] + 1} = {self.clue}"


class KakuroPuzzle:
    """A parsed board: its grid, its white cells (variables) and its runs (constraints)."""

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.grid: List[List[str]] = [line.split() for line in text.strip().splitlines() if line.strip()]
        if not self.grid or any(len(row) != len(self.grid[0]) for row in self.grid):
            raise PuzzleError(f"{name}: rows must all have the same number of cells")
        self.height = len(self.grid)
        self.width = len(self.grid[0])
        self.clues: Dict[Tuple[int, int], ClueCell] = {}
        self.cells: List[Tuple[int, int]] = []
        self._cell_index: Dict[Tuple[int, int], int] = {}
        self._read_tokens()
        self.runs: List[Run] = self._build_runs()
        self._check_every_cell_has_two_runs()

    def _read_tokens(self) -> None:
        for r, row in enumerate(self.grid):
            for c, token in enumerate(row):
                if token == ".":
                    self._cell_index[(r, c)] = len(self.cells)
                    self.cells.append((r, c))
                elif "\\" in token:
                    down, across = token.split("\\", 1)
                    try:
                        self.clues[(r, c)] = ClueCell(r, c, int(down) if down else None,
                                                      int(across) if across else None)
                    except ValueError as error:
                        raise PuzzleError(f"{self.name}: bad clue '{token}' at r{r + 1}c{c + 1}") from error
                elif token != "X":
                    raise PuzzleError(f"{self.name}: unknown token '{token}' at r{r + 1}c{c + 1}")

    def is_white(self, row: int, col: int) -> bool:
        return (row, col) in self._cell_index

    def cell_index(self, row: int, col: int) -> int:
        return self._cell_index[(row, col)]

    def cell_name(self, index: int) -> str:
        row, col = self.cells[index]
        return f"r{row + 1}c{col + 1}"

    def _collect(self, row: int, col: int, d_row: int, d_col: int) -> Tuple[int, ...]:
        cells = []
        r, c = row + d_row, col + d_col
        while 0 <= r < self.height and 0 <= c < self.width and self.is_white(r, c):
            cells.append(self.cell_index(r, c))
            r, c = r + d_row, c + d_col
        return tuple(cells)

    def _build_runs(self) -> List[Run]:
        runs: List[Run] = []
        for (r, c), clue in sorted(self.clues.items()):
            for direction, total, step in ((ACROSS, clue.across, (0, 1)), (DOWN, clue.down, (1, 0))):
                cells = self._collect(r, c, *step)
                where = f"{self.name}: {direction} clue at r{r + 1}c{c + 1}"
                if total is None:
                    if cells:
                        raise PuzzleError(f"{where}: white cells follow but there is no clue")
                    continue
                if not cells:
                    raise PuzzleError(f"{where}: no white cells to sum")
                if len(cells) > 9:
                    raise PuzzleError(f"{where}: {len(cells)} cells cannot hold distinct digits")
                if not sum_is_possible(total, len(cells)):
                    raise PuzzleError(f"{where}: no {len(cells)} distinct digits sum to {total}")
                runs.append(Run(len(runs), direction, total, cells, (r, c)))
        return runs

    def _check_every_cell_has_two_runs(self) -> None:
        counts = {index: {ACROSS: 0, DOWN: 0} for index in range(len(self.cells))}
        for run in self.runs:
            for cell in run.cells:
                counts[cell][run.direction] += 1
        for index, count in counts.items():
            if count[ACROSS] != 1 or count[DOWN] != 1:
                raise PuzzleError(f"{self.name}: {self.cell_name(index)} must belong to one across "
                                  f"and one down run")


def sum_is_possible(total: int, length: int) -> bool:
    return any(sum(combo) == total for combo in combinations(range(1, 10), length))


class SolutionChecker:
    """Checks a solution against the board text itself, not against the solver's model.

    It walks the grid again to find the runs, so an error in the CSP model or in the
    solver cannot agree with itself and pass unnoticed.
    """

    def __init__(self, puzzle: KakuroPuzzle) -> None:
        self.puzzle = puzzle

    def problems(self, values: Sequence[int]) -> List[str]:
        """Every broken rule; an empty list means the solution is valid."""
        puzzle = self.puzzle
        found: List[str] = []
        if len(values) != len(puzzle.cells):
            return [f"expected {len(puzzle.cells)} values, got {len(values)}"]
        for index, value in enumerate(values):
            if not 1 <= value <= 9:
                found.append(f"{puzzle.cell_name(index)} holds {value}, not a digit from 1 to 9")
        value_at = {cell: values[i] for i, cell in enumerate(puzzle.cells)}
        for r, row in enumerate(puzzle.grid):
            for c, token in enumerate(row):
                if "\\" not in token:
                    continue
                down, across = token.split("\\", 1)
                for text, d_row, d_col in ((down, 1, 0), (across, 0, 1)):
                    if not text:
                        continue
                    digits = []
                    rr, cc = r + d_row, c + d_col
                    while (rr, cc) in value_at:
                        digits.append(value_at[(rr, cc)])
                        rr, cc = rr + d_row, cc + d_col
                    if sum(digits) != int(text):
                        found.append(f"clue {text} at r{r + 1}c{c + 1}: {digits} sums to {sum(digits)}")
                    if len(set(digits)) != len(digits):
                        found.append(f"clue {text} at r{r + 1}c{c + 1}: {digits} repeats a digit")
        return found

    def is_valid(self, values: Sequence[int]) -> bool:
        return not self.problems(values)


EXAMPLE_BOARD = r"""
X     X      21\   14\   X
X     14\12  .     .     11\
\21   .      .     .     .
\11   .      .     .     .
X     \16    .     .     X
"""

COMPLEX_BOARD = r"""
X     X      44\   16\   9\    X      15\   44\   X
X     \22    .     .     .     11\3   .     .     14\
X     17\28  .     .     .     .      .     .     .
\14   .      .     X     12\20 .      .     .     .
\17   .      .     29\22 .     .      .     .     7\
X     12\28  .     .     .     .      \12   .     .
\14   .      .     .     .     7\     12\6  .     .
\39   .      .     .     .     .      .     .     X
X     \16    .     .     \8    .      .     .     X
"""

# Not from the statement. MAC solves both boards above without any search, which leaves
# nothing to see of backtracking under MAC. This one, from BoardGenerator(10, 10, 0.27, 18),
# makes MAC search for real. Like most random boards it has many solutions (at least 50).
EXTRA_BOARD = r"""
X      X      16\    11\    X      35\    23\    9\     X      X
X      \17    .      .      22\14  .      .      .      X      X
X      \26    .      .      .      .      .      .      X      X
X      X      X      14\21  .      .      .      X      X      X
X      X      24\14  .      .      .      .      X      X      X
X      27\7   .      .      \13    .      .      21\    9\     X
\17    .      .      .      \25    .      .      .      .      X
\9     .      .      7\     X      13\    13\3   .      .      X
\19    .      .      .      \20    .      .      .      X      X
\18    .      .      .      \21    .      .      .      X      X
"""

EXTRA_BOARD_NAME = "Extra (10x10)"
STATEMENT_PUZZLES = {
    "Example (5x5)": EXAMPLE_BOARD,
    "Complex (9x9)": COMPLEX_BOARD,
}
BUILTIN_PUZZLES = {**STATEMENT_PUZZLES, EXTRA_BOARD_NAME: EXTRA_BOARD}


def load_builtin(name: str) -> KakuroPuzzle:
    return KakuroPuzzle(name, BUILTIN_PUZZLES[name])


def load_file(path: str) -> KakuroPuzzle:
    with open(path, encoding="utf-8") as handle:
        return KakuroPuzzle(path, handle.read())
