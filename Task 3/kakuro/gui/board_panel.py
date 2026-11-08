"""The grid. Each empty cell shows its domain as a 3 x 3 block of candidate digits."""
from __future__ import annotations

from typing import Optional, Sequence, Set, Tuple

import pygame

from ..csp import DIGITS, KakuroCSP, POPCOUNT
from ..puzzle import ACROSS, KakuroPuzzle, Run
from ..trace import ASSIGN, BACKTRACK, ORDER, REJECT, REVISE, SELECT, WIPEOUT, ReplayState, TraceEvent
from .theme import Color, Theme, draw_text


class BoardPanel:
    def __init__(self, area: pygame.Rect) -> None:
        self.area = area
        self.puzzle: Optional[KakuroPuzzle] = None
        self.size = 0
        self.origin = (0, 0)

    def set_puzzle(self, puzzle: KakuroPuzzle) -> None:
        self.puzzle = puzzle
        self.size = min(self.area.width // puzzle.width, self.area.height // puzzle.height, 112)
        self.origin = (self.area.x + (self.area.width - self.size * puzzle.width) // 2,
                       self.area.y + (self.area.height - self.size * puzzle.height) // 2)

    def _rect(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(self.origin[0] + col * self.size, self.origin[1] + row * self.size, self.size, self.size)

    def cell_rect(self, row: int, col: int) -> pygame.Rect:
        return self._rect(row, col)

    def cell_at(self, position: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        x, y = position[0] - self.origin[0], position[1] - self.origin[1]
        if x < 0 or y < 0:
            return None
        row, col = y // self.size, x // self.size
        return (row, col) if row < self.puzzle.height and col < self.puzzle.width else None

    def clue_at(self, position: Tuple[int, int]) -> Optional[Tuple[int, int, str]]:
        """The clue under the mouse: its cell and 'across' (upper right half) or 'down' (lower left half)."""
        cell = self.cell_at(position)
        if cell is None or cell not in self.puzzle.clues:
            return None
        rect = self._rect(*cell)
        across = position[0] - rect.x > position[1] - rect.y  # above the diagonal
        clue = self.puzzle.clues[cell]
        direction, total = (ACROSS, clue.across) if across else ("down", clue.down)
        return (cell[0], cell[1], direction) if total is not None else None

    def _draw_frame(self, surface: pygame.Surface) -> None:
        board = pygame.Rect(self.origin[0], self.origin[1], self.size * self.puzzle.width, self.size * self.puzzle.height)
        pygame.draw.rect(surface, Theme.GRID, board.inflate(3, 3), 2)

    # -------------------------------------------------------------------- replay
    def draw_replay(self, surface: pygame.Surface, state: ReplayState, event: TraceEvent, csp: KakuroCSP,
                    show_heat: bool, inspected: Sequence[Run]) -> None:
        puzzle = self.puzzle
        run = csp.runs[event.run] if event.run is not None else None
        run_cells = set(run.cells) if run is not None else set()
        inspected_cells: Set[int] = {cell for item in inspected for cell in item.cells}
        changed = {variable: old & ~new for variable, old, new in event.changes} if event.kind == REVISE else {}
        dead_end = event.kind == WIPEOUT

        for r in range(puzzle.height):
            for c in range(puzzle.width):
                rect = self._rect(r, c)
                if puzzle.is_white(r, c):
                    index = puzzle.cell_index(r, c)
                    fill = self._cell_fill(index, state, run_cells, inspected_cells, dead_end, show_heat)
                    pygame.draw.rect(surface, fill, rect)
                    self._draw_domain(surface, rect, index, state, changed.get(index, 0), event, fill)
                else:
                    self._draw_black(surface, rect, r, c, ([run] if run is not None else []) + list(inspected))
                pygame.draw.rect(surface, Theme.GRID, rect, 1)

        if event.variable is not None and event.kind in (SELECT, ORDER, ASSIGN, REJECT, BACKTRACK, WIPEOUT):
            r, c = puzzle.cells[event.variable]
            colors = {ASSIGN: Theme.GOOD, BACKTRACK: Theme.BAD, REJECT: Theme.BAD, WIPEOUT: Theme.BAD}
            pygame.draw.rect(surface, colors.get(event.kind, Theme.SELECT), self._rect(r, c).inflate(-1, -1), 4)
        self._draw_frame(surface)

    @staticmethod
    def _cell_fill(index: int, state: ReplayState, run_cells: Set[int], inspected: Set[int], dead_end: bool,
                   show_heat: bool) -> Color:
        if index in run_cells:
            return Theme.BAD_FILL if dead_end else Theme.RUN_FILL
        if index in inspected:
            return Theme.RUN_FILL
        if show_heat and index not in state.assigned:
            size = POPCOUNT[state.domains[index]]
            if size == 2:
                return Theme.HEAT[3]
            if size == 3:
                return Theme.HEAT[2]
            if size == 4:
                return Theme.HEAT[1]
        return Theme.WHITE_CELL

    def _draw_black(self, surface: pygame.Surface, rect: pygame.Rect, r: int, c: int, active: Sequence[Run]) -> None:
        pygame.draw.rect(surface, Theme.BLACK_CELL, rect)
        clue = self.puzzle.clues.get((r, c))
        if clue is None:
            return
        pygame.draw.line(surface, Theme.GRID, rect.topleft, rect.bottomright, 1)
        size = max(13, self.size // 4)
        for total, direction, position in (
            (clue.across, ACROSS, (rect.x + rect.width * 3 // 4 - 1, rect.y + rect.height // 4)),
            (clue.down, "down", (rect.x + rect.width // 4 + 1, rect.y + rect.height * 3 // 4)),
        ):
            if total is None:
                continue
            if any(run.start == (r, c) and run.direction == direction for run in active):
                pygame.draw.circle(surface, Theme.RUN_CLUE, position, size - 1)
            lit = any(run.start == (r, c) and run.direction == direction for run in active)
            draw_text(surface, str(total), position, size, (255, 255, 255) if lit else Theme.TEXT, bold=True, center=True)

    def _draw_domain(self, surface: pygame.Surface, rect: pygame.Rect, index: int, state: ReplayState, pruned: int,
                     event: TraceEvent, fill: Color) -> None:
        if index in state.assigned:
            color = Theme.GOOD if event.kind == ASSIGN and event.variable == index else Theme.ASSIGNED
            draw_text(surface, str(state.assigned[index]), rect.center, self.size * 3 // 5, color, bold=True, center=True)
            return
        domain = state.domains[index]
        digits = DIGITS[domain]
        if len(digits) == 1 and not pruned:
            draw_text(surface, str(digits[0]), rect.center, self.size * 3 // 5, Theme.DETERMINED, center=True)
            return
        self._draw_candidates(surface, rect, domain, pruned, fill)

    def _draw_candidates(self, surface: pygame.Surface, rect: pygame.Rect, domain: int, pruned: int = 0,
                         fill: Optional[Color] = None) -> None:
        """Candidates in dark ink; removed digits stay faintly visible, so the loss can be seen."""
        fill = Theme.WHITE_CELL if fill is None else fill
        third = self.size / 3
        font = max(10, int(self.size * 0.24))
        ghost = (int(fill[0] * 0.88), int(fill[1] * 0.88), int(fill[2] * 0.88))  # a shade of the cell's own colour
        for digit in range(1, 10):
            row, col = divmod(digit - 1, 3)
            position = (int(rect.x + (col + 0.5) * third), int(rect.y + (row + 0.5) * third))
            if pruned >> digit & 1:
                image_rect = draw_text(surface, str(digit), position, font, Theme.PRUNED, bold=True, center=True)
                pygame.draw.line(surface, Theme.PRUNED, image_rect.bottomleft, image_rect.topright, 2)
            elif domain >> digit & 1:
                draw_text(surface, str(digit), position, font, Theme.DIGIT, center=True)
            else:
                draw_text(surface, str(digit), position, font, ghost, center=True)

    # ---------------------------------------------------------------------- play
    PLAY_SELECTED = (238, 238, 238)  # the fill kakuros.com gives the cell being edited

    def draw_play(self, surface: pygame.Surface, values: Sequence[int], conflicts: Set[int],
                  selected: Optional[int], candidates: Optional[Sequence[int]], csp: KakuroCSP) -> None:
        """The board as a person plays it: digits in order are green, digits that break a rule are red."""
        puzzle = self.puzzle
        selected_runs = [csp.runs[r] for r in csp.runs_of[selected]] if selected is not None else []
        selected_cells = {cell for run in selected_runs for cell in run.cells}
        for r in range(puzzle.height):
            for c in range(puzzle.width):
                rect = self._rect(r, c)
                if not puzzle.is_white(r, c):
                    self._draw_black(surface, rect, r, c, selected_runs)
                    pygame.draw.rect(surface, Theme.GRID, rect, 1)
                    continue
                index = puzzle.cell_index(r, c)
                if index == selected:
                    fill = self.PLAY_SELECTED
                elif index in selected_cells:
                    fill = Theme.RUN_FILL
                else:
                    fill = Theme.WHITE_CELL
                pygame.draw.rect(surface, fill, rect)
                if values[index]:
                    color = Theme.BAD if index in conflicts else Theme.USER_DIGIT
                    draw_text(surface, str(values[index]), rect.center, self.size * 3 // 5, color, bold=True, center=True)
                elif candidates is not None:
                    self._draw_candidates(surface, rect, candidates[index], fill=fill)
                pygame.draw.rect(surface, Theme.GRID, rect, 1)
        if selected is not None:
            r, c = puzzle.cells[selected]
            pygame.draw.rect(surface, Theme.ACCENT, self._rect(r, c).inflate(-1, -1), 3)
        self._draw_frame(surface)
