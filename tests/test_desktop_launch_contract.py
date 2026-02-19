from __future__ import annotations

import argparse
import builtins
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator import cli as migrator_cli  # noqa: E402


class TestDesktopLaunchContract(unittest.TestCase):
    def test_parser_accepts_desktop_shell_command(self) -> None:
        parser = migrator_cli.build_parser()
        args = parser.parse_args([migrator_cli.DESKTOP_SHELL_COMMAND_NAME, "--no-event-loop"])
        self.assertEqual(args.command, migrator_cli.DESKTOP_SHELL_COMMAND_NAME)
        self.assertTrue(args.no_event_loop)

    def test_run_desktop_shell_returns_contract_error_when_module_is_missing(self) -> None:
        stderr = io.StringIO()
        original_import = builtins.__import__

        def _mocked_import(
            name: str,
            globals_dict: dict[str, object] | None = None,
            locals_dict: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "migrator.desktop":
                raise ImportError("desktop module missing for contract smoke")
            return original_import(name, globals_dict, locals_dict, fromlist, level)

        with unittest.mock.patch("builtins.__import__", side_effect=_mocked_import):
            with redirect_stderr(stderr):
                rc = migrator_cli.run_desktop_shell(argparse.Namespace(no_event_loop=True))

        self.assertEqual(rc, 2)
        self.assertIn("Desktop shell module is unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
