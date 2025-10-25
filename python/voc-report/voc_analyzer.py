"""Core script for fetching and analysing LMS VOC data.

Step 1 focuses on fetching rows from Google Sheets so that we can
confirm OAuth and column mappings before wiring the rest of the pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

# Read-only scope is enough for our analytics use-case.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = ROOT_DIR / ".env"
DEFAULT_CREDENTIALS_PATH = ROOT_DIR / "credentials.json"
DEFAULT_TOKEN_PATH = ROOT_DIR / "token.json"
DEFAULT_REPORT_PATH = ROOT_DIR / "voc_report.json"


def load_environment() -> None:
    """Loads environment variables from .env if present."""
    if DEFAULT_ENV_PATH.exists():
        load_dotenv(DEFAULT_ENV_PATH, override=False)
    else:
        load_dotenv(override=False)


def get_credentials(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
) -> Credentials:
    """Fetches (or refreshes) OAuth credentials for Google Sheets API."""
    creds: Optional[Credentials] = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Missing credentials file: {credentials_path}. "
                    "Download it from Google Cloud Console and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            # Opens a browser for the first-time login flow; token will be cached.
            creds = flow.run_local_server(port=0)

        # Cache the refreshed/new credentials for next time.
        token_path.write_text(creds.to_json())

    return creds


def fetch_raw_data(limit: Optional[int] = None) -> pd.DataFrame:
    """Fetches raw VOC rows from Google Sheets into a DataFrame."""
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    range_name = os.environ.get("GOOGLE_SHEETS_RANGE", "raw data!K:S")

    if not spreadsheet_id:
        raise ValueError(
            "GOOGLE_SHEETS_SPREADSHEET_ID is not set. "
            "Define it in .env or your shell environment."
        )

    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)

    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )

    values = response.get("values", [])
    if not values:
        return pd.DataFrame()

    header, *rows = values
    df = pd.DataFrame(rows, columns=header)
    df = standardise_columns(df)

    if limit is not None:
        df = df.head(limit)

    return df


def print_sample_rows(limit: int) -> None:
    """Fetches a small sample and prints it for manual inspection."""
    df = fetch_raw_data(limit=limit)
    if df.empty:
        print("No data returned from Google Sheets (check range or sheet).")
        return

    # Keep the output compact for console viewing.
    print(df.to_markdown(index=False))


def standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renames columns to a canonical schema and parses dates."""
    column_map = {
        "문의일자": "created_at",
        "created_at": "created_at",
        "createdat": "created_at",
        "createdAt": "created_at",
        "문의내용": "content",
        "content": "content",
        "대분류": "category",
        "소분류": "subcategory",
    }

    df = df.rename(columns={src: dst for src, dst in column_map.items() if src in df})

    if "created_at" in df.columns:
        df["created_at_raw"] = df["created_at"]
        df["created_at"] = df["created_at"].apply(parse_created_at)

    df = assign_content_text(df)

    return df


def is_json_object(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    try:
        json.loads(text)
        return True
    except Exception:
        return False


def assign_content_text(df: pd.DataFrame) -> pd.DataFrame:
    """Creates a content_text column prioritising sanitized inquiry text."""
    if df.empty:
        df["content_text"] = ""
        return df

    candidate_columns: List[str] = []
    for col in df.columns:
        name = str(col)
        lower = name.lower()
        if "문의" in name and "내용" in name:
            candidate_columns.append(col)
        elif lower in {"desc", "description"}:
            candidate_columns.append(col)

    candidate_columns = list(dict.fromkeys(candidate_columns))

    content_series: List[str] = []
    for idx, row in df.iterrows():
        chosen: Optional[str] = None

        for col in candidate_columns:
            value = row.get(col)
            if value is None or pd.isna(value):
                continue
            text = str(value).strip()
            if not text:
                continue
            if is_json_object(text):
                continue
            chosen = text
            break

        if chosen is None:
            raw = row.get("content")
            if isinstance(raw, str) and is_json_object(raw):
                try:
                    parsed = json.loads(raw)
                    desc = parsed.get("desc") or parsed.get("description")
                    if desc:
                        chosen = str(desc).strip()
                except Exception:
                    chosen = None

        if chosen is None:
            fallback = row.get("content")
            if fallback is not None and not pd.isna(fallback):
                chosen = str(fallback).strip()

        content_series.append(chosen or "")

    df["content_text"] = pd.Series(content_series, index=df.index)
    return df


def compute_recent_windows_kst(
    df: pd.DataFrame, reference: Optional[pd.Timestamp] = None
) -> Dict[str, pd.DataFrame]:
    """Filters dataframe into recent time windows using Asia/Seoul local dates."""
    empty = df.iloc[0:0]
    if "created_at" not in df.columns:
        return {"full": df, "recent_30d": empty, "recent_90d": empty, "prev_30d": empty}

    created = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    if created.isna().all():
        return {"full": df, "recent_30d": empty, "recent_90d": empty, "prev_30d": empty}

    created_kst = created.dt.tz_convert("Asia/Seoul")
    created_kst_day = created_kst.dt.normalize()

    if reference is not None:
        ref_kst = reference.tz_convert("Asia/Seoul")
    else:
        ref_kst = pd.Timestamp.now(tz="Asia/Seoul")

    today0 = ref_kst.normalize()
    tomorrow0 = today0 + pd.Timedelta(days=1)

    start30 = today0 - pd.Timedelta(days=29)
    prev_start30 = start30 - pd.Timedelta(days=30)
    prev_end30 = start30
    start90 = today0 - pd.Timedelta(days=89)

    mask_valid = created_kst_day.notna()
    mask_future = created_kst_day < tomorrow0

    mask_recent_30 = mask_valid & mask_future & (created_kst_day >= start30)
    mask_prev_30 = mask_valid & (created_kst_day >= prev_start30) & (created_kst_day < prev_end30)
    mask_recent_90 = mask_valid & mask_future & (created_kst_day >= start90)

    recent_30 = df[mask_recent_30]
    prev_30 = df[mask_prev_30]
    recent_90 = df[mask_recent_90]

    return {
        "full": df,
        "recent_30d": recent_30,
        "prev_30d": prev_30,
        "recent_90d": recent_90,
    }


def top_categories(df: pd.DataFrame, limit: int = 5) -> List[Tuple[str, int]]:
    """Returns top categories by count."""
    if "category" not in df or df.empty:
        return []

    counts = df["category"].fillna("미분류").value_counts().head(limit)
    return list(counts.items())


def month_over_month_change(df: pd.DataFrame) -> Dict[str, float]:
    """Calculates month-over-month percentage change for categories."""
    if "created_at" not in df or "category" not in df:
        return {}

    df = df.dropna(subset=["created_at"]).copy()
    if df.empty:
        return {}

    created_utc = df["created_at"].dt.tz_convert("UTC")
    created_naive = created_utc.dt.tz_localize(None)

    latest_month_start = created_naive.max().to_period("M").to_timestamp()
    prev_month_start = latest_month_start - pd.DateOffset(months=1)
    latest_month_end = latest_month_start + pd.offsets.MonthEnd(0)
    prev_month_end = prev_month_start + pd.offsets.MonthEnd(0)

    this_month = df[
        created_naive.between(latest_month_start, latest_month_end)
    ]
    prev_month = df[
        created_naive.between(prev_month_start, prev_month_end)
    ]

    if this_month.empty and prev_month.empty:
        return {}

    this_counts = this_month["category"].value_counts()
    prev_counts = prev_month["category"].value_counts()

    categories = set(this_counts.index).union(prev_counts.index)
    changes: Dict[str, float] = {}
    for category in categories:
        current = this_counts.get(category, 0)
        previous = prev_counts.get(category, 0)
        if previous == 0:
            changes[category] = float("inf") if current > 0 else 0.0
        else:
            changes[category] = (current - previous) / previous * 100

    return changes


def summarise_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Builds a dictionary with core stats for recent windows."""
    windows = compute_recent_windows_kst(df)
    date_info = extract_date_info(df)

    summary = {
        "total_count": len(df),
        "recent_30d_count": len(windows["recent_30d"]),
        "recent_90d_count": len(windows["recent_90d"]),
        "prev_30d_count": len(windows["prev_30d"]),
        "top_categories_30d": top_categories(windows["recent_30d"]),
        "top_categories_90d": top_categories(windows["recent_90d"]),
        "top_categories_prev_30d": top_categories(windows["prev_30d"]),
        "mom_change": month_over_month_change(df),
        "created_at_min": date_info["min"],
        "created_at_max": date_info["max"],
        "created_at_invalid_rows": date_info["invalid_count"],
    }
    return summary


def parse_created_at(value) -> Optional[pd.Timestamp]:
    """Parses various created_at formats into UTC timestamps."""
    if value is None or value == "":
        return pd.NaT

    if isinstance(value, (int, float)):
        # Treat numeric values as Excel serials (days since 1899-12-30).
        try:
            return pd.to_datetime(value, unit="d", origin="1899-12-30", utc=True)
        except Exception:
            return pd.NaT

    text = str(value).strip()
    if not text:
        return pd.NaT

    # Normalize Korean AM/PM markers and dot-separated date parts.
    text = text.replace("오전", "AM").replace("오후", "PM")
    text = re.sub(r"\.\s*", "-", text)
    text = re.sub(r"\s+", " ", text)

    seoul_tz = ZoneInfo("Asia/Seoul")
    formats = [
        "%Y-%m-%d %p %I:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt.endswith("%p %I:%M:%S") or fmt.endswith("%H:%M:%S"):
                dt = dt.replace(tzinfo=seoul_tz)
            else:
                dt = datetime.combine(dt.date(), datetime.min.time(), tzinfo=seoul_tz)
            return pd.Timestamp(dt.astimezone(timezone.utc))
        except ValueError:
            continue

    return pd.to_datetime(text, errors="coerce", utc=True)


def extract_date_info(df: pd.DataFrame) -> Dict[str, object]:
    """Returns min/max/invalid counts for created_at column."""
    if "created_at" not in df:
        return {"min": None, "max": None, "invalid_count": len(df)}

    series = df["created_at"]
    valid = series.dropna()
    return {
        "min": valid.min(),
        "max": valid.max(),
        "invalid_count": len(series) - len(valid),
    }


def map_category_to_phase(category: Optional[str]) -> str:
    """Maps a category string into a learning phase bucket."""
    if not category:
        return "기타"

    category = category.strip().lower()
    phase_rules = [
        ("장비", "준비"),
        ("기기", "준비"),
        ("환경", "준비"),
        ("수업", "진행"),
        ("커리큘럼", "진행"),
        ("멘토", "진행"),
        ("지원", "지원"),
        ("장려금", "행정"),
        ("행정", "행정"),
        ("출석", "행정"),
    ]
    for keyword, phase in phase_rules:
        if keyword in category:
            return phase
    return "기타"


def aggregate_phase_counts(df: pd.DataFrame) -> Dict[str, int]:
    """Counts VOCs per learning phase."""
    if df.empty:
        return {}
    phases = df.get("category", pd.Series(dtype=str)).apply(map_category_to_phase)
    return phases.value_counts().to_dict()


def compose_issue_keys(df: pd.DataFrame) -> pd.Series:
    """Builds issue keys based on category/subcategory columns."""
    if df.empty:
        return pd.Series(dtype=str)

    categories = df.get("category", pd.Series(index=df.index, dtype=str)).fillna("")
    subcategories = df.get(
        "subcategory", pd.Series(index=df.index, dtype=str)
    ).fillna("")

    categories = categories.astype(str).str.strip()
    subcategories = subcategories.astype(str).str.strip()

    issue_keys = categories.copy()
    mask_sub = subcategories != ""
    issue_keys.loc[mask_sub] = (
        categories.loc[mask_sub] + " > " + subcategories.loc[mask_sub]
    )

    return issue_keys.where(issue_keys != "", "미분류")


def compute_issue_counts(df: pd.DataFrame) -> Dict[str, int]:
    """Counts occurrences per issue key."""
    issue_keys = compose_issue_keys(df)
    if issue_keys.empty:
        return {}
    counts = issue_keys.value_counts()
    return counts.to_dict()


def change_percentage(current: int, previous: int) -> float:
    """Mimics Apps Script changePct calculation."""
    if previous == 0 and current > 0:
        return 100.0
    if previous == 0 and current == 0:
        return 0.0
    return ((current - previous) / max(1, previous)) * 100.0


def summarize_top_issues(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    limit: int = 5,
    quotes_per_issue: int = 2,
) -> List[Dict[str, Any]]:
    """Returns top issues with counts and change percentage, mirroring Apps Script."""
    current_counts = compute_issue_counts(current_df)
    previous_counts = compute_issue_counts(previous_df)

    issue_quotes: Dict[str, List[str]] = {}
    if not current_df.empty:
        issue_keys = compose_issue_keys(current_df)
        content_series = current_df.get(
            "content_text", pd.Series(index=current_df.index, dtype=str)
        )
        for idx, issue_key in issue_keys.items():
            if not isinstance(issue_key, str):
                continue
            text_value = ""
            if content_series is not None and idx in content_series.index:
                text_value = str(content_series.loc[idx])
            if not text_value and "content" in current_df.columns:
                text_value = str(current_df.loc[idx].get("content", "") or "")
            text_value = text_value.strip().replace("\n", " ")
            if not text_value:
                continue
            if issue_key not in issue_quotes:
                issue_quotes[issue_key] = []
            if len(issue_quotes[issue_key]) >= quotes_per_issue:
                continue
            if len(text_value) > 120:
                text_value = text_value[:117] + "..."
            issue_quotes[issue_key].append(f'예: "{text_value}"')

    rows = []
    for issue_key, count in current_counts.items():
        previous = previous_counts.get(issue_key, 0)
        change = round(change_percentage(int(count), int(previous)), 1)
        rows.append(
            {
                "issue_key": issue_key,
                "count": int(count),
                "previous_count": int(previous),
                "change_pct": change,
                "summary": build_issue_summary(issue_key, change),
                "quotes": issue_quotes.get(issue_key, []),
            }
        )

    rows.sort(key=lambda item: item["count"], reverse=True)
    return rows[:limit]


def build_issue_summary(issue_key: str, change_pct: float) -> str:
    """Generates a one-line summary similar to Apps Script."""
    sign = "+" if change_pct >= 0 else ""
    rounded = int(round(change_pct))
    return f"{issue_key} 전월 대비 {sign}{rounded}%"


def determine_phase_from_row(row: pd.Series) -> str:
    """Assigns a phase using category, subcategory, and content heuristics."""
    text = " ".join(
        str(row.get(col, "") or "")
        for col in ("category", "subcategory", "content_text", "content")
    ).lower()

    patterns = [
        (r"(장비|노트북|맥북|사양|대여|반납|주변기기|모니터|마우스|키보드)", "학습 준비"),
        (r"(플랫폼|실습|콘솔|빌드|로그인|접속|출결|qr|오류|강의실)", "학습 진행"),
        (r"(장려금|지원금|지급|자격|증빙|정산)", "학습 지원"),
        (r"(수강 변경|휴가|공가|행정|신청|증명서|환불|이관|출석)", "행정 처리"),
    ]

    for pattern, phase in patterns:
        if re.search(pattern, text):
            return phase

    return "학습 진행"


def aggregate_phase_breakdown(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    quotes_per_issue: int = 2,
    top_per_phase: int = 6,
) -> Dict[str, Dict[str, Any]]:
    """Builds phase-specific breakdown similar to Apps Script."""
    if current_df.empty:
        return {}

    current_phase = current_df.apply(determine_phase_from_row, axis=1)
    prev_phase = (
        previous_df.apply(determine_phase_from_row, axis=1)
        if not previous_df.empty
        else pd.Series(index=previous_df.index, dtype=str)
    )

    current_issues = compose_issue_keys(current_df)
    prev_issues = compose_issue_keys(previous_df) if not previous_df.empty else None
    current_texts = current_df.get(
        "content_text", pd.Series(index=current_df.index, dtype=str)
    )

    phase_data: Dict[str, Dict[str, Any]] = {}

    for idx, phase in current_phase.items():
        issue_key = current_issues.get(idx, "미분류")
        phase_bucket = phase_data.setdefault(
            phase,
            {"total": 0, "issues": {}, "quotes": {}},
        )
        phase_bucket["total"] += 1
        phase_bucket["issues"][issue_key] = phase_bucket["issues"].get(issue_key, 0) + 1

        if issue_key not in phase_bucket["quotes"]:
            phase_bucket["quotes"][issue_key] = []
        if len(phase_bucket["quotes"][issue_key]) < quotes_per_issue:
            text_val = ""
            if current_texts is not None and idx in current_texts.index:
                text_val = str(current_texts.loc[idx] or "")
            if not text_val:
                text_val = str(current_df.loc[idx].get("content", "") or "")
            text_val = text_val.strip().replace("\n", " ")
            if text_val:
                if len(text_val) > 120:
                    text_val = text_val[:117] + "..."
                phase_bucket["quotes"][issue_key].append(f'예: "{text_val}"')

    prev_counts: Dict[str, Dict[str, int]] = {}
    if prev_issues is not None:
        for idx, phase in prev_phase.items():
            issue_key = prev_issues.get(idx, "미분류")
            prev_phase_bucket = prev_counts.setdefault(phase, {})
            prev_phase_bucket[issue_key] = prev_phase_bucket.get(issue_key, 0) + 1

    result: Dict[str, Dict[str, Any]] = {}
    for phase, info in phase_data.items():
        issues_list = []
        for issue_key, count in info["issues"].items():
            previous = prev_counts.get(phase, {}).get(issue_key, 0)
            change = round(change_percentage(count, previous), 1)
            issues_list.append(
                {
                    "issue_key": issue_key,
                    "count": count,
                    "previous_count": previous,
                    "change_pct": change,
                    "summary": build_issue_summary(issue_key, change),
                    "quotes": info["quotes"].get(issue_key, []),
                }
            )

        issues_list.sort(key=lambda item: item["count"], reverse=True)
        result[phase] = {
            "total": info["total"],
            "issues": issues_list[:top_per_phase],
        }

    return result


def build_trend_cards(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Builds trend info combining month-over-month change with color cues."""
    changes = month_over_month_change(df)
    trends = []
    for category, delta in changes.items():
        if delta == float("inf"):
            status = "increase"
            emoji = "🔴"
        elif delta >= 20:
            status = "increase"
            emoji = "🔴"
        elif delta >= 5:
            status = "moderate"
            emoji = "🟡"
        else:
            status = "stable"
            emoji = "🟢"
        trends.append(
            {
                "category": category,
                "change_pct": None if delta == float("inf") else round(delta, 1),
                "status": status,
                "emoji": emoji,
            }
        )
    return trends


def extract_quotes(df: pd.DataFrame, limit: int = 2) -> List[str]:
    """Grabs representative learner quotes from content column."""
    if df.empty:
        return []

    content_series = df.get("content_text")
    if content_series is None or content_series.dropna().empty:
        content_series = df.get("content")
    if content_series is None or content_series.dropna().empty:
        return []

    quotes = []
    for value in content_series.dropna().head(limit):
        text = str(value).strip().replace("\n", " ")
        if len(text) > 180:
            text = text[:177] + "..."
        quotes.append(text)
    return quotes


def build_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Creates a structured JSON-ready report payload."""
    now_kst = pd.Timestamp.now(tz="Asia/Seoul")
    windows = compute_recent_windows_kst(df, reference=now_kst)
    stats = summarise_stats(df)

    recent_30 = windows["recent_30d"]
    prev_30 = windows["prev_30d"]
    top_issues = summarize_top_issues(recent_30, prev_30, limit=5)
    top_issue_rows = []
    for rank, item in enumerate(top_issues, start=1):
        top_issue_rows.append(
            {
                "rank": rank,
                "issue_key": item["issue_key"],
                "count": item["count"],
                "previous_count": item["previous_count"],
                "change_pct": item["change_pct"],
                "summary": item.get("summary"),
                "quotes": item.get("quotes", []),
            }
        )

    report = {
        "meta": {
            "generated_at": now_kst,
            "analysis_period": {
                "label": "최근 30일",
                "start": stats.get("created_at_min"),
                "end": stats.get("created_at_max"),
            },
            "total_count": stats["total_count"],
        },
        "windows": {
            "recent_30d_count": stats["recent_30d_count"],
            "prev_30d_count": stats["prev_30d_count"],
            "recent_90d_count": stats["recent_90d_count"],
        },
        "issues": {
            "top_recent_30d": top_issue_rows,
            "phase_counts": aggregate_phase_counts(recent_30),
            "phase_breakdown": aggregate_phase_breakdown(recent_30, prev_30),
            "trend_cards": build_trend_cards(df),
        },
        "samples": {
            "recent_quotes": extract_quotes(recent_30, limit=2),
        },
        "recommendations": {
            "short_term": [],
            "mid_term": [],
            "long_term": [],
        },
    }

    # Serialize timestamps in trend cards if any numeric issues exist.
    return convert_timestamps(report)


def convert_timestamps(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively converts pandas/Datetime objects to ISO strings."""
    def convert(value: Any) -> Any:
        if isinstance(value, pd.Timestamp):
            if pd.isna(value):
                return None
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return convert(payload)


def save_report(report: Dict[str, Any], path: Path) -> None:
    """Writes the report payload to disk as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report saved to {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch VOC data from Google Sheets and run analyses."
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Fetch rows and print a small sample, then exit.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Compute and print summary statistics after fetching data.",
    )
    parser.add_argument(
        "--show-top-issues",
        action="store_true",
        help="Display top VOC issues with change percentages.",
    )
    parser.add_argument(
        "--export-report",
        action="store_true",
        help="Generate JSON report file using the fetched data.",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=None,
        help="Custom path for the generated report JSON file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of rows to display when using --fetch-only (default: 3).",
    )
    return parser.parse_args()


def main() -> None:
    load_environment()
    args = parse_args()

    if args.fetch_only:
        print_sample_rows(limit=args.limit)
        return
    if not (args.stats or args.export_report or args.show_top_issues):
        print(
            "No action requested. Use --fetch-only, --stats, --show-top-issues, or --export-report."
        )
        return

    df = fetch_raw_data()
    if df.empty:
        print("No data available to process.")
        return

    if args.stats:
        stats = summarise_stats(df)
        print(pd.Series(stats).to_markdown())

    if args.show_top_issues:
        windows = compute_recent_windows_kst(df)
        recent_30 = windows["recent_30d"]
        prev_30 = windows["prev_30d"]
        top_rows = summarize_top_issues(recent_30, prev_30, limit=5)
        if not top_rows:
            print("No issues found in the recent 30-day window.")
        else:
            print(pd.DataFrame(top_rows).to_markdown(index=False))

    if args.export_report:
        report = build_report(df)
        report_path = Path(
            args.report_path
            or os.environ.get("REPORT_OUTPUT_PATH", str(DEFAULT_REPORT_PATH))
        )
        save_report(report, report_path)


if __name__ == "__main__":
    main()
