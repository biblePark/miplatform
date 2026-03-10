from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.desktop_batch_workflow import build_batch_run_plan  # noqa: E402
from migrator.desktop_filepicker import (  # noqa: E402
    build_batch_job_payloads,
    list_known_project_keys,
    resolve_recent_project_key,
)


class TestDesktopFilePickerPayloads(unittest.TestCase):
    def test_build_batch_job_payloads_wires_plan_layout_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            preview_host = workspace / "preview-host"
            preview_host.mkdir(parents=True)

            profiles_dir = workspace / "data" / "input" / "profiles"
            profiles_dir.mkdir(parents=True)
            known_tags = profiles_dir / "known_tags.txt"
            known_attrs = profiles_dir / "known_attrs.json"
            known_tags.write_text("Form\nButton\n", encoding="utf-8")
            known_attrs.write_text('{"*": ["id"]}', encoding="utf-8")

            xml_dir = workspace / "xml"
            xml_dir.mkdir(parents=True)
            first_xml = xml_dir / "a.xml"
            second_xml = xml_dir / "b.xml"
            first_xml.write_text("<Form id='A'/>", encoding="utf-8")
            second_xml.write_text("<Form id='B'/>", encoding="utf-8")

            plan = build_batch_run_plan(
                output_root_dir=workspace / "out",
                source_xml_dir=xml_dir,
                recursive=False,
                glob_pattern="*.xml",
                run_id="demo-run",
            )

            payloads = build_batch_job_payloads(
                plan,
                workspace_root=workspace,
                strict=False,
            )
            self.assertEqual(len(payloads), 2)
            for item, payload in zip(plan.items, payloads, strict=False):
                self.assertEqual(payload["xml_path"], item.xml_path)
                self.assertEqual(payload["out_dir"], item.output.out_dir)
                self.assertEqual(payload["api_out_dir"], item.output.api_out_dir)
                self.assertEqual(payload["ui_out_dir"], item.output.ui_out_dir)
                self.assertEqual(payload["preview_host_dir"], item.output.preview_host_dir)
                self.assertEqual(payload["summary_out"], item.output.summary_out)
                self.assertTrue(payload["use_isolated_preview_host"])
                self.assertEqual(payload["preview_host_source_dir"], str(preview_host.resolve()))
                self.assertEqual(payload["known_tags_file"], str(known_tags.resolve()))
                self.assertEqual(payload["known_attrs_file"], str(known_attrs.resolve()))
                self.assertEqual(payload["render_policy_mode"], "auto")
                self.assertFalse(payload["strict"])
                self.assertTrue(payload["capture_text"])

    def test_build_batch_job_payloads_requires_preview_host_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            xml_dir = workspace / "xml"
            xml_dir.mkdir(parents=True)
            fixture_xml = xml_dir / "fixture.xml"
            fixture_xml.write_text("<Form id='A'/>", encoding="utf-8")

            plan = build_batch_run_plan(
                output_root_dir=workspace / "out",
                source_xml_file=fixture_xml,
                run_id="demo-run",
            )

            with self.assertRaises(FileNotFoundError):
                build_batch_job_payloads(plan, workspace_root=workspace)

    def test_build_batch_job_payloads_supports_shared_preview_host_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            preview_host = workspace / "preview-host"
            preview_host.mkdir(parents=True)

            xml_dir = workspace / "xml"
            xml_dir.mkdir(parents=True)
            first_xml = xml_dir / "a.xml"
            second_xml = xml_dir / "b.xml"
            first_xml.write_text("<Form id='A'/>", encoding="utf-8")
            second_xml.write_text("<Form id='B'/>", encoding="utf-8")

            plan = build_batch_run_plan(
                output_root_dir=workspace / "out",
                source_xml_dir=xml_dir,
                recursive=False,
                glob_pattern="*.xml",
                run_id="shared-preview",
            )
            shared_preview_host_dir = Path(plan.output.run_root_dir) / "preview-host"

            payloads = build_batch_job_payloads(
                plan,
                workspace_root=workspace,
                shared_preview_host_dir=shared_preview_host_dir,
            )
            self.assertEqual(len(payloads), 2)
            for payload in payloads:
                self.assertEqual(
                    payload["preview_host_dir"],
                    str(shared_preview_host_dir.resolve()),
                )

    def test_list_known_project_keys_collects_projects_and_history_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "out"
            (output_root / "projects" / "gs").mkdir(parents=True)
            (output_root / "projects" / "erp").mkdir(parents=True)
            (output_root / "projects" / "tmp.txt").write_text("ignore", encoding="utf-8")

            history_entries = [
                SimpleNamespace(project_key=None),
                SimpleNamespace(project_key="oms"),
                SimpleNamespace(project_key="gs"),
            ]
            with mock.patch(
                "migrator.desktop_filepicker.list_batch_run_history",
                return_value=history_entries,
            ):
                keys = list_known_project_keys(output_root)

            self.assertEqual(keys, ["erp", "gs", "oms"])

    def test_resolve_recent_project_key_returns_latest_non_empty_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "out"
            history_entries = [
                SimpleNamespace(project_key=None),
                SimpleNamespace(project_key="alpha"),
                SimpleNamespace(project_key="beta"),
            ]
            with mock.patch(
                "migrator.desktop_filepicker.list_batch_run_history",
                return_value=history_entries,
            ):
                key = resolve_recent_project_key(output_root)

            self.assertEqual(key, "alpha")


if __name__ == "__main__":
    unittest.main()
