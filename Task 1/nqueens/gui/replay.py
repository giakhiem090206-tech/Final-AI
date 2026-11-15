"""Replays a recorded Min-Conflicts run frame by frame. No PyGame here, so it is unit-tested."""
from __future__ import annotations

from bisect import bisect_right
from typing import List, Optional, Tuple

from ..min_conflicts import ConflictTracker, MinConflictsTrace

Move = Tuple[int, int, int]


class MinConflictsPlayer:
    """Moves forward and backward through a recorded run.

    Attempt i contributes len(moves_i) + 1 frames: its random start, then the board after
    each repair. Going from the last frame of an attempt to the first frame of the next
    one is a restart. A repair (row, old, new) is undone by moving the row back to `old`,
    so stepping backward costs as little as stepping forward.
    """

    def __init__(self, trace: MinConflictsTrace) -> None:
        if not trace.attempts:
            raise ValueError("the trace holds no attempt")
        self.attempts = trace.attempts
        self.starts: List[int] = []
        total = 0
        for attempt in self.attempts:
            self.starts.append(total)
            total += len(attempt.moves) + 1
        self.frame_count = total
        self.pairs = self._attacking_pairs_per_frame()
        self.max_pairs = max(self.pairs)
        self._attempt = 0
        self._step = 0
        self._tracker = ConflictTracker(self.attempts[0].initial)

    def _attacking_pairs_per_frame(self) -> List[int]:
        pairs: List[int] = []
        for attempt in self.attempts:
            tracker = ConflictTracker(attempt.initial)
            pairs.append(tracker.attacking_pairs())
            for row, _, new in attempt.moves:
                tracker.move(row, new)
                pairs.append(tracker.attacking_pairs())
        return pairs

    @property
    def n(self) -> int:
        return self._tracker.n

    @property
    def frame(self) -> int:
        return self.starts[self._attempt] + self._step

    @property
    def attempt_index(self) -> int:
        return self._attempt

    @property
    def step(self) -> int:
        """Repairs made so far in the current attempt."""
        return self._step

    @property
    def attempt_steps(self) -> int:
        return len(self.attempts[self._attempt].moves)

    @property
    def at_end(self) -> bool:
        return self.frame == self.frame_count - 1

    @property
    def queens(self) -> List[int]:
        """Column of the queen of each row."""
        return self._tracker.queens

    @property
    def row_conflicts(self) -> List[int]:
        return self._tracker.conflicts

    @property
    def attacking_pairs(self) -> int:
        return self.pairs[self.frame]

    def locate(self, frame: int) -> Tuple[int, int]:
        """(attempt, step within the attempt) of a frame."""
        attempt = bisect_right(self.starts, frame) - 1
        return attempt, frame - self.starts[attempt]

    def seek(self, frame: int) -> None:
        frame = max(0, min(self.frame_count - 1, frame))
        attempt, step = self.locate(frame)
        if attempt != self._attempt or step < self._step - step:
            # Replaying from the attempt's start is cheaper than undoing that many repairs.
            self._attempt, self._step = attempt, 0
            self._tracker = ConflictTracker(self.attempts[attempt].initial)
        moves, tracker = self.attempts[attempt].moves, self._tracker
        while self._step < step:
            row, _, new = moves[self._step]
            tracker.move(row, new)
            self._step += 1
        while self._step > step:
            self._step -= 1
            row, old, _ = moves[self._step]
            tracker.move(row, old)

    def next_move(self) -> Optional[Move]:
        moves = self.attempts[self._attempt].moves
        return moves[self._step] if self._step < len(moves) else None

    def conflicts_at(self, row: int, col: int) -> int:
        """Queens of other rows that would attack the queen of `row` placed in `col`."""
        return self._tracker.conflicts_if_placed(row, col)

    def candidate_counts(self, row: int) -> List[int]:
        return [self.conflicts_at(row, col) for col in range(self.n)]
