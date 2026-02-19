from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Callable, Literal, Protocol, TextIO
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote
import webbrowser

from .preview_manifest import (
    ScreenManifestEntry,
    ScreensManifest,
    load_screens_manifest_file,
)


class PreviewBridgeError(RuntimeError):
    """Base error for desktop preview bridge operations."""


class PreviewHostProcessError(PreviewBridgeError):
    """Raised when preview-host process lifecycle fails."""


class PreviewHostStartTimeoutError(PreviewHostProcessError):
    """Raised when preview-host does not become healthy before timeout."""


class PreviewScreenSelectionError(PreviewBridgeError):
    """Raised when requested preview screen cannot be resolved."""


PreviewOpenMode = Literal["embedded", "external"]


@dataclass(frozen=True, slots=True)
class PreviewOpenResult:
    url: str
    mode: PreviewOpenMode
    screen_id: str
    preview_host_dir: str


@dataclass(frozen=True, slots=True)
class PreviewHostLaunchConfig:
    preview_host_dir: str
    host: str = "127.0.0.1"
    port: int = 4173
    health_path: str = "/"
    startup_timeout_seconds: float = 20.0
    poll_interval_seconds: float = 0.25
    request_timeout_seconds: float = 1.0
    start_command: tuple[str, ...] | None = None
    env_overrides: dict[str, str] | None = None
    log_file_name: str = ".mifl-preview-host.log"

    def resolved_preview_host_dir(self) -> Path:
        return Path(self.preview_host_dir).resolve()

    def resolved_log_file(self) -> Path:
        return (self.resolved_preview_host_dir() / self.log_file_name).resolve()

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def build_start_command(self) -> tuple[str, ...]:
        if self.start_command is None:
            return (
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                self.host,
                "--port",
                str(self.port),
                "--strictPort",
            )

        return tuple(token.format(host=self.host, port=self.port) for token in self.start_command)


def _tail_text(path: Path, *, line_limit: int) -> str:
    if line_limit <= 0 or not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return ""
    return "\n".join(lines[-line_limit:])


class PreviewHostProcessManager:
    def __init__(
        self,
        config: PreviewHostLaunchConfig,
        *,
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.config = config
        self._popen_factory = popen_factory
        self._process: subprocess.Popen[str] | None = None
        self._log_handle: TextIO | None = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def health_url(self) -> str:
        health_path = self.config.health_path
        if not health_path.startswith("/"):
            health_path = f"/{health_path}"
        return f"{self.config.base_url()}{health_path}"

    def check_health(self, *, timeout_seconds: float | None = None) -> bool:
        timeout = (
            self.config.request_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        try:
            request = urllib_request.Request(
                self.health_url(),
                method="GET",
                headers={"Accept": "text/html,application/json"},
            )
            with urllib_request.urlopen(request, timeout=timeout) as response:
                status_code = getattr(response, "status", 0)
                return int(status_code) >= 200 and int(status_code) < 400
        except (urllib_error.URLError, TimeoutError, OSError):
            return False

    def start(self) -> str:
        preview_host_dir = self.config.resolved_preview_host_dir()
        if not preview_host_dir.exists():
            raise FileNotFoundError(f"Preview host directory not found: {preview_host_dir}")
        if not preview_host_dir.is_dir():
            raise NotADirectoryError(f"Preview host path is not a directory: {preview_host_dir}")

        if self.config.start_command is None and not (preview_host_dir / "package.json").exists():
            raise PreviewHostProcessError(
                "Preview host directory must contain package.json for npm launch mode: "
                f"{preview_host_dir}"
            )

        if self.is_running() and self.check_health():
            return self.config.base_url()
        if self.is_running():
            self.stop()

        command = self.config.build_start_command()
        env = os.environ.copy()
        env.setdefault("BROWSER", "none")
        if self.config.env_overrides:
            env.update(self.config.env_overrides)

        self._close_log_handle()
        log_file = self.config.resolved_log_file()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = log_file.open("a", encoding="utf-8")

        try:
            self._process = self._popen_factory(
                command,
                cwd=str(preview_host_dir),
                stdout=self._log_handle,
                stderr=self._log_handle,
                stdin=subprocess.DEVNULL,
                text=True,
                env=env,
            )
        except FileNotFoundError as exc:
            self._close_log_handle()
            raise PreviewHostProcessError(
                "Failed to launch preview-host command. "
                f"Executable not found: {command[0]}"
            ) from exc
        except OSError as exc:
            self._close_log_handle()
            raise PreviewHostProcessError(
                f"Failed to launch preview-host command: {' '.join(command)}"
            ) from exc

        deadline = time.monotonic() + max(0.1, self.config.startup_timeout_seconds)
        poll_interval = max(0.05, self.config.poll_interval_seconds)
        while time.monotonic() <= deadline:
            if self.check_health():
                return self.config.base_url()
            process = self._process
            if process is not None and process.poll() is not None:
                exit_code = process.returncode
                log_tail = _tail_text(log_file, line_limit=30)
                self.stop()
                detail = f"preview-host exited early with code {exit_code}."
                if log_tail:
                    detail = f"{detail}\nRecent log tail:\n{log_tail}"
                raise PreviewHostProcessError(detail)
            time.sleep(poll_interval)

        log_tail = _tail_text(log_file, line_limit=30)
        self.stop()
        detail = (
            "preview-host did not become healthy before timeout "
            f"({self.config.startup_timeout_seconds:.2f}s)."
        )
        if log_tail:
            detail = f"{detail}\nRecent log tail:\n{log_tail}"
        raise PreviewHostStartTimeoutError(detail)

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        process = self._process
        self._process = None
        if process is None:
            self._close_log_handle()
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=max(0.1, timeout_seconds))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        self._close_log_handle()

    def _close_log_handle(self) -> None:
        if self._log_handle is None:
            return
        try:
            self._log_handle.close()
        finally:
            self._log_handle = None


def load_preview_manifest(preview_host_dir: str | Path) -> ScreensManifest:
    host_dir = Path(preview_host_dir).resolve()
    manifest_path = host_dir / "src" / "manifest" / "screens.manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "Preview manifest file not found. "
            f"Expected: {manifest_path}"
        )
    return load_screens_manifest_file(manifest_path)


def resolve_preview_host_dir_from_summary(summary_file: str | Path) -> Path:
    summary_path = Path(summary_file).resolve()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreviewBridgeError(f"Summary payload must be an object: {summary_path}")

    stages = payload.get("stages")
    if not isinstance(stages, dict):
        raise PreviewBridgeError(
            "Summary payload does not contain object field `stages`."
        )
    sync_preview = stages.get("sync_preview")
    if not isinstance(sync_preview, dict):
        raise PreviewBridgeError(
            "Summary payload does not contain object field `stages.sync_preview`."
        )
    manifest_file = sync_preview.get("manifest_file")
    if not isinstance(manifest_file, str) or not manifest_file.strip():
        raise PreviewBridgeError(
            "Summary payload does not contain string field `stages.sync_preview.manifest_file`."
        )

    manifest_path = Path(manifest_file).resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest file referenced by summary does not exist: {manifest_path}"
        )

    for ancestor in manifest_path.parents:
        expected = ancestor / "src" / "manifest" / "screens.manifest.json"
        if expected.resolve() == manifest_path:
            return ancestor.resolve()

    if (
        manifest_path.name == "screens.manifest.json"
        and manifest_path.parent.name == "manifest"
        and manifest_path.parent.parent.name == "src"
    ):
        return manifest_path.parent.parent.parent.resolve()

    raise PreviewBridgeError(
        "Unable to infer preview-host directory from summary manifest path. "
        f"manifest_file={manifest_path}"
    )


def build_preview_url(base_url: str, screen_id: str) -> str:
    cleaned_screen_id = screen_id.strip()
    if not cleaned_screen_id:
        raise PreviewScreenSelectionError("screen_id must be a non-empty string.")
    return f"{base_url.rstrip('/')}/preview/{quote(cleaned_screen_id, safe='-_')}"


def require_screen_entry(manifest: ScreensManifest, *, screen_id: str) -> ScreenManifestEntry:
    entry = manifest.find_screen(screen_id)
    if entry is None:
        available = ", ".join(sorted(screen.screen_id for screen in manifest.screens))
        raise PreviewScreenSelectionError(
            f"screenId `{screen_id}` was not found in preview manifest. "
            f"Available screenIds: [{available}]"
        )
    return entry


class PreviewUrlOpener(Protocol):
    def open(
        self,
        url: str,
        *,
        screen_id: str,
        preview_host_dir: str,
        prefer_embedded: bool,
        parent_widget: object | None = None,
    ) -> PreviewOpenResult:
        ...


class DesktopPreviewUrlOpener:
    def __init__(
        self,
        *,
        browser_open: Callable[..., bool] = webbrowser.open,
    ) -> None:
        self._browser_open = browser_open
        self._embedded_views: list[object] = []

    def open(
        self,
        url: str,
        *,
        screen_id: str,
        preview_host_dir: str,
        prefer_embedded: bool,
        parent_widget: object | None = None,
    ) -> PreviewOpenResult:
        if prefer_embedded:
            embedded_view = self._open_embedded_web_view(url, parent_widget=parent_widget)
            if embedded_view is not None:
                self._embedded_views.append(embedded_view)
                return PreviewOpenResult(
                    url=url,
                    mode="embedded",
                    screen_id=screen_id,
                    preview_host_dir=preview_host_dir,
                )

        opened = bool(self._browser_open(url, new=2))
        if not opened:
            raise PreviewBridgeError(f"Failed to open preview URL in external browser: {url}")
        return PreviewOpenResult(
            url=url,
            mode="external",
            screen_id=screen_id,
            preview_host_dir=preview_host_dir,
        )

    def _open_embedded_web_view(
        self,
        url: str,
        *,
        parent_widget: object | None = None,
    ) -> object | None:
        try:
            from PySide6.QtCore import QUrl  # type: ignore
            from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
            from PySide6.QtWidgets import QApplication  # type: ignore
        except Exception:
            return None

        app = QApplication.instance()
        if app is None:
            return None

        view = QWebEngineView(parent_widget)
        view.setWindowTitle("MIFL Preview")
        view.resize(1280, 840)
        view.setUrl(QUrl(url))
        view.show()
        return view


@dataclass(frozen=True, slots=True)
class DesktopPreviewBridgeConfig:
    preview_host_dir: str = "preview-host"
    host: str = "127.0.0.1"
    port: int = 4173
    health_path: str = "/"
    startup_timeout_seconds: float = 20.0
    poll_interval_seconds: float = 0.25
    request_timeout_seconds: float = 1.0
    start_command: tuple[str, ...] | None = None
    env_overrides: dict[str, str] | None = None


class DesktopPreviewBridge:
    def __init__(
        self,
        *,
        config: DesktopPreviewBridgeConfig | None = None,
        url_opener: PreviewUrlOpener | None = None,
        process_manager_factory: Callable[[PreviewHostLaunchConfig], PreviewHostProcessManager]
        | None = None,
    ) -> None:
        self.config = config or DesktopPreviewBridgeConfig()
        self._url_opener = url_opener or DesktopPreviewUrlOpener()
        self._process_manager_factory = process_manager_factory or PreviewHostProcessManager
        self._process_manager: PreviewHostProcessManager | None = None
        self._managed_preview_host_dir: Path | None = None

    def stop_preview_host(self) -> None:
        if self._process_manager is None:
            return
        self._process_manager.stop()
        self._process_manager = None
        self._managed_preview_host_dir = None

    def preview_host_is_healthy(self) -> bool:
        manager = self._process_manager
        if manager is None:
            return False
        return manager.check_health()

    def start_preview_host(
        self,
        *,
        run_summary_file: str | Path | None = None,
        run_preview_host_dir: str | Path | None = None,
    ) -> str:
        preview_host_dir = self._resolve_preview_host_dir(
            run_summary_file=run_summary_file,
            run_preview_host_dir=run_preview_host_dir,
        )
        manager = self._ensure_process_manager(preview_host_dir)
        return manager.start()

    def list_available_screens(
        self,
        *,
        run_summary_file: str | Path | None = None,
        run_preview_host_dir: str | Path | None = None,
    ) -> tuple[ScreenManifestEntry, ...]:
        preview_host_dir = self._resolve_preview_host_dir(
            run_summary_file=run_summary_file,
            run_preview_host_dir=run_preview_host_dir,
        )
        manifest = load_preview_manifest(preview_host_dir)
        return manifest.screens

    def open_screen_preview(
        self,
        *,
        screen_id: str,
        run_summary_file: str | Path | None = None,
        run_preview_host_dir: str | Path | None = None,
        prefer_embedded: bool = True,
        parent_widget: object | None = None,
    ) -> PreviewOpenResult:
        preview_host_dir = self._resolve_preview_host_dir(
            run_summary_file=run_summary_file,
            run_preview_host_dir=run_preview_host_dir,
        )
        manifest = load_preview_manifest(preview_host_dir)
        _ = require_screen_entry(manifest, screen_id=screen_id)

        manager = self._ensure_process_manager(preview_host_dir)
        base_url = manager.start()
        preview_url = build_preview_url(base_url, screen_id)
        return self._url_opener.open(
            preview_url,
            screen_id=screen_id,
            preview_host_dir=str(preview_host_dir),
            prefer_embedded=prefer_embedded,
            parent_widget=parent_widget,
        )

    def _resolve_preview_host_dir(
        self,
        *,
        run_summary_file: str | Path | None,
        run_preview_host_dir: str | Path | None,
    ) -> Path:
        if run_preview_host_dir is not None:
            resolved = Path(run_preview_host_dir).resolve()
            if not resolved.exists() or not resolved.is_dir():
                raise FileNotFoundError(
                    f"Run preview-host directory was not found: {resolved}"
                )
            return resolved

        if run_summary_file is not None:
            return resolve_preview_host_dir_from_summary(run_summary_file)

        default_dir = Path(self.config.preview_host_dir).resolve()
        if not default_dir.exists() or not default_dir.is_dir():
            raise FileNotFoundError(
                f"Default preview-host directory was not found: {default_dir}"
            )
        return default_dir

    def _ensure_process_manager(self, preview_host_dir: Path) -> PreviewHostProcessManager:
        if (
            self._process_manager is not None
            and self._managed_preview_host_dir is not None
            and self._managed_preview_host_dir == preview_host_dir
        ):
            return self._process_manager

        self.stop_preview_host()
        launch_config = PreviewHostLaunchConfig(
            preview_host_dir=str(preview_host_dir),
            host=self.config.host,
            port=self.config.port,
            health_path=self.config.health_path,
            startup_timeout_seconds=self.config.startup_timeout_seconds,
            poll_interval_seconds=self.config.poll_interval_seconds,
            request_timeout_seconds=self.config.request_timeout_seconds,
            start_command=self.config.start_command,
            env_overrides=self.config.env_overrides,
        )
        manager = self._process_manager_factory(launch_config)
        self._process_manager = manager
        self._managed_preview_host_dir = preview_host_dir
        return manager


__all__ = [
    "DesktopPreviewBridge",
    "DesktopPreviewBridgeConfig",
    "DesktopPreviewUrlOpener",
    "PreviewBridgeError",
    "PreviewHostLaunchConfig",
    "PreviewHostProcessError",
    "PreviewHostProcessManager",
    "PreviewHostStartTimeoutError",
    "PreviewOpenResult",
    "PreviewScreenSelectionError",
    "build_preview_url",
    "load_preview_manifest",
    "resolve_preview_host_dir_from_summary",
]
