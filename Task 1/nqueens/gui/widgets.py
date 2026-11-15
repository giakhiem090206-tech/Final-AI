"""Buttons, steppers, an option list and a segmented control.

Icons are drawn from shapes instead of symbol characters, so they look the same on
every platform, whatever fonts are installed.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

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
        pygame.draw.rect(surface, color, (cx - bar - 2, cy - s, bar, 2 * s + 1), border_radius=1)
        pygame.draw.rect(surface, color, (cx + 2, cy - s, bar, 2 * s + 1), border_radius=1)
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

    def __init__(self, on_click: Callable[[], None], label: str = "", icon: Optional[str] = None,
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
            ink = Palette.ON_ACCENT
        else:
            fill = Palette.CONTROL_HOVER if hovered else Palette.CONTROL
            ink = Palette.TEXT if self.enabled else Palette.FAINT
        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        if not self.primary:
            pygame.draw.rect(surface, Palette.BORDER, self.rect, 1, border_radius=8)
        if self.icon:
            draw_icon(surface, self.icon, self.rect, ink)
        else:
            size = 16 if self.primary else 14
            label = fit_text(self.label, self.rect.w - 12, size, bold=True)
            draw_text(surface, label, self.rect.center, size, ink, bold=True, anchor="center")


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
        self.minus.draw(surface, mouse)
        self.plus.draw(surface, mouse)
        middle = pygame.Rect(self.minus.rect.right, self.rect.y, self.plus.rect.x - self.minus.rect.right, self.rect.h)
        draw_text(surface, fit_text(self.text, middle.w - 4, 16, True), middle.center, 16, Palette.TEXT,
                  bold=True, anchor="center")


class OptionList:
    """Mutually exclusive choices stacked vertically, each with a title and a subtitle."""

    def __init__(self, options: Sequence[Tuple[str, str]], on_select: Callable[[int], None]) -> None:
        self.options = list(options)
        self.on_select = on_select
        self.selected = 0
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.item_height = 46
        self.gap = 6
        self.show_subtitles = True

    @property
    def height(self) -> int:
        count = len(self.options)
        return count * self.item_height + (count - 1) * self.gap

    def item_rect(self, index: int) -> pygame.Rect:
        y = self.rect.y + index * (self.item_height + self.gap)
        return pygame.Rect(self.rect.x, y, self.rect.w, self.item_height)

    def hit(self, position: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.options)):
                if self.item_rect(index).collidepoint(event.pos):
                    self.on_select(index)
                    return True
        return False

    def draw(self, surface: pygame.Surface, mouse: Tuple[int, int]) -> None:
        for index, (title, subtitle) in enumerate(self.options):
            rect = self.item_rect(index)
            chosen = index == self.selected
            hovered = rect.collidepoint(mouse)
            fill = Palette.SELECTED if chosen else (Palette.CONTROL_HOVER if hovered else Palette.CONTROL)
            pygame.draw.rect(surface, fill, rect, border_radius=9)
            pygame.draw.rect(surface, Palette.ACCENT if chosen else Palette.BORDER, rect, 2 if chosen else 1,
                             border_radius=9)
            cx, cy = rect.x + 20, rect.centery
            ring = Palette.ACCENT if chosen else Palette.FAINT
            pygame.gfxdraw.aacircle(surface, cx, cy, 8, ring)
            pygame.gfxdraw.aacircle(surface, cx, cy, 7, ring)
            if chosen:
                pygame.gfxdraw.aacircle(surface, cx, cy, 4, Palette.ACCENT)
                pygame.gfxdraw.filled_circle(surface, cx, cy, 4, Palette.ACCENT)
            key = draw_text(surface, str(index + 1), (rect.right - 12, cy), 12, Palette.FAINT, anchor="midright")
            text_x, text_w = rect.x + 38, key.x - rect.x - 46
            if self.show_subtitles:
                draw_text(surface, fit_text(title, text_w, 15, True), (text_x, rect.y + 5), 15, Palette.TEXT, True)
                draw_text(surface, fit_text(subtitle, text_w, 12), (text_x, rect.y + 26), 12, Palette.MUTED)
            else:
                draw_text(surface, fit_text(title, text_w, 15, True), (text_x, cy), 15, Palette.TEXT, True,
                          anchor="midleft")


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
        pygame.draw.rect(surface, Palette.CONTROL, self.rect, border_radius=8)
        pygame.draw.rect(surface, Palette.BORDER, self.rect, 1, border_radius=8)
        for index, label in enumerate(self.labels):
            cell = self.cell(index).inflate(-4, -4)
            chosen = index == self.selected
            if chosen:
                pygame.draw.rect(surface, Palette.ACCENT, cell, border_radius=6)
            elif cell.collidepoint(mouse):
                pygame.draw.rect(surface, Palette.CONTROL_HOVER, cell, border_radius=6)
            draw_text(surface, label, cell.center, 13, Palette.ON_ACCENT if chosen else Palette.TEXT,
                      bold=chosen, anchor="center")
