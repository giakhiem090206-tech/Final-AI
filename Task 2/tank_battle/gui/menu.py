"""The start screen."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from ..maps import BUILTIN_MAPS
from .constants import HUMAN, SERIES_LENGTHS, TIME_LIMITS, WINDOW_SIZE
from .retro import brick_title
from .theme import Theme, draw_text, fit_text
from .widgets import Button, MapPicker, OptionList, Segmented

if TYPE_CHECKING:
    from .app import TankBattleApp


_TAGS = {
    HUMAN: "you",
    "Heuristic A-B + optimizations": "strong, fastest",
    "Heuristic Alpha-Beta": "strong",
    "Heuristic Minimax": "strong",
    "Alpha-Beta": "weak: no heuristic",
    "Minimax": "weak: no heuristic",
    "Random": "easiest",
}


def player_tag(name: str) -> str:
    """A hint for choosing an opponent. The three heuristic searches play about equally well at the
    same time per move (README, Task 2, experiment 6), so they share one label."""
    return _TAGS.get(name, "plugin")


class MenuScreen:
    """Choose two players, a map, the thinking time and the length of the match."""

    def __init__(self, app: "TankBattleApp") -> None:
        self.app = app
        self.title = brick_title("TANK BATTLE", 5)
        self.message = ""
        self.message_ok = True
        margin = 14
        top = 74
        column = 288
        lists_height = 548
        names = app.player_names()
        # By default a person plays against the full controller: press Enter and play.
        self.player1 = OptionList(pygame.Rect(margin, top, column, lists_height), "Player 1", names, 0, Theme.PLAYERS[0],
                                  player_tag)
        self.player2 = OptionList(pygame.Rect(margin * 2 + column, top, column, lists_height), "Player 2", names, 1,
                                  Theme.PLAYERS[1], player_tag)
        picker_x = margin * 3 + 2 * column
        picker_width = WINDOW_SIZE[0] - picker_x - margin
        self.maps = MapPicker(pygame.Rect(picker_x, top, picker_width, lists_height), "Map",
                              list(BUILTIN_MAPS.values()), 2)
        controls_y = top + lists_height + 12
        self.limits = Segmented(pygame.Rect(margin, controls_y, column, 54), "Time per decision",
                                [f"{int(t * 1000)} ms" for t in TIME_LIMITS], 2)
        self.series = Segmented(pygame.Rect(margin * 2 + column, controls_y, column, 54),
                                "Games in the match (players swap sides each game)",
                                [str(n) for n in SERIES_LENGTHS], 0)
        self.buttons = [
            Button(pygame.Rect(picker_x, controls_y + 20, picker_width // 2 + 40, 40), "Start game", self.start, accent=True),
            Button(pygame.Rect(picker_x + picker_width // 2 + 46, controls_y + 20, picker_width // 2 - 46, 40), "Reload",
                   self.reload),
        ]
        self.widgets = [self.player1, self.player2, self.maps, self.limits, self.series]

    def start(self) -> None:
        self.app.start_game(self.player1.value, self.player2.value, BUILTIN_MAPS[self.maps.value],
                            TIME_LIMITS[self.limits.selected], SERIES_LENGTHS[self.series.selected])

    def _refresh_players(self) -> None:
        names = self.app.player_names()
        self.player1.set_items(names)
        self.player2.set_items(names)

    def reload(self) -> None:
        self.app.catalog.reload()
        self._refresh_players()
        self.message = f"Plugins reloaded: {len(self.app.catalog.plugin_names())} agent(s) found."
        self.message_ok = True

    def add_dropped_file(self, path: str) -> None:
        """Another group's file can simply be dragged onto the window."""
        if not path.lower().endswith(".py"):
            self.message, self.message_ok = "Only Python (.py) files can be added as players.", False
            return
        try:
            added = self.app.catalog.add_file(path)
        except BaseException as error:  # foreign code must not stop the program, even with SystemExit
            if isinstance(error, KeyboardInterrupt):
                raise
            self.message, self.message_ok = f"Could not load that file: {type(error).__name__}: {error}", False
            return
        self._refresh_players()
        self.message, self.message_ok = f"Added: {', '.join(added)}", True

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.DROPFILE:
            self.add_dropped_file(event.file)
            return
        for widget in self.widgets:
            widget.handle(event)
        for button in self.buttons:
            if button.handle(event):
                return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self.start()

    def update(self, milliseconds: int) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(Theme.BACKGROUND)
        surface.blit(self.title, (14, 9))
        draw_text(surface, "Destroy the enemy tank or base. To add another group's algorithm, drag its .py file "
                           "onto this window or put it in the plugins folder.", (14, 54), 13, Theme.MUTED)
        for widget in self.widgets:
            widget.draw(surface)
        for button in self.buttons:
            button.draw(surface)
        # One status line at the very bottom: what just happened, otherwise any plugin problem.
        y = WINDOW_SIZE[1] - 24
        errors = self.app.catalog.errors
        if self.message:
            color = Theme.GOOD if self.message_ok else Theme.BAD
            draw_text(surface, fit_text(self.message, 13, WINDOW_SIZE[0] - 28), (14, y), 13, color)
        elif errors:
            filename, reason = next(iter(errors.items()))
            more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
            draw_text(surface, fit_text(f"Plugin not loaded{more}: {filename}: {reason}", 13, WINDOW_SIZE[0] - 28),
                      (14, y), 13, Theme.BAD)
        else:
            draw_text(surface, self.controls_line(), (14, y), 13, Theme.MUTED)

    def controls_line(self) -> str:
        """How the people chosen will drive their tanks, or how to start."""
        humans = [self.player1.value == HUMAN, self.player2.value == HUMAN]
        if all(humans):
            return "Two players: Player 1 uses W A S D, Space fires, X stays. Player 2 uses the arrows, Enter, Right Shift."
        if any(humans):
            return ("You drive with W A S D or the arrow keys, fire with Space or Enter, stay with X. "
                    "Press Enter to start.")
        return "Press Enter to start. Choose Human (keyboard) as a player to drive a tank yourself."
