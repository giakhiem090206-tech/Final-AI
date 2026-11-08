"""The search tree as it grows. Hover to read a node; click to jump to that moment of the search."""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

import pygame

from ..csp import KakuroCSP
from ..trace import SearchTree, TreeNode
from .theme import Theme, draw_text


class TreePanel:
    MAX_DRAWN = 3000

    def __init__(self, area: pygame.Rect) -> None:
        self.area = area
        self.tree: Optional[SearchTree] = None

    def set_tree(self, tree: SearchTree) -> None:
        self.tree = tree

    @property
    def _inner(self) -> pygame.Rect:
        return pygame.Rect(self.area.x + 14, self.area.y + 34, self.area.width - 28, self.area.height - 46)

    def _nodes(self) -> List[TreeNode]:
        return self.tree.nodes[:self.MAX_DRAWN]

    def _place(self, node: TreeNode) -> Tuple[int, int]:
        inner = self._inner
        columns = max(1, self.tree.leaves - 1)
        rows = max(1, self.tree.depth - 1)
        fraction = node.x / columns if self.tree.leaves > 1 else 0.5
        return int(inner.x + fraction * inner.width), int(inner.y + (node.depth - 1) / rows * inner.height)

    def node_at(self, point: Tuple[int, int], position: int) -> Optional[TreeNode]:
        """The nearest visible node within a few pixels of the mouse."""
        if not self.area.collidepoint(point) or self.tree is None:
            return None
        best, best_distance = None, 64
        for node in self._nodes():
            if node.born > position:
                continue
            x, y = self._place(node)
            distance = (x - point[0]) ** 2 + (y - point[1]) ** 2
            if distance < best_distance:
                best, best_distance = node, distance
        return best

    def draw(self, surface: pygame.Surface, position: int, csp: KakuroCSP) -> None:
        pygame.draw.rect(surface, Theme.PANEL, self.area, border_radius=10)
        draw_text(surface, "Search tree", (self.area.x + 12, self.area.y + 7), 14, Theme.TEXT, bold=True)
        total = len(self.tree.nodes)
        note = f"{total} assignments"
        if total > self.MAX_DRAWN:
            note += f", first {self.MAX_DRAWN} shown"
        draw_text(surface, note, (self.area.x + 100, self.area.y + 9), 12, Theme.MUTED)
        draw_text(surface, "hover to read, click to jump", (self.area.right - 12, self.area.y + 9), 12, Theme.FAINT,
                  right=True)

        nodes = self._nodes()
        if not nodes:
            return
        current = self._current_path(nodes, position)
        visible = [node for node in nodes if node.born <= position]
        for node in visible:
            if node.parent is None or node.parent >= len(nodes):
                continue
            failed = node.died is not None and node.died <= position
            color = Theme.BAD if failed else (Theme.ACCENT if id(node) in current else Theme.BORDER)
            self._draw_edge(surface, self._place(nodes[node.parent]), self._place(node), color,
                            2 if id(node) in current else 1)
        radius = 3 if len(nodes) < 400 else 2
        for node in visible:
            failed = node.died is not None and node.died <= position
            color = Theme.BAD if failed else (Theme.GOOD if node.solution else Theme.ACCENT)
            pygame.draw.circle(surface, color, self._place(node), radius)
        if current:
            newest = max((node for node in visible if id(node) in current), key=lambda n: n.depth)
            pygame.draw.circle(surface, Theme.TEXT, self._place(newest), radius + 3, 2)
        self._draw_hover(surface, position, csp)

    @staticmethod
    def _draw_edge(surface: pygame.Surface, start: Tuple[int, int], end: Tuple[int, int], color, width: int) -> None:
        """Right-angled edges keep long chains and wide branches readable at this small size."""
        if start[0] == end[0]:
            pygame.draw.line(surface, color, start, end, width)
            return
        pygame.draw.line(surface, color, start, (end[0], start[1]), width)
        pygame.draw.line(surface, color, (end[0], start[1]), end, width)

    def _current_path(self, nodes: List[TreeNode], position: int) -> Set[int]:
        """Nodes on the branch the search is on at this moment."""
        active = [node for node in nodes if node.born <= position and (node.died is None or node.died > position)]
        return {id(node) for node in active}

    def _draw_hover(self, surface: pygame.Surface, position: int, csp: KakuroCSP) -> None:
        node = self.node_at(pygame.mouse.get_pos(), position)
        if node is None:
            return
        x, y = self._place(node)
        pygame.draw.circle(surface, Theme.TEXT, (x, y), 5, 2)
        state = "failed" if node.died is not None and node.died <= position else "open"
        if node.solution:
            state = "on the solution"
        label = f"{csp.variable_name(node.variable)} = {node.value}, depth {node.depth}, {state}"
        width = 230
        box = pygame.Rect(min(max(x - width // 2, self.area.x + 4), self.area.right - width - 4), max(self.area.y + 28, y - 28),
                          width, 21)
        pygame.draw.rect(surface, Theme.CARD_HOVER, box, border_radius=4)
        draw_text(surface, label, box.center, 12, Theme.TEXT, center=True)
