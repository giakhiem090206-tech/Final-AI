"""Solves the CNF model with the Glucose3 solver from PySAT."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Optional

from pysat.solvers import Glucose3

from .board import Placement
from .encoding import AtMostOneEncoding, CnfEncoder


@dataclass
class SatResult:
    n: int
    satisfiable: bool
    placement: Optional[Placement]
    num_variables: int
    num_clauses: int
    encode_seconds: float
    load_seconds: float
    solve_seconds: float
    conflicts: int
    decisions: int

    @property
    def total_seconds(self) -> float:
        return self.encode_seconds + self.load_seconds + self.solve_seconds


class Glucose3QueensSolver:
    """Encodes N-Queens, runs Glucose3 and decodes the model into a placement."""

    def __init__(self, at_most_one: Optional[AtMostOneEncoding] = None) -> None:
        self.at_most_one = at_most_one

    def solve(self, n: int) -> SatResult:
        encoder = CnfEncoder(n, self.at_most_one)

        start = perf_counter()
        formula = encoder.encode()
        encoded = perf_counter()

        with Glucose3(bootstrap_with=formula.clauses) as solver:
            loaded = perf_counter()
            satisfiable = bool(solver.solve())
            solved = perf_counter()
            model = solver.get_model() if satisfiable else None
            stats = solver.accum_stats() or {}

        placement = Placement(n, encoder.queens_in_model(model)) if model is not None else None

        return SatResult(
            n=n,
            satisfiable=satisfiable,
            placement=placement,
            num_variables=formula.num_variables,
            num_clauses=formula.num_clauses,
            encode_seconds=encoded - start,
            load_seconds=loaded - encoded,
            solve_seconds=solved - loaded,
            conflicts=int(stats.get("conflicts", 0)),
            decisions=int(stats.get("decisions", 0)),
        )
