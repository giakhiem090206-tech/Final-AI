"""Propositional-logic model of N-Queens and its conversion to CNF.

One Boolean variable per square: Q(r, c) is True iff the square holds a queen.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Dict, Iterable, List, Tuple

Square = Tuple[int, int]
Clause = List[int]


class SquareVariables:
    """Bijection between squares and DIMACS variables 1 .. N^2."""

    def __init__(self, n: int) -> None:
        self.n = n

    @property
    def count(self) -> int:
        return self.n * self.n

    def variable(self, row: int, col: int) -> int:
        return row * self.n + col + 1

    def square(self, variable: int) -> Square:
        return divmod(variable - 1, self.n)


@dataclass(frozen=True)
class AttackLine:
    """A maximal row, column or diagonal: any two of its squares attack each other."""

    kind: str
    key: int
    squares: Tuple[Square, ...]


class ConstraintDiscovery:
    """Discovers the constraints by one scan of the board.

    Two squares attack each other iff they share one of four keys:
    r (row), c (column), r - c (diagonal), r + c (anti-diagonal).
    Grouping squares by key yields every attack line in O(N^2), and each attacking
    pair of squares falls in exactly one line, so no clause is ever generated twice.
    """

    ROW, COLUMN, DIAGONAL, ANTI_DIAGONAL = "row", "column", "diagonal", "anti-diagonal"

    def __init__(self, n: int) -> None:
        self.n = n

    @classmethod
    def line_keys(cls, r: int, c: int) -> Tuple[Tuple[str, int], ...]:
        """The four lines through (r, c). Two squares attack each other iff they share a key."""
        return (cls.ROW, r), (cls.COLUMN, c), (cls.DIAGONAL, r - c), (cls.ANTI_DIAGONAL, r + c)

    def attack_lines(self) -> List[AttackLine]:
        groups: Dict[Tuple[str, int], List[Square]] = {}
        for r in range(self.n):
            for c in range(self.n):
                for group in self.line_keys(r, c):
                    groups.setdefault(group, []).append((r, c))
        return [AttackLine(kind, key, tuple(squares)) for (kind, key), squares in groups.items()]


@dataclass
class CnfFormula:
    """A CNF formula in the DIMACS list-of-lists form that PySAT accepts."""

    num_variables: int
    clauses: List[Clause]

    @property
    def num_clauses(self) -> int:
        return len(self.clauses)


def at_most_one(literals: List[int]) -> List[Clause]:
    """AtMostOne(x1..xk) in pairwise form: for each pair i < j, NOT(xi AND xj),
    which De Morgan rewrites as (-xi v -xj). C(k,2) clauses, hence Theta(N^3) on the board."""
    return [[-a, -b] for a, b in combinations(literals, 2)]


class CnfEncoder:
    """Turns the attack lines into CNF.

    Rows and columns:   ExactlyOne(line) = AtLeastOne(line) AND AtMostOne(line)
    Diagonals:          AtMostOne(line)

    AtLeastOne(x1..xk)  is already one clause: (x1 v ... v xk).
    AtMostOne(x1..xk)   is the pairwise form, see at_most_one().
    """

    def __init__(self, n: int) -> None:
        if n < 1:
            raise ValueError("N must be positive")
        self.n = n
        self.variables = SquareVariables(n)
        self.discovery = ConstraintDiscovery(n)

    def _literals(self, line: AttackLine) -> List[int]:
        return [self.variables.variable(r, c) for r, c in line.squares]

    def encode(self) -> CnfFormula:
        clauses: List[Clause] = []
        for line in self.discovery.attack_lines():
            literals = self._literals(line)
            if line.kind in (ConstraintDiscovery.ROW, ConstraintDiscovery.COLUMN):
                clauses.append(literals)
            clauses.extend(at_most_one(literals))
        return CnfFormula(self.variables.count, clauses)

    def clause_breakdown(self) -> Dict[str, int]:
        """Clauses of each kind, counted from the attack lines without building them."""
        counts = {"at_least_one": 0, "at_most_one_lines": 0, "at_most_one_diagonals": 0}
        for line in self.discovery.attack_lines():
            pairs = comb(len(line.squares), 2)
            if line.kind in (ConstraintDiscovery.ROW, ConstraintDiscovery.COLUMN):
                counts["at_least_one"] += 1
                counts["at_most_one_lines"] += pairs
            else:
                counts["at_most_one_diagonals"] += pairs
        return counts

    @staticmethod
    def attacked_squares(n: int, row: int, col: int) -> int:
        """Squares sharing a row, column or diagonal with (row, col)."""
        diagonal = n - abs(row - col)
        anti_diagonal = n - abs(row + col - (n - 1))
        return 2 * (n - 1) + (diagonal - 1) + (anti_diagonal - 1)

    @classmethod
    def clauses_with_square(cls, n: int, row: int, col: int) -> int:
        """Clauses that mention Q(row, col): its row's and column's at-least-one clause,
        and one at-most-one clause for each square it attacks. N = 1 has a single line
        that is both the row and the column, still two clauses."""
        return 2 + cls.attacked_squares(n, row, col)

    def queens_in_model(self, model: Iterable[int]) -> Tuple[Square, ...]:
        """The squares whose variable is true in the model."""
        return tuple(self.variables.square(lit) for lit in model if 0 < lit <= self.variables.count)

    @staticmethod
    def expected_clause_count(n: int) -> int:
        """Pairwise encoding, closed form: 2N + 2N*C(N,2) + 2*C(N,2) + 4*C(N,3), Theta(N^3).

        2N          at-least-one on rows and columns
        2N*C(N,2)   at-most-one on rows and columns
        2*C(N,2) + 4*C(N,3)   at-most-one on both diagonal directions, since one
                    direction contributes 2*sum(C(L,2), L=1..N-1) + C(N,2).
        """
        return 2 * n + 2 * n * comb(n, 2) + 2 * comb(n, 2) + 4 * comb(n, 3)
