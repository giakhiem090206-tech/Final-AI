"""Backtracking search combined with constraint propagation and ordering heuristics."""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from time import perf_counter
from typing import List, Optional, Sequence, Tuple

from .csp import BITS, DIGITS, POPCOUNT, KakuroCSP, largest_sum, smallest_sum

# Propagation applied after each assignment.
PROPAGATE_NONE, PROPAGATE_FC, PROPAGATE_MAC = "none", "fc", "mac"
# Variable and value ordering.
VAR_STATIC, VAR_MRV, VAR_MRV_DEGREE, VAR_DOM_WDEG = "static", "mrv", "mrv+degree", "dom/wdeg"
VAL_ASCENDING, VAL_LCV = "ascending", "lcv"

Change = Tuple[int, int, int]  # variable, old mask, new mask


@dataclass(frozen=True)
class SolverConfig:
    propagation: str = PROPAGATE_MAC
    variable_order: str = VAR_DOM_WDEG
    value_order: str = VAL_ASCENDING
    restarts: bool = False

    @classmethod
    def best(cls) -> "SolverConfig":
        """The best combination measured on hard boards (see run_evaluation.py)."""
        return cls(PROPAGATE_MAC, VAR_DOM_WDEG, VAL_ASCENDING, restarts=True)

    @property
    def name(self) -> str:
        text = f"{self.propagation} / {self.variable_order} / {self.value_order}"
        return f"{text} / restarts" if self.restarts else text


@dataclass
class SolverStats:
    assignments: int = 0      # search nodes: values tried
    branch_points: int = 0    # choices between two or more values
    backtracks: int = 0       # assignments undone
    revisions: int = 0        # constraints filtered
    pruned_values: int = 0    # digits removed from domains
    wipeouts: int = 0         # propagation emptied a domain
    max_depth: int = 0
    restarts: int = 0         # times the search started over


@dataclass
class SolveResult:
    status: str               # "solved", "unsatisfiable" or "limit"
    solutions: List[List[int]]
    stats: SolverStats
    seconds: float
    limit_reached: bool = False  # the search was cut short, so finding no more solutions proves nothing

    @property
    def solution(self) -> Optional[List[int]]:
        return self.solutions[0] if self.solutions else None


class SearchObserver:
    """Receives each step of the search. The default does nothing, so solving stays fast."""

    active = False

    def on_start(self, domains: Sequence[int]) -> None: ...
    def on_propagation_start(self, reason: str, queue: Sequence[int]) -> None: ...
    def on_revise(self, run: int, changes: Sequence[Change], queue: Sequence[int], kind: str) -> None: ...
    def on_wipeout(self, run: int, variable: Optional[int]) -> None: ...
    def on_propagation_end(self, consistent: bool) -> None: ...
    def on_select_variable(self, variable: int, reason: str) -> None: ...
    def on_order_values(self, variable: int, values: Sequence[int], reason: str) -> None: ...
    def on_assign(self, variable: int, value: int, depth: int, changes: Sequence[Change]) -> None: ...
    def on_reject(self, variable: int, value: int, reason: str) -> None: ...
    def on_backtrack(self, variable: int, value: int, depth: int, changes: Sequence[Change]) -> None: ...
    def on_solution(self, values: Sequence[int]) -> None: ...
    def on_finish(self, status: str) -> None: ...


class _LimitReached(Exception):
    pass


class _RestartSearch(Exception):
    pass


class BacktrackingSolver:
    """BACKTRACKING-SEARCH with INFERENCE, in the configuration given by SolverConfig."""

    RESTART_BASE = 64      # backtracks allowed in the first attempt
    RESTART_GROWTH = 1.5   # each attempt gets this much more, so the search stays complete

    def __init__(self, csp: KakuroCSP, config: Optional[SolverConfig] = None,
                 observer: Optional[SearchObserver] = None, rng: Optional[random.Random] = None,
                 max_assignments: Optional[int] = None, time_limit: Optional[float] = None) -> None:
        self.csp = csp
        self.config = config or SolverConfig.best()
        self.observer = observer or SearchObserver()
        self.rng = rng
        self.max_assignments = max_assignments
        self.time_limit = time_limit

    def solve(self, max_solutions: int = 1) -> SolveResult:
        """Find up to `max_solutions` solutions. Use 2 to test uniqueness, 0 to only propagate."""
        self.stats = SolverStats()
        self.solutions: List[List[int]] = []
        self.max_solutions = max_solutions
        self.domains = self.csp.initial_domains()
        self.assignment = [0] * self.csp.num_variables
        self.run_weights = [1] * len(self.csp.runs)  # dom/wdeg: how often each run caused a dead end
        self.static_order = list(range(self.csp.num_variables))
        if self.rng is not None:
            self.rng.shuffle(self.static_order)  # lets experiments test other fixed orders
        self.trail: List[Tuple[int, int]] = []
        self._deadline = None if self.time_limit is None else perf_counter() + self.time_limit
        self._backtrack_limit: Optional[int] = None
        self._restart_rng: Optional[random.Random] = None
        self.observer.on_start(self.domains)

        start = perf_counter()
        status = "unsatisfiable"
        limit_reached = False
        try:
            if self._propagate_initial() and max_solutions > 0:
                # Counting solutions needs one uninterrupted pass over the whole tree.
                if self.config.restarts and max_solutions == 1:
                    self._search_with_restarts()
                else:
                    self._search(0)
            if self.solutions:
                status = "solved"
        except _LimitReached:
            limit_reached = True
            status = "solved" if self.solutions else "limit"
        seconds = perf_counter() - start
        self.observer.on_finish(status)
        return SolveResult(status, self.solutions, self.stats, seconds, limit_reached)

    # --------------------------------------------------------------------- search
    def _search_with_restarts(self) -> None:
        """Run the search with a growing budget of backtracks, starting over when it runs out.

        Search times on these boards are heavy-tailed: a few early choices decide between
        an instant answer and a very long run. A restart gives up on a bad start, while
        dom/wdeg keeps what it learned about hard runs. Budgets keep growing, so an
        unsatisfiable board is still eventually proven so.
        """
        root_mark = len(self.trail)
        budget = float(self.RESTART_BASE)
        while True:
            self._backtrack_limit = self.stats.backtracks + int(budget)
            try:
                self._search(0)
                return
            except _RestartSearch:
                self.stats.restarts += 1
                while len(self.trail) > root_mark:
                    changed, old = self.trail.pop()
                    self.domains[changed] = old
                for variable in range(self.csp.num_variables):
                    self.assignment[variable] = 0
                budget *= self.RESTART_GROWTH
                if self._restart_rng is None:  # value order varies from the second attempt on
                    self._restart_rng = self.rng or random.Random(1)

    def _search(self, depth: int) -> bool:
        """Depth-first search; True means enough solutions were found and it should stop."""
        variable = self._select_variable()
        if variable is None:
            self.solutions.append(list(self.assignment))
            self.observer.on_solution(self.assignment)
            return len(self.solutions) >= self.max_solutions

        values = self._order_values(variable)
        if len(values) > 1:
            self.stats.branch_points += 1
        for value in values:
            if self.config.propagation == PROPAGATE_NONE and not self.csp.is_consistent(variable, value, self.assignment):
                if self.observer.active:
                    self.observer.on_reject(variable, value, "breaks a run with the cells already assigned")
                continue
            mark = len(self.trail)
            self._assign(variable, value, depth + 1)
            if self._propagate_after(variable, value) and self._search(depth + 1):
                return True
            self._undo(variable, value, depth + 1, mark)
            if self._backtrack_limit is not None and self.stats.backtracks >= self._backtrack_limit:
                raise _RestartSearch
        return False

    def _assign(self, variable: int, value: int, depth: int) -> None:
        stats = self.stats
        stats.assignments += 1
        if self.max_assignments is not None and stats.assignments > self.max_assignments:
            raise _LimitReached
        if self._deadline is not None and perf_counter() > self._deadline:
            raise _LimitReached
        if depth > stats.max_depth:
            stats.max_depth = depth
        old = self.domains[variable]
        self.assignment[variable] = value
        self.trail.append((variable, old))
        self.domains[variable] = 1 << value
        if self.observer.active:
            self.observer.on_assign(variable, value, depth, [(variable, old, 1 << value)])

    def _undo(self, variable: int, value: int, depth: int, mark: int) -> None:
        self.stats.backtracks += 1
        self.assignment[variable] = 0
        active = self.observer.active
        changes: List[Change] = []
        while len(self.trail) > mark:
            changed, old = self.trail.pop()
            if active:
                changes.append((changed, self.domains[changed], old))
            self.domains[changed] = old
        if active:
            self.observer.on_backtrack(variable, value, depth, changes)

    def _select_variable(self) -> Optional[int]:
        """Static order, or MRV, optionally breaking ties by the degree heuristic."""
        assignment, domains = self.assignment, self.domains
        order = self.config.variable_order
        if order == VAR_STATIC:
            for variable in self.static_order:
                if assignment[variable] == 0:
                    if self.observer.active:
                        self.observer.on_select_variable(variable, "next cell in a fixed order")
                    return variable
            return None
        if order == VAR_DOM_WDEG:
            return self._select_dom_wdeg()

        use_degree = order == VAR_MRV_DEGREE
        runs_of = self.csp.runs_of
        unassigned = self._unassigned_per_run() if use_degree else None
        best: List[int] = []
        best_key: Optional[Tuple[int, int]] = None
        for variable, value in enumerate(assignment):
            if value != 0:
                continue
            size = POPCOUNT[domains[variable]]
            if best_key is not None and size > best_key[0]:
                continue  # a larger domain loses whatever its degree, so the degree is not needed
            degree = 0
            if unassigned is not None:
                # A cell's across and down runs share only that cell, so its unassigned
                # neighbours are the other unassigned cells of its two runs.
                across, down = runs_of[variable]
                degree = unassigned[across] + unassigned[down] - 2
            key = (size, -degree)
            if best_key is None or key < best_key:
                best_key, best = key, [variable]
            elif key == best_key:
                best.append(variable)
        if not best:
            return None
        chosen = self.rng.choice(best) if self.rng is not None else best[0]
        if self.observer.active:
            reason = f"MRV: {best_key[0]} value(s) left"
            if use_degree:
                reason += f", degree {-best_key[1]} (most unassigned neighbours)"
            self.observer.on_select_variable(chosen, reason)
        return chosen

    def _unassigned_per_run(self) -> List[int]:
        """How many cells of each run are still unassigned."""
        runs_of = self.csp.runs_of
        counts = [0] * len(self.csp.runs)
        for variable, value in enumerate(self.assignment):
            if value == 0:
                for run_index in runs_of[variable]:
                    counts[run_index] += 1
        return counts

    def _select_dom_wdeg(self) -> Optional[int]:
        """Smallest domain size / weight: prefer cells in runs that have caused dead ends.

        Each dead end adds 1 to the weight of the run it happened in, so the search learns
        where the board is hard and turns to those cells first.
        """
        assignment, domains, csp, weights = self.assignment, self.domains, self.csp, self.run_weights
        # A run counts for a cell only while it has another unassigned cell. Counting the
        # unassigned cells of every run once is cheaper than looking through runs per cell.
        unassigned = self._unassigned_per_run()
        best: List[int] = []
        best_ratio = 0.0
        for variable, value in enumerate(assignment):
            if value != 0:
                continue
            weight = 0
            for run_index in csp.runs_of[variable]:
                if unassigned[run_index] > 1:  # this cell and at least one more
                    weight += weights[run_index]
            ratio = POPCOUNT[domains[variable]] / max(weight, 1)
            if not best or ratio < best_ratio:
                best_ratio, best = ratio, [variable]
            elif ratio == best_ratio:
                best.append(variable)
        if not best:
            return None
        chosen = self.rng.choice(best) if self.rng is not None else best[0]
        if self.observer.active:
            size = POPCOUNT[domains[chosen]]
            self.observer.on_select_variable(chosen, f"dom/wdeg: {size} value(s), ratio {best_ratio:.2f}")
        return chosen

    def _order_values(self, variable: int) -> List[int]:
        values = list(DIGITS[self.domains[variable]])
        shuffler = self._restart_rng or self.rng
        if shuffler is not None:
            shuffler.shuffle(values)
        if self.config.value_order == VAL_LCV and len(values) > 1:
            scores = {value: self._values_ruled_out(variable, value) for value in values}
            values.sort(key=scores.__getitem__)
            if self.observer.active:
                detail = ", ".join(f"{v} removes {scores[v]}" for v in values)
                self.observer.on_order_values(variable, values, f"LCV: {detail}")
        elif self.observer.active:
            self.observer.on_order_values(variable, values, "in ascending order")
        return values

    def _values_ruled_out(self, variable: int, value: int) -> int:
        """LCV score: digits lost by the variable's neighbours if it took this value."""
        csp, domains = self.csp, self.domains
        removed = 0
        for run_index in csp.runs_of[variable]:
            run = csp.runs[run_index]
            before = tuple(1 << value if cell == variable else domains[cell] for cell in run.cells)
            after = csp.filter.filter(run.clue, before)
            if after is None:
                return 1000  # this value fails at once: try it last
            removed += sum(POPCOUNT[a] - POPCOUNT[b] for a, b in zip(before, after))
        return removed

    # ---------------------------------------------------------------- propagation
    def _set_domain(self, variable: int, new_mask: int, changes: List[Change]) -> None:
        old = self.domains[variable]
        self.trail.append((variable, old))
        self.domains[variable] = new_mask
        changes.append((variable, old, new_mask))
        self.stats.pruned_values += POPCOUNT[old] - POPCOUNT[new_mask]

    def _propagate_initial(self) -> bool:
        propagation = self.config.propagation
        if propagation == PROPAGATE_MAC:
            return self._gac3(list(range(len(self.csp.runs))), "initial propagation over all runs")
        if propagation == PROPAGATE_FC:
            return self._node_consistency()
        return True

    def _propagate_after(self, variable: int, value: int) -> bool:
        propagation = self.config.propagation
        if propagation == PROPAGATE_MAC:
            name = self.csp.variable_name(variable)
            return self._gac3(list(self.csp.runs_of[variable]), f"after {name} = {value}")
        if propagation == PROPAGATE_FC:
            return self._forward_check(variable, value)
        return True

    def _node_consistency(self) -> bool:
        """Forward checking's starting point: each run alone trims its cells' domains once."""
        csp, domains, observer = self.csp, self.domains, self.observer
        if observer.active:
            observer.on_propagation_start("initial domains from each run's possible digit sets",
                                          [run.index for run in csp.runs])
        for position, run in enumerate(csp.runs):
            after = csp.filter.filter(run.clue, csp.run_readers[run.index](domains))
            self.stats.revisions += 1
            if after is None:
                self.stats.wipeouts += 1
                if observer.active:
                    observer.on_wipeout(run.index, None)
                    observer.on_propagation_end(False)
                return False
            changes: List[Change] = []
            for cell, mask in zip(run.cells, after):
                if mask != domains[cell]:
                    self._set_domain(cell, mask, changes)
            if observer.active:
                observer.on_revise(run.index, changes, [r.index for r in csp.runs[position + 1:]], "initial")
        if observer.active:
            observer.on_propagation_end(True)
        return True

    def _forward_check(self, variable: int, value: int) -> bool:
        """Prune only the neighbours of the new assignment, without any cascade.

        A neighbour loses the digit just used, and any digit that would leave the rest of
        the run's sum out of reach of the digits still to be placed.
        """
        csp, domains, assignment, observer = self.csp, self.domains, self.assignment, self.observer
        bit = 1 << value
        if observer.active:
            name = csp.variable_name(variable)
            observer.on_propagation_start(f"forward checking after {name} = {value}", csp.runs_of[variable])
        ok = True
        for position, run_index in enumerate(csp.runs_of[variable]):
            run = csp.runs[run_index]
            total = 0
            unassigned = []
            for cell in run.cells:
                if assignment[cell]:
                    total += assignment[cell]
                else:
                    unassigned.append(cell)
            left = run.clue - total
            self.stats.revisions += 1
            changes: List[Change] = []
            failed: Optional[int] = None
            others = len(unassigned) - 1
            if not unassigned and left != 0:
                ok = False
            else:
                low = left - largest_sum(others) if others >= 0 else 0
                high = left - smallest_sum(others) if others >= 0 else 0
                for cell in unassigned:
                    new_mask = domains[cell] & ~bit
                    for candidate in BITS[new_mask]:
                        digit = candidate.bit_length() - 1
                        if digit < low or digit > high:
                            new_mask &= ~candidate
                    if new_mask != domains[cell]:
                        self._set_domain(cell, new_mask, changes)
                    if new_mask == 0:
                        failed = cell
                        ok = False
                        break
            if observer.active:
                observer.on_revise(run_index, changes, csp.runs_of[variable][position + 1:], "forward")
            if not ok:
                self.stats.wipeouts += 1
                self.run_weights[run_index] += 1
                if observer.active:
                    observer.on_wipeout(run_index, failed)
                break
        if observer.active:
            observer.on_propagation_end(ok)
        return ok

    def _gac3(self, initial_runs: Sequence[int], reason: str) -> bool:
        """AC-3 generalized to n-ary constraints: revise runs until nothing changes."""
        csp, domains, observer, stats = self.csp, self.domains, self.observer, self.stats
        readers = csp.run_readers
        active = observer.active
        queue = deque(initial_runs)
        queued = set(initial_runs)
        if active:
            observer.on_propagation_start(reason, list(queue))
        while queue:
            run_index = queue.popleft()
            queued.discard(run_index)
            run = csp.runs[run_index]
            cells = run.cells
            after = csp.filter.filter(run.clue, readers[run_index](domains))
            stats.revisions += 1
            if after is None:
                stats.wipeouts += 1
                self.run_weights[run_index] += 1
                if active:
                    observer.on_revise(run_index, [], list(queue), "gac")
                    observer.on_wipeout(run_index, None)
                    observer.on_propagation_end(False)
                return False
            changes: List[Change] = []
            for cell, mask in zip(cells, after):
                if mask != domains[cell]:
                    self._set_domain(cell, mask, changes)
                    for other in csp.runs_of[cell]:  # the run itself is already consistent
                        if other != run_index and other not in queued:
                            queue.append(other)
                            queued.add(other)
            if active:
                observer.on_revise(run_index, changes, list(queue), "gac")
        if active:
            observer.on_propagation_end(True)
        return True

