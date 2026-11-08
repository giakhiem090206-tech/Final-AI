"""Drives the real interface without a window, through the dummy SDL video driver."""
import os
import sys
import tempfile
import time
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame

from tank_battle.gui import HUMAN, GameScreen, MenuScreen, TankBattleApp
from tank_battle.gui.theme import Theme
from tank_battle.maps import BUILTIN_MAPS
from tank_battle.model import Action
from tank_battle.plugins import AgentCatalog

PLUGINS = os.path.join(os.path.dirname(__file__), "..", "plugins")
FAST = "Heuristic Alpha-Beta"


def key(code):
    return pygame.event.Event(pygame.KEYDOWN, key=code)


class _Pressed:
    """Stands in for pygame.key.get_pressed(), which the dummy video driver cannot fake."""

    def __init__(self, codes):
        self.codes = codes

    def __getitem__(self, code):
        return code in self.codes


def run_until(app, predicate, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        app.screen.update(16)
        app.screen.draw(app.surface)
        time.sleep(0.001)
    return predicate()


class GuiTest(unittest.TestCase):
    def setUp(self):
        self.app = TankBattleApp(AgentCatalog(PLUGINS))

    def tearDown(self):
        pygame.quit()

    def test_menu_lists_plugins_and_draws(self):
        menu = self.app.screen
        self.assertIsInstance(menu, MenuScreen)
        menu.draw(self.app.surface)
        self.assertIn("Example: shoot when aligned", menu.player1.items)
        self.assertIn(HUMAN, menu.player1.items)

    def test_menu_starts_the_chosen_game(self):
        menu = self.app.screen
        menu.player1.selected = menu.player1.items.index(FAST)
        menu.player2.selected = menu.player2.items.index("Random")
        menu.maps.selected = menu.maps.items.index("Duel")
        menu.start()
        self.assertIsInstance(self.app.screen, GameScreen)
        self.assertEqual(self.app.screen.game_map.name, "Duel")
        self.assertEqual(self.app.screen.names, (FAST, "Random"))

    def test_game_between_agents_reaches_the_end(self):
        self.app.start_game(FAST, "Example: shoot when aligned", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        screen.speed = 3
        self.assertTrue(run_until(self.app, lambda: screen.phase == GameScreen.OVER, 60))
        self.assertTrue(screen.session.is_over)
        screen.draw(self.app.surface)

    def test_keyboard_controls_a_human_player(self):
        self.app.start_game(HUMAN, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        self.assertTrue(run_until(self.app, lambda: screen.decisions[1] is not None, 5))
        self.assertEqual(screen.session.state.cycle, 0)  # the game waits for the person
        screen.handle(key(pygame.K_d))
        self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle == 1, 5))
        self.assertEqual(screen.last_decisions[0].action, Action.MOVE_RIGHT)
        self.assertEqual(screen.session.state.tanks[0].facing, int(Action.MOVE_RIGHT))

    def test_a_key_pressed_while_a_cycle_plays_is_kept_for_the_next_turn(self):
        self.app.start_game(HUMAN, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        self.assertTrue(run_until(self.app, lambda: screen.decisions[1] is not None, 5))
        screen.handle(key(pygame.K_SPACE))
        self.assertTrue(run_until(self.app, lambda: screen.phase == GameScreen.ANIMATING, 5))
        screen.handle(key(pygame.K_a))  # pressed during the animation
        self.assertEqual(screen.queued[0], Action.MOVE_LEFT)
        self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle == 2, 5))
        self.assertEqual(screen.last_decisions[0].action, Action.MOVE_LEFT)
        self.assertIsNone(screen.queued[0])

    def test_a_held_key_repeats_its_move(self):
        self.app.start_game(HUMAN, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        held = {pygame.K_d}
        original = pygame.key.get_pressed
        pygame.key.get_pressed = lambda: _Pressed(held)
        try:
            self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle >= 2, 10))
        finally:
            pygame.key.get_pressed = original
        self.assertEqual(screen.last_decisions[0].action, Action.MOVE_RIGHT)

    def test_a_person_sees_which_tank_is_theirs_and_the_result_in_their_words(self):
        self.app.start_game(HUMAN, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        self.assertFalse(screen.show_plan)  # the AI's plan would give it away
        self.assertTrue(run_until(self.app, lambda: screen._waiting_for_human() and screen.decisions[1] is not None, 5))
        self.assertEqual(screen._marker_label(0), "YOU")
        tank = screen.session.state.tanks[0]
        cell = screen.view.cell_rect(tank.x, tank.y)
        screen.clock_ms = 0  # brackets on
        screen.draw(self.app.surface)
        # The tag "YOU" (2 x 17 pixels wide) sits in a black box with 4 pixels of padding, above the tank.
        self.assertEqual(self.app.surface.get_at((cell.centerx - 19, cell.y - 10))[:3], (0, 0, 0))
        self.assertEqual(self.app.surface.get_at((cell.centerx - 21, cell.y - 10))[:3], Theme.PLAYERS[0])
        screen.handle(key(pygame.K_p))
        screen.draw(self.app.surface)  # with the PAUSE banner

    def test_menu_offers_a_game_against_the_ai_by_default(self):
        menu = self.app.screen
        self.assertEqual(menu.player1.value, HUMAN)
        self.assertEqual(menu.player2.value, "Heuristic A-B + optimizations")
        self.assertIn("arrow keys", menu.controls_line())
        self.assertEqual(menu.player1.tag_of("Random"), "easiest")
        self.assertEqual(menu.player1.tag_of("Example: shoot when aligned"), "plugin")

    def test_pause_and_single_step(self):
        self.app.start_game(FAST, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        screen.speed = 3
        screen.handle(key(pygame.K_p))
        for _ in range(30):
            screen.update(16)
        self.assertEqual(screen.session.state.cycle, 0)
        screen.handle(key(pygame.K_n))
        self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle == 1, 5))
        self.assertTrue(run_until(self.app, lambda: screen.phase == GameScreen.THINKING, 5))
        for _ in range(30):
            screen.update(16)
        self.assertEqual(screen.session.state.cycle, 1)

    def test_animation_frames_cover_a_cycle_with_collisions(self):
        self.app.start_game(FAST, FAST, BUILTIN_MAPS["Bunkers"], 0.05)
        screen = self.app.screen
        screen.speed = 0
        self.assertTrue(run_until(self.app, lambda: bool(screen.trace.events), 30))
        for fraction in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            screen.view.draw_animated(self.app.surface, screen.before, screen.session.state, screen.trace, fraction)

    def test_overlays_draw_and_toggle(self):
        self.app.start_game(FAST, "Random", BUILTIN_MAPS["Bunkers"], 0.05)
        screen = self.app.screen
        screen.speed = 3
        self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle >= 2, 10))
        for code in (pygame.K_l, pygame.K_v, pygame.K_h, pygame.K_h, pygame.K_h):
            screen.handle(key(code))
            screen.draw(self.app.surface)
        self.assertIsNone(screen.show_effort)  # off, player 1, player 2, off
        self.assertFalse(screen.show_fire_lines)
        self.assertFalse(screen.show_plan)

    def test_finished_cycles_can_be_browsed(self):
        self.app.start_game(FAST, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        screen.speed = 3
        self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle >= 3, 10))
        screen.handle(key(pygame.K_p))
        self.assertTrue(run_until(self.app, lambda: screen.phase == GameScreen.THINKING and screen.worker is None, 5)
                        or screen.paused)
        latest = len(screen.history) - 1
        screen.handle(key(pygame.K_LEFT))
        self.assertEqual(screen.browsing, latest - 1)
        self.assertIs(screen._shown_state(), screen.history[latest - 1].state)
        screen.draw(self.app.surface)
        screen.handle(key(pygame.K_RIGHT))
        self.assertIsNone(screen.browsing)

    def test_series_counts_wins_for_the_entrant_after_swapping_sides(self):
        self.app.start_game("Example: shoot when aligned", "Random", BUILTIN_MAPS["Duel"], 0.05, games=3)
        screen = self.app.screen
        screen.speed = 3
        self.assertEqual(screen.names[0], "Example: shoot when aligned")
        self.assertTrue(run_until(self.app, lambda: screen.phase == GameScreen.OVER, 60))
        first_result = screen.session.outcome
        screen.handle(key(pygame.K_RETURN))
        self.assertEqual(screen.series.game, 2)
        self.assertEqual(screen.names[1], "Example: shoot when aligned")  # sides are swapped
        self.assertEqual(screen.session.state.cycle, 0)
        self.assertEqual(sum(screen.series.wins) + screen.series.draws, 1)
        if first_result == 0:
            self.assertEqual(screen.series.wins[0], 1)
        self.assertTrue(run_until(self.app, lambda: screen.phase == GameScreen.OVER, 60))
        if screen.session.outcome == 1:  # the same entrant, now in the second seat
            self.assertGreaterEqual(screen.series.wins[0], 1)

    def test_a_dropped_python_file_becomes_a_player(self):
        menu = self.app.screen
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "group7.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("AGENT_NAME = 'Group 7'\ndef choose_action(o):\n    return 'FIRE'\n")
            menu.handle(pygame.event.Event(pygame.DROPFILE, file=path))
        self.assertIn("Group 7", menu.player1.items)
        self.assertIn("Group 7", menu.player2.items)
        self.assertTrue(menu.message_ok)

    def test_a_dropped_broken_file_is_reported(self):
        menu = self.app.screen
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "broken.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("def nope(:\n")
            menu.handle(pygame.event.Event(pygame.DROPFILE, file=path))
        self.assertFalse(menu.message_ok)
        menu.handle(pygame.event.Event(pygame.DROPFILE, file="notes.txt"))
        self.assertFalse(menu.message_ok)
        menu.draw(self.app.surface)

    def test_map_picker_fits_inside_its_panel(self):
        picker = self.app.screen.maps
        for index in range(len(picker.items)):
            self.assertTrue(picker.rect.contains(picker._cell(index)), picker.items[index])

    def test_real_main_loop_stops_when_the_window_closes(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)

    def test_restart_and_return_to_menu(self):
        self.app.start_game(FAST, "Random", BUILTIN_MAPS["Duel"], 0.05)
        screen = self.app.screen
        screen.speed = 3
        self.assertTrue(run_until(self.app, lambda: screen.session.state.cycle >= 2, 10))
        self.assertTrue(run_until(self.app, lambda: screen.worker is None, 5))
        screen.handle(key(pygame.K_r))
        self.assertEqual(screen.session.state.cycle, 0)
        screen.handle(key(pygame.K_ESCAPE))
        self.assertIsInstance(self.app.screen, MenuScreen)


if __name__ == "__main__":
    unittest.main()


class RetroLookTest(unittest.TestCase):
    """The arcade look: pixel sprites at whole-number scales, a pixel font and explosions made of frames."""

    def setUp(self):
        pygame.init()
        pygame.display.set_mode((64, 64))

    def tearDown(self):
        pygame.quit()

    def test_pixel_text_has_the_size_of_its_glyphs(self):
        from tank_battle.gui.retro import pixel_text, pixel_text_size
        self.assertEqual(pixel_text_size("AB", 3), ((5 + 1 + 5) * 3, 7 * 3))
        self.assertEqual(pixel_text("AB", 3, (255, 255, 255)).get_size(), pixel_text_size("AB", 3))
        self.assertEqual(pixel_text_size("", 4)[0], 0)

    def test_every_letter_and_digit_has_a_glyph_with_ink(self):
        from tank_battle.gui.retro import _GLYPHS
        for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            rows = _GLYPHS[character].split()
            self.assertEqual(len(rows), 7, character)
            self.assertTrue(all(len(row) == 5 for row in rows), character)
            self.assertIn("1", "".join(rows), character)

    def test_sprites_are_whole_number_multiples_of_the_sprite_grid(self):
        from tank_battle.gui.retro import SPRITE_SIZE, Sprites
        sprites = Sprites(3)
        self.assertEqual(sprites.size, SPRITE_SIZE * 3)
        for image in (sprites.tank(0, 0), sprites.tank(1, 90, 1), sprites.eagle(0), sprites.eagle(1, False),
                      sprites.bricks(3), sprites.bricks(2), sprites.bricks(1), sprites.bullet(0, 180)):
            self.assertEqual(image.get_size(), (sprites.size, sprites.size))
        self.assertEqual(sprites.blast(0, big=True).get_size(), (sprites.size * 2, sprites.size * 2))

    def test_tank_frames_differ_only_in_the_treads_and_both_players_differ(self):
        from tank_battle.gui.retro import Sprites
        sprites = Sprites(1)
        first, second = sprites.tank(0, 0, 0), sprites.tank(0, 0, 1)
        self.assertNotEqual(pygame.image.tostring(first, "RGBA"), pygame.image.tostring(second, "RGBA"))
        self.assertEqual(first.get_at((8, 8)), second.get_at((8, 8)))  # the turret is the same
        self.assertNotEqual(sprites.tank(0, 0).get_at((5, 8)), sprites.tank(1, 0).get_at((5, 8)))

    def test_a_turned_tank_faces_the_way_it_is_rotated(self):
        from tank_battle.gui.retro import Sprites
        sprites = Sprites(1)
        up, right = sprites.tank(0, 0), sprites.tank(0, -90)
        self.assertEqual(up.get_at((7, 0)).a, 255)      # the barrel tip is at the top
        self.assertEqual(right.get_at((15, 7)).a, 255)  # ... and at the right after a quarter turn clockwise

    def test_damaged_walls_show_fewer_bricks(self):
        from tank_battle.gui.retro import Sprites
        sprites = Sprites(1)
        solid = [sum(1 for y in range(16) for x in range(16) if sprites.bricks(hp).get_at((x, y)).a)
                 for hp in (3, 2, 1)]
        self.assertGreater(solid[0], solid[1])
        self.assertGreater(solid[1], solid[2])
        self.assertGreater(solid[2], 0)

    def test_a_destroyed_base_is_drawn_as_rubble_not_an_eagle(self):
        from tank_battle.gui.retro import Sprites
        sprites = Sprites(1)
        self.assertNotEqual(pygame.image.tostring(sprites.eagle(0, True), "RGBA"),
                            pygame.image.tostring(sprites.eagle(0, False), "RGBA"))

    def test_brick_title_is_made_of_the_letters_and_nothing_else(self):
        from tank_battle.gui.retro import brick_title, pixel_text_size
        title = brick_title("TANK", 4)
        width, height = pixel_text_size("TANK", 4)
        self.assertEqual(title.get_size(), (width + 4, height + 4))
        self.assertEqual(title.get_at((21, 0)).a, 0)   # in the gap between T and A, above any shadow
        self.assertEqual(title.get_at((2, 0)).a, 255)  # on the bar of the T

    def test_tiles_use_whole_number_scales_and_the_frame_has_room_on_every_map(self):
        from tank_battle.gui.board_view import BoardView
        from tank_battle.gui.constants import BOARD_PIXELS, TOP_BAR
        for name, game_map in BUILTIN_MAPS.items():
            view = BoardView((0, TOP_BAR), game_map.width, game_map.height)
            self.assertEqual(view.cell % 16, 0, name)
            self.assertTrue(view.arena.contains(view.field), name)
            self.assertGreaterEqual(view.field.x - view.arena.x, 8, f"{name}: room for the grey frame")
            self.assertLessEqual(view.cell * max(game_map.width, game_map.height), BOARD_PIXELS, name)

    def test_explosions_play_their_frames_and_then_disappear(self):
        from tank_battle.gui.board_view import Effects
        from tank_battle.gui.retro import Sprites
        effects = Effects(Sprites(3))
        screen = pygame.Surface((300, 300))
        effects.blast((150, 150), big=False)
        effects.blast((100, 100), big=True)
        for _ in range(12):
            effects.draw(screen)
            effects.update(0.05)
        self.assertEqual(effects._blasts, [])
        effects.burst((50, 50), (255, 255, 255), 3, 100)  # a spark: no explosion for tiny counts
        self.assertEqual(effects._blasts, [])

    def test_both_players_have_clearly_different_colours(self):
        from tank_battle.gui.theme import Theme
        a, b = Theme.PLAYERS
        self.assertGreater(sum(abs(x - y) for x, y in zip(a, b)), 200)
