import os
import random
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tank_battle.agents import Agent, RandomAgent, SearchAgent
from tank_battle.evaluation import (
    FiringEffortMap, HeuristicEvaluator, RaceEvaluator, RaceWeights, direction_towards,
)
from tank_battle.experiments import SPARRING_PARTNERS, OpeningBook
from tank_battle.maps import BUILTIN_MAPS, GameMap, is_point_symmetric, random_map
from tank_battle.model import DELTAS, DRAW, Action, Bullet, Direction
from tank_battle.plugins import PluginLoader
from tank_battle.rules import GameRules
from tank_battle.search import WIN_SCORE, AdversarialSearch, SearchConfig
from tank_battle.session import (
    STATUS_ERROR, STATUS_INVALID, STATUS_OK, STATUS_TIMEOUT, HeadlessMatch, SafeAgentRunner,
)

OPEN = ("b.........", "..........", "..........", "A.........", "B.......a.")


def random_midgame(game_map: GameMap, seed: int, cycles: int = 12):
    """A position reached by random play, with bullets and damage on the board."""
    rng = random.Random(seed)
    state = game_map.create_state()
    for _ in range(cycles):
        following = GameRules.step(state, rng.choice(list(Action)), rng.choice(list(Action)))
        if GameRules.outcome(following) is not None:
            break
        state = following
    return state


class EvaluatorTest(unittest.TestCase):
    def test_is_zero_sum_on_many_positions(self):
        evaluator = HeuristicEvaluator()
        for game_map in BUILTIN_MAPS.values():
            for seed in range(25):
                state = random_midgame(game_map, seed)
                self.assertAlmostEqual(evaluator.evaluate(state, 0), -evaluator.evaluate(state, 1))

    def test_initial_position_of_a_fair_map_is_even(self):
        evaluator = HeuristicEvaluator()
        for game_map in BUILTIN_MAPS.values():
            self.assertAlmostEqual(evaluator.evaluate(game_map.create_state(), 0), 0.0, msg=game_map.name)

    def test_stays_far_below_the_win_score(self):
        evaluator = HeuristicEvaluator()
        for seed in range(25):
            self.assertLess(abs(evaluator.evaluate(random_midgame(BUILTIN_MAPS["Fortress"], seed), 0)), WIN_SCORE / 10)

    def test_more_health_is_better(self):
        state = BUILTIN_MAPS["Duel"].create_state()
        hurt = state.replace(tanks=(state.tanks[0]._replace(hp=3), state.tanks[1]))
        evaluator = HeuristicEvaluator()
        self.assertLess(evaluator.evaluate(hurt, 0), evaluator.evaluate(state, 0))


class FiringEffortTest(unittest.TestCase):
    def effort_at(self, rows, x, y):
        state = GameMap("t", rows).create_state()
        target = state.bases[1]
        return FiringEffortMap().effort(state, target.x, target.y)[y * state.width + x]

    def test_a_cell_in_clear_line_needs_no_effort_at_any_distance(self):
        rows = ("b........A", "..........", "..........", "B.......a.")
        self.assertEqual(self.effort_at(rows, 9, 0), 0)

    def test_a_wall_in_the_line_costs_its_hit_points_in_shots(self):
        rows = ("b...#....A", "..........", "..........", "B.......a.")
        self.assertEqual(self.effort_at(rows, 9, 0), 3)

    def test_shooting_through_is_preferred_when_cheaper_than_walking(self):
        rows = ("b.#.#.#..A", "..........", "..........", "B.......a.")
        # Three walls in line take 9 shots; walking to the base's column takes 10 moves.
        self.assertEqual(self.effort_at(rows, 9, 0), 9)

    def test_walking_to_a_clear_line_is_preferred_when_cheaper(self):
        rows = ("b.#.#.#.#A", "..........", "..........", "B.......a.")
        # Four walls in line would take 12 shots; walking still takes 10 moves.
        self.assertEqual(self.effort_at(rows, 9, 0), 10)

    def test_own_base_blocks_the_line(self):
        rows = ("b...a....A", "..........", "..........", "B.........")
        self.assertGreater(self.effort_at(rows, 9, 0), 0)

    def test_agrees_with_a_slow_exact_computation_on_random_maps(self):
        """Each cell's effort must equal the best of: shots from here, or a step then its effort."""
        for seed in range(6):
            state = random_map(seed).create_state()
            target = state.bases[1]
            costs = FiringEffortMap().effort(state, target.x, target.y)
            blocked = {(b.x, b.y) for b in state.bases}
            for y in range(state.height):
                for x in range(state.width):
                    if (x, y) in blocked or y * state.width + x in state.walls:
                        continue
                    options = []
                    direction = direction_towards(x, y, target.x, target.y)
                    if direction is not None:
                        dx, dy = DELTAS[direction]
                        cx, cy, shots, stopped = x + dx, y + dy, 0, False
                        while (cx, cy) != (target.x, target.y):
                            if (cx, cy) in blocked:
                                stopped = True
                                break
                            shots += state.walls.get(cy * state.width + cx, 0)
                            cx, cy = cx + dx, cy + dy
                        if not stopped:
                            options.append(shots)
                    for dx, dy in DELTAS:
                        nx, ny = x + dx, y + dy
                        if state.in_bounds(nx, ny) and (nx, ny) not in blocked:
                            options.append(1 + state.walls.get(ny * state.width + nx, 0) + costs[ny * state.width + nx])
                    self.assertEqual(costs[y * state.width + x], min(options), f"seed {seed} cell {(x, y)}")


class RaceEvaluatorTest(unittest.TestCase):
    NEUTRAL = RaceWeights(aggression=0.0)

    def test_is_zero_sum_without_the_aggression_term(self):
        evaluator = RaceEvaluator(self.NEUTRAL)
        for game_map in BUILTIN_MAPS.values():
            for seed in range(25):
                state = random_midgame(game_map, seed)
                self.assertAlmostEqual(evaluator.evaluate(state, 0), -evaluator.evaluate(state, 1))

    def test_aggression_rewards_only_the_searching_side(self):
        state = random_midgame(BUILTIN_MAPS["Duel"], 3)
        neutral = RaceEvaluator(self.NEUTRAL).evaluate(state, 0)
        self.assertLess(RaceEvaluator(RaceWeights(aggression=2.0)).evaluate(state, 0), neutral)

    def test_initial_position_of_a_fair_map_is_even(self):
        evaluator = RaceEvaluator(self.NEUTRAL)
        for game_map in list(BUILTIN_MAPS.values()) + [random_map(s) for s in range(10)]:
            self.assertAlmostEqual(evaluator.evaluate(game_map.create_state(), 0), 0.0, msg=game_map.name)

    def test_being_nearer_to_finishing_is_better(self):
        evaluator = RaceEvaluator(self.NEUTRAL)
        rows = ("b...#....A", "..........", "..........", "B.......a.")
        state = GameMap("t", rows).create_state()
        weakened = state.replace(bases=(state.bases[0], state.bases[1]._replace(hp=2)))
        self.assertGreater(evaluator.evaluate(weakened, 0), evaluator.evaluate(state, 0))

    def test_a_long_shot_at_a_shielding_wall_is_credited_before_it_lands(self):
        """The bug behind tanks that stood still: such a bullet lands beyond the search horizon."""
        evaluator = RaceEvaluator(self.NEUTRAL)
        rows = ("b...#....A", "..........", "..........", "B.......a.")
        state = GameMap("t", rows).create_state()
        state = state.replace(tanks=(state.tanks[0]._replace(facing=int(Direction.LEFT)), state.tanks[1]))
        flying = state.replace(bullets=(Bullet(0, 8, 0, int(Direction.LEFT)),))
        self.assertGreater(evaluator.evaluate(flying, 0), evaluator.evaluate(state, 0))

    def test_a_shot_at_an_unrelated_wall_earns_nothing(self):
        evaluator = RaceEvaluator(self.NEUTRAL)
        rows = ("b...#....A", "..........", "....#.....", "B.......a.")
        state = GameMap("t", rows).create_state()
        wasted = state.replace(bullets=(Bullet(0, 7, 2, int(Direction.LEFT)),))
        self.assertAlmostEqual(evaluator.evaluate(wasted, 0), evaluator.evaluate(state, 0))


class RandomMapTest(unittest.TestCase):
    def test_random_maps_are_fair_and_reproducible(self):
        for seed in range(60):
            game_map = random_map(seed)
            self.assertTrue(is_point_symmetric(game_map.rows), game_map.name)
            game_map.create_state()
            self.assertEqual(game_map.rows, random_map(seed).rows)

    def test_seeds_give_different_maps(self):
        self.assertGreater(len({random_map(seed).rows for seed in range(30)}), 25)


class GoingInCirclesTest(unittest.TestCase):
    def test_a_position_recorded_as_visited_loses_value(self):
        state = BUILTIN_MAPS["Bunkers"].create_state()
        config = SearchConfig.optimized()
        fresh = AdversarialSearch(config).search(state, 0, 2)
        search = AdversarialSearch(config)
        for action in Action:
            # Every position reachable in one cycle with the enemy standing still counts as seen.
            search.record_position(GameRules.step(state, action, Action.STAY), 0)
        self.assertLessEqual(search.search(state, 0, 2).value, fresh.value)

    def test_pruning_stays_correct_with_penalties(self):
        """The penalty moves the search window; alpha-beta must still agree with plain minimax."""
        for seed in range(6):
            state = random_midgame(BUILTIN_MAPS["Bunkers"], seed)
            plain = AdversarialSearch(SearchConfig("plain", heuristic=True, repetition_penalty=7.5))
            pruned = AdversarialSearch(SearchConfig("pruned", heuristic=True, alpha_beta=True, repetition_penalty=7.5))
            rng = random.Random(seed)
            for _ in range(8):
                position = GameRules.step(state, rng.choice(list(Action)), rng.choice(list(Action)))
                plain.record_position(position, 0)
                pruned.record_position(position, 0)
            a, b = plain.search(state, 0, 2), pruned.search(state, 0, 2)
            self.assertAlmostEqual(a.value, b.value)
            self.assertEqual(a.action, b.action)

    def test_tanks_no_longer_stall_from_the_openings_that_stalled_before(self):
        openings = OpeningBook.generate(10, 1, ["Crossroads", "Corridors"])
        for state in openings:
            agents = (SearchAgent(SearchConfig.optimized(), depth=2), SearchAgent(SearchConfig.optimized(), depth=2))
            result = HeadlessMatch(state, agents).play()
            self.assertLess(result.cycles, state.max_cycles)


class PrincipalVariationTest(unittest.TestCase):
    def test_plan_is_a_path_of_single_steps_from_the_tank(self):
        for seed in range(6):
            state = random_midgame(BUILTIN_MAPS["Fortress"], seed)
            search = AdversarialSearch(SearchConfig.optimized())
            result = search.search(state, 0, 3)
            previous = (state.tanks[0].x, state.tanks[0].y)
            plan = search.principal_variation(state, 0, result.action)
            self.assertGreater(len(plan), 0)
            for cell in plan:
                self.assertLessEqual(abs(cell[0] - previous[0]) + abs(cell[1] - previous[1]), 1)
                previous = cell

    def test_agent_reports_its_plan(self):
        agent = SearchAgent(SearchConfig.optimized(), depth=2)
        agent.choose_action(BUILTIN_MAPS["Duel"].create_state(), 0)
        self.assertIn("plan", agent.last_info)

    def test_configurations_without_memory_report_no_plan(self):
        agent = SearchAgent(SearchConfig.heuristic_alpha_beta(), depth=1)
        agent.choose_action(BUILTIN_MAPS["Duel"].create_state(), 0)
        self.assertNotIn("plan", agent.last_info)


class SparringPartnerTest(unittest.TestCase):
    def test_all_play_legal_games_to_the_end(self):
        for recipe in SPARRING_PARTNERS:
            for game_map in (BUILTIN_MAPS["Duel"], random_map(3)):
                result = HeadlessMatch(game_map.create_state(100), (recipe.build(), RandomAgent(seed=1))).play()
                self.assertEqual(result.records[0].faults, 0, recipe.label)


class SearchCorrectnessTest(unittest.TestCase):
    def test_node_count_of_full_minimax_matches_the_formula(self):
        """No terminal in reach: one cycle adds 6 MIN nodes and 36 MAX nodes per MAX node."""
        state = GameMap("open", OPEN).create_state()
        expected = {1: 1 + 6 + 36, 2: 1 + 6 + 36 + 36 * (6 + 36)}
        for depth, nodes in expected.items():
            result = AdversarialSearch(SearchConfig.minimax()).search(state, 0, depth)
            self.assertEqual(result.stats.nodes, nodes)
            self.assertEqual(result.stats.expansions, sum(36 ** i for i in range(1, depth + 1)))

    def test_pruning_never_changes_value_or_action(self):
        """The defining property of alpha-beta, on varied positions, for both players."""
        positions = [random_midgame(m, s) for m in BUILTIN_MAPS.values() for s in range(4)]
        pairs = (
            (SearchConfig.minimax(), SearchConfig.alpha_beta_search()),
            (SearchConfig.heuristic_minimax(), SearchConfig.heuristic_alpha_beta()),
        )
        for plain, pruned in pairs:
            for state in positions:
                for player in (0, 1):
                    a = AdversarialSearch(plain).search(state, player, 2)
                    b = AdversarialSearch(pruned).search(state, player, 2)
                    self.assertEqual(a.value, b.value)
                    self.assertEqual(a.action, b.action)
                    self.assertLessEqual(b.stats.nodes, a.stats.nodes)

    def test_optimizations_keep_the_heuristic_alpha_beta_value(self):
        positions = [random_midgame(m, s) for m in BUILTIN_MAPS.values() for s in range(4)]
        for state in positions:
            for player in (0, 1):
                reference = AdversarialSearch(SearchConfig.heuristic_alpha_beta()).search(state, player, 2)
                optimized = AdversarialSearch(SearchConfig.optimized()).search(state, player, 2)
                self.assertEqual(reference.value, optimized.value)

    def test_transposition_table_stays_correct_between_decisions(self):
        """Re-using one table along a game must give the values a fresh search gives."""
        state = BUILTIN_MAPS["Bunkers"].create_state()
        shared = AdversarialSearch(SearchConfig.optimized())
        rng = random.Random(4)
        for _ in range(10):
            fresh = AdversarialSearch(SearchConfig.heuristic_alpha_beta()).search(state, 0, 2)
            self.assertEqual(shared.search(state, 0, 2).value, fresh.value)
            state = GameRules.step(state, rng.choice(list(Action)), rng.choice(list(Action)))
            if GameRules.outcome(state) is not None:
                break

    @staticmethod
    def one_shot_from_winning():
        """Player 1 aims at an enemy base with 1 HP. A base cannot dodge, so the win is forced.

        A tank, by contrast, is never a forced kill while it can step aside: tanks move
        before bullets, and in the tree MIN answers knowing that MAX fired.
        """
        rows = ("..........", "..........", "A..b......", "..........", "B.......a.")
        state = GameMap("t", rows).create_state()
        return state.replace(tanks=(state.tanks[0]._replace(facing=int(Direction.RIGHT)), state.tanks[1]),
                             bases=(state.bases[0], state.bases[1]._replace(hp=1)))

    def test_takes_the_winning_shot(self):
        state = self.one_shot_from_winning()
        for config in SearchConfig.required_four() + [SearchConfig.optimized()]:
            result = AdversarialSearch(config).search(state, 0, 1)
            self.assertEqual(result.action, Action.FIRE, config.name)
            self.assertGreaterEqual(result.value, WIN_SCORE)

    def test_search_sees_that_a_free_tank_can_dodge(self):
        rows = ("b.........", "..........", "A..B......", "..........", "........a.")
        state = GameMap("t", rows).create_state()
        state = state.replace(tanks=(state.tanks[0]._replace(facing=int(Direction.RIGHT)),
                                     state.tanks[1]._replace(hp=1)))
        self.assertLess(AdversarialSearch(SearchConfig.minimax()).search(state, 0, 1).value, WIN_SCORE)

    def test_search_sees_a_kill_on_a_tank_that_cannot_dodge(self):
        rows = ("b...#.....", "...#......", "A..B#.....", "...#......", "........a.")
        state = GameMap("t", rows).create_state()
        state = state.replace(tanks=(state.tanks[0]._replace(facing=int(Direction.RIGHT)),
                                     state.tanks[1]._replace(hp=1)))
        result = AdversarialSearch(SearchConfig.minimax()).search(state, 0, 1)
        self.assertEqual(result.action, Action.FIRE)
        self.assertGreaterEqual(result.value, WIN_SCORE)

    def test_avoids_a_certain_loss_when_it_can(self):
        """A bullet 1 cell away will kill a tank that stays in its path."""
        rows = ("b.........", "..........", "..A.......", "..........", "B.......a.")
        state = GameMap("t", rows).create_state()
        state = state.replace(tanks=(state.tanks[0]._replace(hp=1), state.tanks[1]),
                              bullets=(Bullet(1, 3, 2, int(Direction.LEFT)),))
        result = AdversarialSearch(SearchConfig.alpha_beta_search()).search(state, 0, 1)
        self.assertIn(result.action, (Action.MOVE_UP, Action.MOVE_DOWN))
        self.assertGreater(result.value, -WIN_SCORE)

    def test_prefers_the_nearer_win(self):
        """STAY then FIRE also wins within depth 2, but FIRE now must be valued higher."""
        result = AdversarialSearch(SearchConfig.minimax()).search(self.one_shot_from_winning(), 0, 2)
        self.assertEqual(result.action, Action.FIRE)
        self.assertEqual(result.value, WIN_SCORE + 1)

    def test_terminal_state_at_cycle_limit_is_a_draw_for_search(self):
        state = GameMap("t", OPEN).create_state().replace(max_cycles=1)
        result = AdversarialSearch(SearchConfig.minimax()).search(state, 0, 3)
        self.assertEqual(result.value, 0.0)
        self.assertEqual(result.stats.terminals, 36)

    def test_iterative_deepening_respects_the_time_limit(self):
        state = BUILTIN_MAPS["Fortress"].create_state()
        for limit in (0.02, 0.1):
            result = AdversarialSearch(SearchConfig.optimized()).iterative_deepening(state, 0, limit)
            self.assertLess(result.seconds, limit + 0.05)
            self.assertGreaterEqual(result.depth, 1)

    def test_iterative_deepening_stops_once_the_result_is_forced(self):
        result = AdversarialSearch(SearchConfig.optimized()).iterative_deepening(
            self.one_shot_from_winning(), 0, 5.0)
        self.assertLess(result.seconds, 1.0)
        self.assertEqual(result.action, Action.FIRE)
        self.assertEqual(result.depth, 1)


class _Crashes(Agent):
    def choose_action(self, state, player):
        raise RuntimeError("boom")


class _Nonsense(Agent):
    def choose_action(self, state, player):
        return "DANCE"


class _Sleeps(Agent):
    def choose_action(self, state, player):
        time.sleep(0.3)
        return Action.FIRE


class _Vandal(Agent):
    """Tries to delete the walls of the real game through the state it was given."""

    def choose_action(self, state, player):
        state.walls.clear()
        return Action.STAY


class SafeRunnerTest(unittest.TestCase):
    def setUp(self):
        self.state = BUILTIN_MAPS["Duel"].create_state()

    def test_crash_becomes_stay(self):
        decision = SafeAgentRunner(_Crashes(), 0).decide(self.state)
        self.assertEqual((decision.action, decision.status), (Action.STAY, STATUS_ERROR))
        self.assertIn("boom", decision.detail)

    def test_invalid_answer_becomes_stay(self):
        decision = SafeAgentRunner(_Nonsense(), 0).decide(self.state)
        self.assertEqual((decision.action, decision.status), (Action.STAY, STATUS_INVALID))

    def test_timeout_becomes_stay_and_stays_busy(self):
        runner = SafeAgentRunner(_Sleeps(), 0, hard_limit=0.02)
        self.assertEqual(runner.decide(self.state).status, STATUS_TIMEOUT)
        self.assertEqual(runner.decide(self.state).status, STATUS_TIMEOUT)

    def test_agent_cannot_damage_the_real_state(self):
        walls_before = dict(self.state.walls)
        SafeAgentRunner(_Vandal(), 0).decide(self.state)
        self.assertEqual(self.state.walls, walls_before)

    def test_good_agent_passes_through(self):
        decision = SafeAgentRunner(RandomAgent(seed=1), 0).decide(self.state)
        self.assertEqual(decision.status, STATUS_OK)


class PluginTest(unittest.TestCase):
    def write(self, folder, name, source):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(source))
        return path

    def test_loads_a_function_plugin_that_knows_nothing_of_this_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "group9.py", """
                AGENT_NAME = "Group 9"
                def choose_action(observation):
                    assert observation["my_tank"]["hp"] == 6
                    assert isinstance(observation["walls"], list)
                    return "FIRE"
            """)
            factories = PluginLoader.load_file(path)
            self.assertIn("Group 9", factories)
            decision = SafeAgentRunner(factories["Group 9"](), 0).decide(BUILTIN_MAPS["Duel"].create_state())
            self.assertEqual((decision.action, decision.status), (Action.FIRE, STATUS_OK))

    def test_loads_an_agent_subclass_plugin(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "group3.py", """
                from tank_battle.agents import Agent
                from tank_battle.model import Action
                class Bot(Agent):
                    name = "Bot"
                    def choose_action(self, state, player):
                        return Action.STAY
            """)
            self.assertIn("group3: Bot", PluginLoader.load_file(path))

    def test_helper_classes_are_not_offered_as_players(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "group5.py", """
                from tank_battle.agents import Agent
                from tank_battle.model import Action
                class _Base(Agent):
                    def choose_action(self, state, player):
                        return Action.STAY
                class Bot(_Base):
                    name = "Bot"
            """)
            self.assertEqual(list(PluginLoader.load_file(path)), ["group5: Bot"])

    def test_broken_files_are_reported_without_stopping_the_others(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "good.py", "def choose_action(o):\n    return 'STAY'\n")
            self.write(folder, "syntax.py", "def broken(:\n")
            self.write(folder, "exits.py", "import sys\nsys.exit(1)\n")
            self.write(folder, "empty.py", "x = 1\n")
            catalog = PluginLoader.discover(folder)
            self.assertIn("good", catalog.factories)
            self.assertEqual(set(catalog.errors), {"syntax.py", "exits.py", "empty.py"})

    def test_two_groups_may_use_the_same_file_name(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = self.write(first, "agent.py", "def choose_action(o):\n    return 'FIRE'\n")
            b = self.write(second, "agent.py", "def choose_action(o):\n    return 'STAY'\n")
            state = BUILTIN_MAPS["Duel"].create_state()
            agent_a = PluginLoader.load_file(a)["agent"]()
            agent_b = PluginLoader.load_file(b)["agent"]()
            self.assertEqual(SafeAgentRunner(agent_a, 0).decide(state).action, Action.FIRE)
            self.assertEqual(SafeAgentRunner(agent_b, 0).decide(state).action, Action.STAY)

    def test_bundled_example_plugins_load(self):
        folder = os.path.join(os.path.dirname(__file__), "..", "plugins")
        catalog = PluginLoader.discover(folder)
        self.assertEqual(catalog.errors, {})
        self.assertGreaterEqual(len(catalog.factories), 2)


class MatchTest(unittest.TestCase):
    def test_game_always_ends_and_result_is_consistent(self):
        for game_map in BUILTIN_MAPS.values():
            result = HeadlessMatch(game_map.create_state(max_cycles=60),
                                   (RandomAgent(seed=1), RandomAgent(seed=2))).play()
            self.assertIn(result.outcome, (0, 1, DRAW))
            self.assertLessEqual(result.cycles, 60)
            self.assertEqual(result.records[0].decisions, result.cycles)

    def test_a_faulty_agent_loses_turns_not_the_game_loop(self):
        result = HeadlessMatch(BUILTIN_MAPS["Duel"].create_state(max_cycles=20),
                               (_Crashes(), RandomAgent(seed=3))).play()
        self.assertEqual(result.records[0].faults, result.cycles)

    def test_heuristic_search_beats_random_play(self):
        wins = 0
        for seed in range(4):
            agents = (SearchAgent(SearchConfig.heuristic_alpha_beta(), depth=2), RandomAgent(seed=seed))
            wins += HeadlessMatch(BUILTIN_MAPS["Bunkers"].create_state(), agents).play().outcome == 0
        self.assertEqual(wins, 4)


if __name__ == "__main__":
    unittest.main()


def reference_effort_map(state, target_x, target_y):
    """The effort map as first written: one complete Dijkstra, with no pausing and no bound."""
    import heapq
    width, height, walls = state.width, state.height, state.walls
    blocked = {base.y * width + base.x for base in state.bases}
    costs = [width * height * 8] * (width * height)
    heap = []
    for dx, dy in DELTAS:
        x, y, shots = target_x + dx, target_y + dy, 0
        while 0 <= x < width and 0 <= y < height:
            cell = y * width + x
            if cell in blocked:
                break
            hp = walls.get(cell)
            if hp is not None:
                shots += hp
            elif shots < costs[cell]:
                costs[cell] = shots
                heap.append((shots, cell))
            x += dx
            y += dy
    heapq.heapify(heap)
    while heap:
        cost, cell = heapq.heappop(heap)
        if cost > costs[cell]:
            continue
        y, x = divmod(cell, width)
        step = 1 + walls.get(cell, 0)
        for dx, dy in DELTAS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                neighbour = ny * width + nx
                if neighbour not in blocked and cost + step < costs[neighbour]:
                    costs[neighbour] = cost + step
                    heapq.heappush(heap, (cost + step, neighbour))
    return costs


class ReferenceRaceEvaluator(RaceEvaluator):
    """RaceEvaluator with the finish time computed as first written, from complete maps."""

    def _finish_time(self, state, tank, enemy, base, enemy_hp, base_hp, clearing):
        w = self.weights
        cell = tank.y * state.width + tank.x
        at_base = max(reference_effort_map(state, base.x, base.y)[cell] - clearing, 0)
        at_tank = reference_effort_map(state, enemy.x, enemy.y)[cell]
        finish_base = at_base + max(base_hp, 0)
        finish_tank = at_tank + max(enemy_hp, 0) + w.tank_margin
        line_to_base = direction_towards(tank.x, tank.y, base.x, base.y)
        if line_to_base is not None:
            finish_base += -w.aiming if tank.facing == line_to_base else 1
        if at_tank == 0 and tank.facing != direction_towards(tank.x, tank.y, enemy.x, enemy.y):
            finish_tank += 1
        return max(1.0, min(finish_base, finish_tank))


def varied_states(count_per_map=6):
    """Positions from random play on built-in and random maps: damaged walls, bullets, moved tanks."""
    states = []
    maps = list(BUILTIN_MAPS.values()) + [random_map(seed) for seed in (3, 11)]
    for index, game_map in enumerate(maps):
        for seed in range(count_per_map):
            states.append(random_midgame(game_map, 100 * index + seed, cycles=4 + 5 * seed))
    return states


class ResumableEffortSearchTest(unittest.TestCase):
    """The effort map is computed lazily and with a bound; the answers must be exactly the old ones."""

    def test_every_cell_matches_a_complete_run_whatever_the_order_of_questions(self):
        rng = random.Random(5)
        for state in varied_states(3):
            targets = [(b.x, b.y) for b in state.bases] + [(t.x, t.y) for t in state.tanks]
            for target_x, target_y in targets:
                expected = reference_effort_map(state, target_x, target_y)
                effort = FiringEffortMap()
                cells = list(range(state.width * state.height))
                rng.shuffle(cells)
                for cell in cells:
                    self.assertEqual(effort.effort_at(state, target_x, target_y, cell), expected[cell])
                self.assertEqual(effort.effort(state, target_x, target_y), expected)
                self.assertEqual(FiringEffortMap().effort(state, target_x, target_y), expected)

    def test_a_bounded_question_is_exact_up_to_the_bound_and_never_below_it_after(self):
        rng = random.Random(9)
        for state in varied_states(2):
            tank = state.tanks[1]
            expected = reference_effort_map(state, tank.x, tank.y)
            for _ in range(40):
                cell = rng.randrange(state.width * state.height)
                limit = rng.uniform(-1, 15)
                answer = FiringEffortMap().effort_at(state, tank.x, tank.y, cell, limit)
                if expected[cell] <= limit:
                    self.assertEqual(answer, expected[cell])
                else:
                    self.assertGreater(answer, limit)

    def test_race_evaluator_gives_exactly_the_values_of_the_complete_maps(self):
        fast, reference = RaceEvaluator(), ReferenceRaceEvaluator()
        for state in varied_states():
            for player in (0, 1):
                self.assertEqual(fast.evaluate(state, player), reference.evaluate(state, player))

    def test_optimizations_change_the_work_but_not_the_root_values(self):
        from tank_battle.experiments import OptimizationAblation
        table = OptimizationAblation(depths=(2,), repeats=1).run()
        self.assertTrue(all(row[-1] for row in table.rows), table)
        nodes = {row[1]: row[3] for row in table.rows}
        self.assertLess(nodes["all three"], nodes["Heuristic Alpha-Beta"])
