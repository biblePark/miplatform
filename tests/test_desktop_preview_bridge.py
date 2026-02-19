from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.desktop_preview_bridge import (  # noqa: E402
    DesktopPreviewBridge,
    DesktopPreviewBridgeConfig,
    DesktopPreviewUrlOpener,
    PreviewHostLaunchConfig,
    PreviewHostProcessError,
    PreviewHostProcessManager,
    PreviewHostStartTimeoutError,
    PreviewOpenResult,
    PreviewScreenSelectionError,
    build_preview_url,
    resolve_preview_host_dir_from_summary,
)


def _pick_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _write_preview_manifest(preview_host_dir: Path, screen_ids: list[str]) -> Path:
    manifest_path = preview_host_dir / "src" / "manifest" / "screens.manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "1.0",
        "generatedAtUtc": "2026-02-19T00:00:00+00:00",
        "screens": [
            {
                "screenId": screen_id,
                "entryModule": f"screens/generated/{screen_id}",
                "sourceXmlPath": f"data/input/xml/{screen_id}.xml",
                "sourceNodePath": f"/Screen[@id='{screen_id}']",
            }
            for screen_id in screen_ids
        ],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


class _FakeUrlOpener:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def open(
        self,
        url: str,
        *,
        screen_id: str,
        preview_host_dir: str,
        prefer_embedded: bool,
        parent_widget: object | None = None,
    ) -> PreviewOpenResult:
        self.calls.append(
            {
                "url": url,
                "screen_id": screen_id,
                "preview_host_dir": preview_host_dir,
                "prefer_embedded": prefer_embedded,
                "parent_widget": parent_widget,
            }
        )
        return PreviewOpenResult(
            url=url,
            mode="external",
            screen_id=screen_id,
            preview_host_dir=preview_host_dir,
        )


class _FakeProcessManager:
    def __init__(self, config: PreviewHostLaunchConfig) -> None:
        self.config = config
        self.started = False
        self.stop_calls = 0

    def start(self) -> str:
        self.started = True
        return self.config.base_url()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        _ = timeout_seconds
        self.started = False
        self.stop_calls += 1

    def check_health(self, *, timeout_seconds: float | None = None) -> bool:
        _ = timeout_seconds
        return self.started


class TestPreviewHostProcessManager(unittest.TestCase):
    def test_start_stop_and_health_check_with_python_http_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            port = _pick_free_port()
            config = PreviewHostLaunchConfig(
                preview_host_dir=tmp_dir,
                host="127.0.0.1",
                port=port,
                startup_timeout_seconds=5.0,
                poll_interval_seconds=0.1,
                start_command=(sys.executable, "-m", "http.server", "{port}"),
            )
            manager = PreviewHostProcessManager(config)
            try:
                base_url = manager.start()
                self.assertEqual(base_url, f"http://127.0.0.1:{port}")
                self.assertTrue(manager.is_running())
                self.assertTrue(manager.check_health())
            finally:
                manager.stop()
            self.assertFalse(manager.is_running())

    def test_start_raises_when_process_exits_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = PreviewHostLaunchConfig(
                preview_host_dir=tmp_dir,
                startup_timeout_seconds=2.0,
                poll_interval_seconds=0.05,
                start_command=(sys.executable, "-c", "import sys; sys.exit(3)"),
            )
            manager = PreviewHostProcessManager(config)
            with self.assertRaises(PreviewHostProcessError) as ctx:
                manager.start()
            self.assertIn("exited early", str(ctx.exception))
            self.assertFalse(manager.is_running())

    def test_start_raises_timeout_when_process_never_becomes_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = PreviewHostLaunchConfig(
                preview_host_dir=tmp_dir,
                startup_timeout_seconds=0.4,
                poll_interval_seconds=0.05,
                start_command=(sys.executable, "-c", "import time; time.sleep(30)"),
            )
            manager = PreviewHostProcessManager(config)
            with self.assertRaises(PreviewHostStartTimeoutError):
                manager.start()
            self.assertFalse(manager.is_running())


class TestDesktopPreviewBridge(unittest.TestCase):
    def test_resolve_preview_host_dir_from_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            preview_host_dir = workspace / "runs" / "job-001" / "preview-host"
            manifest_path = _write_preview_manifest(preview_host_dir, ["orders"])

            summary_path = workspace / "runs" / "job-001" / "summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "stages": {
                            "sync_preview": {
                                "status": "success",
                                "manifest_file": str(manifest_path),
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            resolved = resolve_preview_host_dir_from_summary(summary_path)
            self.assertEqual(resolved, preview_host_dir.resolve())

    def test_open_screen_preview_uses_selected_screen_and_run_summary_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            preview_host_dir = workspace / "runs" / "job-001" / "preview-host"
            manifest_path = _write_preview_manifest(preview_host_dir, ["orders", "detail"])
            summary_path = workspace / "runs" / "job-001" / "summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "stages": {
                            "sync_preview": {
                                "status": "success",
                                "manifest_file": str(manifest_path),
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            created_managers: list[_FakeProcessManager] = []

            def _factory(config: PreviewHostLaunchConfig) -> _FakeProcessManager:
                manager = _FakeProcessManager(config)
                created_managers.append(manager)
                return manager

            fake_opener = _FakeUrlOpener()
            bridge = DesktopPreviewBridge(
                config=DesktopPreviewBridgeConfig(
                    preview_host_dir="preview-host",
                    host="127.0.0.1",
                    port=43091,
                ),
                url_opener=fake_opener,
                process_manager_factory=_factory,
            )

            result = bridge.open_screen_preview(
                screen_id="orders",
                run_summary_file=summary_path,
                prefer_embedded=False,
            )
            self.assertEqual(result.mode, "external")
            self.assertEqual(result.url, "http://127.0.0.1:43091/preview/orders")
            self.assertEqual(result.screen_id, "orders")
            self.assertEqual(result.preview_host_dir, str(preview_host_dir.resolve()))
            self.assertEqual(len(fake_opener.calls), 1)
            self.assertEqual(fake_opener.calls[0]["screen_id"], "orders")
            self.assertEqual(len(created_managers), 1)
            self.assertTrue(created_managers[0].started)

            bridge.stop_preview_host()
            self.assertEqual(created_managers[0].stop_calls, 1)

    def test_open_screen_preview_rejects_unknown_screen_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            preview_host_dir = Path(tmp_dir) / "preview-host"
            _write_preview_manifest(preview_host_dir, ["orders"])
            fake_opener = _FakeUrlOpener()

            bridge = DesktopPreviewBridge(
                config=DesktopPreviewBridgeConfig(preview_host_dir=str(preview_host_dir)),
                url_opener=fake_opener,
                process_manager_factory=lambda config: _FakeProcessManager(config),
            )

            with self.assertRaises(PreviewScreenSelectionError):
                bridge.open_screen_preview(
                    screen_id="missing",
                    run_preview_host_dir=preview_host_dir,
                )
            self.assertEqual(fake_opener.calls, [])


class TestDesktopPreviewUrlOpener(unittest.TestCase):
    def test_open_falls_back_to_external_browser_when_embedded_view_unavailable(self) -> None:
        opener = DesktopPreviewUrlOpener(browser_open=lambda url, new=2: True)
        with mock.patch.object(opener, "_open_embedded_web_view", return_value=None):
            result = opener.open(
                "http://127.0.0.1:5173/preview/orders",
                screen_id="orders",
                preview_host_dir="/tmp/preview-host",
                prefer_embedded=True,
            )
        self.assertEqual(result.mode, "external")

    def test_open_prefers_embedded_view_when_available(self) -> None:
        opener = DesktopPreviewUrlOpener(browser_open=lambda url, new=2: False)
        with mock.patch.object(opener, "_open_embedded_web_view", return_value=object()):
            result = opener.open(
                "http://127.0.0.1:5173/preview/orders",
                screen_id="orders",
                preview_host_dir="/tmp/preview-host",
                prefer_embedded=True,
            )
        self.assertEqual(result.mode, "embedded")

    def test_build_preview_url_escapes_screen_id(self) -> None:
        url = build_preview_url("http://127.0.0.1:5173", "sales/report")
        self.assertEqual(url, "http://127.0.0.1:5173/preview/sales%2Freport")


if __name__ == "__main__":
    unittest.main()
