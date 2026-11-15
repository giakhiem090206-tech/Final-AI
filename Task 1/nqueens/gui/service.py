"""Runs one solver for the interface and turns its result into what the screens show.

No PyGame here: the interface calls it from a worker thread, and the tests call it directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..board import Placement
from ..encoding import CnfEncoder
from ..min_conflicts import SELECTORS, MinConflictsSolver, MinConflictsTrace
from .replay import MinConflictsPlayer

Square = Tuple[int, int]


@dataclass(frozen=True)
class Algorithm:
    key: str
    title: str
    subtitle: str

    @property
    def is_local_search(self) -> bool:
        return self.key != "sat"


ALGORITHMS = (
    Algorithm("sat", "Glucose3 (SAT)", "Mã hóa CNF rồi giải bằng PySAT"),
    Algorithm("standard", "Min-Conflicts chuẩn", "Chọn ngẫu nhiên một biến đang xung đột"),
    Algorithm("tabu", "Min-Conflicts + heuristic", "Biến xung đột nhiều nhất, kèm danh sách tabu"),
)


@dataclass
class Outcome:
    """The result of one run, ready to display."""

    algorithm: Algorithm
    n: int
    status: str  # "solved", "unsat" (proved impossible), "unsolved" (gave up) or "error"
    placement: Optional[Placement] = None
    stats: List[Tuple[str, str]] = field(default_factory=list)
    player: Optional[MinConflictsPlayer] = None
    error: str = ""
    fixed: Tuple[Square, ...] = ()  # queens placed by hand before solving
    valid: bool = False  # the placement passed the chess-rule check, independent of the solver


def _checked(outcome: Outcome) -> Outcome:
    """Check a returned placement against the chess rules (once) and report it."""
    if outcome.placement is not None:
        outcome.valid = outcome.placement.is_solution()
        outcome.stats.append(("Kiểm tra lại bằng luật cờ", "hợp lệ" if outcome.valid else "SAI"))
    return outcome


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.2f}"


class SolverService:
    BREAKDOWN_LABELS = (
        ("at_least_one", "Ít nhất một hậu trên mỗi hàng, cột"),
        ("at_most_one_lines", "Nhiều nhất một hậu trên mỗi hàng, cột"),
        ("at_most_one_diagonals", "Nhiều nhất một hậu trên mỗi đường chéo"),
    )

    def __init__(self) -> None:
        self._breakdowns: Dict[int, List[Tuple[str, int]]] = {}

    def run(self, algorithm: Algorithm, n: int, seed: int, fixed: Sequence[Square] = ()) -> Outcome:
        """`fixed`: queens placed by hand. Glucose3 must keep them (assumptions);
        Min-Conflicts starts from them (at most one per row) and may move them."""
        fixed = tuple(sorted(fixed))
        try:
            if algorithm.is_local_search:
                return self._min_conflicts(algorithm, n, seed, fixed)
            return self._sat(algorithm, n, fixed)
        except Exception as error:  # a missing package or a solver error is shown in the window
            return Outcome(algorithm, n, "error", error=str(error) or type(error).__name__, fixed=fixed)

    def cnf_breakdown(self, n: int) -> List[Tuple[str, int]]:
        """(label, clause count) for each kind of clause of the N x N model."""
        if n not in self._breakdowns:
            counts = CnfEncoder(n).clause_breakdown()
            self._breakdowns[n] = [(label, counts[key]) for key, label in self.BREAKDOWN_LABELS]
        return self._breakdowns[n]

    @staticmethod
    def _sat(algorithm: Algorithm, n: int, fixed: Tuple[Square, ...]) -> Outcome:
        from ..sat_solver import Glucose3QueensSolver  # imports PySAT

        result = Glucose3QueensSolver().solve(n, fixed)
        stats = [
            ("Kết quả", "SAT" if result.satisfiable else "UNSAT"),
            ("Biến · mệnh đề CNF", f"{result.num_variables:,} · {result.num_clauses:,}"),
            ("Mã hóa · nạp · giải", f"{_ms(result.encode_seconds)} · {_ms(result.load_seconds)} · "
                                    f"{_ms(result.solve_seconds)} ms"),
            ("Tổng thời gian", f"{_ms(result.total_seconds)} ms"),
            ("Xung đột · quyết định", f"{result.conflicts:,} · {result.decisions:,}"),
        ]
        if fixed:
            stats.insert(1, ("Hậu đặt sẵn (giả định)", str(len(fixed))))
        status = "solved" if result.satisfiable else "unsat"
        return _checked(Outcome(algorithm, n, status, result.placement, stats, fixed=fixed))

    def _min_conflicts(self, algorithm: Algorithm, n: int, seed: int, fixed: Tuple[Square, ...]) -> Outcome:
        initial = None
        if fixed:  # the hand-placed queens; rows left empty keep the seed's random column
            initial = MinConflictsSolver.random_assignment(n, seed)
            for row, col in fixed:
                initial[row] = col
        trace = MinConflictsTrace()
        result = MinConflictsSolver(SELECTORS[algorithm.key]()).solve_with_restarts(
            n, seed, trace=trace, initial=initial)
        # The other strategy from the same initial assignments: the comparison of requirement 3.
        other_key = "tabu" if algorithm.key == "standard" else "standard"
        other = MinConflictsSolver(SELECTORS[other_key]()).solve_with_restarts(n, seed, initial=initial)
        steps = f"{result.steps:,}"
        if result.restarts:
            steps += f" ({result.restarts} lần khởi động lại)"
        stats = [
            ("Kết quả", "Tìm thấy lời giải" if result.solved else "Chưa tìm thấy"),
            ("Số bước", steps),
            ("Thời gian tìm kiếm", f"{_ms(result.seconds)} ms"),
            ("Cặp tấn công còn lại", str(result.remaining_conflicts)),
            ("Heuristic, cùng seed" if other_key == "tabu" else "Chuẩn, cùng seed",
             f"{other.steps:,} bước" + ("" if other.solved else " (chưa giải)")),
        ]
        if fixed:
            stats.insert(1, ("Bắt đầu từ", f"{len(fixed)} hậu bạn đặt"))
        status = "solved" if result.solved else "unsolved"
        return _checked(Outcome(algorithm, n, status, result.placement, stats, MinConflictsPlayer(trace), fixed=fixed))
