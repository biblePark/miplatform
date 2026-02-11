"""MIPLATFORM migrator core package."""

from .models import ParseConfig, ParseReport
from .parser import ParseStrictError, parse_xml_file
from .preview_manifest import (
    ManifestContractError,
    ScreenManifestEntry,
    ScreensManifest,
    load_screens_manifest,
    load_screens_manifest_file,
)
from .ui_codegen import UiCodegenReport, UiCodegenSummary, generate_ui_codegen_artifacts
from .behavior_store_codegen import (
    BehaviorStorePlan,
    BehaviorStoreReport,
    BehaviorStoreSummary,
    generate_behavior_store_artifacts,
    plan_behavior_store_scaffold,
)
from .preview_sync import (
    GeneratedScreenEntry,
    PreviewSyncReport,
    sync_preview_host,
)
from .validator import (
    compute_canonical_hash_pair,
    compute_roundtrip_mismatches,
    compute_roundtrip_structural_diff,
)

__all__ = [
    "ParseConfig",
    "ParseReport",
    "ParseStrictError",
    "ManifestContractError",
    "GeneratedScreenEntry",
    "PreviewSyncReport",
    "ScreenManifestEntry",
    "ScreensManifest",
    "BehaviorStorePlan",
    "BehaviorStoreReport",
    "BehaviorStoreSummary",
    "UiCodegenReport",
    "UiCodegenSummary",
    "compute_canonical_hash_pair",
    "compute_roundtrip_mismatches",
    "compute_roundtrip_structural_diff",
    "generate_behavior_store_artifacts",
    "generate_ui_codegen_artifacts",
    "load_screens_manifest",
    "load_screens_manifest_file",
    "parse_xml_file",
    "plan_behavior_store_scaffold",
    "sync_preview_host",
]
