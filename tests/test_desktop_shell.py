from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator import desktop as desktop_pkg  # noqa: E402
from migrator.desktop import app as desktop_app  # noqa: E402
from migrator.desktop.state import DesktopRunMode, DesktopShellState  # noqa: E402
from migrator.desktop.window import DesktopDependencyError  # noqa: E402


class _FakeApplication:
    _instance: "_FakeApplication | None" = None

    def __init__(self, _argv: list[str]) -> None:
        self.exec_calls = 0
        type(self)._instance = self

    @classmethod
    def instance(cls) -> "_FakeApplication | None":
        return cls._instance

    def exec(self) -> int:
        self.exec_calls += 1
        return 0


class _FakeWindow:
    def __init__(self) -> None:
        self.was_shown = False

    def show(self) -> None:
        self.was_shown = True


class TestDesktopStateModel(unittest.TestCase):
    def test_default_state_contains_single_and_batch_modes(self) -> None:
        state = DesktopShellState()
        self.assertEqual(state.run_plan.mode, DesktopRunMode.SINGLE_XML)
        self.assertIsNone(state.run_plan.single_xml.xml_path)
        self.assertIsNone(state.run_plan.batch_folder.folder_path)
        self.assertTrue(state.run_plan.batch_folder.recursive)
        self.assertEqual(state.run_plan.batch_folder.glob_pattern, "*.xml")

    def test_mode_switch_updates_status(self) -> None:
        state = DesktopShellState()
        state.set_mode(DesktopRunMode.BATCH_FOLDER)

        self.assertEqual(state.run_plan.mode, DesktopRunMode.BATCH_FOLDER)
        self.assertEqual(state.status.phase, "idle")
        self.assertIn("batch_folder", state.status.summary)


class TestDesktopBootstrap(unittest.TestCase):
    def setUp(self) -> None:
        _FakeApplication._instance = None

    def test_desktop_package_exports_launcher(self) -> None:
        self.assertTrue(hasattr(desktop_pkg, "launch_desktop_shell"))

    def test_launch_desktop_shell_bootstraps_without_event_loop(self) -> None:
        fake_window = _FakeWindow()
        fake_qt = SimpleNamespace(QApplication=_FakeApplication)
        state = DesktopShellState()

        with mock.patch.object(desktop_app, "create_main_window", return_value=fake_window):
            rc = desktop_app.launch_desktop_shell(
                exec_event_loop=False,
                qt=fake_qt,
                state=state,
            )

        self.assertEqual(rc, 0)
        self.assertTrue(fake_window.was_shown)

    def test_launch_desktop_shell_returns_error_when_qt_unavailable(self) -> None:
        with mock.patch.object(
            desktop_app,
            "load_qt_widgets_module",
            side_effect=DesktopDependencyError("PySide6 unavailable"),
        ):
            rc = desktop_app.launch_desktop_shell(exec_event_loop=False)

        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
