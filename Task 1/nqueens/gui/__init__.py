"""PyGame interface of Task 1; start it with `python main.py ui`."""


def run() -> None:
    """Open the window (PyGame is imported only here, so the solvers work without it)."""
    from .app import NQueensApp

    NQueensApp().run()
