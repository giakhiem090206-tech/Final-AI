"""Adversarial search: the four required configurations share this one implementation.

Modelling the simultaneous cycle. Both tanks choose on the same state and the cycle then
resolves. In the tree this becomes two plies: MAX picks a1, MIN picks a2 knowing a1, and
RESULT(s, a1, a2) is applied after MIN's ply. This assumes the opponent can answer our
move, so it is cautious, and it keeps the game an ordinary zero-sum tree. A depth of d
cycles is 2d plies; the cut-off only ever falls on a complete cycle.

Configurations
    Minimax / Alpha-Beta                  cut-off value 0, utility only on terminal states
    Heuristic Minimax / Heuristic A-B     cut-off value EVAL(s)

A cut-off value of 0 means treating the depth limit as a declared draw. That is exactly
plain minimax on the same game truncated at that depth, which is what makes the plain
algorithms measurable here: the real game tree is far too deep to search to its end.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from time import perf_counter
from typing import Dict, List, Optional, Sequence, Tuple

from .evaluation import Evaluator, RaceEvaluator, has_clear_shot
from .model import ALL_ACTIONS, DRAW, Action, GameState
from .rules import GameRules

WIN_SCORE = 1_000_000.0
INFINITY = float("inf")
MAX_DEPTH = 40

_EXACT, _LOWER, _UPPER = 0, 1, 2


class _SearchTimeout(Exception):
    pass


def _progress_key(state: GameState, player: int) -> tuple:
    """What a player has achieved so far, to detect a tank going in circles.

    It leaves out the enemy tank's position on purpose: a tank pacing back and forth has made
    no progress, even when the whole board looks new because the enemy kept moving.
    """
    enemy = 1 - player
    mine = tuple(bullet for bullet in state.bullets if bullet.owner == player)
    return (state.tanks[player], state.tanks[enemy].hp, state.bases[enemy].hp, mine, state.walls_key)


@dataclass(frozen=True)
class SearchConfig:
    name: str
    alpha_beta: bool = False
    heuristic: bool = False
    move_ordering: bool = False
    transposition_table: bool = False
    action_pruning: bool = False
    repetition_penalty: float = 0.0  # value lost for each earlier visit to a position of this game

    @classmethod
    def minimax(cls) -> "SearchConfig":
        return cls("Minimax")

    @classmethod
    def alpha_beta_search(cls) -> "SearchConfig":
        return cls("Alpha-Beta", alpha_beta=True)

    @classmethod
    def heuristic_minimax(cls) -> "SearchConfig":
        return cls("Heuristic Minimax", heuristic=True)

    @classmethod
    def heuristic_alpha_beta(cls) -> "SearchConfig":
        return cls("Heuristic Alpha-Beta", alpha_beta=True, heuristic=True)

    @classmethod
    def optimized(cls) -> "SearchConfig":
        """The controller for real play: Heuristic Alpha-Beta with every speed-up on."""
        return cls("Heuristic A-B + optimizations", alpha_beta=True, heuristic=True, move_ordering=True,
                   transposition_table=True, action_pruning=True, repetition_penalty=11.25)

    @classmethod
    def required_four(cls) -> List["SearchConfig"]:
        return [cls.minimax(), cls.alpha_beta_search(), cls.heuristic_minimax(), cls.heuristic_alpha_beta()]


@dataclass
class SearchStats:
    nodes: int = 0             # states explored: MAX nodes and MIN nodes
    expansions: int = 0        # calls to RESULT
    evaluations: int = 0       # cut-off evaluations
    terminals: int = 0         # terminal states reached
    cutoffs: int = 0           # alpha or beta cut-offs
    table_hits: int = 0        # searches avoided by the transposition table

    def add(self, other: "SearchStats") -> None:
        self.nodes += other.nodes
        self.expansions += other.expansions
        self.evaluations += other.evaluations
        self.terminals += other.terminals
        self.cutoffs += other.cutoffs
        self.table_hits += other.table_hits


@dataclass
class SearchResult:
    action: Action
    value: float
    depth: int                 # complete cycles searched
    seconds: float
    stats: SearchStats = field(default_factory=SearchStats)
    timed_out: bool = False

    @property
    def plies(self) -> int:
        return 2 * self.depth


class AdversarialSearch:
    """Depth-limited search of the game tree for one player, under a SearchConfig."""

    MAX_TABLE_SIZE = 400_000

    def __init__(self, config: SearchConfig, evaluator: Optional[Evaluator] = None) -> None:
        self.config = config
        self.evaluator = (evaluator or RaceEvaluator()) if config.heuristic else None
        self._table: Dict[tuple, Tuple[int, float, int, Action]] = {}
        self._killers: Dict[int, Action] = {}
        self._stats = SearchStats()
        self._player = 0
        self._deadline: Optional[float] = None
        self._root_best: Optional[Tuple[Action, float]] = None
        self._visits: Dict[tuple, int] = {}
        self._replies: Dict[tuple, Action] = {}
        self._history: List[List[int]] = [[0] * 6, [0] * 6]

    def reset(self) -> None:
        """Forget everything learned, for a new game."""
        self._table.clear()
        self._killers.clear()
        self._visits.clear()
        self._replies.clear()
        self._history = [[0] * 6, [0] * 6]

    def record_position(self, state: GameState, player: int) -> None:
        """Note a position the real game has reached, so the search can avoid going in circles."""
        key = _progress_key(state, player)
        self._visits[key] = self._visits.get(key, 0) + 1

    # ----------------------------------------------------------------- entry points
    def search(self, state: GameState, player: int, depth: int,
               rng: Optional[random.Random] = None) -> SearchResult:
        """Fixed-depth search. `rng` shuffles the root actions, which breaks ties at random."""
        self._player = player
        self._stats = SearchStats()
        self._deadline = None
        start = perf_counter()
        action, value = self._search_root(state, depth, self._root_actions(state, rng))
        return SearchResult(action, value, depth, perf_counter() - start, self._stats)

    def iterative_deepening(self, state: GameState, player: int, time_limit: float,
                            max_depth: int = MAX_DEPTH,
                            rng: Optional[random.Random] = None) -> SearchResult:
        """Deepen one cycle at a time until the time runs out: this is what keeps play real-time.

        If an iteration is interrupted its partial answer is still used, because the previous
        best action is searched first and is replaced only by something proven better.
        """
        self._player = player
        self._stats = SearchStats()
        start = perf_counter()
        self._deadline = start + time_limit
        best_action, best_value, completed = Action.STAY, 0.0, 0
        timed_out = False
        order = self._root_actions(state, rng)
        for depth in range(1, max_depth + 1):
            self._root_best = None
            try:
                best_action, best_value = self._search_root(state, depth, order)
            except _SearchTimeout:
                timed_out = True
                if self._root_best is not None:
                    best_action, best_value = self._root_best
                break
            completed = depth
            if abs(best_value) >= WIN_SCORE:  # a forced result: deeper search cannot change it
                break
            order = [best_action] + [a for a in order if a != best_action]
        self._deadline = None
        return SearchResult(best_action, best_value, completed, perf_counter() - start,
                            self._stats, timed_out)

    def principal_variation(self, state: GameState, player: int, first: Action, length: int = 6) -> List[Tuple[int, int]]:
        """The cells this player's tank is expected to visit, read back from the search's memory."""
        cells: List[Tuple[int, int]] = []
        action: Optional[Action] = first
        for _ in range(length):
            key = state.key()
            if action is None:
                entry = self._table.get(key)
                if entry is None:
                    break
                action = entry[3]
            reply = self._replies.get((key, action))
            if reply is None:
                break
            state = GameRules.step(state, action, reply) if player == 0 else GameRules.step(state, reply, action)
            tank = state.tanks[player]
            cells.append((tank.x, tank.y))
            if GameRules.outcome(state) is not None:
                break
            action = None
        return cells

    # ------------------------------------------------------------------- the search
    def _root_actions(self, state: GameState, rng: Optional[random.Random]) -> List[Action]:
        actions = self._actions(state, self._player)
        if rng is not None:
            rng.shuffle(actions)
        elif self.config.move_ordering:
            actions = self._order(state, self._player, actions, None)
        return actions

    def _search_root(self, state: GameState, depth: int, actions: Sequence[Action]) -> Tuple[Action, float]:
        self._stats.nodes += 1
        alpha, beta = -INFINITY, INFINITY
        best_action, best_value = actions[0], -INFINITY
        key = state.key() if self.config.transposition_table else None
        for action in actions:
            value = self._min_value(state, action, depth, alpha, beta, key)
            if value > best_value:
                best_action, best_value = action, value
                self._root_best = (best_action, best_value)
            if self.config.alpha_beta and value > alpha:
                alpha = value
        return best_action, best_value

    def _max_value(self, state: GameState, depth: int, alpha: float, beta: float) -> float:
        stats = self._stats
        stats.nodes += 1
        if self._deadline is not None and not stats.nodes & 255 and perf_counter() > self._deadline:
            raise _SearchTimeout

        outcome = GameRules.outcome(state)
        if outcome is not None:
            stats.terminals += 1
            if outcome == DRAW:
                return 0.0
            # The remaining depth makes a nearer win worth more and a nearer loss worth less.
            return WIN_SCORE + depth if outcome == self._player else -WIN_SCORE - depth
        if depth == 0:
            if self.evaluator is None:
                return 0.0
            stats.evaluations += 1
            return self.evaluator.evaluate(state, self._player)

        config = self.config
        table_move: Optional[Action] = None
        key = None
        original_alpha = alpha
        if config.transposition_table:
            key = state.key()
            entry = self._table.get(key)
            if entry is not None:
                table_depth, table_value, flag, table_move = entry
                if table_depth == depth and (
                    flag == _EXACT
                    or (flag == _LOWER and table_value >= beta)
                    or (flag == _UPPER and table_value <= alpha)
                ):
                    stats.table_hits += 1
                    return table_value

        actions = self._actions(state, self._player)
        if config.move_ordering:
            actions = self._order(state, self._player, actions, table_move)

        prune = config.alpha_beta
        best_value = -INFINITY
        best_action = actions[0]
        for action in actions:
            value = self._min_value(state, action, depth, alpha, beta, key)
            if value > best_value:
                best_value, best_action = value, action
            if prune:
                if best_value >= beta:
                    stats.cutoffs += 1
                    if config.move_ordering:
                        self._history[self._player][action] += depth * depth
                    break
                if best_value > alpha:
                    alpha = best_value

        if key is not None:
            if len(self._table) >= self.MAX_TABLE_SIZE:
                self._table.clear()
            if best_value <= original_alpha:
                flag = _UPPER
            elif best_value >= beta:
                flag = _LOWER
            else:
                flag = _EXACT
            self._table[key] = (depth, best_value, flag, best_action)
        return best_value

    def _min_value(self, state: GameState, action: Action, depth: int, alpha: float, beta: float,
                   key: Optional[tuple] = None) -> float:
        """MIN answers MAX's `action`; the cycle resolves and a new state is reached."""
        stats = self._stats
        stats.nodes += 1
        opponent = 1 - self._player
        config = self.config
        replies = self._actions(state, opponent)
        memory_key = (key, action) if key is not None else None
        if config.move_ordering:
            remembered = self._replies.get(memory_key) if memory_key is not None else None
            replies = self._order(state, opponent, replies, remembered or self._killers.get(depth))

        prune = config.alpha_beta
        step = GameRules.step
        first_is_max = self._player == 0
        best_value = INFINITY
        best_reply = replies[0]
        visits = self._visits
        penalty_per_visit = config.repetition_penalty
        for reply in replies:
            child = step(state, action, reply) if first_is_max else step(state, reply, action)
            stats.expansions += 1
            count = visits.get(_progress_key(child, self._player)) if visits else None
            if count:
                # The window moves with the penalty, so that pruning stays correct.
                penalty = count * penalty_per_visit
                value = self._max_value(child, depth - 1, alpha + penalty, beta + penalty) - penalty
            else:
                value = self._max_value(child, depth - 1, alpha, beta)
            if value < best_value:
                best_value, best_reply = value, reply
            if prune:
                if best_value <= alpha:
                    stats.cutoffs += 1
                    self._killers[depth] = reply
                    if config.move_ordering:
                        self._history[opponent][reply] += depth * depth
                    break
                if best_value < beta:
                    beta = best_value
        if memory_key is not None:
            if len(self._replies) >= self.MAX_TABLE_SIZE:
                self._replies.clear()
            self._replies[memory_key] = best_reply
        return best_value

    # -------------------------------------------------------------- the optimizations
    def _actions(self, state: GameState, player: int) -> List[Action]:
        if self.config.action_pruning:
            return GameRules.effective_actions(state, player)
        return list(ALL_ACTIONS)

    def _order(self, state: GameState, player: int, actions: List[Action],
               first: Optional[Action]) -> List[Action]:
        """Likely-best first: remembered move, a shot that hits, moves, then the rest.

        Within a rank, actions that have caused more cut-offs so far come first.
        """
        tank = state.tanks[player]
        shot_is_clear = has_clear_shot(state, tank)
        history = self._history[player]
        ranked = []
        for action in actions:
            if action == first:
                rank = 0
            elif action == Action.FIRE:
                rank = 1 if shot_is_clear else 3
            elif action == Action.STAY:
                rank = 4
            else:
                rank = 2
            ranked.append((rank, -history[action], action))
        # Actions arrive in ascending order, so ties fall back to that order, as a stable sort would.
        ranked.sort()
        return [action for _, _, action in ranked]
