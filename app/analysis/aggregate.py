"""단지·평형·기간별 시세 집계.

사용 예:
    df = load_unjeong_trades(months=12)
    summary = summarize_complex(df, "산내마을9단지힐스테이트운정", period="3M")
    # summary = {
    #   "84㎡대": {"avg": 95000, "count": 12, "change_pct": 3.5, ...},
    #   "59㎡대": {...}
    # }
"""

from datetime import date, timedelta
from typing import Dict
import pandas as pd

# 기간 라벨 → (현재 구간 일수, 직전 구간 일수)
PERIOD_DAYS = {
    "6M": 180,
    "3M": 90,
    "1M": 30,
    "1W": 7,
}


def get_period_window(period: str, ref_date: date = None) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """기간 라벨로부터 (구간시작, 구간끝, 직전구간시작) 반환.

    예: period='3M', ref_date=2026-05-07
        → 현재구간: 2026-02-06 ~ 2026-05-07
        → 직전구간: 2025-11-08 ~ 2026-02-06
    """
    if ref_date is None:
        ref_date = date.today()
    days = PERIOD_DAYS[period]
    end = pd.Timestamp(ref_date)
    start = end - pd.Timedelta(days=days)
    prev_start = start - pd.Timedelta(days=days)
    return start, end, prev_start


def summarize_complex(
    df: pd.DataFrame,
    apt_name: str,
    period: str = "3M",
) -> Dict[str, Dict]:
    """단지의 평형 버킷별 시세 요약.

    Args:
        df: load_unjeong_trades()로 받은 정제 데이터프레임
        apt_name: 단지명 (정확히 일치해야 함)
        period: '6M' / '3M' / '1M' / '1W'

    Returns:
        평형 버킷 → 통계 dict 매핑.
        통계 dict: avg(만원), median(만원), count(건), change_pct(%),
                   min(만원), max(만원), per_sqm(만원/m²)
    """
    if period not in PERIOD_DAYS:
        raise ValueError(f"지원하지 않는 기간: {period}. {list(PERIOD_DAYS)} 중 하나를 사용하세요.")

    apt_df = df[df["apt_name"] == apt_name]
    if apt_df.empty:
        return {}

    start, end, prev_start = get_period_window(period)

    current = apt_df[(apt_df["deal_date"] >= start) & (apt_df["deal_date"] <= end)]
    previous = apt_df[(apt_df["deal_date"] >= prev_start) & (apt_df["deal_date"] < start)]

    result = {}
    for bucket in current["area_bucket"].dropna().unique():
        cur_b = current[current["area_bucket"] == bucket]
        prev_b = previous[previous["area_bucket"] == bucket]
        if cur_b.empty:
            continue

        avg = int(cur_b["deal_amount"].mean())
        prev_avg = int(prev_b["deal_amount"].mean()) if not prev_b.empty else None
        change_pct = (
            round((avg - prev_avg) / prev_avg * 100, 2) if prev_avg else None
        )

        result[bucket] = {
            "avg": avg,
            "median": int(cur_b["deal_amount"].median()),
            "count": len(cur_b),
            "min": int(cur_b["deal_amount"].min()),
            "max": int(cur_b["deal_amount"].max()),
            "per_sqm": int(cur_b["price_per_sqm"].mean()),
            "change_pct": change_pct,
            "prev_avg": prev_avg,
            "prev_count": len(prev_b),
        }
    return result


def get_trend_series(
    df: pd.DataFrame,
    apt_name: str,
    area_bucket: str,
    months: int = 12,
) -> pd.DataFrame:
    """단지·평형의 월별 평균가 시계열 (차트용).

    Returns:
        컬럼: month (YYYY-MM), avg_amount (만원), count (건수)
    """
    apt_df = df[
        (df["apt_name"] == apt_name) & (df["area_bucket"] == area_bucket)
    ].copy()
    if apt_df.empty:
        return pd.DataFrame(columns=["month", "avg_amount", "count"])

    apt_df["month"] = apt_df["deal_date"].dt.to_period("M")
    grouped = apt_df.groupby("month").agg(
        avg_amount=("deal_amount", "mean"),
        count=("deal_amount", "size"),
    ).reset_index()
    grouped["month"] = grouped["month"].astype(str)
    grouped["avg_amount"] = grouped["avg_amount"].astype(int)
    return grouped.tail(months)
