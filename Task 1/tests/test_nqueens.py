"""Run from the `Task 1` folder with: python -m unittest discover -s tests -v"""
import os
import random
import sys
import unittest
from itertools import combinations

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nqueens.board import Placement
from nqueens.encoding import (
    AuxiliaryVariables, CnfEncoder, ConstraintDiscovery, PairwiseEncoding, SequentialCounterEncoding, SquareVariables,
)
from nqueens.min_conflicts import (
    ConflictTracker,
    MinConflictsSolver,
    MostConflictedSelector,
    MostConflictedTabuSelector,
    RandomConflictedSelector,
)
from nqueens.sat_solver import Glucose3QueensSolver

# Number of distinct solutions of N-Queens for N = 1..8 (OEIS A000170).
KNOWN_SOLUTION_COUNTS = {1: 1, 2: 0, 3: 0, 4: 2, 5: 10, 6: 4, 7: 40, 8: 92}


class PlacementTest(unittest.TestCase):
    def test_accepts_known_solution(self):
        self.assertTrue(Placement.from_columns([1, 3, 0, 2]).is_solution())

    def test_rejects_shared_column_and_diagonal(self):
        self.assertFalse(Placement.from_columns([0, 0, 1, 3]).is_solution())
        self.assertFalse(Placement.from_columns([0, 1, 3, 2]).is_solution())

    def test_rejects_wrong_queen_count(self):
        self.assertFalse(Placement(4, ((0, 1), (1, 3), (2, 0))).is_solution())


class EncodingTest(unittest.TestCase):
    def test_variable_mapping_is_a_bijection(self):
        variables = SquareVariables(7)
        seen = {variables.variable(r, c) for r in range(7) for c in range(7)}
        self.assertEqual(seen, set(range(1, 50)))
        self.assertEqual(variables.square(variables.variable(3, 5)), (3, 5))

    def test_attack_lines_contain_exactly_the_attacking_pairs(self):
        n = 6
        from_lines = set()
        for line in ConstraintDiscovery(n).attack_lines():
            from_lines.update(combinations(sorted(line.squares), 2))
        squares = [(r, c) for r in range(n) for c in range(n)]
        by_rules = {
            (a, b)
            for a, b in combinations(squares, 2)
            if a[0] == b[0] or a[1] == b[1] or abs(a[0] - b[0]) == abs(a[1] - b[1])
        }
        self.assertEqual(from_lines, by_rules)

    def test_clause_count_matches_closed_form_without_duplicates(self):
        for n in range(2, 16):  # at N=1 the only row and column coincide
            formula = CnfEncoder(n).encode()
            self.assertEqual(formula.num_clauses, CnfEncoder.expected_clause_count(n))
            unique = {tuple(sorted(clause)) for clause in formula.clauses}
            self.assertEqual(len(unique), formula.num_clauses)

    def test_cnf_models_are_exactly_the_real_solutions(self):
        from pysat.solvers import Glucose3

        for n, expected in KNOWN_SOLUTION_COUNTS.items():
            encoder = CnfEncoder(n)
            with Glucose3(bootstrap_with=encoder.encode().clauses) as solver:
                count = 0
                for model in solver.enum_models():
                    queens = tuple(encoder.variables.square(lit) for lit in model if lit > 0)
                    self.assertTrue(Placement(n, queens).is_solution())
                    count += 1
            self.assertEqual(count, expected, f"N={n}")


class SequentialCounterTest(unittest.TestCase):
    def satisfying_assignments(self, literals_count, encoding):
        """Assignments of the x variables that some setting of the extra variables satisfies."""
        from itertools import product

        from pysat.solvers import Glucose3

        literals = list(range(1, literals_count + 1))
        clauses = encoding.encode(literals, AuxiliaryVariables(literals_count + 1))
        allowed = set()
        with Glucose3(bootstrap_with=clauses) as solver:
            for values in product((False, True), repeat=literals_count):
                assumptions = [lit if value else -lit for lit, value in zip(literals, values)]
                if solver.solve(assumptions=assumptions):
                    allowed.add(values)
        return allowed

    def test_means_exactly_at_most_one(self):
        for k in range(2, 11):
            allowed = self.satisfying_assignments(k, SequentialCounterEncoding())
            expected = {tuple(i == j for j in range(k)) for i in range(k)} | {(False,) * k}
            self.assertEqual(allowed, expected, f"k={k}")

    def test_clause_and_variable_counts_of_a_long_line(self):
        k = 20
        auxiliary = AuxiliaryVariables(k + 1)
        clauses = SequentialCounterEncoding().encode(list(range(1, k + 1)), auxiliary)
        self.assertEqual(len(clauses), 3 * k - 4)
        self.assertEqual(auxiliary.next - (k + 1), k - 1)

    def test_short_lines_use_the_smaller_pairwise_form(self):
        auxiliary = AuxiliaryVariables(10)
        clauses = SequentialCounterEncoding().encode([1, 2, 3], auxiliary)
        self.assertEqual(len(clauses), 3)
        self.assertEqual(auxiliary.next, 10)

    def test_models_project_to_exactly_the_real_solutions(self):
        from pysat.solvers import Glucose3

        for n, expected in KNOWN_SOLUTION_COUNTS.items():
            encoder = CnfEncoder(n, SequentialCounterEncoding())
            found = set()
            with Glucose3(bootstrap_with=encoder.encode().clauses) as solver:
                while solver.solve():
                    queens = encoder.queens_in_model(solver.get_model())
                    self.assertTrue(Placement(n, queens).is_solution())
                    found.add(frozenset(queens))
                    # Exclude this placement, whatever values the extra variables took.
                    solver.add_clause([-encoder.variables.variable(r, c) for r, c in queens])
            self.assertEqual(len(found), expected, f"N={n}")

    def test_much_smaller_than_pairwise_on_large_boards(self):
        for n in (50, 120):
            pairwise = CnfEncoder(n, PairwiseEncoding()).encode().num_clauses
            sequential = CnfEncoder(n, SequentialCounterEncoding()).encode().num_clauses
            self.assertLess(sequential * 4, pairwise)

    def test_solver_gives_valid_solutions(self):
        for n in (4, 8, 20, 60, 150):
            result = Glucose3QueensSolver(SequentialCounterEncoding()).solve(n)
            self.assertTrue(result.placement.is_solution())

    def test_still_reports_unsatisfiable_boards(self):
        for n in (2, 3):
            self.assertFalse(Glucose3QueensSolver(SequentialCounterEncoding()).solve(n).satisfiable)


class SatSolverTest(unittest.TestCase):
    def test_finds_valid_solution_for_increasing_n(self):
        for n in (4, 5, 8, 12, 20, 30):
            result = Glucose3QueensSolver().solve(n)
            self.assertTrue(result.satisfiable)
            self.assertTrue(result.placement.is_solution())
            self.assertEqual(result.num_clauses, CnfEncoder.expected_clause_count(n))

    def test_reports_unsatisfiable_boards(self):
        for n in (2, 3):
            result = Glucose3QueensSolver().solve(n)
            self.assertFalse(result.satisfiable)
            self.assertIsNone(result.placement)


class ConflictTrackerTest(unittest.TestCase):
    @staticmethod
    def direct(tracker, row, col):
        return sum(
            1
            for other, other_col in enumerate(tracker.queens)
            if other != row and (other_col == col or abs(other_col - col) == abs(other - row))
        )

    def assert_matches_direct_counting(self, tracker):
        n = tracker.n
        for row in range(n):
            for col in range(n):
                self.assertEqual(tracker.conflicts_if_placed(row, col), self.direct(tracker, row, col))
        expected = [self.direct(tracker, r, tracker.queens[r]) for r in range(n)]
        self.assertEqual(tracker.conflicts, expected)
        self.assertEqual(sorted(tracker.conflicted), [r for r in range(n) if expected[r] > 0])

    def test_counters_agree_with_direct_counting(self):
        tracker = ConflictTracker(MinConflictsSolver.random_assignment(12, seed=3))
        self.assert_matches_direct_counting(tracker)
        tracker.move(4, 7)
        tracker.move(9, 0)
        self.assert_matches_direct_counting(tracker)

    def test_incremental_updates_stay_right_over_many_random_moves(self):
        rng = random.Random(9)
        for n in (5, 9, 16):
            tracker = ConflictTracker(MinConflictsSolver.random_assignment(n, seed=n))
            for _ in range(300):
                tracker.move(rng.randrange(n), rng.randrange(n))
                self.assert_matches_direct_counting(tracker)

    def test_moving_to_the_same_value_changes_nothing(self):
        tracker = ConflictTracker([0, 1, 2, 3])
        before = list(tracker.conflicts)
        tracker.move(2, 2)
        self.assertEqual(tracker.conflicts, before)

    def test_value_choice_is_a_true_minimum(self):
        rng = random.Random(4)
        tracker = ConflictTracker(MinConflictsSolver.random_assignment(40, seed=1))
        for row in range(40):
            chosen = MinConflictsSolver._min_conflict_value(tracker, row, rng)
            values = [tracker.conflicts_if_placed(row, col) for col in range(40)]
            self.assertEqual(values[chosen], min(values))


class MinConflictsTest(unittest.TestCase):
    SELECTORS = (RandomConflictedSelector, MostConflictedSelector, MostConflictedTabuSelector)

    def test_every_returned_solution_is_valid(self):
        for selector_cls in self.SELECTORS:
            for n in (4, 8, 16, 50):
                for seed in range(5):
                    result = MinConflictsSolver(selector_cls(), max_steps=20000).solve(n, seed)
                    if result.solved:
                        self.assertTrue(result.placement.is_solution())
                    else:
                        self.assertGreater(result.remaining_conflicts, 0)

    def test_same_seed_is_reproducible(self):
        first = MinConflictsSolver(MostConflictedTabuSelector()).solve(32, seed=11)
        second = MinConflictsSolver(MostConflictedTabuSelector()).solve(32, seed=11)
        self.assertEqual(first.steps, second.steps)
        self.assertEqual(first.placement, second.placement)

    def test_selectors_share_the_initial_assignment(self):
        self.assertEqual(
            MinConflictsSolver.random_assignment(20, 5),
            MinConflictsSolver.random_assignment(20, 5),
        )

    def test_restarts_solve_boards_that_get_stuck(self):
        for selector_cls in self.SELECTORS:
            for seed in range(30):
                result = MinConflictsSolver(selector_cls(), max_steps=2000).solve_with_restarts(6, seed)
                self.assertTrue(result.solved)
                self.assertTrue(result.placement.is_solution())

    def test_restarts_give_up_on_unsolvable_boards(self):
        solver = MinConflictsSolver(RandomConflictedSelector(), max_steps=50)
        self.assertFalse(solver.solve_with_restarts(3, seed=0, max_restarts=3).solved)

    def test_step_limit_is_respected(self):
        result = MinConflictsSolver(RandomConflictedSelector(), max_steps=1).solve(200, seed=1)
        self.assertLessEqual(result.steps, 1)
        self.assertFalse(result.solved)


if __name__ == "__main__":
    unittest.main()


class ReferenceTabuSelector(MostConflictedTabuSelector):
    """The proposed heuristic as first written: one Python loop over the conflicted rows."""

    def reset(self, n):
        self._last_moved = [-self.tenure - 1] * n

    def select(self, tracker, step, rng):
        earliest_allowed = step - self.tenure
        conflicts = tracker.conflicts
        worst, best = 0, []
        for row in tracker.conflicted:
            count = conflicts[row]
            if count >= worst and self._last_moved[row] < earliest_allowed:
                if count > worst:
                    worst, best = count, [row]
                else:
                    best.append(row)
        if not best:
            worst = max(conflicts[row] for row in tracker.conflicted)
            best = [row for row in tracker.conflicted if conflicts[row] == worst]
        return rng.choice(best)

    def notify_move(self, variable, step):
        self._last_moved[variable] = step


class ReferenceSolver(MinConflictsSolver):
    """The min-conflicts value choice as first written: a Python list of every tied column."""

    @staticmethod
    def _min_conflict_value(tracker, row, rng):
        counts = [tracker.conflicts_if_placed(row, col) for col in range(tracker.n)]
        lowest = min(counts)
        return rng.choice([col for col, count in enumerate(counts) if count == lowest])


class FasterSelectionTest(unittest.TestCase):
    """The C-level scans must reproduce the plain loops exactly: same choices, same random draws."""

    def test_random_item_with_matches_choice_on_the_list_of_matches(self):
        from nqueens.min_conflicts import _random_item_with
        for seed in range(400):
            rng = random.Random(seed)
            counts = [rng.randrange(4) for _ in range(rng.randrange(1, 60))]
            target = rng.choice(counts)
            items = list(range(100, 100 + len(counts)))
            plain, fast = random.Random(seed + 1), random.Random(seed + 1)
            expected = plain.choice([item for item, count in zip(items, counts) if count == target])
            self.assertEqual(_random_item_with(items, counts, target, fast), expected)
            self.assertEqual(plain.random(), fast.random())  # both used the same randomness

    def test_standard_runs_are_step_for_step_those_of_the_plain_loops(self):
        for n in (8, 25, 120):
            for seed in range(4):
                fast = MinConflictsSolver(RandomConflictedSelector(), max_steps=3000).solve(n, seed)
                reference = ReferenceSolver(RandomConflictedSelector(), max_steps=3000).solve(n, seed)
                self.assertEqual((fast.steps, fast.solved, fast.remaining_conflicts),
                                 (reference.steps, reference.solved, reference.remaining_conflicts), f"N={n}, seed {seed}")
                if fast.solved:
                    self.assertEqual(fast.placement.queens, reference.placement.queens)

    @staticmethod
    def random_tracker(rng, n, moves):
        tracker = ConflictTracker([rng.randrange(n) for _ in range(n)])
        for _ in range(moves):
            tracker.move(rng.randrange(n), rng.randrange(n))
        return tracker

    def test_heuristic_picks_among_exactly_the_most_conflicted_rows_that_are_not_tabu(self):
        """The same set as the plain loop, and every row of it can be picked."""
        rng = random.Random(4)
        checked = 0
        for _ in range(80):
            n = rng.choice((6, 12, 30))
            tracker = self.random_tracker(rng, n, rng.randrange(40))
            if not tracker.conflicted:
                continue
            recent = rng.sample(range(n), 3)
            fast, reference = MostConflictedTabuSelector(tenure=3), ReferenceTabuSelector(tenure=3)
            for selector in (fast, reference):
                selector.reset(n)
                for step, row in enumerate(recent):
                    selector.notify_move(row, step)
            # The reference keeps every row it could return; collect them over many draws.
            expected = {reference.select(tracker, 3, random.Random(seed)) for seed in range(300)}
            picked = {fast.select(tracker, 3, random.Random(seed)) for seed in range(300)}
            self.assertEqual(picked, expected)
            checked += 1
        self.assertGreater(checked, 50)

    def test_most_conflicted_picks_among_the_rows_with_the_most_conflicts(self):
        rng = random.Random(6)
        for _ in range(40):
            tracker = self.random_tracker(rng, 15, rng.randrange(20))
            if not tracker.conflicted:
                continue
            worst = max(tracker.conflicts)
            expected = {row for row in tracker.conflicted if tracker.conflicts[row] == worst}
            picked = {MostConflictedSelector().select(tracker, 0, random.Random(seed)) for seed in range(200)}
            self.assertEqual(picked, expected)

    def test_buckets_hold_exactly_the_rows_with_each_conflict_count(self):
        rng = random.Random(8)
        for n in (1, 4, 13, 40):
            tracker = ConflictTracker([rng.randrange(n) for _ in range(n)])
            for move in range(400):
                tracker.move(rng.randrange(n), rng.randrange(n))
                if move % 20:
                    continue
                for count in range(1, 3 * n):
                    self.assertEqual(sorted(tracker.buckets[count]),
                                     [row for row in range(n) if tracker.conflicts[row] == count])
                self.assertEqual(tracker.top_count(), max(tracker.conflicts))
                self.assertEqual(sorted(tracker.conflicted), [row for row in range(n) if tracker.conflicts[row] > 0])

    def test_tabu_list_holds_only_the_last_repairs(self):
        selector = MostConflictedTabuSelector(tenure=3)
        selector.reset(10)
        for step, row in enumerate((4, 5, 6, 7)):
            selector.notify_move(row, step)
        self.assertEqual(list(selector._recent), [5, 6, 7])
