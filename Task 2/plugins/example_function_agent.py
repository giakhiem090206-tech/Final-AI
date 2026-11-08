"""Example plugin in the simplest form: one function, no import from this project.

Copy this file, change the body of `choose_action` and put your own algorithm there.
"""

AGENT_NAME = "Example: shoot when aligned"

MOVES = {(0, -1): "MOVE_UP", (0, 1): "MOVE_DOWN", (-1, 0): "MOVE_LEFT", (1, 0): "MOVE_RIGHT"}
FACING = {"MOVE_UP": "UP", "MOVE_DOWN": "DOWN", "MOVE_LEFT": "LEFT", "MOVE_RIGHT": "RIGHT"}


def choose_action(observation):
    """Turn towards the enemy base, shoot if aligned with it, otherwise walk closer."""
    me, target = observation["my_tank"], observation["enemy_base"]
    dx, dy = target["x"] - me["x"], target["y"] - me["y"]

    if dx == 0 or dy == 0:
        step = (0 if dx == 0 else (1 if dx > 0 else -1), 0 if dy == 0 else (1 if dy > 0 else -1))
        move = MOVES[step]
        return "FIRE" if me["facing"] == FACING[move] else move

    if abs(dx) >= abs(dy):
        return "MOVE_RIGHT" if dx > 0 else "MOVE_LEFT"
    return "MOVE_DOWN" if dy > 0 else "MOVE_UP"
