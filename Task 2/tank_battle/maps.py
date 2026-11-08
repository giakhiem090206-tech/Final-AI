"""Battlefields written as ASCII art.

    .  empty     #  wall
    A  tank of player 1     a  base of player 1
    B  tank of player 2     b  base of player 2

Every map is identical after a half-turn that swaps the players, so neither side
starts with a positional advantage (tests/test_maps.py checks this).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .model import BASE_HP, DEFAULT_MAX_CYCLES, TANK_HP, WALL_HP, Base, Direction, GameState, Tank


@dataclass(frozen=True)
class GameMap:
    name: str
    rows: Tuple[str, ...]

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    def _find(self, symbol: str) -> Tuple[int, int]:
        cells = [(x, y) for y, row in enumerate(self.rows) for x, ch in enumerate(row) if ch == symbol]
        if len(cells) != 1:
            raise ValueError(f"map '{self.name}' must contain exactly one '{symbol}', found {len(cells)}")
        return cells[0]

    def create_state(self, max_cycles: int = DEFAULT_MAX_CYCLES) -> GameState:
        """Initial state. Player 1 (index 0) starts facing up, player 2 (index 1) facing down."""
        if any(len(row) != self.width for row in self.rows):
            raise ValueError(f"map '{self.name}' has rows of different lengths")
        unknown = set("".join(self.rows)) - set(".#AaBb")
        if unknown:
            raise ValueError(f"map '{self.name}' has unknown symbols: {sorted(unknown)}")
        ax, ay = self._find("A")
        bx, by = self._find("B")
        base_ax, base_ay = self._find("a")
        base_bx, base_by = self._find("b")
        walls = {
            y * self.width + x: WALL_HP
            for y, row in enumerate(self.rows) for x, ch in enumerate(row) if ch == "#"
        }
        return GameState(
            self.width, self.height,
            (Tank(0, ax, ay, int(Direction.UP), TANK_HP), Tank(1, bx, by, int(Direction.DOWN), TANK_HP)),
            (Base(0, base_ax, base_ay, BASE_HP), Base(1, base_bx, base_by, BASE_HP)),
            walls, (), 0, max_cycles,
        )

    @classmethod
    def from_file(cls, path: str, name: Optional[str] = None) -> "GameMap":
        with open(path, encoding="utf-8") as handle:
            rows = tuple(line.strip() for line in handle if line.strip())
        return cls(name or path, rows)


BUILTIN_MAPS: Dict[str, GameMap] = {
    game_map.name: game_map for game_map in (
        GameMap("Crossroads", (
            "....##b##....",
            ".............",
            "..##..B..##..",
            "..#.......#..",
            "....##.##....",
            ".#.........#.",
            ".#...###...#.",
            ".#.........#.",
            "....##.##....",
            "..#.......#..",
            "..##..A..##..",
            ".............",
            "....##a##....",
        )),
        GameMap("Fortress", (
            ".....#b#.....",
            ".....###.....",
            "..B..........",
            ".##.#...#.##.",
            ".....#.#.....",
            ".#.#.....#.#.",
            "...#..#..#...",
            ".#.#.....#.#.",
            ".....#.#.....",
            ".##.#...#.##.",
            "..........A..",
            ".....###.....",
            ".....#a#.....",
        )),
        GameMap("Corridors", (
            "......b......",
            ".###.###.###.",
            "...#.....#...",
            ".#.#.###.#.#.",
            ".#.B.....#.#.",
            ".#.###.###.#.",
            ".............",
            ".#.###.###.#.",
            ".#.#.....A.#.",
            ".#.#.###.#.#.",
            "...#.....#...",
            ".###.###.###.",
            "......a......",
        )),
        GameMap("Bunkers", (
            "....b....",
            ".##.#.##.",
            ".........",
            "..#...#..",
            ".B..#..A.",
            "..#...#..",
            ".........",
            ".##.#.##.",
            "....a....",
        )),
        GameMap("Duel", (
            "...b...",
            ".......",
            ".B.#...",
            "..#.#..",
            "...#.A.",
            ".......",
            "...a...",
        )),
        GameMap("Islands", (
            ".....b.....",
            ".#.#.#.#.#.",
            "...........",
            "..##...##..",
            ".....#.....",
            ".B.#...#.A.",
            ".....#.....",
            "..##...##..",
            "...........",
            ".#.#.#.#.#.",
            ".....a.....",
        )),
        GameMap("Diagonal", (
            "b..#.........",
            ".#.#.###.###.",
            ".#...#.......",
            ".###.#.##.##.",
            ".....#..#....",
            ".B##...#..##.",
            ".....#.#.....",
            ".##..#...##A.",
            "....#..#.....",
            ".##.##.#.###.",
            ".......#...#.",
            ".###.###.#.#.",
            ".........#..a",
        )),
    )
}


def map_names() -> List[str]:
    return list(BUILTIN_MAPS)


def random_map(seed: int) -> GameMap:
    """A random fair map: bases, tanks and walls are placed with half-turn symmetry.

    Tuning on a handful of fixed maps learns those maps, so tuning and testing use many
    random maps drawn from separate seeds. Walls can be shot away, so any layout is playable.
    """
    rng = random.Random(f"map-{seed}")
    size = rng.choice((9, 11, 13))
    density = rng.uniform(0.1, 0.38)
    last = size - 1
    cells = [["."] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            if (y, x) <= (last - y, last - x) and rng.random() < density:
                cells[y][x] = cells[last - y][last - x] = "#"

    base_x, base_y = rng.randrange(size), rng.randrange(max(1, size // 4))
    while True:
        tank_x, tank_y = rng.randrange(size), rng.randrange(size // 2)
        if (tank_x, tank_y) != (base_x, base_y):
            break
    cells[base_y][base_x] = "b"
    cells[last - base_y][last - base_x] = "a"
    cells[tank_y][tank_x] = "B"
    cells[last - tank_y][last - tank_x] = "A"
    return GameMap(f"Random {seed}", tuple("".join(row) for row in cells))


def is_point_symmetric(rows: Sequence[str]) -> bool:
    """True when a half-turn plus swapping the players leaves the map unchanged."""
    swap = str.maketrans("AaBb", "BbAa")
    return list(rows) == [row[::-1].translate(swap) for row in reversed(rows)]
