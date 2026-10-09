"""Safe, low-detail diagnostics for the live traffic request path."""

import json
import time
from datetime import datetime

import pandas as pd
import requests


_EVENT_FIELDS = {
    "secret_lookup": {"status": {"present", "missing", "read_error"}},
    "request_skipped": {
        "reason": {"secret_missing", "fresh_cache", "place_unselected"}
    },
    "request_started": {"started": bool},
    "request_result": {
        "http_status": int,
        "elapsed_ms": int,
        "error": {
            "none", "timeout", "connection", "http_status",
            "invalid_json", "response_invalid", "other"
        },
    },
    "response_validation": {
        "outcome": {
            "success", "api_rejected", "empty_info",
            "required_columns_missing", "reference_missing",
            "reference_invalid", "response_invalid"
        },
        "rows": int,
        "missing_required": bool,
        "reference_time_count": int,
    },
    "traffic_inputs": {
        "traffic_usable": bool,
        "baseline_available": bool,
        "baseline_rows": int,
        "coordinate_available": bool,
        "coordinate_rows": int,
    },
    "heatmap_match": {
        "outcome": {
            "input_empty", "comparison_empty", "matched",
            "coordinates_unmatched", "invalid_rows", "empty"
        },
        "comparison_rows": int,
        "coordinate_matched_rows": int,
        "valid_rows": int,
        "output_rows": int,
        "error_category": {"response_invalid", "other"},
    },
    "fallback": {
        "active": bool,
        "reason": {
            "none", "traffic_unavailable", "baseline_unavailable",
            "coordinates_unavailable", "comparison_empty",
            "coordinates_unmatched", "invalid_rows", "heatmap_error",
            "place_unselected", "expired_cache", "no_baseline",
            "heatmap_empty"
        },
    },
}


def emit_traffic_diagnostic(event, **fields):
    """Print only allowlisted scalar fields; diagnostics must never break the app."""
    schema = _EVENT_FIELDS.get(event)
    if schema is None:
        return

    record = {"event": event}
    for name, value in fields.items():
        allowed = schema.get(name)
        if allowed is None:
            continue

        if isinstance(allowed, set):
            if isinstance(value, str) and value in allowed:
                record[name] = value
            continue

        if allowed is bool:
            if type(value) is bool:
                record[name] = value
            continue

        if allowed is int:
            if type(value) is int and value >= 0:
                record[name] = min(value, 2_147_483_647)
            elif value is None and name == "http_status":
                record[name] = None

    try:
        print("TRAFFIC_DIAG " + json.dumps(record, separators=(",", ":")))
    except Exception:
        # Logging must not change request, data, or fallback behavior.
        pass


def read_its_api_key(secrets):
    """Read the configured key without exposing it; return (key, safe status)."""
    try:
        api_key = secrets["ITS_API_KEY"]
    except KeyError:
        api_key = ""
        status = "missing"
    except Exception:
        api_key = ""
        status = "read_error"
    else:
        status = "present" if api_key else "missing"

    emit_traffic_diagnostic("secret_lookup", status=status)
    return api_key, status


def _error_category(error):
    if isinstance(error, requests.Timeout):
        return "timeout"
    if isinstance(error, requests.ConnectionError):
        return "connection"
    if isinstance(error, requests.HTTPError):
        return "http_status"
    if isinstance(error, (ValueError, AttributeError, TypeError, KeyError)):
        return "response_invalid"
    return "other"


def traffic_error_category(error):
    return _error_category(error)


def fetch_hourly_traffic(api_key, visit_date, visit_time):
    visit_dt = datetime.strptime(
        f"{visit_date} {visit_time}",
        "%Y-%m-%d %H:%M"
    )

    stat_dt = visit_dt.strftime("%Y%m%d%H")

    if not api_key:
        emit_traffic_diagnostic(
            "request_skipped", reason="secret_missing"
        )
        return {
            "available": False,
            "stat_dt": stat_dt,
            "result": "secret_unavailable",
            "info_cnt": 0,
            "data": pd.DataFrame()
        }

    emit_traffic_diagnostic("request_started", started=True)
    started_at = time.monotonic()

    try:
        response = requests.get(
            "http://api.jejuits.go.kr/api/getFrafficInfo",
            params={"code": api_key, "type": "L"},
            timeout=10
        )
    except Exception as error:
        emit_traffic_diagnostic(
            "request_result",
            http_status=None,
            elapsed_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            error=_error_category(error),
        )
        raise

    try:
        response.raise_for_status()
    except Exception as error:
        emit_traffic_diagnostic(
            "request_result",
            http_status=getattr(response, "status_code", None),
            elapsed_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            error=_error_category(error),
        )
        raise

    try:
        data = response.json()
    except Exception as error:
        emit_traffic_diagnostic(
            "request_result",
            http_status=getattr(response, "status_code", None),
            elapsed_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            error=("invalid_json" if isinstance(error, ValueError) else "other"),
        )
        raise

    emit_traffic_diagnostic(
        "request_result",
        http_status=getattr(response, "status_code", None),
        elapsed_ms=max(0, int((time.monotonic() - started_at) * 1000)),
        error="none",
    )

    validation_logged = False
    try:
        if data.get("result") != "success":
            emit_traffic_diagnostic(
                "response_validation", outcome="api_rejected", rows=0
            )
            validation_logged = True
            return {
                "available": False,
                "stat_dt": stat_dt,
                "result": data.get("result"),
                "info_cnt": 0,
                "data": pd.DataFrame()
            }

        info = data.get("info", [])
        if len(info) == 0:
            emit_traffic_diagnostic(
                "response_validation", outcome="empty_info", rows=0
            )
            validation_logged = True
            return {
                "available": False,
                "stat_dt": stat_dt,
                "result": "success",
                "info_cnt": 0,
                "data": pd.DataFrame()
            }

        hourly_df = pd.DataFrame(info)
        required_columns = ["link_id", "sped", "trvl_hh"]
        missing_columns = [
            column for column in required_columns
            if column not in hourly_df.columns
        ]

        if missing_columns:
            emit_traffic_diagnostic(
                "response_validation",
                outcome="required_columns_missing",
                rows=len(hourly_df),
                missing_required=True,
            )
            validation_logged = True
            raise ValueError(
                "ITS 응답 필수 컬럼 누락: " + ", ".join(missing_columns)
            )

        hourly_df["link_id"] = (
            hourly_df["link_id"].astype("string").str.strip()
        )
        hourly_df["sped"] = pd.to_numeric(
            hourly_df["sped"], errors="coerce"
        )
        hourly_df["trvl_hh"] = pd.to_numeric(
            hourly_df["trvl_hh"], errors="coerce"
        )

        if "prcn_dt" not in hourly_df.columns:
            emit_traffic_diagnostic(
                "response_validation",
                outcome="reference_missing",
                rows=len(hourly_df),
                missing_required=True,
                reference_time_count=0,
            )
            validation_logged = True
            raise ValueError("ITS 실시간 응답에 prcn_dt가 없습니다.")

        hourly_df["prcn_dt"] = (
            hourly_df["prcn_dt"].astype("string").str.strip()
        )
        prcn_dt_values = hourly_df["prcn_dt"].dropna().unique()
        if len(prcn_dt_values) != 1:
            emit_traffic_diagnostic(
                "response_validation",
                outcome="reference_invalid",
                rows=len(hourly_df),
                reference_time_count=len(prcn_dt_values),
            )
            validation_logged = True
            raise ValueError(
                "ITS 실시간 응답 기준시각이 하나로 일치하지 않습니다."
            )

        actual_prcn_dt = str(prcn_dt_values[0])
        actual_stat_dt = actual_prcn_dt[:10]
        emit_traffic_diagnostic(
            "response_validation",
            outcome="success",
            rows=len(hourly_df),
            missing_required=False,
            reference_time_count=1,
        )
        validation_logged = True
        return {
            "available": True,
            "stat_dt": actual_stat_dt,
            "prcn_dt": actual_prcn_dt,
            "result": data.get("result"),
            "info_cnt": len(hourly_df),
            "data": hourly_df
        }
    except Exception as error:
        if not validation_logged:
            emit_traffic_diagnostic(
                "response_validation",
                outcome="response_invalid",
                rows=0,
            )
        raise
