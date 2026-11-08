"""Propositional-logic model of N-Queens and its conversion to CNF.

One Boolean variable per square: Q(r, c) is True iff the square holds a queen.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Dict, Iterable, List, Optional, Tuple

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

    def attack_lines(self) -> List[AttackLine]:
        groups: Dict[Tuple[str, int], List[Square]] = {}
        for r in range(self.n):
            for c in range(self.n):
                keys = (
                    (self.ROW, r),
                    (self.COLUMN, c),
                    (self.DIAGONAL, r - c),
                    (self.ANTI_DIAGONAL, r + c),
                )
                for group in keys:
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


class AuxiliaryVariables:
    """Hands out fresh variables numbered after the N^2 square variables."""

    def __init__(self, first: int) -> None:
        self.next = first

    def new(self) -> int:
        variable = self.next
        self.next += 1
        return variable


class AtMostOneEncoding(ABC):
    """A way of writing AtMostOne(x1..xk) as clauses."""

    name = "abstract"

    @abstractmethod
    def encode(self, literals: List[int], auxiliary: AuxiliaryVariables) -> List[Clause]:
        """Clauses that hold exactly when at most one of the literals is true."""


class PairwiseEncoding(AtMostOneEncoding):
    """For each pair i < j, NOT(xi AND xj), which De Morgan rewrites as (-xi v -xj).

    No extra variables, but C(k,2) clauses per line, hence Theta(N^3) on the whole board.
    """

    name = "pairwise"

    def encode(self, literals: List[int], auxiliary: AuxiliaryVariables) -> List[Clause]:
        return [[-a, -b] for a, b in combinations(literals, 2)]


class SequentialCounterEncoding(AtMostOneEncoding):
    """Sinz's sequential counter: 3k - 4 clauses and k - 1 extra variables per line.

    Each extra variable s_i means "some queen among x1..xi". The clauses say that a queen
    sets the counter, that a set counter stays set, and that no queen may follow a set
    counter. This gives Theta(N^2) clauses on the whole board. Below SHORT_LINE cells
    the pairwise form is the smaller of the two, so it is used there.
    """

    name = "sequential"
    SHORT_LINE = 5

    def encode(self, literals: List[int], auxiliary: AuxiliaryVariables) -> List[Clause]:
        if len(literals) <= self.SHORT_LINE:
            return [[-a, -b] for a, b in combinations(literals, 2)]
        counters = [auxiliary.new() for _ in literals[:-1]]
        clauses: List[Clause] = [[-literals[0], counters[0]]]
        for i in range(1, len(literals) - 1):
            clauses.append([-literals[i], counters[i]])
            clauses.append([-counters[i - 1], counters[i]])
            clauses.append([-literals[i], -counters[i - 1]])
        clauses.append([-literals[-1], -counters[-1]])
        return clauses


AT_MOST_ONE_ENCODINGS = {encoding.name: encoding for encoding in (PairwiseEncoding, SequentialCounterEncoding)}


class CnfEncoder:
    """Turns the attack lines into CNF.

    Rows and columns:   ExactlyOne(line) = AtLeastOne(line) AND AtMostOne(line)
    Diagonals:          AtMostOne(line)

    AtLeastOne(x1..xk)  is already one clause: (x1 v ... v xk).
    AtMostOne(x1..xk)   is delegated to an AtMostOneEncoding.

    The variables 1..N^2 are always the squares, so that decoding a model never depends
    on the encoding: only extra variables come after them.
    """

    def __init__(self, n: int, at_most_one: Optional[AtMostOneEncoding] = None) -> None:
        if n < 1:
            raise ValueError("N must be positive")
        self.n = n
        self.variables = SquareVariables(n)
        self.discovery = ConstraintDiscovery(n)
        self.at_most_one = at_most_one or PairwiseEncoding()

    def _literals(self, line: AttackLine) -> List[int]:
        return [self.variables.variable(r, c) for r, c in line.squares]

    def encode(self) -> CnfFormula:
        clauses: List[Clause] = []
        auxiliary = AuxiliaryVariables(self.variables.count + 1)
        for line in self.discovery.attack_lines():
            literals = self._literals(line)
            if line.kind in (ConstraintDiscovery.ROW, ConstraintDiscovery.COLUMN):
                clauses.append(literals)
            clauses.extend(self.at_most_one.encode(literals, auxiliary))
        return CnfFormula(auxiliary.next - 1, clauses)

    def queens_in_model(self, model: Iterable[int]) -> Tuple[Square, ...]:
        """The queens of a model, ignoring the encoding's extra variables."""
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
