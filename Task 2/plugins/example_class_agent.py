"""Example plugin as an Agent subclass, for a group that wants to simulate with our rules."""
from tank_battle.agents import Agent
from tank_battle.model import Action
from tank_battle.rules import GameRules


class OnePlyGreedy(Agent):
    """Looks one cycle ahead, assuming the enemy stays still, and keeps the best damage balance."""

    name = "One-ply greedy"

    def choose_action(self, state, player):
        enemy = 1 - player

        def score(action):
            pair = (action, Action.STAY) if player == 0 else (Action.STAY, action)
            after = GameRules.step(state, *pair)
            return (after.tanks[player].hp + after.bases[player].hp
                    - after.tanks[enemy].hp - after.bases[enemy].hp)

        return max(GameRules.legal_actions(state, player), key=score)
