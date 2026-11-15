"""Draws the chessboard: squares, coordinates, queens, attacks and the next Min-Conflicts repair."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import comb
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pygame

from ..encoding import ConstraintDiscovery
from .queen import QueenPainter
from .theme import Palette, draw_text

Square = Tuple[int, int]


def queen_lines(queens: Sequence[Square]) -> Dict[Tuple[str, int], List[Square]]:
    """The queens grouped by the lines they stand on; queens on one line attack each other."""
    lines: Dict[Tuple[str, int], List[Square]] = defaultdict(list)
    for square in queens:
        for key in ConstraintDiscovery.line_keys(*square):
            lines[key].append(square)
    return lines


def attack_segments(queens: Sequence[Square]) -> Tuple[List[Tuple[Square, Square]], Set[Square]]:
    """For each line holding two or more queens, its two outermost queens; and the set of
    queens that are attacked."""
    segments, attacked = [], set()
    for squares in queen_lines(queens).values():
        if len(squares) > 1:
            squares.sort()  # along any line, sorting by (row, col) puts the two ends first and last
            segments.append((squares[0], squares[-1]))
            attacked.update(squares)
    return segments, attacked


def attacking_pair_count(queens: Sequence[Square]) -> int:
    """Pairs of queens attacking each other (two squares share at most one line)."""
    return sum(comb(len(squares), 2) for squares in queen_lines(queens).values())


def attackers_by_row(n: int, queens: Sequence[Square]) -> List[Optional[int]]:
    """For a board with at most one queen per row: how many queens attack each row's queen
    (None for an empty row). The Min-Conflicts view of a board set by hand."""
    lines = queen_lines(queens)
    counts: List[Optional[int]] = [None] * n
    for r, c in queens:
        counts[r] = sum(len(lines[key]) - 1 for key in ConstraintDiscovery.line_keys(r, c))
    return counts


def squares_attacked_from(n: int, square: Square) -> Set[Square]:
    """Every square sharing a row, column or diagonal with `square` (the four lines only)."""
    r, c = square
    found = set()
    for i in range(n):
        found.update(((r, i), (i, c)))
        if 0 <= i - r + c < n:
            found.add((i, i - r + c))
        if 0 <= r + c - i < n:
            found.add((i, r + c - i))
    found.discard(square)
    return found


@dataclass
class BoardScene:
    """Everything the board shows in one frame."""

    n: int
    queens: Sequence[Square] = ()
    row_conflicts: Optional[Sequence[Optional[int]]] = None  # attackers of each row's queen (None: empty row)
    move: Optional[Tuple[int, int, int]] = None  # next repair: (row, from column, to column)
    candidates: Optional[Sequence[int]] = None  # conflicts of each column of the move's row
    hover: Optional[Square] = None
    pinned: Sequence[Square] = ()  # queens placed by hand that the solver had to keep


class BoardView:
    LABEL = 22  # room for the coordinates above and left of the board
    GUTTER = 38  # room for the conflict count right of each row
    MAX_CELL = 84

    def __init__(self) -> None:
        self.painter = QueenPainter()
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.cell = 1
        self.row_gutter = False
        # Squares, frame and coordinates only change with N or the cell size: drawn once, then blitted.
        self._static: Optional[pygame.Surface] = None
        self._static_key: Optional[Tuple[int, int]] = None
        self._overlay: Optional[pygame.Surface] = None

    def layout(self, area: pygame.Rect, n: int, row_gutter: bool) -> None:
        self.row_gutter = row_gutter
        right = self.GUTTER if row_gutter else 0
        cell = min((area.w - self.LABEL - right) // n, (area.h - self.LABEL) // n, self.MAX_CELL)
        self.cell = max(3, cell)
        size = self.cell * n
        x = area.x + (area.w - (self.LABEL + size + right)) // 2 + self.LABEL
        y = area.y + (area.h - (self.LABEL + size)) // 2 + self.LABEL
        self.rect = pygame.Rect(x, y, size, size)

    def square_at(self, position: Tuple[int, int]) -> Optional[Square]:
        if not self.rect.collidepoint(position):
            return None
        return (position[1] - self.rect.y) // self.cell, (position[0] - self.rect.x) // self.cell

    def cell_rect(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(self.rect.x + col * self.cell, self.rect.y + row * self.cell, self.cell, self.cell)

    def draw(self, surface: pygame.Surface, scene: BoardScene) -> None:
        surface.blit(self._static_layer(scene.n), (self.rect.x - self.LABEL, self.rect.y - self.LABEL))
        if scene.move is not None or scene.hover is not None:
            overlay = self._clear_overlay()
            if scene.move is not None:
                self._shade_move_row(overlay, scene)
            if scene.hover is not None:
                self._shade_hover(overlay, scene.n, scene.hover)
            surface.blit(overlay, self.rect.topleft)

        segments, attacked = attack_segments(scene.queens)
        width = 3 if self.cell >= 40 else 2
        for start, end in segments:
            pygame.draw.line(surface, Palette.CRITICAL, self._center(start), self._center(end), width)
        if scene.move is not None:
            self._draw_move(surface, scene)
        self._draw_queens(surface, scene.queens, attacked)
        self._draw_pins(surface, scene.pinned)
        if self.row_gutter and scene.row_conflicts is not None:
            self._draw_row_conflicts(surface, scene.row_conflicts)

    def _static_layer(self, n: int) -> pygame.Surface:
        if self._static_key != (n, self.cell):
            label, cell, size = self.LABEL, self.cell, self.cell * n
            layer = pygame.Surface((label + size + 2, label + size + 2))
            layer.fill(Palette.CARD)
            for row in range(n):
                for col in range(n):
                    color = Palette.LIGHT_SQUARE if (row + col) % 2 == 0 else Palette.DARK_SQUARE
                    layer.fill(color, (label + col * cell, label + row * cell, cell, cell))
            pygame.draw.rect(layer, Palette.BOARD_EDGE, (label - 2, label - 2, size + 4, size + 4), 2)
            text_size = max(9, min(13, cell // 2))
            step = 1 if cell >= 18 else (2 if cell >= 10 else 4)
            for index in range(0, n, step):
                middle = label + index * cell + cell // 2
                draw_text(layer, str(index), (middle, label - 5), text_size, Palette.MUTED, anchor="midbottom")
                draw_text(layer, str(index), (label - 7, middle), text_size, Palette.MUTED, anchor="midright")
            self._static, self._static_key = layer, (n, cell)
        return self._static

    def _clear_overlay(self) -> pygame.Surface:
        if self._overlay is None or self._overlay.get_size() != self.rect.size:
            self._overlay = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 0))
        return self._overlay

    def _local(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(col * self.cell, row * self.cell, self.cell, self.cell)

    def _shade_hover(self, overlay: pygame.Surface, n: int, hover: Square) -> None:
        """The hovered square framed, and a dot on every square it attacks (as chess sites mark moves)."""
        pygame.draw.rect(overlay, (*Palette.HOVER_LINE, 255), self._local(*hover), max(2, self.cell // 14))
        radius = max(2, round(self.cell * 0.13))
        for square in squares_attacked_from(n, hover):
            pygame.draw.circle(overlay, (*Palette.HOVER_LINE, 235), self._local(*square).center, radius)

    def _shade_move_row(self, overlay: pygame.Surface, scene: BoardScene) -> None:
        row = scene.move[0]
        overlay.fill((*Palette.MOVE_ROW, 115), pygame.Rect(0, row * self.cell, self.rect.w, self.cell))
        if scene.candidates:
            best = min(scene.candidates)
            for col, count in enumerate(scene.candidates):
                if count == best:
                    overlay.fill((*Palette.BEST_VALUE, 120), self._local(row, col))

    def _center(self, square: Square) -> Tuple[int, int]:
        return self.cell_rect(*square).center

    def _piece_size(self) -> int:
        return max(4, round(self.cell * 0.84))

    def _draw_move(self, surface: pygame.Surface, scene: BoardScene) -> None:
        row, old, new = scene.move
        target = self.cell_rect(row, new)
        if new != old:
            ghost = self.painter.get(self._piece_size(), Palette.GOOD, Palette.QUEEN_EDGE, alpha=120)
            surface.blit(ghost, ghost.get_rect(center=target.center))
        pygame.draw.rect(surface, Palette.GOOD, target.inflate(-2, -2), 3 if self.cell >= 24 else 2)
        if scene.candidates and self.cell >= 26:
            size = max(10, min(15, self.cell // 4))
            for col, count in enumerate(scene.candidates):
                corner = self.cell_rect(row, col)
                draw_text(surface, str(count), (corner.right - 4, corner.bottom - 2), size, Palette.TEXT, bold=True,
                          anchor="bottomright")

    def _draw_queens(self, surface: pygame.Surface, queens: Sequence[Square], attacked: Set[Square]) -> None:
        size = self._piece_size()
        for square in queens:
            fill = Palette.CRITICAL if square in attacked else Palette.QUEEN
            piece = self.painter.get(size, fill, Palette.QUEEN_EDGE)
            surface.blit(piece, piece.get_rect(center=self._center(square)))

    def _draw_pins(self, surface: pygame.Surface, pinned: Sequence[Square]) -> None:
        """A dot in the corner of each queen placed by hand: "you put this one here"."""
        radius = max(3, self.cell // 9)
        for square in pinned:
            cell = self.cell_rect(*square)
            center = (cell.x + radius + 3, cell.y + radius + 3)
            pygame.draw.circle(surface, Palette.QUEEN_EDGE, center, radius + 2)
            pygame.draw.circle(surface, Palette.ACCENT, center, radius)

    def _draw_row_conflicts(self, surface: pygame.Surface, conflicts: Sequence[Optional[int]]) -> None:
        size = max(9, min(13, self.cell - 5))
        height = max(10, min(self.cell - 4, 20))
        for row, count in enumerate(conflicts):
            if count is None:
                continue
            cy = self.rect.y + row * self.cell + self.cell // 2
            x = self.rect.right + 9
            if count > 0:
                width = max(height, len(str(count)) * size // 2 + 10)
                pill = pygame.Rect(x, cy - height // 2, width, height)
                pygame.draw.rect(surface, Palette.CRITICAL, pill, border_radius=height // 2)
                draw_text(surface, str(count), pill.center, size, Palette.ON_ACCENT, bold=True, anchor="center")
            else:
                draw_text(surface, "0", (x + height // 2, cy), size, Palette.FAINT, anchor="center")
