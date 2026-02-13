from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from .preview_manifest import ScreenManifestEntry, load_screens_manifest

SUPPORTED_SCREEN_EXTENSIONS: tuple[str, ...] = (".tsx", ".jsx", ".ts", ".js")
GENERATED_ENTRY_PREFIX = "screens/generated/"
REGISTRY_ENTRY_RE = re.compile(
    r'^\s*"(?P<entry_module>screens/[A-Za-z0-9/_-]+)"\s*:\s*\(\)\s*=>\s*import\("'
)


@dataclass(slots=True)
class PreviewSmokeScreenEvidence:
    screen_id: str
    entry_module: str
    route_path: str
    source_xml_path: str
    source_node_path: str
    loader_registered: bool
    module_present: bool
    route_resolvable: bool
    module_file: str | None = None
    unresolved_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PreviewSmokeReport:
    generated_screens_dir: str
    preview_host_dir: str
    manifest_file: str
    registry_generated_file: str
    manifest_screen_count: int
    generated_screen_count: int
    route_paths: list[str]
    unresolved_module_count: int
    screens: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def has_unresolved_modules(self) -> bool:
        return self.unresolved_module_count > 0


def _load_registry_loader_keys(registry_generated_file: Path) -> set[str]:
    if not registry_generated_file.exists() or not registry_generated_file.is_file():
        raise FileNotFoundError(
            f"Preview host generated registry file not found: {registry_generated_file}"
        )

    keys: set[str] = set()
    for line in registry_generated_file.read_text(encoding="utf-8").splitlines():
        match = REGISTRY_ENTRY_RE.match(line)
        if match:
            keys.add(match.group("entry_module"))
    return keys


def _resolve_generated_module_file(
    *,
    entry_module: str,
    generated_screens_dir: Path,
) -> Path | None:
    module_stem = entry_module.removeprefix(GENERATED_ENTRY_PREFIX)
    if not module_stem:
        return None

    for extension in SUPPORTED_SCREEN_EXTENSIONS:
        candidate = generated_screens_dir / f"{module_stem}{extension}"
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def _build_screen_evidence(
    *,
    screen: ScreenManifestEntry,
    generated_screens_dir: Path,
    loader_keys: set[str],
) -> PreviewSmokeScreenEvidence:
    module_file = _resolve_generated_module_file(
        entry_module=screen.entry_module,
        generated_screens_dir=generated_screens_dir,
    )
    loader_registered = screen.entry_module in loader_keys
    module_present = module_file is not None
    route_resolvable = loader_registered and module_present

    unresolved_reasons: list[str] = []
    if not loader_registered:
        unresolved_reasons.append("missing_registry_loader")
    if not module_present:
        unresolved_reasons.append("missing_module_file")

    return PreviewSmokeScreenEvidence(
        screen_id=screen.screen_id,
        entry_module=screen.entry_module,
        route_path=screen.preview_route(),
        source_xml_path=screen.source_xml_path,
        source_node_path=screen.source_node_path,
        loader_registered=loader_registered,
        module_present=module_present,
        route_resolvable=route_resolvable,
        module_file=str(module_file) if module_file else None,
        unresolved_reasons=unresolved_reasons,
    )


def smoke_preview_host(
    *,
    generated_screens_dir: str | Path,
    preview_host_dir: str | Path = "preview-host",
    manifest_file: str | Path | None = None,
    registry_generated_file: str | Path | None = None,
) -> PreviewSmokeReport:
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

    if not manifest_path.exists() or not manifest_path.is_file():
        raise FileNotFoundError(f"Preview host manifest file not found: {manifest_path}")

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = load_screens_manifest(manifest_payload)
    generated_screens = sorted(
        (
            screen
            for screen in manifest.screens
            if screen.entry_module.startswith(GENERATED_ENTRY_PREFIX)
        ),
        key=lambda screen: (screen.screen_id, screen.entry_module),
    )
    loader_keys = _load_registry_loader_keys(registry_generated_path)

    evidence = [
        _build_screen_evidence(
            screen=screen,
            generated_screens_dir=generated_dir,
            loader_keys=loader_keys,
        )
        for screen in generated_screens
    ]
    route_paths = [item.route_path for item in evidence]
    unresolved_module_count = sum(1 for item in evidence if not item.route_resolvable)

    warnings: list[str] = []
    if not generated_screens:
        warnings.append("No generated screen entries were found in screens manifest.")
    if unresolved_module_count > 0:
        warnings.append(
            f"Unresolved generated screen modules detected: {unresolved_module_count}"
        )

    return PreviewSmokeReport(
        generated_screens_dir=str(generated_dir),
        preview_host_dir=str(host_dir),
        manifest_file=str(manifest_path),
        registry_generated_file=str(registry_generated_path),
        manifest_screen_count=len(manifest.screens),
        generated_screen_count=len(generated_screens),
        route_paths=route_paths,
        unresolved_module_count=unresolved_module_count,
        screens=[item.to_dict() for item in evidence],
        warnings=warnings,
    )


__all__ = [
    "PreviewSmokeReport",
    "PreviewSmokeScreenEvidence",
    "smoke_preview_host",
]
