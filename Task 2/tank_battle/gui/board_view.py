"""Draws the battlefield in the style of the 8-bit arcade tank games, with overlays that show the AI's thinking."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pygame

from ..model import BASE_HP, DELTAS, TANK_HP, WALL_HP, Direction, GameState
from ..rules import TARGET_BASE, TARGET_TANK, TARGET_WALL, CollisionEvent, StepTrace
from .constants import BOARD_PIXELS
from .retro import SPRITE_SIZE, Sprites, draw_frame, draw_pixel_text, pixel_text
from .theme import Color, Theme, draw_pips, draw_text

# Rotation of a sprite drawn facing up, by direction; pygame rotates anticlockwise.
_ANGLE = {int(Direction.UP): 0, int(Direction.DOWN): 180, int(Direction.LEFT): 90, int(Direction.RIGHT): -90}
_BLAST_SECONDS = 0.07  # time one frame of an explosion stays on screen


class Effects:
    """Short-lived feedback: explosions, built from the frames of the sprite sheet, and floating damage numbers."""

    def __init__(self, sprites: Sprites) -> None:
        self._sprites = sprites
        self._blasts: List[List[object]] = []   # x, y, big, age
        self._labels: List[List[object]] = []   # x, y, text, color, age

    def clear(self) -> None:
        self._blasts.clear()
        self._labels.clear()

    def blast(self, center: Tuple[int, int], big: bool = False) -> None:
        self._blasts.append([center[0], center[1], big, 0.0])

    def burst(self, center: Tuple[int, int], color: Color, count: int, speed: float, life: float = 0.45) -> None:
        """Kept for callers that think in particles: a large count is a big explosion, a small one a spark."""
        if count > 6:
            self.blast(center, big=count >= 30)

    def label(self, center: Tuple[int, int], text: str, color: Color) -> None:
        self._labels.append([center[0], center[1] - 8, text, color, 0.0])

    def update(self, seconds: float) -> None:
        for blast in self._blasts:
            blast[3] += seconds
        self._blasts = [b for b in self._blasts
                        if b[3] < _BLAST_SECONDS * Sprites.blast_frames(bool(b[2]))]
        for item in self._labels:
            item[1] -= 34 * seconds
            item[4] += seconds
        self._labels = [item for item in self._labels if item[4] < 0.8]

    def draw(self, surface: pygame.Surface) -> None:
        for x, y, big, age in self._blasts:
            image = self._sprites.blast(int(age / _BLAST_SECONDS), bool(big))
            surface.blit(image, image.get_rect(center=(int(x), int(y))))
        for x, y, text, color, _ in self._labels:
            draw_pixel_text(surface, str(text), (int(x), int(y)), 3, color, center=True, shadow=(0, 0, 0))


class BoardView:
    """Turns game states into pictures. Sprites are drawn once and reused, to keep 60 frames/s."""

    def __init__(self, origin: Tuple[int, int], width: int, height: int) -> None:
        # Whole-number enlargement keeps every game pixel a sharp square.
        scale = max(1, BOARD_PIXELS // (SPRITE_SIZE * max(width, height)))
        self.sprites = Sprites(scale)
        self.cell = self.sprites.size
        self.width, self.height = width, height
        self.arena = pygame.Rect(origin, (BOARD_PIXELS, BOARD_PIXELS))
        self.origin = (origin[0] + (BOARD_PIXELS - self.cell * width) // 2,
                       origin[1] + (BOARD_PIXELS - self.cell * height) // 2)
        self.field = pygame.Rect(self.origin, (self.cell * width, self.cell * height))
        self.effects = Effects(self.sprites)
        self._ground = self._render_ground()

    # ---------------------------------------------------------------- coordinates
    def center(self, x: float, y: float) -> Tuple[int, int]:
        return (int(self.origin[0] + (x + 0.5) * self.cell), int(self.origin[1] + (y + 0.5) * self.cell))

    def cell_rect(self, x: float, y: float) -> pygame.Rect:
        return pygame.Rect(int(self.origin[0] + x * self.cell), int(self.origin[1] + y * self.cell), self.cell, self.cell)

    # -------------------------------------------------------------------- sprites
    def _render_ground(self) -> pygame.Surface:
        """The black field with a faint dot at each tile corner, so that tiles can still be counted."""
        image = pygame.Surface(self.field.size)
        for y in range(self.height + 1):
            for x in range(self.width + 1):
                pygame.draw.rect(image, (30, 30, 30), (min(x * self.cell, self.field.width - 2),
                                                       min(y * self.cell, self.field.height - 2), 2, 2))
        return image

    # -------------------------------------------------------------------- pieces
    def draw_ground(self, surface: pygame.Surface) -> None:
        draw_frame(surface, self.arena, self.field)
        surface.blit(self._ground, self.field.topleft)

    def draw_wall(self, surface: pygame.Surface, x: int, y: int, hp: int) -> None:
        surface.blit(self.sprites.bricks(max(1, min(hp, WALL_HP))), self.cell_rect(x, y))

    def draw_base(self, surface: pygame.Surface, owner: int, x: int, y: int, hp: int) -> None:
        """The eagle, with a strip of blocks under it: one per hit point."""
        rect = self.cell_rect(x, y)
        surface.blit(self.sprites.eagle(owner, hp > 0), rect)
        strip = pygame.Rect(rect.x + 3, rect.bottom - 7, rect.width - 6, 4)
        pygame.draw.rect(surface, (0, 0, 0), strip.inflate(2, 2))
        draw_pips(surface, strip, hp, BASE_HP, Theme.PLAYERS[owner])

    def draw_tank(self, surface: pygame.Surface, owner: int, x: float, y: float, facing: int, hp: int,
                  angle: Optional[int] = None, frame: int = 0) -> None:
        center = self.center(x, y)
        image = self.sprites.tank(owner, _ANGLE[facing] if angle is None else angle, frame)
        surface.blit(image, image.get_rect(center=center))
        size = int(self.cell * 0.72)
        bar = pygame.Rect(center[0] - size // 2, center[1] - self.cell // 2 - 1, size, max(3, self.cell // 12))
        draw_pips(surface, bar, hp, TANK_HP, Theme.GOOD if hp > TANK_HP // 3 else Theme.BAD)

    def draw_bullet(self, surface: pygame.Surface, owner: int, x: float, y: float, direction: int) -> None:
        image = self.sprites.bullet(owner, _ANGLE[direction])
        surface.blit(image, image.get_rect(center=self.center(x, y)))

    # ------------------------------------------------------------------ whole board
    def draw_state(self, surface: pygame.Surface, state: GameState) -> None:
        self.draw_ground(surface)
        for wall in state.wall_list():
            self.draw_wall(surface, wall.x, wall.y, wall.hp)
        for base in state.bases:
            self.draw_base(surface, base.owner, base.x, base.y, max(base.hp, 0))
        for tank in state.tanks:
            self.draw_tank(surface, tank.owner, tank.x, tank.y, tank.facing, max(tank.hp, 0))
        for bullet in state.bullets:
            self.draw_bullet(surface, bullet.owner, bullet.x, bullet.y, bullet.direction)
        self.effects.draw(surface)

    @staticmethod
    def _flight(progress: float, trace: StepTrace) -> float:
        """Sub-steps of bullet flight completed: bullets fly in the last two thirds of a cycle."""
        return max(0.0, progress * 1.5 - 0.5) * len(trace.frames)

    def events_reached(self, trace: StepTrace, progress: float) -> List[CollisionEvent]:
        flight = self._flight(progress, trace)
        return [e for e in trace.events if e.substep == 0 or e.substep - 1 < flight or progress >= 1.0]

    def draw_animated(self, surface: pygame.Surface, before: GameState, after: GameState,
                      trace: StepTrace, progress: float) -> None:
        """A frame inside a cycle. Tanks move in the first third; bullets fly cell by cell;
        HP drops at the moment each collision happens rather than at the end of the cycle."""
        move = min(1.0, progress * 3)
        flight = self._flight(progress, trace)
        substep = min(int(flight), len(trace.frames) - 1) if trace.frames else -1
        within = flight - substep if trace.frames else 0.0

        walls = dict(before.walls)
        tank_hp = [before.tanks[0].hp, before.tanks[1].hp]
        base_hp = [before.bases[0].hp, before.bases[1].hp]
        for event in self.events_reached(trace, progress):
            if event.target == TARGET_WALL:
                index = event.y * before.width + event.x
                if event.hp_after > 0:
                    walls[index] = event.hp_after
                else:
                    walls.pop(index, None)
            elif event.target == TARGET_TANK:
                tank_hp[event.target_owner] = event.hp_after
            elif event.target == TARGET_BASE:
                base_hp[event.target_owner] = event.hp_after

        self.draw_ground(surface)
        for index, hp in walls.items():
            self.draw_wall(surface, index % before.width, index // before.width, hp)
        for base in before.bases:
            self.draw_base(surface, base.owner, base.x, base.y, max(base_hp[base.owner], 0))
        for old, new in zip(before.tanks, after.tanks):
            x, y = self.tank_position(before, after, new.owner, progress)
            moving = (old.x, old.y) != (new.x, new.y) and move < 1.0
            self.draw_tank(surface, new.owner, x, y, new.facing, max(tank_hp[new.owner], 0),
                           self._turn_angle(old.facing, new.facing, move), int(move * 6) % 2 if moving else 0)

        if move < 1.0 or not trace.frames:
            for bullet in before.bullets:
                self.draw_bullet(surface, bullet.owner, bullet.x, bullet.y, bullet.direction)
        else:
            step = min(1.0, within)
            for bullet in trace.frames[substep]:
                dx, dy = DELTAS[bullet.direction]
                self.draw_bullet(surface, bullet.owner, bullet.x - dx * (1 - step), bullet.y - dy * (1 - step),
                                 bullet.direction)
        self.effects.draw(surface)

    @staticmethod
    def tank_position(before: GameState, after: GameState, owner: int, progress: float) -> Tuple[float, float]:
        """Where a tank is drawn inside a cycle: it drives during the first third."""
        move = min(1.0, progress * 3)
        old, new = before.tanks[owner], after.tanks[owner]
        return old.x + (new.x - old.x) * move, old.y + (new.y - old.y) * move

    def draw_player_marker(self, surface: pygame.Surface, owner: int, x: float, y: float, label: str,
                           brackets: bool) -> None:
        """Marks the tank a person drives: a tag above it and, when it is their turn, corner brackets."""
        rect = self.cell_rect(x, y)
        scale = 2 if self.cell >= 40 else 1
        tag = pixel_text(label, scale, Theme.PLAYERS[owner])
        box = tag.get_rect().inflate(4 * scale, 4 * scale)
        box.midbottom = (rect.centerx, rect.y - 3)
        if box.y < self.field.y:  # no room above the top row: put the tag under the tank
            box.midtop = (rect.centerx, rect.bottom + 3)
        pygame.draw.rect(surface, (0, 0, 0), box)
        pygame.draw.rect(surface, Theme.PLAYERS[owner], box, 1)
        surface.blit(tag, tag.get_rect(center=box.center))
        if brackets:
            frame = rect.inflate(6, 6)
            arm = max(6, self.cell // 4)
            color = Theme.PLAYERS_LIGHT[owner]
            for corner, (dx, dy) in ((frame.topleft, (1, 1)), (frame.topright, (-1, 1)),
                                     (frame.bottomleft, (1, -1)), (frame.bottomright, (-1, -1))):
                cx, cy = corner[0] - (dx < 0), corner[1] - (dy < 0)
                pygame.draw.line(surface, color, (cx, cy), (cx + dx * arm, cy), 3)
                pygame.draw.line(surface, color, (cx, cy), (cx, cy + dy * arm), 3)

    def draw_banner(self, surface: pygame.Surface, text: str, color: Color, shade: bool = True) -> None:
        """Large pixel text across the middle of the field, as the arcade game shows PAUSE."""
        if shade:
            veil = pygame.Surface(self.field.size, pygame.SRCALPHA)
            veil.fill((0, 0, 0, 120))
            surface.blit(veil, self.field.topleft)
        scale = max(3, min(7, self.field.width // (len(text) * 6 * 2)))
        draw_pixel_text(surface, text, self.field.center, scale, color, center=True, shadow=(40, 8, 0))

    @staticmethod
    def _turn_angle(old: int, new: int, progress: float) -> int:
        """A pixel sprite cannot turn smoothly: it snaps to its new facing half way through the move."""
        return _ANGLE[new if progress >= 0.5 or old == new else old] % 360

    def play_event(self, event: CollisionEvent) -> None:
        """Effects for one collision, at the moment the animation reaches it."""
        center = self.center(event.x, event.y)
        if event.target == TARGET_WALL:
            self.effects.blast(center, big=False)
            return
        self.effects.blast(center, big=bool(event.destroyed))
        self.effects.label(center, "-1", Theme.BAD)

    # ------------------------------------------------------------------- overlays
    def draw_fire_lines(self, surface: pygame.Surface, state: GameState) -> None:
        """Where each tank's next shot would go, up to the first thing it would hit."""
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for tank in state.tanks:
            dx, dy = DELTAS[tank.facing]
            x, y = tank.x + dx, tank.y + dy
            while state.in_bounds(x, y):
                occupied = (state.cell(x, y) in state.walls
                            or any((b.x, b.y) == (x, y) for b in state.bases)
                            or any((t.x, t.y) == (x, y) for t in state.tanks))
                cx, cy = self.center(x, y)
                pygame.draw.circle(overlay, (*Theme.PLAYERS[tank.owner], 95), (cx, cy), max(2, self.cell // 14))
                if occupied:
                    break
                x, y = x + dx, y + dy
        surface.blit(overlay, (0, 0))

    def draw_plan(self, surface: pygame.Surface, owner: int, start: Tuple[int, int], plan: Sequence[Tuple[int, int]]) -> None:
        """The moves the search expects from this tank: the line it is thinking along."""
        if not plan:
            return
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        points = [self.center(*start)] + [self.center(*cell) for cell in plan]
        for index, (a, b) in enumerate(zip(points, points[1:])):
            alpha = max(60, 210 - index * 28)
            if a != b:
                pygame.draw.line(overlay, (*Theme.PLAYERS_LIGHT[owner], alpha), a, b, 3)
            pygame.draw.circle(overlay, (*Theme.PLAYERS_LIGHT[owner], alpha), b, max(3, self.cell // 10))
        surface.blit(overlay, (0, 0))

    def draw_effort(self, surface: pygame.Surface, effort: Sequence[int], owner: int) -> None:
        """How far each cell is from a shot at the target, as a single-hue scale plus the number."""
        reachable = [value for value in effort if value < self.width * self.height]
        top = max(reachable) if reachable else 1
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        font_size = max(10, self.cell // 3)
        for y in range(self.height):
            for x in range(self.width):
                value = effort[y * self.width + x]
                if value >= self.width * self.height:
                    continue
                strength = 1.0 - value / max(top, 1)
                rect = self.cell_rect(x, y).inflate(-2, -2)
                pygame.draw.rect(overlay, (*Theme.PLAYERS[owner], int(26 + 140 * strength)), rect, border_radius=3)
                draw_text(overlay, str(value), rect.center, font_size, Theme.TEXT, center=True)
        surface.blit(overlay, (0, 0))
