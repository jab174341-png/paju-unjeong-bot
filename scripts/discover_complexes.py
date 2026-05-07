"""운정신도시 아파트 단지 목록 자동 발견 스크립트.

최근 6개월간의 파주시 거래 데이터를 받아와, 운정 지역 법정동에 속하는
아파트 단지명을 거래 빈도 순으로 정렬해 출력합니다.

실행:
    python scripts/discover_complexes.py
"""

import sys
from pathlib import Path
from collections import Counter
from datetime import date

# 프로젝트 루트를 import 경로에 추가 (app.* 모듈을 쓰기 위함)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.molit import fetch_apt_trades
from app.data.regions import PAJU_LAWD_CD, UNJEONG_DONGS


def get_recent_months(n: int) -> list[str]:
    """오늘로부터 거꾸로 n개월의 YYYYMM 리스트 반환 (최신부터)."""
    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(n):
        months.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return months


def main():
    months = get_recent_months(6)
    print(f"📅 조회 기간: {months[-1]} ~ {months[0]} (최근 6개월)\n")

    all_trades = []
    for ym in months:
        print(f"  [{ym}] 조회 중...", end=" ", flush=True)
        try:
            trades = fetch_apt_trades(PAJU_LAWD_CD, ym)
            print(f"{len(trades)}건")
            all_trades.extend(trades)
        except Exception as e:
            print(f"오류: {e}")

    print(f"\n📊 파주시 전체 거래: {len(all_trades)}건")

    # 운정 지역 필터링 — API 응답의 어떤 키가 법정동인지 모르니 후보 키들을 시도
    dong_keys_candidates = ["법정동", "umdNm"]
    apt_keys_candidates = ["아파트", "aptNm"]

    def get_field(trade, candidates):
        for k in candidates:
            if k in trade and trade[k]:
                return trade[k]
        return ""

    unjeong_trades = [
        t for t in all_trades
        if get_field(t, dong_keys_candidates).strip() in UNJEONG_DONGS
    ]
    print(f"📍 운정 지역 거래: {len(unjeong_trades)}건\n")

    if not unjeong_trades:
        # 디버그: 응답 키 구조 확인
        if all_trades:
            print("⚠️  운정 지역 거래가 0건입니다. 첫 거래의 필드 키를 확인하세요:")
            print(f"   {list(all_trades[0].keys())}")
            print(f"\n   첫 거래 샘플: {all_trades[0]}")
        return

    # 단지명 카운트 + 단지별 동
    counter = Counter(
        get_field(t, apt_keys_candidates).strip() for t in unjeong_trades
    )
    apt_to_dongs = {}
    for t in unjeong_trades:
        apt = get_field(t, apt_keys_candidates).strip()
        dong = get_field(t, dong_keys_candidates).strip()
        apt_to_dongs.setdefault(apt, set()).add(dong)

    print("🏢 거래 빈도 상위 30개 단지:")
    print("=" * 70)
    for i, (apt, count) in enumerate(counter.most_common(30), 1):
        dong_str = ", ".join(sorted(apt_to_dongs.get(apt, [])))
        print(f"{i:2d}. {apt[:35]:35s} {count:4d}건  ({dong_str})")


if __name__ == "__main__":
    main()
