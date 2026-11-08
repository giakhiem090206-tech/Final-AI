"""The rules of the game: transition function, terminal test and utility.

One game cycle, given both players' actions:
  1. Tanks turn and move at the same time.
  2. A tank that drove onto a bullet in flight is hit.
  3. FIRE places a bullet on the shooter's cell, facing the same way.
  4. Three times over, every bullet advances one cell and collisions are checked at once.
     The game stops at the end of the sub-step in which a tank or base is destroyed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .model import (
    ALL_ACTIONS,
    BULLET_SPEED,
    DAMAGE_PER_HIT,
    DELTAS,
    DRAW,
    Action,
    Base,
    Bullet,
    GameState,
    Tank,
)

_FIRE = int(Action.FIRE)
_STAY = int(Action.STAY)

TARGET_WALL, TARGET_TANK, TARGET_BASE = "WALL", "TANK", "BASE"


@dataclass(frozen=True)
class CollisionEvent:
    """A bullet hit something. `substep` is 0 when a tank drove into a bullet."""

    substep: int
    shooter: int
    target: str
    target_owner: Optional[int]
    x: int
    y: int
    hp_after: int

    @property
    def destroyed(self) -> bool:
        return self.hp_after <= 0


@dataclass
class StepTrace:
    """What happened inside a cycle, for the interface and for logging.

    `frames[i]` lists every bullet's cell after sub-step i + 1. A bullet that collided
    appears on the cell it hit in that frame and is gone from the next one.
    """

    frames: List[List[Bullet]] = field(default_factory=list)
    events: List[CollisionEvent] = field(default_factory=list)


class GameRules:
    """Stateless implementation of RESULT(s, a), TERMINAL-TEST(s) and UTILITY(s, p)."""

    @staticmethod
    def legal_actions(state: GameState, player: int) -> Tuple[Action, ...]:
        """All six actions are always legal: a blocked move still turns the tank."""
        return ALL_ACTIONS

    @staticmethod
    def effective_actions(state: GameState, player: int) -> List[Action]:
        """Legal actions without those identical to STAY (blocked and already facing that way)."""
        tank = state.tanks[player]
        return [
            action for action in ALL_ACTIONS
            if action >= _FIRE or action != tank.facing or GameRules.can_enter(
                state, player, tank.x + DELTAS[action][0], tank.y + DELTAS[action][1])
        ]

    @staticmethod
    def can_enter(state: GameState, player: int, x: int, y: int) -> bool:
        if not (0 <= x < state.width and 0 <= y < state.height):
            return False
        if y * state.width + x in state.walls:
            return False
        other = state.tanks[1 - player]
        if other.x == x and other.y == y:
            return False
        base0, base1 = state.bases
        return not ((base0.x == x and base0.y == y) or (base1.x == x and base1.y == y))

    @staticmethod
    def step(state: GameState, action0: int, action1: int,
             trace: Optional[StepTrace] = None) -> GameState:
        """RESULT(s, a0, a1). This is the hot path of the search, hence the unpacked locals."""
        width, height = state.width, state.height
        walls = state.walls
        walls_key = state.walls_key
        tank0, tank1 = state.tanks
        base0, base1 = state.bases
        old_x0, old_y0, facing0, hp0 = tank0.x, tank0.y, tank0.facing, tank0.hp
        old_x1, old_y1, facing1, hp1 = tank1.x, tank1.y, tank1.facing, tank1.hp
        base_x0, base_y0, base_hp0 = base0.x, base0.y, base0.hp
        base_x1, base_y1, base_hp1 = base1.x, base1.y, base1.hp
        x0, y0, x1, y1 = old_x0, old_y0, old_x1, old_y1

        # 1. Turn and move. A move always turns the tank, even when the cell ahead is
        # blocked: otherwise a tank could never aim at a wall right next to it.
        if action0 < _FIRE:
            facing0 = int(action0)
            dx, dy = DELTAS[action0]
            cx, cy = old_x0 + dx, old_y0 + dy
            if (0 <= cx < width and 0 <= cy < height and cy * width + cx not in walls
                    and not (cx == old_x1 and cy == old_y1)
                    and not (cx == base_x0 and cy == base_y0)
                    and not (cx == base_x1 and cy == base_y1)):
                x0, y0 = cx, cy
        if action1 < _FIRE:
            facing1 = int(action1)
            dx, dy = DELTAS[action1]
            cx, cy = old_x1 + dx, old_y1 + dy
            if (0 <= cx < width and 0 <= cy < height and cy * width + cx not in walls
                    and not (cx == old_x0 and cy == old_y0)
                    and not (cx == base_x0 and cy == base_y0)
                    and not (cx == base_x1 and cy == base_y1)):
                x1, y1 = cx, cy
        if x0 == x1 and y0 == y1:  # both chose the same free cell: neither gets it
            x0, y0, x1, y1 = old_x0, old_y0, old_x1, old_y1

        # 2. A tank that drove onto a bullet in flight would otherwise jump over it.
        flying = state.bullets
        if flying and ((x0 != old_x0 or y0 != old_y0) or (x1 != old_x1 or y1 != old_y1)):
            remaining = []
            for bullet in flying:
                if bullet.x == x0 and bullet.y == y0:
                    hp0 -= DAMAGE_PER_HIT
                    if trace is not None:
                        trace.events.append(CollisionEvent(0, bullet.owner, TARGET_TANK, 0, x0, y0, hp0))
                elif bullet.x == x1 and bullet.y == y1:
                    hp1 -= DAMAGE_PER_HIT
                    if trace is not None:
                        trace.events.append(CollisionEvent(0, bullet.owner, TARGET_TANK, 1, x1, y1, hp1))
                else:
                    remaining.append(bullet)
            flying = tuple(remaining)

        over = hp0 <= 0 or hp1 <= 0
        bullets = list(flying)

        # 3. Fire. The new bullet starts on the shooter's cell and is not checked there.
        if not over:
            if action0 == _FIRE:
                bullets.append(Bullet(0, x0, y0, facing0))
            if action1 == _FIRE:
                bullets.append(Bullet(1, x1, y1, facing1))

        # 4. Bullets advance cell by cell in lock-step, so neither player is processed first.
        walls_copied = False
        substep = 0
        while substep < BULLET_SPEED and bullets and not over:
            substep += 1
            survivors = []
            frame = [] if trace is not None else None
            wall_hits = []
            for bullet in bullets:
                dx, dy = DELTAS[bullet.direction]
                nx, ny = bullet.x + dx, bullet.y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                moved = Bullet(bullet.owner, nx, ny, bullet.direction)
                if frame is not None:
                    frame.append(moved)
                index = ny * width + nx
                if index in walls:
                    wall_hits.append((index, bullet.owner))
                elif nx == x0 and ny == y0:
                    hp0 -= DAMAGE_PER_HIT
                    if trace is not None:
                        trace.events.append(CollisionEvent(substep, bullet.owner, TARGET_TANK, 0, nx, ny, hp0))
                elif nx == x1 and ny == y1:
                    hp1 -= DAMAGE_PER_HIT
                    if trace is not None:
                        trace.events.append(CollisionEvent(substep, bullet.owner, TARGET_TANK, 1, nx, ny, hp1))
                elif nx == base_x0 and ny == base_y0:
                    base_hp0 -= DAMAGE_PER_HIT
                    if trace is not None:
                        trace.events.append(CollisionEvent(substep, bullet.owner, TARGET_BASE, 0, nx, ny, base_hp0))
                elif nx == base_x1 and ny == base_y1:
                    base_hp1 -= DAMAGE_PER_HIT
                    if trace is not None:
                        trace.events.append(CollisionEvent(substep, bullet.owner, TARGET_BASE, 1, nx, ny, base_hp1))
                else:
                    survivors.append(moved)
            if wall_hits:  # applied after all bullets moved: a wall absorbs every bullet of the sub-step
                if not walls_copied:
                    walls = dict(walls)
                    walls_copied = True
                for index, shooter in wall_hits:
                    old_hp = walls.get(index)
                    new_hp = (old_hp if old_hp is not None else 0) - DAMAGE_PER_HIT
                    if old_hp is not None:
                        walls_key ^= hash((index, old_hp))
                        if new_hp > 0:
                            walls[index] = new_hp
                            walls_key ^= hash((index, new_hp))
                        else:
                            del walls[index]
                    if trace is not None:
                        trace.events.append(CollisionEvent(substep, shooter, TARGET_WALL, None, index % width,
                                                           index // width, max(new_hp, 0)))
            if frame is not None:
                trace.frames.append(frame)
            bullets = survivors
            over = hp0 <= 0 or hp1 <= 0 or base_hp0 <= 0 or base_hp1 <= 0

        # A tank that did not move, turn or take damage keeps its (immutable) object.
        if x0 != old_x0 or y0 != old_y0 or facing0 != tank0.facing or hp0 != tank0.hp:
            tank0 = Tank(0, x0, y0, facing0, hp0)
        if x1 != old_x1 or y1 != old_y1 or facing1 != tank1.facing or hp1 != tank1.hp:
            tank1 = Tank(1, x1, y1, facing1, hp1)
        return GameState(
            width, height,
            (tank0, tank1),
            (base0 if base_hp0 == base0.hp else Base(0, base_x0, base_y0, base_hp0),
             base1 if base_hp1 == base1.hp else Base(1, base_x1, base_y1, base_hp1)),
            walls, tuple(bullets), state.cycle + 1, state.max_cycles, walls_key,
        )

    @staticmethod
    def outcome(state: GameState) -> Optional[int]:
        """TERMINAL-TEST: None while the game goes on; otherwise the winner (0 or 1) or DRAW.

        The winner is whoever still has more operational assets among tank and base. An
        equal count (each lost one in the same sub-step, or the cycle limit) is a draw.
        """
        tank0, tank1 = state.tanks
        base0, base1 = state.bases
        alive0 = (tank0.hp > 0) + (base0.hp > 0)
        alive1 = (tank1.hp > 0) + (base1.hp > 0)
        if alive0 == 2 and alive1 == 2:
            return DRAW if state.cycle >= state.max_cycles else None
        if alive0 == alive1:
            return DRAW
        return 0 if alive0 > alive1 else 1

    @staticmethod
    def utility(state: GameState, player: int) -> int:
        """UTILITY on a terminal state: +1 win, -1 loss, 0 draw. U(s, 0) + U(s, 1) = 0."""
        result = GameRules.outcome(state)
        if result is None:
            raise ValueError("utility is defined only on terminal states")
        if result == DRAW:
            return 0
        return 1 if result == player else -1
