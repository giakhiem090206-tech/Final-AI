"""Min-Conflicts local search for N-Queens, with pluggable variable selection.

CSP model: one variable per row, whose value is the column of that row's queen.
A complete assignment therefore always has one queen per row and only column and
diagonal conflicts remain to be repaired.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from operator import add
from time import perf_counter
from typing import Deque, List, Optional, Sequence, Set

from .board import Placement


class ConflictTracker:
    """Current assignment, with conflicts updated incrementally instead of recounted.

    A move changes the conflicts of the queens on just six lines (the column and two
    diagonals it leaves and the three it joins), and those lines hold few queens as the
    search nears a solution. So a move costs little, however large the board is, and
    `conflicted` always holds the variables a selector has to choose from.

    `buckets[c]` holds the rows with exactly c conflicts, kept up to date in the same way,
    so the most conflicted rows are found without scanning every conflicted row.
    """

    __slots__ = ("n", "queens", "columns", "diagonals", "anti_diagonals", "column_rows", "diagonal_rows",
                 "anti_rows", "conflicts", "conflicted", "_position", "buckets", "_bucket_index", "_top")

    def __init__(self, queens: Sequence[int]) -> None:
        self.n = len(queens)
        self.queens = list(queens)
        size = 2 * self.n - 1
        self.columns = [0] * self.n
        self.diagonals = [0] * size
        self.anti_diagonals = [0] * size
        self.column_rows: List[Set[int]] = [set() for _ in range(self.n)]
        self.diagonal_rows: List[Set[int]] = [set() for _ in range(size)]
        self.anti_rows: List[Set[int]] = [set() for _ in range(size)]
        for row, col in enumerate(self.queens):
            self.columns[col] += 1
            self.diagonals[row - col + self.n - 1] += 1
            self.anti_diagonals[row + col] += 1
            self.column_rows[col].add(row)
            self.diagonal_rows[row - col + self.n - 1].add(row)
            self.anti_rows[row + col].add(row)
        self.conflicts = [
            self.columns[col] + self.diagonals[row - col + self.n - 1] + self.anti_diagonals[row + col] - 3
            for row, col in enumerate(self.queens)
        ]
        self.conflicted: List[int] = [row for row, count in enumerate(self.conflicts) if count > 0]
        self._position = {row: index for index, row in enumerate(self.conflicted)}
        # A queen has at most n - 1 attackers on each of its three lines.
        self.buckets: List[List[int]] = [[] for _ in range(3 * self.n)]
        self._bucket_index = [-1] * self.n
        for row, count in enumerate(self.conflicts):
            if count > 0:
                self._bucket_index[row] = len(self.buckets[count])
                self.buckets[count].append(row)
        self._top = max(self.conflicts, default=0)  # never below the largest count

    def top_count(self) -> int:
        """The largest number of conflicts of any row, 0 when there is none."""
        while self._top > 0 and not self.buckets[self._top]:
            self._top -= 1
        return self._top

    def conflicts_if_placed(self, row: int, col: int) -> int:
        """Queens in other rows that would attack a queen placed at (row, col)."""
        count = (
            self.columns[col]
            + self.diagonals[row - col + self.n - 1]
            + self.anti_diagonals[row + col]
        )
        return count - 3 if self.queens[row] == col else count

    def _set_conflicts(self, row: int, count: int) -> None:
        old = self.conflicts[row]
        if old == count:
            return
        self.conflicts[row] = count
        if count > 0 and old == 0:
            self._position[row] = len(self.conflicted)
            self.conflicted.append(row)
        elif count == 0:
            # Swap with the last element, to remove from the list in constant time.
            index = self._position.pop(row)
            last = self.conflicted.pop()
            if last != row:
                self.conflicted[index] = last
                self._position[last] = index
        if old > 0:  # leave the old bucket, by the same swap with its last element
            bucket = self.buckets[old]
            index = self._bucket_index[row]
            last = bucket.pop()
            if last != row:
                bucket[index] = last
                self._bucket_index[last] = index
        if count > 0:
            self._bucket_index[row] = len(self.buckets[count])
            self.buckets[count].append(row)
            if count > self._top:
                self._top = count

    def move(self, row: int, col: int) -> None:
        old = self.queens[row]
        if old == col:
            return
        n = self.n
        conflicts = self.conflicts
        lines = (
            (self.column_rows[old], self.columns, old),
            (self.diagonal_rows[row - old + n - 1], self.diagonals, row - old + n - 1),
            (self.anti_rows[row + old], self.anti_diagonals, row + old),
        )
        for members, counts, index in lines:
            members.discard(row)
            counts[index] -= 1
            for other in members:
                self._set_conflicts(other, conflicts[other] - 1)

        self.queens[row] = col
        total = 0
        lines = (
            (self.column_rows[col], self.columns, col),
            (self.diagonal_rows[row - col + n - 1], self.diagonals, row - col + n - 1),
            (self.anti_rows[row + col], self.anti_diagonals, row + col),
        )
        for members, counts, index in lines:
            for other in members:
                self._set_conflicts(other, conflicts[other] + 1)
            total += len(members)
            members.add(row)
            counts[index] += 1
        self._set_conflicts(row, total)

    def attacking_pairs(self) -> int:
        return sum(self.conflicts) // 2


class VariableSelector(ABC):
    """Strategy deciding which conflicted variable Min-Conflicts repairs next."""

    name = "abstract"

    def reset(self, n: int) -> None:
        """Forget state from a previous run."""

    @abstractmethod
    def select(self, tracker: ConflictTracker, step: int, rng: random.Random) -> int:
        """Pick a variable; the tracker has at least one conflicted variable."""

    def notify_move(self, variable: int, step: int) -> None:
        """Called after `variable` has been repaired at `step`."""


class RandomConflictedSelector(VariableSelector):
    """Standard Min-Conflicts: a uniformly random conflicted variable."""

    name = "standard"

    def select(self, tracker: ConflictTracker, step: int, rng: random.Random) -> int:
        return rng.choice(tracker.conflicted)


class MostConflictedSelector(VariableSelector):
    """The variable with the most conflicts, ties broken at random (no memory)."""

    name = "most-conflicted"

    def select(self, tracker: ConflictTracker, step: int, rng: random.Random) -> int:
        return rng.choice(tracker.buckets[tracker.top_count()])


class MostConflictedTabuSelector(VariableSelector):
    """Proposed heuristic: most-conflicted variable that was not repaired recently.

    Choosing the worst variable removes the most attacks per repair while conflicts
    are dense. Near a solution most variables tie at one conflict and pure greed can
    keep re-picking the same few rows, so a variable just repaired is barred for
    `tenure` steps, which forces the search to work on other rows.
    """

    name = "most-conflicted+tabu"

    def __init__(self, tenure: int = 8) -> None:
        self.tenure = tenure
        self._recent: Deque[int] = deque(maxlen=tenure)  # rows repaired in the last `tenure` steps

    def reset(self, n: int) -> None:
        self._recent = deque(maxlen=self.tenure)

    def select(self, tracker: ConflictTracker, step: int, rng: random.Random) -> int:
        tabu = set(self._recent)
        conflicts, buckets = tracker.conflicts, tracker.buckets
        # From the most conflicted rows down, the first group with a row that is not tabu.
        for count in range(tracker.top_count(), 0, -1):
            bucket = buckets[count]
            if len(bucket) > sum(1 for row in tabu if conflicts[row] == count):
                while True:  # a uniform choice among the group's rows that are not tabu
                    row = rng.choice(bucket)
                    if row not in tabu:
                        return row
        # Every conflicted variable is tabu: ignore the tabu list this once.
        return rng.choice(buckets[tracker.top_count()])

    def notify_move(self, variable: int, step: int) -> None:
        self._recent.append(variable)


@dataclass
class MinConflictsResult:
    n: int
    selector: str
    solved: bool
    steps: int
    seconds: float
    remaining_conflicts: int
    placement: Optional[Placement]


class MinConflictsSolver:
    """MIN-CONFLICTS(csp, max_steps) with the variable-selection step replaceable."""

    def __init__(self, selector: VariableSelector, max_steps: Optional[int] = None) -> None:
        self.selector = selector
        self.max_steps = max_steps

    @staticmethod
    def random_assignment(n: int, seed: int) -> List[int]:
        """Initial assignment; depends only on the seed so that selectors can be paired."""
        rng = random.Random(f"init-{n}-{seed}")
        return [rng.randrange(n) for _ in range(n)]

    def default_max_steps(self, n: int) -> int:
        return max(2000, 100 * n)

    def solve(self, n: int, seed: int = 0) -> MinConflictsResult:
        rng = random.Random(f"search-{n}-{seed}")
        tracker = ConflictTracker(self.random_assignment(n, seed))
        max_steps = self.max_steps if self.max_steps is not None else self.default_max_steps(n)
        selector = self.selector
        selector.reset(n)

        start = perf_counter()
        step = 0
        while step < max_steps and tracker.conflicted:
            variable = selector.select(tracker, step, rng)
            tracker.move(variable, self._min_conflict_value(tracker, variable, rng))
            selector.notify_move(variable, step)
            step += 1
        elapsed = perf_counter() - start

        solved = not tracker.conflicted
        return MinConflictsResult(
            n=n,
            selector=selector.name,
            solved=solved,
            steps=step,
            seconds=elapsed,
            remaining_conflicts=tracker.attacking_pairs(),
            placement=Placement.from_columns(tracker.queens) if solved else None,
        )

    def solve_with_restarts(self, n: int, seed: int = 0, max_restarts: int = 50) -> MinConflictsResult:
        """Restart from a new random assignment whenever the step limit is reached.

        On small boards (about N = 6..16) a run can end in a local minimum that no
        variable-selection rule can leave, because it is the min-conflict value choice
        that keeps every queen in place. A restart is what escapes it. The experiments
        call `solve` directly, so that these failures stay visible in the results.
        """
        steps, seconds = 0, 0.0
        for attempt in range(max_restarts + 1):
            result = self.solve(n, seed + attempt)
            steps += result.steps
            seconds += result.seconds
            if result.solved:
                break
        result.steps, result.seconds = steps, seconds
        return result

    @staticmethod
    def _min_conflict_value(tracker: ConflictTracker, row: int, rng: random.Random) -> int:
        """Value with the fewest conflicts, ties broken at random (as in AIMA).

        The three counters are added by C-level map() over slices, which is several times
        faster than a Python loop on a large board.
        """
        n = tracker.n
        diagonal_slice = tracker.diagonals[row:row + n]
        diagonal_slice.reverse()  # column c lies on diagonal row - c + n - 1
        counts = list(map(add, map(add, tracker.columns, diagonal_slice), tracker.anti_diagonals[row:row + n]))
        counts[tracker.queens[row]] -= 3
        return _random_item_with(range(n), counts, min(counts), rng)



def _random_item_with(items: Sequence[int], counts: List[int], target: int, rng: random.Random) -> int:
    """A random item, uniformly among those whose count equals `target`.

    rng.choice(seq) draws rng.randrange(len(seq)) and returns that element, so drawing the
    index here and walking to that match gives exactly what rng.choice would on the list of
    matches, without building the list. The counting and searching run in C (list.count,
    list.index), and on average only half the matches are visited.
    """
    chosen = rng.randrange(counts.count(target))
    position = counts.index(target)
    for _ in range(chosen):
        position = counts.index(target, position + 1)
    return items[position]
