"""Line chart of the attacking pairs after every Min-Conflicts step, with the current step marked.

Clicking or dragging on it moves the replay to that step.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import pygame
import pygame.gfxdraw

from .replay import MinConflictsPlayer
from .service import plural
from .theme import Palette, dashed_line, draw_text

LINE = Palette.SERIES[0]


class Timeline:
    MAX_RESTART_MARKS = 12

    def __init__(self) -> None:
        self.rect = pygame.Rect(0, 0, 0, 0)  # the plot itself; value labels go left of it
        self._cache_key: Optional[Tuple[int, int]] = None
        self._points: List[Tuple[int, int]] = []
        self._spans: List[Tuple[int, int, int]] = []  # (x, top y, bottom y) where frames share a pixel

    def set_rect(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self._cache_key = None

    def hit_rect(self) -> pygame.Rect:
        return self.rect.inflate(8, 12)

    def frame_at(self, x: int, player: MinConflictsPlayer) -> int:
        fraction = (x - self.rect.x) / max(1, self.rect.w - 1)
        return round(min(1.0, max(0.0, fraction)) * max(1, player.frame_count - 1))

    def _x(self, frame: int, player: MinConflictsPlayer) -> int:
        return self.rect.x + round(frame / max(1, player.frame_count - 1) * (self.rect.w - 1))

    def _y(self, value: int, top: int) -> int:
        return self.rect.bottom - 1 - round(value / top * (self.rect.h - 4))

    def _build(self, player: MinConflictsPlayer, top: int) -> None:
        """Points of the line; when several frames share a pixel column, their min-max span."""
        self._points, self._spans = [], []
        frames, width = player.frame_count, self.rect.w
        if frames <= width:
            self._points = [(self._x(f, player), self._y(v, top)) for f, v in enumerate(player.pairs)]
            return
        for column in range(width):
            first, last = column * frames // width, max(column * frames // width + 1, (column + 1) * frames // width)
            values = player.pairs[first:last]
            x = self.rect.x + column
            self._points.append((x, self._y(values[0], top)))
            low, high = min(values), max(values)
            if high > low:
                self._spans.append((x, self._y(high, top), self._y(low, top)))

    def draw(self, surface: pygame.Surface, player: MinConflictsPlayer, mouse: Tuple[int, int]) -> None:
        top = max(1, player.max_pairs)
        key = (id(player), self.rect.w)
        if key != self._cache_key:
            self._build(player, top)
            self._cache_key = key
        rect = self.rect
        # Recessive axes: a baseline, a dashed line at the maximum and their two values.
        pygame.draw.line(surface, Palette.BORDER, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1))
        dashed_line(surface, Palette.BORDER, (rect.x, self._y(top, top)), (rect.right, self._y(top, top)))
        draw_text(surface, "0", (rect.x - 6, rect.bottom - 1), 11, Palette.MUTED, anchor="midright")
        draw_text(surface, str(top), (rect.x - 6, self._y(top, top)), 11, Palette.MUTED, anchor="midright")
        if len(player.starts) <= self.MAX_RESTART_MARKS:  # restarts; too many would only add noise
            for start in player.starts[1:]:
                x = self._x(start, player)
                dashed_line(surface, Palette.FAINT, (x, rect.y), (x, rect.bottom))

        for x, high, low in self._spans:
            pygame.draw.line(surface, LINE, (x, high), (x, low), 1)
        if len(self._points) > 1:
            pygame.draw.lines(surface, LINE, False, self._points, 2)
        elif self._points:
            pygame.draw.circle(surface, LINE, self._points[0], 3)

        if self.hit_rect().collidepoint(mouse):  # crosshair; its value is shown by hover_label()
            frame = self.frame_at(mouse[0], player)
            x, y = self._x(frame, player), self._y(player.pairs[frame], top)
            pygame.draw.line(surface, Palette.FAINT, (x, rect.y), (x, rect.bottom - 1))
            pygame.gfxdraw.aacircle(surface, x, y, 4, Palette.MUTED)

        # Playhead: the current frame, a marker with a ring of the card colour.
        x = self._x(player.frame, player)
        y = self._y(player.attacking_pairs, top)
        pygame.draw.line(surface, Palette.TEXT, (x, rect.y), (x, rect.bottom - 1))
        pygame.gfxdraw.filled_circle(surface, x, y, 6, Palette.CARD)
        pygame.gfxdraw.aacircle(surface, x, y, 4, LINE)
        pygame.gfxdraw.filled_circle(surface, x, y, 4, LINE)

    def hover_label(self, player: MinConflictsPlayer, mouse: Tuple[int, int]) -> Optional[str]:
        """The value under the mouse, for the card header (a floating box would hide the title)."""
        if not self.hit_rect().collidepoint(mouse):
            return None
        frame = self.frame_at(mouse[0], player)
        attempt, step = player.locate(frame)
        label = f"step {step:,}: {plural(player.pairs[frame], 'attacking pair')}"
        return f"run {attempt + 1}, {label}" if len(player.attempts) > 1 else label
