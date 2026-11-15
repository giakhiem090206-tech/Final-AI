"""Buttons, steppers, radio buttons and a segmented control.

Icons are drawn from shapes instead of symbol characters, so they look the same on
every platform, whatever fonts are installed.
"""
from __future__ import annotations

from typing import Callable, Sequence, Tuple

import pygame
import pygame.gfxdraw

from .theme import Palette, draw_text, fit_text


def _triangle(surface: pygame.Surface, color, points) -> None:
    points = [(round(x), round(y)) for x, y in points]
    pygame.gfxdraw.aapolygon(surface, points, color)
    pygame.gfxdraw.filled_polygon(surface, points, color)


def draw_icon(surface: pygame.Surface, name: str, rect: pygame.Rect, color) -> None:
    cx, cy = rect.center
    s = max(4, min(rect.w, rect.h) // 4)  # half the height of the glyph
    if name == "play":
        _triangle(surface, color, [(cx - s * 0.7, cy - s), (cx - s * 0.7, cy + s), (cx + s, cy)])
    elif name == "pause":
        bar = max(2, round(s * 0.55))
        pygame.draw.rect(surface, color, (cx - bar - 2, cy - s, bar, 2 * s + 1))
        pygame.draw.rect(surface, color, (cx + 2, cy - s, bar, 2 * s + 1))
    elif name in ("prev", "next"):
        d = 1 if name == "next" else -1
        _triangle(surface, color, [(cx - d * s * 0.6, cy - s), (cx - d * s * 0.6, cy + s), (cx + d * s * 0.8, cy)])
    elif name in ("first", "last"):
        d = 1 if name == "last" else -1
        _triangle(surface, color, [(cx - d * s, cy - s), (cx - d * s, cy + s), (cx + d * s * 0.5, cy)])
        bar_x = cx + d * s * 0.6 - (0 if d > 0 else 2)
        pygame.draw.rect(surface, color, (round(bar_x), cy - s, 2, 2 * s + 1))
    elif name in ("minus", "plus"):
        pygame.draw.rect(surface, color, (cx - s, cy - 1, 2 * s + 1, 2))
        if name == "plus":
            pygame.draw.rect(surface, color, (cx - 1, cy - s, 2, 2 * s + 1))


class Button:
    """A clickable rectangle with a label or an icon. `primary` buttons are filled."""

    def __init__(self, on_click: Callable[[], None], label: str = "", icon: str = "",
                 primary: bool = False) -> None:
        self.on_click = on_click
        self.label = label
        self.icon = icon
        self.primary = primary
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.enabled = True
        self.visible = True

    def hit(self, position: Tuple[int, int]) -> bool:
        return self.visible and self.enabled and self.rect.collidepoint(position)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hit(event.pos):
            self.on_click()
            return True
        return False

    def draw(self, surface: pygame.Surface, mouse: Tuple[int, int]) -> None:
        if not self.visible:
            return
        hovered = self.enabled and self.rect.collidepoint(mouse)
        if self.primary:
            fill = Palette.DISABLED if not self.enabled else (Palette.ACCENT_HOVER if hovered else Palette.ACCENT)
            ink, edge = Palette.ON_ACCENT, fill
        else:
            fill = Palette.CONTROL_HOVER if hovered else Palette.CONTROL
            ink, edge = (Palette.TEXT if self.enabled else Palette.FAINT), Palette.BORDER
        pygame.draw.rect(surface, fill, self.rect, border_radius=3)
        pygame.draw.rect(surface, edge, self.rect, 1, border_radius=3)
        if self.icon:
            draw_icon(surface, self.icon, self.rect, ink)
        else:
            label = fit_text(self.label, self.rect.w - 10, 14, bold=self.primary)
            draw_text(surface, label, self.rect.center, 14, ink, bold=self.primary, anchor="center")


class Stepper:
    """[-] value [+]. `on_change` receives -1 or +1."""

    def __init__(self, on_change: Callable[[int], None]) -> None:
        self.minus = Button(lambda: on_change(-1), icon="minus")
        self.plus = Button(lambda: on_change(+1), icon="plus")
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.text = ""
        self.visible = True

    def set_rect(self, rect: pygame.Rect) -> None:
        self.rect = rect
        side = rect.h
        self.minus.rect = pygame.Rect(rect.x, rect.y, side, side)
        self.plus.rect = pygame.Rect(rect.right - side, rect.y, side, side)

    def hit(self, position: Tuple[int, int]) -> bool:
        return self.visible and (self.minus.hit(position) or self.plus.hit(position))

    def handle(self, event: pygame.event.Event) -> bool:
        return self.visible and (self.minus.handle(event) or self.plus.handle(event))

    def draw(self, surface: pygame.Surface, mouse: Tuple[int, int]) -> None:
        if not self.visible:
            return
        middle = pygame.Rect(self.minus.rect.right - 1, self.rect.y, self.plus.rect.x - self.minus.rect.right + 2,
                             self.rect.h)
        pygame.draw.rect(surface, Palette.CARD, middle)
        pygame.draw.rect(surface, Palette.BORDER, middle, 1)
        self.minus.draw(surface, mouse)
        self.plus.draw(surface, mouse)
        draw_text(surface, fit_text(self.text, middle.w - 4, 14), middle.center, 14, Palette.TEXT, anchor="center")


class RadioGroup:
    """Mutually exclusive choices, one plain radio button per line."""

    def __init__(self, labels: Sequence[str], on_select: Callable[[int], None]) -> None:
        self.labels = list(labels)
        self.on_select = on_select
        self.selected = 0
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.item_height = 26

    @property
    def height(self) -> int:
        return len(self.labels) * self.item_height

    def item_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(self.rect.x, self.rect.y + index * self.item_height, self.rect.w, self.item_height)

    def hit(self, position: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.labels)):
                if self.item_rect(index).collidepoint(event.pos):
                    self.on_select(index)
                    return True
        return False

    def draw(self, surface: pygame.Surface, mouse: Tuple[int, int]) -> None:
        for index, label in enumerate(self.labels):
            rect = self.item_rect(index)
            cx, cy = rect.x + 8, rect.centery
            ring = Palette.ACCENT if rect.collidepoint(mouse) else Palette.MUTED
            pygame.gfxdraw.aacircle(surface, cx, cy, 7, ring)
            pygame.gfxdraw.filled_circle(surface, cx, cy, 6, Palette.CARD)
            pygame.gfxdraw.aacircle(surface, cx, cy, 7, ring)
            if index == self.selected:
                pygame.gfxdraw.aacircle(surface, cx, cy, 4, Palette.ACCENT)
                pygame.gfxdraw.filled_circle(surface, cx, cy, 4, Palette.ACCENT)
            draw_text(surface, fit_text(label, rect.w - 24, 14), (rect.x + 22, cy), 14, Palette.TEXT, anchor="midleft")


class Segmented:
    """A row of mutually exclusive short choices."""

    def __init__(self, labels: Sequence[str], on_select: Callable[[int], None], selected: int = 0) -> None:
        self.labels = list(labels)
        self.on_select = on_select
        self.selected = selected
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.visible = True

    def cell(self, index: int) -> pygame.Rect:
        width = self.rect.w // len(self.labels)
        return pygame.Rect(self.rect.x + index * width, self.rect.y, width, self.rect.h)

    def hit(self, position: Tuple[int, int]) -> bool:
        return self.visible and self.rect.collidepoint(position)

    def handle(self, event: pygame.event.Event) -> bool:
        if self.visible and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.labels)):
                if self.cell(index).collidepoint(event.pos):
                    self.on_select(index)
                    return True
        return False

    def draw(self, surface: pygame.Surface, mouse: Tuple[int, int]) -> None:
        if not self.visible:
            return
        for index, label in enumerate(self.labels):
            cell = self.cell(index)
            chosen = index == self.selected
            fill = Palette.ACCENT if chosen else (Palette.CONTROL_HOVER if cell.collidepoint(mouse) else Palette.CONTROL)
            pygame.draw.rect(surface, fill, cell)
            pygame.draw.rect(surface, Palette.ACCENT if chosen else Palette.BORDER, cell, 1)
            draw_text(surface, label, cell.center, 13, Palette.ON_ACCENT if chosen else Palette.TEXT, anchor="center")
