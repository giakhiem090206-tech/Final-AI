"""Small interface components: buttons, lists, segmented choices and the map picker."""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import pygame

from ..maps import GameMap
from .theme import Color, Fonts, Theme, draw_text, fit_text


class Button:
    def __init__(self, rect: pygame.Rect, label: str, on_click: Callable[[], None], accent: bool = False) -> None:
        self.rect = rect
        self.label = label
        self.on_click = on_click
        self.accent = accent

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.on_click()
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        color = Theme.ACCENT if self.accent else (Theme.CARD_HOVER if hovered else Theme.CARD)
        pygame.draw.rect(surface, color, self.rect, border_radius=7)
        text_color = Theme.BACKGROUND if self.accent else Theme.TEXT
        draw_text(surface, self.label, self.rect.center, 15, text_color, bold=self.accent, center=True)


class OptionList:
    """A titled, scrollable list with one selected item."""

    ROW = 30

    def __init__(self, rect: pygame.Rect, title: str, items: Sequence[str], selected: int = 0,
                 color: Color = Theme.ACCENT, tag_of: Optional[Callable[[str], str]] = None) -> None:
        self.rect = rect
        self.title = title
        self.items = list(items)
        self.selected = min(selected, max(0, len(self.items) - 1))
        self.color = color
        self.tag_of = tag_of or (lambda item: "")  # a short note shown at the right of an item
        self.scroll = 0

    @property
    def value(self) -> str:
        return self.items[self.selected]

    @property
    def _visible(self) -> int:
        return max(1, (self.rect.height - 40) // self.ROW)

    def set_items(self, items: Sequence[str]) -> None:
        current = self.value
        self.items = list(items)
        self.selected = self.items.index(current) if current in self.items else 0
        self.scroll = 0

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            index = self.scroll + (event.pos[1] - self.rect.y - 40) // self.ROW
            if event.pos[1] >= self.rect.y + 40 and 0 <= index < len(self.items):
                self.selected = index
        elif event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            limit = max(0, len(self.items) - self._visible)
            self.scroll = min(limit, max(0, self.scroll - event.y))

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, Theme.PANEL, self.rect, border_radius=10)
        pygame.draw.rect(surface, self.color, (self.rect.x + 12, self.rect.y + 12, 12, 12), border_radius=3)
        draw_text(surface, self.title, (self.rect.x + 30, self.rect.y + 9), 15, Theme.TEXT, bold=True)
        for row, index in enumerate(range(self.scroll, min(len(self.items), self.scroll + self._visible))):
            line = pygame.Rect(self.rect.x + 8, self.rect.y + 40 + row * self.ROW, self.rect.width - 16, self.ROW - 3)
            if index == self.selected:
                pygame.draw.rect(surface, Theme.CARD_HOVER, line, border_radius=6)
                pygame.draw.rect(surface, self.color, (line.x, line.y + 3, 3, line.height - 6), border_radius=2)
            elif line.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(surface, Theme.CARD, line, border_radius=6)
            color = Theme.TEXT if index == self.selected else Theme.MUTED
            tag = self.tag_of(self.items[index])
            tag_width = Fonts.get(11).size(tag)[0] + 12 if tag else 0
            if tag:
                draw_text(surface, tag, (line.right - 8, line.centery - Fonts.get(11).get_height() // 2), 11,
                          Theme.FAINT if index != self.selected else Theme.MUTED, right=True)
            text = fit_text(self.items[index], 14, line.width - 20 - tag_width)
            draw_text(surface, text, (line.x + 10, line.centery - Fonts.get(14).get_height() // 2), 14, color)
        if len(self.items) > self._visible:
            draw_text(surface, "scroll for more", (self.rect.right - 12, self.rect.y + 12), 11, Theme.FAINT, right=True)


class Segmented:
    """A row of mutually exclusive choices with a caption above."""

    def __init__(self, rect: pygame.Rect, caption: str, labels: Sequence[str], selected: int = 0) -> None:
        self.rect = rect
        self.caption = caption
        self.labels = list(labels)
        self.selected = selected

    def _cell(self, index: int) -> pygame.Rect:
        width = self.rect.width // len(self.labels)
        return pygame.Rect(self.rect.x + index * width, self.rect.y + 22, width - 3, self.rect.height - 22)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.labels)):
                if self._cell(index).collidepoint(event.pos):
                    self.selected = index
                    return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        draw_text(surface, self.caption, (self.rect.x, self.rect.y), 13, Theme.MUTED)
        for index, label in enumerate(self.labels):
            cell = self._cell(index)
            chosen = index == self.selected
            hovered = cell.collidepoint(pygame.mouse.get_pos())
            color = Theme.ACCENT if chosen else (Theme.CARD_HOVER if hovered else Theme.CARD)
            pygame.draw.rect(surface, color, cell, border_radius=6)
            draw_text(surface, label, cell.center, 13, Theme.BACKGROUND if chosen else Theme.TEXT, center=True)


class MapPicker:
    """A grid of map thumbnails, so that a map can be chosen by what it looks like."""

    def __init__(self, rect: pygame.Rect, title: str, maps: Sequence[GameMap], selected: int = 0, columns: int = 3) -> None:
        self.rect = rect
        self.title = title
        self.maps = list(maps)
        self.items: List[str] = [game_map.name for game_map in maps]
        self.selected = selected
        self.columns = columns
        self._thumbnails = [self._render(game_map) for game_map in maps]

    @property
    def value(self) -> str:
        return self.items[self.selected]

    @property
    def _tile(self) -> Tuple[int, int]:
        rows = (len(self.items) + self.columns - 1) // self.columns
        return (self.rect.width - 16) // self.columns, (self.rect.height - 42) // rows

    def _cell(self, index: int) -> pygame.Rect:
        row, col = divmod(index, self.columns)
        width, height = self._tile
        return pygame.Rect(self.rect.x + 8 + col * width, self.rect.y + 36 + row * height, width - 4, height - 4)

    def _render(self, game_map: GameMap) -> pygame.Surface:
        width, height = self._tile
        side = min(width - 16, height - 28)
        size = max(1, side // max(game_map.width, game_map.height))
        image = pygame.Surface((size * game_map.width, size * game_map.height))
        image.fill(Theme.GROUND_A)
        colors = {"#": Theme.WALL_FACE[2], "A": Theme.PLAYERS[0], "a": Theme.PLAYERS[0], "B": Theme.PLAYERS[1],
                  "b": Theme.PLAYERS[1]}
        for y, row in enumerate(game_map.rows):
            for x, symbol in enumerate(row):
                if symbol in colors:
                    rect = pygame.Rect(x * size, y * size, size, size)
                    if symbol in "AB":
                        pygame.draw.circle(image, colors[symbol], rect.center, max(1, size // 2))
                    else:
                        pygame.draw.rect(image, colors[symbol], rect)
        return image

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index in range(len(self.maps)):
                if self._cell(index).collidepoint(event.pos):
                    self.selected = index

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, Theme.PANEL, self.rect, border_radius=10)
        draw_text(surface, self.title, (self.rect.x + 12, self.rect.y + 9), 15, Theme.TEXT, bold=True)
        for index, thumbnail in enumerate(self._thumbnails):
            cell = self._cell(index)
            chosen = index == self.selected
            hovered = cell.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, Theme.CARD_HOVER if chosen or hovered else Theme.CARD, cell, border_radius=6)
            if chosen:
                pygame.draw.rect(surface, Theme.ACCENT, cell, 2, border_radius=6)
            surface.blit(thumbnail, thumbnail.get_rect(center=(cell.centerx, cell.y + (cell.height - 16) // 2 + 1)))
            draw_text(surface, self.items[index], (cell.centerx, cell.bottom - 10), 11,
                      Theme.TEXT if chosen else Theme.MUTED, center=True)
