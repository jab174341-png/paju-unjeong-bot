"""정제된 운정 거래 데이터를 로드하는 진입점.

호출 흐름:
    load_unjeong_trades(months=12)
      → 최근 12개월 각 월에 대해
        → 캐시 확인 → 있으면 사용
                   → 없으면 API 호출 → 캐시에 저장
      → 모든 월 데이터를 합쳐 정제(normalize)
      → 운정 6개 법정동만 필터링
      → DataFrame 반환
"""

from datetime import date
from typing import List
import pandas as pd

from app.api.molit import fetch_apt_trades
from app.analysis.cache import get_cached, save_to_cache
from app.analysis.normalize import normalize_trades
from app.data.regions import PAJU_LAWD_CD, UNJEONG_DONGS


def get_recent_months(n: int) -> List[str]:
    """오늘 기준 최근 n개월의 YYYYMM 리스트 (오래된 순)."""
    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(n):
        months.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def fetch_with_cache(lawd_cd: str, deal_ymd: str, max_age_hours: int = 24) -> List[dict]:
    """캐시 우선. 없거나 만료면 API 호출 후 저장."""
    cached = get_cached(lawd_cd, deal_ymd, max_age_hours=max_age_hours)
    if cached is not None:
        return cached

    trades = fetch_apt_trades(lawd_cd, deal_ymd)
    save_to_cache(lawd_cd, deal_ymd, trades)
    return trades


def load_unjeong_trades(months: int = 12) -> pd.DataFrame:
    """최근 N개월의 운정신도시 정제 거래 데이터 반환.

    Args:
        months: 가져올 개월 수 (기본 12개월)

    Returns:
        정제된 거래 DataFrame. 운정 6개 법정동에 속한 거래만 포함.
    """
    all_raw = []
    for ym in get_recent_months(months):
        # 현재 월은 신규 거래가 계속 추가되므로 캐시를 짧게(6시간) 유지
        is_current = (ym == date.today().strftime("%Y%m"))
        max_age = 6 if is_current else 24 * 7  # 과거 월은 1주일 캐시
        try:
            trades = fetch_with_cache(PAJU_LAWD_CD, ym, max_age_hours=max_age)
            all_raw.extend(trades)
        except Exception as e:
            print(f"⚠️  {ym} 조회 실패: {e}")

    df = normalize_trades(all_raw)
    if df.empty:
        return df

    # 운정 6개 법정동만 필터링
    df = df[df["dong"].isin(UNJEONG_DONGS)].reset_index(drop=True)
    return df
