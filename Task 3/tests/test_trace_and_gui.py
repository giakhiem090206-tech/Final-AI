"""Tests the replay against the solver, and drives the real interface through SDL's dummy driver."""
import os
import sys
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame

from kakuro.csp import KakuroCSP
from kakuro.gui import VisualizerApp
from kakuro.puzzle import load_builtin
from kakuro.solver import (
    PROPAGATE_FC, PROPAGATE_MAC, PROPAGATE_NONE, VAL_ASCENDING, VAL_LCV, VAR_MRV_DEGREE, VAR_STATIC,
    BacktrackingSolver, SolverConfig,
)
from kakuro.trace import ASSIGN, BACKTRACK, FINISH, SOLUTION, START, Replay, SearchTree, TraceRecorder

EXAMPLE, COMPLEX = "Example (5x5)", "Complex (9x9)"
CONFIGS = [
    SolverConfig(PROPAGATE_NONE, VAR_STATIC, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING),
    SolverConfig(PROPAGATE_FC, VAR_MRV_DEGREE, VAL_LCV),
    SolverConfig(PROPAGATE_MAC, VAR_MRV_DEGREE, VAL_LCV),
]


def record(name, config):
    csp = KakuroCSP(load_builtin(name))
    recorder = TraceRecorder(csp)
    result = BacktrackingSolver(csp, config, recorder).solve()
    return csp, recorder.events, result


class ReplayTest(unittest.TestCase):
    def test_observing_does_not_change_the_search(self):
        for config in CONFIGS:
            csp, events, recorded = record(COMPLEX, config)
            silent = BacktrackingSolver(KakuroCSP(load_builtin(COMPLEX)), config).solve()
            self.assertEqual(recorded.solution, silent.solution)
            self.assertEqual(recorded.stats, silent.stats)

    def test_replay_ends_with_the_solution_and_the_solver_counters(self):
        for name in (EXAMPLE, COMPLEX):
            for config in CONFIGS:
                csp, events, result = record(name, config)
                replay = Replay(events, csp.initial_domains())
                replay.seek(len(replay) - 1)
                final = replay.state
                expected = {i: v for i, v in enumerate(result.solution)}
                self.assertEqual(final.assigned, expected, config.name)
                self.assertEqual(final.assignments, result.stats.assignments)
                self.assertEqual(final.backtracks, result.stats.backtracks)
                self.assertEqual(final.revisions, result.stats.revisions)
                self.assertEqual(final.wipeouts, result.stats.wipeouts)

    def test_random_access_equals_replaying_from_the_start(self):
        """Stepping backwards must show exactly the state reached by going forwards."""
        csp, events, _ = record(COMPLEX, SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING))
        forward = Replay(events, csp.initial_domains())
        states = []
        for index in range(len(events)):
            forward.seek(index)
            states.append(forward.state.copy())
        jumping = Replay(events, csp.initial_domains())
        for index in list(range(len(events) - 1, -1, -7)) + [0, len(events) - 1, 5]:
            jumping.seek(index)
            self.assertEqual(jumping.state.domains, states[index].domains)
            self.assertEqual(jumping.state.assigned, states[index].assigned)
            self.assertEqual([e.variable for e in jumping.state.stack], [e.variable for e in states[index].stack])

    def test_backtracking_restores_the_domains_seen_before_the_assignment(self):
        csp, events, _ = record(COMPLEX, SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING))
        replay = Replay(events, csp.initial_domains())
        checked = 0
        open_assignments = {}
        for index, event in enumerate(events):
            replay.seek(index)
            if event.kind == ASSIGN:
                replay.seek(index - 1)
                open_assignments[event.depth] = list(replay.state.domains)
                replay.seek(index)
            elif event.kind == BACKTRACK:
                self.assertEqual(replay.state.domains, open_assignments[event.depth])
                checked += 1
        self.assertGreater(checked, 0)

    def test_stack_shows_failed_current_and_remaining_values(self):
        csp, events, _ = record(COMPLEX, SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING))
        replay = Replay(events, csp.initial_domains())
        first_backtrack = next(i for i, e in enumerate(events) if e.kind == BACKTRACK)
        replay.seek(first_backtrack)
        top = replay.state.stack[-1]
        self.assertEqual(top.variable, events[first_backtrack].variable)
        self.assertIn(events[first_backtrack].value, top.failed)
        self.assertIsNone(top.current)

    def test_events_start_and_finish_properly(self):
        for config in CONFIGS:
            _, events, _ = record(EXAMPLE, config)
            self.assertEqual(events[0].kind, START)
            self.assertEqual(events[-1].kind, FINISH)
            self.assertEqual(sum(e.kind == SOLUTION for e in events), 1)


class SearchTreeTest(unittest.TestCase):
    def test_tree_has_one_node_per_assignment_and_marks_the_solution_path(self):
        for config in CONFIGS:
            csp, events, result = record(COMPLEX, config)
            tree = SearchTree(events)
            self.assertEqual(len(tree.nodes), result.stats.assignments, config.name)
            on_path = [n for n in tree.nodes if n.solution]
            self.assertEqual(len(on_path), csp.num_variables, config.name)
            self.assertEqual(sorted(n.depth for n in on_path), list(range(1, csp.num_variables + 1)))
            self.assertTrue(all(n.died is None for n in on_path))

    def test_failed_nodes_are_exactly_the_backtracks(self):
        for config in CONFIGS:
            _, events, result = record(COMPLEX, config)
            tree = SearchTree(events)
            self.assertEqual(sum(n.died is not None for n in tree.nodes), result.stats.backtracks, config.name)

    def test_parents_are_one_level_up(self):
        _, events, _ = record(COMPLEX, SolverConfig(PROPAGATE_FC, VAR_STATIC, VAL_ASCENDING))
        tree = SearchTree(events)
        for node in tree.nodes:
            if node.parent is None:
                self.assertEqual(node.depth, 1)
            else:
                self.assertEqual(tree.nodes[node.parent].depth, node.depth - 1)


def click(position):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)


class InterfaceTest(unittest.TestCase):
    def setUp(self):
        self.app = VisualizerApp()

    def tearDown(self):
        pygame.quit()

    def test_every_step_of_every_configuration_can_be_drawn(self):
        for puzzle_index in range(2):
            self.app.puzzle_choice.selected = puzzle_index
            for propagation in range(3):
                self.app.propagation_choice.selected = propagation
                self.app.rebuild()
                step = max(1, len(self.app.replay) // 150)
                for index in range(0, len(self.app.replay), step):
                    self.app.replay.seek(index)
                    self.app.draw()

    def test_choosing_a_configuration_re_solves(self):
        app = self.app
        self.assertEqual(app.result.stats.backtracks, 0)  # MAC needs no search on this board
        app.choices[1].handle(click(app.choices[1]._cell(1).center))  # forward checking
        self.assertGreater(app.result.stats.backtracks, 0)
        self.assertTrue(app.valid)
        self.assertEqual(app.replay.position, 0)

    def test_transport_buttons(self):
        app = self.app
        app.step_forward()
        self.assertEqual(app.replay.position, 1)
        app.step_back()
        self.assertEqual(app.replay.position, 0)
        app.go_end()
        self.assertEqual(app.replay.position, len(app.replay) - 1)
        app.go_start()
        app.next_decision()
        self.assertIn(app.replay.event.kind, (ASSIGN, BACKTRACK))

    def test_play_advances_and_stops_at_the_end(self):
        app = self.app
        app.speed = 7
        app.toggle_play()
        for _ in range(200):
            app.update(0.5)
        self.assertFalse(app.playing)
        self.assertEqual(app.replay.position, len(app.replay) - 1)
        app.toggle_play()  # at the end, play starts over
        self.assertTrue(app.playing)
        self.assertEqual(app.replay.position, 0)

    def test_timeline_click_seeks(self):
        app = self.app
        bar = app.timeline
        app.handle(click((bar.centerx, bar.centery)))
        self.assertAlmostEqual(app.replay.position, (len(app.replay) - 1) / 2, delta=len(app.replay) * 0.05)

    def test_clicking_a_tree_node_jumps_to_that_moment(self):
        app = self.app
        app.propagation_choice.selected = 1  # forward checking, so that the tree has branches
        app.rebuild()
        app.go_end()
        node = app.tree.nodes[len(app.tree.nodes) // 2]
        app.handle(click(app.tree_panel._place(node)))
        self.assertEqual(app.replay.event.kind, ASSIGN)
        self.assertIn(app.replay.position, {n.born for n in app.tree.nodes})
        self.assertLess(app.replay.position, len(app.replay) - 1)

    def test_clicking_a_cell_shows_its_runs_and_clicking_again_hides_them(self):
        app = self.app
        r, c = app.puzzle.cells[0]
        rect = app.board._rect(r, c)
        app.handle(click(rect.center))
        self.assertEqual(len(app._inspected_runs()), 2)
        app.draw()
        app.handle(click(rect.center))
        self.assertEqual(app._inspected_runs(), [])

    def test_clicking_a_clue_shows_its_run(self):
        app = self.app
        clue_position = next(iter(app.puzzle.clues))
        app.handle(click(app.board._rect(*clue_position).center))
        runs = app._inspected_runs()
        self.assertTrue(runs)
        self.assertTrue(all(run.start == clue_position for run in runs))

    def test_default_is_mac_with_the_lecture_heuristics(self):
        app = self.app
        self.assertEqual(app.current_config(), SolverConfig.best())
        self.assertTrue(app.valid)

    def test_forward_checking_with_a_fixed_order_shows_backtracking(self):
        app = self.app
        app.propagation_choice.selected = 1  # forward checking
        app.variable_choice.selected = 0     # fixed order
        app.value_choice.selected = 0        # ascending
        app.rebuild()
        self.assertGreater(app.result.stats.backtracks, 0)
        self.assertTrue(app.valid)
        app.go_end()
        app.draw()

    def test_real_main_loop_stops_when_the_window_closes(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)


if __name__ == "__main__":
    unittest.main()
