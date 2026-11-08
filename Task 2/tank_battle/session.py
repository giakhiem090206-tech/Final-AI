"""Runs games under one set of rules for all agents, protecting the game from faulty ones."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Optional, Tuple

from .agents import Agent
from .model import DRAW, Action, GameState
from .rules import GameRules, StepTrace

STATUS_OK, STATUS_TIMEOUT, STATUS_ERROR, STATUS_INVALID = "ok", "timeout", "error", "invalid"


@dataclass
class Decision:
    action: Action
    seconds: float
    status: str = STATUS_OK
    detail: str = ""


class SafeAgentRunner:
    """Asks one agent for its action and always comes back with a legal one.

    An agent that crashes, answers nonsense or overruns the hard limit plays STAY for that
    cycle and the fault is reported. A thread cannot be killed, so an agent still running
    from an earlier overrun keeps playing STAY until it returns.
    """

    def __init__(self, agent: Agent, player: int, hard_limit: Optional[float] = None) -> None:
        self.agent = agent
        self.player = player
        self.hard_limit = hard_limit
        self._worker: Optional[threading.Thread] = None

    def decide(self, state: GameState) -> Decision:
        if self._worker is not None and self._worker.is_alive():
            return Decision(Action.STAY, 0.0, STATUS_TIMEOUT, "still busy with an earlier decision")

        box: dict = {}

        def work() -> None:
            try:
                box["answer"] = self.agent.choose_action(state.clone(), self.player)
            except BaseException as error:  # foreign code must not be able to stop the game
                box["error"] = f"{type(error).__name__}: {error}"

        start = perf_counter()
        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self._worker.join(self.hard_limit)
        seconds = perf_counter() - start

        if self._worker.is_alive():
            return Decision(Action.STAY, seconds, STATUS_TIMEOUT, f"no answer within {self.hard_limit:.2f} s")
        if "error" in box:
            return Decision(Action.STAY, seconds, STATUS_ERROR, str(box["error"]))
        action = Action.parse(box.get("answer"))
        if action is None:
            return Decision(Action.STAY, seconds, STATUS_INVALID, f"invalid action {box.get('answer')!r}")
        return Decision(action, seconds)


@dataclass
class PlayerRecord:
    """Totals for one player over a game."""

    decisions: int = 0
    seconds: float = 0.0
    longest: float = 0.0
    faults: int = 0

    def record(self, decision: Decision) -> None:
        self.decisions += 1
        self.seconds += decision.seconds
        self.longest = max(self.longest, decision.seconds)
        if decision.status != STATUS_OK:
            self.faults += 1

    @property
    def mean_seconds(self) -> float:
        return self.seconds / self.decisions if self.decisions else 0.0


class GameSession:
    """One game in progress: its state, its two players and what they have done so far."""

    GRACE_FACTOR = 1.5
    GRACE_SECONDS = 0.05

    def __init__(self, initial_state: GameState, agents: Tuple[Agent, Agent],
                 time_limit: Optional[float] = None) -> None:
        self.initial_state = initial_state
        self.state = initial_state
        self.agents = agents
        self.time_limit = time_limit
        hard_limit = None if time_limit is None else time_limit * self.GRACE_FACTOR + self.GRACE_SECONDS
        self.runners = tuple(SafeAgentRunner(agent, i, hard_limit) for i, agent in enumerate(agents))
        self.records = (PlayerRecord(), PlayerRecord())
        for i, agent in enumerate(agents):
            if time_limit is not None:
                agent.time_limit = time_limit
            try:
                agent.reset(i)
            except Exception:  # a faulty reset must not stop the game either
                self.records[i].faults += 1

    @property
    def outcome(self) -> Optional[int]:
        return GameRules.outcome(self.state)

    @property
    def is_over(self) -> bool:
        return self.outcome is not None

    def decide(self, player: int) -> Decision:
        decision = self.runners[player].decide(self.state)
        self.records[player].record(decision)
        return decision

    def advance(self, action0: Action, action1: Action) -> StepTrace:
        trace = StepTrace()
        self.state = GameRules.step(self.state, action0, action1, trace)
        return trace


@dataclass
class MatchResult:
    outcome: int
    cycles: int
    final_state: GameState
    records: Tuple[PlayerRecord, PlayerRecord]


class HeadlessMatch:
    """Plays one game to its end without a window, for tournaments and experiments."""

    def __init__(self, initial_state: GameState, agents: Tuple[Agent, Agent],
                 time_limit: Optional[float] = None) -> None:
        self.session = GameSession(initial_state, agents, time_limit)

    def play(self) -> MatchResult:
        session = self.session
        while not session.is_over:
            first = session.decide(0)
            second = session.decide(1)
            session.advance(first.action, second.action)
        outcome = session.outcome
        return MatchResult(DRAW if outcome is None else outcome, session.state.cycle,
                           session.state, session.records)
