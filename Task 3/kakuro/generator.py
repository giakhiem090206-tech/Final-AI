"""Generates random Kakuro boards, to test the solver on more than the two boards of the statement.

A board is built in three steps: a random pattern of black cells that respects the rules
(runs of 2 to 9 cells), a random filling with digits that do not repeat in any run, and the
clues that this filling implies. Every generated board therefore has at least one solution.
"""
from __future__ import annotations

import random
from typing import List, Optional, Tuple

from .csp import KakuroCSP
from .puzzle import KakuroPuzzle
from .solver import BacktrackingSolver, SolverConfig

Grid = List[List[bool]]  # True marks a white cell


class BoardGenerator:
    # A budget in assignments rather than seconds: the same seed must give the same board on any machine.
    SEARCH_BUDGET = 100_000

    def __init__(self, height: int, width: int, black_density: float = 0.22, seed: int = 0) -> None:
        self.height = height
        self.width = width
        self.black_density = black_density
        self.rng = random.Random(seed)

    def generate(self) -> KakuroPuzzle:
        """A board with at least one solution. Patterns that cannot be filled are drawn again."""
        while True:
            white = self._draw_pattern()
            digits = self._fill(white)
            if digits is not None:
                return KakuroPuzzle(f"Random {self.height}x{self.width}", self._board_text(white, digits))

    def generate_unique(self, max_repairs: int = 300, attempts: int = 5) -> Optional[KakuroPuzzle]:
        """A board with exactly one solution, or None if the repairs do not get there.

        Random fillings almost never give a unique solution (none of 4800 in a trial). So
        the filling is repaired: find a second solution, change a digit in a cell where the
        two differ, and try again. Each change alters clues that the rival solution relied on.
        """
        for _ in range(attempts):
            white = self._draw_pattern()
            digits = self._fill(white)
            if digits is None:
                continue
            for _ in range(max_repairs):
                puzzle = KakuroPuzzle(f"Random {self.height}x{self.width}", self._board_text(white, digits))
                result = BacktrackingSolver(KakuroCSP(puzzle), SolverConfig(),
                                            max_assignments=self.SEARCH_BUDGET).solve(max_solutions=2)
                own = [digits[r][c] for r, c in puzzle.cells]
                rival = next((solution for solution in result.solutions if solution != own), None)
                if rival is None:
                    # Only a search that ran to its end proves that no other solution exists.
                    if result.limit_reached:
                        break
                    return puzzle
                if not self._change_a_differing_digit(puzzle, white, digits, rival):
                    break
        return None

    def _change_a_differing_digit(self, puzzle: KakuroPuzzle, white: Grid, digits: List[List[int]],
                                  rival: List[int]) -> bool:
        differing = [(r, c) for index, (r, c) in enumerate(puzzle.cells) if digits[r][c] != rival[index]]
        self.rng.shuffle(differing)
        for r, c in differing:
            used = self._digits_in_runs(white, digits, r, c)
            options = [d for d in range(1, 10) if d not in used]
            if options:
                digits[r][c] = self.rng.choice(options)
                return True
        return False

    def _digits_in_runs(self, white: Grid, digits: List[List[int]], r: int, c: int) -> set:
        """Digits of the other cells in the two runs through (r, c); the cell's own digit counts as used."""
        used = {digits[r][c]}
        for d_row, d_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = r + d_row, c + d_col
            while 0 <= rr < self.height and 0 <= cc < self.width and white[rr][cc]:
                used.add(digits[rr][cc])
                rr, cc = rr + d_row, cc + d_col
        return used

    # ------------------------------------------------------------------- pattern
    def _draw_pattern(self) -> Grid:
        rng = self.rng
        while True:
            white = [[r > 0 and c > 0 and rng.random() >= self.black_density for c in range(self.width)]
                     for r in range(self.height)]
            self._repair(white)
            if sum(map(sum, white)) >= (self.height - 1) * (self.width - 1) // 2:
                return white

    def _repair(self, white: Grid) -> None:
        """Blacken cells until every run has between 2 and 9 cells."""
        changed = True
        while changed:
            changed = False
            for line, cells in self._all_lines():
                run: List[Tuple[int, int]] = []
                for r, c in cells + [(-1, -1)]:
                    if r >= 0 and white[r][c]:
                        run.append((r, c))
                        continue
                    if len(run) == 1:
                        white[run[0][0]][run[0][1]] = False
                        changed = True
                    elif len(run) > 9:
                        r2, c2 = run[self.rng.randrange(2, len(run) - 2)]
                        white[r2][c2] = False
                        changed = True
                    run = []

    def _all_lines(self) -> List[Tuple[int, List[Tuple[int, int]]]]:
        lines = [(r, [(r, c) for c in range(self.width)]) for r in range(self.height)]
        lines += [(c, [(r, c) for r in range(self.height)]) for c in range(self.width)]
        return lines

    # --------------------------------------------------------------------- filling
    def _fill(self, white: Grid, max_steps: int = 200_000) -> Optional[List[List[int]]]:
        """Random digits with no repeat in a row or column run, by randomized backtracking."""
        cells = [(r, c) for r in range(self.height) for c in range(self.width) if white[r][c]]
        digits = [[0] * self.width for _ in range(self.height)]
        steps = [0]

        def used_by_neighbours(r: int, c: int) -> set:
            used = set()
            for d_row, d_col in ((-1, 0), (0, -1)):  # cells are filled top-down and left to right
                rr, cc = r + d_row, c + d_col
                while rr >= 0 and cc >= 0 and white[rr][cc]:
                    used.add(digits[rr][cc])
                    rr, cc = rr + d_row, cc + d_col
            return used

        def place(index: int) -> bool:
            if index == len(cells):
                return True
            steps[0] += 1
            if steps[0] > max_steps:
                return False
            r, c = cells[index]
            options = [d for d in range(1, 10) if d not in used_by_neighbours(r, c)]
            self.rng.shuffle(options)
            for digit in options:
                digits[r][c] = digit
                if place(index + 1):
                    return True
            digits[r][c] = 0
            return False

        return digits if place(0) else None

    # ------------------------------------------------------------------------ text
    def _board_text(self, white: Grid, digits: List[List[int]]) -> str:
        rows = []
        for r in range(self.height):
            tokens = []
            for c in range(self.width):
                if white[r][c]:
                    tokens.append(".")
                    continue
                down = self._sum_from(white, digits, r, c, 1, 0)
                across = self._sum_from(white, digits, r, c, 0, 1)
                tokens.append(f"{down or ''}\\{across or ''}" if down or across else "X")
            rows.append(" ".join(tokens))
        return "\n".join(rows)

    def _sum_from(self, white: Grid, digits: List[List[int]], r: int, c: int, d_row: int, d_col: int) -> int:
        total = 0
        r, c = r + d_row, c + d_col
        while r < self.height and c < self.width and white[r][c]:
            total += digits[r][c]
            r, c = r + d_row, c + d_col
        return total
