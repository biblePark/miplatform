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
    "ScreenManifestEntry",
    "ScreensManifest",
    "compute_canonical_hash_pair",
    "compute_roundtrip_mismatches",
    "compute_roundtrip_structural_diff",
    "load_screens_manifest",
    "load_screens_manifest_file",
    "parse_xml_file",
]
