"""Layout and timing shared by the screens."""

BOARD_PIXELS = 656  # 13 tiles of 48 pixels plus a grey frame of 16; smaller maps get larger tiles
PANEL_WIDTH = 350
TOP_BAR = 48
BOTTOM_BAR = 32
WINDOW_SIZE = (BOARD_PIXELS + PANEL_WIDTH, BOARD_PIXELS + TOP_BAR + BOTTOM_BAR)

HUMAN = "Human (keyboard)"
TIME_LIMITS = (0.05, 0.1, 0.2, 0.5, 1.0)
SERIES_LENGTHS = (1, 3, 5, 7)
ANIMATION_MS = (900, 450, 220, 90, 0)  # duration of a cycle at each speed setting
