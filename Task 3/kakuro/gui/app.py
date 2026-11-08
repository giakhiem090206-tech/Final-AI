"""The window, its controls, and the two modes: watching the solver and playing by hand."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pygame

from ..csp import KakuroCSP, digits_text
from ..puzzle import BUILTIN_PUZZLES, KakuroPuzzle, Run, SolutionChecker, load_builtin
from ..solver import (
    PROPAGATE_FC, PROPAGATE_MAC, PROPAGATE_NONE, VAL_ASCENDING, VAL_LCV, VAR_DOM_WDEG, VAR_MRV, VAR_MRV_DEGREE,
    VAR_STATIC, BacktrackingSolver, SolveResult, SolverConfig,
)
from ..trace import ASSIGN, BACKTRACK, FINISH, REJECT, SOLUTION, WIPEOUT, Replay, SearchTree, TraceRecorder
from .board_panel import BoardPanel
from .play_screen import PlayScreen
from .theme import Fonts, Theme, draw_text, wrap_text
from .tree_panel import TreePanel
from .widgets import Button, Segmented

WINDOW_SIZE = (1250, 800)
BOARD_AREA = pygame.Rect(12, 12, 610, 610)
RIGHT = 636
RIGHT_WIDTH = WINDOW_SIZE[0] - RIGHT - 12
DISPLAY_LIMIT = 20_000  # assignments recorded for display
SPEEDS = (1, 2, 4, 8, 15, 30, 60, 120)  # events per second
MODE_REPLAY, MODE_PLAY = "replay", "play"


class VisualizerApp:
    def __init__(self, puzzles: Optional[Dict[str, KakuroPuzzle]] = None) -> None:
        pygame.init()
        Fonts.clear()
        pygame.display.set_caption("Kakuro: CSP solver visualizer")
        self.surface = self._open_window()
        # The game never needs typed text. With text input on, an input method (Vietnamese Telex,
        # for example) holds each digit as "composition" until another key arrives, and the
        # digit never reaches the board as a key press.
        pygame.key.stop_text_input()
        self.clock = pygame.time.Clock()
        self.running = True
        self.playing = False
        self.speed = 3
        self.accumulated = 0.0
        self.dragging = False
        self.show_heat = True
        self.pinned_cell: Optional[Tuple[int, int]] = None
        self.puzzles = puzzles or {name: load_builtin(name) for name in BUILTIN_PUZZLES}
        self.names = list(self.puzzles)

        self.board = BoardPanel(BOARD_AREA)
        self.timeline = pygame.Rect(BOARD_AREA.x + 2, BOARD_AREA.bottom + 96, BOARD_AREA.width - 4, 22)
        self.tree_panel = TreePanel(pygame.Rect(RIGHT, 612, RIGHT_WIDTH, WINDOW_SIZE[1] - 612 - 12))

        self.mode_choice = Segmented(pygame.Rect(RIGHT + 200, 16, RIGHT_WIDTH - 212, 26), "",
                                     [("Watch the solver", MODE_REPLAY), ("Play it yourself", MODE_PLAY)], 0, self._mode_changed)
        y, h = 50, 26
        default_puzzle = self.names.index("Complex (9x9)") if "Complex (9x9)" in self.names else 0
        self.choices = [
            Segmented(pygame.Rect(RIGHT + 12, y, RIGHT_WIDTH - 24, h), "Puzzle",
                      [(name, name) for name in self.names], default_puzzle, self.rebuild),
            Segmented(pygame.Rect(RIGHT + 12, y + 30, RIGHT_WIDTH - 24, h), "Propagation",
                      [("None", PROPAGATE_NONE), ("Forward checking", PROPAGATE_FC), ("MAC (GAC-3)", PROPAGATE_MAC)],
                      2, self.rebuild),
            Segmented(pygame.Rect(RIGHT + 12, y + 60, RIGHT_WIDTH - 24, h), "Variable order",
                      [("Fixed", VAR_STATIC), ("MRV", VAR_MRV), ("MRV+degree", VAR_MRV_DEGREE), ("dom/wdeg", VAR_DOM_WDEG)],
                      3, self.rebuild),
            Segmented(pygame.Rect(RIGHT + 12, y + 90, RIGHT_WIDTH - 24, h), "Value order",
                      [("Ascending", VAL_ASCENDING), ("LCV", VAL_LCV)], 0, self.rebuild),
        ]
        self.puzzle_choice, self.propagation_choice, self.variable_choice, self.value_choice = self.choices

        self.buttons = self._layout_buttons(RIGHT + 12, 170, [
            ("|<", self.go_start, 36), ("<", self.step_back, 36), ("Play", self.toggle_play, 56),
            (">", self.step_forward, 36), (">|", self.go_end, 36), ("<< Choice", self.previous_decision, 78),
            ("Choice >>", self.next_decision, 78), ("Slower", self.slower, 56), ("Faster", self.faster, 56),
            ("Heat", self.toggle_heat, 50),
        ])
        self.play_button = self.buttons[2]
        self.play = PlayScreen(self.puzzles, BOARD_AREA, RIGHT, RIGHT_WIDTH)
        self.theme_button = Button(pygame.Rect(BOARD_AREA.right - 132, WINDOW_SIZE[1] - 31, 132, 24), "", self.toggle_theme)
        self.rebuild()

    @staticmethod
    def _open_window() -> pygame.Surface:
        """A window that scales to fit small screens and can be resized by the user."""
        try:
            return pygame.display.set_mode(WINDOW_SIZE, pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:  # scaling needs a renderer, which not every video driver has
            return pygame.display.set_mode(WINDOW_SIZE)

    @staticmethod
    def _layout_buttons(x: int, y: int, specs: Sequence[Tuple[str, Callable[[], None], int]]) -> List[Button]:
        buttons = []
        for label, handler, width in specs:
            buttons.append(Button(pygame.Rect(x, y, width, 26), label, handler))
            x += width + 4
        return buttons

    # ------------------------------------------------------------------ solving
    def current_config(self) -> SolverConfig:
        # Restarts stay off here: the search tree on screen is one continuous search.
        return SolverConfig(self.propagation_choice.value, self.variable_choice.value, self.value_choice.value,
                            restarts=False)

    def rebuild(self) -> None:
        """Run the solver in the chosen configuration, recording every step for replay."""
        self.puzzle = self.puzzles[self.puzzle_choice.value]
        self.csp = KakuroCSP(self.puzzle)
        recorder = TraceRecorder(self.csp)
        solver = BacktrackingSolver(self.csp, self.current_config(), recorder, max_assignments=DISPLAY_LIMIT)
        self.result: SolveResult = solver.solve()
        self.replay = Replay(recorder.events, self.csp.initial_domains())
        self.tree = SearchTree(recorder.events)
        self.board.set_puzzle(self.puzzle)
        self.tree_panel.set_tree(self.tree)
        self.playing = False
        self.accumulated = 0.0
        self.pinned_cell = None
        self.valid = self.result.solution is not None and SolutionChecker(self.puzzle).is_valid(self.result.solution)
        self.backtrack_marks = [i for i, e in enumerate(recorder.events) if e.kind == BACKTRACK]
        self.assign_marks = [i for i, e in enumerate(recorder.events) if e.kind == ASSIGN]

    # ----------------------------------------------------------------- transport
    def go_start(self) -> None:
        self.playing = False
        self.replay.seek(0)

    def go_end(self) -> None:
        self.playing = False
        self.replay.seek(len(self.replay) - 1)

    def step_back(self) -> None:
        self.playing = False
        self.replay.seek(self.replay.position - 1)

    def step_forward(self) -> None:
        self.playing = False
        self.replay.seek(self.replay.position + 1)

    def toggle_play(self) -> None:
        if not self.playing and self.replay.position >= len(self.replay) - 1:
            self.replay.seek(0)
        self.playing = not self.playing

    def next_decision(self) -> None:
        self.playing = False
        self.replay.seek(self.replay.next_position((ASSIGN, BACKTRACK, SOLUTION, FINISH), 1))

    def previous_decision(self) -> None:
        self.playing = False
        self.replay.seek(self.replay.next_position((ASSIGN, BACKTRACK), -1))

    def slower(self) -> None:
        self.speed = max(0, self.speed - 1)

    def faster(self) -> None:
        self.speed = min(len(SPEEDS) - 1, self.speed + 1)

    def toggle_heat(self) -> None:
        self.show_heat = not self.show_heat

    def _seek_mouse(self, x: int) -> None:
        fraction = (x - self.timeline.x) / max(1, self.timeline.width)
        self.replay.seek(int(fraction * (len(self.replay) - 1)))

    def _mode_changed(self) -> None:
        self.playing = False

    @property
    def mode(self) -> str:
        return self.mode_choice.value

    def toggle_theme(self) -> None:
        Theme.use(Theme.other())

    # --------------------------------------------------------------------- input
    def handle(self, event: pygame.event.Event) -> None:
        if self.mode_choice.handle(event) or self.theme_button.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_t:
            self.toggle_theme()
            return
        if self.mode == MODE_PLAY:
            self.play.handle(event)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.timeline.collidepoint(event.pos):
                self.dragging = True
                self.playing = False
                self._seek_mouse(event.pos[0])
                return
            node = self.tree_panel.node_at(event.pos, self.replay.position)
            if node is not None:
                self.playing = False
                self.replay.seek(node.born)
                return
            cell = self.board.cell_at(event.pos)
            if cell is not None:
                self.pinned_cell = None if self.pinned_cell == cell else cell
                return
        if event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._seek_mouse(event.pos[0])
        elif event.type == pygame.KEYDOWN:
            shortcuts = {
                pygame.K_SPACE: self.toggle_play, pygame.K_RIGHT: self.step_forward, pygame.K_LEFT: self.step_back,
                pygame.K_UP: self.next_decision, pygame.K_DOWN: self.previous_decision, pygame.K_HOME: self.go_start,
                pygame.K_END: self.go_end, pygame.K_MINUS: self.slower, pygame.K_EQUALS: self.faster,
                pygame.K_PLUS: self.faster, pygame.K_m: self.toggle_heat,
            }
            if event.key in shortcuts:
                shortcuts[event.key]()
            return
        for widget in self.choices + self.buttons:
            if widget.handle(event):
                return

    def update(self, seconds: float) -> None:
        if not self.playing:
            return
        self.accumulated += seconds * SPEEDS[self.speed]
        steps = int(self.accumulated)
        self.accumulated -= steps
        for _ in range(steps):
            if self.replay.position >= len(self.replay) - 1:
                self.playing = False
                break
            self.replay.seek(self.replay.position + 1)

    # ------------------------------------------------------------------- drawing
    def draw(self) -> None:
        surface = self.surface
        surface.fill(Theme.BACKGROUND)
        if self.mode == MODE_PLAY:
            self.play.draw(surface)
            self.mode_choice.draw(surface)
        else:
            self._draw_replay(surface)
        self.theme_button.label = "Theme: " + ("classic" if Theme.name == "classic" else "dark")
        self.theme_button.draw(surface)

    def _inspected_runs(self) -> List[Run]:
        """The runs through the clicked cell, or the run of a clicked clue."""
        if self.pinned_cell is None:
            return []
        r, c = self.pinned_cell
        if self.puzzle.is_white(r, c):
            return [self.csp.runs[i] for i in self.csp.runs_of[self.puzzle.cell_index(r, c)]]
        return [run for run in self.csp.runs if run.start == (r, c)]

    def _draw_replay(self, surface: pygame.Surface) -> None:
        inspected = self._inspected_runs()
        self.board.draw_replay(surface, self.replay.state, self.replay.event, self.csp, self.show_heat, inspected)
        self._draw_narration(surface)
        self._draw_timeline(surface)
        self._draw_controls(surface)
        self._draw_propagation(surface, inspected)
        self._draw_stack(surface)
        self.tree_panel.draw(surface, self.replay.position, self.csp)
        self._draw_legend(surface)

    def _draw_narration(self, surface: pygame.Surface) -> None:
        """A sentence saying what the current step does and why."""
        box = pygame.Rect(BOARD_AREA.x, BOARD_AREA.bottom + 6, BOARD_AREA.width, 84)
        pygame.draw.rect(surface, Theme.PANEL, box, border_radius=10)
        event = self.replay.event
        draw_text(surface, f"Step {self.replay.position + 1} of {len(self.replay)}", (box.x + 12, box.y + 7), 12,
                  Theme.ACCENT, bold=True)
        color = {WIPEOUT: Theme.BAD, BACKTRACK: Theme.BAD, REJECT: Theme.BAD, SOLUTION: Theme.GOOD}.get(event.kind, Theme.TEXT)
        y = box.y + 25
        for line in wrap_text(event.message, 13, box.width - 24)[:3]:
            draw_text(surface, line, (box.x + 12, y), 13, color)
            y += 18

    def _draw_timeline(self, surface: pygame.Surface) -> None:
        bar = self.timeline
        pygame.draw.rect(surface, Theme.CARD, bar, border_radius=4)
        last = max(1, len(self.replay) - 1)
        for mark in self.assign_marks:
            x = bar.x + mark * bar.width // last
            pygame.draw.line(surface, Theme.GOOD, (x, bar.y + 12), (x, bar.bottom - 3))
        for mark in self.backtrack_marks:
            x = bar.x + mark * bar.width // last
            pygame.draw.line(surface, Theme.BAD, (x, bar.y + 3), (x, bar.y + 11))
        x = bar.x + self.replay.position * bar.width // last
        pygame.draw.rect(surface, Theme.ACCENT, (x - 2, bar.y - 2, 4, bar.height + 4), border_radius=2)
        draw_text(surface, "Timeline: green below = assignment, red above = backtrack. Click or drag to move.",
                  (bar.x, bar.bottom + 5), 12, Theme.MUTED)

    def _draw_controls(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(RIGHT, 8, RIGHT_WIDTH, 196)
        pygame.draw.rect(surface, Theme.PANEL, panel, border_radius=10)
        draw_text(surface, "Solver configuration", (panel.x + 12, panel.y + 12), 14, Theme.TEXT, bold=True)
        self.mode_choice.draw(surface)
        for choice in self.choices:
            choice.draw(surface)
        self.play_button.label = "Pause" if self.playing else "Play"
        for button in self.buttons:
            button.draw(surface)

    def _draw_propagation(self, surface: pygame.Surface, inspected: Sequence[Run]) -> None:
        panel = pygame.Rect(RIGHT, 210, RIGHT_WIDTH, 164)
        pygame.draw.rect(surface, Theme.PANEL, panel, border_radius=10)
        state = self.replay.state
        event = self.replay.event
        column = panel.x + 12
        draw_text(surface, "Constraint propagation", (column, panel.y + 7), 14, Theme.TEXT, bold=True)

        # What the run being looked at still allows: this is the reason behind each removal.
        shown = list(inspected)
        if event.run is not None and not shown:
            shown = [self.csp.runs[event.run]]
        y = panel.y + 28
        for run in shown[:2]:
            sets = self.csp.possible_digit_sets(run, state.domains)
            draw_text(surface, run.label, (column, y), 13, Theme.TEXT, bold=True)
            y += 17
            text = " ".join(digits_text(mask) for mask in sets) if sets else "no digit set fits"
            for line in wrap_text(f"Possible digit sets: {text}", 12, 320)[:2]:
                draw_text(surface, line, (column, y), 12, Theme.MUTED if sets else Theme.BAD)
                y += 15
        if not shown:
            draw_text(surface, "Click a clue or cell to see what its runs still allow.", (column, y), 12, Theme.FAINT)
            y += 18

        queue = state.queue
        draw_text(surface, f"Queue: {len(queue)} run(s) waiting", (column, panel.bottom - 56 if y < panel.bottom - 56 else y), 12,
                  Theme.MUTED)
        y = max(y, panel.bottom - 56) + 16
        names = [self.csp.runs[i].label for i in queue[:2]]
        if len(queue) > 2:
            names.append(f"and {len(queue) - 2} more")
        if names:
            draw_text(surface, ", ".join(names), (column, y), 12, Theme.TEXT)

        stats_x = panel.x + panel.width - 216
        draw_text(surface, "Counters so far", (stats_x, panel.y + 7), 14, Theme.TEXT, bold=True)
        rows = [("Assignments", state.assignments), ("Backtracks", state.backtracks), ("Revisions", state.revisions),
                ("Digits pruned", state.pruned), ("Dead ends", state.wipeouts), ("Replay speed", f"{SPEEDS[self.speed]} steps/s")]
        y = panel.y + 28
        for label, value in rows:
            draw_text(surface, label, (stats_x, y), 13, Theme.MUTED)
            draw_text(surface, str(value), (stats_x + 104, y), 13)
            y += 20

    def _draw_stack(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(RIGHT, 380, RIGHT_WIDTH, 226)
        pygame.draw.rect(surface, Theme.PANEL, panel, border_radius=10)
        draw_text(surface, "Backtracking search: current path", (panel.x + 12, panel.y + 7), 14, Theme.TEXT, bold=True)
        self._draw_verdict(surface, panel)
        stack = self.replay.state.stack
        rows = 9
        shown = stack[-rows:]
        y = panel.y + 30
        if not stack:
            draw_text(surface, "No variable chosen yet.", (panel.x + 12, y), 13, Theme.MUTED)
        if len(stack) > rows:
            draw_text(surface, f"{len(stack) - rows} shallower level(s) not shown", (panel.right - 12, panel.y + 27), 11,
                      Theme.FAINT, right=True)
        for offset, entry in enumerate(shown):
            depth = len(stack) - len(shown) + offset + 1
            draw_text(surface, f"{depth:>2}", (panel.x + 12, y), 13, Theme.MUTED)
            draw_text(surface, self.csp.variable_name(entry.variable), (panel.x + 36, y), 13, bold=True)
            x = panel.x + 84
            for value in entry.failed:
                rect = draw_text(surface, str(value), (x, y), 14, Theme.BAD, bold=True)
                pygame.draw.line(surface, Theme.BAD, rect.bottomleft, rect.topright, 2)
                x += 22
            if entry.current is not None:
                rect = pygame.Rect(x - 3, y - 1, 20, 19)
                pygame.draw.rect(surface, Theme.GOOD, rect, border_radius=4)
                draw_text(surface, str(entry.current), rect.center, 14, Theme.BACKGROUND, bold=True, center=True)
                x += 24
            for value in entry.remaining:
                draw_text(surface, str(value), (x, y), 14, Theme.MUTED)
                x += 22
            y += 21

    def _draw_verdict(self, surface: pygame.Surface, panel: pygame.Rect) -> None:
        """How the whole run ended, and a hint when this configuration never needs to backtrack."""
        stats = self.result.stats
        if self.result.status == "limit":
            text, color = f"Display limit of {DISPLAY_LIMIT} assignments reached", Theme.BAD
        elif self.result.status == "unsatisfiable":
            text, color = "No solution exists", Theme.BAD
        elif stats.backtracks == 0:
            text, color = "0 backtracks: try Forward checking or the Extra board", Theme.ACCENT
        else:
            text, color = f"{stats.backtracks} backtracks in this run", Theme.GOOD
        draw_text(surface, text, (panel.right - 12, panel.y + 9), 12, color, right=True)

    def _draw_legend(self, surface: pygame.Surface) -> None:
        y = WINDOW_SIZE[1] - 24
        items = [("candidate", Theme.DIGIT), ("just pruned", Theme.PRUNED), ("determined", Theme.DETERMINED),
                 ("selected", Theme.SELECT), ("assigned", Theme.GOOD), ("few values", Theme.HEAT[3])]
        x = BOARD_AREA.x
        for label, color in items:
            pygame.draw.rect(surface, color, (x, y + 2, 11, 11), border_radius=2)
            rect = draw_text(surface, label, (x + 15, y), 12, Theme.MUTED)
            x = rect.right + 12

    # ---------------------------------------------------------------------- play
    # ------------------------------------------------------------------ main loop
    def run(self) -> None:
        while self.running:
            seconds = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    self.running = False
                else:
                    self.handle(event)
            self.update(seconds)
            self.draw()
            pygame.display.flip()
        pygame.quit()
