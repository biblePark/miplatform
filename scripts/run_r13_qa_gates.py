#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys

DEFAULT_TEST_TARGETS: tuple[str, ...] = (
    "tests.test_desktop_launch_contract",
    "tests.test_runner_service_contract",
    "tests.test_orchestrator_api",
    "tests.test_cli",
    "tests.test_preview_smoke",
    "tests.test_prototype_acceptance",
    "tests.test_real_sample_e2e_regression",
    "tests.test_real_sample_baseline",
    "tests.test_report_view",
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_r13_qa_gates",
        description="Execute the R13 QA gate test set.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full test suite (`unittest discover`) instead of the R13 gate subset.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when a test failure is detected.",
    )
    return parser


def _build_unittest_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-m", "unittest"]
    if args.fail_fast:
        command.append("-f")
    command.append("-v")

    if args.full:
        command.extend(["discover", "-s", "tests"])
    else:
        command.extend(DEFAULT_TEST_TARGETS)
    return command


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    command = _build_unittest_command(args)
    print(f"[run_r13_qa_gates] {' '.join(command)}")
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
