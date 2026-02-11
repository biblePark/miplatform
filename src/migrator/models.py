from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class SourceRef:
    file_path: str
    node_path: str
    line: int | None = None


@dataclass(slots=True)
class AstNode:
    tag: str
    attributes: dict[str, str]
    text: str | None
    source: SourceRef
    children: list["AstNode"] = field(default_factory=list)


@dataclass(slots=True)
class DatasetColumnIR:
    column_id: str | None
    data_type: str | None
    attributes: dict[str, str]
    source: SourceRef


@dataclass(slots=True)
class DatasetRecordIR:
    values: dict[str, str]
    source: SourceRef


@dataclass(slots=True)
class DatasetIR:
    dataset_id: str | None
    attributes: dict[str, str]
    columns: list[DatasetColumnIR] = field(default_factory=list)
    records: list[DatasetRecordIR] = field(default_factory=list)
    source: SourceRef | None = None


@dataclass(slots=True)
class BindingIR:
    node_tag: str
    node_id: str | None
    binding_key: str
    binding_value: str
    source: SourceRef


@dataclass(slots=True)
class EventIR:
    node_tag: str
    node_id: str | None
    event_name: str
    handler: str
    source: SourceRef


@dataclass(slots=True)
class UnknownTag:
    tag: str
    node_path: str


@dataclass(slots=True)
class UnknownAttr:
    tag: str
    attr: str
    node_path: str


@dataclass(slots=True)
class ParseStats:
    total_nodes: int
    max_depth: int
    tag_counts: dict[str, int]
    attr_counts: dict[str, int]
    unknown_tags: list[UnknownTag] = field(default_factory=list)
    unknown_attrs: list[UnknownAttr] = field(default_factory=list)


@dataclass(slots=True)
class ValidationGate:
    name: str
    passed: bool
    value: int
    expected: int
    message: str


@dataclass(slots=True)
class ScreenIR:
    screen_id: str
    root: AstNode
    datasets: list[DatasetIR] = field(default_factory=list)
    bindings: list[BindingIR] = field(default_factory=list)
    events: list[EventIR] = field(default_factory=list)


@dataclass(slots=True)
class ParseConfig:
    strict: bool = False
    known_tags: set[str] | None = None
    known_attrs_by_tag: dict[str, set[str]] | None = None
    capture_text: bool = False
    enable_roundtrip_gate: bool = True


@dataclass(slots=True)
class ParseReport:
    screen: ScreenIR
    stats: ParseStats
    gates: list[ValidationGate]
    errors: list[str]
    warnings: list[str]
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
