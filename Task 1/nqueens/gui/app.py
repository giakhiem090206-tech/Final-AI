"""The N-Queens window: settings, board, results and a step-by-step replay of the search."""
from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import List, Optional, Set, Tuple

import pygame

from ..encoding import CnfEncoder, SquareVariables
from .board_view import BoardScene, BoardView, Square, attackers_by_row, attacking_pair_count
from .replay import MinConflictsPlayer
from .service import ALGORITHMS, Algorithm, Outcome, SolverService, plural
from .theme import Palette, draw_text, fit_text
from .timeline import Timeline
from .widgets import Button, RadioGroup, Segmented, Stepper

KEY_HELP = ("Enter: solve    Space: play/pause    Left/Right: step    Home/End: first/last    "
            "Up/Down: N    1-3: algorithm    R: next seed    C: clear    Esc: quit")


class NQueensApp:
    """Owns the window and the state; solvers run in a worker thread so the window never freezes."""

    PREFERRED_SIZE = (1220, 800)
    MIN_SIZE = (960, 680)
    MIN_N, MAX_N = 1, 32
    SPEEDS = (("2/s", 2), ("8/s", 8), ("30/s", 30), ("120/s", 120))  # replayed steps per second
    MARGIN, GAP, HEADER, STATUS_BAR, PAD = 12, 12, 46, 24, 14
    PROCESS_HEIGHT = 140

    def __init__(self, size: Optional[Tuple[int, int]] = None) -> None:
        pygame.init()
        pygame.display.set_caption("N-Queens Solver")
        pygame.key.set_repeat(320, 45)
        self.screen = pygame.display.set_mode(self._clamp(size or self._initial_size()), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.service = SolverService()
        self.board = BoardView()
        self.timeline = Timeline()

        self.n, self.seed, self.algorithm_index = 8, 0, 0
        self.user_queens: Set[Square] = set()  # queens placed by clicking on the board
        self.outcome: Optional[Outcome] = None
        self.busy = False
        self.playing = False
        self.dragging = False
        self.running = True
        self.speed_index = 1
        self._budget = 0.0  # fractional steps carried to the next frame while playing
        self._request = 0  # id of the run whose result is still wanted
        self._results: Queue = Queue()

        self.options = RadioGroup([a.title for a in ALGORITHMS], self.select_algorithm)
        self.n_stepper = Stepper(lambda delta: self.set_n(self.n + delta))
        self.seed_stepper = Stepper(lambda delta: self.set_seed(self.seed + delta))
        self.solve_button = Button(self.start_solve, "Solve", primary=True)
        self.clear_button = Button(self.clear_board, "Clear board")
        self.playback: List[Button] = [
            Button(lambda: self.jump(to_end=False), icon="first"),
            Button(lambda: self.step(-1), icon="prev"),
            Button(self.toggle_play, icon="play", primary=True),
            Button(lambda: self.step(+1), icon="next"),
            Button(lambda: self.jump(to_end=True), icon="last"),
        ]
        self.speed_control = Segmented([label for label, _ in self.SPEEDS], self.set_speed, self.speed_index)
        self.widgets = (self.options, self.n_stepper, self.seed_stepper, self.solve_button, self.clear_button,
                        *self.playback, self.speed_control)
        self._cursor: Optional[int] = None
        self._layout()

    # ----------------------------------------------------------------- state
    @property
    def algorithm(self) -> Algorithm:
        return ALGORITHMS[self.algorithm_index]

    @property
    def player(self) -> Optional[MinConflictsPlayer]:
        return self.outcome.player if self.outcome is not None else None

    def _invalidate(self) -> None:
        """Settings changed: drop the shown result and ignore a run still in progress."""
        self._request += 1
        self.busy = self.playing = self.dragging = False
        self.outcome = None

    def select_algorithm(self, index: int) -> None:
        if index != self.algorithm_index:
            self.algorithm_index = self.options.selected = index
            self._invalidate()
            self.user_queens = self._fit_to_model(self.user_queens)

    def set_n(self, n: int) -> None:
        n = max(self.MIN_N, min(self.MAX_N, n))
        if n != self.n:
            self.n = n
            self.user_queens = set()
            self._invalidate()

    def shown_queens(self) -> List[Square]:
        """The queens on the board right now: the replay's frame, a solution, or the hand-set board."""
        player = self.player
        if player is not None:
            return list(enumerate(player.queens))
        if self.outcome is not None:
            return list(self.outcome.placement.queens) if self.outcome.placement else []
        return sorted(self.user_queens)

    def place(self, square: Square) -> None:
        """A click on the board: put or remove a queen, starting from what the board shows.

        Glucose3 has one variable per square, so any square can be toggled. Min-Conflicts has
        one variable per row, so a click moves that row's queen to the clicked column.
        """
        queens = set(self.shown_queens())
        self._invalidate()
        if square in queens:
            self.user_queens = queens - {square}
        else:
            self.user_queens = self._fit_to_model(queens | {square}, keep=square)

    def _fit_to_model(self, queens: Set[Square], keep: Optional[Square] = None) -> Set[Square]:
        """Min-Conflicts has one variable per row, so it keeps one queen per row (`keep` wins its
        row, otherwise the leftmost); Glucose3 has one variable per square and keeps them all."""
        if not self.algorithm.is_local_search:
            return set(queens)
        rows = dict(sorted(queens, reverse=True))  # the leftmost queen of a row is written last
        if keep is not None:
            rows[keep[0]] = keep[1]
        return set(rows.items())

    def clear_board(self) -> None:
        self._invalidate()
        self.user_queens = set()

    def set_seed(self, seed: int) -> None:
        seed = max(0, seed)
        if seed != self.seed:
            self.seed = seed
            self._invalidate()

    def set_speed(self, index: int) -> None:
        self.speed_index = self.speed_control.selected = index

    def start_solve(self) -> None:
        if self.busy:
            return
        self._invalidate()
        self.busy = True
        request, algorithm, n, seed = self._request, self.algorithm, self.n, self.seed
        fixed = tuple(sorted(self.user_queens))

        def work() -> None:
            self._results.put((request, self.service.run(algorithm, n, seed, fixed)))

        Thread(target=work, daemon=True).start()

    def poll(self) -> None:
        """Take the worker's result, unless the settings changed while it ran."""
        while True:
            try:
                request, outcome = self._results.get_nowait()
            except Empty:
                return
            if request != self._request:
                continue
            self.busy = False
            self.outcome = outcome
            if outcome.player is not None:  # a new player stands at frame 0: play the search
                self.playing = outcome.player.frame_count > 1
                self._budget = 0.0

    def toggle_play(self) -> None:
        player = self.player
        if player is None:
            return
        if not self.playing and player.at_end:
            player.seek(0)
        self.playing = not self.playing
        self._budget = 0.0

    def step(self, delta: int) -> None:
        player = self.player
        if player is not None:
            self.playing = False
            player.seek(player.frame + delta)

    def jump(self, to_end: bool) -> None:
        player = self.player
        if player is not None:
            self.playing = False
            player.seek(player.frame_count - 1 if to_end else 0)

    def advance(self, seconds: float) -> None:
        player = self.player
        if not self.playing or player is None:
            return
        self._budget += seconds * self.SPEEDS[self.speed_index][1]
        steps = int(self._budget)
        if steps:
            self._budget -= steps
            player.seek(player.frame + steps)
        if player.at_end:
            self.playing = False

    # ---------------------------------------------------------------- layout
    def _initial_size(self) -> Tuple[int, int]:
        info = pygame.display.Info()
        width, height = self.PREFERRED_SIZE
        if info.current_w > 0 and info.current_h > 0:  # leave room for the title bar, dock or taskbar
            width, height = min(width, info.current_w - 40), min(height, info.current_h - 90)
        return width, height

    def _clamp(self, size: Tuple[int, int]) -> Tuple[int, int]:
        return max(self.MIN_SIZE[0], size[0]), max(self.MIN_SIZE[1], size[1])

    def resize(self, size: Tuple[int, int]) -> None:
        self.screen = pygame.display.set_mode(self._clamp(size), pygame.RESIZABLE)
        self._layout()

    def _layout(self) -> None:
        width, height = self.screen.get_size()
        m, g, top, pad = self.MARGIN, self.GAP, self.HEADER, self.PAD
        panel_height = height - top - self.STATUS_BAR - m
        side = 360 if width < 1150 else 390
        self.board_panel = pygame.Rect(m, top, width - 2 * m - g - side, panel_height)
        self.side_panel = pygame.Rect(self.board_panel.right + g, top, side, panel_height)
        x, inner = self.side_panel.x + pad, side - 2 * pad

        y = top + 12
        self._algorithm_label_y = y
        self.options.rect = pygame.Rect(x, y + 24, inner, self.options.height)
        y = self.options.rect.bottom + 10
        self._n_row_y = y
        self.n_stepper.set_rect(pygame.Rect(x + inner - 124, y, 124, 28))
        y += 36
        self._seed_row_y = y
        self.seed_stepper.set_rect(pygame.Rect(x + inner - 124, y, 124, 28))
        y += 40
        half = (inner - 8) // 2
        self.solve_button.rect = pygame.Rect(x, y, half, 32)
        self.clear_button.rect = pygame.Rect(x + inner - half, y, half, 32)
        self._results_y = y + 32 + 18

        self._process_y = self.side_panel.bottom - self.PROCESS_HEIGHT
        self.timeline.set_rect(pygame.Rect(x + 30, self._process_y + 30, inner - 30, 52))
        for index, button in enumerate(self.playback):
            button.rect = pygame.Rect(x + index * 34, self._process_y + 96, 30, 28)
        self.speed_control.rect = pygame.Rect(x + inner - 160, self._process_y + 96, 160, 28)

    # ---------------------------------------------------------------- events
    def _sync_widgets(self) -> None:
        has_player = self.player is not None
        for button in self.playback:
            button.visible = has_player
        self.speed_control.visible = has_player
        self.playback[2].icon = "pause" if self.playing else "play"
        self.solve_button.enabled = not self.busy
        self.solve_button.label = "Solving..." if self.busy else "Solve"
        self.n_stepper.text = str(self.n)
        self.seed_stepper.text = str(self.seed)
        self.seed_stepper.visible = self.algorithm.is_local_search
        self.clear_button.enabled = bool(self.user_queens) or self.outcome is not None

    def handle(self, event: pygame.event.Event) -> None:
        self._sync_widgets()
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE:
            self.resize((event.w, event.h))
        elif event.type == pygame.KEYDOWN:
            self._key(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if any(widget.handle(event) for widget in self.widgets):
                return
            player = self.player
            if player is not None and self.timeline.hit_rect().collidepoint(event.pos):
                self.dragging, self.playing = True, False
                player.seek(self.timeline.frame_at(event.pos[0], player))
                return
            square = self.board.square_at(event.pos)
            if square is not None:
                self.place(square)
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            player = self.player
            if player is None:
                self.dragging = False
            else:
                player.seek(self.timeline.frame_at(event.pos[0], player))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False

    def _key(self, event: pygame.event.Event) -> None:
        key = event.key
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.start_solve()
        elif key == pygame.K_SPACE:
            self.toggle_play()
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.step(-1 if key == pygame.K_LEFT else +1)
        elif key in (pygame.K_HOME, pygame.K_END):
            self.jump(to_end=key == pygame.K_END)
        elif key in (pygame.K_UP, pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.set_n(self.n + 1)
        elif key in (pygame.K_DOWN, pygame.K_MINUS, pygame.K_KP_MINUS):
            self.set_n(self.n - 1)
        elif key == pygame.K_TAB:
            delta = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self.select_algorithm((self.algorithm_index + delta) % len(ALGORITHMS))
        elif pygame.K_1 <= key <= pygame.K_3:
            self.select_algorithm(key - pygame.K_1)
        elif key == pygame.K_r:
            self.set_seed(self.seed + 1)
        elif key in (pygame.K_c, pygame.K_DELETE, pygame.K_BACKSPACE):
            self.clear_board()

    # --------------------------------------------------------------- drawing
    def draw(self) -> None:
        mouse = pygame.mouse.get_pos()
        self._sync_widgets()
        self.screen.fill(Palette.BACKGROUND)
        self._draw_header()
        self._draw_board_panel(mouse)
        self._draw_side_panel(mouse)
        self._draw_status_bar()
        self._update_cursor(mouse)

    def _update_cursor(self, mouse: Tuple[int, int]) -> None:
        """A hand over everything clickable, so that the board shows it can be clicked."""
        clickable = (self.board.square_at(mouse) is not None
                     or any(widget.hit(mouse) for widget in self.widgets)
                     or (self.player is not None and self.timeline.hit_rect().collidepoint(mouse)))
        cursor = pygame.SYSTEM_CURSOR_HAND if clickable else pygame.SYSTEM_CURSOR_ARROW
        if cursor != self._cursor:
            self._cursor = cursor
            try:
                pygame.mouse.set_cursor(cursor)
            except pygame.error:  # no cursor support (e.g. off-screen drawing)
                pass

    def _panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, Palette.CARD, rect)
        pygame.draw.rect(self.screen, Palette.BORDER, rect, 1)

    def _label(self, text: str, x: int, y: int, right_text: str = "", right_x: int = 0,
               right_color=Palette.MUTED) -> pygame.Rect:
        """A bold section label, with an optional note aligned to `right_x`."""
        label = draw_text(self.screen, text, (x, y), 14, Palette.TEXT, bold=True)
        if right_text:
            right_text = fit_text(right_text, right_x - label.right - 12, 12)
            draw_text(self.screen, right_text, (right_x, label.centery), 12, right_color, anchor="midright")
        return label

    def _draw_header(self) -> None:
        width = self.screen.get_width()
        draw_text(self.screen, "N-Queens Solver", (self.MARGIN, self.HEADER // 2), 20, Palette.TEXT, bold=True,
                  anchor="midleft")
        kind, label = self._status()
        color = {"good": Palette.GOOD, "warning": Palette.WARNING, "error": Palette.CRITICAL}.get(kind, Palette.MUTED)
        draw_text(self.screen, label, (width - self.MARGIN, self.HEADER // 2), 14, color, bold=kind != "idle",
                  anchor="midright")

    def _draw_status_bar(self) -> None:
        width, height = self.screen.get_size()
        bar = pygame.Rect(0, height - self.STATUS_BAR, width, self.STATUS_BAR)
        pygame.draw.rect(self.screen, Palette.STATUS_BAR, bar)
        pygame.draw.line(self.screen, Palette.BORDER, bar.topleft, bar.topright)
        draw_text(self.screen, fit_text(KEY_HELP, width - 2 * self.MARGIN, 12), (self.MARGIN, bar.centery), 12,
                  Palette.MUTED, anchor="midleft")

    # The board ----------------------------------------------------------
    def _draw_board_panel(self, mouse: Tuple[int, int]) -> None:
        panel = self.board_panel
        self._panel(panel)
        self._label(f"Board {self.n} x {self.n}", panel.x + 12, panel.y + 10)
        area = pygame.Rect(panel.x + 10, panel.y + 34, panel.w - 20, panel.h - 34 - 30)
        self.board.layout(area, self.n, row_gutter=self.algorithm.is_local_search)
        hover = None if self.dragging else self.board.square_at(mouse)
        scene = self._scene(hover)
        self.board.draw(self.screen, scene)
        caption = fit_text(self._board_caption(scene), panel.w - 24, 13)
        draw_text(self.screen, caption, (panel.x + 12, panel.bottom - 16), 13, Palette.MUTED, anchor="midleft")

    def _scene(self, hover: Optional[Square]) -> BoardScene:
        queens, player, outcome = self.shown_queens(), self.player, self.outcome
        if player is not None:
            move = player.next_move()
            candidates = player.candidate_counts(move[0]) if move else None
            return BoardScene(self.n, queens, player.row_conflicts, move, candidates, hover)
        if outcome is not None:
            return BoardScene(self.n, queens, hover=hover, pinned=outcome.fixed if outcome.placement else ())
        row_conflicts = attackers_by_row(self.n, queens) if self.algorithm.is_local_search else None
        return BoardScene(self.n, queens, row_conflicts, hover=hover)

    def _phase(self) -> str:
        """What the window is showing, decided once for the caption and the status."""
        if self.busy:
            return "busy"
        outcome = self.outcome
        if outcome is None:
            return "editing" if self.user_queens else "idle"
        if outcome.player is not None and not outcome.player.at_end:
            return "replay"
        return outcome.status  # "solved", "unsat", "unsolved" or "error"

    def _board_caption(self, scene: BoardScene) -> str:
        n, player, outcome, local = self.n, self.player, self.outcome, self.algorithm.is_local_search
        if scene.hover is not None:
            r, c = scene.hover
            if player is not None:
                return (f"Square ({r}, {c}): row {r}'s queen would have "
                        f"{plural(player.conflicts_at(r, c), 'conflict')} here.")
            if local:
                return f"Square ({r}, {c}): click to put the queen of row {r} in column {c}."
            return (f"Square ({r}, {c}) = x{SquareVariables(n).variable(r, c)}, attacks "
                    f"{CnfEncoder.attacked_squares(n, r, c)} squares, appears in "
                    f"{CnfEncoder.clauses_with_square(n, r, c)} clauses. Click to place or remove a queen.")
        phase = self._phase()
        if phase == "busy":
            return "Solving..."
        if phase == "editing":
            placed = len(self.user_queens)
            if local:
                return f"{plural(placed, 'queen')} placed by hand. Solve starts Min-Conflicts from this board."
            return f"{plural(placed, 'queen')} placed by hand. Solve keeps them as assumptions for Glucose3."
        if phase == "replay":
            if scene.move is None:  # the last frame of an attempt that ran out of steps
                return f"Step limit ({player.attempt_steps:,}) reached: restart from a new random assignment."
            row, old, new = scene.move
            attackers = plural(player.row_conflicts[row], "conflict")
            if new == old:
                return f"Next: row {row} ({attackers}) stays in column {old}, no column is better."
            return (f"Next: row {row} ({attackers}) moves from column {old} to column {new} "
                    f"({plural(scene.candidates[new], 'conflict')}). Green: the columns with the fewest conflicts.")
        if phase == "solved" and player is not None:
            return f"Solved after {plural(player.attempt_steps, 'step')}."
        if phase == "solved":
            kept = f", keeping the {plural(len(outcome.fixed), 'queen')} placed by hand" if outcome.fixed else ""
            return f"Solution decoded from the Glucose3 model{kept}, then checked against the rules."
        if phase == "unsolved":
            return f"No solution after {plural(len(player.attempts), 'run')}."
        if phase == "unsat" and outcome.fixed:
            return "UNSAT: no solution contains the queens placed by hand."
        if phase == "unsat":
            return f"UNSAT: {n} queens cannot be placed on a {n} x {n} board."
        if local:  # idle, or an error (shown with the results)
            return "Numbers on the right: conflicts of each row's queen. Click a square to place a queen."
        return "Hover a square to see its variable. Click a square to place a queen."

    def _status(self) -> Tuple[str, str]:
        """(kind, text) of the status shown in the header."""
        phase, outcome = self._phase(), self.outcome
        if phase == "editing":
            placed, pairs = len(self.user_queens), attacking_pair_count(list(self.user_queens))
            if placed == self.n and pairs == 0:
                return "good", f"{placed}/{self.n} queens, no attacks: valid solution"
            if pairs:
                return "warning", f"{placed}/{self.n} queens, {plural(pairs, 'attacking pair')}"
            return "idle", f"{placed}/{self.n} queens, no attacks"
        if phase == "replay":
            player = outcome.player
            return "idle", f"Step {player.step:,}/{player.attempt_steps:,}, {plural(player.attacking_pairs, 'attacking pair')}"
        if phase == "solved":
            return ("good", "Valid solution") if outcome.valid else ("error", "Invalid solution")
        if phase == "unsat":
            return "warning", "UNSAT with the placed queens" if outcome.fixed else "No solution (UNSAT)"
        return {"busy": ("idle", "Solving..."), "idle": ("idle", "Not solved yet"), "error": ("error", "Error"),
                "unsolved": ("warning", "No solution found")}[phase]

    # The side panel -----------------------------------------------------
    def _draw_side_panel(self, mouse: Tuple[int, int]) -> None:
        panel = self.side_panel
        self._panel(panel)
        x, right = panel.x + self.PAD, panel.right - self.PAD
        self._label("Algorithm", x, self._algorithm_label_y)
        self.options.draw(self.screen, mouse)
        draw_text(self.screen, "Board size N", (x, self._n_row_y + 14), 14, Palette.TEXT, anchor="midleft")
        self.n_stepper.draw(self.screen, mouse)
        if self.seed_stepper.visible:
            draw_text(self.screen, "Random seed", (x, self._seed_row_y + 14), 14, Palette.TEXT, anchor="midleft")
            self.seed_stepper.draw(self.screen, mouse)
        self.solve_button.draw(self.screen, mouse)
        self.clear_button.draw(self.screen, mouse)

        pygame.draw.line(self.screen, Palette.BORDER, (panel.x, self._results_y - 8), (panel.right - 1, self._results_y - 8))
        self._draw_results(x, right, self._results_y, self._process_y - 14)
        pygame.draw.line(self.screen, Palette.BORDER, (panel.x, self._process_y - 8), (panel.right - 1, self._process_y - 8))
        self._draw_process(x, right, self._process_y, mouse)

    def _draw_results(self, x: int, right: int, top: int, bottom: int) -> None:
        outcome = self.outcome
        self._label("Results", x, top, f"{outcome.algorithm.title}, N = {outcome.n}" if outcome else "", right)
        y = top + 26
        if self.busy:
            draw_text(self.screen, "Solving...", (x, y), 14, Palette.MUTED)
        elif outcome is None:
            draw_text(self.screen, "Press Solve to run the selected algorithm.", (x, y), 14, Palette.MUTED)
        elif outcome.status == "error":
            draw_text(self.screen, fit_text(f"Error: {outcome.error}", right - x, 14), (x, y), 14, Palette.CRITICAL)
        else:
            row_height = max(20, min(24, (bottom - y) // len(outcome.stats)))
            for name, value in outcome.stats:
                if y + row_height > bottom:
                    break
                cy = y + row_height // 2
                name_rect = draw_text(self.screen, name, (x, cy), 14, Palette.MUTED, anchor="midleft")
                draw_text(self.screen, fit_text(value, right - name_rect.right - 12, 14), (right, cy), 14,
                          Palette.TEXT, anchor="midright")
                y += row_height

    def _draw_process(self, x: int, right: int, top: int, mouse: Tuple[int, int]) -> None:
        player = self.player
        if not self.algorithm.is_local_search:
            self._draw_cnf_structure(x, right, top)
        elif player is None:
            self._label("Search progress", x, top)
            draw_text(self.screen, "Press Solve to replay the search step by step.", (x, top + 26), 14, Palette.MUTED)
        else:
            info, color = self.timeline.hover_label(player, mouse), Palette.TEXT
            if info is None:
                info, color = f"step {player.step:,}/{player.attempt_steps:,}", Palette.MUTED
                if len(player.attempts) > 1:
                    info = f"run {player.attempt_index + 1}/{len(player.attempts)}, {info}"
            self._label("Attacking pairs per step", x, top, info, right, color)
            self.timeline.draw(self.screen, player, mouse)
            for button in self.playback:
                button.draw(self.screen, mouse)
            self.speed_control.draw(self.screen, mouse)

    def _draw_cnf_structure(self, x: int, right: int, top: int) -> None:
        """A stacked bar of the clause kinds of the current N, with a legend carrying the values."""
        parts = self.service.cnf_breakdown(self.n)
        total = sum(count for _, count in parts)
        self._label("CNF clauses", x, top, f"{self.n * self.n:,} variables, {total:,} clauses", right)
        bar = pygame.Rect(x, top + 30, right - x, 12)
        shown = [(index, count) for index, (_, count) in enumerate(parts) if count > 0]
        gap = 2
        usable = bar.w - gap * (len(shown) - 1)
        widths = [max(4, round(usable * count / total)) for _, count in shown]
        widths[widths.index(max(widths))] += usable - sum(widths)
        left = bar.x
        for (index, _), segment_width in zip(shown, widths):
            pygame.draw.rect(self.screen, Palette.SERIES[index], (left, bar.y, segment_width, bar.h))
            left += segment_width + gap
        for index, (name, count) in enumerate(parts):
            cy = bar.bottom + 20 + index * 22
            pygame.draw.rect(self.screen, Palette.SERIES[index], (x, cy - 5, 10, 10))
            share = 100 * count / total
            value = f"{count:,} ({share:.1f}%)" if share < 10 else f"{count:,} ({share:.0f}%)"
            value_rect = draw_text(self.screen, value, (right, cy), 13, Palette.TEXT, anchor="midright")
            draw_text(self.screen, fit_text(name, value_rect.x - x - 28, 13), (x + 16, cy), 13, Palette.TEXT,
                      anchor="midleft")

    # ------------------------------------------------------------------ loop
    def run(self) -> None:
        while self.running:
            # Full speed only while something moves; a still window needs far fewer redraws.
            active = self.playing or self.busy or self.dragging
            seconds = self.clock.tick(60 if active else 30) / 1000
            self.poll()
            for event in pygame.event.get():
                self.handle(event)
            self.advance(seconds)
            self.draw()
            pygame.display.flip()
        pygame.quit()
