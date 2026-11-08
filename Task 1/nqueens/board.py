"""Solver-independent representation and validation of a queen placement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class Placement:
    """A set of queens on an N x N board, as (row, col) squares."""

    n: int
    queens: Tuple[Tuple[int, int], ...]

    @classmethod
    def from_columns(cls, columns: Sequence[int]) -> "Placement":
        """Build a placement from `columns[row] = column of the queen in that row`."""
        return cls(len(columns), tuple((row, col) for row, col in enumerate(columns)))

    def attacking_pairs(self) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Every pair of queens attacking each other, checked directly from the chess rules."""
        pairs = []
        for i, (r1, c1) in enumerate(self.queens):
            for r2, c2 in self.queens[i + 1:]:
                if r1 == r2 or c1 == c2 or abs(r1 - r2) == abs(c1 - c2):
                    pairs.append(((r1, c1), (r2, c2)))
        return pairs

    def is_solution(self) -> bool:
        """True when exactly N on-board queens stand on distinct squares without attacks.

        This deliberately ignores the CNF and the CSP model, so a bug in an encoding
        or in a solver cannot hide itself from the check.
        """
        if len(self.queens) != self.n or len(set(self.queens)) != self.n:
            return False
        if any(not (0 <= r < self.n and 0 <= c < self.n) for r, c in self.queens):
            return False
        return not self.attacking_pairs()

    def render(self) -> str:
        """ASCII drawing of the board."""
        occupied = set(self.queens)
        return "\n".join(
            " ".join("Q" if (r, c) in occupied else "." for c in range(self.n))
            for r in range(self.n)
        )
