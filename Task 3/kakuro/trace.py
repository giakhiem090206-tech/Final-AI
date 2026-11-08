"""Records a solver run so that the interface can replay it forwards and backwards."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .csp import POPCOUNT, KakuroCSP, digits_text
from .solver import Change, SearchObserver

START, PROPAGATE, REVISE, WIPEOUT, PROPAGATE_END, SELECT, ORDER, ASSIGN, REJECT, BACKTRACK, SOLUTION, FINISH = (
    "start", "propagate", "revise", "wipeout", "propagate_end", "select", "order", "assign", "reject",
    "backtrack", "solution", "finish",
)
SNAPSHOT_EVERY = 128


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    message: str
    variable: Optional[int] = None
    value: Optional[int] = None
    run: Optional[int] = None
    changes: Tuple[Change, ...] = ()
    queue: Tuple[int, ...] = ()
    values: Tuple[int, ...] = ()
    depth: int = 0


class TraceRecorder(SearchObserver):
    """Turns solver callbacks into a list of events with readable explanations."""

    active = True

    def __init__(self, csp: KakuroCSP) -> None:
        self.csp = csp
        self.events: List[TraceEvent] = []

    def _add(self, kind: str, message: str, **fields: object) -> None:
        self.events.append(TraceEvent(kind, message, **fields))

    def _changes_text(self, changes: Sequence[Change]) -> str:
        parts = [f"{self.csp.variable_name(v)} {digits_text(old)} to {digits_text(new)}" for v, old, new in changes]
        return "; ".join(parts) if parts else "nothing removed"

    def on_start(self, domains: Sequence[int]) -> None:
        self._add(START, "Every white cell starts with the domain {1,...,9}.")

    def on_propagation_start(self, reason: str, queue: Sequence[int]) -> None:
        self._add(PROPAGATE, f"Propagation: {reason}.", queue=tuple(queue))

    def on_revise(self, run: int, changes: Sequence[Change], queue: Sequence[int], kind: str) -> None:
        self._add(REVISE, f"Revise {self.csp.runs[run].label}: {self._changes_text(changes)}.",
                  run=run, changes=tuple(changes), queue=tuple(queue))

    def on_wipeout(self, run: int, variable: Optional[int]) -> None:
        where = f"{self.csp.variable_name(variable)} has no value left" if variable is not None \
            else "no combination of digits fits"
        self._add(WIPEOUT, f"Dead end in {self.csp.runs[run].label}: {where}.", run=run, variable=variable)

    def on_propagation_end(self, consistent: bool) -> None:
        text = "Propagation finished: domains are consistent." if consistent else "Propagation found a contradiction."
        self._add(PROPAGATE_END, text)

    def on_select_variable(self, variable: int, reason: str) -> None:
        self._add(SELECT, f"Select {self.csp.variable_name(variable)} ({reason}).", variable=variable)

    def on_order_values(self, variable: int, values: Sequence[int], reason: str) -> None:
        listed = ", ".join(str(v) for v in values)
        self._add(ORDER, f"Try {self.csp.variable_name(variable)} with values {listed} ({reason}).",
                  variable=variable, values=tuple(values))

    def on_assign(self, variable: int, value: int, depth: int, changes: Sequence[Change]) -> None:
        self._add(ASSIGN, f"Assign {self.csp.variable_name(variable)} = {value} (depth {depth}).",
                  variable=variable, value=value, changes=tuple(changes), depth=depth)

    def on_reject(self, variable: int, value: int, reason: str) -> None:
        self._add(REJECT, f"Reject {self.csp.variable_name(variable)} = {value}: {reason}.",
                  variable=variable, value=value)

    def on_backtrack(self, variable: int, value: int, depth: int, changes: Sequence[Change]) -> None:
        self._add(BACKTRACK, f"Backtrack: undo {self.csp.variable_name(variable)} = {value} "
                             f"and restore {len(changes)} domain change(s).",
                  variable=variable, value=value, changes=tuple(changes), depth=depth)

    def on_solution(self, values: Sequence[int]) -> None:
        self._add(SOLUTION, "Solution found: every cell is assigned and all runs are satisfied.")

    def on_finish(self, status: str) -> None:
        text = {"solved": "Search finished: solved.", "unsatisfiable": "Search finished: this board has no solution.",
                "limit": "Search stopped at the display limit."}[status]
        self._add(FINISH, text)


@dataclass
class StackEntry:
    """One level of the search: a variable and what has happened to its values."""

    variable: int
    failed: List[int] = field(default_factory=list)
    current: Optional[int] = None
    remaining: List[int] = field(default_factory=list)

    def copy(self) -> "StackEntry":
        return StackEntry(self.variable, list(self.failed), self.current, list(self.remaining))


@dataclass
class ReplayState:
    """What the search looked like just after some event."""

    domains: List[int]
    assigned: Dict[int, int] = field(default_factory=dict)
    stack: List[StackEntry] = field(default_factory=list)
    queue: Tuple[int, ...] = ()
    assignments: int = 0
    backtracks: int = 0
    revisions: int = 0
    pruned: int = 0
    wipeouts: int = 0

    def copy(self) -> "ReplayState":
        return ReplayState(list(self.domains), dict(self.assigned), [e.copy() for e in self.stack], self.queue,
                           self.assignments, self.backtracks, self.revisions, self.pruned, self.wipeouts)

    def apply(self, event: TraceEvent) -> None:
        kind = event.kind
        for variable, _, new in event.changes:
            self.domains[variable] = new
        if kind == PROPAGATE:
            self.queue = event.queue
        elif kind == REVISE:
            self.queue = event.queue
            self.revisions += 1
            self.pruned += sum(POPCOUNT[old] - POPCOUNT[new] for _, old, new in event.changes)
        elif kind == WIPEOUT:
            self.wipeouts += 1
        elif kind == PROPAGATE_END:
            self.queue = ()
        elif kind == ORDER:
            self.stack.append(StackEntry(event.variable, remaining=list(event.values)))
        elif kind == ASSIGN:
            top = self.stack[-1]
            top.current = event.value
            top.remaining.remove(event.value)
            self.assigned[event.variable] = event.value
            self.assignments += 1
        elif kind == REJECT:
            top = self.stack[-1]
            top.remaining.remove(event.value)
            top.failed.append(event.value)
        elif kind == BACKTRACK:
            # Levels above this one ran out of values without an event of their own.
            while self.stack[-1].variable != event.variable:
                self.stack.pop()
            top = self.stack[-1]
            top.failed.append(event.value)
            top.current = None
            del self.assigned[event.variable]
            self.backtracks += 1
            self.queue = ()


class Replay:
    """Random access to the states of a recorded run, using periodic snapshots."""

    def __init__(self, events: List[TraceEvent], initial_domains: Sequence[int]) -> None:
        self.events = events
        self._snapshots: List[ReplayState] = []
        state = ReplayState(list(initial_domains))
        for index, event in enumerate(events):
            if index % SNAPSHOT_EVERY == 0:
                self._snapshots.append(state.copy())
            state.apply(event)
        self.position = 0
        self.state = self._state_at(0)

    def __len__(self) -> int:
        return len(self.events)

    def _state_at(self, index: int) -> ReplayState:
        state = self._snapshots[index // SNAPSHOT_EVERY].copy()
        for position in range(index - index % SNAPSHOT_EVERY, index + 1):
            state.apply(self.events[position])
        return state

    def seek(self, index: int) -> None:
        index = max(0, min(index, len(self.events) - 1))
        if index == self.position + 1:
            self.state.apply(self.events[index])
        elif index != self.position:
            self.state = self._state_at(index)
        self.position = index

    @property
    def event(self) -> TraceEvent:
        return self.events[self.position]

    def next_position(self, kinds: Sequence[str], direction: int = 1) -> int:
        """Nearest event of the given kinds in a direction, or the end if there is none."""
        index = self.position + direction
        while 0 <= index < len(self.events):
            if self.events[index].kind in kinds:
                return index
            index += direction
        return len(self.events) - 1 if direction > 0 else 0


@dataclass
class TreeNode:
    variable: int
    value: int
    depth: int
    parent: Optional[int]
    born: int                     # event index of the assignment
    died: Optional[int] = None    # event index of the backtrack
    solution: bool = False
    x: float = 0.0
    children: List[int] = field(default_factory=list)


class SearchTree:
    """The tree of assignments in a run, with fixed positions so it can grow on screen."""

    def __init__(self, events: Sequence[TraceEvent]) -> None:
        self.nodes: List[TreeNode] = []
        self.depth = 0
        path: List[int] = []
        for index, event in enumerate(events):
            if event.kind == ASSIGN:
                while len(path) >= event.depth:
                    path.pop()
                parent = path[-1] if path else None
                node = TreeNode(event.variable, event.value, event.depth, parent, index)
                self.nodes.append(node)
                if parent is not None:
                    self.nodes[parent].children.append(len(self.nodes) - 1)
                path.append(len(self.nodes) - 1)
                self.depth = max(self.depth, event.depth)
            elif event.kind == BACKTRACK:
                while len(path) > event.depth:
                    path.pop()
                if path:
                    self.nodes[path[-1]].died = index
                    path.pop()
            elif event.kind == SOLUTION:
                for node_index in path:
                    self.nodes[node_index].solution = True
        self.leaves = 0
        for index, node in enumerate(self.nodes):
            if node.parent is None:
                self._place(index)

    def _place(self, index: int) -> None:
        """Leaves take the next free column; a parent sits above the middle of its children."""
        node = self.nodes[index]
        if not node.children:
            node.x = float(self.leaves)
            self.leaves += 1
            return
        for child in node.children:
            self._place(child)
        node.x = (self.nodes[node.children[0]].x + self.nodes[node.children[-1]].x) / 2
