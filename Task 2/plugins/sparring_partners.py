"""Simple opponents with distinct styles, for testing an algorithm against more than itself."""
import heapq

from tank_battle.agents import Agent
from tank_battle.evaluation import direction_towards, first_hit
from tank_battle.model import DELTAS, Action
from tank_battle.rules import GameRules


class _Attacker(Agent):
    """Shoots when a target is in clear line, otherwise walks the cheapest way towards one."""

    def targets(self, state, player):
        raise NotImplementedError

    def choose_action(self, state, player):
        tank = state.tanks[player]
        targets = self.targets(state, player)
        for target in targets:
            direction = direction_towards(tank.x, tank.y, target.x, target.y)
            if direction is not None and self._clear(state, tank, target, direction):
                return Action.FIRE if tank.facing == direction else Action(direction)
        return self._walk(state, player, targets[0])

    @staticmethod
    def _clear(state, tank, target, direction):
        x, y = tank.x, tank.y
        dx, dy = DELTAS[direction]
        x, y = x + dx, y + dy
        while (x, y) != (target.x, target.y):
            if y * state.width + x in state.walls:
                return False
            x, y = x + dx, y + dy
        return True

    @staticmethod
    def _walk(state, player, target):
        """First step of the cheapest path; a wall in the way is shot rather than walked around."""
        tank = state.tanks[player]
        width = state.width
        goal = target.y * width + target.x
        blocked = {b.y * width + b.x for b in state.bases} - {goal}
        best = {tank.y * width + tank.x: 0}
        heap = [(0, tank.y * width + tank.x, None)]
        while heap:
            cost, cell, first = heapq.heappop(heap)
            if cell == goal:
                break
            if cost > best[cell]:
                continue
            y, x = divmod(cell, width)
            for action, (dx, dy) in enumerate(DELTAS):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < state.height):
                    continue
                neighbour = ny * width + nx
                if neighbour in blocked:
                    continue
                step = cost + 1 + state.walls.get(neighbour, 0)
                if step < best.get(neighbour, 10 ** 9):
                    best[neighbour] = step
                    heapq.heappush(heap, (step, neighbour, action if first is None else first))
        else:
            return Action.STAY
        if first is None:
            return Action.FIRE
        ahead = (tank.y + DELTAS[first][1]) * width + tank.x + DELTAS[first][0]
        if ahead in state.walls and tank.facing == first:
            return Action.FIRE
        return Action(first)


class Rusher(_Attacker):
    """Ignores the enemy tank and goes straight for the enemy base."""

    name = "Rusher"

    def targets(self, state, player):
        return [state.bases[1 - player]]


class Hunter(_Attacker):
    """Chases the enemy tank, and shoots the base only when it happens to be in line."""

    name = "Hunter"

    def targets(self, state, player):
        return [state.tanks[1 - player], state.bases[1 - player]]


class Turret(Agent):
    """Stays put and turns to shoot whatever it has a clear line to."""

    name = "Turret"

    def choose_action(self, state, player):
        tank = state.tanks[player]
        enemy = 1 - player
        for target, wanted in ((state.tanks[enemy], _TANK[enemy]), (state.bases[enemy], _BASE[enemy])):
            direction = direction_towards(tank.x, tank.y, target.x, target.y)
            if direction is not None and first_hit(state, tank.x, tank.y, direction) == wanted:
                return Action.FIRE if tank.facing == direction else Action(direction)
        return Action.STAY


# Codes returned by first_hit for each player's tank and base.
_TANK = (2, 3)
_BASE = (4, 5)


class Dodger(_Attacker):
    """Attacks the base like a rusher, but first steps out of the way of bullets coming at it."""

    name = "Dodger"

    def targets(self, state, player):
        return [state.bases[1 - player]]

    def choose_action(self, state, player):
        tank = state.tanks[player]
        code = _TANK[player]
        threatened = any(
            b.owner != player and first_hit(state, b.x, b.y, b.direction) == code for b in state.bullets
        )
        if threatened:
            for action in (Action.MOVE_LEFT, Action.MOVE_RIGHT, Action.MOVE_UP, Action.MOVE_DOWN):
                dx, dy = DELTAS[action]
                if GameRules.can_enter(state, player, tank.x + dx, tank.y + dy):
                    return action
        return super().choose_action(state, player)
