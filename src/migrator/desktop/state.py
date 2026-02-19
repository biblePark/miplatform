from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class DesktopRunMode(StrEnum):
    SINGLE_XML = "single_xml"
    BATCH_FOLDER = "batch_folder"


@dataclass(slots=True)
class SingleXmlRunSelection:
    xml_path: str | None = None


@dataclass(slots=True)
class BatchFolderRunSelection:
    folder_path: str | None = None
    recursive: bool = True
    glob_pattern: str = "*.xml"


@dataclass(slots=True)
class DesktopRunPlan:
    mode: DesktopRunMode = DesktopRunMode.SINGLE_XML
    single_xml: SingleXmlRunSelection = field(default_factory=SingleXmlRunSelection)
    batch_folder: BatchFolderRunSelection = field(default_factory=BatchFolderRunSelection)
    output_dir: str | None = None
    strict: bool = False
    capture_text: bool = False


@dataclass(slots=True)
class DesktopLogEvent:
    level: str
    message: str
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(slots=True)
class DesktopStatus:
    phase: str = "idle"
    summary: str = "Ready"
    updated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(slots=True)
class DesktopShellState:
    run_plan: DesktopRunPlan = field(default_factory=DesktopRunPlan)
    status: DesktopStatus = field(default_factory=DesktopStatus)
    logs: list[DesktopLogEvent] = field(default_factory=list)

    def set_mode(self, mode: DesktopRunMode) -> None:
        self.run_plan.mode = mode
        self.set_status("idle", f"Run mode changed to {mode.value}.")

    def set_status(self, phase: str, summary: str) -> None:
        self.status.phase = phase
        self.status.summary = summary
        self.status.updated_at_utc = datetime.now(UTC).isoformat()

    def append_log(self, message: str, *, level: str = "info") -> None:
        self.logs.append(DesktopLogEvent(level=level, message=message))


__all__ = [
    "BatchFolderRunSelection",
    "DesktopLogEvent",
    "DesktopRunMode",
    "DesktopRunPlan",
    "DesktopShellState",
    "DesktopStatus",
    "SingleXmlRunSelection",
]
