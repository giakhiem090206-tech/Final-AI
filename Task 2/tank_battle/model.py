"""Game vocabulary and state. Entities are immutable values and a state is never edited in
place, which is what lets the search explore thousands of futures cheaply."""
from __future__ import annotations

from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Tuple

TANK_HP = 6
BASE_HP = 9
WALL_HP = 3
DAMAGE_PER_HIT = 1
BULLET_SPEED = 3
DEFAULT_MAX_CYCLES = 300
DRAW = -1


class Direction(IntEnum):
    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3


# Indexed by Direction. Actions 0-3 share these indices, so a move action is also its direction.
DELTAS: Tuple[Tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))


class Action(IntEnum):
    MOVE_UP = 0
    MOVE_DOWN = 1
    MOVE_LEFT = 2
    MOVE_RIGHT = 3
    FIRE = 4
    STAY = 5

    @classmethod
    def parse(cls, value: object) -> Optional["Action"]:
        """Read an action from an Action, its name or its number; None if it is none of these."""
        if isinstance(value, Action):
            return value
        if isinstance(value, str):
            return cls.__members__.get(value.strip().upper())
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 5:
            return cls(value)
        return None


ALL_ACTIONS: Tuple[Action, ...] = tuple(Action)
_MOVE_ACTIONS = (Action.MOVE_UP, Action.MOVE_DOWN, Action.MOVE_LEFT, Action.MOVE_RIGHT)


class Tank(NamedTuple):
    owner: int
    x: int
    y: int
    facing: int
    hp: int


class Base(NamedTuple):
    owner: int
    x: int
    y: int
    hp: int


class Bullet(NamedTuple):
    owner: int
    x: int
    y: int
    direction: int


class Wall(NamedTuple):
    x: int
    y: int
    hp: int


class GameState:
    """Complete, fully observable game state s.

    `walls` maps cell index (y * width + x) to remaining HP. States share that dictionary
    and it is copied only when a wall is damaged, so it must be treated as read-only.
    `walls_key` is an incremental hash of `walls`, used to recognise repeated states.
    """

    __slots__ = ("width", "height", "tanks", "bases", "walls", "bullets", "cycle",
                 "max_cycles", "walls_key")

    def __init__(self, width: int, height: int, tanks: Tuple[Tank, Tank], bases: Tuple[Base, Base],
                 walls: Dict[int, int], bullets: Tuple[Bullet, ...] = (), cycle: int = 0,
                 max_cycles: int = DEFAULT_MAX_CYCLES, walls_key: Optional[int] = None) -> None:
        self.width = width
        self.height = height
        self.tanks = tanks
        self.bases = bases
        self.walls = walls
        self.bullets = bullets
        self.cycle = cycle
        self.max_cycles = max_cycles
        self.walls_key = self.hash_walls(walls) if walls_key is None else walls_key

    @staticmethod
    def hash_walls(walls: Dict[int, int]) -> int:
        key = 0
        for item in walls.items():
            key ^= hash(item)
        return key

    def cell(self, x: int, y: int) -> int:
        return y * self.width + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def wall_list(self) -> List[Wall]:
        return [Wall(index % self.width, index // self.width, hp) for index, hp in self.walls.items()]

    def clone(self) -> "GameState":
        """A copy that outside code can damage without affecting the real game."""
        return GameState(self.width, self.height, self.tanks, self.bases, dict(self.walls),
                         self.bullets, self.cycle, self.max_cycles, self.walls_key)

    def replace(self, **changes: object) -> "GameState":
        """A copy with some fields changed; used to set up test positions and scenarios."""
        fields = {name: getattr(self, name) for name in self.__slots__ if name != "walls_key"}
        fields.update(changes)
        return GameState(**fields)  # type: ignore[arg-type]

    def key(self) -> tuple:
        """Hashable identity of the state, used by the transposition table."""
        return (self.tanks, self.bases[0].hp, self.bases[1].hp, self.bullets, self.walls_key, self.cycle)

    def to_observation(self, player: int) -> dict:
        """The state as plain data, so other groups' code need not know these classes."""

        def tank(t: Tank) -> dict:
            return {"x": t.x, "y": t.y, "facing": Direction(t.facing).name, "hp": t.hp}

        def base(b: Base) -> dict:
            return {"x": b.x, "y": b.y, "hp": b.hp}

        opponent = 1 - player
        return {
            "player": player,
            "width": self.width,
            "height": self.height,
            "cycle": self.cycle,
            "max_cycles": self.max_cycles,
            "my_tank": tank(self.tanks[player]),
            "enemy_tank": tank(self.tanks[opponent]),
            "my_base": base(self.bases[player]),
            "enemy_base": base(self.bases[opponent]),
            "walls": [{"x": w.x, "y": w.y, "hp": w.hp} for w in self.wall_list()],
            "bullets": [
                {"x": b.x, "y": b.y, "direction": Direction(b.direction).name,
                 "mine": b.owner == player}
                for b in self.bullets
            ],
        }
