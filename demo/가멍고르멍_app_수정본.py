import streamlit as st
import pandas as pd
import pydeck as pdk
from urllib.parse import urlencode
from traffic_diagnostics import (
    emit_traffic_diagnostic,
    fetch_hourly_traffic,
    read_its_api_key,
    traffic_error_category,
)

ITS_API_KEY, ITS_API_KEY_STATUS = read_its_api_key(st.secrets)
from datetime import datetime
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("Asia/Seoul"))

visit_date = now.strftime("%Y-%m-%d")
visit_time = now.strftime("%H:%M")

def judge_operating_time(open_time, close_time, visit_time):
    if pd.isna(open_time) or pd.isna(close_time):
        return "방문 전 확인 필요"

    open_time = str(open_time).strip()
    close_time = str(close_time).strip()

    if open_time == "00:00" and close_time == "00:00":
        return "방문 전 확인 필요"

    try:
        open_minutes = (
            int(open_time.split(":")[0]) * 60
            + int(open_time.split(":")[1])
        )
        close_minutes = (
            int(close_time.split(":")[0]) * 60
            + int(close_time.split(":")[1])
        )
        visit_minutes = (
            int(visit_time.split(":")[0]) * 60
            + int(visit_time.split(":")[1])
        )

    except (ValueError, IndexError):
        return "방문 전 확인 필요"

    if close_minutes > open_minutes:
        if open_minutes <= visit_minutes < close_minutes:
            return "운영 중"

        return "운영시간 외"

    if close_minutes < open_minutes:
        if visit_minutes >= open_minutes or visit_minutes < close_minutes:
            return "운영 중"

        return "운영시간 외"

    return "방문 전 확인 필요"

def get_operating_display_status(
    open_time,
    close_time,
    visit_time
):
    if pd.isna(open_time) or pd.isna(close_time):
        return {
            "status": "방문 전 확인 필요",
            "label": "⚠ 방문 전 확인 필요"
        }

    open_time = str(open_time).strip()
    close_time = str(close_time).strip()

    if open_time == "00:00" and close_time == "00:00":
        return {
            "status": "방문 전 확인 필요",
            "label": "⚠ 방문 전 확인 필요"
        }

    try:
        open_minutes = (
            int(open_time.split(":")[0]) * 60
            + int(open_time.split(":")[1])
        )

        close_minutes = (
            int(close_time.split(":")[0]) * 60
            + int(close_time.split(":")[1])
        )

        visit_minutes = (
            int(visit_time.split(":")[0]) * 60
            + int(visit_time.split(":")[1])
        )

    except (ValueError, IndexError):
        return {
            "status": "방문 전 확인 필요",
            "label": "⚠ 방문 전 확인 필요"
        }

    if close_minutes > open_minutes:
        is_open = (
            open_minutes
            <= visit_minutes
            < close_minutes
        )

        if is_open:
            minutes_until_close = (
                close_minutes - visit_minutes
            )

            if minutes_until_close <= 120:
                return {
                    "status": "마감 임박",
                    "label": f"운영 중 · {close_time}까지"
                }

            return {
                "status": "정상 운영",
                "label": f"운영 중 · {close_time}까지"
            }

        if visit_minutes < open_minutes:
            minutes_until_open = (
                open_minutes - visit_minutes
            )

            if minutes_until_open <= 60:
                return {
                    "status": "운영 시작 임박",
                    "label": f"{open_time} 운영 시작"
                }

        return {
            "status": "운영시간 외",
            "label": (
                f"운영시간 외 · "
                f"{open_time}–{close_time}"
            )
        }

    if close_minutes < open_minutes:
        is_open = (
            visit_minutes >= open_minutes
            or visit_minutes < close_minutes
        )

        if is_open:
            if visit_minutes < close_minutes:
                minutes_until_close = (
                    close_minutes - visit_minutes
                )
            else:
                minutes_until_close = (
                    1440 - visit_minutes
                    + close_minutes
                )

            if minutes_until_close <= 120:
                return {
                    "status": "마감 임박",
                    "label": f"운영 중 · {close_time}까지"
                }

            return {
                "status": "정상 운영",
                "label": f"운영 중 · {close_time}까지"
            }

        return {
            "status": "운영시간 외",
            "label": (
                f"운영시간 외 · "
                f"{open_time}–{close_time}"
            )
        }

    return {
        "status": "방문 전 확인 필요",
        "label": "⚠ 방문 전 확인 필요"
    }


def get_day_type(visit_date):
    visit_dt = datetime.strptime(
        visit_date,
        "%Y-%m-%d"
    )

    if visit_dt.weekday() >= 5:
        return "주말"

    return "평일"
    
import requests
import socket
import time


def diagnose_its_network():
    host = "api.jejuits.go.kr"
    port = 80
    url = "http://api.jejuits.go.kr/api/getFrafficInfo"

    result = {
        "dns": "미확인",
        "dns_detail": "",
        "tcp": "미확인",
        "tcp_detail": "",
        "http": "미확인",
        "http_detail": ""
    }

    # 1. DNS
    try:
        addresses = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM
        )

        resolved_ips = sorted(
            {
                item[4][0]
                for item in addresses
                if item[4]
            }
        )

        if resolved_ips:
            result["dns"] = "성공"
            result["dns_detail"] = ", ".join(
                resolved_ips
            )
        else:
            result["dns"] = "실패"
            result["dns_detail"] = "IP 주소를 찾지 못함"

    except Exception as error:
        result["dns"] = "실패"
        result["dns_detail"] = (
            f"{type(error).__name__}: {error}"
        )

    # 2. TCP
    if result["dns"] == "성공":
        try:
            start_time = time.perf_counter()

            with socket.create_connection(
                (host, port),
                timeout=10
            ):
                elapsed = (
                    time.perf_counter()
                    - start_time
                )

            result["tcp"] = "성공"
            result["tcp_detail"] = (
                f"{elapsed:.2f}초"
            )

        except Exception as error:
            result["tcp"] = "실패"
            result["tcp_detail"] = (
                f"{type(error).__name__}: {error}"
            )

    # 3. HTTP
    if result["tcp"] == "성공":
        try:
            start_time = time.perf_counter()

            response = requests.get(
                url,
                params={
                    "type": "L"
                },
                timeout=10
            )

            elapsed = (
                time.perf_counter()
                - start_time
            )

            result["http"] = (
                f"응답 {response.status_code}"
            )
            result["http_detail"] = (
                f"{elapsed:.2f}초"
            )

        except Exception as error:
            result["http"] = "실패"
            result["http_detail"] = (
                f"{type(error).__name__}: {error}"
            )

    return result

def fetch_latest_available_traffic(
    visit_date,
    visit_time,
    max_lookback_hours=4
):
    requested_dt = datetime.strptime(
        f"{visit_date} {visit_time}",
        "%Y-%m-%d %H:%M"
    )

    last_result = None

    for hours_back in range(max_lookback_hours + 1):
        target_dt = requested_dt - pd.Timedelta(
            hours=hours_back
        )

        target_date = target_dt.strftime("%Y-%m-%d")
        target_time = target_dt.strftime("%H:00")

        try:
            result = fetch_hourly_traffic(
                ITS_API_KEY,
                target_date,
                target_time
            )

        except requests.RequestException:
            continue

        last_result = result

        if result["available"]:
            result["requested_stat_dt"] = (
                requested_dt.strftime("%Y%m%d%H")
            )
            result["fallback_hours"] = hours_back

            return result

    return {
        "available": False,
        "stat_dt": (
            last_result["stat_dt"]
            if last_result is not None
            else requested_dt.strftime("%Y%m%d%H")
        ),
        "requested_stat_dt": requested_dt.strftime(
            "%Y%m%d%H"
        ),
        "fallback_hours": None,
        "result": (
            last_result["result"]
            if last_result is not None
            else None
        ),
        "info_cnt": 0,
        "data": pd.DataFrame()
    }

def save_latest_traffic_snapshot(
    traffic_result,
    snapshot_path
):
    if not traffic_result.get("available", False):
        return False

    snapshot_df = traffic_result.get("data")

    if (
        snapshot_df is None
        or snapshot_df.empty
    ):
        return False

    snapshot_to_save = snapshot_df.copy()

    snapshot_to_save["snapshot_stat_dt"] = (
        traffic_result.get("stat_dt")
    )

    snapshot_to_save["snapshot_saved_at"] = (
        datetime.now(ZoneInfo("Asia/Seoul")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    snapshot_to_save.to_csv(
        snapshot_path,
        index=False,
        encoding="utf-8-sig"
    )

    return True

def load_latest_traffic_snapshot(
    snapshot_path
):
    if not snapshot_path.exists():
        return {
            "available": False,
            "stat_dt": None,
            "saved_at": None,
            "data": pd.DataFrame()
        }

    try:
        snapshot_df = pd.read_csv(
            snapshot_path,
            encoding="utf-8-sig",
            dtype={"link_id": str}
        )

    except Exception:
        return {
            "available": False,
            "stat_dt": None,
            "saved_at": None,
            "data": pd.DataFrame()
        }

    if snapshot_df.empty:
        return {
            "available": False,
            "stat_dt": None,
            "saved_at": None,
            "data": pd.DataFrame()
        }

    if "snapshot_stat_dt" in snapshot_df.columns:
        stat_dt_values = (
            snapshot_df["snapshot_stat_dt"]
            .dropna()
            .astype(str)
        )

        if not stat_dt_values.empty:
            stat_dt = stat_dt_values.iloc[0]
        else:
            stat_dt = None
    else:
        stat_dt = None

    if "snapshot_saved_at" in snapshot_df.columns:
        saved_at_values = (
            snapshot_df["snapshot_saved_at"]
            .dropna()
            .astype(str)
        )

        if not saved_at_values.empty:
            saved_at = saved_at_values.iloc[0]
        else:
            saved_at = None
    else:
        saved_at = None

    return {
        "available": True,
        "stat_dt": stat_dt,
        "saved_at": saved_at,
        "data": snapshot_df
    }


def load_latest_traffic_heatmap(
    input_path
):
    if not input_path.exists():
        return {
            "available": False,
            "reference_dt": None,
            "reference_time": None,
            "data": pd.DataFrame()
        }

    try:
        heatmap_df = pd.read_csv(
            input_path,
            encoding="utf-8-sig",
            dtype={"LINK_ID": str}
        )

    except Exception:
        return {
            "available": False,
            "reference_dt": None,
            "reference_time": None,
            "data": pd.DataFrame()
        }

    if heatmap_df.empty:
        return {
            "available": False,
            "reference_dt": None,
            "reference_time": None,
            "data": pd.DataFrame()
        }

    required_columns = [
        "LINK_ID",
        "traffic_weight",
        "longitude",
        "latitude",
        "traffic_reference_dt",
        "traffic_reference_time"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in heatmap_df.columns
    ]

    if missing_columns:
        return {
            "available": False,
            "reference_dt": None,
            "reference_time": None,
            "data": pd.DataFrame()
        }

    reference_dt_values = (
        heatmap_df["traffic_reference_dt"]
        .dropna()
        .astype(str)
        .unique()
    )

    reference_time_values = (
        heatmap_df["traffic_reference_time"]
        .dropna()
        .astype(str)
        .unique()
    )

    if len(reference_dt_values) != 1:
        return {
            "available": False,
            "reference_dt": None,
            "reference_time": None,
            "data": pd.DataFrame()
        }

    reference_dt = reference_dt_values[0]

    reference_time = (
        reference_time_values[0]
        if len(reference_time_values) == 1
        else None
    )

    return {
        "available": True,
        "reference_dt": reference_dt,
        "reference_time": reference_time,
        "data": heatmap_df
    }

def load_traffic_baseline(
    baseline_path
):
    if not baseline_path.exists():
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    try:
        baseline_df = pd.read_csv(
            baseline_path,
            encoding="utf-8-sig",
            dtype={"LINK_ID": str}
        )

    except Exception:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    if baseline_df.empty:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    required_columns = [
        "LINK_ID",
        "weekday",
        "hour",
        "baseline_median_speed",
        "baseline_observation_count",
        "baseline_quality"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in baseline_df.columns
    ]

    if missing_columns:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    baseline_df["LINK_ID"] = (
        baseline_df["LINK_ID"]
        .astype("string")
        .str.strip()
    )

    baseline_df["weekday"] = pd.to_numeric(
        baseline_df["weekday"],
        errors="coerce"
    )

    baseline_df["hour"] = pd.to_numeric(
        baseline_df["hour"],
        errors="coerce"
    )

    baseline_df["baseline_median_speed"] = (
        pd.to_numeric(
            baseline_df["baseline_median_speed"],
            errors="coerce"
        )
    )

    baseline_df["baseline_observation_count"] = (
        pd.to_numeric(
            baseline_df["baseline_observation_count"],
            errors="coerce"
        )
    )

    return {
        "available": True,
        "data": baseline_df
    }

def load_traffic_link_coordinates(
    coordinate_path
):
    if not coordinate_path.exists():
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    try:
        coordinate_df = pd.read_csv(
            coordinate_path,
            encoding="utf-8-sig",
            dtype={"LINK_ID": str}
        )

    except Exception:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    if coordinate_df.empty:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    required_columns = [
        "LINK_ID",
        "longitude",
        "latitude"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in coordinate_df.columns
    ]

    if missing_columns:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    coordinate_df["LINK_ID"] = (
        coordinate_df["LINK_ID"]
        .astype("string")
        .str.strip()
    )

    coordinate_df["longitude"] = pd.to_numeric(
        coordinate_df["longitude"],
        errors="coerce"
    )

    coordinate_df["latitude"] = pd.to_numeric(
        coordinate_df["latitude"],
        errors="coerce"
    )

    coordinate_df = coordinate_df.dropna(
        subset=[
            "LINK_ID",
            "longitude",
            "latitude"
        ]
    ).copy()

    if coordinate_df.empty:
        return {
            "available": False,
            "data": pd.DataFrame()
        }

    return {
        "available": True,
        "data": coordinate_df
    }


def calculate_traffic_data_age_hours(
    stat_dt
):
    if stat_dt is None:
        return None

    try:
        traffic_dt = datetime.strptime(
            str(stat_dt),
            "%Y%m%d%H"
        ).replace(tzinfo=ZoneInfo("Asia/Seoul"))

    except (ValueError, TypeError):
        return None

    age_delta = datetime.now(ZoneInfo("Asia/Seoul")) - traffic_dt

    return max(
        0.0,
        age_delta.total_seconds() / 3600
    )

def classify_traffic_data_freshness(
    age_hours
):
    if age_hours is None:
        return "unavailable"

    if age_hours <= 2:
        return "recent"

    if age_hours <= 24:
        return "stale"

    return "expired"


def build_current_place_traffic(
    current_traffic,
    traffic_link_master
):
    if current_traffic.empty:
        return pd.DataFrame()

    traffic_links = traffic_link_master.copy()
    if "link_id" not in traffic_links.columns:
        if "LINK_ID" in traffic_links.columns:
            traffic_links["link_id"] = (
                traffic_links["LINK_ID"]
                .astype("string")
                .str.strip()
            )
        else:
            raise ValueError(
                "교통 링크 Master에 "
                "LINK_ID/link_id가 없습니다."
            )

    else:
        traffic_links["link_id"] = (
            traffic_links["link_id"]
            .astype("string")
            .str.strip()
        )

    current_links = current_traffic[
        [
            "link_id",
            "sped"
        ]
    ].copy()

    current_links["link_id"] = (
        current_links["link_id"]
        .astype("string")
        .str.strip()
    )

    merged_traffic = traffic_links.merge(
        current_links,
        on="link_id",
        how="inner"
    )

    if merged_traffic.empty:
        return pd.DataFrame()

    place_traffic = (
        merged_traffic
        .groupby(
            "related_place",
            as_index=False
        )
        .agg(
            current_median_speed=(
                "sped",
                "median"
            ),
            current_link_count=(
                "link_id",
                "nunique"
            )
        )
    )

    return place_traffic

def build_baseline_traffic_comparison(
    current_traffic,
    baseline_data,
    reference_dt
):
    if current_traffic.empty:
        return pd.DataFrame()

    if baseline_data.empty:
        return pd.DataFrame()

    current_df = current_traffic.copy()
    baseline_df = baseline_data.copy()

    if "LINK_ID" not in current_df.columns:
        if "link_id" in current_df.columns:
            current_df["LINK_ID"] = (
                current_df["link_id"]
                .astype("string")
                .str.strip()
            )
        else:
            raise ValueError(
                "현재 교통데이터에 "
                "LINK_ID/link_id가 없습니다."
            )

    current_df["LINK_ID"] = (
        current_df["LINK_ID"]
        .astype("string")
        .str.strip()
    )

    baseline_df["LINK_ID"] = (
        baseline_df["LINK_ID"]
        .astype("string")
        .str.strip()
    )

    current_df["sped"] = pd.to_numeric(
        current_df["sped"],
        errors="coerce"
    )

    current_df["weekday"] = (
        reference_dt.weekday()
    )

    current_df["hour"] = (
        reference_dt.hour
    )

    comparison = current_df.merge(
        baseline_df,
        on=[
            "LINK_ID",
            "weekday",
            "hour"
        ],
        how="left"
    )

    def calculate_row_weight(row):
        if (
            row.get("baseline_quality")
            != "sufficient"
        ):
            return None

        current_speed = row.get("sped")

        baseline_speed = row.get(
            "baseline_median_speed"
        )

        if (
            pd.isna(current_speed)
            or pd.isna(baseline_speed)
        ):
            return None

        baseline_speed = float(
            baseline_speed
        )

        if baseline_speed <= 0:
            return None

        speed_ratio = (
            float(current_speed)
            / baseline_speed
        )

        return max(
            0.0,
            min(
                1.0 - speed_ratio,
                1.0
            )
        )

    comparison["traffic_weight"] = (
        comparison.apply(
            calculate_row_weight,
            axis=1
        )
    )

    return comparison


def build_live_traffic_heatmap_data(
    current_traffic,
    baseline_data,
    coordinate_data,
    reference_dt
):
    if current_traffic.empty:
        emit_traffic_diagnostic(
            "heatmap_match", outcome="input_empty", output_rows=0
        )
        return pd.DataFrame()

    if baseline_data.empty:
        emit_traffic_diagnostic(
            "heatmap_match", outcome="input_empty", output_rows=0
        )
        return pd.DataFrame()

    if coordinate_data.empty:
        emit_traffic_diagnostic(
            "heatmap_match", outcome="input_empty", output_rows=0
        )
        return pd.DataFrame()

    comparison = (
        build_baseline_traffic_comparison(
            current_traffic=current_traffic,
            baseline_data=baseline_data,
            reference_dt=reference_dt
        )
    )

    if comparison.empty:
        emit_traffic_diagnostic(
            "heatmap_match",
            outcome="comparison_empty",
            comparison_rows=0,
            output_rows=0,
        )
        return pd.DataFrame()

    coordinates = coordinate_data.copy()

    coordinates["LINK_ID"] = (
        coordinates["LINK_ID"]
        .astype("string")
        .str.strip()
    )

    heatmap_data = comparison.merge(
        coordinates[
            [
                "LINK_ID",
                "longitude",
                "latitude"
            ]
        ],
        on="LINK_ID",
        how="left"
    )

    comparison_rows = len(comparison)
    coordinate_matched_rows = int(
        heatmap_data[["longitude", "latitude"]]
        .notna()
        .all(axis=1)
        .sum()
    )

    heatmap_data = heatmap_data.dropna(
        subset=[
            "longitude",
            "latitude",
            "traffic_weight"
        ]
    ).copy()

    if heatmap_data.empty:
        outcome = (
            "coordinates_unmatched"
            if coordinate_matched_rows == 0
            else "invalid_rows"
        )
        emit_traffic_diagnostic(
            "heatmap_match",
            outcome=outcome,
            comparison_rows=comparison_rows,
            coordinate_matched_rows=coordinate_matched_rows,
            valid_rows=0,
            output_rows=0,
        )
        return pd.DataFrame()

    emit_traffic_diagnostic(
        "heatmap_match",
        outcome="matched",
        comparison_rows=comparison_rows,
        coordinate_matched_rows=coordinate_matched_rows,
        valid_rows=len(heatmap_data),
        output_rows=len(heatmap_data),
    )

    heatmap_data["traffic_reference_dt"] = (
        reference_dt.strftime(
            "%Y%m%d%H"
        )
    )

    heatmap_data["traffic_reference_time"] = (
        reference_dt.strftime(
            "%Y-%m-%d %H:00"
        )
    )

    return heatmap_data

def save_latest_traffic_heatmap(
    heatmap_data,
    output_path
):
    if heatmap_data.empty:
        return False

    required_columns = [
        "LINK_ID",
        "sped",
        "baseline_median_speed",
        "baseline_quality",
        "traffic_weight",
        "longitude",
        "latitude",
        "traffic_reference_dt",
        "traffic_reference_time"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in heatmap_data.columns
    ]

    if missing_columns:
        return False

    heatmap_to_save = (
        heatmap_data[
            required_columns
        ]
        .copy()
    )

    heatmap_to_save.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig"
    )

    return True



st.markdown(
    """
    <style>
    div[data-testid="stLinkButton"] > a {
        background-color: rgba(234, 179, 8, 0.18) !important;
        border-color: rgba(234, 179, 8, 0.70) !important;
        color: #8A6700 !important;
    }

    div[data-testid="stLinkButton"] > a:hover {
        background-color: rgba(234, 179, 8, 0.28) !important;
        border-color: rgb(234, 179, 8) !important;
        color: #6F5200 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("가멍고르멍")

st.subheader(
    "상황에 맞는 다음 목적지를 비교하고 선택하세요"
)

st.write(
    "여행 중 계획한 목적지를 이용하기 어려운 상황이 발생하면, "
    "운영 상태와 이동거리, 제주 관광수요 정보를 비교해 "
    "다음 목적지를 선택할 수 있습니다."
)


core_places = [
    "서귀포매일올레시장",
    "제주국제공항",
    "동문재래시장",
    "성산일출봉",
    "함덕해수욕장",
    "협재해수욕장",
    "오설록티뮤지엄",
    "섭지코지",
    "주상절리대",
    "용머리해안"
]

search_place = st.text_input(
    "어디로 가시나요?",
    placeholder="제주 관광지를 검색하세요"
)

selected_place = None

if "selected_alternative" not in st.session_state:
    st.session_state.selected_alternative = None

if "previous_selected_place" not in st.session_state:
    st.session_state.previous_selected_place = None
    

if search_place:
    search_text = search_place.strip()

    matched_places = [
        place
        for place in core_places
        if search_text in place
    ]

    if len(matched_places) == 1:
        selected_place = matched_places[0]
        st.success(f"{selected_place}을(를) 선택했습니다.")

    elif len(matched_places) > 1:
        selected_place = st.selectbox(
            "검색 결과",
            matched_places
        )

    else:
        st.info(
            f"'{search_text}'은(는) 현재 준비 중인 목적지입니다.\n\n"
            "가멍고르멍 데모에서는 데이터 구축과 추천 검증을 완료한 "
            "제주 주요 목적지 10곳을 우선 체험할 수 있습니다."
        )

st.markdown(
    "검증 완료된 제주 관광지 10곳을 바로 체험해보세요."
)

demo_place = st.selectbox(
    "체험할 관광지 선택",
    ["선택하세요"] + core_places
)

st.caption(
    "목록에 없는 관광지도 검색할 수 있으며, "
    "현재 데모에서 검증되지 않은 장소는 '준비 중'으로 안내합니다."
)

if demo_place != "선택하세요":
    selected_place = demo_place
    st.success(f"{selected_place}을(를) 선택했습니다.")

if selected_place != st.session_state.previous_selected_place:
    st.session_state.selected_alternative = None
    st.session_state.previous_selected_place = selected_place

import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

TRAFFIC_CACHE_DIR = BASE_DIR / "03_traffic" / "cache"

LATEST_TRAFFIC_SNAPSHOT_PATH = (
    TRAFFIC_CACHE_DIR / "latest_traffic_snapshot.csv"
)

TRAFFIC_LINK_COORDINATE_PATH = (
    BASE_DIR
    / "03_traffic"
    / "09_traffic_link_coordinate_master.csv"
)

TRAFFIC_BASELINE_PATH = (
    BASE_DIR
    / "03_traffic"
    / "10_traffic_link_baseline.csv"
)

LATEST_TRAFFIC_HEATMAP_PATH = (
    TRAFFIC_CACHE_DIR
    / "latest_traffic_heatmap.csv"
)





TRAFFIC_CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

core_master = pd.read_csv(
    BASE_DIR / "01_processed" / "10_core_service_master.csv",
    encoding="utf-8-sig"
)

recommendation_master = pd.read_csv(
    BASE_DIR / "01_processed" / "09_recommendation_master.csv",
    encoding="utf-8-sig"
)

jeju_tourism_demand = pd.read_csv(
    BASE_DIR / "01_processed" / "11_jeju_tourism_demand_lookup.csv",
    encoding="utf-8-sig"
)

alternative_traffic_master = pd.read_csv(
    BASE_DIR / "03_traffic" / "06_alternative_traffic_master.csv",
    encoding="utf-8-sig"
)


traffic_link_master = pd.read_csv(
    BASE_DIR / "03_traffic" / "07_alternative_traffic_link_master.csv",
    encoding="utf-8-sig",
    dtype={"LINK_ID": str}
)

heatmap_snapshot = pd.read_csv(
    BASE_DIR / "03_traffic" / "08_heatmap_demo_snapshot.csv",
    encoding="utf-8-sig",
    dtype={"link_id": str}
)

traffic_baseline_result = (
    load_traffic_baseline(
        TRAFFIC_BASELINE_PATH
    )
)

traffic_baseline_available = (
    traffic_baseline_result["available"]
)

traffic_baseline_data = (
    traffic_baseline_result["data"]
)

traffic_coordinate_result = (
    load_traffic_link_coordinates(
        TRAFFIC_LINK_COORDINATE_PATH
    )
)

traffic_coordinate_available = (
    traffic_coordinate_result["available"]
)

traffic_link_coordinate_data = (
    traffic_coordinate_result["data"]
)

latest_heatmap_result = (
    load_latest_traffic_heatmap(
        LATEST_TRAFFIC_HEATMAP_PATH
    )
)



final_heatmap_available = (
    latest_heatmap_result["available"]
)

final_heatmap_age_hours = (
    calculate_traffic_data_age_hours(
        latest_heatmap_result["reference_dt"]
    )
)

final_heatmap_freshness = (
    classify_traffic_data_freshness(
        final_heatmap_age_hours
    )
)

if (
    final_heatmap_available
    and final_heatmap_freshness
    in ["recent", "stale"]
):
    active_heatmap_data = (
        latest_heatmap_result["data"]
        .copy()
    )

    active_heatmap_type = "baseline"
    active_heatmap_status = "baseline"

    active_heatmap_reference_time = (
        latest_heatmap_result[
            "reference_time"
        ]
    )

else:
    active_heatmap_data = (
        heatmap_snapshot.copy()
    )

    active_heatmap_type = "demo"

    if (
        final_heatmap_available
        and final_heatmap_freshness
        == "expired"
    ):
        active_heatmap_status = "demo_expired"

    else:
        active_heatmap_status = "demo_no_baseline"

    active_heatmap_reference_time = None

traffic_error_message = None

if not selected_place:
    emit_traffic_diagnostic(
        "request_skipped", reason="place_unselected"
    )
    emit_traffic_diagnostic(
        "fallback",
        active=(active_heatmap_type == "demo"),
        reason=(
            "place_unselected"
            if active_heatmap_type == "demo"
            else "none"
        ),
    )

if selected_place:
    initial_cached_traffic = (
        load_latest_traffic_snapshot(
            LATEST_TRAFFIC_SNAPSHOT_PATH
        )
    )

    initial_cache_age_hours = (
        calculate_traffic_data_age_hours(
            initial_cached_traffic["stat_dt"]
        )
    )

    initial_cache_freshness = (
        classify_traffic_data_freshness(
            initial_cache_age_hours
        )
    )

    initial_cache_is_usable = (
        initial_cached_traffic["available"]
        and initial_cache_freshness
        in ["recent", "stale"]
    )



    if initial_cache_is_usable:
        emit_traffic_diagnostic(
            "request_skipped", reason="fresh_cache"
        )
        current_traffic = initial_cached_traffic["data"]
        traffic_stat_dt = initial_cached_traffic["stat_dt"]
        traffic_data_source = "cache"

    else:
        try:
            print("TRAFFIC_DIAG_APP dns_probe_v1", flush=True)
            traffic_result = fetch_hourly_traffic(
                ITS_API_KEY,
                visit_date,
                visit_time
            )

            if traffic_result["available"]:
                save_latest_traffic_snapshot(
                    traffic_result,
                    LATEST_TRAFFIC_SNAPSHOT_PATH
                )

                current_traffic = traffic_result["data"]
                traffic_stat_dt = traffic_result["stat_dt"]
                traffic_data_source = "api"

            else:
                cached_traffic_result = (
                    load_latest_traffic_snapshot(
                        LATEST_TRAFFIC_SNAPSHOT_PATH
                    )
                )

                if cached_traffic_result["available"]:
                    current_traffic = (
                        cached_traffic_result["data"]
                    )
                    traffic_stat_dt = (
                        cached_traffic_result["stat_dt"]
                    )
                    traffic_data_source = "cache"

                else:
                    current_traffic = pd.DataFrame()
                    traffic_stat_dt = None
                    traffic_data_source = "unavailable"

        except Exception as traffic_error:
            traffic_error_message = str(traffic_error)

            cached_traffic_result = (
                load_latest_traffic_snapshot(
                    LATEST_TRAFFIC_SNAPSHOT_PATH
                )
            )

            cached_traffic_age_hours = (
                calculate_traffic_data_age_hours(
                    cached_traffic_result["stat_dt"]
                )
            )

            cached_traffic_freshness = (
                classify_traffic_data_freshness(
                    cached_traffic_age_hours
                )
            )

            cached_traffic_is_usable = (
                cached_traffic_result["available"]
                and cached_traffic_freshness
                in ["recent", "stale"]
            )

            if cached_traffic_is_usable:
                current_traffic = (
                    cached_traffic_result["data"]
                )
                traffic_stat_dt = (
                    cached_traffic_result["stat_dt"]
                )
                traffic_data_source = "cache"

            else:
                current_traffic = pd.DataFrame()
                traffic_stat_dt = None
                traffic_data_source = "unavailable"



    current_place_traffic = build_current_place_traffic(
        current_traffic,
        traffic_link_master
    )

    traffic_data_age_hours = (
        calculate_traffic_data_age_hours(
            traffic_stat_dt
        )
    )

    traffic_data_freshness = (
        classify_traffic_data_freshness(
            traffic_data_age_hours
        )
    )

    traffic_data_is_usable = (
        traffic_data_freshness
        in ["recent", "stale"]
    )

    emit_traffic_diagnostic(
        "traffic_inputs",
        traffic_usable=traffic_data_is_usable,
        baseline_available=traffic_baseline_available,
        baseline_rows=len(traffic_baseline_data),
        coordinate_available=traffic_coordinate_available,
        coordinate_rows=len(traffic_link_coordinate_data),
    )

    if not traffic_data_is_usable:
        current_traffic = pd.DataFrame()

        current_place_traffic = pd.DataFrame()

    live_heatmap_data = pd.DataFrame()
    live_heatmap_error = None

    if (
        traffic_data_is_usable
        and traffic_baseline_available
        and traffic_coordinate_available
    ):
        try:
            live_reference_dt = datetime.strptime(
                str(traffic_stat_dt),
                "%Y%m%d%H"
            )

            live_heatmap_data = (
                build_live_traffic_heatmap_data(
                    current_traffic=current_traffic,
                    baseline_data=traffic_baseline_data,
                    coordinate_data=traffic_link_coordinate_data,
                    reference_dt=live_reference_dt
                )
            )

        except Exception as heatmap_error:
            live_heatmap_error = str(heatmap_error)
            emit_traffic_diagnostic(
                "heatmap_match",
                outcome="empty",
                output_rows=0,
                error_category=traffic_error_category(heatmap_error),
            )
            live_heatmap_data = pd.DataFrame()

    live_heatmap_saved = False

    if not live_heatmap_data.empty:
        live_heatmap_saved = (
            save_latest_traffic_heatmap(
                heatmap_data=live_heatmap_data,
                output_path=LATEST_TRAFFIC_HEATMAP_PATH
            )
        )



    if not live_heatmap_data.empty:
        active_heatmap_data = (
            live_heatmap_data.copy()
        )

        active_heatmap_type = "baseline"
        active_heatmap_status = "baseline"

        active_heatmap_reference_time = (
            live_heatmap_data[
                "traffic_reference_time"
            ]
            .iloc[0]
        )

    if active_heatmap_type != "demo":
        fallback_reason = "none"
    elif not traffic_data_is_usable:
        fallback_reason = "traffic_unavailable"
    elif not traffic_baseline_available:
        fallback_reason = "baseline_unavailable"
    elif not traffic_coordinate_available:
        fallback_reason = "coordinates_unavailable"
    elif live_heatmap_error is not None:
        fallback_reason = "heatmap_error"
    else:
        fallback_reason = "heatmap_empty"

    emit_traffic_diagnostic(
        "fallback",
        active=(active_heatmap_type == "demo"),
        reason=fallback_reason,
    )



    selected_core = core_master[
        core_master["place_name_datalab"] == selected_place
    ].iloc[0]

    day_type = get_day_type(visit_date)

    if day_type == "평일":
        core_open_col = "weekday_open"
        core_close_col = "weekday_close"
    else:
        core_open_col = "weekend_open"
        core_close_col = "weekend_close"

    core_operating_display = get_operating_display_status(
        selected_core[core_open_col],
        selected_core[core_close_col],
        visit_time
    )

    core_operating_status = judge_operating_time(
        selected_core[core_open_col],
        selected_core[core_close_col],
        visit_time
    )

    st.subheader(selected_place)

    core_status = core_operating_display["status"]
    core_label = core_operating_display["label"]

    if core_status == "정상 운영":
        core_status_bg = "#E8F5E9"
        core_status_color = "#16803A"

    elif core_status == "마감 임박":
        core_status_bg = "#FFF3E0"
        core_status_color = "#E66A00"

    elif core_status == "운영 시작 임박":
        core_status_bg = "#E8F0FE"
        core_status_color = "#1769D2"

    elif core_status == "운영시간 외":
        core_status_bg = "#F1F3F5"
        core_status_color = "#62676D"

    else:
        core_status_bg = "#FFF8DC"
        core_status_color = "#8A6700"

    if core_status == "방문 전 확인 필요":
        google_core_place_url = (
            "https://www.google.com/maps/search/?"
            + urlencode(
                {
                    "api": "1",
                    "query": f"{selected_place} 제주"
                }
            )
        )

        st.link_button(
            core_label,
            google_core_place_url,
            width="stretch"
        )

    else:
        st.markdown(
            f"""
            <div style="
                background:{core_status_bg};
                color:{core_status_color};
                padding:12px 16px;
                border-radius:8px;
                font-weight:700;
                line-height:1.3;
                margin-bottom:20px;
            ">
                {core_label}
            </div>
            """,
            unsafe_allow_html=True
        )



    selected_alternatives = (
        recommendation_master[
            recommendation_master["core_place"] == selected_place
        ]
        .sort_values("related_rank")
        [
            [
                "related_place",
                "category_datalab",
                "straight_distance_km",
                "alternative_latitude",
                "alternative_longitude",
                "related_rank"
            ]
        ]
        .copy()
    )

    selected_alternatives = selected_alternatives.merge(
        alternative_traffic_master[
            [
                "related_place",
                "relative_traffic_status",
                "traffic_data_status",
                "traffic_data_time"
            ]
        ],
        on="related_place",
        how="left"
    )

    # 제주 관광수요 정보는 후보별 비교 정보로만 사용하며,
    # 운영상태·거리·관련순위 정렬에는 사용하지 않는다.
    selected_alternatives = selected_alternatives.merge(
        jeju_tourism_demand[
            [
                "related_place",
                "jeju_data_match_status",
                "data_period",
                "available_months",
                "data_completeness_pct",
                "tourist_arrival_monthly_avg",
                "jeju_data_note"
            ]
        ],
        on="related_place",
        how="left"
    )


    day_type = get_day_type(visit_date)

    if day_type == "평일":
        open_col = "weekday_open"
        close_col = "weekday_close"
    else:
        open_col = "weekend_open"
        close_col = "weekend_close"

    operating_info = recommendation_master[
        [
            "core_place",
            "related_place",
            open_col,
            close_col,
            "operating_data_status"
        ]
    ].copy()

    selected_alternatives = selected_alternatives.merge(
        operating_info[
            operating_info["core_place"] == selected_place
        ][
            [
                "related_place",
                open_col,
                close_col,
                "operating_data_status"
            ]
        ],
        on="related_place",
        how="left"
    )

    selected_alternatives["현재 운영상태"] = (
        selected_alternatives.apply(
            lambda row: judge_operating_time(
                row[open_col],
                row[close_col],
                visit_time
            ),
            axis=1
        )
    )

    selected_alternatives["운영상태 상세"] = (
        selected_alternatives.apply(
            lambda row: get_operating_display_status(
                row[open_col],
                row[close_col],
                visit_time
            ),
            axis=1
        )
    )

    selected_alternatives["운영상태 유형"] = (
        selected_alternatives["운영상태 상세"].apply(
            lambda value: value["status"]
        )
    )

    selected_alternatives["운영상태 표시"] = (
        selected_alternatives["운영상태 상세"].apply(
            lambda value: value["label"]
        )
    )

    selected_alternatives["UI 추천 상태"] = (
        selected_alternatives["운영상태 유형"].map(
            {
                "정상 운영": "운영 중",
                "마감 임박": "마감 임박",
                "운영 시작 임박": "운영 시작 임박",
                "운영시간 외": "운영시간 외",
                "방문 전 확인 필요": "방문 전 확인 필요"
            }
        )
    )

    operating_priority = {
        "정상 운영": 1,
        "마감 임박": 2,
        "운영 시작 임박": 3,
        "방문 전 확인 필요": 4,
        "운영시간 외": 5
    }

    traffic_priority = {
        "평소 범위 내": 1,
        "평소 범위보다 느림": 2
    }

    selected_alternatives["운영 우선순위"] = (
        selected_alternatives["운영상태 유형"]
        .map(operating_priority)
        .fillna(9)
    )

    selected_alternatives["교통 우선순위"] = (
        selected_alternatives["relative_traffic_status"]
        .map(traffic_priority)
        .fillna(3)
    )

    selected_alternatives["거리 우선순위"] = (
        selected_alternatives["straight_distance_km"]
        .fillna(float("inf"))
    )

    selected_alternatives = (
        selected_alternatives
        .sort_values(
            by=[
                "운영 우선순위",
                "거리 우선순위",
                "related_rank"
            ],
            ascending=[
                True,
                True,
                True
            ],
            na_position="last"
        )
        .reset_index(drop=True)
    )




    selected_alternatives["표시순위"] = (
        selected_alternatives.index + 1
    )

    def classify_candidate(row):
        if row["현재 운영상태"] == "운영 중":
            return "추천 가능"

        if (
            row["현재 운영상태"] == "방문 전 확인 필요"
            or row["operating_data_status"] != "확인 가능"
        ):
            return "조건부"

        return "추천 제외"

    selected_alternatives["추천 상태"] = (
        selected_alternatives.apply(
            classify_candidate,
            axis=1
        )
    )




    st.subheader("다음 목적지를 비교해보세요")

    st.caption(
        "운영 상태와 이동거리, 제주 관광수요 정보를 확인하고 "
        "다음 목적지를 선택해보세요."
    )

    st.caption(
        "[⚠ 방문 전 확인 필요]의 경우 클릭으로 상세 정보를 확인 할 수 있어요"
    )

    st.caption(
        "거리 : 선택한 목적지에서 대체 관광지까지의 직선거리"
    )

    for _, row in selected_alternatives.iterrows():
        rank = int(row["표시순위"])
        place_name = row["related_place"]
        distance = row["straight_distance_km"]
        operating_label = row["운영상태 표시"]
        operating_type = row["운영상태 유형"]

        if operating_type == "정상 운영":
            rank_color = "#16803A"

        elif operating_type == "마감 임박":
            rank_color = "#E66A00"

        elif operating_type == "운영 시작 임박":
            rank_color = "#1769D2"

        elif operating_type == "운영시간 외":
            rank_color = "#62676D"

        else:
            rank_color = "#B77900"

        if pd.isna(distance):
            distance_label = "거리 확인 필요"
        else:
            distance_label = f"{distance:.2f} km"

        if operating_type == "정상 운영":
            status_bg = "#E8F5E9"
            status_color = "#16803A"

        elif operating_type == "마감 임박":
            status_bg = "#FFF3E0"
            status_color = "#E66A00"

        elif operating_type == "운영 시작 임박":
            status_bg = "#E8F0FE"
            status_color = "#1769D2"

        elif operating_type == "운영시간 외":
            status_bg = "#F1F3F5"
            status_color = "#62676D"

        else:
            status_bg = "#FFF8DC"
            status_color = "#8A6700"

        with st.container(border=True):
            col_rank, col_place, col_status = st.columns(
                [0.45, 3.35, 2.20],
                vertical_alignment="center"
            )

            with col_rank:
                st.markdown(
                    f"""
                    <div style="
                        color:{rank_color};
                        font-size:1.05rem;
                        font-weight:800;
                        text-align:center;
                    ">
                        {rank}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with col_place:
                st.markdown(
                    f"**{place_name}**"
                )
                st.caption(
                    distance_label
                )

                tourism_match_status = row.get(
                    "jeju_data_match_status",
                    "unmatched"
                )

                tourism_avg = row.get(
                    "tourist_arrival_monthly_avg",
                    float("nan")
                )

                tourism_months = row.get(
                    "available_months",
                    0
                )

                if (
                    tourism_match_status in ["matched", "duplicate_resolved"]
                    and pd.notna(tourism_avg)
                ):
                    tourism_label = (
                        f"관광객 도착 규모 · 최근 12개월 월평균 "
                        f"{tourism_avg:,.0f}명"
                    )

                    if pd.notna(tourism_months) and int(tourism_months) < 12:
                        tourism_label += (
                            f" · {int(tourism_months)}개월 데이터 기준"
                        )

                    st.caption(tourism_label)

                else:
                    st.caption(
                        "관광객 도착 데이터 확인 불가"
                    )

            with col_status:
                if operating_type == "방문 전 확인 필요":
                    google_place_url = (
                        "https://www.google.com/maps/search/?"
                        + urlencode(
                            {
                                "api": "1",
                                "query": f"{place_name} 제주"
                            }
                        )
                    )

                    st.link_button(
                        "⚠ 방문 전 확인 필요",
                        google_place_url,
                        width="stretch"
                    )

                else:
                    st.markdown(
                        f"""
                        <div style="
                            background:{status_bg};
                            color:{status_color};
                            padding:6px 8px;
                            border-radius:7px;
                            text-align:center;
                            font-weight:700;
                            font-size:0.88rem;
                            line-height:1.2;
                        ">
                            {operating_label}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )


                has_map_location = (
                    pd.notna(row["alternative_latitude"])
                    and pd.notna(row["alternative_longitude"])
                )

                if has_map_location:
                    if st.button(
                        "지도에서 보기",
                        key=f"map_select_{selected_place}_{place_name}",
                        width="stretch"
                    ):
                        st.session_state.selected_alternative = (
                            place_name
                        )

                else:
                    st.button(
                        "지도 정보 없음",
                        key=f"map_unavailable_{selected_place}_{place_name}",
                        disabled=True,
                        width="stretch"
                    )


    status_map_data = selected_alternatives[
        [
            "related_place",
            "alternative_latitude",
            "alternative_longitude",
            "운영상태 유형",
            "운영상태 표시",
            "표시순위"
        ]
    ].copy()

    status_map_data = status_map_data.dropna(
        subset=[
            "alternative_latitude",
            "alternative_longitude"
        ]
    )

    status_map_data["map_place_name"] = (
        status_map_data["related_place"]
    )

    status_map_data["map_status_label"] = (
        status_map_data["운영상태 표시"]
    )

    status_map_data["map_place_type"] = (
        "대체 목적지"
    )

    status_map_data["map_rank_label"] = (
        status_map_data["표시순위"]
        .astype(int)
        .astype(str)
    )    

    def get_marker_color(status):
        if status == "정상 운영":
            return [34, 197, 94, 220]

        if status == "마감 임박":
            return [249, 115, 22, 220]

        if status == "운영 시작 임박":
            return [37, 99, 235, 220]

        if status == "운영시간 외":
            return [107, 114, 128, 220]

        return [234, 179, 8, 220]

    status_map_data["marker_color"] = (
        status_map_data["운영상태 유형"].apply(
            get_marker_color
        )
    )

    if not status_map_data.empty:
        core_map_data = pd.DataFrame(
            {
                "map_place_name": [
                    selected_place
                ],
                "map_status_label": [
                    core_label
                ],
                "map_place_type": [
                    "선택한 목적지"
                ],
                "map_fixed_label": [
                    "핵심 목적지"
                ],
                "latitude": [
                    float(selected_core["latitude"])
                ],
                "longitude": [
                    float(selected_core["longitude"])
                ]
            }
        )

        core_pin_base_layer = pdk.Layer(
            "ScatterplotLayer",
            data=core_map_data,
            get_position=[
                "longitude",
                "latitude"
            ],
            get_fill_color=[220, 38, 38, 255],
            get_line_color=[255, 255, 255, 255],
            get_radius=320,
            radius_min_pixels=16,
            radius_max_pixels=20,
            line_width_min_pixels=2,
            stroked=True,
            filled=True,
            pickable=True
        )

        core_pin_center_layer = pdk.Layer(
            "ScatterplotLayer",
            data=core_map_data,
            get_position=[
                "longitude",
                "latitude"
            ],
            get_fill_color=[255, 255, 255, 255],
            get_radius=110,
            radius_min_pixels=5,
            radius_max_pixels=7,
            stroked=False,
            filled=True,
            pickable=False
        )



        test_map_layer = pdk.Layer(
            "ScatterplotLayer",
            data=status_map_data,
            get_position=[
                "alternative_longitude",
                "alternative_latitude"
            ],
            get_fill_color="marker_color",
            get_line_color=[255, 255, 255, 255],
            get_radius=260,
            radius_min_pixels=14,
            radius_max_pixels=18,
            line_width_min_pixels=2,
            stroked=True,
            filled=True,
            pickable=True,
            auto_highlight=True
        )

        rank_text_layer = pdk.Layer(
            "TextLayer",
            data=status_map_data,
            get_position=[
                "alternative_longitude",
                "alternative_latitude"
            ],
            get_text="map_rank_label",
            get_size=16,
            get_color=[255, 255, 255, 255],
            get_text_anchor="'middle'",
            get_alignment_baseline="'center'",
            get_font_weight=800,
            billboard=True,
            pickable=False
        )


        selected_connection_layer = None
        selected_alternative_layer = None
        selected_distance_text = None
        selected_map_point = None


        if st.session_state.selected_alternative:
            selected_map_point = status_map_data[
                status_map_data["related_place"]
                == st.session_state.selected_alternative
            ].copy()

            selected_map_point["map_selected_label"] = (
                "선택 대체지"
            )

            if not selected_map_point.empty:
                selected_alternative_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=selected_map_point,
                    get_position=[
                        "alternative_longitude",
                        "alternative_latitude"
                    ],
                    get_fill_color=[255, 255, 255, 0],
                    get_line_color=[99, 102, 241, 255],
                    get_radius=360,
                    radius_min_pixels=19,
                    radius_max_pixels=23,
                    line_width_min_pixels=3,
                    stroked=True,
                    filled=True,
                    pickable=False
                )






            selected_alt_row = selected_alternatives[
                selected_alternatives["related_place"]
                == st.session_state.selected_alternative
            ].iloc[0]

            selected_distance = (
                selected_alt_row["straight_distance_km"]
            )

            if pd.isna(selected_distance):
                selected_distance_text = (
                    "직선거리 확인 필요"
                )
            else:
                selected_distance_text = (
                    f"직선거리 {selected_distance:.2f} km"
                )

            connection_data = pd.DataFrame(
                {
                    "source_lon": [
                        float(selected_core["longitude"])
                    ],
                    "source_lat": [
                        float(selected_core["latitude"])
                    ],
                    "target_lon": [
                        float(
                            selected_map_point[
                                "alternative_longitude"
                            ].iloc[0]
                        )
                    ],
                    "target_lat": [
                        float(
                            selected_map_point[
                                "alternative_latitude"
                            ].iloc[0]
                        )
                    ],
                    "distance_label": [
                        (
                            f"직선거리 "
                            f"{selected_alt_row['straight_distance_km']:.2f} km"
                        )
                    ]
                }
            )

            selected_connection_layer = pdk.Layer(
                "LineLayer",
                data=connection_data,
                get_source_position=[
                    "source_lon",
                    "source_lat"
                ],
                get_target_position=[
                    "target_lon",
                    "target_lat"
                ],
                get_color=[55, 65, 81, 190],
                get_width=4,
                width_min_pixels=2,
                pickable=True
            )


        initial_view_candidates = (
            status_map_data
            .sort_values(
                "표시순위"
            )
            .head(3)
            .copy()
        )

        all_map_latitudes = (
            initial_view_candidates[
                "alternative_latitude"
            ].tolist()
            + core_map_data["latitude"].tolist()
        )

        all_map_longitudes = (
            initial_view_candidates[
                "alternative_longitude"
            ].tolist()
            + core_map_data["longitude"].tolist()
        )

        latitude_span = (
            max(all_map_latitudes)
            - min(all_map_latitudes)
        )

        longitude_span = (
            max(all_map_longitudes)
            - min(all_map_longitudes)
        )

        max_span = max(
            latitude_span,
            longitude_span
        )

        if max_span < 0.03:
            map_zoom = 12
        elif max_span < 0.07:
            map_zoom = 11
        elif max_span < 0.15:
            map_zoom = 10
        elif max_span < 0.30:
            map_zoom = 9
        else:
            map_zoom = 8

        if (
            st.session_state.selected_alternative
            and selected_map_point is not None
            and not selected_map_point.empty
        ):
            selected_core_lat = float(
                selected_core["latitude"]
            )

            selected_core_lon = float(
                selected_core["longitude"]
            )

            selected_alt_lat = float(
                selected_map_point[
                    "alternative_latitude"
                ].iloc[0]
            )

            selected_alt_lon = float(
                selected_map_point[
                    "alternative_longitude"
                ].iloc[0]
            )

            selected_lat_span = abs(
                selected_core_lat
                - selected_alt_lat
            )

            selected_lon_span = abs(
                selected_core_lon
                - selected_alt_lon
            )

            selected_max_span = max(
                selected_lat_span,
                selected_lon_span
            )

            if selected_max_span < 0.03:
                selected_map_zoom = 12
            elif selected_max_span < 0.07:
                selected_map_zoom = 11
            elif selected_max_span < 0.15:
                selected_map_zoom = 10
            elif selected_max_span < 0.30:
                selected_map_zoom = 9
            else:
                selected_map_zoom = 8

            selected_map_zoom = (
                selected_map_zoom + 1
            )

            test_map_view = pdk.ViewState(
                latitude=(
                    selected_core_lat
                    + selected_alt_lat
                ) / 2,
                longitude=(
                    selected_core_lon
                    + selected_alt_lon
                ) / 2,
                zoom=selected_map_zoom
            )

        else:
            test_map_view = pdk.ViewState(
                latitude=(
                    min(all_map_latitudes)
                    + max(all_map_latitudes)
                ) / 2,
                longitude=(
                    min(all_map_longitudes)
                    + max(all_map_longitudes)
                ) / 2,
                zoom=map_zoom
            )

        heatmap_lat_min = (
            min(all_map_latitudes) - 0.03
        )

        heatmap_lat_max = (
            max(all_map_latitudes) + 0.03
        )

        heatmap_lon_min = (
            min(all_map_longitudes) - 0.03
        )

        heatmap_lon_max = (
            max(all_map_longitudes) + 0.03
        )

        visible_heatmap_data = active_heatmap_data[
            (
                active_heatmap_data["latitude"]
                >= heatmap_lat_min
            )
            & (
                active_heatmap_data["latitude"]
                <= heatmap_lat_max
            )
            & (
                active_heatmap_data["longitude"]
                >= heatmap_lon_min
            )
            & (
                active_heatmap_data["longitude"]
                <= heatmap_lon_max
            )
        ].copy()

        visible_heatmap_data = (
            visible_heatmap_data[
                visible_heatmap_data["traffic_weight"] > 0
            ]
            .copy()
        )

        traffic_heatmap_layer = pdk.Layer(
            "HeatmapLayer",
            data=visible_heatmap_data,
            get_position=[
                "longitude",
                "latitude"
            ],
            get_weight="traffic_weight",
            radius_pixels=45,
            intensity=1,
            threshold=0.05
        )

        if (
            st.session_state.selected_alternative
            and selected_distance_text
        ):
            st.markdown(
                f"**📍 {selected_place} → "
                f"{st.session_state.selected_alternative} "
                f"{selected_distance_text}**"
            )

            st.caption(
                "실제 도로 이동거리와 다를 수 있습니다."
            )

            if (
                selected_map_point is not None
                and not selected_map_point.empty
                and pd.notna(selected_core["latitude"])
                and pd.notna(selected_core["longitude"])
                and pd.notna(
                    selected_map_point[
                        "alternative_latitude"
                    ].iloc[0]
                )
                and pd.notna(
                    selected_map_point[
                        "alternative_longitude"
                    ].iloc[0]
                )
            ):
                google_route_url = (
                    "https://www.google.com/maps/dir/?"
                    + urlencode(
                        {
                            "api": "1",
                            "origin": (
                                f"{float(selected_core['latitude'])},"
                                f"{float(selected_core['longitude'])}"
                            ),
                            "destination": (
                                f"{float(selected_map_point['alternative_latitude'].iloc[0])},"
                                f"{float(selected_map_point['alternative_longitude'].iloc[0])}"
                            )
                        }
                    )
                )


        if active_heatmap_status == "baseline":
            if active_heatmap_reference_time:
                st.caption(
                    "교통 혼잡 분포 : "
                    "평소 같은 요일·시간대 대비 "
                    "소통이 저하된 영역 · "
                    f"교통정보 기준 {active_heatmap_reference_time}"
                )

            else:
                st.caption(
                    "교통 혼잡 분포 : "
                    "평소 같은 요일·시간대 대비 "
                    "소통이 저하된 영역"
                )

        elif active_heatmap_status == "demo_expired":
            st.caption(
                "현재 교통정보를 확인할 수 없어 "
                "개발용 교통 분포를 표시합니다. "
                "색이 강할수록 제한속도 대비 "
                "주행속도가 낮은 영역입니다."
            )

        else:
            st.caption(
                "교통 혼잡 분포 : "
                "색이 강할수록 제한속도 대비 "
                "주행속도가 낮은 영역"
            )

        st.caption(
            "지도 마커 색상 : "
            "🟢 방문 적합  |  "
            "🟠 마감 임박  |  "
            "🔵 곧 운영 시작  |  "
            "회색: 운영시간 외  |  "
            "🟡 확인 필요"
        )

        st.pydeck_chart(
            pdk.Deck(
                map_style="light",
                initial_view_state=test_map_view,
                layers=[
                    traffic_heatmap_layer,
                    *(
                        [selected_connection_layer]
                        if selected_connection_layer
                        is not None
                        else []
                    ),
                    test_map_layer,
                    rank_text_layer,
                    *(
                        [selected_alternative_layer]
                        if selected_alternative_layer
                        is not None
                        else []
                    ),
                    core_pin_base_layer,
                    core_pin_center_layer
                ],
                tooltip={
                    "html": (
                        "<b>{map_place_name}</b><br/>"
                        "{map_place_type}<br/>"
                        "{map_status_label}"
                    )
                }
            ),
            width="stretch"
        )

        if (
            st.session_state.selected_alternative
            and selected_map_point is not None
            and not selected_map_point.empty
            and pd.notna(selected_core["latitude"])
            and pd.notna(selected_core["longitude"])
            and pd.notna(
                selected_map_point[
                    "alternative_latitude"
                ].iloc[0]
            )
            and pd.notna(
                selected_map_point[
                    "alternative_longitude"
                ].iloc[0]
            )
        ):
            st.link_button(
                "Google 지도에서 경로 확인",
                google_route_url,
                width="stretch"
            )

if not selected_place:
    map_data = core_master[
        [
            "place_name_datalab",
            "latitude",
            "longitude"
        ]
    ].copy()

    st.map(
        map_data,
        latitude="latitude",
        longitude="longitude",
        zoom=9
    )
