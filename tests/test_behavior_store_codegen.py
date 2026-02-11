from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migrator.behavior_store_codegen import (  # noqa: E402
    DUPLICATE_ACTION_POLICY,
    generate_behavior_store_artifacts,
    plan_behavior_store_scaffold,
)
from migrator.models import (  # noqa: E402
    AstNode,
    EventIR,
    ScreenIR,
    SourceRef,
    TransactionIR,
)
from migrator.parser import parse_xml_file  # noqa: E402


FIXTURE_XML = Path(__file__).parent / "fixtures" / "simple_screen_fixture.txt"


def _src(path: str, node_path: str = "/Screen[1]") -> SourceRef:
    return SourceRef(file_path=path, node_path=node_path, line=1)


def _make_screen(events: list[EventIR], transactions: list[TransactionIR]) -> ScreenIR:
    return ScreenIR(
        screen_id="Behavior Action Test",
        root=AstNode(
            tag="Screen",
            attributes={"id": "BehaviorActionTest"},
            text=None,
            source=_src("behavior.xml"),
            children=[],
        ),
        events=events,
        transactions=transactions,
    )


class TestBehaviorStoreCodegen(unittest.TestCase):
    def test_plan_behavior_store_scaffold_names_event_and_transaction_actions(self) -> None:
        screen = _make_screen(
            events=[
                EventIR(
                    node_tag="Button",
                    node_id="btnSearch",
                    event_name="onclick",
                    handler="fnSearch",
                    source=_src("behavior.xml", "/Screen[1]/Button[1]"),
                ),
                EventIR(
                    node_tag="Grid",
                    node_id="grdOrders",
                    event_name="onrowclick",
                    handler="",
                    source=_src("behavior.xml", "/Screen[1]/Grid[1]"),
                ),
            ],
            transactions=[
                TransactionIR(
                    node_tag="Transaction",
                    node_id="txSearch",
                    transaction_id="SVC_ORDER_SEARCH",
                    endpoint="/api/orders/search",
                    method="POST",
                    source=_src("behavior.xml", "/Screen[1]/Transaction[1]"),
                ),
                TransactionIR(
                    node_tag="Transaction",
                    node_id=None,
                    transaction_id=None,
                    endpoint="/api/orders/save",
                    method="POST",
                    source=_src("behavior.xml", "/Screen[1]/Transaction[2]"),
                ),
            ],
        )

        plan = plan_behavior_store_scaffold(screen)
        action_names = [item.action_name for item in plan.actions]

        self.assertEqual(
            action_names,
            [
                "onFnSearch",
                "onOnrowclickGrdOrders",
                "requestSvcOrderSearch",
                "requestPostApiOrdersSave",
            ],
        )
        self.assertEqual(plan.summary.generated_actions, 4)
        self.assertEqual(plan.summary.duplicate_actions, 0)

    def test_plan_behavior_store_scaffold_applies_duplicate_suffix_policy(self) -> None:
        screen = _make_screen(
            events=[
                EventIR(
                    node_tag="Button",
                    node_id="btnSave",
                    event_name="onclick",
                    handler="fnSave",
                    source=_src("behavior.xml", "/Screen[1]/Button[1]"),
                ),
                EventIR(
                    node_tag="Button",
                    node_id="btnSave2",
                    event_name="onclick",
                    handler="fnSave();",
                    source=_src("behavior.xml", "/Screen[1]/Button[2]"),
                ),
            ],
            transactions=[
                TransactionIR(
                    node_tag="Transaction",
                    node_id="txSearch",
                    transaction_id="SVC_ORDER_SEARCH",
                    endpoint="/api/orders/search",
                    method="POST",
                    source=_src("behavior.xml", "/Screen[1]/Transaction[1]"),
                ),
                TransactionIR(
                    node_tag="Transaction",
                    node_id="txSearch2",
                    transaction_id="SVC_ORDER_SEARCH",
                    endpoint="/api/orders/search2",
                    method="POST",
                    source=_src("behavior.xml", "/Screen[1]/Transaction[2]"),
                ),
            ],
        )

        plan = plan_behavior_store_scaffold(screen)

        self.assertEqual(plan.actions[0].action_name, "onFnSave")
        self.assertEqual(plan.actions[1].action_name, "onFnSave2")
        self.assertEqual(plan.actions[1].duplicate_of_index, 1)
        self.assertEqual(plan.actions[1].duplicate_of_action_name, "onFnSave")

        self.assertEqual(plan.actions[2].action_name, "requestSvcOrderSearch")
        self.assertEqual(plan.actions[3].action_name, "requestSvcOrderSearch2")
        self.assertEqual(plan.actions[3].duplicate_of_index, 3)
        self.assertEqual(
            plan.actions[3].duplicate_of_action_name,
            "requestSvcOrderSearch",
        )

        self.assertEqual(plan.summary.duplicate_actions, 2)

    def test_generate_behavior_store_artifacts_writes_deterministic_files(self) -> None:
        parsed = parse_xml_file(FIXTURE_XML)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "generated-behavior"
            report = generate_behavior_store_artifacts(
                screen=parsed.screen,
                input_xml_path=str(FIXTURE_XML),
                out_dir=out_dir,
            )

            store_path = out_dir / "src" / "behavior" / "simple-screen-fixture.store.ts"
            actions_path = out_dir / "src" / "behavior" / "simple-screen-fixture.actions.ts"

            self.assertEqual(Path(report.store_file), store_path.resolve())
            self.assertEqual(Path(report.actions_file), actions_path.resolve())
            self.assertEqual(report.duplicate_action_policy, DUPLICATE_ACTION_POLICY)
            self.assertEqual(report.summary.generated_actions, 2)
            self.assertEqual(report.summary.generated_state_keys, 1)
            self.assertTrue(store_path.exists())
            self.assertTrue(actions_path.exists())

            store_text = store_path.read_text(encoding="utf-8")
            actions_text = actions_path.read_text(encoding="utf-8")

            self.assertIn("useSimpleScreenFixtureBehaviorStore", store_text)
            self.assertIn("bindingDsOrder", store_text)
            self.assertIn("createScreenBehaviorActions", store_text)
            self.assertIn("onFnSearch", actions_text)
            self.assertIn("requestSvcOrderSearch", actions_text)
            self.assertIn("duplicateActionPolicy", actions_text)


if __name__ == "__main__":
    unittest.main()
