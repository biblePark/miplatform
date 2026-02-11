from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.api_mapping import (  # noqa: E402
    MAPPING_STATUS_FAILURE,
    MAPPING_STATUS_SUCCESS,
    MAPPING_STATUS_UNSUPPORTED,
    generate_api_mapping_artifacts,
    plan_transaction_api_mapping,
)
from migrator.models import (  # noqa: E402
    AstNode,
    ScreenIR,
    SourceRef,
    TransactionIR,
)
from migrator.parser import parse_xml_file  # noqa: E402


FIXTURE_XML = Path(__file__).parent / "fixtures" / "simple_screen.xml"


def _src(path: str) -> SourceRef:
    return SourceRef(file_path=path, node_path="/Screen[1]", line=1)


class TestApiMapping(unittest.TestCase):
    def test_plan_transaction_api_mapping_classifies_statuses(self) -> None:
        transactions = [
            TransactionIR(
                node_tag="Transaction",
                node_id="tx1",
                transaction_id="SVC_ORDER_SEARCH",
                endpoint="api/orders/search",
                method="post",
                source=_src("a.xml"),
            ),
            TransactionIR(
                node_tag="Transaction",
                node_id="tx2",
                transaction_id="SVC_ORDER_EMPTY",
                endpoint=None,
                method="GET",
                source=_src("a.xml"),
            ),
            TransactionIR(
                node_tag="Transaction",
                node_id="tx3",
                transaction_id="SVC_ORDER_HEAD",
                endpoint="/api/orders/head",
                method="HEAD",
                source=_src("a.xml"),
            ),
            TransactionIR(
                node_tag="Transaction",
                node_id="tx4",
                transaction_id="SVC_ORDER_SEARCH_DUP",
                endpoint="/api/orders/search",
                method="POST",
                source=_src("a.xml"),
            ),
        ]

        plan = plan_transaction_api_mapping(transactions)

        self.assertEqual(plan.summary.total_transactions, 4)
        self.assertEqual(plan.summary.mapped_success, 1)
        self.assertEqual(plan.summary.mapped_failure, 2)
        self.assertEqual(plan.summary.unsupported, 1)

        self.assertEqual(plan.results[0].status, MAPPING_STATUS_SUCCESS)
        self.assertEqual(plan.results[0].route_method, "post")
        self.assertEqual(plan.results[0].route_path, "/api/orders/search")
        self.assertEqual(plan.results[0].service_function, "svcOrderSearch")

        self.assertEqual(plan.results[1].status, MAPPING_STATUS_FAILURE)
        self.assertEqual(plan.results[1].reason, "missing_endpoint")

        self.assertEqual(plan.results[2].status, MAPPING_STATUS_UNSUPPORTED)
        self.assertEqual(plan.results[2].reason, "unsupported_http_method:HEAD")

        self.assertEqual(plan.results[3].status, MAPPING_STATUS_FAILURE)
        self.assertEqual(
            plan.results[3].reason,
            "duplicate_route:POST:/api/orders/search",
        )

    def test_generate_api_mapping_artifacts_writes_stubs(self) -> None:
        parsed = parse_xml_file(FIXTURE_XML)
        screen = parsed.screen

        with tempfile.TemporaryDirectory() as tmp_dir:
            report = generate_api_mapping_artifacts(
                screen=screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=tmp_dir,
            )

            route_path = Path(report.route_file)
            service_path = Path(report.service_file)
            self.assertTrue(route_path.exists())
            self.assertTrue(service_path.exists())

            route_text = route_path.read_text(encoding="utf-8")
            service_text = service_path.read_text(encoding="utf-8")

            self.assertIn('router.post("/api/orders/search"', route_text)
            self.assertIn("service.svcOrderSearch", route_text)
            self.assertIn("async function svcOrderSearch(req)", service_text)

            self.assertEqual(report.summary.total_transactions, 1)
            self.assertEqual(report.summary.mapped_success, 1)
            self.assertEqual(report.summary.mapped_failure, 0)
            self.assertEqual(report.summary.unsupported, 0)
            self.assertEqual(report.results[0].status, MAPPING_STATUS_SUCCESS)

    def test_generate_api_mapping_artifacts_no_success_writes_empty_stubs(self) -> None:
        source = _src("broken.xml")
        screen = ScreenIR(
            screen_id="BrokenScreen",
            root=AstNode(
                tag="Screen",
                attributes={},
                text=None,
                source=source,
                children=[],
            ),
            transactions=[
                TransactionIR(
                    node_tag="Transaction",
                    node_id="broken1",
                    transaction_id="BROKEN_ONE",
                    endpoint=None,
                    method="POST",
                    source=source,
                ),
                TransactionIR(
                    node_tag="Transaction",
                    node_id="broken2",
                    transaction_id="BROKEN_TWO",
                    endpoint="/api/broken/two",
                    method="TRACE",
                    source=source,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            report = generate_api_mapping_artifacts(
                screen=screen,
                input_xml_path=source.file_path,
                out_dir=tmp_dir,
            )

            route_text = Path(report.route_file).read_text(encoding="utf-8")
            service_text = Path(report.service_file).read_text(encoding="utf-8")

            self.assertIn("No transactions were eligible", route_text)
            self.assertIn("module.exports = {};", service_text)
            self.assertEqual(report.summary.mapped_success, 0)
            self.assertEqual(report.summary.mapped_failure, 1)
            self.assertEqual(report.summary.unsupported, 1)
            self.assertEqual(
                report.warnings,
                ["Mapping failures: 1", "Unsupported transaction mappings: 1"],
            )


if __name__ == "__main__":
    unittest.main()
