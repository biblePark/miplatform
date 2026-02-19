from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .desktop_batch_workflow import (
    DEFAULT_XML_GLOB_PATTERN,
    BatchRunItemResult,
    BatchRunPlan,
    BatchRunSummaryView,
    build_batch_run_plan,
    build_batch_summary_view,
    build_failure_retry_plan,
)

try:  # pragma: no cover - optional dependency branch
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
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


if _PYSIDE6_AVAILABLE:  # pragma: no cover - UI integration is optional for CI
    class FilePickerBatchWorkflowWidget(QWidget):
        plan_generated = Signal(dict)
        summary_generated = Signal(dict)
        retry_plan_generated = Signal(dict)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("MIFL Migrator Desktop Batch Workflow")
            self._current_plan: BatchRunPlan | None = None
            self._current_summary: BatchRunSummaryView | None = None
            self._setup_ui()

        def _setup_ui(self) -> None:
            root = QVBoxLayout(self)
            form = QFormLayout()

            self.source_file_edit = QLineEdit()
            source_file_layout = QHBoxLayout()
            source_file_layout.addWidget(self.source_file_edit)
            browse_file_button = QPushButton("Browse File")
            browse_file_button.clicked.connect(self._select_source_file)
            source_file_layout.addWidget(browse_file_button)
            form.addRow("Source XML file", source_file_layout)

            self.source_dir_edit = QLineEdit()
            source_dir_layout = QHBoxLayout()
            source_dir_layout.addWidget(self.source_dir_edit)
            browse_dir_button = QPushButton("Browse Folder")
            browse_dir_button.clicked.connect(self._select_source_dir)
            source_dir_layout.addWidget(browse_dir_button)
            form.addRow("Source folder", source_dir_layout)

            self.recursive_checkbox = QCheckBox("Recursive folder scan")
            self.recursive_checkbox.setChecked(True)
            form.addRow("", self.recursive_checkbox)

            self.glob_pattern_edit = QLineEdit(DEFAULT_XML_GLOB_PATTERN)
            form.addRow("Folder glob pattern", self.glob_pattern_edit)

            self.output_dir_edit = QLineEdit()
            output_dir_layout = QHBoxLayout()
            output_dir_layout.addWidget(self.output_dir_edit)
            browse_output_button = QPushButton("Browse Output")
            browse_output_button.clicked.connect(self._select_output_dir)
            output_dir_layout.addWidget(browse_output_button)
            form.addRow("Output root", output_dir_layout)

            self.run_id_edit = QLineEdit()
            self.run_id_edit.setPlaceholderText("Optional deterministic run id")
            form.addRow("Run id", self.run_id_edit)

            root.addLayout(form)

            controls = QHBoxLayout()
            self.plan_button = QPushButton("Generate Batch Plan")
            self.plan_button.clicked.connect(self._generate_plan)
            controls.addWidget(self.plan_button)

            self.retry_plan_button = QPushButton("Generate Failure Retry Plan")
            self.retry_plan_button.setEnabled(False)
            self.retry_plan_button.clicked.connect(self._generate_retry_plan)
            controls.addWidget(self.retry_plan_button)
            root.addLayout(controls)

            self.summary_label = QLabel("Summary: no plan")
            root.addWidget(self.summary_label)

            self.queue_table = QTableWidget(0, 4)
            self.queue_table.setHorizontalHeaderLabels(
                ["#", "XML path", "Status", "Summary output"]
            )
            header = self.queue_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.Stretch)
            root.addWidget(self.queue_table)

            self.contract_preview = QPlainTextEdit()
            self.contract_preview.setReadOnly(True)
            root.addWidget(self.contract_preview)

        def _show_error(self, message: str) -> None:
            QMessageBox.critical(self, "Batch Workflow Error", message)

        def _infer_start_dir(self, raw_value: str) -> str | None:
            value = raw_value.strip()
            if not value:
                return None
            return value

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

        def _render(self) -> None:
            plan = self._current_plan
            summary = self._current_summary
            if plan is None or summary is None:
                self.summary_label.setText("Summary: no plan")
                self.queue_table.setRowCount(0)
                self.contract_preview.clear()
                self.retry_plan_button.setEnabled(False)
                return

            self.summary_label.setText(
                "Summary: "
                f"total={summary.total_items}, "
                f"queued={summary.queued_count}, "
                f"running={summary.running_count}, "
                f"succeeded={summary.succeeded_count}, "
                f"failed={summary.failed_count}, "
                f"retryable_failed={summary.retryable_failed_count}"
            )
            self.queue_table.setRowCount(len(summary.items))
            for row, item in enumerate(summary.items):
                self.queue_table.setItem(row, 0, QTableWidgetItem(str(item.queue_index)))
                self.queue_table.setItem(row, 1, QTableWidgetItem(item.xml_path))
                self.queue_table.setItem(row, 2, QTableWidgetItem(item.status))
                summary_out = item.summary_file or item.summary_out
                self.queue_table.setItem(row, 3, QTableWidgetItem(summary_out))

            contract = {
                "plan": plan.to_dict(),
                "summary_view": summary.to_dict(),
            }
            self.contract_preview.setPlainText(
                json.dumps(contract, ensure_ascii=False, indent=2)
            )
            self.retry_plan_button.setEnabled(summary.retryable_failed_count > 0)

        def _generate_plan(self) -> None:
            output_root = self.output_dir_edit.text().strip()
            if not output_root:
                self._show_error("`Output root` is required.")
                return

            source_file = self.source_file_edit.text().strip() or None
            source_dir = self.source_dir_edit.text().strip() or None
            run_id = self.run_id_edit.text().strip() or None
            glob_pattern = self.glob_pattern_edit.text().strip() or DEFAULT_XML_GLOB_PATTERN

            try:
                plan = build_batch_run_plan(
                    output_root_dir=output_root,
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
            self._render()
            self.plan_generated.emit(plan.to_dict())
            self.summary_generated.emit(self._current_summary.to_dict())

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
            self._render()
            self.retry_plan_generated.emit(retry_plan.to_dict())
            self.summary_generated.emit(self._current_summary.to_dict())


    def launch_filepicker_batch_workflow() -> int:
        _require_pyside6()
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])
        widget = FilePickerBatchWorkflowWidget()
        widget.resize(1200, 760)
        widget.show()
        if owns_app:
            return app.exec()
        return 0
else:
    class FilePickerBatchWorkflowWidget:  # pragma: no cover - optional dependency branch
        def __init__(self, *_: Any, **__: Any) -> None:
            _require_pyside6()


    def launch_filepicker_batch_workflow() -> int:  # pragma: no cover - optional dependency branch
        _require_pyside6()
        return 0


__all__ = [
    "FilePickerBatchWorkflowWidget",
    "launch_filepicker_batch_workflow",
    "pick_output_dir",
    "pick_source_xml_dir",
    "pick_source_xml_file",
]
