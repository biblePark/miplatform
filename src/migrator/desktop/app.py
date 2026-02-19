from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any, Sequence

from .state import DesktopShellState
from .window import DesktopDependencyError, QtWidgetsModule, create_main_window, load_qt_widgets_module


@dataclass(slots=True)
class DesktopRuntime:
    app: Any
    window: Any
    state: DesktopShellState


def bootstrap_desktop_runtime(
    *,
    qt: QtWidgetsModule | None = None,
    state: DesktopShellState | None = None,
) -> DesktopRuntime:
    qt_widgets = qt or load_qt_widgets_module()
    runtime_state = state or DesktopShellState()
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    window = create_main_window(qt=qt_widgets, state=runtime_state)
    return DesktopRuntime(app=app, window=window, state=runtime_state)


def launch_desktop_shell(
    *,
    exec_event_loop: bool = True,
    qt: QtWidgetsModule | None = None,
    state: DesktopShellState | None = None,
) -> int:
    try:
        runtime = bootstrap_desktop_runtime(qt=qt, state=state)
    except DesktopDependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    runtime.window.show()
    if not exec_event_loop:
        return 0
    return int(runtime.app.exec())


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    return launch_desktop_shell(exec_event_loop=True)


__all__ = [
    "DesktopRuntime",
    "bootstrap_desktop_runtime",
    "launch_desktop_shell",
    "main",
]
