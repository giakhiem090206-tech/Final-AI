"""Playing by hand, in the manner of kakuros.com.

Click a white cell and a small blue pad of digits appears beside it; pick one, or type it.
Digits that are in order are green and digits that break a rule are red. Hover over a clue to
see every set of digits that could make its sum. The board can be one of the statement's, or a
fresh random one of a chosen size.
"""
from __future__ import annotations

import random
from itertools import combinations
from typing import Callable, Dict, List, Optional, Tuple

import pygame

from ..csp import DIGITS, KakuroCSP, digits_text
from ..generator import BoardGenerator
from ..play import PlayBoard
from ..puzzle import KakuroPuzzle
from .board_panel import BoardPanel
from .theme import Theme, draw_text, wrap_text
from .widgets import Button, Segmented

RANDOM_SIZES = ("4x4", "5x5", "7x7", "9x9", "10x10", "13x13")
DEFAULT_RANDOM_SIZE = 1
PICKER_BLUE = (102, 153, 221)   # the pad's colour on kakuros.com (#69d)
PICKER_BORDER = (136, 136, 136)
PICKER_DIGIT = (0, 0, 200)
TIP_FILL = (255, 255, 225)
DIGIT_KEYS = {getattr(pygame, f"K_{d}"): d for d in range(1, 10)}
DIGIT_KEYS.update({getattr(pygame, f"K_KP{d}"): d for d in range(1, 10)})


def digit_combinations(total: int, length: int) -> List[Tuple[int, ...]]:
    """Every set of distinct digits, in ascending order, with this sum."""
    return [combo for combo in combinations(range(1, 10), length) if sum(combo) == total]


class PlayScreen:
    def __init__(self, puzzles: Dict[str, KakuroPuzzle], area: pygame.Rect, right: int, right_width: int) -> None:
        self.builtin = puzzles
        self.area = area
        self.right, self.right_width = right, right_width
        self.view = BoardPanel(area)
        self.show_candidates = False
        self.selected: Optional[int] = None
        self.picker_open = False
        self.solved = False
        self.message = ""
        self._tips: Dict[Tuple[int, int], List[Tuple[int, ...]]] = {}

        names = list(puzzles)
        default = names.index("Complex (9x9)") if "Complex (9x9)" in names else 0
        x, width = right + 12, right_width - 24
        self.boards = Segmented(pygame.Rect(x, 50, width, 26), "Board", [(n, n) for n in names], default,
                                self._board_chosen)
        self.sizes = Segmented(pygame.Rect(x, 80, width, 26), "Random board", [(s, s.split("x")[0]) for s in RANDOM_SIZES],
                               -1, self._size_chosen)
        self.hint_button = Button(pygame.Rect(0, 0, 58, 26), "Hint", self.hint)
        self.undo_button = Button(pygame.Rect(0, 0, 62, 26), "Undo", self.undo)
        self.candidates_button = Button(pygame.Rect(0, 0, 124, 26), "Candidates: off", self.toggle_candidates)
        self.clear_button = Button(pygame.Rect(0, 0, 62, 26), "Clear", self.reset)
        self.solution_button = Button(pygame.Rect(0, 0, 118, 26), "Show solution", self.show_solution)
        self.new_button = Button(pygame.Rect(0, 0, 100, 26), "New puzzle", self.new_puzzle)
        self.finish_button = Button(pygame.Rect(0, 0, 100, 26), "New puzzle", self.new_puzzle)  # shown under a solved board
        self.buttons = [self.hint_button, self.undo_button, self.candidates_button, self.clear_button,
                        self.solution_button, self.new_button]
        self.clock: Callable[[], int] = pygame.time.get_ticks  # milliseconds; replaceable in tests
        self.history: List[List[int]] = []  # board contents before each change, for Undo
        self.hints_used = 0
        self.revealed = False  # the board was filled by Show solution, not by the player
        self._started = self._stopped = 0
        edge = x
        for button in self.buttons:
            button.rect.topleft = (edge, 114)
            edge += button.rect.width + 4
        self._set_puzzle(puzzles[names[default]])

    # ------------------------------------------------------------------ state
    @property
    def puzzle(self) -> KakuroPuzzle:
        return self._puzzle

    def _set_puzzle(self, puzzle: KakuroPuzzle) -> None:
        self._puzzle = puzzle
        self.csp = KakuroCSP(puzzle)
        self.board = PlayBoard(self.csp)
        self.view.set_puzzle(puzzle)
        self.selected = None
        self.picker_open = False
        self.solved = False
        self.message = ""
        self._tips.clear()
        self._restart_clock()

    def _restart_clock(self) -> None:
        self.history = []
        self.hints_used = 0
        self.revealed = False
        self._started = self.clock()
        self._stopped = 0

    def elapsed_seconds(self) -> int:
        """Time spent on this puzzle; the clock stops when it is solved."""
        end = self._stopped if self._stopped else self.clock()
        return max(0, end - self._started) // 1000

    def _remember(self) -> None:
        self.history.append(list(self.board.values))
        del self.history[:-500]

    def _check_finished(self) -> None:
        self.solved = self.board.is_solved()
        if self.solved and not self._stopped:
            self._stopped = self.clock()

    def undo(self) -> None:
        """Takes back the last change: a digit, an erase, a hint or clearing the board."""
        if not self.history or self.revealed:
            return
        self.board.values = self.history.pop()
        self.picker_open = False
        self.solved = self.board.is_solved()
        if not self.solved:
            self._stopped = 0

    def _board_chosen(self) -> None:
        self.sizes.selected = -1
        self._set_puzzle(self.builtin[self.boards.value])

    def _size_chosen(self) -> None:
        self.new_random(int(self.sizes.value))

    def new_random(self, size: int) -> None:
        puzzle = BoardGenerator(size, size, 0.25, random.randrange(1_000_000)).generate()
        self.boards.selected = -1
        self.sizes.selected = [int(s.split("x")[0]) for s in RANDOM_SIZES].index(size)
        self._set_puzzle(puzzle)

    def new_puzzle(self) -> None:
        """Another random board of the size in use, or of the usual size if a statement board is showing."""
        size = int(self.sizes.value) if self.sizes.selected >= 0 else int(RANDOM_SIZES[DEFAULT_RANDOM_SIZE].split("x")[0])
        self.new_random(size)

    def hint(self) -> None:
        if self.solved:
            return
        hint = self.board.hint(self.selected)
        if hint is not None:
            self.hints_used += 1
            self._enter(hint[0], hint[1])
            self.selected = hint[0]

    def toggle_candidates(self) -> None:
        self.show_candidates = not self.show_candidates
        self.candidates_button.label = "Candidates: on" if self.show_candidates else "Candidates: off"

    def reset(self) -> None:
        """Clears the board. It can be undone, unless the solution was on show: then it starts afresh."""
        if self.revealed:
            self._restart_clock()
        elif self.board.filled:
            self._remember()
        self.board.reset()
        self.selected = None
        self.picker_open = False
        self.solved = False
        self._stopped = 0
        self.message = ""

    def show_solution(self) -> None:
        solution = self.board.solution()
        if solution is None:
            self.message = "This board has no solution."
            return
        self.board.values = list(solution)
        self.picker_open = False
        self.revealed = True
        self._check_finished()

    def _enter(self, cell: int, digit: int) -> None:
        if self.board.values[cell] != digit:
            self._remember()
        if digit:
            self.board.set_value(cell, digit)
        else:
            self.board.clear(cell)
        self.picker_open = False
        self._check_finished()

    # ------------------------------------------------------------------ the digit pad
    def _picker_cells(self) -> List[Tuple[pygame.Rect, int]]:
        """The pad beside the selected cell: digits 1 to 9, then X to erase."""
        if self.selected is None:
            return []
        row, col = self.puzzle.cells[self.selected]
        cell = self.view.cell_rect(row, col)
        mini, gap = max(26, min(40, self.view.size // 2 + 2)), 3
        width, height = 3 * (mini + gap) + gap, 4 * (mini + gap) + gap
        x = cell.right + 4
        if x + width > self.area.right:
            x = cell.x - width - 4
        if x < self.area.x:
            x = min(cell.x, self.area.right - width)
        y = max(self.area.y, min(cell.y, self.area.bottom - height))
        pad = pygame.Rect(x, y, width, height)
        items = [(pygame.Rect(pad.x + gap + ((d - 1) % 3) * (mini + gap), pad.y + gap + ((d - 1) // 3) * (mini + gap), mini, mini), d)
                 for d in range(1, 10)]
        items.append((pygame.Rect(pad.x + gap, pad.y + gap + 3 * (mini + gap), mini, mini), 0))
        return items

    def _picker_box(self) -> Optional[pygame.Rect]:
        items = self._picker_cells()
        return items[0][0].unionall([r for r, _ in items[1:]]).inflate(6, 6) if items else None

    # ------------------------------------------------------------------ input
    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click(event.pos)
        elif event.type == pygame.KEYDOWN:
            self._key(event.key)
        elif event.type == pygame.TEXTINPUT:
            # Some keyboard layouts and input methods deliver digits only as text, never as a key
            # press. Entering the same digit twice is harmless, so both paths stay active.
            for character in event.text:
                if character in "123456789" and self.selected is not None and not self.solved:
                    self._enter(self.selected, int(character))

    def _click(self, position: Tuple[int, int]) -> None:
        if self.boards.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)):
            return
        if self.sizes.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)):
            return
        for button in self.buttons:
            if button.rect.collidepoint(position):
                button.on_click()
                return
        if self.solved:
            if self.finish_button.rect.collidepoint(position):
                self.finish_button.on_click()
            return
        if self.picker_open:
            for rect, digit in self._picker_cells():
                if rect.collidepoint(position):
                    self._enter(self.selected, digit)
                    return
        cell = self.view.cell_at(position)
        if cell is not None and self.puzzle.is_white(*cell):
            index = self.puzzle.cell_index(*cell)
            self.picker_open = not (self.picker_open and self.selected == index)
            self.selected = index
        else:
            self.picker_open = False

    def _key(self, key: int) -> None:
        if key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.undo()
            return
        if self.solved:
            return
        cell = self.selected
        if cell is not None and key in DIGIT_KEYS:
            self._enter(cell, DIGIT_KEYS[key])
        elif cell is not None and key in (pygame.K_BACKSPACE, pygame.K_DELETE, pygame.K_0, pygame.K_KP0):
            self._enter(cell, 0)
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            self.picker_open = False
            self._move_selection(key)

    def _move_selection(self, key: int) -> None:
        if self.selected is None:
            self.selected = 0
            return
        d_row, d_col = {pygame.K_UP: (-1, 0), pygame.K_DOWN: (1, 0), pygame.K_LEFT: (0, -1), pygame.K_RIGHT: (0, 1)}[key]
        r, c = self.puzzle.cells[self.selected]
        r, c = r + d_row, c + d_col
        while 0 <= r < self.puzzle.height and 0 <= c < self.puzzle.width:
            if self.puzzle.is_white(r, c):
                self.selected = self.puzzle.cell_index(r, c)
                return
            r, c = r + d_row, c + d_col

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: pygame.Surface) -> None:
        conflicts = self.board.conflicts()
        candidates = self.board.candidates() if self.show_candidates else None
        self.view.draw_play(surface, self.board.values, conflicts, self.selected, candidates, self.csp)
        if self.solved:
            veil = pygame.Surface(self.area.size, pygame.SRCALPHA)
            veil.fill((*Theme.BACKGROUND, 150))
            surface.blit(veil, self.area.topleft)
        self._draw_bottom_text(surface)
        self._draw_header(surface, conflicts, candidates)
        self._draw_help(surface)
        if self.selected is not None:
            self._draw_selected_cell_help(surface, pygame.Rect(self.right, 424, self.right_width, 170), candidates)
        if self.picker_open and not self.solved:
            self._draw_picker(surface)
        elif not self.solved:
            self._draw_clue_tip(surface)

    def _draw_header(self, surface: pygame.Surface, conflicts, candidates) -> None:
        panel = pygame.Rect(self.right, 8, self.right_width, 196)
        pygame.draw.rect(surface, Theme.PANEL, panel, border_radius=10)
        draw_text(surface, "Your game", (panel.x + 12, panel.y + 12), 14, Theme.TEXT, bold=True)
        self.boards.draw(surface)
        self.sizes.draw(surface)
        for button in self.buttons:
            button.draw(surface)
        total = self.csp.num_variables
        y = panel.y + 152
        draw_text(surface, f"{self.puzzle.name}: {self.board.filled} of {total} cells filled", (panel.x + 12, y), 14,
                  Theme.TEXT)
        minutes, seconds = divmod(self.elapsed_seconds(), 60)
        clock = f"Time {minutes:02d}:{seconds:02d}"
        if self.hints_used:
            clock += f"   Hints {self.hints_used}"
        draw_text(surface, clock, (panel.right - 12, y), 14, Theme.TEXT, bold=True, right=True)
        if self.message:
            status, color = self.message, Theme.BAD
        elif self.revealed:
            status, color = "Solution shown. Clear the board or take a new puzzle to play.", Theme.MUTED
        elif self.solved:
            status, color = f"Solved in {minutes:02d}:{seconds:02d}! Every run adds up and no digit repeats.", Theme.GOOD
        elif conflicts:
            status, color = f"{len(conflicts)} cell(s) break a rule", Theme.BAD
        else:
            status, color = "No rule broken so far", Theme.MUTED
        draw_text(surface, status, (panel.x + 12, y + 22), 14, color, bold=self.solved)
        if self.show_candidates and candidates is None and not conflicts:
            draw_text(surface, "The entries contradict the clues, though no single run shows it yet.",
                      (panel.x + 250, y), 12, Theme.BAD)

    def _draw_bottom_text(self, surface: pygame.Surface) -> None:
        """Under the board: what the game does for you, or the news that the board is solved."""
        y = self.area.bottom + 16
        if self.solved:
            text, color = (("The solution of this puzzle.", Theme.TEXT) if self.revealed
                           else ("The current puzzle is successfully solved!", Theme.GOOD))
            rect = draw_text(surface, text, (self.area.x + 6, y), 17, color, bold=True)
            self.finish_button.rect.topleft = (rect.right + 18, y - 3)
            self.finish_button.draw(surface)
        else:
            draw_text(surface, "The game detects a correct solution by itself. Hover over a clue to see the digits that could make its sum.",
                      (self.area.x + 6, y), 13, Theme.MUTED)

    def _draw_help(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(self.right, 210, self.right_width, 208)
        pygame.draw.rect(surface, Theme.PANEL, panel, border_radius=10)
        draw_text(surface, "How to play", (panel.x + 12, panel.y + 8), 14, Theme.TEXT, bold=True)
        lines = (
            "Fill each white cell with a digit from 1 to 9.",
            "The digits of a run must add up to its clue, and may not repeat within the run.",
            "A clue in the upper right sums the cells to its right; in the lower left, the cells below it.",
            "",
            "Click a cell and pick a digit from the blue pad, or type 1-9. Backspace erases; arrow keys move.",
            "Undo (or Ctrl+Z) takes back the last change.",
            "Candidates shows what constraint propagation allows, given your entries.",
            "Hint fills in the selected cell, or the first empty or wrong one.",
        )
        y = panel.y + 34
        for line in lines:
            for part in wrap_text(line, 13, panel.width - 24) or [""]:
                draw_text(surface, part, (panel.x + 12, y), 13, Theme.MUTED)
                y += 20

    def _draw_selected_cell_help(self, surface: pygame.Surface, panel: pygame.Rect, candidates) -> None:
        pygame.draw.rect(surface, Theme.PANEL, panel, border_radius=10)
        cell = self.selected
        draw_text(surface, f"Cell {self.csp.variable_name(cell)}", (panel.x + 12, panel.y + 8), 14, Theme.TEXT, bold=True)
        y = panel.y + 32
        domains = candidates if candidates is not None else self.board.candidates()
        if domains is None:
            draw_text(surface, "These entries cannot all be right.", (panel.x + 12, y), 13, Theme.BAD)
            return
        for run_index in self.csp.runs_of[cell]:
            run = self.csp.runs[run_index]
            sets = self.csp.possible_digit_sets(run, domains)
            draw_text(surface, run.label, (panel.x + 12, y), 13, Theme.TEXT, bold=True)
            y += 18
            text = " ".join(digits_text(mask) for mask in sets[:12]) or "no digit set fits"
            for line in wrap_text(f"Possible digit sets: {text}", 12, panel.width - 24)[:2]:
                draw_text(surface, line, (panel.x + 12, y), 12, Theme.MUTED)
                y += 16
            y += 4
        digits = ", ".join(str(d) for d in DIGITS[domains[cell]])
        draw_text(surface, f"Possible here: {digits}", (panel.x + 12, panel.bottom - 22), 13, Theme.TEXT)

    def _draw_picker(self, surface: pygame.Surface) -> None:
        box = self._picker_box()
        pygame.draw.rect(surface, PICKER_BLUE, box)
        pygame.draw.rect(surface, PICKER_BORDER, box, 1)
        mouse = pygame.mouse.get_pos()
        for rect, digit in self._picker_cells():
            hovered = rect.collidepoint(mouse)
            pygame.draw.rect(surface, (224, 238, 255) if hovered else (255, 255, 255), rect)
            draw_text(surface, str(digit) if digit else "X", rect.center, max(15, rect.height * 3 // 5),
                      PICKER_DIGIT if digit else (60, 60, 60), bold=True, center=True)

    # ------------------------------------------------------------------ clue tooltips
    def _tip_lines(self, clue: Tuple[int, int, str]) -> Tuple[str, List[str]]:
        row, col, direction = clue
        run = next(r for r in self.csp.runs if r.start == (row, col) and r.direction == direction)
        key = (run.clue, len(run.cells))
        if key not in self._tips:
            self._tips[key] = digit_combinations(*key)
        combos = self._tips[key]
        shown = [" + ".join(map(str, combo)) for combo in combos[:10]]
        if len(combos) > 10:
            shown.append(f"... and {len(combos) - 10} more")
        return f"{run.clue} in {len(run.cells)} cells", shown or ["no digits fit"]

    def _draw_clue_tip(self, surface: pygame.Surface) -> None:
        mouse = pygame.mouse.get_pos()
        clue = self.view.clue_at(mouse) if self.area.collidepoint(mouse) else None
        if clue is None:
            return
        title, lines = self._tip_lines(clue)
        width = max([150] + [len(line) * 8 + 20 for line in lines])
        box = pygame.Rect(mouse[0] + 14, mouse[1] + 18, width, 26 + 17 * len(lines))
        box.x = min(box.x, surface.get_width() - box.width - 4)
        box.y = min(box.y, surface.get_height() - box.height - 4)
        pygame.draw.rect(surface, TIP_FILL, box)
        pygame.draw.rect(surface, PICKER_BORDER, box, 1)
        draw_text(surface, title, (box.x + 8, box.y + 5), 13, (51, 51, 51), bold=True)
        for index, line in enumerate(lines):
            draw_text(surface, line, (box.x + 8, box.y + 24 + 17 * index), 13, (51, 51, 51))
