"""Tests the replay against the solver, and drives the real interface through SDL's dummy driver."""
import os
import sys
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame

from kakuro.csp import KakuroCSP
from kakuro.gui import VisualizerApp
from kakuro.gui.play_screen import digit_combinations
from kakuro.puzzle import EXTRA_BOARD_NAME, load_builtin
from kakuro.solver import (
    PROPAGATE_FC, PROPAGATE_MAC, PROPAGATE_NONE, VAL_ASCENDING, VAL_LCV, VAR_DOM_WDEG, VAR_MRV_DEGREE, VAR_STATIC,
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

    def test_dom_wdeg_option_is_offered_and_solves(self):
        app = self.app
        self.assertEqual(app.variable_choice.value, VAR_DOM_WDEG)
        self.assertTrue(app.valid)

    def test_extra_board_makes_mac_search(self):
        app = self.app
        app.puzzle_choice.selected = app.names.index(EXTRA_BOARD_NAME)
        app.rebuild()
        self.assertEqual(app.propagation_choice.value, PROPAGATE_MAC)
        self.assertGreater(app.result.stats.backtracks, 0)
        self.assertTrue(app.valid)

    def _enter_play_mode(self, board_name=None):
        app = self.app
        app.mode_choice.handle(click(app.mode_choice._cell(1).center))
        self.assertEqual(app.mode, "play")
        if board_name is not None:
            app.play.boards.selected = app.play.boards.options.index((board_name, board_name))
            app.play._board_chosen()
        return app.play

    def test_play_mode_full_game_with_the_keyboard(self):
        play = self._enter_play_mode(EXAMPLE)
        solution = BacktrackingSolver(KakuroCSP(load_builtin(EXAMPLE))).solve().solution
        for cell, digit in enumerate(solution):
            r, c = play.puzzle.cells[cell]
            self.app.handle(click(play.view.cell_rect(r, c).center))
            self.assertEqual(play.selected, cell)
            self.app.handle(pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, f"K_{digit}")))
            self.app.draw()
        self.assertTrue(play.board.is_solved())
        self.assertTrue(play.solved)

    def test_play_mode_backspace_arrows_candidates_and_hint(self):
        play = self._enter_play_mode()
        key = lambda code: self.app.handle(pygame.event.Event(pygame.KEYDOWN, key=code))
        key(pygame.K_RIGHT)
        self.assertEqual(play.selected, 0)
        key(pygame.K_5)
        self.assertEqual(play.board.values[0], 5)
        key(pygame.K_BACKSPACE)
        self.assertEqual(play.board.values[0], 0)
        key(pygame.K_RIGHT)
        self.assertEqual(play.selected, 1)
        play.toggle_candidates()
        self.app.draw()
        play.hint()
        self.assertEqual(play.board.values[1], play.board.solution()[1])
        self.app.draw()
        play.reset()
        self.assertEqual(play.board.filled, 0)

    def test_digits_that_arrive_as_text_are_entered_too(self):
        # With an input method active (Telex, for example) a digit can arrive as text only.
        play = self._enter_play_mode()
        self.app.handle(pygame.event.Event(pygame.TEXTINPUT, text="5"))
        self.assertEqual(play.board.filled, 0)  # no cell selected yet
        self.app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
        self.app.handle(pygame.event.Event(pygame.TEXTINPUT, text="7"))
        self.app.handle(pygame.event.Event(pygame.TEXTINPUT, text="x"))
        self.assertEqual(play.board.values[play.selected], 7)

    def test_digit_pad_opens_beside_a_clicked_cell_and_enters_the_chosen_digit(self):
        play = self._enter_play_mode()
        r, c = play.puzzle.cells[3]
        self.app.handle(click(play.view.cell_rect(r, c).center))
        self.assertTrue(play.picker_open)
        pad = play._picker_cells()
        self.assertEqual([digit for _, digit in pad], list(range(1, 10)) + [0])
        box = play._picker_box()
        self.assertTrue(play.area.contains(box), "the pad must stay inside the board area")
        self.assertFalse(box.colliderect(play.view.cell_rect(r, c)), "the pad must not hide the cell it edits")
        self.app.draw()
        self.app.handle(click(pad[6][0].center))  # the 7
        self.assertEqual(play.board.values[3], 7)
        self.assertFalse(play.picker_open)
        self.app.handle(click(play.view.cell_rect(r, c).center))
        self.app.handle(click(pad[9][0].center))  # the X
        self.assertEqual(play.board.values[3], 0)

    def test_clicking_the_same_cell_twice_closes_the_pad(self):
        play = self._enter_play_mode()
        r, c = play.puzzle.cells[0]
        for expected in (True, False):
            self.app.handle(click(play.view.cell_rect(r, c).center))
            self.assertEqual(play.picker_open, expected)

    def test_clue_under_the_mouse_lists_every_digit_set_for_its_sum(self):
        play = self._enter_play_mode(EXAMPLE)
        view = play.view
        clue_cell = next(cell for cell, clue in play.puzzle.clues.items() if clue.down == 14)
        rect = view.cell_rect(*clue_cell)
        lower_left = (rect.x + rect.width // 4, rect.y + rect.height * 3 // 4)
        self.assertEqual(view.clue_at(lower_left), (*clue_cell, "down"))
        title, lines = play._tip_lines(view.clue_at(lower_left))
        self.assertIn("14", title)
        run = next(r for r in play.csp.runs if r.start == clue_cell and r.direction == "down")
        self.assertEqual(sorted(lines), sorted(" + ".join(map(str, combo))
                                               for combo in digit_combinations(14, len(run.cells))))
        self.assertIn(f"{len(run.cells)} cells", title)
        self.assertEqual(view.clue_at((rect.right - 3, rect.y + 3)), None if play.puzzle.clues[clue_cell].across is None
                         else (*clue_cell, "across"))

    def test_digit_combinations(self):
        self.assertEqual(digit_combinations(3, 2), [(1, 2)])
        self.assertEqual(digit_combinations(45, 9), [tuple(range(1, 10))])
        self.assertEqual(digit_combinations(17, 2), [(8, 9)])
        self.assertEqual(digit_combinations(2, 2), [])

    def test_new_puzzle_gives_a_solvable_random_board_of_the_chosen_size(self):
        play = self._enter_play_mode()
        for index, label in enumerate(("4x4", "5x5", "7x7", "9x9", "10x10", "13x13")):
            play.sizes.selected = -1
            self.app.handle(click(play.sizes._cell(index).center))
            self.assertEqual(play.sizes.selected, index)
            self.assertEqual(play.boards.selected, -1)
            self.assertEqual((play.puzzle.height, play.puzzle.width), (int(label.split("x")[0]),) * 2)
            self.assertIsNotNone(play.board.solution(), label)
            self.app.draw()
        before = play.puzzle
        play.new_puzzle()
        self.assertIsNot(play.puzzle, before)
        self.assertEqual(play.board.filled, 0)

    def test_show_solution_marks_the_board_solved_and_new_puzzle_clears_it(self):
        play = self._enter_play_mode(EXAMPLE)
        play.show_solution()
        self.assertTrue(play.solved)
        self.app.draw()
        play.finish_button.rect.topleft = (300, 650)
        self.app.handle(click(play.finish_button.rect.center))
        self.assertFalse(play.solved)
        self.assertEqual(play.board.filled, 0)

    def test_undo_takes_back_digits_hints_and_clearing(self):
        play = self._enter_play_mode(EXAMPLE)
        key = lambda code, mod=0: self.app.handle(pygame.event.Event(pygame.KEYDOWN, key=code, mod=mod))
        key(pygame.K_RIGHT)
        key(pygame.K_5)
        key(pygame.K_6)
        self.assertEqual(play.board.values[0], 6)
        play.undo()
        self.assertEqual(play.board.values[0], 5)
        play.hint()
        self.assertEqual(play.hints_used, 1)
        filled = play.board.filled
        play.reset()
        self.assertEqual(play.board.filled, 0)
        play.undo()  # clearing the board can be taken back too
        self.assertEqual(play.board.filled, filled)
        while play.history:
            play.undo()
        self.assertEqual(play.board.filled, 0)
        play.undo()  # nothing left: no error
        self.app.handle(click(play.undo_button.rect.center))
        self.app.draw()

    def test_the_clock_runs_until_the_puzzle_is_solved(self):
        play = self._enter_play_mode(EXAMPLE)
        now = [10_000]
        play.clock = lambda: now[0]
        play._restart_clock()
        now[0] += 75_000
        self.assertEqual(play.elapsed_seconds(), 75)
        for cell, digit in enumerate(play.board.solution()):
            play._enter(cell, digit)
        self.assertTrue(play.solved)
        now[0] += 60_000
        self.assertEqual(play.elapsed_seconds(), 75)  # stopped at the solution
        self.app.draw()
        play.show_solution()
        self.assertTrue(play.revealed)
        play.undo()  # the shown solution is not taken back piece by piece
        self.assertTrue(play.solved)
        play.reset()
        self.assertFalse(play.revealed)
        self.assertEqual(play.elapsed_seconds(), 0)

    def test_wrong_digits_show_in_red_and_correct_ones_in_green(self):
        play = self._enter_play_mode(EXAMPLE)
        play.board.set_value(0, 9)
        play.board.set_value(1, 9)  # the same digit twice in a run
        self.assertTrue(play.board.conflicts())
        self.app.draw()

    def test_both_themes_draw_every_screen(self):
        from kakuro.gui.theme import Theme
        try:
            for name in ("dark", "classic"):
                Theme.use(name)
                self.app.mode_choice.selected = 0
                self.app.draw()
                self.app.mode_choice.selected = 1
                self.app.draw()
        finally:
            Theme.use("classic")

    def test_theme_button_and_key_switch_themes(self):
        from kakuro.gui.theme import Theme
        try:
            Theme.use("classic")
            self.app.handle(click(self.app.theme_button.rect.center))
            self.assertEqual(Theme.name, "dark")
            self.app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t))
            self.assertEqual(Theme.name, "classic")
        finally:
            Theme.use("classic")

    def test_board_keeps_its_place_when_returning_to_the_solver_view(self):
        app = self.app
        app.go_end()
        position = app.replay.position
        app.mode_choice.handle(click(app.mode_choice._cell(1).center))
        app.draw()
        app.mode_choice.handle(click(app.mode_choice._cell(0).center))
        self.assertEqual(app.replay.position, position)
        app.draw()

    def test_real_main_loop_stops_when_the_window_closes(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)


if __name__ == "__main__":
    unittest.main()
