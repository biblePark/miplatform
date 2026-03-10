from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from .preview_manifest import ScreenManifestEntry, load_screens_manifest

SUPPORTED_SCREEN_EXTENSIONS = {".tsx", ".jsx", ".ts", ".js"}
SCREEN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
NON_SCREEN_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
GENERATED_ENTRY_PREFIX = "screens/generated/"


@dataclass(slots=True)
class GeneratedScreenEntry:
    screen_id: str
    entry_module: str
    import_module: str
    source_xml_path: str
    source_node_path: str
    title: str | None = None

    def to_manifest_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {
            "screenId": self.screen_id,
            "entryModule": self.entry_module,
            "sourceXmlPath": self.source_xml_path,
            "sourceNodePath": self.source_node_path,
        }
        if self.title:
            payload["title"] = self.title
        return payload


@dataclass(slots=True)
class PreviewSyncReport:
    generated_screens_dir: str
    preview_host_dir: str
    manifest_file: str
    registry_generated_file: str
    preserved_screen_count: int
    generated_screen_count: int
    generated_screen_ids: list[str]
    generated_entry_modules: list[str]
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ensure_string(value: object, *, field_name: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {field_name} must be a non-empty string when provided.")
    return value.strip()


def _read_preview_metadata(module_file: Path) -> dict[str, str]:
    metadata_file = module_file.with_suffix(".preview.json")
    if not metadata_file.exists():
        return {}

    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{metadata_file}: metadata payload must be an object.")

    metadata: dict[str, str] = {}
    for field_name in ("screenId", "title", "sourceXmlPath", "sourceNodePath"):
        if field_name in payload:
            metadata[field_name] = _ensure_string(
                payload[field_name],
                field_name=field_name,
                path=metadata_file,
            )
    return metadata


def _to_screen_id(raw: str) -> str:
    collapsed = raw.replace("\\", "/").replace("/", "-").strip()
    collapsed = NON_SCREEN_ID_RE.sub("-", collapsed).strip("-_")
    if not collapsed:
        collapsed = "screen"
    if not collapsed[0].isalnum():
        collapsed = f"s{collapsed}"
    return collapsed


def _allocate_unique_screen_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _relative_posix(
    path: Path,
    *,
    base: Path,
    allow_absolute_fallback: bool = False,
) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        if allow_absolute_fallback:
            return path.resolve().as_posix()
        raise


def _to_import_module(module_file: Path, *, registry_dir: Path) -> str:
    relative = module_file.resolve().relative_to(registry_dir.resolve(), walk_up=True)
    no_suffix = relative.with_suffix("")
    module_path = no_suffix.as_posix()
    if not module_path.startswith("."):
        module_path = f"./{module_path}"
    return module_path


def _list_generated_screen_files(generated_screens_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in generated_screens_dir.rglob("*")
        if path.is_file()
        and path.suffix in SUPPORTED_SCREEN_EXTENSIONS
        and not path.name.endswith(".d.ts")
    )


def _build_generated_entries(
    *,
    generated_screens_dir: Path,
    registry_dir: Path,
    project_root: Path,
    reserved_screen_ids: set[str],
    warnings: list[str],
) -> list[GeneratedScreenEntry]:
    screen_files = _list_generated_screen_files(generated_screens_dir)
    entries: list[GeneratedScreenEntry] = []
    used_ids = set(reserved_screen_ids)

    for module_file in screen_files:
        try:
            module_file.resolve().relative_to(project_root.resolve())
        except ValueError:
            warnings.append(
                "Skipped generated screen module outside preview workspace root: "
                f"{module_file.resolve()}"
            )
            continue

        module_token = _relative_posix(
            module_file.with_suffix(""),
            base=generated_screens_dir,
        )
        metadata = _read_preview_metadata(module_file)

        if "screenId" in metadata:
            screen_id = metadata["screenId"]
            if not SCREEN_ID_RE.match(screen_id):
                raise ValueError(
                    f"{module_file.with_suffix('.preview.json')}: screenId has invalid format: "
                    f"{screen_id}"
                )
        else:
            screen_id = _to_screen_id(module_token)

        unique_screen_id = _allocate_unique_screen_id(screen_id, used_ids)
        entry_module = f"{GENERATED_ENTRY_PREFIX}{module_token}"
        source_xml_path = metadata.get(
            "sourceXmlPath",
            _relative_posix(
                module_file,
                base=project_root,
                allow_absolute_fallback=True,
            ),
        )
        source_node_path = metadata.get(
            "sourceNodePath",
            f"/generated/screens/{unique_screen_id}",
        )

        entries.append(
            GeneratedScreenEntry(
                screen_id=unique_screen_id,
                entry_module=entry_module,
                import_module=_to_import_module(module_file, registry_dir=registry_dir),
                source_xml_path=source_xml_path,
                source_node_path=source_node_path,
                title=metadata.get("title"),
            )
        )

    entries.sort(key=lambda item: (item.screen_id, item.entry_module))
    return entries


def _load_preserved_screens(manifest_file: Path) -> tuple[str, list[ScreenManifestEntry]]:
    if not manifest_file.exists():
        return "./screens.manifest.schema.json", []

    raw_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    parsed_manifest = load_screens_manifest(raw_payload)
    schema_ref = raw_payload.get("$schema")
    schema = schema_ref if isinstance(schema_ref, str) and schema_ref.strip() else "./screens.manifest.schema.json"

    preserved = [
        entry
        for entry in parsed_manifest.screens
        if not entry.entry_module.startswith(GENERATED_ENTRY_PREFIX)
    ]
    return schema, preserved


def _render_registry_generated(entries: list[GeneratedScreenEntry]) -> str:
    lines = [
        "/*",
        " * Auto-generated by `mifl-migrator sync-preview`.",
        " * Do not edit manually.",
        " */",
        "",
        'import type { ScreenModuleLoader } from "../manifest/types";',
        "",
        "export const generatedScreenModuleLoaders: Record<string, ScreenModuleLoader> = {",
    ]

    for entry in entries:
        lines.append(
            f'  "{entry.entry_module}": () => import("{entry.import_module}"),'
        )

    lines.extend(["};", ""])
    return "\n".join(lines)


def sync_preview_host(
    *,
    generated_screens_dir: str | Path,
    preview_host_dir: str | Path = "preview-host",
    manifest_file: str | Path | None = None,
    registry_generated_file: str | Path | None = None,
    pretty: bool = True,
) -> PreviewSyncReport:
    generated_dir = Path(generated_screens_dir).resolve()
    host_dir = Path(preview_host_dir).resolve()
    if not generated_dir.exists() or not generated_dir.is_dir():
        raise FileNotFoundError(f"Generated screens directory not found: {generated_dir}")
    if not host_dir.exists() or not host_dir.is_dir():
        raise FileNotFoundError(f"Preview host directory not found: {host_dir}")

    manifest_path = (
        Path(manifest_file).resolve()
        if manifest_file
        else host_dir / "src" / "manifest" / "screens.manifest.json"
    )
    registry_generated_path = (
        Path(registry_generated_file).resolve()
        if registry_generated_file
        else host_dir / "src" / "screens" / "registry.generated.ts"
    )

    schema_ref, preserved_entries = _load_preserved_screens(manifest_path)
    reserved_screen_ids = {entry.screen_id for entry in preserved_entries}

    warnings: list[str] = []

    generated_entries = _build_generated_entries(
        generated_screens_dir=generated_dir,
        registry_dir=registry_generated_path.parent,
        project_root=host_dir.parent,
        reserved_screen_ids=reserved_screen_ids,
        warnings=warnings,
    )

    generated_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    manifest_payload = {
        "$schema": schema_ref,
        "schemaVersion": "1.0",
        "generatedAtUtc": generated_at_utc,
        "screens": [
            {
                "screenId": entry.screen_id,
                "entryModule": entry.entry_module,
                "sourceXmlPath": entry.source_xml_path,
                "sourceNodePath": entry.source_node_path,
                **({"title": entry.title} if entry.title else {}),
            }
            for entry in preserved_entries
        ]
        + [entry.to_manifest_dict() for entry in generated_entries],
    }

    # Defensive contract check before writing artifacts.
    load_screens_manifest(manifest_payload)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            manifest_payload,
            indent=2 if pretty else None,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry_generated_path.parent.mkdir(parents=True, exist_ok=True)
    registry_generated_path.write_text(
        _render_registry_generated(generated_entries),
        encoding="utf-8",
    )

    if not generated_entries:
        warnings.append("No generated screen modules were found.")

    return PreviewSyncReport(
        generated_screens_dir=str(generated_dir),
        preview_host_dir=str(host_dir),
        manifest_file=str(manifest_path),
        registry_generated_file=str(registry_generated_path),
        preserved_screen_count=len(preserved_entries),
        generated_screen_count=len(generated_entries),
        generated_screen_ids=[entry.screen_id for entry in generated_entries],
        generated_entry_modules=[entry.entry_module for entry in generated_entries],
        warnings=warnings,
        generated_at_utc=generated_at_utc,
    )


__all__ = [
    "GeneratedScreenEntry",
    "PreviewSyncReport",
    "sync_preview_host",
]
