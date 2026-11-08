"""The look of the 8-bit arcade tank games: pixel sprites and a pixel font, all drawn by code.

Nothing here is loaded from a file. Every sprite is drawn once on a 16 x 16 grid of "game
pixels" and then enlarged by a whole number, so that each game pixel stays a sharp square.
"""
from __future__ import annotations

import random
from typing import Dict, Optional, Tuple

import pygame

Color = Tuple[int, int, int]

FRAME_GREY = (99, 99, 99)
FRAME_LIGHT = (160, 160, 160)
FRAME_DARK = (58, 58, 58)
FIELD_BLACK = (0, 0, 0)
BRICK = (200, 72, 24)
BRICK_LIGHT = (240, 128, 64)
BRICK_MORTAR = (72, 20, 8)
TREAD = (52, 52, 52)
TREAD_MARK = (150, 150, 150)

SPRITE_SIZE = 16  # game pixels per tile

# Body, light and dark shade of each player's tank, and of the eagle that stands for the base.
TANK_COLORS: Tuple[Tuple[Color, Color, Color], ...] = (
    ((232, 192, 40), (252, 232, 128), (156, 112, 16)),   # player 1: yellow, as in the arcade original
    ((74, 168, 232), (172, 220, 252), (24, 88, 148)),    # player 2: blue
)

# ------------------------------------------------------------------------------ pixel font
_GLYPHS = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 11011 10001", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11110 00001 00001 01110 00001 00001 11110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    ":": "00000 00100 00100 00000 00100 00100 00000", "-": "00000 00000 00000 11111 00000 00000 00000",
    ".": "00000 00000 00000 00000 00000 01100 01100", "/": "00001 00001 00010 00100 01000 10000 10000",
    "+": "00000 00100 00100 11111 00100 00100 00000", "!": "00100 00100 00100 00100 00100 00000 00100",
    " ": "00000 00000 00000 00000 00000 00000 00000",
}
GLYPH_W, GLYPH_H, GLYPH_GAP = 5, 7, 1


def pixel_text_size(text: str, scale: int) -> Tuple[int, int]:
    width = max(0, len(text) * (GLYPH_W + GLYPH_GAP) - GLYPH_GAP)
    return width * scale, GLYPH_H * scale


def pixel_text(text: str, scale: int, color: Color) -> pygame.Surface:
    """Text in a 5 x 7 pixel font, each font pixel enlarged to scale x scale screen pixels."""
    width, height = pixel_text_size(text, scale)
    image = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
    for index, character in enumerate(text.upper()):
        rows = _GLYPHS.get(character, _GLYPHS[" "]).split()
        for y, row in enumerate(rows):
            for x, bit in enumerate(row):
                if bit == "1":
                    pygame.draw.rect(image, color, ((index * (GLYPH_W + GLYPH_GAP) + x) * scale, y * scale, scale, scale))
    return image


def draw_pixel_text(surface: pygame.Surface, text: str, position: Tuple[int, int], scale: int, color: Color,
                    center: bool = False, right: bool = False, shadow: Optional[Color] = None) -> pygame.Rect:
    image = pixel_text(text, scale, color)
    rect = image.get_rect(center=position) if center else (image.get_rect(topright=position) if right
                                                           else image.get_rect(topleft=position))
    if shadow is not None:
        surface.blit(pixel_text(text, scale, shadow), rect.move(scale, scale))
    surface.blit(image, rect)
    return rect


def brick_texture(size: Tuple[int, int], course: int = 4) -> pygame.Surface:
    """A wall of small bricks, used to fill the letters of the title."""
    image = pygame.Surface(size)
    image.fill(BRICK_MORTAR)
    brick_w = course * 2
    for row in range(size[1] // course + 1):
        offset = 0 if row % 2 == 0 else brick_w // 2
        for col in range(-1, size[0] // brick_w + 2):
            rect = pygame.Rect(col * brick_w + offset, row * course, brick_w - 1, course - 1)
            pygame.draw.rect(image, BRICK, rect)
            pygame.draw.line(image, BRICK_LIGHT, rect.topleft, (rect.right - 1, rect.y))
    return image


def brick_title(text: str, scale: int) -> pygame.Surface:
    """The title as the arcade shows it: block letters built out of bricks, with a shadow."""
    letters = pixel_text(text, scale, (255, 255, 255))
    mask = pygame.mask.from_surface(letters)
    bricks = brick_texture(letters.get_size(), max(2, scale)).convert_alpha()
    filled = mask.to_surface(setsurface=bricks, unsetcolor=(0, 0, 0, 0))
    shadow = mask.to_surface(setcolor=(40, 10, 4), unsetcolor=(0, 0, 0, 0))
    image = pygame.Surface((letters.get_width() + scale, letters.get_height() + scale), pygame.SRCALPHA)
    image.blit(shadow, (scale, scale))
    image.blit(filled, (0, 0))
    return image


# ----------------------------------------------------------------------------- sprites
def _canvas() -> pygame.Surface:
    return pygame.Surface((SPRITE_SIZE, SPRITE_SIZE), pygame.SRCALPHA)


def _tank_base(owner: int, frame: int) -> pygame.Surface:
    """A tank seen from above and facing up. The two frames differ in the tread marks only."""
    body, light, dark = TANK_COLORS[owner]
    image = _canvas()
    for x0 in (0, 13):  # treads
        pygame.draw.rect(image, TREAD, (x0, 1, 3, 15))
        for y in range(1 + frame, 16, 2):
            pygame.draw.line(image, TREAD_MARK, (x0, y), (x0 + 2, y))
    pygame.draw.rect(image, body, (3, 3, 10, 12))         # hull
    pygame.draw.rect(image, light, (3, 3, 10, 1))
    pygame.draw.rect(image, dark, (3, 14, 10, 1))
    pygame.draw.rect(image, dark, (3, 4, 1, 10))
    pygame.draw.rect(image, dark, (12, 4, 1, 10))
    for y in range(5, 14, 2):                             # a stipple, as the sprite sheets have
        for x in range(4 + (y // 2) % 2, 12, 2):
            image.set_at((x, y), dark)
    pygame.draw.rect(image, light, (5, 6, 6, 6))          # turret
    pygame.draw.rect(image, body, (6, 7, 4, 4))
    pygame.draw.rect(image, dark, (7, 8, 2, 2))
    pygame.draw.rect(image, light, (7, 0, 2, 7))          # barrel
    pygame.draw.rect(image, dark, (8, 0, 1, 7))
    pygame.draw.rect(image, (20, 20, 20), (7, 0, 2, 1))
    return image


def _mirrored(points):
    """A polygon given for the left half of the sprite, completed with its mirror image."""
    return list(points) + [(SPRITE_SIZE - x, y) for x, y in reversed(points)]


def _eagle_base(owner: int, alive: bool) -> pygame.Surface:
    """An eagle with spread wings, the emblem of the base; the colour on its breast is its owner's."""
    body, light, dark = TANK_COLORS[owner]
    image = _canvas()
    if not alive:  # a ruin: a few grey stones where the eagle stood
        rng = random.Random(7)
        for _ in range(22):
            x, y = rng.randint(2, 13), rng.randint(6, 14)
            image.set_at((x, y), rng.choice(((70, 70, 70), (110, 110, 110), (40, 40, 40))))
        return image
    silhouette = _mirrored([(8, 1), (6, 1), (5, 3), (4, 4), (2, 2), (0, 2), (1, 6), (2, 9), (5, 10), (5, 13),
                            (4, 15), (7, 14), (8, 15)])
    pygame.draw.polygon(image, light, silhouette)
    pygame.draw.polygon(image, dark, _mirrored([(2, 9), (5, 10), (5, 13), (4, 15), (7, 14), (8, 15), (8, 11), (4, 8)]))
    for x0, y0, x1, y1 in ((4, 5, 1, 4), (4, 7, 1, 6), (4, 9, 2, 8)):   # feathers along the wings
        pygame.draw.line(image, dark, (x0, y0), (x1, y1))
        pygame.draw.line(image, dark, (SPRITE_SIZE - 1 - x0, y0), (SPRITE_SIZE - 1 - x1, y1))
    pygame.draw.rect(image, body, (7, 5, 2, 7))                         # the breast
    pygame.draw.rect(image, (252, 160, 32), (7, 3, 2, 2))               # the beak
    for x in (6, 9):
        image.set_at((x, 2), (16, 16, 16))                              # the eyes
    outline = pygame.mask.from_surface(image).outline()
    for point in outline:
        image.set_at(point, (16, 16, 16))
    return image


def _brick_base(quadrants: Tuple[bool, bool, bool, bool]) -> pygame.Surface:
    """A tile of four 8 x 8 blocks of bricks; destroyed blocks are left out."""
    image = _canvas()
    for index, present in enumerate(quadrants):
        if not present:
            continue
        x0, y0 = (index % 2) * 8, (index // 2) * 8
        pygame.draw.rect(image, BRICK_MORTAR, (x0, y0, 8, 8))
        for row in range(2):
            offset = 0 if row == 0 else 2
            for col in range(-1, 2):
                rect = pygame.Rect(x0 + col * 4 + offset, y0 + row * 4, 3, 3).clip(pygame.Rect(x0, y0, 8, 8))
                if rect.width > 0 and rect.height > 0:
                    pygame.draw.rect(image, BRICK, rect)
                    pygame.draw.line(image, BRICK_LIGHT, rect.topleft, (rect.right - 1, rect.y))
    return image


def _blast_base(radius: int, seed: int) -> pygame.Surface:
    """A burst of fire made of rings of colour, ragged at its edge."""
    image = _canvas()
    rng = random.Random(seed)
    center = SPRITE_SIZE / 2 - 0.5
    rings = ((0.30, (255, 255, 255)), (0.55, (252, 232, 120)), (0.80, (248, 152, 32)), (1.0, (200, 48, 24)))
    for y in range(SPRITE_SIZE):
        for x in range(SPRITE_SIZE):
            distance = (abs(x - center) + abs(y - center)) / max(1, radius)
            if distance > 1.0 or (distance > 0.7 and rng.random() < 0.35):
                continue
            for limit, color in rings:
                if distance <= limit:
                    image.set_at((x, y), color)
                    break
    return image


def _bullet_base(owner: int) -> pygame.Surface:
    _, light, dark = TANK_COLORS[owner]
    image = _canvas()
    pygame.draw.rect(image, dark, (6, 4, 4, 8))
    pygame.draw.rect(image, light, (7, 4, 2, 8))
    pygame.draw.rect(image, (255, 255, 255), (7, 5, 2, 3))
    return image


class Sprites:
    """Every sprite of a game at one enlargement, made once and reused."""

    def __init__(self, scale: int) -> None:
        self.scale = max(1, scale)
        self.size = SPRITE_SIZE * self.scale
        self._cache: Dict[tuple, pygame.Surface] = {}

    def _scaled(self, image: pygame.Surface) -> pygame.Surface:
        return pygame.transform.scale(image, (self.size, self.size))

    def _get(self, key: tuple, build) -> pygame.Surface:
        if key not in self._cache:
            self._cache[key] = self._scaled(build())
        return self._cache[key]

    def tank(self, owner: int, angle: int, frame: int = 0) -> pygame.Surface:
        angle %= 360
        return self._get(("tank", owner, angle, frame % 2),
                         lambda: pygame.transform.rotate(_tank_base(owner, frame % 2), angle))

    def eagle(self, owner: int, alive: bool = True) -> pygame.Surface:
        return self._get(("eagle", owner, alive), lambda: _eagle_base(owner, alive))

    def bricks(self, hit_points: int) -> pygame.Surface:
        """Three hit points leave a full tile, two the right half, one a single block."""
        shape = {3: (True, True, True, True), 2: (False, True, False, True), 1: (False, True, False, False)}
        return self._get(("bricks", hit_points), lambda: _brick_base(shape[max(1, min(3, hit_points))]))

    def bullet(self, owner: int, angle: int) -> pygame.Surface:
        return self._get(("bullet", owner, angle % 360),
                         lambda: pygame.transform.rotate(_bullet_base(owner), angle % 360))

    def blast(self, stage: int, big: bool = False) -> pygame.Surface:
        """One frame of an explosion; a big one covers two tiles by two."""
        radii = (4, 7, 10, 8, 5) if big else (3, 5, 7, 4)
        radius = radii[min(stage, len(radii) - 1)]
        key = ("blast", big, stage)
        if key not in self._cache:
            base = _blast_base(radius, stage + (50 if big else 0))
            side = self.size * (2 if big else 1)
            self._cache[key] = pygame.transform.scale(base, (side, side))
        return self._cache[key]

    @staticmethod
    def blast_frames(big: bool) -> int:
        return 5 if big else 4

    def flag(self) -> pygame.Surface:
        """The stage flag shown beside the map name."""
        def build() -> pygame.Surface:
            image = _canvas()
            pygame.draw.rect(image, (230, 230, 230), (3, 1, 2, 14))
            pygame.draw.rect(image, (220, 40, 40), (5, 2, 8, 6))
            pygame.draw.rect(image, (252, 232, 128), (7, 4, 2, 2))
            pygame.draw.rect(image, (230, 230, 230), (1, 14, 7, 1))
            return image
        return self._get(("flag",), build)


def draw_frame(surface: pygame.Surface, arena: pygame.Rect, field: pygame.Rect) -> None:
    """The grey surround of the playfield, with a lit and a shaded edge, and the black field inside."""
    pygame.draw.rect(surface, FRAME_GREY, arena)
    pygame.draw.rect(surface, FRAME_LIGHT, arena, 2)
    pygame.draw.rect(surface, FRAME_DARK, field.inflate(4, 4))
    pygame.draw.rect(surface, FIELD_BLACK, field)
