"""국토부 API 응답을 깔끔한 pandas DataFrame으로 변환.

원본 응답은 문자열·공백·콤마가 섞여 있어 그대로 분석할 수 없습니다.
이 모듈은 다음을 수행합니다:
- 숫자 문자열 → 정수/실수로 변환
- 년/월/일 → 단일 날짜(datetime)로 통합
- 전용면적 → 평형 버킷 추가 (59㎡대/84㎡대 등)
- 평당 단가 컬럼 추가
"""

from typing import List, Dict, Optional
import pandas as pd

# 평형 버킷 정의 (전용면적 m² 기준)
AREA_BUCKETS = [
    ("59㎡대", 50, 67),
    ("74㎡대", 67, 80),
    ("84㎡대", 80, 95),
    ("100㎡대", 95, 110),
    ("120㎡+", 110, 9999),
]


def _to_int(s: Optional[str]) -> Optional[int]:
    """'  85,000  ' → 85000. 변환 실패 시 None."""
    if not s:
        return None
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _to_float(s: Optional[str]) -> Optional[float]:
    """문자열을 float로. 실패 시 None."""
    if not s:
        return None
    try:
        return float(s.strip())
    except (ValueError, AttributeError):
        return None


def _bucket_for_area(area_sqm: Optional[float]) -> Optional[str]:
    """전용면적(m²)을 평형 버킷 라벨로 변환."""
    if area_sqm is None:
        return None
    for label, lo, hi in AREA_BUCKETS:
        if lo <= area_sqm < hi:
            return label
    return None


def normalize_trades(raw_trades: List[Dict[str, str]]) -> pd.DataFrame:
    """원본 API 응답을 정제된 DataFrame으로 변환.

    Returns:
        다음 컬럼을 가진 DataFrame:
        - apt_name (str): 단지명
        - dong (str): 법정동
        - deal_amount (int): 거래금액 (만원 단위)
        - area_sqm (float): 전용면적 (m²)
        - area_bucket (str): 평형 버킷 ('59㎡대' 등)
        - floor (int): 층
        - build_year (int): 건축년도
        - deal_date (datetime): 계약일
        - price_per_sqm (int): 평당 단가 (만원/m²)
    """
    rows = []
    for t in raw_trades:
        amount = _to_int(t.get("dealAmount"))
        area = _to_float(t.get("excluUseAr"))
        year = _to_int(t.get("dealYear"))
        month = _to_int(t.get("dealMonth"))
        day = _to_int(t.get("dealDay"))

        if amount is None or area is None or not year or not month or not day:
            continue  # 필수 데이터 빠진 거래는 스킵

        try:
            deal_date = pd.Timestamp(year=year, month=month, day=day)
        except (ValueError, TypeError):
            continue

        rows.append({
            "apt_name": (t.get("aptNm") or "").strip(),
            "dong": (t.get("umdNm") or "").strip(),
            "deal_amount": amount,
            "area_sqm": area,
            "area_bucket": _bucket_for_area(area),
            "floor": _to_int(t.get("floor")) or 0,
            "build_year": _to_int(t.get("buildYear")) or 0,
            "deal_date": deal_date,
            "price_per_sqm": round(amount / area) if area > 0 else 0,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("deal_date").reset_index(drop=True)
    return df
