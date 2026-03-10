from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Any, Sequence

from .desktop_batch_workflow import (
    COVERAGE_LEDGER_FILENAME,
    DEFAULT_XML_GLOB_PATTERN,
    BatchItemStatus,
    BatchRunHistoryEntry,
    BatchRunItemResult,
    BatchRunPlan,
    BatchRunPlanItem,
    BatchRunSummaryView,
    build_batch_run_plan,
    build_batch_summary_view,
    build_project_workspace_layout,
    build_failure_retry_plan,
    consolidate_batch_run_artifacts,
    list_batch_run_history,
    materialize_batch_run_layout,
    read_batch_run_plan,
    read_batch_summary_view,
    read_project_coverage_ledger,
    read_project_manifest,
    write_batch_summary_view,
)
from .desktop_preview_bridge import (
    DesktopPreviewBridge,
    DesktopPreviewBridgeConfig,
    build_preview_url,
)
from .preview_sync import sync_preview_host
from .runner_service import (
    TERMINAL_JOB_STATUSES,
    OrchestratorApiError,
    RunnerService,
)

try:  # pragma: no cover - optional dependency branch
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QCompleter,
        QComboBox,
        QFileDialog,
        QFrame,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QPlainTextEdit,
        QSplitter,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    _PYSIDE6_AVAILABLE = True
    _PYSIDE6_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency branch
    _PYSIDE6_AVAILABLE = False
    _PYSIDE6_IMPORT_ERROR = exc

if _PYSIDE6_AVAILABLE:  # pragma: no cover - optional dependency branch
    try:
        from PySide6.QtCore import QUrl  # type: ignore
        from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore

        _QT_WEBENGINE_AVAILABLE = True
    except Exception:
        QUrl = None  # type: ignore[assignment]
        QWebEngineView = None  # type: ignore[assignment]
        _QT_WEBENGINE_AVAILABLE = False
else:
    QUrl = None  # type: ignore[assignment]
    QWebEngineView = None  # type: ignore[assignment]
    _QT_WEBENGINE_AVAILABLE = False


def _require_pyside6() -> None:
    if _PYSIDE6_AVAILABLE:
        return
    message = "PySide6 is required for desktop file picker workflow."
    if _PYSIDE6_IMPORT_ERROR is None:
        raise RuntimeError(message)
    raise RuntimeError(message) from _PYSIDE6_IMPORT_ERROR


def _normalize_start_dir(start_dir: str | Path | None) -> str:
    if start_dir is None:
        return str(Path.cwd())
    candidate = Path(start_dir).expanduser()
    if candidate.is_file():
        return str(candidate.parent.resolve())
    if candidate.exists() and candidate.is_dir():
        return str(candidate.resolve())
    return str(candidate.parent.resolve())


def pick_source_xml_file(
    *,
    parent: Any = None,
    start_dir: str | Path | None = None,
) -> str | None:
    _require_pyside6()
    selected, _ = QFileDialog.getOpenFileName(
        parent,
        "Select Source XML File",
        _normalize_start_dir(start_dir),
        "XML Files (*.xml *.XML *.txt);;All Files (*)",
    )
    return selected or None


def pick_source_xml_dir(
    *,
    parent: Any = None,
    start_dir: str | Path | None = None,
) -> str | None:
    _require_pyside6()
    selected = QFileDialog.getExistingDirectory(
        parent,
        "Select Source XML Directory",
        _normalize_start_dir(start_dir),
    )
    return selected or None


def pick_output_dir(
    *,
    parent: Any = None,
    start_dir: str | Path | None = None,
) -> str | None:
    _require_pyside6()
    selected = QFileDialog.getExistingDirectory(
        parent,
        "Select Output Root Directory",
        _normalize_start_dir(start_dir),
    )
    return selected or None


_DEFAULT_KNOWN_TAGS_PATH = Path("data/input/profiles/known_tags.txt")
_DEFAULT_KNOWN_ATTRS_PATH = Path("data/input/profiles/known_attrs.json")
_DEFAULT_PREVIEW_HOST_DIRNAME = "preview-host"
_DEFAULT_SHARED_PREVIEW_SCREENS_DIRNAME = "_preview-generated-screens"
_SUPPORTED_SCREEN_MODULE_EXTENSIONS = {".tsx", ".jsx", ".ts", ".js"}
_PROJECT_KEY_AUTO_SENTINEL = "__AUTO_PROJECT_KEY__"
_PROJECT_KEY_AUTO_LABEL = "Auto (output-root name)"
_PROJECT_KEY_HISTORY_SCAN_LIMIT = 200
_DESKTOP_APP_STYLESHEET = """
QWidget {
  background: #f2f5fb;
  color: #152037;
  font-family: "Apple SD Gothic Neo", "Pretendard", "Malgun Gothic", sans-serif;
  font-size: 12px;
}
QLabel#titleLabel {
  font-size: 27px;
  font-weight: 700;
  color: #0f2447;
}
QLabel#subtitleLabel {
  font-size: 13px;
  color: #506489;
}
QLabel[class="sectionTitle"] {
  font-size: 15px;
  font-weight: 700;
  color: #15305f;
}
QLabel#summaryLabel {
  color: #3a517a;
  font-weight: 600;
}
QGroupBox {
  border: 1px solid #d3dff2;
  border-radius: 10px;
  margin-top: 12px;
  padding-top: 10px;
  background: #f9fbff;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 10px;
  top: 3px;
  padding: 0 4px;
  color: #274b84;
  font-weight: 700;
}
QFrame#heroCard,
QFrame#monitorCard,
QFrame#controlCard,
QFrame#historyHeaderCard,
QFrame#historyTableCard,
QFrame#historyDetailCard,
QFrame#previewHeaderCard,
QFrame#previewControlsCard,
QFrame#previewCanvasCard,
QFrame#previewMetaCard,
QFrame#kpiCard {
  border: 1px solid #d3dff2;
  border-radius: 10px;
  background: #f9fbff;
}
QLineEdit,
QComboBox,
QTableWidget,
QPlainTextEdit {
  border: 1px solid #c6d4ea;
  border-radius: 8px;
  background: #ffffff;
  padding: 5px 8px;
}
QLineEdit:focus,
QComboBox:focus,
QTableWidget:focus,
QPlainTextEdit:focus {
  border: 1px solid #5c8dee;
}
QTableWidget {
  gridline-color: #dde6f4;
  alternate-background-color: #f5f8ff;
}
QTableWidget::item:selected {
  background: #d8e7ff;
  color: #0f2447;
}
QTabWidget::pane {
  border: 1px solid #d3dff2;
  border-radius: 10px;
  background: #f9fbff;
  top: -1px;
}
QTabBar::tab {
  background: #e8eef9;
  border: 1px solid #c8d6ee;
  border-bottom: none;
  min-width: 120px;
  padding: 8px 12px;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: #2a4270;
  font-weight: 600;
}
QTabBar::tab:selected {
  background: #f9fbff;
  color: #0f2447;
}
QPushButton {
  border: 1px solid #aac1e6;
  border-radius: 8px;
  background: #edf3ff;
  color: #143367;
  font-weight: 600;
  padding: 7px 12px;
}
QPushButton:hover {
  background: #dfeaff;
}
QPushButton:disabled {
  color: #8596b3;
  border: 1px solid #d2dbea;
  background: #f1f4fa;
}
QPushButton#primaryActionButton {
  background: #2060ff;
  border: 1px solid #2060ff;
  color: #ffffff;
}
QPushButton#dangerActionButton {
  background: #ffeef1;
  border: 1px solid #efb2c0;
  color: #8c2138;
}
QLabel[class="kpiValue"] {
  font-size: 20px;
  font-weight: 700;
  color: #0f2447;
}
QLabel[class="kpiTitle"] {
  color: #536a92;
  font-size: 11px;
}
QLabel[class="metaLabel"] {
  color: #536a92;
  font-size: 11px;
  font-weight: 600;
}
QLabel[class="metaValue"] {
  color: #1e355d;
  font-size: 12px;
  font-weight: 600;
}
QProgressBar {
  border: 1px solid #c6d4ea;
  border-radius: 7px;
  background: #edf2fb;
  text-align: center;
  color: #143367;
  font-weight: 600;
}
QProgressBar::chunk {
  background-color: #2e6bff;
  border-radius: 6px;
}
QPlainTextEdit#logStreamView {
  background: #0f182b;
  color: #d8e3ff;
  border: 1px solid #1f3051;
  border-radius: 8px;
}
QPlainTextEdit#previewFallbackView {
  background: #f4f7ff;
  color: #20365d;
}
QSplitter::handle {
  background: #d8e2f5;
}
"""
_PIPELINE_STAGE_ORDER_UI: tuple[str, ...] = (
    "parse",
    "map_api",
    "gen_ui",
    "fidelity_audit",
    "sync_preview",
    "preview_smoke",
)
_HISTORY_FILTER_ALL = "__all__"
_HISTORY_FILTER_NONE = "__none__"


def list_known_project_keys(
    output_root: Path,
    *,
    history_limit: int = _PROJECT_KEY_HISTORY_SCAN_LIMIT,
) -> list[str]:
    resolved_output_root = output_root.expanduser().resolve()
    project_keys: set[str] = set()

    projects_root = resolved_output_root / "projects"
    if projects_root.exists() and projects_root.is_dir():
        for child in projects_root.iterdir():
            if not child.is_dir():
                continue
            key = child.name.strip()
            if key:
                project_keys.add(key)

    try:
        history_entries = list_batch_run_history(resolved_output_root, limit=history_limit)
    except Exception:
        history_entries = []
    for entry in history_entries:
        if entry.project_key:
            project_keys.add(entry.project_key)

    return sorted(project_keys, key=str.casefold)


def resolve_recent_project_key(
    output_root: Path,
    *,
    history_limit: int = _PROJECT_KEY_HISTORY_SCAN_LIMIT,
) -> str | None:
    resolved_output_root = output_root.expanduser().resolve()
    try:
        entries = list_batch_run_history(resolved_output_root, limit=history_limit)
    except Exception:
        return None
    for entry in entries:
        if entry.project_key:
            return entry.project_key
    return None


def resolve_workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / _DEFAULT_PREVIEW_HOST_DIRNAME).exists():
        return cwd
    return Path(__file__).resolve().parents[2]


def _resolve_optional_profile_file(workspace_root: Path, relative_path: Path) -> str | None:
    candidate = (workspace_root / relative_path).resolve()
    if candidate.exists() and candidate.is_file():
        return str(candidate)
    return None


def _map_job_status_to_batch_item_status(status: str | None) -> BatchItemStatus:
    if status in {"queued", "running", "succeeded", "failed", "canceled"}:
        return status
    return "failed"


@dataclass(frozen=True, slots=True)
class _PreviewTarget:
    queue_index: int
    xml_path: str
    preview_host_dir: str
    screen_ids: tuple[str, ...]


def build_batch_job_payloads(
    plan: BatchRunPlan,
    *,
    workspace_root: Path,
    strict: bool = True,
    capture_text: bool = True,
    render_policy_mode: str = "auto",
    pretty: bool = True,
    shared_preview_host_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    resolved_root = workspace_root.resolve()
    preview_host_source_dir = (resolved_root / _DEFAULT_PREVIEW_HOST_DIRNAME).resolve()
    if not preview_host_source_dir.exists() or not preview_host_source_dir.is_dir():
        raise FileNotFoundError(
            "Preview host source directory not found: "
            f"{preview_host_source_dir} "
            "(expected workspace-root/preview-host)."
        )

    known_tags_file = _resolve_optional_profile_file(resolved_root, _DEFAULT_KNOWN_TAGS_PATH)
    known_attrs_file = _resolve_optional_profile_file(resolved_root, _DEFAULT_KNOWN_ATTRS_PATH)
    shared_preview_host_path = (
        Path(shared_preview_host_dir).resolve()
        if shared_preview_host_dir is not None
        else None
    )

    payloads: list[dict[str, Any]] = []
    for item in plan.items:
        preview_host_dir = (
            str(shared_preview_host_path)
            if shared_preview_host_path is not None
            else item.output.preview_host_dir
        )
        payload: dict[str, Any] = {
            "xml_path": item.xml_path,
            "out_dir": item.output.out_dir,
            "api_out_dir": item.output.api_out_dir,
            "ui_out_dir": item.output.ui_out_dir,
            "preview_host_dir": preview_host_dir,
            "summary_out": item.output.summary_out,
            "strict": strict,
            "capture_text": capture_text,
            "render_policy_mode": render_policy_mode,
            "pretty": pretty,
            "use_isolated_preview_host": True,
            "preview_host_source_dir": str(preview_host_source_dir),
        }
        if known_tags_file:
            payload["known_tags_file"] = known_tags_file
        if known_attrs_file:
            payload["known_attrs_file"] = known_attrs_file
        payloads.append(payload)
    return payloads


if _PYSIDE6_AVAILABLE:  # pragma: no cover - UI integration is optional for CI
    class FilePickerBatchWorkflowWidget(QWidget):
        plan_generated = Signal(dict)
        summary_generated = Signal(dict)
        retry_plan_generated = Signal(dict)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("MIFL Migrator Desktop Batch Workflow")
            self._workspace_root = resolve_workspace_root()
            self._current_plan: BatchRunPlan | None = None
            self._current_summary: BatchRunSummaryView | None = None
            self._runner_service: RunnerService | None = None
            self._preview_bridge: DesktopPreviewBridge | None = None
            self._preview_targets: list[_PreviewTarget] = []
            self._shared_preview_host_dir: Path | None = None
            self._shared_preview_generated_screens_dir: Path | None = None
            self._syncing_preview_combo = False
            self._embedded_preview_view: Any | None = None
            self._active_jobs_by_queue_index: dict[int, str] = {}
            self._last_batch_schedule: dict[str, Any] | None = None
            self._history_entries: list[BatchRunHistoryEntry] = []
            self._job_snapshot_by_queue_index: dict[int, dict[str, Any]] = {}
            self._job_logs_by_job_id: dict[str, list[dict[str, Any]]] = {}
            self._last_project_consolidation: dict[str, Any] | None = None
            self._last_used_project_key: str | None = None
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(500)
            self._poll_timer.timeout.connect(self._poll_active_jobs)
            self._setup_ui()

        def _setup_ui(self) -> None:
            self.setStyleSheet(_DESKTOP_APP_STYLESHEET)
            root = QVBoxLayout(self)
            root.setContentsMargins(16, 14, 16, 16)
            root.setSpacing(12)

            hero_card = QFrame()
            hero_card.setObjectName("heroCard")
            hero_layout = QVBoxLayout(hero_card)
            hero_layout.setContentsMargins(14, 12, 14, 12)
            hero_layout.setSpacing(2)
            title = QLabel("MIFL Migrator Studio (Desktop)")
            title.setObjectName("titleLabel")
            subtitle = QLabel(
                "XML 배치 변환, 실시간 파이프라인 모니터링, 이력/미리보기까지 하나의 데스크톱 워크플로우"
            )
            subtitle.setObjectName("subtitleLabel")
            subtitle.setWordWrap(True)
            hero_layout.addWidget(title)
            hero_layout.addWidget(subtitle)
            root.addWidget(hero_card)

            self.main_tabs = QTabWidget()
            root.addWidget(self.main_tabs, 1)

            run_tab = QWidget()
            run_tab_layout = QVBoxLayout(run_tab)
            run_tab_layout.setContentsMargins(8, 8, 8, 8)
            run_tab_layout.setSpacing(10)

            splitter = QSplitter(Qt.Horizontal)
            run_tab_layout.addWidget(splitter, 1)

            control_panel = QFrame()
            control_panel.setObjectName("controlCard")
            control_layout = QVBoxLayout(control_panel)
            control_layout.setContentsMargins(14, 12, 14, 12)
            control_layout.setSpacing(10)
            setup_title = QLabel("Run Setup")
            setup_title.setProperty("class", "sectionTitle")
            control_layout.addWidget(setup_title)

            setup_group = QGroupBox("Source / Output")
            setup_form = QFormLayout(setup_group)
            setup_form.setContentsMargins(10, 12, 10, 10)
            setup_form.setHorizontalSpacing(12)
            setup_form.setVerticalSpacing(10)

            self.source_file_edit = QLineEdit()
            source_file_layout = QHBoxLayout()
            source_file_layout.setSpacing(8)
            source_file_layout.addWidget(self.source_file_edit, 1)
            browse_file_button = QPushButton("Browse File")
            browse_file_button.clicked.connect(self._select_source_file)
            source_file_layout.addWidget(browse_file_button)
            setup_form.addRow("Source XML file", source_file_layout)

            self.source_dir_edit = QLineEdit()
            default_source_dir = (self._workspace_root / "data" / "input" / "xml").resolve()
            if default_source_dir.exists():
                self.source_dir_edit.setText(str(default_source_dir))
            source_dir_layout = QHBoxLayout()
            source_dir_layout.setSpacing(8)
            source_dir_layout.addWidget(self.source_dir_edit, 1)
            browse_dir_button = QPushButton("Browse Folder")
            browse_dir_button.clicked.connect(self._select_source_dir)
            source_dir_layout.addWidget(browse_dir_button)
            setup_form.addRow("Source folder", source_dir_layout)

            self.recursive_checkbox = QCheckBox("Recursive folder scan")
            self.recursive_checkbox.setChecked(True)
            setup_form.addRow("", self.recursive_checkbox)

            self.glob_pattern_edit = QLineEdit(DEFAULT_XML_GLOB_PATTERN)
            setup_form.addRow("Folder glob pattern", self.glob_pattern_edit)

            self.output_dir_edit = QLineEdit()
            default_output_root = (self._workspace_root / "out").resolve()
            self.output_dir_edit.setText(str(default_output_root))
            self.output_dir_edit.editingFinished.connect(self._on_output_root_changed)
            output_dir_layout = QHBoxLayout()
            output_dir_layout.setSpacing(8)
            output_dir_layout.addWidget(self.output_dir_edit, 1)
            browse_output_button = QPushButton("Browse Output")
            browse_output_button.clicked.connect(self._select_output_dir)
            output_dir_layout.addWidget(browse_output_button)
            setup_form.addRow("Output root", output_dir_layout)

            self.project_key_combo = QComboBox()
            self.project_key_combo.setEditable(True)
            self.project_key_combo.setInsertPolicy(QComboBox.NoInsert)
            self.project_key_combo.setDuplicatesEnabled(False)
            self.project_key_combo.setPlaceholderText(
                "Select existing project or type a new key (optional)"
            )
            project_key_line_edit = self.project_key_combo.lineEdit()
            if project_key_line_edit is not None:
                project_key_line_edit.setPlaceholderText(
                    "Select existing project or type a new key (optional)"
                )
            project_key_completer = QCompleter(self.project_key_combo.model(), self.project_key_combo)
            project_key_completer.setCaseSensitivity(Qt.CaseInsensitive)
            project_key_completer.setFilterMode(Qt.MatchContains)
            self.project_key_combo.setCompleter(project_key_completer)
            setup_form.addRow("Project key", self.project_key_combo)

            self.run_id_edit = QLineEdit()
            self.run_id_edit.setPlaceholderText("Optional deterministic run id")
            setup_form.addRow("Run id", self.run_id_edit)

            policy_group = QGroupBox("Migration Policy")
            policy_layout = QVBoxLayout(policy_group)
            policy_layout.setContentsMargins(10, 12, 10, 10)
            self.strict_mode_checkbox = QCheckBox("Strict fidelity gate")
            self.strict_mode_checkbox.setChecked(False)
            policy_layout.addWidget(self.strict_mode_checkbox)
            policy_hint = QLabel("모드/게이트는 변환 정확도와 생성 속도의 트레이드오프에 영향을 줍니다.")
            policy_hint.setWordWrap(True)
            policy_hint.setObjectName("subtitleLabel")
            policy_layout.addWidget(policy_hint)

            control_layout.addWidget(setup_group)
            control_layout.addWidget(policy_group)

            button_grid = QGridLayout()
            button_grid.setHorizontalSpacing(8)
            button_grid.setVerticalSpacing(8)

            self.plan_button = QPushButton("Generate Batch Plan")
            self.plan_button.clicked.connect(self._generate_plan)
            button_grid.addWidget(self.plan_button, 0, 0)

            self.new_batch_button = QPushButton("Start New Batch")
            self.new_batch_button.clicked.connect(self._start_new_batch_plan)
            button_grid.addWidget(self.new_batch_button, 0, 1)

            self.retry_plan_button = QPushButton("Generate Failure Retry Plan")
            self.retry_plan_button.setEnabled(False)
            self.retry_plan_button.clicked.connect(self._generate_retry_plan)
            button_grid.addWidget(self.retry_plan_button, 1, 0)

            self.run_button = QPushButton("Run Batch Migration")
            self.run_button.setObjectName("primaryActionButton")
            self.run_button.setEnabled(False)
            self.run_button.clicked.connect(self._run_current_plan)
            button_grid.addWidget(self.run_button, 1, 1)

            self.cancel_button = QPushButton("Cancel Active Batch")
            self.cancel_button.setObjectName("dangerActionButton")
            self.cancel_button.setEnabled(False)
            self.cancel_button.clicked.connect(self._cancel_active_batch)
            button_grid.addWidget(self.cancel_button, 2, 0, 1, 2)

            control_layout.addLayout(button_grid)
            control_layout.addStretch(1)

            monitor_panel = QFrame()
            monitor_panel.setObjectName("monitorCard")
            monitor_layout = QVBoxLayout(monitor_panel)
            monitor_layout.setContentsMargins(14, 12, 14, 12)
            monitor_layout.setSpacing(10)
            monitor_title = QLabel("Live Pipeline Monitor")
            monitor_title.setProperty("class", "sectionTitle")
            monitor_layout.addWidget(monitor_title)

            self.summary_label = QLabel("Summary: no plan")
            self.summary_label.setObjectName("summaryLabel")
            monitor_layout.addWidget(self.summary_label)

            self.live_status_label = QLabel("Pipeline: idle")
            self.live_status_label.setObjectName("subtitleLabel")
            monitor_layout.addWidget(self.live_status_label)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p% completed")
            monitor_layout.addWidget(self.progress_bar)

            kpi_row = QHBoxLayout()
            kpi_row.setSpacing(8)
            self.kpi_total = QLabel("0")
            self.kpi_running = QLabel("0")
            self.kpi_succeeded = QLabel("0")
            self.kpi_failed = QLabel("0")
            self.kpi_canceled = QLabel("0")
            self.kpi_retryable = QLabel("0")
            kpi_specs = [
                ("Total", self.kpi_total),
                ("Running", self.kpi_running),
                ("Succeeded", self.kpi_succeeded),
                ("Failed", self.kpi_failed),
                ("Canceled", self.kpi_canceled),
                ("Retryable", self.kpi_retryable),
            ]
            for title_text, value_label in kpi_specs:
                card = QFrame()
                card.setObjectName("kpiCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(10, 8, 10, 8)
                card_layout.setSpacing(0)
                title_label = QLabel(title_text)
                title_label.setProperty("class", "kpiTitle")
                value_label.setProperty("class", "kpiValue")
                value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                card_layout.addWidget(title_label)
                card_layout.addWidget(value_label)
                kpi_row.addWidget(card)
            monitor_layout.addLayout(kpi_row)

            self.queue_table = QTableWidget(0, 4)
            self.queue_table.setHorizontalHeaderLabels(
                ["#", "XML path", "Status", "Summary output"]
            )
            self.queue_table.setAlternatingRowColors(True)
            self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.queue_table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            queue_header = self.queue_table.horizontalHeader()
            queue_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            queue_header.setSectionResizeMode(1, QHeaderView.Stretch)
            queue_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            queue_header.setSectionResizeMode(3, QHeaderView.Stretch)
            self.queue_table.itemSelectionChanged.connect(self._on_queue_row_changed)
            monitor_layout.addWidget(self.queue_table, 2)

            monitor_tabs = QTabWidget()
            self.stage_table = QTableWidget(0, 2)
            self.stage_table.setHorizontalHeaderLabels(["Stage", "Status"])
            self.stage_table.setAlternatingRowColors(True)
            self.stage_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.stage_table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.stage_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            stage_header = self.stage_table.horizontalHeader()
            stage_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            stage_header.setSectionResizeMode(1, QHeaderView.Stretch)
            monitor_tabs.addTab(self.stage_table, "Stage Status")

            self.live_log_view = QPlainTextEdit()
            self.live_log_view.setObjectName("logStreamView")
            self.live_log_view.setReadOnly(True)
            self.live_log_view.setPlaceholderText(
                "실시간 로그 스트림이 여기에 표시됩니다."
            )
            monitor_tabs.addTab(self.live_log_view, "Log Stream")

            self.contract_preview = QPlainTextEdit()
            self.contract_preview.setReadOnly(True)
            self.contract_preview.setPlaceholderText("Plan/summary/runtime contract JSON")
            monitor_tabs.addTab(self.contract_preview, "Contract JSON")
            monitor_layout.addWidget(monitor_tabs, 2)

            splitter.addWidget(control_panel)
            splitter.addWidget(monitor_panel)
            splitter.setSizes([560, 1040])

            history_tab = QWidget()
            history_tab_layout = QVBoxLayout(history_tab)
            history_tab_layout.setContentsMargins(8, 8, 8, 8)
            history_tab_layout.setSpacing(10)

            history_header_card = QFrame()
            history_header_card.setObjectName("historyHeaderCard")
            history_header_layout = QVBoxLayout(history_header_card)
            history_header_layout.setContentsMargins(12, 10, 12, 10)
            history_header_layout.setSpacing(8)
            history_title = QLabel("Run History")
            history_title.setProperty("class", "sectionTitle")
            history_header_layout.addWidget(history_title)
            history_intro = QLabel(
                "이전 배치 실행 결과를 탐색하고 선택한 실행을 현재 작업 컨텍스트로 다시 로드할 수 있습니다."
            )
            history_intro.setWordWrap(True)
            history_intro.setObjectName("subtitleLabel")
            history_header_layout.addWidget(history_intro)

            history_controls = QHBoxLayout()
            self.history_refresh_button = QPushButton("Refresh History")
            self.history_refresh_button.clicked.connect(self._refresh_history_entries)
            history_controls.addWidget(self.history_refresh_button)

            self.history_load_button = QPushButton("Load Selected Run")
            self.history_load_button.setEnabled(False)
            self.history_load_button.clicked.connect(self._load_selected_history_entry)
            history_controls.addWidget(self.history_load_button)

            history_controls.addWidget(QLabel("Project"))
            self.history_project_filter_combo = QComboBox()
            self.history_project_filter_combo.addItem("All projects", _HISTORY_FILTER_ALL)
            self.history_project_filter_combo.currentIndexChanged.connect(
                self._on_history_project_filter_changed
            )
            history_controls.addWidget(self.history_project_filter_combo)
            history_controls.addStretch(1)
            history_header_layout.addLayout(history_controls)

            self.history_status_label = QLabel("History: not loaded")
            self.history_status_label.setObjectName("summaryLabel")
            history_header_layout.addWidget(self.history_status_label)

            history_kpi_row = QHBoxLayout()
            history_kpi_row.setSpacing(8)
            self.history_runs_value = QLabel("0")
            self.history_selected_run_value = QLabel("-")
            self.history_selected_total_value = QLabel("0")
            self.history_selected_success_value = QLabel("0")
            self.history_selected_failed_value = QLabel("0")
            self.history_selected_canceled_value = QLabel("0")
            history_kpi_specs = [
                ("Runs", self.history_runs_value),
                ("Selected", self.history_selected_run_value),
                ("Items", self.history_selected_total_value),
                ("Succeeded", self.history_selected_success_value),
                ("Failed", self.history_selected_failed_value),
                ("Canceled", self.history_selected_canceled_value),
            ]
            for title_text, value_label in history_kpi_specs:
                card = QFrame()
                card.setObjectName("kpiCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(10, 8, 10, 8)
                card_layout.setSpacing(0)
                title_label = QLabel(title_text)
                title_label.setProperty("class", "kpiTitle")
                value_label.setProperty("class", "kpiValue")
                value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                card_layout.addWidget(title_label)
                card_layout.addWidget(value_label)
                history_kpi_row.addWidget(card)
            history_header_layout.addLayout(history_kpi_row)
            history_tab_layout.addWidget(history_header_card)

            history_splitter = QSplitter(Qt.Horizontal)
            history_tab_layout.addWidget(history_splitter, 1)

            history_table_card = QFrame()
            history_table_card.setObjectName("historyTableCard")
            history_table_layout = QVBoxLayout(history_table_card)
            history_table_layout.setContentsMargins(12, 10, 12, 12)
            history_table_layout.setSpacing(8)
            history_table_title = QLabel("History Table")
            history_table_title.setProperty("class", "sectionTitle")
            history_table_layout.addWidget(history_table_title)
            history_table_hint = QLabel("가장 최근 실행이 상단에 표시됩니다.")
            history_table_hint.setObjectName("subtitleLabel")
            history_table_layout.addWidget(history_table_hint)

            self.history_table = QTableWidget(0, 8)
            self.history_table.setHorizontalHeaderLabels(
                [
                    "Run ID",
                    "Project",
                    "Generated UTC",
                    "Total",
                    "Succeeded",
                    "Failed",
                    "Canceled",
                    "Run Root",
                ]
            )
            self.history_table.setAlternatingRowColors(True)
            self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            history_header = self.history_table.horizontalHeader()
            history_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
            history_header.setSectionResizeMode(7, QHeaderView.Stretch)
            self.history_table.itemSelectionChanged.connect(self._on_history_row_changed)
            history_table_layout.addWidget(self.history_table, 1)

            history_detail_card = QFrame()
            history_detail_card.setObjectName("historyDetailCard")
            history_detail_layout = QVBoxLayout(history_detail_card)
            history_detail_layout.setContentsMargins(12, 10, 12, 12)
            history_detail_layout.setSpacing(8)
            history_detail_title = QLabel("Selected Run Detail")
            history_detail_title.setProperty("class", "sectionTitle")
            history_detail_layout.addWidget(history_detail_title)

            history_meta_grid = QGridLayout()
            history_meta_grid.setHorizontalSpacing(12)
            history_meta_grid.setVerticalSpacing(6)

            history_meta_run_label = QLabel("Run ID")
            history_meta_run_label.setProperty("class", "metaLabel")
            self.history_detail_run_value = QLabel("-")
            self.history_detail_run_value.setProperty("class", "metaValue")
            self.history_detail_run_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            history_meta_grid.addWidget(history_meta_run_label, 0, 0)
            history_meta_grid.addWidget(self.history_detail_run_value, 0, 1)

            history_meta_generated_label = QLabel("Generated")
            history_meta_generated_label.setProperty("class", "metaLabel")
            self.history_detail_generated_value = QLabel("-")
            self.history_detail_generated_value.setProperty("class", "metaValue")
            self.history_detail_generated_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            history_meta_grid.addWidget(history_meta_generated_label, 2, 0)
            history_meta_grid.addWidget(self.history_detail_generated_value, 2, 1)

            history_meta_project_label = QLabel("Project")
            history_meta_project_label.setProperty("class", "metaLabel")
            self.history_detail_project_value = QLabel("-")
            self.history_detail_project_value.setProperty("class", "metaValue")
            self.history_detail_project_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            history_meta_grid.addWidget(history_meta_project_label, 1, 0)
            history_meta_grid.addWidget(self.history_detail_project_value, 1, 1)

            history_meta_totals_label = QLabel("Counts")
            history_meta_totals_label.setProperty("class", "metaLabel")
            self.history_detail_totals_value = QLabel("-")
            self.history_detail_totals_value.setProperty("class", "metaValue")
            self.history_detail_totals_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            history_meta_grid.addWidget(history_meta_totals_label, 3, 0)
            history_meta_grid.addWidget(self.history_detail_totals_value, 3, 1)

            history_meta_root_label = QLabel("Run Root")
            history_meta_root_label.setProperty("class", "metaLabel")
            self.history_detail_root_value = QLabel("-")
            self.history_detail_root_value.setProperty("class", "metaValue")
            self.history_detail_root_value.setWordWrap(True)
            self.history_detail_root_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            history_meta_grid.addWidget(history_meta_root_label, 4, 0)
            history_meta_grid.addWidget(self.history_detail_root_value, 4, 1)
            history_detail_layout.addLayout(history_meta_grid)

            history_detail_tabs = QTabWidget()

            history_contract_tab = QWidget()
            history_contract_layout = QVBoxLayout(history_contract_tab)
            history_contract_layout.setContentsMargins(0, 0, 0, 0)
            history_contract_layout.setSpacing(6)
            self.history_contract_preview = QPlainTextEdit()
            self.history_contract_preview.setReadOnly(True)
            self.history_contract_preview.setPlaceholderText("Selected history run contract preview")
            history_contract_layout.addWidget(self.history_contract_preview, 1)
            history_detail_tabs.addTab(history_contract_tab, "Contract JSON")

            history_coverage_tab = QWidget()
            history_coverage_layout = QVBoxLayout(history_coverage_tab)
            history_coverage_layout.setContentsMargins(0, 0, 0, 0)
            history_coverage_layout.setSpacing(6)
            self.history_coverage_status_label = QLabel(
                "Coverage: select a project run to load coverage-ledger.json"
            )
            self.history_coverage_status_label.setObjectName("subtitleLabel")
            history_coverage_layout.addWidget(self.history_coverage_status_label)

            self.history_coverage_render_bar = QProgressBar()
            self.history_coverage_render_bar.setRange(0, 100)
            self.history_coverage_render_bar.setValue(0)
            self.history_coverage_render_bar.setFormat("UI rendered coverage: %p%")
            history_coverage_layout.addWidget(self.history_coverage_render_bar)

            self.history_coverage_totals_table = QTableWidget(0, 2)
            self.history_coverage_totals_table.setHorizontalHeaderLabels(["Metric", "Value"])
            self.history_coverage_totals_table.setAlternatingRowColors(True)
            self.history_coverage_totals_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.history_coverage_totals_table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.history_coverage_totals_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            history_coverage_totals_header = self.history_coverage_totals_table.horizontalHeader()
            history_coverage_totals_header.setSectionResizeMode(0, QHeaderView.Stretch)
            history_coverage_totals_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            history_coverage_layout.addWidget(self.history_coverage_totals_table, 1)

            self.history_coverage_runs_table = QTableWidget(0, 7)
            self.history_coverage_runs_table.setHorizontalHeaderLabels(
                [
                    "Run",
                    "Generated",
                    "Items",
                    "Parse UnknownTag",
                    "Parse UnknownAttr",
                    "UI UnsupportedEvent",
                    "UI UnsupportedTagWarn",
                ]
            )
            self.history_coverage_runs_table.setAlternatingRowColors(True)
            self.history_coverage_runs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.history_coverage_runs_table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.history_coverage_runs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            history_coverage_runs_header = self.history_coverage_runs_table.horizontalHeader()
            history_coverage_runs_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            history_coverage_runs_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            history_coverage_runs_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            history_coverage_runs_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            history_coverage_runs_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
            history_coverage_runs_header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
            history_coverage_runs_header.setSectionResizeMode(6, QHeaderView.Stretch)
            history_coverage_layout.addWidget(self.history_coverage_runs_table, 1)

            self.history_coverage_warnings_view = QPlainTextEdit()
            self.history_coverage_warnings_view.setReadOnly(True)
            self.history_coverage_warnings_view.setPlaceholderText("Coverage warnings")
            history_coverage_layout.addWidget(self.history_coverage_warnings_view, 1)

            history_detail_tabs.addTab(history_coverage_tab, "Coverage Ledger")
            history_detail_layout.addWidget(history_detail_tabs, 1)

            history_splitter.addWidget(history_table_card)
            history_splitter.addWidget(history_detail_card)
            history_splitter.setSizes([1040, 680])

            preview_tab = QWidget()
            preview_tab_layout = QVBoxLayout(preview_tab)
            preview_tab_layout.setContentsMargins(8, 8, 8, 8)
            preview_tab_layout.setSpacing(10)

            preview_header_card = QFrame()
            preview_header_card.setObjectName("previewHeaderCard")
            preview_header_layout = QVBoxLayout(preview_header_card)
            preview_header_layout.setContentsMargins(12, 10, 12, 10)
            preview_header_layout.setSpacing(8)
            preview_title = QLabel("Preview Workspace")
            preview_title.setProperty("class", "sectionTitle")
            preview_header_layout.addWidget(preview_title)
            preview_subtitle = QLabel(
                "변환 산출물의 실제 화면 렌더링을 검증하는 전용 탭입니다. "
                "Batch Run 상태와 분리되어 있어 결과 검토에 집중할 수 있습니다."
            )
            preview_subtitle.setWordWrap(True)
            preview_subtitle.setObjectName("subtitleLabel")
            preview_header_layout.addWidget(preview_subtitle)

            preview_notice = QLabel(
                "안내: 미리보기는 preview-host의 npm 의존성 설치가 필요합니다. "
                "오프라인 환경에서는 변환/리포트 확인만 가능할 수 있습니다."
            )
            preview_notice.setWordWrap(True)
            preview_notice.setObjectName("subtitleLabel")
            preview_header_layout.addWidget(preview_notice)

            preview_kpi_row = QHBoxLayout()
            preview_kpi_row.setSpacing(8)
            self.preview_items_value = QLabel("0")
            self.preview_screens_value = QLabel("0")
            self.preview_mode_value = QLabel("-")
            preview_kpi_specs = [
                ("Targets", self.preview_items_value),
                ("Screen IDs", self.preview_screens_value),
                ("Last Open", self.preview_mode_value),
            ]
            for title_text, value_label in preview_kpi_specs:
                card = QFrame()
                card.setObjectName("kpiCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(10, 8, 10, 8)
                card_layout.setSpacing(0)
                title_label = QLabel(title_text)
                title_label.setProperty("class", "kpiTitle")
                value_label.setProperty("class", "kpiValue")
                value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                card_layout.addWidget(title_label)
                card_layout.addWidget(value_label)
                preview_kpi_row.addWidget(card)
            preview_header_layout.addLayout(preview_kpi_row)
            preview_tab_layout.addWidget(preview_header_card)

            preview_controls_card = QFrame()
            preview_controls_card.setObjectName("previewControlsCard")
            preview_controls_layout = QVBoxLayout(preview_controls_card)
            preview_controls_layout.setContentsMargins(12, 10, 12, 10)
            preview_controls_layout.setSpacing(8)
            preview_controls_title = QLabel("Preview Controls")
            preview_controls_title.setProperty("class", "sectionTitle")
            preview_controls_layout.addWidget(preview_controls_title)

            preview_control_grid = QGridLayout()
            preview_control_grid.setHorizontalSpacing(8)
            preview_control_grid.setVerticalSpacing(8)
            target_label = QLabel("Target Item")
            target_label.setProperty("class", "metaLabel")
            preview_control_grid.addWidget(target_label, 0, 0)
            self.preview_item_combo = QComboBox()
            self.preview_item_combo.setEditable(False)
            self.preview_item_combo.currentIndexChanged.connect(self._on_preview_item_changed)
            preview_control_grid.addWidget(self.preview_item_combo, 0, 1, 1, 2)

            screen_label = QLabel("screenId")
            screen_label.setProperty("class", "metaLabel")
            preview_control_grid.addWidget(screen_label, 1, 0)
            self.preview_screen_combo = QComboBox()
            self.preview_screen_combo.setEditable(True)
            self.preview_screen_combo.setPlaceholderText("screenId")
            preview_control_grid.addWidget(self.preview_screen_combo, 1, 1, 1, 2)

            self.embed_preview_checkbox = QCheckBox("Embed WebView")
            self.embed_preview_checkbox.setChecked(True)
            preview_control_grid.addWidget(self.embed_preview_checkbox, 2, 1)

            self.refresh_screens_button = QPushButton("Refresh Screens")
            self.refresh_screens_button.clicked.connect(self._refresh_preview_screens)
            preview_control_grid.addWidget(self.refresh_screens_button, 0, 3)

            self.open_preview_button = QPushButton("Open Preview")
            self.open_preview_button.setObjectName("primaryActionButton")
            self.open_preview_button.clicked.connect(self._open_selected_preview)
            preview_control_grid.addWidget(self.open_preview_button, 1, 3, 2, 1)
            preview_control_grid.setColumnStretch(2, 1)
            preview_controls_layout.addLayout(preview_control_grid)

            self.preview_status_label = QLabel("Preview: idle")
            self.preview_status_label.setObjectName("summaryLabel")
            preview_controls_layout.addWidget(self.preview_status_label)
            preview_tab_layout.addWidget(preview_controls_card)

            preview_splitter = QSplitter(Qt.Horizontal)
            preview_tab_layout.addWidget(preview_splitter, 1)

            preview_canvas_card = QFrame()
            preview_canvas_card.setObjectName("previewCanvasCard")
            preview_canvas_layout = QVBoxLayout(preview_canvas_card)
            preview_canvas_layout.setContentsMargins(12, 10, 12, 12)
            preview_canvas_layout.setSpacing(8)
            preview_canvas_title = QLabel("Embedded Preview")
            preview_canvas_title.setProperty("class", "sectionTitle")
            preview_canvas_layout.addWidget(preview_canvas_title)
            preview_canvas_hint = QLabel(
                "실제 React preview route를 임베드합니다. 복잡한 폼은 전체 캔버스를 스크롤하며 확인하세요."
            )
            preview_canvas_hint.setObjectName("subtitleLabel")
            preview_canvas_hint.setWordWrap(True)
            preview_canvas_layout.addWidget(preview_canvas_hint)

            if _QT_WEBENGINE_AVAILABLE and QWebEngineView is not None:
                self._embedded_preview_view = QWebEngineView(self)
                self._embedded_preview_view.setMinimumHeight(840)
                preview_canvas_layout.addWidget(self._embedded_preview_view, 1)
            else:
                self._embedded_preview_view = None
                preview_canvas_layout.addWidget(
                    QLabel(
                        "Embedded WebView unavailable (PySide6.QtWebEngineWidgets missing). "
                        "External browser mode only."
                    )
                )

            preview_meta_card = QFrame()
            preview_meta_card.setObjectName("previewMetaCard")
            preview_meta_layout = QVBoxLayout(preview_meta_card)
            preview_meta_layout.setContentsMargins(12, 10, 12, 12)
            preview_meta_layout.setSpacing(8)
            preview_meta_title = QLabel("Preview Route / Diagnostics")
            preview_meta_title.setProperty("class", "sectionTitle")
            preview_meta_layout.addWidget(preview_meta_title)

            preview_meta_grid = QGridLayout()
            preview_meta_grid.setHorizontalSpacing(8)
            preview_meta_grid.setVerticalSpacing(6)

            preview_route_label = QLabel("Route")
            preview_route_label.setProperty("class", "metaLabel")
            self.preview_route_value = QLabel("/preview/:screenId")
            self.preview_route_value.setProperty("class", "metaValue")
            self.preview_route_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            preview_meta_grid.addWidget(preview_route_label, 0, 0)
            preview_meta_grid.addWidget(self.preview_route_value, 0, 1)

            preview_host_label = QLabel("Preview Host")
            preview_host_label.setProperty("class", "metaLabel")
            self.preview_host_value = QLabel("-")
            self.preview_host_value.setProperty("class", "metaValue")
            self.preview_host_value.setWordWrap(True)
            self.preview_host_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            preview_meta_grid.addWidget(preview_host_label, 1, 0)
            preview_meta_grid.addWidget(self.preview_host_value, 1, 1)

            preview_manifest_label = QLabel("Manifest")
            preview_manifest_label.setProperty("class", "metaLabel")
            self.preview_manifest_value = QLabel("-")
            self.preview_manifest_value.setProperty("class", "metaValue")
            self.preview_manifest_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            preview_meta_grid.addWidget(preview_manifest_label, 2, 0)
            preview_meta_grid.addWidget(self.preview_manifest_value, 2, 1)
            preview_meta_layout.addLayout(preview_meta_grid)

            self.preview_fallback_view = QPlainTextEdit()
            self.preview_fallback_view.setObjectName("previewFallbackView")
            self.preview_fallback_view.setReadOnly(True)
            self.preview_fallback_view.setPlaceholderText("Preview URL / status / errors")
            preview_meta_layout.addWidget(self.preview_fallback_view, 1)

            preview_splitter.addWidget(preview_canvas_card)
            preview_splitter.addWidget(preview_meta_card)
            preview_splitter.setSizes([1280, 420])

            self.main_tabs.addTab(run_tab, "Batch Run")
            self.main_tabs.addTab(history_tab, "History")
            self.preview_tab_index = self.main_tabs.addTab(preview_tab, "Preview")
            self.main_tabs.setTabEnabled(self.preview_tab_index, False)
            self._refresh_history_entries()

        def _show_error(self, message: str) -> None:
            QMessageBox.critical(self, "Batch Workflow Error", message)

        def _infer_start_dir(self, raw_value: str) -> str | None:
            value = raw_value.strip()
            if not value:
                return None
            return value

        def _selected_project_key_input(self) -> str | None:
            current_text = self.project_key_combo.currentText().strip()
            current_index = self.project_key_combo.currentIndex()
            current_data = self.project_key_combo.itemData(current_index)
            if (
                isinstance(current_data, str)
                and current_data == _PROJECT_KEY_AUTO_SENTINEL
                and current_text == _PROJECT_KEY_AUTO_LABEL
            ):
                return None
            if not current_text or current_text == _PROJECT_KEY_AUTO_LABEL:
                return None
            return current_text

        def _set_project_key_selection(
            self,
            project_key: str | None,
            *,
            remember: bool = True,
        ) -> None:
            normalized_key = (project_key or "").strip() or None
            if normalized_key is not None and remember:
                self._last_used_project_key = normalized_key

            self.project_key_combo.blockSignals(True)
            if normalized_key is None:
                auto_index = self.project_key_combo.findData(_PROJECT_KEY_AUTO_SENTINEL)
                if auto_index >= 0:
                    self.project_key_combo.setCurrentIndex(auto_index)
                else:
                    self.project_key_combo.setCurrentIndex(-1)
                    self.project_key_combo.setEditText("")
                self.project_key_combo.blockSignals(False)
                return

            matching_index = self.project_key_combo.findData(normalized_key)
            if matching_index >= 0:
                self.project_key_combo.setCurrentIndex(matching_index)
            else:
                self.project_key_combo.setCurrentIndex(-1)
                self.project_key_combo.setEditText(normalized_key)
            self.project_key_combo.blockSignals(False)

        def _refresh_project_key_options(self, *, preferred_key: str | None = None) -> None:
            output_root_value = self.output_dir_edit.text().strip()
            if not output_root_value:
                return

            output_root = Path(output_root_value).expanduser().resolve()
            known_keys = list_known_project_keys(output_root)
            effective_preferred = (preferred_key or "").strip() or None
            if effective_preferred is None:
                current_value = self._selected_project_key_input()
                effective_preferred = (
                    current_value
                    or self._last_used_project_key
                    or resolve_recent_project_key(output_root)
                )
            if effective_preferred and effective_preferred not in known_keys:
                known_keys = sorted({*known_keys, effective_preferred}, key=str.casefold)

            self.project_key_combo.blockSignals(True)
            self.project_key_combo.clear()
            self.project_key_combo.addItem(_PROJECT_KEY_AUTO_LABEL, _PROJECT_KEY_AUTO_SENTINEL)
            for key in known_keys:
                self.project_key_combo.addItem(key, key)
            self.project_key_combo.blockSignals(False)
            self._set_project_key_selection(effective_preferred, remember=False)

        def _on_output_root_changed(self) -> None:
            self._refresh_history_entries()

        def _is_batch_running(self) -> bool:
            return bool(self._active_jobs_by_queue_index)

        def _ensure_runner_service(self) -> RunnerService:
            if self._runner_service is None:
                self._runner_service = RunnerService(workspace_root=self._workspace_root)
            return self._runner_service

        def _ensure_preview_bridge(self) -> DesktopPreviewBridge:
            if self._preview_bridge is None:
                self._preview_bridge = DesktopPreviewBridge(
                    config=DesktopPreviewBridgeConfig(
                        preview_host_dir=str((self._workspace_root / _DEFAULT_PREVIEW_HOST_DIRNAME).resolve())
                    )
                )
            return self._preview_bridge

        def _selected_plan_item(self) -> BatchRunPlanItem | None:
            plan = self._current_plan
            if plan is None or not plan.items:
                return None
            row_index = self.queue_table.currentRow()
            if row_index < 0:
                row_index = 0
            if row_index >= len(plan.items):
                return None
            return plan.items[row_index]

        def _set_preview_tab_enabled(self, enabled: bool) -> None:
            self.main_tabs.setTabEnabled(self.preview_tab_index, enabled)
            if not enabled and self.main_tabs.currentIndex() == self.preview_tab_index:
                self.main_tabs.setCurrentIndex(0)

        def _current_screen_id_input(self) -> str | None:
            current = self.preview_screen_combo.currentText().strip()
            if not current:
                return None
            return current

        def _selected_preview_target(self) -> _PreviewTarget | None:
            if not self._preview_targets:
                return None
            selected_queue_index = self.preview_item_combo.currentData()
            if isinstance(selected_queue_index, int):
                for target in self._preview_targets:
                    if target.queue_index == selected_queue_index:
                        return target
            return self._preview_targets[0]

        def _resolve_shared_preview_host_dir(self) -> Path:
            if self._current_plan is None:
                raise RuntimeError("Batch plan is required before building preview workspace.")
            return (Path(self._current_plan.output.run_root_dir) / _DEFAULT_PREVIEW_HOST_DIRNAME).resolve()

        def _resolve_shared_preview_screens_dir(self) -> Path:
            if self._current_plan is None:
                raise RuntimeError("Batch plan is required before building preview workspace.")
            return (
                Path(self._current_plan.output.run_root_dir) / _DEFAULT_SHARED_PREVIEW_SCREENS_DIRNAME
            ).resolve()

        def _iter_screen_module_files(self, screen_dir: Path) -> list[Path]:
            return sorted(
                path
                for path in screen_dir.rglob("*")
                if path.is_file()
                and path.suffix in _SUPPORTED_SCREEN_MODULE_EXTENSIONS
                and not path.name.endswith(".d.ts")
            )

        def _build_shared_preview_workspace(self) -> None:
            plan = self._current_plan
            if plan is None:
                self._shared_preview_host_dir = None
                self._shared_preview_generated_screens_dir = None
                return

            source_preview_host_dir = (self._workspace_root / _DEFAULT_PREVIEW_HOST_DIRNAME).resolve()
            if not source_preview_host_dir.exists() or not source_preview_host_dir.is_dir():
                raise FileNotFoundError(
                    f"Preview host source directory not found: {source_preview_host_dir}"
                )

            shared_preview_host_dir = self._resolve_shared_preview_host_dir()
            shared_screens_dir = self._resolve_shared_preview_screens_dir()

            if shared_preview_host_dir.exists():
                shutil.rmtree(shared_preview_host_dir)
            shutil.copytree(
                source_preview_host_dir,
                shared_preview_host_dir,
                symlinks=True,
            )

            if shared_screens_dir.exists():
                shutil.rmtree(shared_screens_dir)
            shared_screens_dir.mkdir(parents=True, exist_ok=True)

            for item in plan.items:
                source_screens_dir = Path(item.output.ui_out_dir) / "src" / "screens"
                if not source_screens_dir.exists() or not source_screens_dir.is_dir():
                    continue
                for module_path in self._iter_screen_module_files(source_screens_dir):
                    relative_module = module_path.relative_to(source_screens_dir)
                    proxy_module = shared_screens_dir / item.output.item_key / relative_module
                    proxy_module.parent.mkdir(parents=True, exist_ok=True)

                    import_target = module_path.with_suffix("")
                    relative_import = os.path.relpath(
                        str(import_target),
                        start=str(proxy_module.parent),
                    )
                    relative_import_posix = Path(relative_import).as_posix()
                    if not relative_import_posix.startswith("."):
                        relative_import_posix = f"./{relative_import_posix}"
                    proxy_module.write_text(
                        (
                            "/* Auto-generated preview proxy module. */\n"
                            f'export {{ default }} from "{relative_import_posix}";\n'
                        ),
                        encoding="utf-8",
                    )

                    source_metadata = module_path.with_suffix(".preview.json")
                    if source_metadata.exists() and source_metadata.is_file():
                        shutil.copy2(
                            source_metadata,
                            proxy_module.with_suffix(".preview.json"),
                        )

            sync_preview_host(
                generated_screens_dir=shared_screens_dir,
                preview_host_dir=shared_preview_host_dir,
                pretty=True,
            )

            for item in plan.items:
                item_preview_host_dir = Path(item.output.preview_host_dir).resolve()
                if item_preview_host_dir == shared_preview_host_dir:
                    continue
                if item_preview_host_dir.exists() and item_preview_host_dir.is_dir():
                    shutil.rmtree(item_preview_host_dir, ignore_errors=True)

            self._shared_preview_host_dir = shared_preview_host_dir
            self._shared_preview_generated_screens_dir = shared_screens_dir

        def _collect_preview_targets(self) -> list[_PreviewTarget]:
            shared_preview_host_dir = self._shared_preview_host_dir
            if shared_preview_host_dir is None:
                return []
            bridge = self._ensure_preview_bridge()
            screens = bridge.list_available_screens(run_preview_host_dir=shared_preview_host_dir)
            screen_ids = tuple(entry.screen_id for entry in screens if entry.screen_id.strip())
            if not screen_ids:
                return []
            return [
                _PreviewTarget(
                    queue_index=1,
                    xml_path="Batch Preview",
                    preview_host_dir=str(shared_preview_host_dir),
                    screen_ids=screen_ids,
                )
            ]

        def _populate_preview_screen_ids(self, target: _PreviewTarget | None) -> None:
            self.preview_screen_combo.clear()
            if target is None:
                return
            for screen_id in target.screen_ids:
                self.preview_screen_combo.addItem(screen_id)

        def _set_preview_inventory_kpis(self) -> None:
            total_targets = len(self._preview_targets)
            total_screens = sum(len(item.screen_ids) for item in self._preview_targets)
            self.preview_items_value.setText(str(total_targets))
            self.preview_screens_value.setText(str(total_screens))

        def _set_preview_target_meta(self, target: _PreviewTarget | None) -> None:
            if target is None:
                self.preview_route_value.setText("/preview/:screenId")
                self.preview_route_value.setToolTip("")
                self.preview_host_value.setText("-")
                self.preview_host_value.setToolTip("")
                self.preview_manifest_value.setText("-")
                return
            host_dir = str(Path(target.preview_host_dir).resolve())
            self.preview_host_value.setText(host_dir)
            self.preview_host_value.setToolTip(host_dir)
            self.preview_manifest_value.setText(
                f"row #{target.queue_index}: {len(target.screen_ids)} screenId(s)"
            )

        def _clear_history_coverage_widgets(self) -> None:
            self.history_coverage_status_label.setText(
                "Coverage: select a project run to load coverage-ledger.json"
            )
            self.history_coverage_render_bar.setValue(0)
            self.history_coverage_render_bar.setFormat("UI rendered coverage: %p%")
            self.history_coverage_totals_table.setRowCount(0)
            self.history_coverage_runs_table.setRowCount(0)
            self.history_coverage_warnings_view.clear()

        def _resolve_history_coverage_ledger_path(
            self,
            entry: BatchRunHistoryEntry,
        ) -> tuple[Path | None, list[str]]:
            notes: list[str] = []
            manifest_payload = None
            manifest_path: Path | None = None
            if entry.project_manifest_file:
                manifest_path = Path(entry.project_manifest_file).expanduser().resolve()
                if manifest_path.exists() and manifest_path.is_file():
                    try:
                        manifest_payload = read_project_manifest(manifest_path)
                    except Exception as exc:
                        notes.append(f"manifest_load_failed: {exc}")
                    else:
                        last_ledger_file = manifest_payload.last_coverage_ledger_file
                        if isinstance(last_ledger_file, str) and last_ledger_file.strip():
                            ledger_candidate = Path(last_ledger_file).expanduser()
                            if not ledger_candidate.is_absolute():
                                ledger_candidate = (manifest_path.parent / ledger_candidate).resolve()
                            else:
                                ledger_candidate = ledger_candidate.resolve()
                            return ledger_candidate, notes
                else:
                    notes.append("manifest_missing")

            if entry.project_root_dir:
                project_root = Path(entry.project_root_dir).expanduser().resolve()
                return project_root / COVERAGE_LEDGER_FILENAME, notes

            if entry.project_key:
                output_root = self._resolve_history_output_root()
                layout = build_project_workspace_layout(output_root, project_key=entry.project_key)
                return Path(layout.coverage_ledger_file).resolve(), notes

            return None, notes

        def _update_history_coverage_widgets(self, entry: BatchRunHistoryEntry | None) -> None:
            if entry is None:
                self._clear_history_coverage_widgets()
                return
            if entry.project_key is None and not entry.project_root_dir and not entry.project_manifest_file:
                self._clear_history_coverage_widgets()
                self.history_coverage_status_label.setText(
                    "Coverage: legacy run(no project) does not provide project coverage ledger."
                )
                return

            ledger_path, notes = self._resolve_history_coverage_ledger_path(entry)
            if ledger_path is None:
                self._clear_history_coverage_widgets()
                self.history_coverage_status_label.setText(
                    "Coverage: ledger path could not be resolved for selected run."
                )
                if notes:
                    self.history_coverage_warnings_view.setPlainText("\n".join(notes))
                return
            if not ledger_path.exists() or not ledger_path.is_file():
                self._clear_history_coverage_widgets()
                self.history_coverage_status_label.setText(
                    f"Coverage: ledger not found ({ledger_path})"
                )
                if notes:
                    self.history_coverage_warnings_view.setPlainText("\n".join(notes))
                return

            try:
                ledger = read_project_coverage_ledger(ledger_path)
            except Exception as exc:
                self._clear_history_coverage_widgets()
                self.history_coverage_status_label.setText(
                    f"Coverage: failed to parse ledger ({exc})"
                )
                if notes:
                    self.history_coverage_warnings_view.setPlainText("\n".join(notes))
                return

            self.history_coverage_status_label.setText(
                "Coverage: "
                f"project={ledger.project_key}, runs={ledger.total_runs}, items={ledger.total_items}"
            )
            rendered_percent = 0
            if ledger.ui_total_nodes > 0:
                rendered_percent = int((ledger.ui_rendered_nodes / ledger.ui_total_nodes) * 100)
            self.history_coverage_render_bar.setValue(max(0, min(100, rendered_percent)))
            self.history_coverage_render_bar.setFormat(
                f"UI rendered coverage: {ledger.ui_rendered_nodes}/{ledger.ui_total_nodes} (%p%)"
            )

            totals_rows = [
                ("Total Runs", str(ledger.total_runs)),
                ("Total Items", str(ledger.total_items)),
                ("Parse Total Nodes", str(ledger.parse_total_nodes)),
                ("Parse Unknown Tags", str(ledger.parse_unknown_tag_count)),
                ("Parse Unknown Attrs", str(ledger.parse_unknown_attr_count)),
                ("UI Total Nodes", str(ledger.ui_total_nodes)),
                ("UI Rendered Nodes", str(ledger.ui_rendered_nodes)),
                ("UI Unsupported Events", str(ledger.ui_unsupported_event_bindings)),
                ("UI Unsupported Tag Warnings", str(ledger.ui_unsupported_tag_warning_count)),
                ("Unique Unknown Tags", str(len(ledger.unique_unknown_tags))),
                ("Unique Unknown Attrs", str(len(ledger.unique_unknown_attrs))),
                ("Unique UI Unsupported Tags", str(len(ledger.unique_ui_unsupported_tags))),
            ]
            self.history_coverage_totals_table.setRowCount(len(totals_rows))
            for row_index, (metric, value) in enumerate(totals_rows):
                self.history_coverage_totals_table.setItem(row_index, 0, QTableWidgetItem(metric))
                self.history_coverage_totals_table.setItem(row_index, 1, QTableWidgetItem(value))

            self.history_coverage_runs_table.setRowCount(len(ledger.runs))
            for row_index, run in enumerate(ledger.runs):
                self.history_coverage_runs_table.setItem(row_index, 0, QTableWidgetItem(run.run_id))
                self.history_coverage_runs_table.setItem(row_index, 1, QTableWidgetItem(run.generated_at_utc))
                self.history_coverage_runs_table.setItem(row_index, 2, QTableWidgetItem(str(run.total_items)))
                self.history_coverage_runs_table.setItem(
                    row_index, 3, QTableWidgetItem(str(run.parse_unknown_tag_count))
                )
                self.history_coverage_runs_table.setItem(
                    row_index, 4, QTableWidgetItem(str(run.parse_unknown_attr_count))
                )
                self.history_coverage_runs_table.setItem(
                    row_index, 5, QTableWidgetItem(str(run.ui_unsupported_event_bindings))
                )
                self.history_coverage_runs_table.setItem(
                    row_index, 6, QTableWidgetItem(str(run.ui_unsupported_tag_warning_count))
                )

            warning_lines: list[str] = []
            warning_lines.extend(notes)
            warning_lines.extend(ledger.warnings)
            if ledger.unique_unknown_tags:
                warning_lines.append(
                    "unique_unknown_tags: " + ", ".join(ledger.unique_unknown_tags[:60])
                )
            if ledger.unique_unknown_attrs:
                warning_lines.append(
                    "unique_unknown_attrs: " + ", ".join(ledger.unique_unknown_attrs[:60])
                )
            if ledger.unique_ui_unsupported_tags:
                warning_lines.append(
                    "unique_ui_unsupported_tags: " + ", ".join(ledger.unique_ui_unsupported_tags[:60])
                )
            if warning_lines:
                self.history_coverage_warnings_view.setPlainText("\n".join(warning_lines))
            else:
                self.history_coverage_warnings_view.setPlainText("No coverage warnings.")

        def _reset_history_detail_widgets(self) -> None:
            self.history_selected_run_value.setText("-")
            self.history_selected_total_value.setText("0")
            self.history_selected_success_value.setText("0")
            self.history_selected_failed_value.setText("0")
            self.history_selected_canceled_value.setText("0")
            self.history_detail_run_value.setText("-")
            self.history_detail_project_value.setText("-")
            self.history_detail_generated_value.setText("-")
            self.history_detail_totals_value.setText("-")
            self.history_detail_root_value.setText("-")
            self.history_detail_root_value.setToolTip("")
            self.history_contract_preview.clear()
            self._clear_history_coverage_widgets()

        def _set_history_selection_kpis(self, entry: BatchRunHistoryEntry | None) -> None:
            if entry is None:
                self._reset_history_detail_widgets()
                return
            self.history_selected_run_value.setText(entry.run_id)
            self.history_selected_total_value.setText(str(entry.total_items))
            self.history_selected_success_value.setText(str(entry.succeeded_count))
            self.history_selected_failed_value.setText(str(entry.failed_count))
            self.history_selected_canceled_value.setText(str(entry.canceled_count))
            self.history_detail_run_value.setText(entry.run_id)
            self.history_detail_project_value.setText(entry.project_key or "-")
            self.history_detail_generated_value.setText(entry.generated_at_utc)
            self.history_detail_totals_value.setText(
                f"total={entry.total_items}, succeeded={entry.succeeded_count}, "
                f"failed={entry.failed_count}, canceled={entry.canceled_count}"
            )
            self.history_detail_root_value.setText(entry.run_root_dir)
            self.history_detail_root_value.setToolTip(entry.run_root_dir)

        def _on_queue_row_changed(self) -> None:
            if self._syncing_preview_combo:
                return
            selected_item = self._selected_plan_item()
            if selected_item is None:
                self._refresh_live_monitoring_panel()
                return
            for index in range(self.preview_item_combo.count()):
                queue_index = self.preview_item_combo.itemData(index)
                if queue_index == selected_item.queue_index:
                    self.preview_item_combo.setCurrentIndex(index)
                    self._refresh_live_monitoring_panel()
                    return
            self._refresh_live_monitoring_panel()

        def _on_preview_item_changed(self, _: int) -> None:
            target = self._selected_preview_target()
            self._populate_preview_screen_ids(target)
            self._set_preview_target_meta(target)
            if target is None:
                self.open_preview_button.setEnabled(False)
                self.preview_status_label.setText("Preview: no available screen in current run.")
                return
            self.open_preview_button.setEnabled(True)
            self.preview_status_label.setText(
                f"Preview: row #{target.queue_index} has {len(target.screen_ids)} screenId(s)."
            )

        def _refresh_preview_screens(self) -> None:
            selected_item = self._selected_plan_item()
            preferred_queue_index = selected_item.queue_index if selected_item else None
            try:
                summary = self._current_summary
                if summary is not None and summary.succeeded_count > 0:
                    self._build_shared_preview_workspace()
                else:
                    self._shared_preview_host_dir = None
                    self._shared_preview_generated_screens_dir = None
                self._preview_targets = self._collect_preview_targets()
            except Exception as exc:
                self._preview_targets = []
                self._set_preview_tab_enabled(False)
                self.preview_item_combo.clear()
                self.preview_screen_combo.clear()
                self.open_preview_button.setEnabled(False)
                self.preview_mode_value.setText("-")
                self._set_preview_target_meta(None)
                self._set_preview_inventory_kpis()
                self.preview_status_label.setText(f"Preview: failed to read manifest(s) ({exc})")
                return
            self._syncing_preview_combo = True
            try:
                self.preview_item_combo.clear()
                for target in self._preview_targets:
                    xml_name = Path(target.xml_path).name
                    self.preview_item_combo.addItem(
                        f"#{target.queue_index} {xml_name} ({len(target.screen_ids)} screens)",
                        target.queue_index,
                    )
            finally:
                self._syncing_preview_combo = False

            if not self._preview_targets:
                self._set_preview_tab_enabled(False)
                self.preview_screen_combo.clear()
                self.open_preview_button.setEnabled(False)
                self.preview_mode_value.setText("-")
                self._set_preview_target_meta(None)
                self._set_preview_inventory_kpis()
                self.preview_status_label.setText(
                    "Preview: no available preview routes yet. Run migration first."
                )
                return

            self._set_preview_tab_enabled(True)
            selected_index = 0
            if preferred_queue_index is not None:
                for index in range(self.preview_item_combo.count()):
                    queue_index = self.preview_item_combo.itemData(index)
                    if queue_index == preferred_queue_index:
                        selected_index = index
                        break
            self.preview_item_combo.setCurrentIndex(selected_index)
            target = self._selected_preview_target()
            self._populate_preview_screen_ids(target)
            self._set_preview_target_meta(target)
            self._set_preview_inventory_kpis()
            self.open_preview_button.setEnabled(target is not None)
            self.preview_status_label.setText(
                "Preview: "
                f"{len(self._preview_targets)} item(s), {self.preview_screens_value.text()} screenId(s) ready."
            )

        def _open_selected_preview(self) -> None:
            target = self._selected_preview_target()
            if target is None:
                self._show_error("No preview target is available. Run migration first.")
                return

            try:
                bridge = self._ensure_preview_bridge()
                screen_id = self._current_screen_id_input()
                if screen_id is None:
                    if not target.screen_ids:
                        raise RuntimeError(
                            "No screenId available in preview manifest. Run migration first."
                        )
                    screen_id = target.screen_ids[0]
                if screen_id not in target.screen_ids:
                    raise RuntimeError(
                        f"screenId `{screen_id}` is not available for row #{target.queue_index}."
                    )

                base_url = bridge.start_preview_host(
                    run_preview_host_dir=target.preview_host_dir
                )
                preview_url = build_preview_url(base_url, screen_id)
                opened_mode = "external"
                if (
                    self.embed_preview_checkbox.isChecked()
                    and self._embedded_preview_view is not None
                    and QUrl is not None
                ):
                    self._embedded_preview_view.setUrl(QUrl(preview_url))
                    opened_mode = "embedded"
                    self.main_tabs.setCurrentIndex(self.preview_tab_index)
                else:
                    result = bridge.open_screen_preview(
                        screen_id=screen_id,
                        run_preview_host_dir=target.preview_host_dir,
                        prefer_embedded=False,
                        parent_widget=self,
                    )
                    preview_url = result.url
                    opened_mode = result.mode
            except Exception as exc:
                self._show_error(str(exc))
                self.preview_status_label.setText(f"Preview: failed ({exc})")
                self.preview_fallback_view.setPlainText(str(exc))
                self.preview_mode_value.setText("error")
                return

            self.preview_fallback_view.setPlainText(preview_url)
            self.preview_route_value.setText(preview_url)
            self.preview_route_value.setToolTip(preview_url)
            self._set_preview_target_meta(target)
            self.preview_mode_value.setText(opened_mode)
            self.preview_status_label.setText(
                "Preview: opened "
                f"{opened_mode} for screenId `{screen_id}` (row #{target.queue_index})."
            )

        def _resolve_history_output_root(self) -> Path:
            explicit = self.output_dir_edit.text().strip()
            if explicit:
                return Path(explicit).expanduser().resolve()
            if self._current_summary is not None:
                return Path(self._current_summary.output_root_dir).expanduser().resolve()
            return (self._workspace_root / "out").resolve()

        def _selected_history_entry(self) -> BatchRunHistoryEntry | None:
            if not self._history_entries:
                return None
            row_index = self.history_table.currentRow()
            if row_index < 0:
                return None
            if row_index >= len(self._history_entries):
                return None
            return self._history_entries[row_index]

        def _on_history_row_changed(self) -> None:
            entry = self._selected_history_entry()
            if entry is None:
                self.history_load_button.setEnabled(False)
                self._set_history_selection_kpis(None)
                return
            self.history_load_button.setEnabled(bool(entry.plan_file))
            self._set_history_selection_kpis(entry)
            self._update_history_coverage_widgets(entry)
            try:
                summary_view = read_batch_summary_view(entry.summary_file)
                contract = {
                    "summary": summary_view.to_dict(),
                    "summary_file": entry.summary_file,
                    "plan_file": entry.plan_file,
                }
                self.history_contract_preview.setPlainText(
                    json.dumps(contract, ensure_ascii=False, indent=2)
                )
            except Exception as exc:
                self.history_contract_preview.setPlainText(str(exc))

        def _selected_history_filter_key(self) -> str:
            filter_key = self.history_project_filter_combo.currentData()
            if isinstance(filter_key, str) and filter_key.strip():
                return filter_key
            return _HISTORY_FILTER_ALL

        def _on_history_project_filter_changed(self) -> None:
            self._refresh_history_entries()

        def _refresh_history_entries(self) -> None:
            output_root = self._resolve_history_output_root()
            previous_selection = self._selected_history_entry()
            preferred_run_id = previous_selection.run_id if previous_selection is not None else None
            preferred_filter_key = self._selected_history_filter_key()
            try:
                all_entries = list_batch_run_history(output_root, limit=200)
            except Exception as exc:
                self._history_entries = []
                self.history_table.setRowCount(0)
                self.history_load_button.setEnabled(False)
                self.history_runs_value.setText("0")
                self._set_history_selection_kpis(None)
                self.history_status_label.setText(f"History: failed to scan ({exc})")
                self._refresh_project_key_options()
                return

            preferred_project_key = self._selected_project_key_input()
            if preferred_project_key is None:
                preferred_project_key = self._last_used_project_key
            if preferred_project_key is None:
                for entry in all_entries:
                    if entry.project_key:
                        preferred_project_key = entry.project_key
                        break
            self._refresh_project_key_options(preferred_key=preferred_project_key)

            available_filter_keys: list[str] = [_HISTORY_FILTER_ALL]
            has_none_project = any(entry.project_key is None for entry in all_entries)
            if has_none_project:
                available_filter_keys.append(_HISTORY_FILTER_NONE)
            available_filter_keys.extend(
                sorted(
                    {entry.project_key for entry in all_entries if entry.project_key is not None},
                    key=str.casefold,
                )
            )
            if preferred_filter_key not in available_filter_keys:
                preferred_filter_key = _HISTORY_FILTER_ALL

            self.history_project_filter_combo.blockSignals(True)
            self.history_project_filter_combo.clear()
            self.history_project_filter_combo.addItem("All projects", _HISTORY_FILTER_ALL)
            if has_none_project:
                self.history_project_filter_combo.addItem("No project (legacy)", _HISTORY_FILTER_NONE)
            for key in sorted(
                {entry.project_key for entry in all_entries if entry.project_key is not None},
                key=str.casefold,
            ):
                self.history_project_filter_combo.addItem(key, key)
            selected_filter_index = self.history_project_filter_combo.findData(preferred_filter_key)
            if selected_filter_index < 0:
                selected_filter_index = 0
            self.history_project_filter_combo.setCurrentIndex(selected_filter_index)
            self.history_project_filter_combo.blockSignals(False)

            selected_filter_key = self._selected_history_filter_key()
            if selected_filter_key == _HISTORY_FILTER_ALL:
                entries = all_entries
            elif selected_filter_key == _HISTORY_FILTER_NONE:
                entries = [entry for entry in all_entries if entry.project_key is None]
            else:
                entries = [entry for entry in all_entries if entry.project_key == selected_filter_key]

            self._history_entries = entries
            self.history_runs_value.setText(str(len(entries)))
            self.history_table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                self.history_table.setItem(row, 0, QTableWidgetItem(entry.run_id))
                self.history_table.setItem(row, 1, QTableWidgetItem(entry.project_key or "-"))
                self.history_table.setItem(row, 2, QTableWidgetItem(entry.generated_at_utc))
                self.history_table.setItem(row, 3, QTableWidgetItem(str(entry.total_items)))
                self.history_table.setItem(row, 4, QTableWidgetItem(str(entry.succeeded_count)))
                self.history_table.setItem(row, 5, QTableWidgetItem(str(entry.failed_count)))
                self.history_table.setItem(row, 6, QTableWidgetItem(str(entry.canceled_count)))
                self.history_table.setItem(row, 7, QTableWidgetItem(entry.run_root_dir))

            if entries:
                filter_label = (
                    "all projects"
                    if selected_filter_key == _HISTORY_FILTER_ALL
                    else (
                        "no project (legacy)"
                        if selected_filter_key == _HISTORY_FILTER_NONE
                        else f"project={selected_filter_key}"
                    )
                )
                self.history_status_label.setText(
                    f"History: {len(entries)} run(s) shown ({filter_label}) "
                    f"out of {len(all_entries)} under {output_root}"
                )
                selected_row_index = 0
                if preferred_run_id is not None:
                    for index, entry in enumerate(entries):
                        if entry.run_id == preferred_run_id:
                            selected_row_index = index
                            break
                self.history_table.selectRow(selected_row_index)
            else:
                if all_entries:
                    self.history_status_label.setText(
                        "History: no runs match current project filter "
                        f"under {output_root}"
                    )
                else:
                    self.history_status_label.setText(
                        f"History: no run summary found under {output_root}"
                    )
                self.history_load_button.setEnabled(False)
                self._set_history_selection_kpis(None)

        def _load_selected_history_entry(self) -> None:
            entry = self._selected_history_entry()
            if entry is None:
                self._show_error("Select a history run first.")
                return
            if entry.plan_file is None:
                self._show_error("Selected history run has no batch-run-plan.json file.")
                return

            try:
                plan = read_batch_run_plan(entry.plan_file)
                summary_view = read_batch_summary_view(entry.summary_file)
            except Exception as exc:
                self._show_error(str(exc))
                return

            previous_source_file = self.source_file_edit.text()
            previous_source_dir = self.source_dir_edit.text()
            self._poll_timer.stop()
            self._active_jobs_by_queue_index = {}
            self._last_batch_schedule = None
            self._job_snapshot_by_queue_index = {}
            self._job_logs_by_job_id = {}
            self._last_project_consolidation = None
            self._current_plan = plan
            self._current_summary = summary_view
            self.output_dir_edit.setText(summary_view.output_root_dir)
            history_project_key = plan.output.project_key or entry.project_key
            self._refresh_project_key_options(preferred_key=history_project_key)
            self._set_project_key_selection(history_project_key)
            self.run_id_edit.clear()
            if plan.selection.source_xml_file:
                self.source_file_edit.setText(plan.selection.source_xml_file)
                self.source_dir_edit.clear()
            elif plan.selection.source_xml_dir:
                self.source_dir_edit.setText(plan.selection.source_xml_dir)
                self.source_file_edit.clear()
            else:
                self.source_file_edit.setText(previous_source_file)
                self.source_dir_edit.setText(previous_source_dir)
            self.recursive_checkbox.setChecked(plan.selection.recursive)
            self.glob_pattern_edit.setText(plan.selection.glob_pattern)
            self._render()
            self._refresh_preview_screens()
            self.main_tabs.setCurrentIndex(0)

        def _start_new_batch_plan(self) -> None:
            self._poll_timer.stop()
            self._active_jobs_by_queue_index = {}
            self._last_batch_schedule = None
            self._job_snapshot_by_queue_index = {}
            self._job_logs_by_job_id = {}
            self._last_project_consolidation = None
            self._current_plan = None
            self._current_summary = None
            self.run_id_edit.clear()
            self._render()

        def _select_source_file(self) -> None:
            selected = pick_source_xml_file(
                parent=self,
                start_dir=self._infer_start_dir(self.source_file_edit.text()),
            )
            if selected:
                self.source_file_edit.setText(selected)
                self.source_dir_edit.clear()

        def _select_source_dir(self) -> None:
            selected = pick_source_xml_dir(
                parent=self,
                start_dir=self._infer_start_dir(self.source_dir_edit.text()),
            )
            if selected:
                self.source_dir_edit.setText(selected)
                self.source_file_edit.clear()

        def _select_output_dir(self) -> None:
            selected = pick_output_dir(
                parent=self,
                start_dir=self._infer_start_dir(self.output_dir_edit.text()),
            )
            if selected:
                self.output_dir_edit.setText(selected)
                self._on_output_root_changed()

        def _render(self) -> None:
            plan = self._current_plan
            summary = self._current_summary
            if plan is None or summary is None:
                self.summary_label.setText("Summary: no plan")
                self.queue_table.setRowCount(0)
                self.contract_preview.clear()
                self.retry_plan_button.setEnabled(False)
                self.run_button.setEnabled(False)
                self.cancel_button.setEnabled(False)
                self.new_batch_button.setEnabled(True)
                self.preview_item_combo.clear()
                self.open_preview_button.setEnabled(False)
                self.refresh_screens_button.setEnabled(False)
                self.preview_screen_combo.clear()
                self.preview_status_label.setText("Preview: idle")
                self.preview_mode_value.setText("-")
                self.preview_route_value.setText("/preview/:screenId")
                self.preview_route_value.setToolTip("")
                self._set_preview_target_meta(None)
                self._set_preview_inventory_kpis()
                self._shared_preview_host_dir = None
                self._shared_preview_generated_screens_dir = None
                self._set_preview_tab_enabled(False)
                self._refresh_live_monitoring_panel()
                return

            self.summary_label.setText(
                "Summary: "
                f"total={summary.total_items}, "
                f"queued={summary.queued_count}, "
                f"running={summary.running_count}, "
                f"succeeded={summary.succeeded_count}, "
                f"failed={summary.failed_count}, "
                f"retryable_failed={summary.retryable_failed_count}, "
                f"project={summary.project_key or '-'}"
            )
            self.queue_table.setRowCount(len(summary.items))
            for row, item in enumerate(summary.items):
                self.queue_table.setItem(row, 0, QTableWidgetItem(str(item.queue_index)))
                self.queue_table.setItem(row, 1, QTableWidgetItem(item.xml_path))
                self.queue_table.setItem(row, 2, QTableWidgetItem(item.status))
                summary_out = item.summary_file or item.summary_out
                self.queue_table.setItem(row, 3, QTableWidgetItem(summary_out))
            if self.queue_table.currentRow() < 0 and summary.items:
                self.queue_table.selectRow(0)

            contract = {
                "plan": plan.to_dict(),
                "summary_view": summary.to_dict(),
                "runtime": {
                    "workspace_root": str(self._workspace_root),
                    "active_jobs_by_queue_index": self._active_jobs_by_queue_index,
                    "last_batch_schedule": self._last_batch_schedule,
                    "strict_mode_enabled": self.strict_mode_checkbox.isChecked(),
                    "project_key": summary.project_key,
                    "project_root_dir": summary.project_root_dir,
                    "project_manifest_file": summary.project_manifest_file,
                    "last_project_consolidation": self._last_project_consolidation,
                },
            }
            self.contract_preview.setPlainText(
                json.dumps(contract, ensure_ascii=False, indent=2)
            )
            running = self._is_batch_running()
            self.plan_button.setEnabled(not running)
            self.new_batch_button.setEnabled(not running)
            self.retry_plan_button.setEnabled((not running) and summary.retryable_failed_count > 0)
            self.run_button.setEnabled((not running) and len(plan.items) > 0)
            self.cancel_button.setEnabled(running)
            self.refresh_screens_button.setEnabled(len(plan.items) > 0)
            self._refresh_live_monitoring_panel()

        def _selected_queue_index(self) -> int | None:
            row_index = self.queue_table.currentRow()
            if row_index < 0:
                return None
            queue_item = self.queue_table.item(row_index, 0)
            if queue_item is None:
                return None
            try:
                return int(queue_item.text())
            except (TypeError, ValueError):
                return None

        def _summary_item_by_queue_index(self, queue_index: int) -> Any | None:
            summary = self._current_summary
            if summary is None:
                return None
            for item in summary.items:
                if item.queue_index == queue_index:
                    return item
            return None

        def _format_log_entry(self, entry: dict[str, Any]) -> str:
            timestamp = str(entry.get("timestamp_utc", "")).strip()
            level = str(entry.get("level", "")).strip().upper() or "INFO"
            event = str(entry.get("event", "")).strip()
            message = str(entry.get("message", "")).strip()
            details = entry.get("details")
            detail_suffix = ""
            if isinstance(details, dict) and details:
                detail_suffix = f" | {json.dumps(details, ensure_ascii=False)}"
            event_prefix = f" [{event}]" if event else ""
            return f"{timestamp} {level}{event_prefix} {message}{detail_suffix}".strip()

        def _build_stage_status_rows_from_summary_payload(
            self,
            summary_payload: dict[str, Any],
        ) -> list[tuple[str, str]]:
            stages_payload = summary_payload.get("stages")
            rows: list[tuple[str, str]] = []
            if not isinstance(stages_payload, dict):
                return rows
            for stage_name in _PIPELINE_STAGE_ORDER_UI:
                stage = stages_payload.get(stage_name)
                if isinstance(stage, dict):
                    raw_status = stage.get("status")
                    status = str(raw_status).strip() if raw_status is not None else "unknown"
                else:
                    status = "unknown"
                rows.append((stage_name, status))
            return rows

        def _render_stage_rows(self, rows: list[tuple[str, str]]) -> None:
            self.stage_table.setRowCount(len(rows))
            for row_index, (stage_name, status) in enumerate(rows):
                self.stage_table.setItem(row_index, 0, QTableWidgetItem(stage_name))
                self.stage_table.setItem(row_index, 1, QTableWidgetItem(status))
            if rows:
                self.stage_table.resizeRowsToContents()

        def _refresh_live_monitoring_panel(self) -> None:
            summary = self._current_summary
            if summary is None:
                self.kpi_total.setText("0")
                self.kpi_running.setText("0")
                self.kpi_succeeded.setText("0")
                self.kpi_failed.setText("0")
                self.kpi_canceled.setText("0")
                self.kpi_retryable.setText("0")
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("%p% completed")
                self.live_status_label.setText("Pipeline: idle")
                self.stage_table.setRowCount(0)
                self.live_log_view.clear()
                return

            total = summary.total_items
            running_count = summary.running_count
            succeeded_count = summary.succeeded_count
            failed_count = summary.failed_count
            canceled_count = summary.canceled_count
            retryable_count = summary.retryable_failed_count
            completed = succeeded_count + failed_count + canceled_count
            progress = int((completed / total) * 100) if total > 0 else 0

            self.kpi_total.setText(str(total))
            self.kpi_running.setText(str(running_count))
            self.kpi_succeeded.setText(str(succeeded_count))
            self.kpi_failed.setText(str(failed_count))
            self.kpi_canceled.setText(str(canceled_count))
            self.kpi_retryable.setText(str(retryable_count))
            self.progress_bar.setValue(progress)
            self.progress_bar.setFormat(f"{completed}/{total} completed (%p%)")

            if self._is_batch_running():
                self.live_status_label.setText(
                    f"Pipeline: running ({running_count} active job(s), {completed}/{total} completed)"
                )
            else:
                self.live_status_label.setText(
                    f"Pipeline: idle (last run: succeeded={succeeded_count}, failed={failed_count}, canceled={canceled_count})"
                )

            selected_queue_index = self._selected_queue_index()
            if selected_queue_index is None and summary.items:
                selected_queue_index = summary.items[0].queue_index

            if selected_queue_index is None:
                self.stage_table.setRowCount(0)
                self.live_log_view.clear()
                return

            job_id = self._active_jobs_by_queue_index.get(selected_queue_index)
            service = self._runner_service
            stage_rows: list[tuple[str, str]] = []

            if service is not None and job_id:
                job_snapshot = self._job_snapshot_by_queue_index.get(selected_queue_index)
                if job_snapshot is None:
                    try:
                        job_snapshot = service.get_job(job_id)
                        self._job_snapshot_by_queue_index[selected_queue_index] = job_snapshot
                    except OrchestratorApiError:
                        job_snapshot = None

                if job_snapshot is not None:
                    status = str(job_snapshot.get("status", "")).strip().lower() or "unknown"
                    if status in TERMINAL_JOB_STATUSES:
                        try:
                            artifacts_payload = service.get_job_artifacts(job_id)
                            artifacts = artifacts_payload.get("artifacts")
                            if isinstance(artifacts, dict):
                                summary_payload = {"stages": artifacts.get("stages", {})}
                                stage_rows = self._build_stage_status_rows_from_summary_payload(
                                    summary_payload
                                )
                        except OrchestratorApiError:
                            stage_rows = [(stage_name, status) for stage_name in _PIPELINE_STAGE_ORDER_UI]
                    elif status == "running":
                        stage_rows = [
                            (_PIPELINE_STAGE_ORDER_UI[0], "running"),
                            *[(stage_name, "pending") for stage_name in _PIPELINE_STAGE_ORDER_UI[1:]],
                        ]
                    else:
                        stage_rows = [(stage_name, status) for stage_name in _PIPELINE_STAGE_ORDER_UI]

                try:
                    logs_payload = service.get_job_logs(job_id)
                    logs_raw = logs_payload.get("logs")
                    if isinstance(logs_raw, list):
                        parsed_logs = [entry for entry in logs_raw if isinstance(entry, dict)]
                        self._job_logs_by_job_id[job_id] = parsed_logs
                except OrchestratorApiError:
                    pass

                log_entries = self._job_logs_by_job_id.get(job_id, [])
                if log_entries:
                    tail_entries = log_entries[-800:]
                    rendered = "\n".join(self._format_log_entry(entry) for entry in tail_entries)
                    self.live_log_view.setPlainText(rendered)
                    self.live_log_view.verticalScrollBar().setValue(
                        self.live_log_view.verticalScrollBar().maximum()
                    )
                else:
                    self.live_log_view.setPlainText("No logs yet for selected queue item.")
            else:
                selected_summary_item = self._summary_item_by_queue_index(selected_queue_index)
                summary_file = (
                    selected_summary_item.summary_file
                    if selected_summary_item is not None
                    else None
                )
                if summary_file:
                    try:
                        payload = json.loads(Path(summary_file).read_text(encoding="utf-8"))
                        stage_rows = self._build_stage_status_rows_from_summary_payload(payload)
                    except Exception:
                        stage_rows = []
                self.live_log_view.setPlainText(
                    "Live logs are available while jobs are running. "
                    "For completed history runs, inspect report files from the summary output path."
                )

            if not stage_rows:
                stage_rows = [(stage_name, "n/a") for stage_name in _PIPELINE_STAGE_ORDER_UI]
            self._render_stage_rows(stage_rows)

        def _generate_plan(self) -> None:
            if self._is_batch_running():
                self._show_error("Cannot generate a new plan while a batch is running.")
                return
            output_root = self.output_dir_edit.text().strip()
            if not output_root:
                self._show_error("`Output root` is required.")
                return

            source_file = self.source_file_edit.text().strip() or None
            source_dir = self.source_dir_edit.text().strip() or None
            project_key = self._selected_project_key_input()
            run_id = self.run_id_edit.text().strip() or None
            glob_pattern = self.glob_pattern_edit.text().strip() or DEFAULT_XML_GLOB_PATTERN

            try:
                plan = build_batch_run_plan(
                    output_root_dir=output_root,
                    project_key=project_key,
                    source_xml_file=source_file,
                    source_xml_dir=source_dir,
                    recursive=self.recursive_checkbox.isChecked(),
                    glob_pattern=glob_pattern,
                    run_id=run_id,
                )
            except Exception as exc:
                self._show_error(str(exc))
                return

            self._current_plan = plan
            self._current_summary = build_batch_summary_view(plan)
            self._last_project_consolidation = None
            self._refresh_project_key_options(preferred_key=plan.output.project_key)
            self._set_project_key_selection(plan.output.project_key)
            self._render()
            self.plan_generated.emit(plan.to_dict())
            self.summary_generated.emit(self._current_summary.to_dict())
            self._refresh_history_entries()
            self._refresh_preview_screens()

        def set_run_results(self, item_results: Sequence[BatchRunItemResult]) -> None:
            if self._current_plan is None:
                raise RuntimeError("Cannot apply run results before generating a plan.")
            self._current_summary = build_batch_summary_view(
                self._current_plan,
                item_results=item_results,
            )
            self._render()
            self.summary_generated.emit(self._current_summary.to_dict())

        def set_summary_view(self, summary_view: BatchRunSummaryView) -> None:
            self._current_summary = summary_view
            self._render()
            self.summary_generated.emit(summary_view.to_dict())

        def _generate_retry_plan(self) -> None:
            if self._is_batch_running():
                self._show_error("Cannot generate a retry plan while a batch is running.")
                return
            if self._current_summary is None:
                self._show_error("No summary view available for retry planning.")
                return
            run_id = self.run_id_edit.text().strip() or None
            output_root = self.output_dir_edit.text().strip() or self._current_summary.output_root_dir
            try:
                retry_plan = build_failure_retry_plan(
                    self._current_summary,
                    output_root_dir=output_root,
                    run_id=run_id,
                )
            except Exception as exc:
                self._show_error(str(exc))
                return

            self._current_plan = retry_plan
            self._current_summary = build_batch_summary_view(retry_plan)
            self._last_project_consolidation = None
            if retry_plan.output.project_key:
                self._refresh_project_key_options(preferred_key=retry_plan.output.project_key)
                self._set_project_key_selection(retry_plan.output.project_key)
            self._render()
            self.retry_plan_generated.emit(retry_plan.to_dict())
            self.summary_generated.emit(self._current_summary.to_dict())
            self._refresh_preview_screens()

        def _run_current_plan(self) -> None:
            plan = self._current_plan
            if plan is None:
                self._show_error("Generate a batch plan before starting execution.")
                return
            if self._is_batch_running():
                self._show_error("A batch is already running.")
                return

            try:
                materialize_batch_run_layout(
                    plan,
                    write_plan_manifest=True,
                    write_queued_summary=True,
                    pretty=True,
                )
                payloads = build_batch_job_payloads(
                    plan,
                    workspace_root=self._workspace_root,
                    strict=self.strict_mode_checkbox.isChecked(),
                )
                service = self._ensure_runner_service()
                scheduled = service.schedule_batch(payloads, batch_id=plan.run_id)
            except Exception as exc:
                self._show_error(str(exc))
                return

            jobs = scheduled.get("jobs")
            if not isinstance(jobs, list) or len(jobs) != len(plan.items):
                self._show_error(
                    "Batch scheduling contract mismatch: expected one job per queue item."
                )
                return

            active_jobs: dict[int, str] = {}
            for item, job in zip(plan.items, jobs, strict=False):
                if not isinstance(job, dict):
                    self._show_error("Batch scheduling returned a malformed job entry.")
                    return
                job_id = job.get("id")
                if not isinstance(job_id, str) or not job_id:
                    self._show_error("Batch scheduling returned a job without a valid id.")
                    return
                active_jobs[item.queue_index] = job_id

            self._active_jobs_by_queue_index = active_jobs
            self._last_batch_schedule = scheduled
            self._job_snapshot_by_queue_index = {}
            self._job_logs_by_job_id = {}
            self._render()
            self._poll_timer.start()
            self._poll_active_jobs()

        def _cancel_active_batch(self) -> None:
            if not self._is_batch_running():
                return
            service = self._runner_service
            if service is None:
                return
            for job_id in self._active_jobs_by_queue_index.values():
                try:
                    job = service.get_job(job_id)
                    status = job.get("status")
                    if isinstance(status, str) and status in TERMINAL_JOB_STATUSES:
                        continue
                    service.cancel_job(job_id)
                except OrchestratorApiError:
                    continue
            self._poll_active_jobs()

        def _build_item_result_from_job(
            self,
            item: BatchRunPlanItem,
            job: dict[str, Any],
        ) -> BatchRunItemResult:
            raw_status = job.get("status")
            status = _map_job_status_to_batch_item_status(
                raw_status if isinstance(raw_status, str) else None
            )
            result_payload = job.get("result")
            exit_code: int | None = None
            summary_file: str | None = None
            if isinstance(result_payload, dict):
                raw_exit_code = result_payload.get("exit_code")
                if isinstance(raw_exit_code, int):
                    exit_code = raw_exit_code
                raw_summary_file = result_payload.get("summary_file")
                if isinstance(raw_summary_file, str) and raw_summary_file:
                    summary_file = raw_summary_file

            error_message: str | None = None
            error_payload = job.get("error")
            if isinstance(error_payload, dict):
                raw_error_message = error_payload.get("message")
                if isinstance(raw_error_message, str) and raw_error_message.strip():
                    error_message = raw_error_message.strip()
                else:
                    raw_error_code = error_payload.get("code")
                    if isinstance(raw_error_code, str) and raw_error_code.strip():
                        error_message = raw_error_code.strip()

            return BatchRunItemResult(
                queue_index=item.queue_index,
                xml_path=item.xml_path,
                status=status,
                exit_code=exit_code,
                summary_file=summary_file,
                error_message=error_message,
            )

        def _poll_active_jobs(self) -> None:
            plan = self._current_plan
            if plan is None or not self._active_jobs_by_queue_index:
                self._poll_timer.stop()
                return
            service = self._runner_service
            if service is None:
                self._poll_timer.stop()
                return

            item_results: list[BatchRunItemResult] = []
            all_terminal = True
            for item in plan.items:
                job_id = self._active_jobs_by_queue_index.get(item.queue_index)
                if not job_id:
                    item_results.append(
                        BatchRunItemResult(
                            queue_index=item.queue_index,
                            xml_path=item.xml_path,
                            status="failed",
                            error_message="No scheduled job id for this queue item.",
                        )
                    )
                    continue

                try:
                    job = service.get_job(job_id)
                    self._job_snapshot_by_queue_index[item.queue_index] = job
                    try:
                        log_payload = service.get_job_logs(job_id)
                        logs_raw = log_payload.get("logs")
                        if isinstance(logs_raw, list):
                            self._job_logs_by_job_id[job_id] = [
                                entry for entry in logs_raw if isinstance(entry, dict)
                            ]
                    except OrchestratorApiError:
                        pass
                    result = self._build_item_result_from_job(item, job)
                except OrchestratorApiError as exc:
                    self._job_snapshot_by_queue_index.pop(item.queue_index, None)
                    result = BatchRunItemResult(
                        queue_index=item.queue_index,
                        xml_path=item.xml_path,
                        status="failed",
                        error_message=str(exc),
                    )
                item_results.append(result)
                if result.status not in TERMINAL_JOB_STATUSES:
                    all_terminal = False

            self.set_run_results(item_results)
            if all_terminal:
                self._finalize_active_batch()

        def _finalize_active_batch(self) -> None:
            self._poll_timer.stop()
            self._active_jobs_by_queue_index = {}
            if self._current_plan is not None and self._current_summary is not None:
                write_batch_summary_view(
                    self._current_summary,
                    output_path=self._current_plan.output.summary_file,
                    pretty=True,
                )
                try:
                    consolidation = consolidate_batch_run_artifacts(
                        self._current_plan,
                        self._current_summary,
                        pretty=True,
                    )
                except Exception as exc:
                    self._last_project_consolidation = {
                        "status": "failed",
                        "error": str(exc),
                    }
                else:
                    self._last_project_consolidation = {
                        "status": "success",
                        **consolidation.to_dict(),
                    }
            self._render()
            self._refresh_history_entries()
            self._refresh_preview_screens()

        def shutdown(self) -> None:
            self._poll_timer.stop()
            if self._runner_service is not None:
                self._runner_service.shutdown()
                self._runner_service = None
            if self._preview_bridge is not None:
                self._preview_bridge.stop_preview_host()
                self._preview_bridge = None
            self._active_jobs_by_queue_index = {}
            self._job_snapshot_by_queue_index = {}
            self._job_logs_by_job_id = {}
            self._shared_preview_host_dir = None
            self._shared_preview_generated_screens_dir = None

        def closeEvent(self, event: Any) -> None:  # noqa: N802
            self.shutdown()
            super().closeEvent(event)


    def launch_filepicker_batch_workflow(*, exec_event_loop: bool = True) -> int:
        _require_pyside6()
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])
        widget = FilePickerBatchWorkflowWidget()
        widget.resize(1680, 1020)
        if not exec_event_loop:
            widget.shutdown()
            widget.deleteLater()
            return 0
        widget.show()
        if owns_app:
            try:
                return app.exec()
            finally:
                widget.shutdown()
        return 0
else:
    class FilePickerBatchWorkflowWidget:  # pragma: no cover - optional dependency branch
        def __init__(self, *_: Any, **__: Any) -> None:
            _require_pyside6()


    def launch_filepicker_batch_workflow(
        *,
        exec_event_loop: bool = True,
    ) -> int:  # pragma: no cover - optional dependency branch
        _ = exec_event_loop
        _require_pyside6()
        return 0


__all__ = [
    "FilePickerBatchWorkflowWidget",
    "build_batch_job_payloads",
    "launch_filepicker_batch_workflow",
    "pick_output_dir",
    "pick_source_xml_dir",
    "pick_source_xml_file",
    "resolve_workspace_root",
]
