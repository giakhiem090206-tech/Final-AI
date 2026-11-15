"""Run from the `Task 1` folder with: python -m unittest discover -s tests -v

The replay and the solver service are plain Python; the window is drawn off-screen
(SDL's dummy video driver), so these tests also run without a display.
"""
import os
import random
import sys
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nqueens.encoding import CnfEncoder
from nqueens.gui.board_view import attack_segments
from nqueens.gui.replay import MinConflictsPlayer
from nqueens.gui.service import ALGORITHMS, SolverService

BY_KEY = {algorithm.key: algorithm for algorithm in ALGORITHMS}
from nqueens.min_conflicts import (
    ConflictTracker,
    MinConflictsSolver,
    MinConflictsTrace,
    MostConflictedTabuSelector,
    RandomConflictedSelector,
)


class EncodingHelpersTest(unittest.TestCase):
    def test_breakdown_adds_up_to_the_clauses_built(self):
        for n in range(1, 13):
            self.assertEqual(sum(CnfEncoder(n).clause_breakdown().values()), CnfEncoder(n).encode().num_clauses)

    def test_clauses_with_square_matches_the_formula(self):
        for n in range(1, 8):
            encoder = CnfEncoder(n)
            clauses = encoder.encode().clauses
            for r in range(n):
                for c in range(n):
                    variable = encoder.variables.variable(r, c)
                    found = sum(1 for clause in clauses if variable in clause or -variable in clause)
                    self.assertEqual(CnfEncoder.clauses_with_square(n, r, c), found, (n, r, c))


class TraceTest(unittest.TestCase):
    SELECTORS = (RandomConflictedSelector, MostConflictedTabuSelector)

    def test_recording_does_not_change_the_search(self):
        for selector_cls in self.SELECTORS:
            for n, seed in ((8, 0), (8, 3), (30, 1)):
                plain = MinConflictsSolver(selector_cls()).solve_with_restarts(n, seed)
                traced = MinConflictsSolver(selector_cls()).solve_with_restarts(n, seed, trace=MinConflictsTrace())
                self.assertEqual((plain.steps, plain.restarts, plain.placement),
                                 (traced.steps, traced.restarts, traced.placement))

    def test_replaying_the_trace_reaches_the_returned_solution(self):
        for selector_cls in self.SELECTORS:
            for seed in range(5):
                trace = MinConflictsTrace()
                result = MinConflictsSolver(selector_cls()).solve_with_restarts(12, seed, trace=trace)
                player = MinConflictsPlayer(trace)
                self.assertEqual(sum(len(a.moves) for a in trace.attempts), result.steps)
                self.assertEqual(len(trace.attempts), result.restarts + 1)
                player.seek(player.frame_count - 1)
                self.assertTrue(player.at_end)
                self.assertEqual(tuple(enumerate(player.queens)), result.placement.queens)
                self.assertEqual(player.pairs[-1], 0)


class PlayerTest(unittest.TestCase):
    @staticmethod
    def restarted_trace():
        trace = MinConflictsTrace()  # a tiny step limit forces several attempts
        MinConflictsSolver(RandomConflictedSelector(), max_steps=6).solve_with_restarts(14, 2, 4, trace)
        return trace

    @staticmethod
    def replayed(trace, frame):
        """The board at `frame`, rebuilt from scratch."""
        for attempt in trace.attempts:
            if frame <= len(attempt.moves):
                tracker = ConflictTracker(attempt.initial)
                for row, _, new in attempt.moves[:frame]:
                    tracker.move(row, new)
                return tracker
            frame -= len(attempt.moves) + 1
        raise IndexError(frame)

    def test_frames_cover_every_attempt(self):
        trace = self.restarted_trace()
        self.assertGreater(len(trace.attempts), 1)
        player = MinConflictsPlayer(trace)
        self.assertEqual(player.frame_count, sum(len(a.moves) + 1 for a in trace.attempts))
        self.assertEqual(len(player.pairs), player.frame_count)
        self.assertEqual(player.locate(player.starts[1]), (1, 0))
        self.assertEqual(player.locate(player.starts[1] - 1), (0, len(trace.attempts[0].moves)))

    def test_any_sequence_of_seeks_matches_a_fresh_replay(self):
        trace = self.restarted_trace()
        player = MinConflictsPlayer(trace)
        rng = random.Random(5)
        for _ in range(300):
            if rng.random() < 0.5:
                target = rng.randrange(player.frame_count)
            else:
                target = player.frame + rng.choice((-2, -1, 1, 2))
            player.seek(target)
            reference = self.replayed(trace, player.frame)
            self.assertEqual(player.queens, reference.queens)
            self.assertEqual(player.row_conflicts, reference.conflicts)
            self.assertEqual(player.attacking_pairs, reference.attacking_pairs())

    def test_next_move_is_the_recorded_repair(self):
        trace = MinConflictsTrace()
        MinConflictsSolver(MostConflictedTabuSelector()).solve(10, 4, trace)
        player = MinConflictsPlayer(trace)
        for step, move in enumerate(trace.attempts[0].moves):
            player.seek(step)
            self.assertEqual(player.next_move(), move)
            self.assertEqual(player.queens[move[0]], move[1])
            counts = player.candidate_counts(move[0])
            self.assertEqual(counts[move[2]], min(counts))  # the value chosen has the fewest conflicts
        player.seek(player.frame_count - 1)
        self.assertIsNone(player.next_move())


class AttackSegmentsTest(unittest.TestCase):
    def test_marks_exactly_the_attacked_queens(self):
        segments, attacked = attack_segments([(0, 0), (1, 2), (2, 2), (3, 3)])
        self.assertEqual(attacked, {(0, 0), (1, 2), (2, 2), (3, 3)})
        self.assertIn(((0, 0), (3, 3)), segments)  # one segment for the whole diagonal
        self.assertIn(((1, 2), (2, 2)), segments)
        self.assertEqual(attack_segments([(0, 1), (1, 3), (2, 0), (3, 2)]), ([], set()))


class HandPlacedQueensTest(unittest.TestCase):
    def test_glucose3_keeps_the_queens_given_as_assumptions(self):
        from nqueens.sat_solver import Glucose3QueensSolver

        plain = Glucose3QueensSolver().solve(8)
        for fixed in ([(0, 0)], [(0, 0), (1, 4)], [(3, 5), (6, 1)]):
            result = Glucose3QueensSolver().solve(8, fixed)
            self.assertTrue(result.satisfiable, fixed)
            self.assertTrue(result.placement.is_solution())
            self.assertTrue(set(fixed) <= set(result.placement.queens))
            self.assertEqual(result.num_clauses, plain.num_clauses)  # assumptions add no clause

    def test_glucose3_reports_queens_that_no_solution_contains(self):
        from nqueens.sat_solver import Glucose3QueensSolver

        self.assertFalse(Glucose3QueensSolver().solve(8, [(0, 0), (1, 1)]).satisfiable)  # same diagonal
        self.assertFalse(Glucose3QueensSolver().solve(4, [(0, 0)]).satisfiable)  # no 4-queens solution uses a corner

    def test_min_conflicts_starts_from_the_given_board(self):
        start = [0, 4, 7, 5, 2, 6, 1, 1]
        trace = MinConflictsTrace()
        result = MinConflictsSolver(MostConflictedTabuSelector()).solve_with_restarts(8, 0, trace=trace, initial=start)
        self.assertEqual(trace.attempts[0].initial, start)
        self.assertTrue(result.solved)
        with self.assertRaises(ValueError):
            MinConflictsSolver(RandomConflictedSelector()).solve(8, 0, initial=[0] * 7)

    def test_service_passes_the_queens_to_each_solver(self):
        service = SolverService()
        sat = service.run(BY_KEY["sat"], 8, 0, [(2, 2)])
        self.assertEqual(sat.fixed, ((2, 2),))
        self.assertIn((2, 2), sat.placement.queens)
        self.assertEqual(service.run(BY_KEY["sat"], 8, 0, [(0, 0), (0, 5)]).status, "unsat")
        local = service.run(BY_KEY["tabu"], 8, 3, [(0, 3), (5, 5)])
        first = local.player.attempts[0].initial
        self.assertEqual((first[0], first[5]), (3, 5))
        self.assertEqual(first[1], MinConflictsSolver.random_assignment(8, 3)[1])  # other rows keep the seed's start


class ServiceTest(unittest.TestCase):
    def test_sat_outcomes(self):
        service = SolverService()
        solved = service.run(BY_KEY["sat"], 8, 0)
        self.assertEqual(solved.status, "solved")
        self.assertTrue(solved.valid)
        self.assertIsNone(solved.player)
        unsat = service.run(BY_KEY["sat"], 3, 0)
        self.assertEqual(unsat.status, "unsat")
        self.assertIsNone(unsat.placement)

    def test_min_conflicts_outcomes(self):
        service = SolverService()
        for key in ("standard", "tabu"):
            outcome = service.run(BY_KEY[key], 10, 1)
            self.assertEqual(outcome.status, "solved")
            self.assertTrue(outcome.valid)
            self.assertIsNotNone(outcome.player)
        self.assertEqual(service.run(BY_KEY["tabu"], 2, 0).status, "unsolved")

    def test_breakdown_labels_follow_the_counts(self):
        parts = SolverService().cnf_breakdown(8)
        self.assertEqual([count for _, count in parts], [16, 448, 280])


class AppTest(unittest.TestCase):
    """Drives the window off-screen: every state must draw without error."""

    @classmethod
    def setUpClass(cls):
        import pygame
        from nqueens.gui.app import NQueensApp

        cls.pygame = pygame
        cls.app = NQueensApp((1220, 800))

    @classmethod
    def tearDownClass(cls):
        cls.pygame.quit()

    def solve(self):
        self.app.start_solve()
        deadline = time.time() + 30
        while self.app.busy and time.time() < deadline:
            time.sleep(0.01)
            self.app.poll()
        self.assertFalse(self.app.busy)

    def key(self, key, mod=0):
        self.app.handle(self.pygame.event.Event(self.pygame.KEYDOWN, key=key, mod=mod))

    def test_every_algorithm_and_size_draws(self):
        app = self.app
        for size in ((960, 680), (1220, 800), (1600, 950)):
            app.resize(size)
            for index in range(3):
                app.select_algorithm(index)
                for n in (1, 3, 8, 32):
                    app.set_n(n)
                    app.draw()
                    self.solve()
                    app.draw()
                    self.assertIsNotNone(app.outcome)
                    self.assertNotEqual(app.outcome.status, "error", app.outcome.error)

    def test_keyboard_controls_the_replay(self):
        app, pygame = self.app, self.pygame
        app.resize((1220, 800))
        app.set_n(8)
        self.key(pygame.K_3)
        self.assertEqual(app.algorithm.key, "tabu")
        self.key(pygame.K_RETURN)
        self.solve()
        player = app.player
        self.assertTrue(app.playing)
        self.key(pygame.K_SPACE)
        self.assertFalse(app.playing)
        self.key(pygame.K_HOME)
        self.assertEqual(player.frame, 0)
        self.key(pygame.K_RIGHT)
        self.assertEqual(player.frame, 1)
        self.key(pygame.K_END)
        self.assertTrue(player.at_end)
        app.draw()
        self.key(pygame.K_r)
        self.assertEqual(app.seed, 1)
        self.assertIsNone(app.outcome)  # a new seed drops the old run

    def test_playing_advances_and_stops_at_the_end(self):
        app = self.app
        app.select_algorithm(1)
        app.set_n(16)
        self.solve()
        player = app.player
        app.advance(0.5)  # 8 steps per second by default
        self.assertEqual(player.frame, min(4, player.frame_count - 1))
        app.advance(10_000)
        self.assertTrue(player.at_end)
        self.assertFalse(app.playing)

    def test_changing_settings_discards_a_run_in_progress(self):
        app = self.app
        app.select_algorithm(0)
        app.set_n(8)
        app.start_solve()
        app.set_n(9)
        time.sleep(0.5)
        app.poll()
        self.assertIsNone(app.outcome)

    def test_mouse_on_widgets_and_timeline(self):
        app, pygame = self.app, self.pygame
        app.resize((1220, 800))
        app.select_algorithm(2)
        app.set_n(8)
        app.draw()
        click = lambda pos: app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        click(app.n_stepper.plus.rect.center)
        self.assertEqual(app.n, 9)
        click(app.solve_button.rect.center)
        self.solve()
        app.draw()
        timeline = app.timeline.rect
        click((timeline.right - 1, timeline.centery))
        self.assertTrue(app.player.at_end)
        app.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=(timeline.x, timeline.centery), rel=(0, 0), buttons=(1, 0, 0)))
        self.assertEqual(app.player.frame, 0)
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(timeline.x, timeline.centery)))
        self.assertFalse(app.dragging)
        click(app.options.item_rect(0).center)
        self.assertEqual(app.algorithm.key, "sat")

    def test_clicking_the_board_places_queens(self):
        app, pygame = self.app, self.pygame
        click = lambda square: app.handle(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=app.board.cell_rect(*square).center))
        app.resize((1220, 800))
        app.select_algorithm(0)
        app.set_n(6)
        app.draw()
        click((0, 1))
        click((0, 4))  # Glucose3: one variable per square, two queens in a row are allowed
        self.assertEqual(app.user_queens, {(0, 1), (0, 4)})
        app.draw()
        self.assertEqual(app._status()[0], "warning")  # they attack each other
        click((0, 4))  # a second click removes it
        self.assertEqual(app.user_queens, {(0, 1)})
        self.solve()
        self.assertEqual(app.outcome.status, "solved")
        self.assertIn((0, 1), app.outcome.placement.queens)
        app.draw()

        app.select_algorithm(2)  # Min-Conflicts: one variable per row, a click moves the row's queen
        app.draw()
        click((3, 0))
        click((3, 2))
        self.assertEqual(app.user_queens, {(0, 1), (3, 2)})
        self.solve()
        self.assertEqual(app.player.attempts[0].initial[3], 2)
        app.draw()
        click((5, 5))  # clicking on a result starts a new board from it
        self.assertIsNone(app.outcome)
        self.assertEqual(len(app.user_queens), 6)
        self.key(pygame.K_c)
        self.assertEqual(app.user_queens, set())


if __name__ == "__main__":
    unittest.main()
