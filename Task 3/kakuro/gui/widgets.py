"""Buttons and segmented choices."""
from __future__ import annotations

from typing import Callable, Sequence, Tuple

import pygame

from .theme import Theme, draw_text


class Button:
    def __init__(self, rect: pygame.Rect, label: str, on_click: Callable[[], None]) -> None:
        self.rect = rect
        self.label = label
        self.on_click = on_click

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.on_click()
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, Theme.CARD_HOVER if hovered else Theme.CARD, self.rect, border_radius=6)
        draw_text(surface, self.label, self.rect.center, 13, center=True)


class Segmented:
    """A row of mutually exclusive choices with a caption on the left."""

    CAPTION_WIDTH = 106

    def __init__(self, rect: pygame.Rect, caption: str, options: Sequence[Tuple[str, str]], selected: int,
                 on_change: Callable[[], None]) -> None:
        self.rect = rect
        self.caption = caption
        self.options = list(options)
        self.selected = selected
        self.on_change = on_change

    @property
    def value(self) -> str:
        return self.options[self.selected][1]

    def _cell(self, index: int) -> pygame.Rect:
        x = self.rect.x + (self.CAPTION_WIDTH if self.caption else 0)
        width = (self.rect.right - x) // len(self.options)
        return pygame.Rect(x + index * width, self.rect.y, width - 3, self.rect.height)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.options)):
                if self._cell(index).collidepoint(event.pos):
                    if index != self.selected:
                        self.selected = index
                        self.on_change()
                    return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if self.caption:
            draw_text(surface, self.caption, (self.rect.x, self.rect.y + 5), 13, Theme.MUTED)
        for index, (label, _) in enumerate(self.options):
            cell = self._cell(index)
            chosen = index == self.selected
            hovered = cell.collidepoint(pygame.mouse.get_pos())
            color = Theme.ACCENT if chosen else (Theme.CARD_HOVER if hovered else Theme.CARD)
            pygame.draw.rect(surface, color, cell, border_radius=5)
            draw_text(surface, label, cell.center, 13, Theme.BACKGROUND if chosen else Theme.TEXT, center=True)
