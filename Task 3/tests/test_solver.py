"""Run from the `Task 3` folder with: python -m unittest discover -s tests -v"""
import os
import random
import sys
import unittest
from itertools import permutations

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kakuro.csp import FULL_DOMAIN, KakuroCSP, RunFilter, largest_sum, smallest_sum
from kakuro.generator import BoardGenerator
from kakuro.play import PlayBoard
from kakuro.puzzle import EXAMPLE_BOARD, EXTRA_BOARD_NAME, KakuroPuzzle, PuzzleError, SolutionChecker, load_builtin
from kakuro.solver import (
    PROPAGATE_FC, PROPAGATE_MAC, PROPAGATE_NONE, VAL_ASCENDING, VAL_LCV, VAR_DOM_WDEG, VAR_MRV, VAR_MRV_DEGREE,
    VAR_STATIC, BacktrackingSolver, SolverConfig,
)

EXAMPLE, COMPLEX = "Example (5x5)", "Complex (9x9)"
# Worked out by hand, independently of the program.
EXAMPLE_SOLUTION = [8, 4, 9, 3, 1, 8, 5, 1, 2, 3, 9, 7]
STRONG_CONFIGS = [
    SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_LCV),
    SolverConfig(PROPAGATE_MAC, VAR_MRV, VAL_ASCENDING),
    SolverConfig(PROPAGATE_MAC, VAR_STATIC, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_MRV_DEGREE, VAL_LCV),
    SolverConfig(PROPAGATE_FC, VAR_MRV, VAL_ASCENDING),
]


def mask(*digits):
    return sum(1 << d for d in digits)


class PuzzleParsingTest(unittest.TestCase):
    def test_example_board_matches_the_statement(self):
        puzzle = load_builtin(EXAMPLE)
        self.assertEqual(len(puzzle.cells), 12)
        self.assertEqual(sum(r.clue for r in puzzle.runs if r.direction == "across"), 60)
        self.assertEqual(sum(r.clue for r in puzzle.runs if r.direction == "down"), 60)
        self.assertEqual({r.clue for r in puzzle.runs if r.direction == "across"}, {12, 21, 11, 16})

    def test_complex_board_matches_the_statement(self):
        puzzle = load_builtin(COMPLEX)
        across = [r.clue for r in puzzle.runs if r.direction == "across"]
        down = [r.clue for r in puzzle.runs if r.direction == "down"]
        self.assertEqual(sorted(across), sorted([22, 3, 28, 14, 20, 17, 22, 28, 12, 14, 6, 39, 16, 8]))
        self.assertEqual(sorted(down), sorted([44, 16, 9, 15, 44, 17, 12, 29, 12, 11, 7, 12, 14, 7]))
        # All cells are counted once across and once down, so both totals must be equal.
        self.assertEqual(sum(across), sum(down))
        self.assertEqual(sum(across), 249)

    def test_every_run_has_the_expected_length(self):
        puzzle = load_builtin(COMPLEX)
        lengths = {(r.direction, r.start): len(r.cells) for r in puzzle.runs}
        self.assertEqual(lengths[("down", (0, 2))], 8)   # 44 in eight cells
        self.assertEqual(lengths[("down", (0, 7))], 8)
        self.assertEqual(lengths[("across", (2, 1))], 7)  # 28 in seven cells
        self.assertEqual(lengths[("across", (7, 0))], 7)  # 39 in seven cells

    def test_rejects_malformed_boards(self):
        bad = {
            "uneven rows": "X .\n.",
            "unknown token": "X Q\nX .",
            "clue without cells": "X 5\\\nX X",
            "cells without clue": "X X\n. .",
            "impossible clue": "X 3\\ 3\\\n\\50 . .\n\\50 . .",
            "not a number": "X a\\\nX .",
        }
        for name, text in bad.items():
            with self.assertRaises(PuzzleError, msg=name):
                KakuroPuzzle(name, text)


class SolutionCheckerTest(unittest.TestCase):
    def setUp(self):
        self.checker = SolutionChecker(load_builtin(EXAMPLE))

    def test_accepts_the_correct_solution(self):
        self.assertEqual(self.checker.problems(EXAMPLE_SOLUTION), [])

    def test_catches_a_wrong_sum(self):
        wrong = list(EXAMPLE_SOLUTION)
        wrong[0] = 7
        self.assertFalse(self.checker.is_valid(wrong))

    def test_catches_a_repeat_even_when_the_sum_is_right(self):
        puzzle = KakuroPuzzle("t", "X 3\\ 7\\\n\\4 . .\n\\6 . .")
        self.assertTrue(SolutionChecker(puzzle).is_valid([1, 3, 2, 4]))
        repeated = [2, 2, 1, 5]  # rows 4 and 6, columns 3 and 7: all sums right, but 2 + 2
        self.assertEqual(len(SolutionChecker(puzzle).problems(repeated)), 1)
        self.assertIn("repeats", SolutionChecker(puzzle).problems(repeated)[0])

    def test_catches_digits_out_of_range_and_wrong_length(self):
        wrong = list(EXAMPLE_SOLUTION)
        wrong[0] = 0
        self.assertFalse(self.checker.is_valid(wrong))
        self.assertFalse(self.checker.is_valid(EXAMPLE_SOLUTION[:-1]))


class RunFilterTest(unittest.TestCase):
    def brute_force(self, clue, domains):
        """GAC by definition: try every assignment."""
        supported = [0] * len(domains)
        found = False
        for digits in permutations(range(1, 10), len(domains)):
            if sum(digits) == clue and all(domains[i] >> d & 1 for i, d in enumerate(digits)):
                found = True
                for i, d in enumerate(digits):
                    supported[i] |= 1 << d
        return tuple(supported) if found else None

    def test_agrees_with_brute_force_on_random_domains(self):
        rng = random.Random(1)
        run_filter = RunFilter()
        for _ in range(1500):
            length = rng.randint(1, 4)
            domains = tuple(mask(*rng.sample(range(1, 10), rng.randint(1, 9))) for _ in range(length))
            clue = rng.randint(1, 30)
            self.assertEqual(run_filter.filter(clue, domains), self.brute_force(clue, domains))

    def test_known_digit_sets(self):
        run_filter = RunFilter()
        full = FULL_DOMAIN
        self.assertEqual(run_filter.filter(3, (full, full)), (mask(1, 2), mask(1, 2)))
        self.assertEqual(run_filter.filter(16, (full, full)), (mask(7, 9), mask(7, 9)))
        self.assertEqual(run_filter.filter(44, (full,) * 8), (mask(2, 3, 4, 5, 6, 7, 8, 9),) * 8)

    def test_all_different_needs_more_than_pairwise_reasoning(self):
        """Three cells limited to {1,2} cannot be all different, which pairwise checks miss."""
        self.assertIsNone(RunFilter().filter(4, (mask(1, 2), mask(1, 2), mask(1, 2))))

    def test_result_is_a_fixed_point(self):
        rng = random.Random(2)
        run_filter = RunFilter()
        for _ in range(300):
            length = rng.randint(2, 5)
            domains = tuple(mask(*rng.sample(range(1, 10), rng.randint(2, 9))) for _ in range(length))
            clue = rng.randint(3, 35)
            result = run_filter.filter(clue, domains)
            if result is not None:
                self.assertEqual(run_filter.filter(clue, result), result)


class PossibleDigitSetsTest(unittest.TestCase):
    def test_lists_the_digit_sets_a_run_can_still_use(self):
        csp = KakuroCSP(KakuroPuzzle("t", "X 5\\ 5\\\n\\4 . .\n\\6 . ."))
        run = next(r for r in csp.runs if r.direction == "across" and r.clue == 4)
        domains = csp.initial_domains()
        self.assertEqual(csp.possible_digit_sets(run, domains), [mask(1, 3)])

    def test_follows_the_domains(self):
        csp = KakuroCSP(load_builtin(COMPLEX))
        run = next(r for r in csp.runs if r.clue == 22 and r.direction == "across" and len(r.cells) == 3)
        domains = csp.initial_domains()
        before = len(csp.possible_digit_sets(run, domains))
        domains[run.cells[0]] = mask(5)  # 22 in three cells is {5,8,9} or {6,7,9}
        after = csp.possible_digit_sets(run, domains)
        self.assertLess(len(after), before)
        self.assertEqual(after, [mask(5, 8, 9)])


class GeneratorTest(unittest.TestCase):
    def test_boards_follow_the_rules_and_have_a_solution(self):
        for seed in range(15):
            puzzle = BoardGenerator(9, 9, 0.25, seed).generate()
            self.assertTrue(all(2 <= len(run.cells) <= 9 for run in puzzle.runs))
            result = BacktrackingSolver(KakuroCSP(puzzle)).solve()
            self.assertEqual(result.status, "solved")
            self.assertTrue(SolutionChecker(puzzle).is_valid(result.solution))

    def test_same_seed_gives_the_same_board(self):
        first = BoardGenerator(9, 9, 0.25, 3).generate()
        second = BoardGenerator(9, 9, 0.25, 3).generate()
        self.assertEqual(first.grid, second.grid)

    def test_repair_produces_a_unique_solution(self):
        puzzle = BoardGenerator(7, 7, 0.3, 1).generate_unique()
        self.assertIsNotNone(puzzle)
        result = BacktrackingSolver(KakuroCSP(puzzle)).solve(max_solutions=2)
        self.assertEqual(len(result.solutions), 1)
        self.assertFalse(result.limit_reached)

    def test_unique_boards_are_reproducible(self):
        first = BoardGenerator(7, 7, 0.3, 1).generate_unique()
        second = BoardGenerator(7, 7, 0.3, 1).generate_unique()
        self.assertEqual(first.grid, second.grid)

    def test_a_search_cut_short_is_reported_as_such(self):
        puzzle = BoardGenerator(16, 16, 0.25, 2).generate()
        result = BacktrackingSolver(KakuroCSP(puzzle), SolverConfig(), max_assignments=5).solve(max_solutions=2)
        self.assertTrue(result.limit_reached)
        finished = BacktrackingSolver(KakuroCSP(load_builtin(EXAMPLE))).solve(max_solutions=2)
        self.assertFalse(finished.limit_reached)


class DomWdegTest(unittest.TestCase):
    CONFIG = SolverConfig(PROPAGATE_MAC, VAR_DOM_WDEG, VAL_ASCENDING)

    def test_finds_the_right_solution(self):
        result = BacktrackingSolver(KakuroCSP(load_builtin(EXAMPLE)), self.CONFIG).solve()
        self.assertEqual(result.solution, EXAMPLE_SOLUTION)

    def test_learns_from_dead_ends(self):
        puzzle = BoardGenerator(16, 16, 0.25, 2).generate()
        solver = BacktrackingSolver(KakuroCSP(puzzle), self.CONFIG, time_limit=5)
        solver.solve()
        if solver.stats.wipeouts:
            self.assertGreater(max(solver.run_weights), 1)

    def test_is_complete_on_every_solution_of_a_small_board(self):
        puzzle = KakuroPuzzle("ambiguous", "X 5\\ 5\\\n\\4 . .\n\\6 . .")
        result = BacktrackingSolver(KakuroCSP(puzzle), self.CONFIG).solve(max_solutions=100)
        self.assertEqual(sorted(result.solutions), [[1, 3, 4, 2], [3, 1, 2, 4]])


class RestartTest(unittest.TestCase):
    def with_small_budget(self, csp, config):
        solver = BacktrackingSolver(csp, config)
        solver.RESTART_BASE = 1
        solver.RESTART_GROWTH = 1.2
        return solver

    def test_every_built_in_board_is_solved_correctly(self):
        for name in (EXAMPLE, COMPLEX):
            puzzle = load_builtin(name)
            result = BacktrackingSolver(KakuroCSP(puzzle), SolverConfig.best()).solve()
            self.assertTrue(SolutionChecker(puzzle).is_valid(result.solution))

    def test_frequent_restarts_still_give_a_valid_solution(self):
        puzzle = BoardGenerator(13, 13, 0.25, 4).generate()
        config = SolverConfig(PROPAGATE_FC, VAR_DOM_WDEG, VAL_ASCENDING, restarts=True)
        result = self.with_small_budget(KakuroCSP(puzzle), config).solve()
        self.assertEqual(result.status, "solved")
        self.assertGreater(result.stats.restarts, 0)
        self.assertTrue(SolutionChecker(puzzle).is_valid(result.solution))

    def test_restarts_stay_complete_on_an_unsatisfiable_board(self):
        csp = KakuroCSP(KakuroPuzzle("broken", EXAMPLE_BOARD.replace("\\21", "\\22")))
        config = SolverConfig(PROPAGATE_FC, VAR_DOM_WDEG, VAL_ASCENDING, restarts=True)
        self.assertEqual(self.with_small_budget(csp, config).solve().status, "unsatisfiable")

    def test_counting_solutions_never_restarts(self):
        puzzle = BoardGenerator(13, 13, 0.25, 4).generate()
        solver = BacktrackingSolver(KakuroCSP(puzzle), SolverConfig.best(), time_limit=2)
        solver.solve(max_solutions=2)
        self.assertEqual(solver.stats.restarts, 0)

    def test_domains_are_restored_at_each_restart(self):
        csp = KakuroCSP(KakuroPuzzle("broken", EXAMPLE_BOARD.replace("\\21", "\\22")))
        config = SolverConfig(PROPAGATE_FC, VAR_DOM_WDEG, VAL_ASCENDING, restarts=True)
        solver = self.with_small_budget(csp, config)
        solver.solve()
        self.assertEqual(solver.assignment, [0] * csp.num_variables)


class PlayBoardTest(unittest.TestCase):
    def setUp(self):
        self.csp = KakuroCSP(load_builtin(EXAMPLE))
        self.board = PlayBoard(self.csp)

    def test_correct_entries_finish_the_game(self):
        for cell, digit in enumerate(EXAMPLE_SOLUTION):
            self.assertFalse(self.board.is_solved())
            self.board.set_value(cell, digit)
            self.assertEqual(self.board.conflicts(), set())
        self.assertTrue(self.board.is_solved())

    def test_a_repeated_digit_marks_both_cells(self):
        first, second = self.csp.runs[0].cells[:2]
        self.board.set_value(first, 5)
        self.board.set_value(second, 5)
        self.assertTrue({first, second} <= self.board.conflicts())

    def test_a_clue_out_of_reach_is_a_conflict(self):
        run = next(r for r in self.csp.runs if r.clue == 11 and len(r.cells) == 4)  # at most 10 + 1 spare
        self.board.set_value(run.cells[0], 9)
        self.assertIn(run.cells[0], self.board.conflicts())

    def test_a_full_run_must_match_its_clue(self):
        run = next(r for r in self.csp.runs if r.clue == 16)
        self.board.set_value(run.cells[0], 1)
        self.board.set_value(run.cells[1], 2)
        self.assertTrue(set(run.cells) <= self.board.conflicts())

    def test_clearing_removes_the_conflict(self):
        first, second = self.csp.runs[0].cells[:2]
        self.board.set_value(first, 5)
        self.board.set_value(second, 5)
        self.board.clear(second)
        self.assertNotIn(first, self.board.conflicts())

    def test_candidates_follow_the_entries(self):
        csp = KakuroCSP(load_builtin(EXTRA_BOARD_NAME))  # propagation alone does not settle this board
        board = PlayBoard(csp)
        solution = board.solution()
        before = board.candidates()
        cell = next(i for i, mask_value in enumerate(before) if bin(mask_value).count("1") > 1)
        board.set_value(cell, solution[cell])
        after = board.candidates()
        self.assertTrue(all(new & ~old == 0 for old, new in zip(before, after)))
        self.assertLess(sum(bin(m).count("1") for m in after), sum(bin(m).count("1") for m in before))

    def test_wrong_entries_can_make_candidates_impossible(self):
        run = next(r for r in self.csp.runs if r.clue == 16)
        self.board.set_value(run.cells[0], 1)
        self.assertIsNone(self.board.candidates())

    def test_hints_finish_the_board_correctly_even_after_mistakes(self):
        self.board.set_value(0, 1 if EXAMPLE_SOLUTION[0] != 1 else 2)  # a wrong digit
        for _ in range(len(EXAMPLE_SOLUTION) + 1):
            hint = self.board.hint()
            if hint is None:
                break
            self.board.set_value(*hint)
        self.assertEqual(self.board.values, EXAMPLE_SOLUTION)
        self.assertIsNone(self.board.hint())

    def test_hint_prefers_the_selected_cell(self):
        self.assertEqual(self.board.hint(3), (3, EXAMPLE_SOLUTION[3]))


class BoundsTest(unittest.TestCase):
    def test_sum_bounds(self):
        self.assertEqual([smallest_sum(k) for k in (0, 1, 2, 9)], [0, 1, 3, 45])
        self.assertEqual([largest_sum(k) for k in (0, 1, 2, 9)], [0, 9, 17, 45])


class SolverTest(unittest.TestCase):
    def test_solves_the_example_in_every_configuration(self):
        csp = KakuroCSP(load_builtin(EXAMPLE))
        configs = STRONG_CONFIGS + [SolverConfig(PROPAGATE_NONE, VAR_STATIC, VAL_ASCENDING)]
        for config in configs:
            result = BacktrackingSolver(csp, config).solve()
            self.assertEqual(result.status, "solved", config.name)
            self.assertEqual(result.solution, EXAMPLE_SOLUTION, config.name)

    def test_solves_the_complex_board_with_a_valid_result(self):
        puzzle = load_builtin(COMPLEX)
        csp = KakuroCSP(puzzle)
        for config in STRONG_CONFIGS:
            result = BacktrackingSolver(csp, config).solve()
            self.assertEqual(result.status, "solved", config.name)
            self.assertEqual(SolutionChecker(puzzle).problems(result.solution), [], config.name)

    def test_both_boards_have_exactly_one_solution(self):
        for name in (EXAMPLE, COMPLEX):
            csp = KakuroCSP(load_builtin(name))
            result = BacktrackingSolver(csp).solve(max_solutions=2)
            self.assertEqual(len(result.solutions), 1, name)

    def test_every_configuration_finds_the_same_solution(self):
        csp = KakuroCSP(load_builtin(COMPLEX))
        answers = {tuple(BacktrackingSolver(csp, c).solve().solution) for c in STRONG_CONFIGS}
        self.assertEqual(len(answers), 1)

    def test_changing_a_clue_makes_a_board_unsatisfiable(self):
        """One clue more breaks the equality of across and down totals: no solution can exist."""
        for config in STRONG_CONFIGS:
            csp = KakuroCSP(KakuroPuzzle("broken", EXAMPLE_BOARD.replace("\\21", "\\22")))
            result = BacktrackingSolver(csp, config).solve()
            self.assertEqual(result.status, "unsatisfiable", config.name)
            self.assertEqual(result.solutions, [])

    def test_finds_all_solutions_of_an_ambiguous_board(self):
        puzzle = KakuroPuzzle("ambiguous", "X 5\\ 5\\\n\\4 . .\n\\6 . .")
        result = BacktrackingSolver(KakuroCSP(puzzle)).solve(max_solutions=100)
        self.assertEqual(sorted(result.solutions), [[1, 3, 4, 2], [3, 1, 2, 4]])

    def test_state_is_fully_restored_after_exhaustive_search(self):
        csp = KakuroCSP(load_builtin(EXAMPLE))
        for config in STRONG_CONFIGS:
            solver = BacktrackingSolver(csp, config)
            solver.solve(max_solutions=100)  # searches everything, undoing all it did
            self.assertEqual(solver.assignment, [0] * csp.num_variables)

    def test_random_tie_breaking_still_finds_the_unique_solution(self):
        puzzle = load_builtin(COMPLEX)
        csp = KakuroCSP(puzzle)
        reference = BacktrackingSolver(csp).solve().solution
        for seed in range(25):
            for config in (STRONG_CONFIGS[0], STRONG_CONFIGS[3]):
                result = BacktrackingSolver(csp, config, rng=random.Random(seed)).solve()
                self.assertEqual(result.solution, reference)

    def test_limits_are_respected_and_reported(self):
        csp = KakuroCSP(load_builtin(COMPLEX))
        config = SolverConfig(PROPAGATE_NONE, VAR_STATIC, VAL_ASCENDING)
        result = BacktrackingSolver(csp, config, max_assignments=50).solve()
        self.assertEqual(result.status, "limit")
        self.assertLessEqual(result.stats.assignments, 51)

    def test_stronger_propagation_never_needs_more_assignments(self):
        csp = KakuroCSP(load_builtin(COMPLEX))
        plain = SolverConfig(PROPAGATE_NONE, VAR_STATIC, VAL_ASCENDING)
        forward = SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING)
        mac = SolverConfig(PROPAGATE_MAC, VAR_STATIC, VAL_ASCENDING)
        counts = [BacktrackingSolver(csp, c, max_assignments=5_000_000).solve().stats.assignments
                  for c in (mac, forward, plain)]
        self.assertLessEqual(counts[0], counts[1])
        self.assertLessEqual(counts[1], counts[2])


if __name__ == "__main__":
    unittest.main()


class ReferenceRunFilter(RunFilter):
    """The run filter as first written: no pruning by sum in the forward pass."""

    @staticmethod
    def _compute(clue, domains):
        from kakuro.csp import BITS, MASK_SUM
        length = len(domains)
        layers = [{0}]
        for domain in domains:
            following = set()
            for used in layers[-1]:
                for bit in BITS[domain & ~used]:
                    following.add(used | bit)
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


class ReferenceSolver(BacktrackingSolver):
    """Variable selection as first written: degree and dom/wdeg weights recounted cell by cell."""

    def _select_variable(self):
        from kakuro.csp import POPCOUNT
        assignment, domains = self.assignment, self.domains
        order = self.config.variable_order
        if order == VAR_STATIC:
            return next((v for v in self.static_order if assignment[v] == 0), None)
        if order == VAR_DOM_WDEG:
            best, best_ratio = [], 0.0
            for variable, value in enumerate(assignment):
                if value != 0:
                    continue
                weight = 0
                for run_index in self.csp.runs_of[variable]:
                    if any(assignment[c] == 0 and c != variable for c in self.csp.runs[run_index].cells):
                        weight += self.run_weights[run_index]
                ratio = POPCOUNT[domains[variable]] / max(weight, 1)
                if not best or ratio < best_ratio:
                    best_ratio, best = ratio, [variable]
                elif ratio == best_ratio:
                    best.append(variable)
        else:
            best, best_key = [], None
            for variable, value in enumerate(assignment):
                if value != 0:
                    continue
                degree = 0
                if order == VAR_MRV_DEGREE:
                    degree = sum(1 for peer in self.csp.peers[variable] if assignment[peer] == 0)
                key = (POPCOUNT[domains[variable]], -degree)
                if best_key is None or key < best_key:
                    best_key, best = key, [variable]
                elif key == best_key:
                    best.append(variable)
        if not best:
            return None
        return self.rng.choice(best) if self.rng is not None else best[0]


class FasterSolverEquivalenceTest(unittest.TestCase):
    """The faster variable selection and run filter must make exactly the same search."""

    def test_same_search_as_the_plain_implementation(self):
        boards = [load_builtin(COMPLEX), load_builtin(EXTRA_BOARD_NAME)]
        boards += [BoardGenerator(12, 12, 0.22, seed).generate() for seed in range(4)]
        configs = [SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_ASCENDING),
                   SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_LCV),
                   SolverConfig(PROPAGATE_FC, VAR_MRV_DEGREE, VAL_ASCENDING),
                   SolverConfig(PROPAGATE_FC, VAR_DOM_WDEG, VAL_ASCENDING),
                   SolverConfig(PROPAGATE_MAC, VAR_MRV, VAL_ASCENDING),
                   SolverConfig.best()]
        for puzzle in boards:
            for config in configs:
                fast = BacktrackingSolver(KakuroCSP(puzzle), config, max_assignments=3000).solve()
                reference_csp = KakuroCSP(puzzle)
                reference_csp.filter = ReferenceRunFilter()
                reference = ReferenceSolver(reference_csp, config, max_assignments=3000).solve()
                self.assertEqual((fast.status, fast.solution), (reference.status, reference.solution))
                self.assertEqual((fast.stats.assignments, fast.stats.backtracks, fast.stats.revisions),
                                 (reference.stats.assignments, reference.stats.backtracks, reference.stats.revisions),
                                 f"{puzzle.name}, {config}")

    def test_pruned_run_filter_equals_the_plain_one_on_random_domains(self):
        rng = random.Random(3)
        fast, plain = RunFilter(), ReferenceRunFilter()
        for _ in range(3000):
            length = rng.randint(1, 9)
            clue = rng.randint(smallest_sum(length), largest_sum(length))
            domains = tuple(rng.randrange(1, 1024) & FULL_DOMAIN or 2 for _ in range(length))
            self.assertEqual(fast.filter(clue, domains), plain.filter(clue, domains), (clue, domains))
