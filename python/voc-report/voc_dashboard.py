"""Streamlit dashboard for the VOC learning environment report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "voc_report.json"


def load_report(path: Path = DEFAULT_REPORT_PATH) -> Dict[str, Any]:
    if not path.exists():
        st.warning(
            f"Report file not found at {path}. "
            "Run `python voc_analyzer.py --export-report` first."
        )
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        st.error(f"Failed to parse report JSON: {exc}")
        return {}


def render_meta(meta: Dict[str, Any]) -> None:
    st.subheader("📊 학습 환경 VOC 리포트")
    if not meta:
        st.info("리포트 메타 정보가 없습니다.")
        return

    cols = st.columns(3)
    cols[0].metric("생성일", meta.get("generated_at", "N/A")[:10])
    period = meta.get("analysis_period", {})
    start = period.get("start")
    end = period.get("end")
    cols[1].metric("분석 기간", period.get("label", "N/A"))
    cols[2].metric("VOC 총량", f"{meta.get('total_count', 0):,}")

    st.caption(
        f"집계 범위: {period.get('label', '최근 30일')} "
        f"(시작: {start}, 종료: {end})"
    )


def render_top_issues(issues: List[Dict[str, Any]]) -> None:
    st.subheader("⚠️ 이번 달 핵심 이슈 Top5")
    if not issues:
        st.info("Top5 이슈 데이터가 없습니다.")
        return

    cols = st.columns(5)
    for col, issue in zip(cols, issues):
        change_pct = issue.get("change_pct", 0)
        emoji = (
            "🔴" if change_pct >= 30 else "🟡" if change_pct >= 10 else "🟢"
        )
        with col:
            st.markdown(
                f"**#{issue.get('rank', '?')} {issue.get('issue_key', '기타')}**"
            )
            st.metric("30일 건수", issue.get("count", 0))
            st.metric(
                "전월 대비",
                f"{change_pct:+.1f}%",
                help=f"직전 30일: {issue.get('previous_count', 0)}건",
            )
            st.markdown(f"{emoji} 변화 상태")


def render_phase_analysis(phase_counts: Dict[str, Any]) -> None:
    st.subheader("📚 학습 단계별 주요 불편")
    if not phase_counts:
        st.info("단계별 집계 데이터가 없습니다.")
        return

    phase_df = pd.DataFrame(
        [
            {"단계": phase, "건수(30일)": count}
            for phase, count in phase_counts.items()
        ]
    ).sort_values("건수(30일)", ascending=False)

    st.dataframe(
        phase_df,
        use_container_width=True,
        hide_index=True,
    )


def render_quotes(quotes: List[str]) -> None:
    st.subheader("💬 대표 수강생 발화")
    if not quotes:
        st.info("대표 발화가 없습니다.")
        return

    for quote in quotes:
        st.markdown(
            f"> “{quote}”",
        )


def render_recommendations(recommendations: Dict[str, Any]) -> None:
    st.subheader("🛠 권장 조치")
    if not recommendations:
        st.info("권장 조치 정보가 없습니다.")
        return

    tabs = st.tabs(["단기", "중기", "모니터링"])
    keys = ["short_term", "mid_term", "long_term"]
    for tab, key in zip(tabs, keys):
        with tab:
            actions = recommendations.get(key, [])
            if not actions:
                st.write("추가 예정")
            else:
                for action in actions:
                    st.markdown(f"- {action}")


def main() -> None:
    st.set_page_config(page_title="VOC 리포트", layout="wide")
    report = load_report()
    if not report:
        return

    render_meta(report.get("meta", {}))
    st.divider()
    render_top_issues(report.get("issues", {}).get("top_recent_30d", []))
    st.divider()
    render_phase_analysis(report.get("issues", {}).get("phase_counts", {}))
    st.divider()
    render_quotes(report.get("samples", {}).get("recent_quotes", []))
    st.divider()
    render_recommendations(report.get("recommendations", {}))


if __name__ == "__main__":
    main()
