"""The N-Queens window: settings, board, results and a step-by-step replay of the search."""
from __future__ import annotations

import math
from queue import Empty, Queue
from threading import Thread
from time import perf_counter
from typing import List, Optional, Set, Tuple

import pygame
import pygame.gfxdraw

from ..encoding import CnfEncoder, SquareVariables
from ..min_conflicts import MostConflictedTabuSelector
from .board_view import BoardScene, BoardView, Square, attackers_by_row, attacking_pair_count
from .replay import MinConflictsPlayer
from .service import ALGORITHMS, Algorithm, Outcome, SolverService
from .theme import Palette, blend, draw_paragraph, draw_text, fit_text, text_width
from .timeline import Timeline
from .widgets import Button, OptionList, Segmented, Stepper


class NQueensApp:
    """Owns the window and the state; solvers run in a worker thread so the window never freezes."""

    PREFERRED_SIZE = (1220, 800)
    MIN_SIZE = (960, 680)
    MIN_N, MAX_N = 1, 32
    SPEEDS = (("2/s", 2), ("8/s", 8), ("30/s", 30), ("120/s", 120))  # replayed steps per second
    MARGIN, GAP, HEADER, PAD = 20, 14, 84, 18
    TITLE_Y, BODY_Y = 18, 46  # offsets of a card's title and body from its top
    PROCESS_HEIGHT = 150

    def __init__(self, size: Optional[Tuple[int, int]] = None) -> None:
        pygame.init()
        pygame.display.set_caption("N-Queens | AI Final Project")
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

        self.options = OptionList([(a.title, a.subtitle) for a in ALGORITHMS], self.select_algorithm)
        self.n_stepper = Stepper(lambda delta: self.set_n(self.n + delta))
        self.seed_stepper = Stepper(lambda delta: self.set_seed(self.seed + delta))
        self.solve_button = Button(self.start_solve, "GIẢI", primary=True)
        self.playback: List[Button] = [
            Button(lambda: self.jump(to_end=False), icon="first"),
            Button(lambda: self.step(-1), icon="prev"),
            Button(self.toggle_play, icon="play", primary=True),
            Button(lambda: self.step(+1), icon="next"),
            Button(lambda: self.jump(to_end=True), icon="last"),
        ]
        self.speed_control = Segmented([label for label, _ in self.SPEEDS], self.set_speed, self.speed_index)
        self.clear_button = Button(self.clear_board, "Xóa bàn cờ")
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
            self._layout()  # the seed field and the solve button's width depend on the algorithm

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
        available = height - top - m
        right = min(520, max(380, width - 2 * m - g - available))
        self.board_card = pygame.Rect(m, top, width - 2 * m - g - right, available)
        x = self.board_card.right + g
        inner_x, inner_w = x + pad, right - 2 * pad

        compact = available < 640  # short screens: algorithm options without subtitles
        self.options.item_height = 34 if compact else 46
        self.options.show_subtitles = not compact
        self.options.rect = pygame.Rect(inner_x, top + 40, inner_w, self.options.height)
        self._settings_y = self.options.rect.bottom + 14
        row = pygame.Rect(inner_x, self._settings_y + 22, 132, 40)
        self.n_stepper.set_rect(row)
        self.seed_stepper.set_rect(pygame.Rect(row.right + 12, row.y, 120, 40))
        solve_x = (self.seed_stepper.rect.right if self.algorithm.is_local_search else row.right) + 12
        self.solve_button.rect = pygame.Rect(solve_x, row.y, inner_x + inner_w - solve_x, 40)
        self.controls_card = pygame.Rect(x, top, right, row.bottom + 18 - top)
        # After the title and the widest "N × N" label, so it never moves when N changes.
        clear_x = (m + pad + text_width("BÀN CỜ", 12, True) + 10
                   + text_width(f"{self.MAX_N} × {self.MAX_N}", 12) + 14)
        self.clear_button.rect = pygame.Rect(clear_x, top + 11, 96, 28)

        self.process_card = pygame.Rect(x, top + available - self.PROCESS_HEIGHT, right, self.PROCESS_HEIGHT)
        results_y = self.controls_card.bottom + g
        self.results_card = pygame.Rect(x, results_y, right, self.process_card.y - g - results_y)

        card = self.process_card
        self.timeline.set_rect(pygame.Rect(inner_x + 30, card.y + 46, inner_w - 30, 52))
        for index, button in enumerate(self.playback):
            button.rect = pygame.Rect(inner_x + index * 36, card.y + 110, 32, 28)
        self.speed_control.rect = pygame.Rect(inner_x + inner_w - 168, card.y + 110, 168, 28)

    # ---------------------------------------------------------------- events
    def _sync_widgets(self) -> None:
        has_player = self.player is not None
        for button in self.playback:
            button.visible = has_player
        self.speed_control.visible = has_player
        self.playback[2].icon = "pause" if self.playing else "play"
        self.solve_button.enabled = not self.busy
        self.solve_button.label = "ĐANG GIẢI…" if self.busy else "GIẢI"
        self.n_stepper.text = str(self.n)
        self.seed_stepper.text = str(self.seed)
        self.seed_stepper.visible = self.algorithm.is_local_search
        self.clear_button.visible = bool(self.user_queens) or self.outcome is not None

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
        self._draw_board_card(mouse)
        self._draw_controls_card(mouse)
        self._draw_results_card()
        self._draw_process_card(mouse)
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

    def _card(self, card: pygame.Rect, title: str, info: str = "", info_color=Palette.MUTED) -> pygame.Rect:
        """Draw a card with its title and an optional right-aligned note; return the title's rect."""
        pygame.draw.rect(self.screen, Palette.SHADOW, card.move(0, 3), border_radius=14)
        pygame.draw.rect(self.screen, Palette.CARD, card, border_radius=14)
        label = self._section(title, card.x + self.PAD, card.y + self.TITLE_Y)
        if info:
            info = fit_text(info, card.right - self.PAD - label.right - 16, 12)
            draw_text(self.screen, info, (card.right - self.PAD, label.centery), 12, info_color, anchor="midright")
        return label

    def _section(self, text: str, x: int, y: int) -> pygame.Rect:
        return draw_text(self.screen, text, (x, y), 12, Palette.ACCENT, bold=True)

    def _draw_header(self) -> None:
        width, m = self.screen.get_width(), self.MARGIN
        draw_text(self.screen, "N-QUEENS", (m + 2, 10), 32, Palette.TEXT, bold=True)
        subtitle = draw_text(self.screen, "Logic mệnh đề + Glucose3   ·   Tìm kiếm cục bộ Min-Conflicts",
                             (m + 3, 54), 14, Palette.MUTED)
        hints = ("Nhấn vào ô: đặt/bỏ hậu  ·  C xóa bàn cờ  ·  Enter giải  ·  Esc thoát",
                 "Space phát/dừng  ·  ←/→ từng bước  ·  Home/End đầu/cuối",
                 "↑/↓ đổi N  ·  1/2/3 hoặc Tab chọn thuật toán  ·  R đổi seed")
        if width - m - max(text_width(line, 13) for line in hints) > subtitle.right + 24:
            for index, line in enumerate(hints):
                draw_text(self.screen, line, (width - m, 12 + 20 * index), 13, Palette.MUTED, anchor="topright")

    # The board ----------------------------------------------------------
    def _draw_board_card(self, mouse: Tuple[int, int]) -> None:
        card = self.board_card
        label = self._card(card, "BÀN CỜ")
        draw_text(self.screen, f"{self.n} × {self.n}", (label.right + 10, label.centery), 12, Palette.MUTED,
                  anchor="midleft")
        self.clear_button.draw(self.screen, mouse)
        self._draw_status(card.right - 16, card.y + 12)

        area = pygame.Rect(card.x + 16, card.y + 44, card.w - 32, card.h - 44 - 48)
        self.board.layout(area, self.n, row_gutter=self.algorithm.is_local_search)
        hover = None if self.dragging else self.board.square_at(mouse)
        scene = self._scene(hover)
        self.board.draw(self.screen, scene)
        draw_paragraph(self.screen, self._board_caption(scene), card.x + self.PAD, card.bottom - 42,
                       card.w - 2 * self.PAD, 13, Palette.MUTED, max_lines=2, line_height=18)

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
        """What the window is showing, decided once for the caption and the status chip."""
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
                return (f"Ô ({r}, {c}): hậu hàng {r} đặt ở đây sẽ bị {player.conflicts_at(r, c)} hậu tấn công. "
                        f"Nhấn để tự đặt hậu, bắt đầu từ thế cờ đang xem.")
            if local:
                return (f"Ô ({r}, {c}) tấn công {CnfEncoder.attacked_squares(n, r, c)} ô. Nhấn để đặt hậu của hàng {r} "
                        f"vào cột {c} (mỗi hàng là một biến, nên mỗi hàng một hậu).")
            return (f"Ô ({r}, {c}) ↔ biến x{SquareVariables(n).variable(r, c)} · tấn công "
                    f"{CnfEncoder.attacked_squares(n, r, c)} ô · có trong {CnfEncoder.clauses_with_square(n, r, c)} "
                    f"mệnh đề CNF. Nhấn để đặt hoặc bỏ hậu.")
        phase = self._phase()
        if phase == "busy":
            return "Đang chạy thuật toán…"
        if phase == "editing":
            placed = len(self.user_queens)
            if local:
                return (f"Bạn đã đặt {placed} hậu. GIẢI: Min-Conflicts bắt đầu từ thế cờ này (hàng trống lấy cột "
                        f"ngẫu nhiên theo seed) và có thể dời các hậu này. C: xóa bàn cờ.")
            return (f"Bạn đã đặt {placed} hậu. GIẢI: Glucose3 tìm cách đặt nốt, với các hậu này là giả định "
                    f"(assumptions) phải đúng. C: xóa bàn cờ.")
        if phase == "replay":
            if scene.move is None:  # the last frame of an attempt that ran out of steps
                return (f"Hết {player.attempt_steps:,} bước mà vẫn còn xung đột: khởi động lại từ một phép gán "
                        f"ngẫu nhiên mới.")
            row, old, new = scene.move
            attackers = player.row_conflicts[row]
            if new == old:
                return (f"Bước tiếp theo: hàng {row} đang bị {attackers} hậu tấn công nhưng giữ cột {old}, "
                        f"vì không cột nào ít xung đột hơn.")
            return (f"Bước tiếp theo: hàng {row} đang bị {attackers} hậu tấn công → dời hậu từ cột {old} sang cột "
                    f"{new} ({scene.candidates[new]} xung đột). Ô xanh: các cột ít xung đột nhất của hàng.")
        if phase == "solved" and player is not None:
            return (f"Không còn cặp hậu nào tấn công nhau: tìm thấy lời giải sau {player.attempt_steps:,} bước "
                    f"của lần chạy cuối.")
        if phase == "solved":
            kept = f", giữ nguyên {len(outcome.fixed)} hậu bạn đã đặt" if outcome.fixed else ""
            return (f"Mô hình Glucose3 trả về được giải mã thành vị trí các hậu{kept}, rồi kiểm tra lại bằng luật cờ: "
                    f"không cặp nào tấn công nhau.")
        if phase == "unsolved":
            return f"Dừng sau {len(player.attempts)} lần chạy mà vẫn còn xung đột (N = 2 và N = 3 không có lời giải)."
        if phase == "unsat" and outcome.fixed:
            return (f"UNSAT với các giả định: không có lời giải nào chứa {len(outcome.fixed)} hậu bạn đã đặt. "
                    f"Nhấn vào ô để sửa, hoặc C để xóa.")
        if phase == "unsat":
            return f"Glucose3 chứng minh công thức CNF không thỏa được: không thể đặt {n} hậu an toàn trên bàn {n} × {n}."
        if local:  # idle, or an error (shown in the results card)
            return ("Số bên phải mỗi hàng: số hậu đang tấn công hậu của hàng đó. Nhấn vào ô để tự đặt hậu, "
                    "hoặc GIẢI để bắt đầu từ một phép gán ngẫu nhiên.")
        return ("Rê chuột lên một ô để xem biến logic và các đường tấn công sinh ra ràng buộc của nó. "
                "Nhấn vào ô để tự đặt hậu.")

    def _status(self) -> Tuple[str, str]:
        """(icon kind, label) of the status chip."""
        phase, outcome = self._phase(), self.outcome
        if phase == "editing":
            placed, pairs = len(self.user_queens), attacking_pair_count(list(self.user_queens))
            if placed == self.n and pairs == 0:
                return "good", "Bạn đã đặt đúng: lời giải hợp lệ"
            if pairs:
                return "warning", f"Đã đặt {placed}/{self.n} hậu · {pairs} cặp tấn công"
            return "progress", f"Đã đặt {placed}/{self.n} hậu · chưa cặp nào tấn công"
        if phase == "replay":
            player = outcome.player
            return "progress", f"Bước {player.step:,} · {player.attacking_pairs} cặp tấn công"
        if phase == "solved":
            return ("good", "Lời giải hợp lệ") if outcome.valid else ("error", "Lời giải sai luật")
        if phase == "unsat":
            return "warning", "UNSAT với các hậu đã đặt" if outcome.fixed else "Không có lời giải (UNSAT)"
        return {"busy": ("busy", "Đang giải…"), "idle": ("idle", "Chưa giải"), "error": ("error", "Lỗi khi giải"),
                "unsolved": ("warning", "Chưa tìm được lời giải")}[phase]

    def _draw_status(self, right: int, y: int) -> None:
        kind, label = self._status()
        color = {"good": Palette.GOOD, "warning": Palette.WARNING, "error": Palette.CRITICAL,
                 "progress": Palette.WARNING, "idle": Palette.FAINT, "busy": Palette.ACCENT}[kind]
        chip = pygame.Rect(0, y, text_width(label, 13, True) + 44, 26)
        chip.right = right
        pygame.draw.rect(self.screen, blend(color, Palette.CARD, 0.14), chip, border_radius=13)
        self._status_icon(kind, color, chip.x + 16, chip.centery)
        draw_text(self.screen, label, (chip.x + 30, chip.centery), 13, Palette.TEXT, bold=True, anchor="midleft")

    def _status_icon(self, kind: str, color, cx: int, cy: int) -> None:
        surface, white = self.screen, Palette.ON_ACCENT
        if kind == "busy":
            angle = perf_counter() * 6 % (2 * math.pi)
            pygame.draw.arc(surface, color, pygame.Rect(cx - 7, cy - 7, 15, 15), angle, angle + 4.2, 2)
            return
        if kind == "idle":
            pygame.gfxdraw.aacircle(surface, cx, cy, 6, color)
            pygame.gfxdraw.aacircle(surface, cx, cy, 5, color)
            return
        pygame.gfxdraw.aacircle(surface, cx, cy, 8, color)
        pygame.gfxdraw.filled_circle(surface, cx, cy, 8, color)
        if kind == "good":
            pygame.draw.lines(surface, white, False, [(cx - 4, cy), (cx - 1, cy + 3), (cx + 4, cy - 3)], 2)
        elif kind == "error":
            pygame.draw.line(surface, white, (cx - 3, cy - 3), (cx + 3, cy + 3), 2)
            pygame.draw.line(surface, white, (cx + 3, cy - 3), (cx - 3, cy + 3), 2)
        elif kind == "warning":
            pygame.draw.line(surface, white, (cx, cy - 4), (cx, cy + 1), 2)
            surface.fill(white, (cx - 1, cy + 3, 2, 2))
        else:  # progress
            for dx in (-4, 0, 4):
                surface.fill(white, (cx + dx - 1, cy - 1, 2, 2))

    # The panel ----------------------------------------------------------
    def _draw_controls_card(self, mouse: Tuple[int, int]) -> None:
        self._card(self.controls_card, "THUẬT TOÁN")
        self.options.draw(self.screen, mouse)
        self._section("KÍCH THƯỚC N", self.n_stepper.rect.x, self._settings_y)
        if self.seed_stepper.visible:
            self._section("SEED", self.seed_stepper.rect.x, self._settings_y)
        self.n_stepper.draw(self.screen, mouse)
        self.seed_stepper.draw(self.screen, mouse)
        self.solve_button.draw(self.screen, mouse)

    def _draw_results_card(self) -> None:
        card, outcome = self.results_card, self.outcome
        self._card(card, "KẾT QUẢ", f"{outcome.algorithm.title} · N = {outcome.n}" if outcome else "")
        x, width, body_y = card.x + self.PAD, card.w - 2 * self.PAD, card.y + self.BODY_Y
        if self.busy:
            draw_paragraph(self.screen, "Đang chạy thuật toán trong luồng nền…", x, body_y, width)
            return
        if outcome is None:
            draw_paragraph(self.screen, "Chọn thuật toán và kích thước N rồi nhấn GIẢI (hoặc Enter). Có thể nhấn vào "
                           "bàn cờ để tự đặt vài hậu trước: Glucose3 sẽ tìm cách đặt nốt, Min-Conflicts sẽ bắt đầu "
                           "tìm kiếm từ thế cờ đó.", x, body_y, width, line_height=20)
            return
        if outcome.status == "error":
            draw_paragraph(self.screen, f"Lỗi: {outcome.error}", x, body_y, width, color=Palette.CRITICAL)
            return
        rows = outcome.stats
        row_height = max(20, min(30, (card.bottom - 6 - body_y) // len(rows)))
        y = body_y - 4
        for index, (name, value) in enumerate(rows):
            if y + row_height > card.bottom - 4:
                break
            cy = y + row_height // 2
            name_rect = draw_text(self.screen, name, (x, cy), 14, Palette.MUTED, anchor="midleft")
            draw_text(self.screen, fit_text(value, width - name_rect.w - 12, 14, True), (x + width, cy), 14,
                      Palette.TEXT, bold=True, anchor="midright")
            y += row_height
            if index < len(rows) - 1:
                pygame.draw.line(self.screen, Palette.BORDER, (x, y), (x + width, y))

    def _draw_process_card(self, mouse: Tuple[int, int]) -> None:
        card, player = self.process_card, self.player
        x, width, body_y = card.x + self.PAD, card.w - 2 * self.PAD, card.y + self.BODY_Y
        if not self.algorithm.is_local_search:
            self._draw_cnf_structure(card, x, width, body_y)
        elif player is None:
            self._card(card, "MIN-CONFLICTS")
            if self.algorithm.key == "standard":
                choice = "Mỗi bước chọn ngẫu nhiên một hàng đang bị tấn công"
            else:
                choice = (f"Heuristic: mỗi bước chọn hàng bị tấn công nhiều nhất, bỏ qua các hàng vừa sửa trong "
                          f"{MostConflictedTabuSelector.DEFAULT_TENURE} bước gần nhất (tabu),")
            text = (f"Mỗi hàng là một biến, giá trị là cột đặt hậu. {choice} rồi dời hậu sang cột ít xung đột nhất. "
                    f"Nhấn GIẢI để xem lại từng bước.")
            draw_paragraph(self.screen, text, x, body_y, width, 13, line_height=19)
        else:
            info, color = self.timeline.hover_label(player, mouse), Palette.TEXT
            if info is None:
                info, color = f"bước {player.step:,}/{player.attempt_steps:,}", Palette.MUTED
                if len(player.attempts) > 1:
                    info = f"lần {player.attempt_index + 1}/{len(player.attempts)} · {info}"
            self._card(card, "CẶP TẤN CÔNG THEO TỪNG BƯỚC", info, color)
            self.timeline.draw(self.screen, player, mouse)
            for button in self.playback:
                button.draw(self.screen, mouse)
            self.speed_control.draw(self.screen, mouse)

    def _draw_cnf_structure(self, card: pygame.Rect, x: int, width: int, body_y: int) -> None:
        """A stacked bar of the clause kinds of the current N, with a legend carrying the values."""
        parts = self.service.cnf_breakdown(self.n)
        total = sum(count for _, count in parts)
        self._card(card, "CẤU TRÚC CNF", f"{self.n * self.n:,} biến · {total:,} mệnh đề")
        bar = pygame.Rect(x, body_y, width, 14)
        shown = [(index, count) for index, (_, count) in enumerate(parts) if count > 0]
        gap = 2
        usable = bar.w - gap * (len(shown) - 1)
        widths = [max(4, round(usable * count / total)) for _, count in shown]
        widths[widths.index(max(widths))] += usable - sum(widths)
        left = bar.x
        for position, ((index, _), segment_width) in enumerate(zip(shown, widths)):
            first, last = position == 0, position == len(shown) - 1
            pygame.draw.rect(self.screen, Palette.SERIES[index], (left, bar.y, segment_width, bar.h),
                             border_top_left_radius=4 if first else 0, border_bottom_left_radius=4 if first else 0,
                             border_top_right_radius=4 if last else 0, border_bottom_right_radius=4 if last else 0)
            left += segment_width + gap
        for index, (name, count) in enumerate(parts):
            cy = bar.bottom + 21 + index * 22
            pygame.draw.rect(self.screen, Palette.SERIES[index], (x, cy - 5, 10, 10), border_radius=3)
            share = 100 * count / total
            value = f"{count:,}  ({share:.1f}%)" if share < 10 else f"{count:,}  ({share:.0f}%)"
            value_rect = draw_text(self.screen, value, (x + width, cy), 13, Palette.TEXT, bold=True, anchor="midright")
            draw_text(self.screen, fit_text(name, value_rect.x - x - 28, 13), (x + 18, cy), 13, Palette.TEXT,
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
