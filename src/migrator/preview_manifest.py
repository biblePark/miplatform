from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


SCREEN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ENTRY_MODULE_RE = re.compile(r"^screens/[A-Za-z0-9/_-]+$")


class ManifestContractError(ValueError):
    """Raised when a screens manifest payload violates the preview-host contract."""


@dataclass(frozen=True, slots=True)
class ScreenManifestEntry:
    screen_id: str
    entry_module: str
    source_xml_path: str
    source_node_path: str
    title: str | None = None

    def preview_route(self) -> str:
        return f"/preview/{self.screen_id}"


@dataclass(frozen=True, slots=True)
class ScreensManifest:
    schema_version: str
    generated_at_utc: str
    screens: tuple[ScreenManifestEntry, ...]

    def find_screen(self, screen_id: str) -> ScreenManifestEntry | None:
        for screen in self.screens:
            if screen.screen_id == screen_id:
                return screen
        return None


def _expect_dict(payload: object, *, field: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ManifestContractError(f"{field} must be an object.")
    return payload


def _expect_non_empty_string(payload: object, *, field: str) -> str:
    if not isinstance(payload, str) or not payload.strip():
        raise ManifestContractError(f"{field} must be a non-empty string.")
    return payload


def _validate_iso8601_datetime(value: str, *, field: str) -> None:
    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ManifestContractError(
            f"{field} must be a valid ISO-8601 datetime, got: {value}"
        ) from exc


def _validate_screen_entry(payload: object, *, index: int) -> ScreenManifestEntry:
    item = _expect_dict(payload, field=f"screens[{index}]")
    required_fields = ("screenId", "entryModule", "sourceXmlPath", "sourceNodePath")
    missing = [field for field in required_fields if field not in item]
    if missing:
        raise ManifestContractError(
            f"screens[{index}] is missing required field(s): {', '.join(missing)}"
        )

    screen_id = _expect_non_empty_string(item["screenId"], field=f"screens[{index}].screenId")
    if not SCREEN_ID_RE.fullmatch(screen_id):
        raise ManifestContractError(
            f"screens[{index}].screenId has invalid format: {screen_id}"
        )

    entry_module = _expect_non_empty_string(
        item["entryModule"], field=f"screens[{index}].entryModule"
    )
    if not ENTRY_MODULE_RE.fullmatch(entry_module):
        raise ManifestContractError(
            f"screens[{index}].entryModule has invalid format: {entry_module}"
        )

    source_xml_path = _expect_non_empty_string(
        item["sourceXmlPath"], field=f"screens[{index}].sourceXmlPath"
    )
    source_node_path = _expect_non_empty_string(
        item["sourceNodePath"], field=f"screens[{index}].sourceNodePath"
    )

    title_raw = item.get("title")
    title = None
    if title_raw is not None:
        title = _expect_non_empty_string(title_raw, field=f"screens[{index}].title")

    return ScreenManifestEntry(
        screen_id=screen_id,
        title=title,
        entry_module=entry_module,
        source_xml_path=source_xml_path,
        source_node_path=source_node_path,
    )


def load_screens_manifest(payload: object) -> ScreensManifest:
    root = _expect_dict(payload, field="manifest")
    required_fields = ("schemaVersion", "generatedAtUtc", "screens")
    missing = [field for field in required_fields if field not in root]
    if missing:
        raise ManifestContractError(
            f"manifest is missing required field(s): {', '.join(missing)}"
        )

    schema_version = _expect_non_empty_string(root["schemaVersion"], field="schemaVersion")
    if schema_version != "1.0":
        raise ManifestContractError(
            f'schemaVersion must be "1.0", got: {schema_version}'
        )

    generated_at_utc = _expect_non_empty_string(root["generatedAtUtc"], field="generatedAtUtc")
    _validate_iso8601_datetime(generated_at_utc, field="generatedAtUtc")

    screens_raw = root["screens"]
    if not isinstance(screens_raw, list):
        raise ManifestContractError("screens must be an array.")

    screens = tuple(
        _validate_screen_entry(item, index=index) for index, item in enumerate(screens_raw)
    )
    seen_screen_ids: set[str] = set()
    for screen in screens:
        if screen.screen_id in seen_screen_ids:
            raise ManifestContractError(
                f"Duplicate screenId in screens manifest: {screen.screen_id}"
            )
        seen_screen_ids.add(screen.screen_id)

    return ScreensManifest(
        schema_version=schema_version,
        generated_at_utc=generated_at_utc,
        screens=screens,
    )


def load_screens_manifest_file(path: str | Path) -> ScreensManifest:
    manifest_path = Path(path).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return load_screens_manifest(payload)


__all__ = [
    "ManifestContractError",
    "ScreenManifestEntry",
    "ScreensManifest",
    "load_screens_manifest",
    "load_screens_manifest_file",
]
