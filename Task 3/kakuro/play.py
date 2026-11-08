"""The game as a person plays it: entries, rule checking, candidates and hints."""
from __future__ import annotations

from collections import deque
from typing import List, Optional, Set, Tuple

from .csp import FULL_DOMAIN, KakuroCSP, largest_sum, smallest_sum
from .solver import BacktrackingSolver


class PlayBoard:
    """A partly filled board. It knows nothing about the screen, so that it can be tested alone."""

    def __init__(self, csp: KakuroCSP) -> None:
        self.csp = csp
        self.values: List[int] = [0] * csp.num_variables  # 0 marks an empty cell
        self._solution: Optional[List[int]] = None

    def set_value(self, cell: int, digit: int) -> None:
        self.values[cell] = digit

    def clear(self, cell: int) -> None:
        self.values[cell] = 0

    def reset(self) -> None:
        self.values = [0] * self.csp.num_variables

    @property
    def filled(self) -> int:
        return sum(1 for value in self.values if value)

    def conflicts(self) -> Set[int]:
        """Cells that break a rule: a repeated digit, or a run whose clue can no longer be met."""
        bad: Set[int] = set()
        for run in self.csp.runs:
            filled = [cell for cell in run.cells if self.values[cell]]
            digits = [self.values[cell] for cell in filled]
            for cell in filled:
                if digits.count(self.values[cell]) > 1:
                    bad.add(cell)
            remaining = len(run.cells) - len(filled)
            left = run.clue - sum(digits)
            if not smallest_sum(remaining) <= left <= largest_sum(remaining):
                bad.update(filled)
        return bad

    def is_solved(self) -> bool:
        return self.filled == self.csp.num_variables and not self.conflicts()

    def candidates(self) -> Optional[List[int]]:
        """Digits still possible in each cell given the entries, or None if they contradict the rules.

        This is the same propagation the solver uses, offered to the player as pencil marks.
        """
        domains = [1 << value if value else FULL_DOMAIN for value in self.values]
        csp = self.csp
        queue: deque = deque(run.index for run in csp.runs)
        queued = set(queue)
        while queue:
            run_index = queue.popleft()
            queued.discard(run_index)
            run = csp.runs[run_index]
            after = csp.filter.filter(run.clue, csp.run_readers[run_index](domains))
            if after is None:
                return None
            for cell, mask in zip(run.cells, after):
                if mask != domains[cell]:
                    domains[cell] = mask
                    for other in csp.runs_of[cell]:
                        if other != run_index and other not in queued:
                            queue.append(other)
                            queued.add(other)
        return domains

    def solution(self) -> Optional[List[int]]:
        if self._solution is None:
            self._solution = BacktrackingSolver(self.csp).solve().solution
        return self._solution

    def hint(self, preferred: Optional[int] = None) -> Optional[Tuple[int, int]]:
        """A correct digit for a cell that is empty or wrong, or None if there is nothing to give.

        With a board of several solutions this follows one of them.
        """
        solution = self.solution()
        if solution is None:
            return None
        if preferred is not None and self.values[preferred] != solution[preferred]:
            return preferred, solution[preferred]
        for cell, value in enumerate(self.values):
            if value != solution[cell]:
                return cell, solution[cell]
        return None
