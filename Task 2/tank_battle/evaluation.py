"""Heuristic evaluation EVAL(s, p) for states the search does not expand further."""
from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .model import DELTAS, Direction, GameState, Tank

# What a ray or bullet path runs into first.
_HIT_NOTHING, _HIT_WALL, _HIT_TANK0, _HIT_TANK1, _HIT_BASE0, _HIT_BASE1 = range(6)
_TANK_HIT = (_HIT_TANK0, _HIT_TANK1)
_BASE_HIT = (_HIT_BASE0, _HIT_BASE1)


class Evaluator(ABC):
    """A heuristic must be zero-sum: evaluate(s, 0) == -evaluate(s, 1)."""

    @abstractmethod
    def evaluate(self, state: GameState, player: int) -> float:
        """Estimated value of a non-terminal state for `player`."""


class PathCostMap:
    """Cheapest way to reach each cell from a target, counting walls as obstacles to shoot.

    Entering a free cell costs 1; entering a wall costs 1 + its HP (the shots to clear it
    and the move). Dijkstra runs only when the walls changed: inside a search tree walls
    rarely change, so almost every query is answered from the cache.
    """

    MAX_CACHED = 2048

    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, int], List[int]] = {}

    def costs_to(self, state: GameState, target_x: int, target_y: int) -> List[int]:
        target = target_y * state.width + target_x
        key = (target, state.walls_key)
        costs = self._cache.get(key)
        if costs is None:
            if len(self._cache) >= self.MAX_CACHED:
                self._cache.clear()
            costs = self._dijkstra(state, target)
            self._cache[key] = costs
        return costs

    @staticmethod
    def _dijkstra(state: GameState, target: int) -> List[int]:
        width, height, walls = state.width, state.height, state.walls
        blocked = {base.y * width + base.x for base in state.bases}
        unreachable = width * height * 8
        costs = [unreachable] * (width * height)
        costs[target] = 0
        heap = [(0, target)]
        while heap:
            cost, cell = heapq.heappop(heap)
            if cost > costs[cell]:
                continue
            y, x = divmod(cell, width)
            # The step from `cell` to a neighbour is paid for entering `cell` on the way back,
            # which charges walls correctly when walking from a tank towards the target.
            step = 1 + walls.get(cell, 0)
            for dx, dy in DELTAS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    neighbour = ny * width + nx
                    if neighbour not in blocked and cost + step < costs[neighbour]:
                        costs[neighbour] = cost + step
                        heapq.heappush(heap, (cost + step, neighbour))
        return costs


@dataclass(frozen=True)
class EvaluationWeights:
    tank_hp: float = 10.0        # per hit point of the player's tank
    base_hp: float = 7.0         # per hit point of the player's base
    bullet_at_tank: float = 5.0  # bullet heading for the tank (it may still dodge)
    bullet_at_base: float = 7.0  # bullet heading for the base (a base cannot dodge)
    line_to_tank: float = 2.0    # clear line of fire to the enemy tank
    line_to_base: float = 2.5    # clear line of fire to the enemy base
    aiming: float = 2.0          # ... and already facing along that line
    path_cost: float = 0.6       # per unit of path cost to the enemy base


class HeuristicEvaluator(Evaluator):
    """Weighted features of each side; EVAL is one side minus the other, so it is zero-sum.

    The features estimate what the search cannot yet see: damage already on its way
    (bullets in flight), damage that could be dealt next (lines of fire, aiming) and
    how far the tank still has to go to threaten the enemy base.
    """

    def __init__(self, weights: Optional[EvaluationWeights] = None,
                 path_costs: Optional[PathCostMap] = None) -> None:
        self.weights = weights or EvaluationWeights()
        self.path_costs = path_costs or PathCostMap()

    def evaluate(self, state: GameState, player: int) -> float:
        score = self._assets_and_bullets(state) + self._threats(state, 0) - self._threats(state, 1)
        return score if player == 0 else -score

    def _assets_and_bullets(self, state: GameState) -> float:
        """HP difference, counting bullets in flight as the damage they are about to do."""
        w = self.weights
        tank0, tank1 = state.tanks
        base0, base1 = state.bases
        score = (w.tank_hp * (tank0.hp - tank1.hp) + w.base_hp * (base0.hp - base1.hp))
        for bullet in state.bullets:
            hit = first_hit(state, bullet.x, bullet.y, bullet.direction)
            if hit == _HIT_TANK0:
                score -= w.bullet_at_tank
            elif hit == _HIT_TANK1:
                score += w.bullet_at_tank
            elif hit == _HIT_BASE0:
                score -= w.bullet_at_base
            elif hit == _HIT_BASE1:
                score += w.bullet_at_base
        return score

    def _threats(self, state: GameState, player: int) -> float:
        """What `player`'s tank could do next, and how close it is to the enemy base."""
        w = self.weights
        tank = state.tanks[player]
        enemy = state.tanks[1 - player]
        base = state.bases[1 - player]
        score = -w.path_cost * self.path_costs.costs_to(state, base.x, base.y)[tank.y * state.width + tank.x]
        direction = direction_towards(tank.x, tank.y, enemy.x, enemy.y)
        if direction is not None and first_hit(state, tank.x, tank.y, direction) == _TANK_HIT[1 - player]:
            score += w.line_to_tank + (w.aiming if tank.facing == direction else 0.0)
        direction = direction_towards(tank.x, tank.y, base.x, base.y)
        if direction is not None and first_hit(state, tank.x, tank.y, direction) == _BASE_HIT[1 - player]:
            score += w.line_to_base + (w.aiming if tank.facing == direction else 0.0)
        return score


INFINITE_EFFORT = float("inf")


class _EffortSearch:
    """One Dijkstra run towards one target, paused as soon as the cell asked about is settled.

    The evaluator needs the effort at a single cell (where the tank stands), not the whole map.
    So the run stops when that cell leaves the queue, and the next question about the same
    target and walls resumes it from there. The costs are those of a complete run, because
    Dijkstra settles cells in order of cost whether or not it is paused in between.
    """

    __slots__ = ("costs", "heap", "settled", "walls", "neighbours")

    def __init__(self, costs: List[int], heap: List[Tuple[int, int]], walls: Dict[int, int],
                 neighbours: Tuple[Tuple[int, ...], ...]) -> None:
        self.costs = costs
        self.heap = heap
        self.settled = bytearray(len(costs))
        self.walls = walls
        self.neighbours = neighbours

    def cost_at(self, cell: int, limit: float = INFINITE_EFFORT) -> float:
        """The exact cost of `cell`, or infinity as soon as it is certain to exceed `limit`."""
        if cell >= 0 and self.settled[cell]:
            return self.costs[cell]
        costs, heap, settled, walls, neighbours = self.costs, self.heap, self.settled, self.walls, self.neighbours
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            if heap[0][0] > limit:  # every cell not yet settled costs more than the limit
                return INFINITE_EFFORT
            cost, current = pop(heap)
            if settled[current]:
                continue  # an outdated queue entry
            settled[current] = 1
            # The step from `current` to a neighbour is paid for entering `current` on the way
            # back, which charges walls correctly when walking from a tank towards the target.
            reached = cost + 1 + walls.get(current, 0)
            for neighbour in neighbours[current]:
                if reached < costs[neighbour]:
                    costs[neighbour] = reached
                    push(heap, (reached, neighbour))
            if current == cell:
                return cost
        return costs[cell] if cell >= 0 else INFINITE_EFFORT  # never reached: walled off

    def complete(self) -> List[int]:
        """Finish the run and return every cell's cost."""
        self.cost_at(-1)  # a cell that never settles, so the run goes to its end
        return self.costs


class FiringEffortMap:
    """Work needed from each cell before a tank can land its first hit on a target.

    Bullets have unlimited range, so a tank does not need to walk up to a target: it only
    needs a straight line to it. Every cell in line with the target is a starting point,
    costing the shots needed to clear the walls in between. Dijkstra then adds the walk to
    such a cell, counting 1 per move and 1 + HP for a wall in the way. Runs are cached by
    target and walls, and each run goes only as far as the questions asked of it need.
    """

    MAX_CACHED = 4096

    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, int, int], _EffortSearch] = {}
        self._neighbours: Dict[tuple, Tuple[Tuple[int, ...], ...]] = {}

    def effort(self, state: GameState, target_x: int, target_y: int) -> List[int]:
        """The whole map, one cost per cell (used to draw it)."""
        return self.search(state, target_x, target_y).complete()

    def effort_at(self, state: GameState, target_x: int, target_y: int, cell: int,
                  limit: float = INFINITE_EFFORT) -> float:
        """The effort from one cell; infinity if it is certainly above `limit`."""
        return self.search(state, target_x, target_y).cost_at(cell, limit)

    def search(self, state: GameState, target_x: int, target_y: int) -> _EffortSearch:
        """The (possibly paused) run for this target and these walls, started if new."""
        key = (target_y * state.width + target_x, state.walls_key, state.width)
        search = self._cache.get(key)
        if search is None:
            if len(self._cache) >= self.MAX_CACHED:
                self._cache.clear()
            search = self._start(state, target_x, target_y)
            self._cache[key] = search
        return search

    def _neighbour_table(self, state: GameState) -> Tuple[Tuple[int, ...], ...]:
        """For each cell, the cells a tank can step to from it. Bases are never entered."""
        width, height = state.width, state.height
        blocked = {base.y * width + base.x for base in state.bases}
        key = (width, height, tuple(sorted(blocked)))
        table = self._neighbours.get(key)
        if table is None:
            rows = []
            for cell in range(width * height):
                y, x = divmod(cell, width)
                row = []
                for dx, dy in DELTAS:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height and ny * width + nx not in blocked:
                        row.append(ny * width + nx)
                rows.append(tuple(row))
            table = self._neighbours[key] = tuple(rows)
        return table

    def _start(self, state: GameState, target_x: int, target_y: int) -> _EffortSearch:
        """Seed the queue with every cell in line with the target, at the cost of the walls in between."""
        width, height, walls = state.width, state.height, state.walls
        blocked = {base.y * width + base.x for base in state.bases}
        costs = [width * height * 8] * (width * height)
        heap: List[Tuple[int, int]] = []
        for dx, dy in DELTAS:
            x, y = target_x + dx, target_y + dy
            shots = 0
            while 0 <= x < width and 0 <= y < height:
                cell = y * width + x
                if cell in blocked:  # a base stops the bullets, and it is not ours to shoot through
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
        return _EffortSearch(costs, heap, walls, self._neighbour_table(state))


@dataclass(frozen=True)
class RaceWeights:
    """Values found by run_tuning.py, by hill climbing on the results of games."""

    tank_hp: float = 10.0         # per hit point of the tank
    base_hp: float = 8.75         # per hit point of the base
    bullet_at_tank: float = 4.188 # bullet heading for a tank (it may still dodge)
    bullet_at_base: float = 18.76 # bullet heading for a base (it cannot dodge)
    race: float = 1.125           # per cycle of lead in the race to destroy something first
    urgency: float = 60.0         # grows sharply as a side gets close to finishing
    tank_margin: float = 6.432    # extra cycles for hunting a tank, since a tank can step aside
    aiming: float = 0.449         # already facing along a clear line of fire at a target
    aggression: float = 1.875     # per cycle of the searching side's own finish time


class RaceEvaluator(Evaluator):
    """Estimates who wins the race to destroy the other side's tank or base.

    For each side, finish time = cycles to get a line of fire + hits still needed, taking
    the better of the two targets and counting bullets already in flight as hits. The
    game is decided by who finishes first, so the lead in finish time is what is scored,
    and a side about to finish weighs far more than a distant advantage.

    `aggression` rewards shortening one's own finish time even when the opponent gains
    as much, for instance by shooting a wall that shields both sides. Without it, two
    tanks facing such a wall see no gain in acting and shuffle about until the cycle
    limit. It is the only term that is not antisymmetric, and it can be set to 0.
    """

    def __init__(self, weights: Optional[RaceWeights] = None, effort: Optional[FiringEffortMap] = None) -> None:
        self.weights = weights or RaceWeights()
        self.effort = effort or FiringEffortMap()

    def evaluate(self, state: GameState, player: int) -> float:
        w = self.weights
        tank0, tank1 = state.tanks
        base0, base1 = state.bases
        hits_tank0 = hits_tank1 = hits_base0 = hits_base1 = 0
        clearing = [0, 0]  # bullets on their way to a wall that shields the enemy base
        for bullet in state.bullets:
            hit = first_hit(state, bullet.x, bullet.y, bullet.direction)
            if hit == _HIT_TANK0:
                hits_tank0 += 1
            elif hit == _HIT_TANK1:
                hits_tank1 += 1
            elif hit == _HIT_BASE0:
                hits_base0 += 1
            elif hit == _HIT_BASE1:
                hits_base1 += 1
            elif hit == _HIT_WALL:
                # A long shot lands only cycles later, usually beyond the search horizon, and
                # would look pointless. It is credited now, as the work it will do.
                target = state.bases[1 - bullet.owner]
                if direction_towards(bullet.x, bullet.y, target.x, target.y) == bullet.direction:
                    clearing[bullet.owner] += 1

        score = (w.tank_hp * (tank0.hp - tank1.hp) + w.base_hp * (base0.hp - base1.hp)
                 + w.bullet_at_tank * (hits_tank1 - hits_tank0) + w.bullet_at_base * (hits_base1 - hits_base0))

        finish0 = self._finish_time(state, tank0, tank1, base1, tank1.hp - hits_tank1, base1.hp - hits_base1, clearing[0])
        finish1 = self._finish_time(state, tank1, tank0, base0, tank0.hp - hits_tank0, base0.hp - hits_base0, clearing[1])
        score += w.race * (finish1 - finish0) + w.urgency * (1.0 / finish0 - 1.0 / finish1)
        if player == 0:
            return score - w.aggression * finish0
        return -score - w.aggression * finish1

    def _finish_time(self, state: GameState, tank: Tank, enemy: Tank, base, enemy_hp: int, base_hp: int,
                     clearing: int) -> float:
        """Cycles until this side could destroy the enemy base or tank; never below 1."""
        w = self.weights
        cell = tank.y * state.width + tank.x
        # Most questions are about a cell the run has already settled: answer those directly.
        to_base = self.effort.search(state, base.x, base.y)
        at_base = to_base.costs[cell] if to_base.settled[cell] else to_base.cost_at(cell)
        at_base = max(at_base - clearing, 0)
        finish_base = at_base + max(base_hp, 0)
        line_to_base = direction_towards(tank.x, tank.y, base.x, base.y)
        if line_to_base is not None:
            # Already lined up, with or without walls in between: only aiming is left to do.
            finish_base += -w.aiming if tank.facing == line_to_base else 1
        # Hunting the tank wins only if it would finish before the base. Above this effort it
        # cannot, so the search for the tank's effort may stop there and answer infinity.
        limit = finish_base - max(enemy_hp, 0) - w.tank_margin + 1e-6
        if limit < 0:  # efforts are never negative, so the base is the target whatever the tank's effort
            at_tank = INFINITE_EFFORT
        else:
            to_tank = self.effort.search(state, enemy.x, enemy.y)
            at_tank = to_tank.costs[cell] if to_tank.settled[cell] else to_tank.cost_at(cell, limit)
        finish_tank = at_tank + max(enemy_hp, 0) + w.tank_margin
        if at_tank == 0 and tank.facing != direction_towards(tank.x, tank.y, enemy.x, enemy.y):
            finish_tank += 1
        return max(1.0, min(finish_base, finish_tank))


def direction_towards(x: int, y: int, target_x: int, target_y: int) -> Optional[int]:
    """Direction of a target in the same row or column, otherwise None."""
    if x == target_x:
        return int(Direction.UP) if target_y < y else int(Direction.DOWN)
    if y == target_y:
        return int(Direction.LEFT) if target_x < x else int(Direction.RIGHT)
    return None


def first_hit(state: GameState, x: int, y: int, direction: int) -> int:
    """Walk along a straight line from (x, y), not counting the start, until something blocks it."""
    width, height, walls = state.width, state.height, state.walls
    tank0, tank1 = state.tanks
    base0, base1 = state.bases
    dx, dy = DELTAS[direction]
    x += dx
    y += dy
    while 0 <= x < width and 0 <= y < height:
        if y * width + x in walls:
            return _HIT_WALL
        if x == tank0.x and y == tank0.y:
            return _HIT_TANK0
        if x == tank1.x and y == tank1.y:
            return _HIT_TANK1
        if x == base0.x and y == base0.y:
            return _HIT_BASE0
        if x == base1.x and y == base1.y:
            return _HIT_BASE1
        x += dx
        y += dy
    return _HIT_NOTHING


def has_clear_shot(state: GameState, tank: Tank) -> bool:
    """True when a bullet fired now would hit the enemy tank or base first."""
    enemy = 1 - tank.owner
    return first_hit(state, tank.x, tank.y, tank.facing) in (_TANK_HIT[enemy], _BASE_HIT[enemy])
