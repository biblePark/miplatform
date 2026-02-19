from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state import DesktopRunMode, DesktopShellState


class DesktopDependencyError(RuntimeError):
    """Raised when desktop dependencies are unavailable."""


@dataclass(slots=True)
class QtWidgetsModule:
    QApplication: type[Any]
    QButtonGroup: type[Any]
    QFormLayout: type[Any]
    QGroupBox: type[Any]
    QHBoxLayout: type[Any]
    QLabel: type[Any]
    QLineEdit: type[Any]
    QMainWindow: type[Any]
    QPlainTextEdit: type[Any]
    QPushButton: type[Any]
    QRadioButton: type[Any]
    QVBoxLayout: type[Any]
    QWidget: type[Any]


def load_qt_widgets_module() -> QtWidgetsModule:
    try:
        from PySide6 import QtWidgets  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise DesktopDependencyError(
            "PySide6 is required for desktop-shell. Install with `pip install PySide6` "
            "or `pip install 'miflatform-migrator[desktop]'`."
        ) from exc

    return QtWidgetsModule(
        QApplication=QtWidgets.QApplication,
        QButtonGroup=QtWidgets.QButtonGroup,
        QFormLayout=QtWidgets.QFormLayout,
        QGroupBox=QtWidgets.QGroupBox,
        QHBoxLayout=QtWidgets.QHBoxLayout,
        QLabel=QtWidgets.QLabel,
        QLineEdit=QtWidgets.QLineEdit,
        QMainWindow=QtWidgets.QMainWindow,
        QPlainTextEdit=QtWidgets.QPlainTextEdit,
        QPushButton=QtWidgets.QPushButton,
        QRadioButton=QtWidgets.QRadioButton,
        QVBoxLayout=QtWidgets.QVBoxLayout,
        QWidget=QtWidgets.QWidget,
    )


def create_main_window(
    *,
    qt: QtWidgetsModule,
    state: DesktopShellState,
) -> Any:
    main_window = qt.QMainWindow()
    main_window.setWindowTitle("MIFL Migrator Desktop")
    main_window.resize(1080, 720)

    root = qt.QWidget()
    main_layout = qt.QVBoxLayout(root)

    run_panel = qt.QGroupBox("Run Panel")
    run_layout = qt.QVBoxLayout(run_panel)

    mode_row = qt.QHBoxLayout()
    single_mode = qt.QRadioButton("Single XML")
    batch_mode = qt.QRadioButton("Batch Folder")
    mode_group = qt.QButtonGroup(run_panel)
    mode_group.addButton(single_mode)
    mode_group.addButton(batch_mode)
    single_mode.setChecked(state.run_plan.mode == DesktopRunMode.SINGLE_XML)
    batch_mode.setChecked(state.run_plan.mode == DesktopRunMode.BATCH_FOLDER)
    mode_row.addWidget(single_mode)
    mode_row.addWidget(batch_mode)
    run_layout.addLayout(mode_row)

    source_form = qt.QFormLayout()
    single_xml_input = qt.QLineEdit(state.run_plan.single_xml.xml_path or "")
    single_xml_input.setPlaceholderText("Select XML source file...")
    batch_folder_input = qt.QLineEdit(state.run_plan.batch_folder.folder_path or "")
    batch_folder_input.setPlaceholderText("Select batch source folder...")
    output_dir_input = qt.QLineEdit(state.run_plan.output_dir or "")
    output_dir_input.setPlaceholderText("Select output directory...")
    source_form.addRow("Single XML", single_xml_input)
    source_form.addRow("Batch Folder", batch_folder_input)
    source_form.addRow("Output Dir", output_dir_input)
    run_layout.addLayout(source_form)

    run_button = qt.QPushButton("Run Migration")
    run_layout.addWidget(run_button)

    status_panel = qt.QGroupBox("Status Area")
    status_layout = qt.QFormLayout(status_panel)
    mode_value = qt.QLabel(state.run_plan.mode.value)
    phase_value = qt.QLabel(state.status.phase)
    summary_value = qt.QLabel(state.status.summary)
    status_layout.addRow("Mode", mode_value)
    status_layout.addRow("Phase", phase_value)
    status_layout.addRow("Summary", summary_value)

    log_panel = qt.QGroupBox("Log Viewer")
    log_layout = qt.QVBoxLayout(log_panel)
    log_viewer = qt.QPlainTextEdit()
    log_viewer.setReadOnly(True)
    log_layout.addWidget(log_viewer)

    state.append_log("Desktop shell initialized.")
    log_viewer.setPlainText("\n".join(log.message for log in state.logs))

    def _select_single_mode() -> None:
        state.set_mode(DesktopRunMode.SINGLE_XML)
        mode_value.setText(state.run_plan.mode.value)
        phase_value.setText(state.status.phase)
        summary_value.setText(state.status.summary)

    def _select_batch_mode() -> None:
        state.set_mode(DesktopRunMode.BATCH_FOLDER)
        mode_value.setText(state.run_plan.mode.value)
        phase_value.setText(state.status.phase)
        summary_value.setText(state.status.summary)

    def _update_single_xml(value: str) -> None:
        state.run_plan.single_xml.xml_path = value.strip() or None

    def _update_batch_folder(value: str) -> None:
        state.run_plan.batch_folder.folder_path = value.strip() or None

    def _update_output_dir(value: str) -> None:
        state.run_plan.output_dir = value.strip() or None

    single_mode.toggled.connect(lambda checked: _select_single_mode() if checked else None)
    batch_mode.toggled.connect(lambda checked: _select_batch_mode() if checked else None)
    single_xml_input.textChanged.connect(_update_single_xml)
    batch_folder_input.textChanged.connect(_update_batch_folder)
    output_dir_input.textChanged.connect(_update_output_dir)

    def _run_placeholder() -> None:
        state.set_status("pending", "Runner service integration pending.")
        phase_value.setText(state.status.phase)
        summary_value.setText(state.status.summary)
        state.append_log("Run button clicked. Execution wiring is pending in R13 follow-up lanes.")
        log_viewer.setPlainText("\n".join(log.message for log in state.logs))

    run_button.clicked.connect(_run_placeholder)

    main_layout.addWidget(run_panel)
    main_layout.addWidget(status_panel)
    main_layout.addWidget(log_panel)

    main_window.setCentralWidget(root)
    return main_window


__all__ = [
    "DesktopDependencyError",
    "QtWidgetsModule",
    "create_main_window",
    "load_qt_widgets_module",
]
