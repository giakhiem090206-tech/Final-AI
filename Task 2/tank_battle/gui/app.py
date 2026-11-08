"""The window and the main loop."""
from __future__ import annotations

from typing import List

import pygame

from ..agents import Agent
from ..maps import GameMap
from ..plugins import AgentCatalog
from .constants import HUMAN, WINDOW_SIZE
from .game_screen import GameScreen, HumanAgent
from .menu import MenuScreen
from .theme import Fonts


class TankBattleApp:
    """Owns the window and the main loop, and switches between the two screens."""

    def __init__(self, catalog: AgentCatalog) -> None:
        pygame.init()
        Fonts.clear()
        pygame.display.set_caption("Tank Battle")
        self.surface = self._open_window()
        # Only key presses are used, never typed text. With text input on, an input method
        # (Vietnamese Telex, for example) can hold keys back as "composition" and swallow them.
        pygame.key.stop_text_input()
        self.clock = pygame.time.Clock()
        self.catalog = catalog
        self.screen: object = MenuScreen(self)
        self.running = True

    @staticmethod
    def _open_window() -> pygame.Surface:
        """A window that scales to fit small screens and can be resized by the user."""
        try:
            return pygame.display.set_mode(WINDOW_SIZE, pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:  # scaling needs a renderer, which not every video driver has
            return pygame.display.set_mode(WINDOW_SIZE)

    def player_names(self) -> List[str]:
        return [HUMAN] + self.catalog.names()

    def _make_agent(self, name: str) -> Agent:
        return HumanAgent() if name == HUMAN else self.catalog.create(name)

    def show_menu(self) -> None:
        self.screen = MenuScreen(self)

    def start_game(self, player1: str, player2: str, game_map: GameMap, limit: float, games: int = 1) -> None:
        agents = (self._make_agent(player1), self._make_agent(player2))
        self.screen = GameScreen(self, (player1, player2), game_map, limit, agents, games)

    def run(self) -> None:
        while self.running:
            milliseconds = self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.screen.handle(event)
            self.screen.update(milliseconds)
            self.screen.draw(self.surface)
            pygame.display.flip()
        pygame.quit()
