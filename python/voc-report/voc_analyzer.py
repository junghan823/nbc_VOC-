"""Core script for fetching and analysing LMS VOC data.

Step 1 focuses on fetching rows from Google Sheets so that we can
confirm OAuth and column mappings before wiring the rest of the pipeline.
"""

from __future__ import annotations

import argparse
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
    if args.stats:
        df = fetch_raw_data()
        if df.empty:
            print("No data available to compute statistics.")
            return
        stats = summarise_stats(df)
        print(pd.Series(stats).to_markdown())
        return

    # Placeholder for upcoming analysis pipeline.
    print(
        "Pipeline entry point not yet implemented. "
        "Run with --fetch-only to test Google Sheets connectivity."
    )


if __name__ == "__main__":
    main()
