"""The game itself: asks both players for actions off the main thread, then animates the cycle."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

import pygame

from ..agents import Agent
from ..maps import GameMap
from ..model import BASE_HP, DRAW, TANK_HP, Action, GameState
from ..rules import TARGET_TANK, TARGET_WALL, StepTrace
from ..session import STATUS_OK, Decision, GameSession
from .board_view import BoardView
from .constants import ANIMATION_MS, BOARD_PIXELS, HUMAN, PANEL_WIDTH, TOP_BAR, WINDOW_SIZE
from .retro import FIELD_BLACK, FRAME_GREY, Sprites, draw_pixel_text
from .theme import Color, Fonts, Theme, draw_pips, draw_text, fit_text
from .widgets import Button

if TYPE_CHECKING:
    from .app import TankBattleApp


_ACTION_WORDS = {
    Action.MOVE_UP: "up", Action.MOVE_DOWN: "down", Action.MOVE_LEFT: "left", Action.MOVE_RIGHT: "right",
    Action.FIRE: "fire", Action.STAY: "stay",
}


def _key_cap(surface: pygame.Surface, label: str, x: int, y: int) -> int:
    """A keyboard key, drawn so that a player recognises it; returns its right edge.

    Arrow keys get a drawn triangle, since not every font has arrow characters.
    """
    arrow = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}.get(label)
    width = 22 if arrow or len(label) == 1 else Fonts.get(11, True).size(label)[0] + 12
    cap = pygame.Rect(x, y, width, 20)
    pygame.draw.rect(surface, Theme.BORDER, cap.move(0, 2), border_radius=4)
    pygame.draw.rect(surface, Theme.CARD_HOVER, cap, border_radius=4)
    if arrow:
        cx, cy = cap.center
        dx, dy = arrow
        tip = (cx + dx * 5, cy + dy * 5)
        side = (-dy * 5, dx * 5)
        base = (cx - dx * 3, cy - dy * 3)
        pygame.draw.polygon(surface, Theme.TEXT, [tip, (base[0] + side[0], base[1] + side[1]),
                                                  (base[0] - side[0], base[1] - side[1])])
    else:
        draw_text(surface, label, cap.center, 11, Theme.TEXT, bold=True, center=True)
    return cap.right


class HumanAgent(Agent):
    """Stands for a person; the game screen supplies its actions from the keyboard."""

    name = HUMAN

    def choose_action(self, state: GameState, player: int) -> Action:
        return Action.STAY


class MatchStats:
    """Counts for one game, shown on the result screen."""

    def __init__(self) -> None:
        self.shots = [0, 0]
        self.hits = [0, 0]
        self.walls_destroyed = [0, 0]

    def record(self, decisions, trace: StepTrace) -> None:
        for player, decision in enumerate(decisions):
            if decision is not None and decision.action == Action.FIRE:
                self.shots[player] += 1
        for event in trace.events:
            if event.target == TARGET_WALL:
                if event.destroyed:
                    self.walls_destroyed[event.shooter] += 1
            elif event.target_owner != event.shooter:
                self.hits[event.shooter] += 1


class Series:
    """A match of several games, in which the two entrants swap sides after each game."""

    def __init__(self, total: int, names: Tuple[str, str]) -> None:
        self.total = total
        self.names = names
        self.game = 1
        self.wins = [0, 0]
        self.draws = 0
        self.swapped = False

    def seat_names(self) -> Tuple[str, str]:
        return (self.names[1], self.names[0]) if self.swapped else self.names

    def record(self, outcome: int) -> None:
        if outcome == DRAW:
            self.draws += 1
        else:
            entrant = outcome if not self.swapped else 1 - outcome
            self.wins[entrant] += 1

    @property
    def is_finished(self) -> bool:
        return self.game >= self.total

    def advance(self) -> None:
        self.game += 1
        self.swapped = not self.swapped


class GameScreen:
    THINKING, ANIMATING, OVER = "thinking", "animating", "over"
    HOLD_REPEAT_MS = 200  # a key held down repeats its action, but at most once in this time
    MOVE_KEYS = {
        pygame.K_w: Action.MOVE_UP, pygame.K_s: Action.MOVE_DOWN, pygame.K_a: Action.MOVE_LEFT,
        pygame.K_d: Action.MOVE_RIGHT, pygame.K_SPACE: Action.FIRE, pygame.K_x: Action.STAY,
    }
    ARROW_KEYS = {
        pygame.K_UP: Action.MOVE_UP, pygame.K_DOWN: Action.MOVE_DOWN, pygame.K_LEFT: Action.MOVE_LEFT,
        pygame.K_RIGHT: Action.MOVE_RIGHT, pygame.K_RETURN: Action.FIRE, pygame.K_RSHIFT: Action.STAY,
    }

    def __init__(self, app: "TankBattleApp", names: Tuple[str, str], game_map: GameMap, limit: float,
                 agents: Tuple[Agent, Agent], series_length: int = 1) -> None:
        self.app = app
        self.game_map = game_map
        self.limit = limit
        self._entrants = agents
        self.series = Series(series_length, names)
        self.view = BoardView((0, TOP_BAR), game_map.width, game_map.height)
        self.icons = Sprites(1)
        self.big_icons = Sprites(2)
        self.speed = 1
        self.paused = False
        self.single_step = False
        self.show_fire_lines = True
        self.clock_ms = 0  # time since the screen opened, for blinking
        self._begin()
        self._make_buttons(any(isinstance(agent, HumanAgent) for agent in agents))

    def _seat_agents(self) -> Tuple[Agent, Agent]:
        a, b = self._entrants
        return (b, a) if self.series.swapped else (a, b)

    def _begin(self) -> None:
        self.names = self.series.seat_names()
        self.agents = self._seat_agents()
        self.is_human = tuple(isinstance(agent, HumanAgent) for agent in self.agents)
        self.session = GameSession(self.game_map.create_state(), self.agents, self.limit)
        self.phase = self.THINKING
        self.decisions: List[Optional[Decision]] = [None, None]
        self.queued: List[Optional[Action]] = [None, None]  # a person's key pressed while the last cycle played
        self._since_cycle = 0
        self.last_decisions: List[Optional[Decision]] = [None, None]
        self.log: List[Tuple[str, Color]] = []
        self.before = self.session.state
        self.trace = StepTrace()
        self.elapsed = 0
        self.worker: Optional[threading.Thread] = None
        self.single_step = False
        self._last_infos: List[Dict[str, object]] = [{}, {}]
        self.stats = MatchStats()
        self._played_events: Set[int] = set()
        self._recorded_result = False
        self.view.effects.clear()

    # ------------------------------------------------------------------ game flow
    def _think(self) -> None:
        """Agents think one after the other on the same state, so each gets the whole CPU."""
        session = self.session
        for player in (0, 1):
            if not self.is_human[player]:
                self.decisions[player] = session.decide(player)

    def update(self, milliseconds: int) -> None:
        self.view.effects.update(milliseconds / 1000.0)
        self.clock_ms += milliseconds
        self._since_cycle += milliseconds
        if self.phase == self.THINKING:
            if not self.paused:
                self._feed_humans()
            if self.worker is None and (not self.paused or self.single_step):
                self.worker = threading.Thread(target=self._think, daemon=True)
                self.worker.start()
            if self.worker is not None and not self.worker.is_alive() and all(d is not None for d in self.decisions):
                self._apply()
        elif self.phase == self.ANIMATING:
            self.elapsed += milliseconds
            duration = ANIMATION_MS[self.speed]
            progress = min(1.0, self.elapsed / duration) if duration else 1.0
            self._play_effects(progress)
            if self.elapsed >= duration:
                self.single_step = False
                self.phase = self.OVER if self.session.is_over else self.THINKING
                if self.phase == self.OVER and not self._recorded_result:
                    self.series.record(self.session.outcome)
                    self._recorded_result = True

    def _play_effects(self, progress: float) -> None:
        for index, event in enumerate(self.trace.events):
            if index not in self._played_events and event in self.view.events_reached(self.trace, progress):
                self._played_events.add(index)
                self.view.play_event(event)

    def _apply(self) -> None:
        self.before = self.session.state
        self.trace = self.session.advance(self.decisions[0].action, self.decisions[1].action)
        self.last_decisions = list(self.decisions)
        self._last_infos = [dict(agent.last_info) for agent in self.agents]
        self.stats.record(self.decisions, self.trace)
        self._played_events = set()
        self.decisions = [None, None]
        self.worker = None
        self.elapsed = 0
        self._since_cycle = 0
        self.phase = self.ANIMATING
        self._write_log()

    def _write_log(self) -> None:
        cycle = self.session.state.cycle
        for player, decision in enumerate(self.last_decisions):
            if decision is not None and decision.status != STATUS_OK:
                self._log(f"C{cycle} P{player + 1} fault ({decision.status}): {decision.detail}", Theme.BAD)
        for event in self.trace.events:
            if event.target == TARGET_WALL:
                what = "wall destroyed" if event.destroyed else f"wall HP {event.hp_after}"
            else:
                name = "tank" if event.target == TARGET_TANK else "base"
                what = f"P{event.target_owner + 1} {name} HP {max(event.hp_after, 0)}"
            self._log(f"C{cycle} P{event.shooter + 1} hit: {what}", Theme.PLAYERS[event.shooter])

    def _log(self, text: str, color: Color) -> None:
        self.log.append((text, color))
        del self.log[:-7]

    # --------------------------------------------------------------------- input
    # ------------------------------------------------------------- actions (keys and buttons)
    def _toggle_pause(self) -> None:
        self.paused = not self.paused

    def _step_once(self) -> None:
        self.paused = True
        self.single_step = True

    def _change_speed(self, delta: int) -> None:
        self.speed = min(len(ANIMATION_MS) - 1, max(0, self.speed + delta))

    def _restart(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            self._begin()

    def _make_buttons(self, human: bool) -> None:
        """On-screen controls, so that everything can be done with the mouse as well as the keyboard."""
        self.pause_button = Button(pygame.Rect(0, 0, 0, 0), "Pause", self._toggle_pause, accent=True)
        self.restart_button = Button(pygame.Rect(0, 0, 0, 0), "Restart", self._restart)
        slower = Button(pygame.Rect(0, 0, 0, 0), "Slower", lambda: self._change_speed(-1))
        faster = Button(pygame.Rect(0, 0, 0, 0), "Faster", lambda: self._change_speed(1))
        menu = Button(pygame.Rect(0, 0, 0, 0), "Menu", self.app.show_menu)
        if human:
            self.buttons = [self.pause_button, slower, faster, self.restart_button, menu]
        else:
            step = Button(pygame.Rect(0, 0, 0, 0), "Step", self._step_once)
            self.buttons = [self.pause_button, step, slower, faster, self.restart_button, menu]

    def _layout_buttons(self, x: int, y: int, width: int) -> int:
        """Place the buttons in rows of four below (x, y); returns the bottom edge."""
        columns, gap, height = 4, 6, 30
        size = (width - gap * (columns - 1)) // columns
        for index, button in enumerate(self.buttons):
            row, col = divmod(index, columns)
            button.rect = pygame.Rect(x + col * (size + gap), y + row * (height + gap), size, height)
        self.pause_button.label = "Resume" if self.paused else "Pause"
        self.restart_button.enabled = self.worker is None or not self.worker.is_alive()
        rows = (len(self.buttons) + columns - 1) // columns
        return y + rows * (height + gap) - gap

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            for button in self.buttons:
                if button.handle(event):
                    return
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if key == pygame.K_ESCAPE:
            self.app.show_menu()
        elif key == pygame.K_r:
            self._restart()
        elif key == pygame.K_p:
            self._toggle_pause()
        elif key == pygame.K_n:
            self._step_once()
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self._change_speed(1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self._change_speed(-1)
        elif key == pygame.K_l:
            self.show_fire_lines = not self.show_fire_lines
        elif key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
        elif key == pygame.K_RETURN and self.phase == self.OVER:
            if not self.series.is_finished:
                self.series.advance()
                self._begin()
        elif self.phase != self.OVER:
            self._human_input(key)

    def _bindings(self) -> List[Tuple[Dict[int, Action], int]]:
        """Which key set drives which player. With one person both sets work; with two, each has their own."""
        humans = [p for p in (0, 1) if self.is_human[p]]
        if not humans:
            return []
        return [(self.MOVE_KEYS, humans[0]), (self.ARROW_KEYS, humans[-1])]

    def _human_input(self, key: int) -> None:
        """A key pressed during the player's turn is their move; pressed while a cycle is still
        playing out, it is kept for the next turn, so that no key press is lost."""
        for keys, player in self._bindings():
            if key not in keys:
                continue
            if self.phase == self.THINKING and self.decisions[player] is None:
                self._decide_for_human(player, keys[key])
            else:
                self.queued[player] = keys[key]

    def _decide_for_human(self, player: int, action: Action) -> None:
        decision = Decision(action, 0.0)
        self.decisions[player] = decision
        self.session.records[player].record(decision)
        self.queued[player] = None

    def _feed_humans(self) -> None:
        """At a person's turn: the key they pressed early, otherwise a key they are holding down."""
        bindings = self._bindings()
        if not bindings:
            return
        held = pygame.key.get_pressed() if self._since_cycle >= self.HOLD_REPEAT_MS else None
        for keys, player in bindings:
            if self.decisions[player] is not None:
                continue
            if self.queued[player] is not None:
                self._decide_for_human(player, self.queued[player])
            elif held is not None:
                for code, action in keys.items():
                    if held[code]:
                        self._decide_for_human(player, action)
                        break

    # ------------------------------------------------------------------- drawing
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(Theme.BACKGROUND)
        state = self.session.state
        self._draw_top_bar(surface, state)
        animating = self.phase == self.ANIMATING and ANIMATION_MS[self.speed] > 0
        if animating:
            self.view.draw_animated(surface, self.before, state, self.trace,
                                    min(1.0, self.elapsed / ANIMATION_MS[self.speed]))
        else:
            self.view.draw_state(surface, state)
            if self.show_fire_lines:
                self.view.draw_fire_lines(surface, state)
        self._draw_player_markers(surface, state, animating)
        if self.paused and self.phase != self.OVER and not self.single_step:
            self.view.draw_banner(surface, "PAUSE", (216, 40, 0))
        self._draw_panel(surface, state)
        self._draw_hints(surface)
        if self.phase == self.OVER:
            self._draw_result(surface)

    def _marker_label(self, player: int) -> str:
        return "YOU" if sum(self.is_human) == 1 else f"{player + 1}P"

    def _draw_player_markers(self, surface: pygame.Surface, state: GameState, animating: bool) -> None:
        """Shows a person which tank is theirs and, by blinking brackets, that the game waits for them."""
        blink = (self.clock_ms // 400) % 2 == 0
        progress = min(1.0, self.elapsed / ANIMATION_MS[self.speed]) if animating else 1.0
        for player in (0, 1):
            if not self.is_human[player] or state.tanks[player].hp <= 0:
                continue
            x, y = self.view.tank_position(self.before, state, player, progress) if animating else \
                (state.tanks[player].x, state.tanks[player].y)
            waiting = self._waiting_for_human() and self.decisions[player] is None and not self.paused
            self.view.draw_player_marker(surface, player, x, y, self._marker_label(player), waiting and blink)

    def _status(self) -> Tuple[str, Color]:
        if self.phase == self.OVER:
            return "finished", Theme.MUTED
        if self.paused:
            return "paused", Theme.ACCENT
        if self._waiting_for_human():
            return "your move", Theme.GOOD
        return ("thinking" if self.phase == self.THINKING else "playing"), Theme.MUTED

    def _draw_top_bar(self, surface: pygame.Surface, state: GameState) -> None:
        surface.blit(self.big_icons.flag(), (10, 8))
        title = draw_pixel_text(surface, self.game_map.name, (46, 14), 3, Theme.TEXT, shadow=Theme.BORDER)
        info = f"CYCLE {state.cycle}/{state.max_cycles}"
        draw_pixel_text(surface, info, (title.right + 24, 18), 2, Theme.ACCENT)
        status, color = self._status()
        if any(self.is_human):
            # A person needs to see at a glance that the game is waiting for them.
            if self._waiting_for_human() and not self.paused:
                draw_pixel_text(surface, "YOUR MOVE", (BOARD_PIXELS - 10, 18), 2, Theme.GOOD, right=True)
            else:
                draw_text(surface, status, (BOARD_PIXELS - 10, 15), 14, color, right=True)
        else:
            draw_text(surface, f"{int(self.limit * 1000)} ms per decision",
                      (title.right + 24 + len(info) * 12 + 16, 17), 13, Theme.MUTED)
            draw_text(surface, status, (BOARD_PIXELS - 10, 15), 14, color, right=True)
        series = self.series
        if series.total > 1:
            line = f"Game {series.game}/{series.total}:  {series.wins[0]} - {series.wins[1]}"
            if series.draws:
                line += f" ({series.draws} drawn)"
            draw_text(surface, line, (WINDOW_SIZE[0] - 14, 15), 14, Theme.ACCENT, right=True)

    def _waiting_for_human(self) -> bool:
        return self.phase == self.THINKING and any(self.is_human[p] and self.decisions[p] is None for p in (0, 1))

    def _draw_panel(self, surface: pygame.Surface, state: GameState) -> None:
        x = BOARD_PIXELS + 8
        y = TOP_BAR - 6
        decisions, infos = self.last_decisions, self._last_infos
        for player in (0, 1):
            y = self._draw_player_card(surface, player, x, y, state, decisions[player], infos[player]) + 6
        y = self._layout_buttons(x, y, PANEL_WIDTH - 16) + 8
        for button in self.buttons:
            button.draw(surface)
        height = WINDOW_SIZE[1] - y - 8
        pygame.draw.rect(surface, Theme.PANEL, (x, y, PANEL_WIDTH - 16, height), border_radius=10)
        draw_text(surface, "Events", (x + 12, y + 7), 14, Theme.TEXT, bold=True)
        line_y = y + 28
        for text, color in self.log[-max(1, (height - 32) // 18):]:
            pygame.draw.rect(surface, color, (x + 12, line_y + 4, 8, 8), border_radius=2)
            draw_text(surface, fit_text(text, 13, PANEL_WIDTH - 56), (x + 26, line_y), 13, Theme.TEXT)
            line_y += 18

    def _draw_player_card(self, surface: pygame.Surface, player: int, x: int, y: int, state: GameState,
                          decision: Optional[Decision], info: Dict[str, object]) -> int:
        height = 150
        card = pygame.Rect(x, y, PANEL_WIDTH - 16, height)
        pygame.draw.rect(surface, Theme.PANEL, card, border_radius=10)
        surface.blit(self.icons.tank(player, 0), (x + 10, y + 6))
        draw_pixel_text(surface, f"{player + 1}P", (x + 32, y + 11), 2, Theme.PLAYER_TEXT[player])
        name = fit_text(self.names[player], 14, card.width - 84, bold=True)
        draw_text(surface, name, (x + 66, y + 8), 14, Theme.TEXT, bold=True)

        tank_hp, base_hp = max(state.tanks[player].hp, 0), max(state.bases[player].hp, 0)
        self._hp_row(surface, "Tank", tank_hp, TANK_HP, x + 12, y + 31, card.width - 24)
        self._hp_row(surface, "Base", base_hp, BASE_HP, x + 12, y + 49, card.width - 24)
        if self.is_human[player]:
            self._draw_controls(surface, player, x + 12, y + 70, decision)
            return card.bottom

        rows: List[Tuple[str, str]] = []
        if decision is not None:
            rows.append(("Action", f"{decision.action.name}   ({decision.seconds * 1000:.0f} ms)"))
        if "depth" in info:
            rows.append(("Search depth", f"{info['depth']} cycles, {int(info['nodes']):,} states"))
            rows.append(("Own estimate", f"{float(info['value']):+.1f}"))
        record = self.session.records[player]
        if record.decisions:
            rows.append(("Mean / longest", f"{record.mean_seconds * 1000:.0f} / {record.longest * 1000:.0f} ms"))
        if record.faults:
            rows.append(("Faults", str(record.faults)))
        line_y = y + 70
        for label, value in rows[:5]:
            draw_text(surface, label, (x + 12, line_y), 12, Theme.MUTED)
            color = Theme.BAD if label == "Faults" else Theme.TEXT
            draw_text(surface, value, (x + 108, line_y), 12, color)
            line_y += 18
        return card.bottom

    def _draw_controls(self, surface: pygame.Surface, player: int, x: int, y: int,
                       decision: Optional[Decision]) -> None:
        """The keys of this person, drawn as key caps, and what they will do next."""
        both = sum(self.is_human) == 1  # alone, a person may use either set of keys
        arrows = not both and player == 1  # two people: player 1 has WASD, player 2 the arrows
        draw_text(surface, "Move", (x, y + 3), 12, Theme.MUTED)
        cap_x = x + 52
        for symbol in (("UP", "LEFT", "DOWN", "RIGHT") if arrows else ("W", "A", "S", "D")):
            cap_x = _key_cap(surface, symbol, cap_x, y) + 4
        if both:
            draw_text(surface, "or arrow keys", (cap_x + 4, y + 3), 12, Theme.MUTED)
        y += 24
        draw_text(surface, "Fire", (x, y + 3), 12, Theme.MUTED)
        cap_x = _key_cap(surface, "Enter" if arrows else "Space", x + 52, y) + 4
        if both:
            cap_x = _key_cap(surface, "Enter", cap_x, y) + 4
        draw_text(surface, "Stay", (cap_x + 10, y + 3), 12, Theme.MUTED)
        cap_x = _key_cap(surface, "RShift" if arrows else "X", cap_x + 44, y) + 4
        if both:
            _key_cap(surface, "RShift", cap_x, y)
        y += 26
        queued = self.queued[player]
        if self.paused and self.phase != self.OVER:
            line, color = "Paused: press P to continue", Theme.ACCENT
        elif self.phase == self.THINKING and self.decisions[player] is None and queued is None:
            line, color = "Your turn: press a key (hold it to keep going)", Theme.GOOD
        elif queued is not None:
            line, color = f"Next move: {_ACTION_WORDS[queued]}", Theme.ACCENT
        elif decision is not None:
            line, color = f"Last move: {_ACTION_WORDS[decision.action]}", Theme.TEXT
        else:
            line, color = "Keys pressed early count for the next turn", Theme.MUTED
        draw_text(surface, fit_text(line, 12, PANEL_WIDTH - 40), (x, y), 12, color)

    @staticmethod
    def _hp_row(surface: pygame.Surface, label: str, hp: int, maximum: int, x: int, y: int, width: int) -> None:
        draw_text(surface, label, (x, y), 12, Theme.MUTED)
        draw_text(surface, f"{hp}/{maximum}", (x + width, y), 12, Theme.TEXT, right=True)
        color = Theme.GOOD if hp > maximum // 3 else Theme.BAD
        draw_pips(surface, pygame.Rect(x + 40, y + 3, width - 78, 10), hp, maximum, color)

    def _draw_hints(self, surface: pygame.Surface) -> None:
        """The shortcut bar under the board: each key drawn as a key cap, with what it does."""
        if any(self.is_human):
            groups = [(["P"], "pause"), (["-", "+"], "speed"), (["L"], "aim line"), (["R"], "restart"),
                      (["ESC"], "menu"), (["F11"], "fullscreen")]
        else:
            groups = [(["P"], "pause"), (["N"], "step"), (["-", "+"], "speed"), (["L"], "bullet lines"),
                      (["R"], "restart"), (["ESC"], "menu"), (["F11"], "fullscreen")]
        x, y = 12, WINDOW_SIZE[1] - 26
        for keys, label in groups:
            for key in keys:
                x = _key_cap(surface, key, x, y) + 3
            x = draw_text(surface, label, (x + 2, y + 2), 12, Theme.MUTED).right + 14

    def _result_reason(self) -> str:
        state = self.session.state
        lost = []
        for player in (0, 1):
            if state.tanks[player].hp <= 0:
                lost.append(f"P{player + 1} tank destroyed")
            if state.bases[player].hp <= 0:
                lost.append(f"P{player + 1} base destroyed")
        return ", ".join(lost) if lost else "cycle limit reached"

    def _draw_result(self, surface: pygame.Surface) -> None:
        outcome = self.session.outcome
        box = pygame.Rect(0, 0, 500, 214)
        box.center = (BOARD_PIXELS // 2, TOP_BAR + BOARD_PIXELS // 2)
        pygame.draw.rect(surface, FIELD_BLACK, box)
        pygame.draw.rect(surface, FRAME_GREY, box, 6)
        accent = Theme.BOARD_ACCENT if outcome == DRAW else Theme.PLAYERS[outcome]
        heading, color = "GAME OVER", (216, 40, 0)
        title = "Draw" if outcome == DRAW else f"P{outcome + 1} wins: {self.names[outcome]}"
        if sum(self.is_human) == 1:  # speak to the person: did they win?
            opponent = self.names[self.is_human.index(False)]
            if outcome == DRAW:
                heading, color, title = "DRAW", Theme.BOARD_ACCENT, f"Nobody wins against {opponent}"
            elif self.is_human[outcome]:
                heading, color, title = "YOU WIN!", Theme.BOARD_GOOD, f"You beat {opponent}"
            else:
                title = f"{opponent} wins"
        draw_pixel_text(surface, heading, (box.centerx, box.y + 30), 5, color, center=True, shadow=(60, 10, 0))
        draw_text(surface, fit_text(title, 19, box.width - 30, bold=True), (box.centerx, box.y + 64), 19, accent,
                  bold=True, center=True)
        draw_text(surface, f"{self._result_reason()}, after {self.session.state.cycle} cycles",
                  (box.centerx, box.y + 90), 13, Theme.BOARD_MUTED, center=True)

        columns = (box.x + 180, box.x + 290, box.x + 400)
        for column, label in zip(columns, ("Shots", "Hits on enemy", "Walls broken")):
            draw_text(surface, label, (column, box.y + 110), 12, Theme.BOARD_MUTED, center=True)
        stats = self.stats
        for player in (0, 1):
            y = box.y + 132 + player * 20
            surface.blit(self.icons.tank(player, 0), (box.x + 18, y - 9))
            draw_text(surface, fit_text(f"P{player + 1}  {self.names[player]}", 12, 96), (box.x + 40, y - 8), 12, Theme.BOARD_TEXT)
            values = (stats.shots[player], stats.hits[player], stats.walls_destroyed[player])
            for column, value in zip(columns, values):
                draw_text(surface, str(value), (column, y), 13, Theme.BOARD_TEXT, center=True)

        if not self.series.is_finished:
            hint = "Enter: next game  |  Esc: menu"
        elif self.series.total > 1:
            hint = (f"Match over: {self.series.names[0]} {self.series.wins[0]} - {self.series.wins[1]} "
                    f"{self.series.names[1]}")
        else:
            hint = "R: play again  |  Esc: menu"
        draw_text(surface, fit_text(hint, 13, box.width - 24), (box.centerx, box.bottom - 24), 13, Theme.BOARD_MUTED, center=True)
