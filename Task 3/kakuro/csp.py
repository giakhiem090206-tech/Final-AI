"""The CSP model of a Kakuro board.

Variables    one per white cell
Domains      subsets of {1, ..., 9}, stored as bit masks (bit d set means digit d is possible)
Constraints  one per run: the digits are all different AND they sum to the clue

Each constraint is n-ary, so the usual binary arc consistency becomes generalized arc
consistency (GAC): a digit stays in a domain only if it is part of some complete,
valid filling of the run.
"""
from __future__ import annotations

from itertools import combinations
from operator import itemgetter
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .puzzle import KakuroPuzzle, Run

FULL_DOMAIN = sum(1 << digit for digit in range(1, 10))
POPCOUNT = tuple(bin(mask).count("1") for mask in range(1024))
DIGITS = tuple(tuple(d for d in range(1, 10) if mask >> d & 1) for mask in range(1024))
# Sum of the digits in a mask.
MASK_SUM = tuple(sum(DIGITS[mask]) for mask in range(1024))
BITS = tuple(tuple(1 << d for d in DIGITS[mask]) for mask in range(1024))
_UNKNOWN = object()  # marks a key missing from the memo (None is a valid, remembered result)


def digits_text(mask: int) -> str:
    return "{" + ",".join(str(d) for d in DIGITS[mask]) + "}"


def smallest_sum(count: int) -> int:
    """Smallest possible sum of `count` distinct digits."""
    return count * (count + 1) // 2


def largest_sum(count: int) -> int:
    """Largest possible sum of `count` distinct digits."""
    return count * (19 - count) // 2


class RunFilter:
    """Generalized arc consistency for one Sum-and-AllDifferent constraint.

    Fill the cells left to right, tracking the set of digits used so far. There are at
    most 512 such sets, and the set alone fixes the sum, so a forward pass finds what is
    reachable and a backward pass keeps what can still finish on the clue. A digit is
    supported for a cell exactly when a transition using it survives both passes. Results
    are remembered, because the search meets the same domains over and over.
    """

    def __init__(self) -> None:
        self._memo: Dict[Tuple[int, Tuple[int, ...]], Optional[Tuple[int, ...]]] = {}

    def filter(self, clue: int, domains: Tuple[int, ...]) -> Optional[Tuple[int, ...]]:
        """The domains with unsupported digits removed, or None if nothing can satisfy the run."""
        key = (clue, domains)
        result = self._memo.get(key, _UNKNOWN)
        if result is _UNKNOWN:
            result = self._memo[key] = self._compute(clue, domains)
        return result

    @staticmethod
    def _compute(clue: int, domains: Tuple[int, ...]) -> Optional[Tuple[int, ...]]:
        length = len(domains)
        layers: List[set] = [{0}]
        for position, domain in enumerate(domains):
            # A set of digits whose sum can no longer reach the clue (even with the smallest or
            # largest digits left for the remaining cells) is dropped now. The backward pass would
            # drop it anyway, so the result is the same; the forward pass just carries less.
            remaining = length - position - 1
            low, high = clue - largest_sum(remaining), clue - smallest_sum(remaining)
            following = set()
            for used in layers[-1]:
                for bit in BITS[domain & ~used]:
                    reached = used | bit
                    if low <= MASK_SUM[reached] <= high:
                        following.add(reached)
            layers.append(following)

        good = {used for used in layers[length] if MASK_SUM[used] == clue}
        if not good:
            return None
        supported = [0] * length
        for position in range(length - 1, -1, -1):
            domain = domains[position]
            alive = set()
            for used in layers[position]:
                for bit in BITS[domain & ~used]:
                    if used | bit in good:
                        alive.add(used)
                        supported[position] |= bit
            good = alive
        return tuple(supported)


def _single_reader(cell: int) -> Callable[[Sequence[int]], Tuple[int, ...]]:
    """itemgetter with one index returns a value, not a tuple, so one-cell runs need this."""
    return lambda domains: (domains[cell],)


class KakuroCSP:
    """Variables, domains and constraints of one puzzle, with the queries the solver needs."""

    def __init__(self, puzzle: KakuroPuzzle) -> None:
        self.puzzle = puzzle
        self.num_variables = len(puzzle.cells)
        self.runs: List[Run] = puzzle.runs
        self.runs_of: List[Tuple[int, ...]] = [() for _ in range(self.num_variables)]
        for run in self.runs:
            for cell in run.cells:
                self.runs_of[cell] = self.runs_of[cell] + (run.index,)
        self.peers: List[Tuple[int, ...]] = [
            tuple(sorted({other for r in self.runs_of[v] for other in self.runs[r].cells} - {v}))
            for v in range(self.num_variables)
        ]
        # run_readers[r](domains) is the tuple of run r's domains, read in one C-level call.
        self.run_readers: List[Callable[[Sequence[int]], Tuple[int, ...]]] = [
            itemgetter(*run.cells) if len(run.cells) > 1 else _single_reader(run.cells[0]) for run in self.runs
        ]
        self.filter = RunFilter()

    def initial_domains(self) -> List[int]:
        return [FULL_DOMAIN] * self.num_variables

    def possible_digit_sets(self, run: Run, domains: Sequence[int]) -> List[int]:
        """The sets of digits that could still fill a run, as masks. This is what explains GAC:
        a digit is removed from a cell exactly when no remaining set can place it there."""
        run_domains = [domains[cell] for cell in run.cells]
        sets = []
        for combo in combinations(range(1, 10), len(run.cells)):
            if sum(combo) == run.clue:
                mask = sum(1 << digit for digit in combo)
                if self.filter.filter(run.clue, tuple(domain & mask for domain in run_domains)) is not None:
                    sets.append(mask)
        return sets

    def variable_name(self, variable: int) -> str:
        return self.puzzle.cell_name(variable)

    def is_consistent(self, variable: int, value: int, assignment: Sequence[int]) -> bool:
        """Could this value still lead to a solution, looking only at assigned cells?

        `assignment[v]` is 0 for an unassigned cell. This is the only check plain
        backtracking has: the value must not repeat in a run, and the run's sum must
        remain reachable by the distinct digits still to be placed.
        """
        for run_index in self.runs_of[variable]:
            run = self.runs[run_index]
            total = value
            remaining = 0
            for cell in run.cells:
                if cell == variable:
                    continue
                other = assignment[cell]
                if other == 0:
                    remaining += 1
                elif other == value:
                    return False
                else:
                    total += other
            left = run.clue - total
            if not smallest_sum(remaining) <= left <= largest_sum(remaining):
                return False
        return True
