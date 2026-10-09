import ast
import contextlib
import io
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))

import traffic_diagnostics as diagnostics


FAKE_KEY = "FAKE_TRAFFIC_KEY_DO_NOT_LOG"


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=None,
                 http_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error
        self.http_error = http_error
        self.url = f"https://example.invalid/?code={FAKE_KEY}"

    def raise_for_status(self):
        if self.http_error:
            raise self.http_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def emitted_records(output):
    return [
        json.loads(line.removeprefix("TRAFFIC_DIAG "))
        for line in output.splitlines()
        if line.startswith("TRAFFIC_DIAG ")
    ]


def load_heatmap_functions():
    app_path = ROOT / "demo" / "가멍고르멍_app_수정본.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    wanted = {
        "build_baseline_traffic_comparison",
        "build_live_traffic_heatmap_data",
    }
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    namespace = {
        "pd": pd,
        "emit_traffic_diagnostic": diagnostics.emit_traffic_diagnostic,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(app_path), "exec"), namespace)
    return namespace["build_live_traffic_heatmap_data"]


class TrafficDiagnosticsTests(unittest.TestCase):
    def test_app_request_calls_match_helper_signature(self):
        helper_path = ROOT / "demo" / "traffic_diagnostics.py"
        helper_tree = ast.parse(helper_path.read_text(encoding="utf-8"))
        helper = next(
            node for node in helper_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "fetch_hourly_traffic"
        )
        required_args = len(helper.args.args) - len(helper.args.defaults)

        app_path = ROOT / "demo" / "가멍고르멍_app_수정본.py"
        app_tree = ast.parse(app_path.read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(app_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "fetch_hourly_traffic"
        ]

        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(
                len(call.args), required_args,
                f"line {call.lineno} passes the wrong number of arguments",
            )

    def call_fetch(self, response=None, side_effect=None):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            with patch.object(
                diagnostics.requests, "get", return_value=response,
                side_effect=side_effect
            ) as get:
                result = None
                error = None
                try:
                    result = diagnostics.fetch_hourly_traffic(
                        FAKE_KEY, "2026-10-09", "12:00"
                    )
                except Exception as caught:
                    error = caught
        return result, error, get, stream.getvalue()

    def test_secret_statuses_never_emit_value(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            missing, missing_status = diagnostics.read_its_api_key({})

            class BrokenSecrets:
                def __getitem__(self, key):
                    raise RuntimeError(FAKE_KEY)

            unreadable, unreadable_status = diagnostics.read_its_api_key(
                BrokenSecrets()
            )
            present, present_status = diagnostics.read_its_api_key(
                {"ITS_API_KEY": FAKE_KEY}
            )

        self.assertEqual((missing, missing_status), ("", "missing"))
        self.assertEqual((unreadable, unreadable_status), ("", "read_error"))
        self.assertEqual((present, present_status), (FAKE_KEY, "present"))
        self.assertNotIn(FAKE_KEY, stream.getvalue())
        self.assertEqual(
            [row["status"] for row in emitted_records(stream.getvalue())],
            ["missing", "read_error", "present"],
        )

    def test_missing_secret_skips_request(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            with patch.object(diagnostics.requests, "get") as get:
                result = diagnostics.fetch_hourly_traffic(
                    "", "2026-10-09", "12:00"
                )
        get.assert_not_called()
        self.assertFalse(result["available"])
        self.assertEqual(emitted_records(stream.getvalue()), [
            {"event": "request_skipped", "reason": "secret_missing"}
        ])

    def test_timeout_and_connection_failures_are_categorized(self):
        for error, expected in [
            (requests.Timeout(f"timeout {FAKE_KEY}"), "timeout"),
            (requests.ConnectionError(f"connection {FAKE_KEY}"), "connection"),
        ]:
            _, caught, _, output = self.call_fetch(side_effect=error)
            self.assertIs(caught, error)
            self.assertEqual(emitted_records(output)[-1]["error"], expected)
            self.assertNotIn(FAKE_KEY, output)
            self.assertNotIn("code=", output)
            self.assertNotIn(str(error), output)

    def test_http_error_logs_status_only(self):
        error = requests.HTTPError(
            f"HTTP failed {FAKE_KEY}",
            response=SimpleNamespace(status_code=403),
        )
        response = FakeResponse(status_code=403, http_error=error)
        _, caught, _, output = self.call_fetch(response=response)
        self.assertIs(caught, error)
        record = emitted_records(output)[-1]
        self.assertEqual(record["error"], "http_status")
        self.assertEqual(record["http_status"], 403)
        self.assertNotIn(FAKE_KEY, output)
        self.assertNotIn("code=", output)
        self.assertNotIn(str(error), output)

    def test_json_and_response_validation_failures_do_not_log_payload(self):
        parse_error = ValueError(f"invalid body {FAKE_KEY} RESPONSE_BODY_SECRET")
        _, caught, _, output = self.call_fetch(
            response=FakeResponse(json_error=parse_error)
        )
        self.assertIs(caught, parse_error)
        self.assertEqual(emitted_records(output)[-1]["error"], "invalid_json")

        bad_payload = {"result": "success", "info": [{"private": FAKE_KEY}]}
        _, caught, _, output = self.call_fetch(
            response=FakeResponse(payload=bad_payload)
        )
        self.assertIsInstance(caught, ValueError)
        self.assertEqual(
            emitted_records(output)[-1]["outcome"],
            "required_columns_missing",
        )
        self.assertNotIn(FAKE_KEY, output)
        self.assertNotIn("code=", output)
        self.assertNotIn("RESPONSE_BODY_SECRET", output)
        self.assertNotIn(str(caught), output)

    def test_reference_time_missing_or_inconsistent_is_detected(self):
        for rows, expected in [
            ([{"link_id": "A", "sped": 10, "trvl_hh": 1}], "reference_missing"),
            ([
                {"link_id": "A", "sped": 10, "trvl_hh": 1, "prcn_dt": "2026100912"},
                {"link_id": "B", "sped": 12, "trvl_hh": 1, "prcn_dt": "2026100913"},
            ], "reference_invalid"),
        ]:
            _, caught, _, output = self.call_fetch(
                response=FakeResponse(payload={"result": "success", "info": rows})
            )
            self.assertIsInstance(caught, ValueError)
            self.assertEqual(
                emitted_records(output)[-1]["outcome"], expected
            )

    def test_api_rejected_empty_and_valid_response(self):
        rejected, error, _, output = self.call_fetch(
            response=FakeResponse(payload={"result": "denied", "info": []})
        )
        self.assertIsNone(error)
        self.assertFalse(rejected["available"])
        self.assertEqual(emitted_records(output)[-1]["outcome"], "api_rejected")

        empty, error, _, output = self.call_fetch(
            response=FakeResponse(payload={"result": "success", "info": []})
        )
        self.assertIsNone(error)
        self.assertFalse(empty["available"])
        self.assertEqual(emitted_records(output)[-1]["outcome"], "empty_info")

        valid = {
            "result": "success",
            "info": [{
                "link_id": "LINK_PRIVATE_ID",
                "sped": "15",
                "trvl_hh": "2",
                "prcn_dt": "202610091200",
            }],
        }
        accepted, error, _, output = self.call_fetch(
            response=FakeResponse(payload=valid)
        )
        self.assertIsNone(error)
        self.assertTrue(accepted["available"])
        self.assertEqual(accepted["info_cnt"], 1)
        self.assertEqual(emitted_records(output)[-1]["outcome"], "success")
        request_result = next(
            row for row in emitted_records(output)
            if row["event"] == "request_result"
        )
        self.assertEqual(request_result["http_status"], 200)
        self.assertGreaterEqual(request_result["elapsed_ms"], 0)
        self.assertNotIn("LINK_PRIVATE_ID", output)
        self.assertNotIn(FAKE_KEY, output)
        self.assertNotIn("code=", output)

    def test_log_failure_does_not_change_success_result(self):
        response = FakeResponse(payload={
            "result": "success",
            "info": [{
                "link_id": "A", "sped": "10", "trvl_hh": "1",
                "prcn_dt": "202610091200",
            }],
        })
        with patch("builtins.print", side_effect=OSError("log unavailable")):
            with patch.object(diagnostics.requests, "get", return_value=response):
                result = diagnostics.fetch_hourly_traffic(
                    FAKE_KEY, "2026-10-09", "12:00"
                )
        self.assertTrue(result["available"])

    def test_diagnostic_allowlist_rejects_unexpected_fields(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            diagnostics.emit_traffic_diagnostic(
                "fallback",
                active=True,
                reason="heatmap_empty",
                exception=FAKE_KEY,
                request_url=f"?code={FAKE_KEY}",
            )
        self.assertEqual(emitted_records(stream.getvalue()), [{
            "event": "fallback",
            "active": True,
            "reason": "heatmap_empty",
        }])
        self.assertNotIn(FAKE_KEY, stream.getvalue())

    def test_zero_matches_and_successful_heatmap(self):
        build_heatmap = load_heatmap_functions()
        reference_dt = datetime(2026, 10, 9, 12)
        current = pd.DataFrame([{"link_id": "LINK_PRIVATE_ID", "sped": 10}])
        baseline = pd.DataFrame([{
            "LINK_ID": "LINK_PRIVATE_ID",
            "weekday": reference_dt.weekday(),
            "hour": reference_dt.hour,
            "baseline_quality": "sufficient",
            "baseline_median_speed": 10,
        }])

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            no_coordinates = build_heatmap(
                current,
                baseline,
                pd.DataFrame([{
                    "LINK_ID": "OTHER_PRIVATE_ID",
                    "longitude": 126.5,
                    "latitude": 33.5,
                }]),
                reference_dt,
            )
        self.assertTrue(no_coordinates.empty)
        self.assertEqual(
            emitted_records(stream.getvalue())[-1]["outcome"],
            "coordinates_unmatched",
        )
        self.assertNotIn("LINK_PRIVATE_ID", stream.getvalue())
        self.assertNotIn("OTHER_PRIVATE_ID", stream.getvalue())

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = build_heatmap(
                current,
                baseline,
                pd.DataFrame([{
                    "LINK_ID": "LINK_PRIVATE_ID",
                    "longitude": 126.5,
                    "latitude": 33.5,
                }]),
                reference_dt,
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["traffic_weight"], 0)
        self.assertEqual(
            emitted_records(stream.getvalue())[-1]["output_rows"], 1
        )
        self.assertNotIn("LINK_PRIVATE_ID", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
