"""Run from the `Task 2` folder with: python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tank_battle.maps import BUILTIN_MAPS, GameMap, is_point_symmetric
from tank_battle.model import (
    BASE_HP, DRAW, TANK_HP, WALL_HP, Action, Bullet, Direction, GameState,
)
from tank_battle.rules import TARGET_BASE, TARGET_TANK, TARGET_WALL, GameRules, StepTrace

STAY, FIRE = Action.STAY, Action.FIRE


def make_state(rows, **changes):
    return GameMap("test", tuple(rows)).create_state().replace(**changes)


def with_tank(state, player, **fields):
    tanks = list(state.tanks)
    tanks[player] = tanks[player]._replace(**fields)
    return state.replace(tanks=tuple(tanks))


LANE = (
    "b.........",
    "..........",
    "A.........",
    "..........",
    "B.......a.",
)


class BulletTest(unittest.TestCase):
    def fired_state(self):
        """Player 1 at (0,2) faces right along an empty row."""
        return with_tank(make_state(LANE), 0, facing=int(Direction.RIGHT))

    def test_bullet_travels_three_cells_in_the_cycle_it_is_fired(self):
        state = GameRules.step(self.fired_state(), FIRE, STAY)
        self.assertEqual(state.bullets, (Bullet(0, 3, 2, int(Direction.RIGHT)),))

    def test_bullet_keeps_travelling_three_cells_per_cycle(self):
        state = GameRules.step(self.fired_state(), FIRE, STAY)
        state = GameRules.step(state, STAY, STAY)
        self.assertEqual(state.bullets, (Bullet(0, 6, 2, int(Direction.RIGHT)),))

    def test_trace_shows_every_cell_of_the_flight(self):
        trace = StepTrace()
        GameRules.step(self.fired_state(), FIRE, STAY, trace)
        self.assertEqual([(f[0].x, f[0].y) for f in trace.frames], [(1, 2), (2, 2), (3, 2)])

    def test_bullet_stops_at_first_wall_and_damages_only_it(self):
        rows = (
            "b.........",
            "..........",
            "A.#.#.....",
            "..........",
            "B.......a.",
        )
        start = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        trace = StepTrace()
        state = GameRules.step(start, FIRE, STAY, trace)
        self.assertEqual(state.bullets, ())
        self.assertEqual(state.walls[2 * 10 + 2], WALL_HP - 1)
        self.assertEqual(state.walls[2 * 10 + 4], WALL_HP)
        self.assertEqual(len(trace.frames), 2)  # hit on the second cell, not moved further
        self.assertEqual(trace.events[0].target, TARGET_WALL)
        self.assertEqual(trace.events[0].substep, 2)

    def test_collision_is_checked_on_each_cell_not_only_the_last(self):
        """A target 1 cell ahead must be hit, although the bullet could move 3 cells."""
        rows = (
            "b.........",
            "..........",
            "AB........",
            "..........",
            "........a.",
        )
        start = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        state = GameRules.step(start, FIRE, STAY)
        self.assertEqual(state.tanks[1].hp, TANK_HP - 1)
        self.assertEqual(state.bullets, ())

    def test_wall_is_destroyed_after_three_hits_then_lets_bullets_through(self):
        rows = (
            "b.........",
            "..........",
            "A.#.......",
            "..........",
            "B.......a.",
        )
        state = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        index = 2 * 10 + 2
        for expected in (2, 1):
            state = GameRules.step(state, FIRE, STAY)
            self.assertEqual(state.walls[index], expected)
        state = GameRules.step(state, FIRE, STAY)
        self.assertNotIn(index, state.walls)
        state = GameRules.step(state, FIRE, STAY)
        self.assertEqual(state.bullets, (Bullet(0, 3, 2, int(Direction.RIGHT)),))

    def test_damaging_a_wall_does_not_change_the_previous_state(self):
        rows = ("b.........", "..........", "A.#.......", "..........", "B.......a.")
        before = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        GameRules.step(before, FIRE, STAY)
        self.assertEqual(before.walls[2 * 10 + 2], WALL_HP)

    def test_walls_key_matches_full_recomputation(self):
        rows = ("b.........", "..........", "A.#.......", "..........", "B.......a.")
        state = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        for _ in range(4):
            state = GameRules.step(state, FIRE, STAY)
            self.assertEqual(state.walls_key, GameState.hash_walls(state.walls))

    def test_bullet_leaving_the_board_disappears(self):
        rows = ("b.........", "..........", ".........A", "..........", "B.......a.")
        start = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        self.assertEqual(GameRules.step(start, FIRE, STAY).bullets, ())

    def test_bullet_damages_a_base(self):
        rows = ("A.b.......", "..........", "..........", "..........", "B.......a.")
        start = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        trace = StepTrace()
        state = GameRules.step(start, FIRE, STAY, trace)
        self.assertEqual(state.bases[1].hp, BASE_HP - 1)
        self.assertEqual(trace.events[0].target, TARGET_BASE)
        self.assertEqual(trace.events[0].target_owner, 1)

    def test_friendly_fire_counts(self):
        """The statement says a bullet hits any tank or base it meets, without exception."""
        rows = ("b.........", "..........", "A.a.......", "..........", "B.........")
        start = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        self.assertEqual(GameRules.step(start, FIRE, STAY).bases[0].hp, BASE_HP - 1)

    def test_bullets_pass_through_each_other(self):
        rows = ("b.........", "..........", "A..B......", "..........", "........a.")
        start = with_tank(with_tank(make_state(rows), 0, facing=int(Direction.RIGHT)),
                          1, facing=int(Direction.LEFT))
        state = GameRules.step(start, FIRE, FIRE)
        self.assertEqual((state.tanks[0].hp, state.tanks[1].hp), (TANK_HP - 1, TANK_HP - 1))

    def test_tank_driving_onto_a_bullet_is_hit(self):
        rows = ("b.........", "..........", "..........", "A.........", "B.......a.")
        start = make_state(rows, bullets=(Bullet(1, 1, 3, int(Direction.UP)),))
        trace = StepTrace()
        state = GameRules.step(start, Action.MOVE_RIGHT, STAY, trace)
        self.assertEqual(state.tanks[0].hp, TANK_HP - 1)
        self.assertEqual(state.bullets, ())
        self.assertEqual(trace.events[0].target, TARGET_TANK)

    def test_tank_can_dodge_by_moving_out_of_line(self):
        rows = ("b.........", "..........", "A.........", "..........", "B.......a.")
        start = make_state(rows, bullets=(Bullet(1, 3, 2, int(Direction.LEFT)),))
        state = GameRules.step(start, Action.MOVE_UP, STAY)
        self.assertEqual(state.tanks[0].hp, TANK_HP)


class MovementTest(unittest.TestCase):
    def test_each_move_goes_one_cell_and_turns(self):
        rows = ("b.........", "..........", "..A.......", "..........", "B.......a.")
        expected = {
            Action.MOVE_UP: (2, 1), Action.MOVE_DOWN: (2, 3),
            Action.MOVE_LEFT: (1, 2), Action.MOVE_RIGHT: (3, 2),
        }
        for action, cell in expected.items():
            tank = GameRules.step(make_state(rows), action, STAY).tanks[0]
            self.assertEqual((tank.x, tank.y), cell)
            self.assertEqual(tank.facing, int(action))

    def test_fire_and_stay_do_not_move(self):
        rows = ("b.........", "..........", "..A.......", "..........", "B.......a.")
        for action in (FIRE, STAY):
            tank = GameRules.step(make_state(rows), action, STAY).tanks[0]
            self.assertEqual((tank.x, tank.y), (2, 2))

    def test_blocked_move_turns_without_moving(self):
        for rows in (
            ("b.........", "..........", "A#........", "..........", "B.......a."),  # wall
            ("b.........", "..........", "Aa........", "..........", "B........."),  # base
            ("b.........", "..........", "AB........", "..........", "........a."),  # tank
        ):
            tank = GameRules.step(make_state(rows), Action.MOVE_RIGHT, STAY).tanks[0]
            self.assertEqual((tank.x, tank.y, tank.facing), (0, 2, int(Direction.RIGHT)))

    def test_tank_cannot_leave_the_board(self):
        rows = ("b.........", "..........", "A.........", "..........", "B.......a.")
        tank = GameRules.step(make_state(rows), Action.MOVE_LEFT, STAY).tanks[0]
        self.assertEqual((tank.x, tank.y), (0, 2))

    def test_contested_cell_goes_to_nobody(self):
        rows = ("b.........", "..........", "A.B.......", "..........", "........a.")
        state = GameRules.step(make_state(rows), Action.MOVE_RIGHT, Action.MOVE_LEFT)
        self.assertEqual((state.tanks[0].x, state.tanks[1].x), (0, 2))

    def test_tanks_cannot_swap_cells(self):
        rows = ("b.........", "..........", "AB........", "..........", "........a.")
        state = GameRules.step(make_state(rows), Action.MOVE_RIGHT, Action.MOVE_LEFT)
        self.assertEqual((state.tanks[0].x, state.tanks[1].x), (0, 1))

    def test_effective_actions_drop_only_moves_equal_to_stay(self):
        rows = ("b.........", "..........", "A#........", "..........", "B.......a.")
        state = with_tank(make_state(rows), 0, facing=int(Direction.RIGHT))
        actions = GameRules.effective_actions(state, 0)
        self.assertNotIn(Action.MOVE_RIGHT, actions)
        self.assertIn(Action.MOVE_LEFT, actions)  # blocked by the edge, but it would still turn
        self.assertIn(FIRE, actions)
        self.assertIn(STAY, actions)
        for action in Action:
            if action not in actions:
                moved = GameRules.step(state, action, STAY).key()
                self.assertEqual(moved, GameRules.step(state, STAY, STAY).key())


class TerminalTest(unittest.TestCase):
    BASE = ("b.........", "..........", "A.........", "..........", "B.......a.")

    def test_game_goes_on_when_everything_is_alive(self):
        self.assertIsNone(GameRules.outcome(make_state(self.BASE)))

    def test_destroying_a_tank_wins(self):
        state = with_tank(make_state(self.BASE), 1, hp=0)
        self.assertEqual(GameRules.outcome(state), 0)

    def test_destroying_a_base_wins(self):
        state = make_state(self.BASE)
        state = state.replace(bases=(state.bases[0]._replace(hp=0), state.bases[1]))
        self.assertEqual(GameRules.outcome(state), 1)

    def test_each_losing_one_asset_is_a_draw(self):
        state = with_tank(make_state(self.BASE), 0, hp=0)
        state = state.replace(bases=(state.bases[0], state.bases[1]._replace(hp=0)))
        self.assertEqual(GameRules.outcome(state), DRAW)

    def test_cycle_limit_is_a_draw(self):
        self.assertEqual(GameRules.outcome(make_state(self.BASE, cycle=300, max_cycles=300)), DRAW)

    def test_utility_is_zero_sum(self):
        state = with_tank(make_state(self.BASE), 1, hp=0)
        self.assertEqual(GameRules.utility(state, 0), 1)
        self.assertEqual(GameRules.utility(state, 1), -1)
        with self.assertRaises(ValueError):
            GameRules.utility(make_state(self.BASE), 0)

    def test_killing_shot_ends_the_flight_of_later_bullets(self):
        """Player 2's tank dies in sub-step 1; a bullet needing 2 more cells must not land."""
        rows = ("b.........", "..........", "AB........", "..........", "........a.")
        start = with_tank(with_tank(make_state(rows), 0, facing=int(Direction.RIGHT)), 1, hp=1)
        start = start.replace(bullets=(Bullet(1, 3, 4, int(Direction.RIGHT)),
                                       Bullet(1, 5, 4, int(Direction.RIGHT))))
        state = GameRules.step(start, FIRE, STAY)
        self.assertEqual(GameRules.outcome(state), 0)
        self.assertEqual(state.bases[0].hp, BASE_HP)


class ActionParseTest(unittest.TestCase):
    def test_accepts_enum_name_and_number(self):
        self.assertEqual(Action.parse(Action.FIRE), FIRE)
        self.assertEqual(Action.parse("fire"), FIRE)
        self.assertEqual(Action.parse(4), FIRE)

    def test_rejects_anything_else(self):
        for bad in ("SHOOT", 6, -1, None, 1.5, True):
            self.assertIsNone(Action.parse(bad))


class MapTest(unittest.TestCase):
    def test_every_builtin_map_is_fair_and_loads(self):
        for name, game_map in BUILTIN_MAPS.items():
            self.assertTrue(is_point_symmetric(game_map.rows), name)
            state = game_map.create_state()
            self.assertEqual(len(state.tanks), 2)
            self.assertEqual((state.tanks[0].hp, state.bases[0].hp), (TANK_HP, BASE_HP))
            self.assertTrue(all(hp == WALL_HP for hp in state.walls.values()))

    def test_rejects_malformed_maps(self):
        with self.assertRaises(ValueError):
            GameMap("two tanks", ("AAb", "B.a")).create_state()
        with self.assertRaises(ValueError):
            GameMap("uneven", ("Ab", "B.a")).create_state()
        with self.assertRaises(ValueError):
            GameMap("unknown", ("A?b", "B.a")).create_state()


if __name__ == "__main__":
    unittest.main()
