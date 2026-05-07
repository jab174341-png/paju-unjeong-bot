"""분석 모듈 통합 테스트.

운정 데이터를 12개월치 로드한 뒤, 한 단지의 기간별 시세를 출력합니다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis.loader import load_unjeong_trades
from app.analysis.aggregate import summarize_complex, get_trend_series

TARGET = "산내마을9단지힐스테이트운정"


def fmt_won(amount_manwon: int) -> str:
    """85000(만원) → '8억 5,000만원' 형식."""
    eok = amount_manwon // 10000
    rest = amount_manwon % 10000
    if eok and rest:
        return f"{eok}억 {rest:,}만원"
    if eok:
        return f"{eok}억"
    return f"{rest:,}만원"


def main():
    print("📥 운정 12개월치 데이터 로드 중 (캐시 사용)...")
    df = load_unjeong_trades(months=12)
    print(f"   → 운정 거래 총 {len(df)}건\n")

    print(f"🏢 분석 대상: {TARGET}\n")

    for period, label in [("6M", "6개월"), ("3M", "3개월"), ("1M", "1개월"), ("1W", "주간")]:
        print(f"━━━ [{label}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        summary = summarize_complex(df, TARGET, period=period)
        if not summary:
            print(f"   해당 기간 거래 없음\n")
            continue

        for bucket, s in sorted(summary.items()):
            change = (
                f"{s['change_pct']:+.2f}%" if s["change_pct"] is not None else "—"
            )
            print(
                f"  {bucket:8s} | 평균 {fmt_won(s['avg']):14s} "
                f"| 거래 {s['count']:2d}건 | 직전대비 {change}"
            )
            print(
                f"  {'':8s} | 최저 {fmt_won(s['min']):14s} "
                f"| 최고 {fmt_won(s['max']):14s} "
                f"| 단가 {s['per_sqm']:,}만원/㎡"
            )
        print()

    # 월별 추이 (차트 데이터)
    print("📈 84㎡대 월별 평균 추이 (최근 12개월):")
    trend = get_trend_series(df, TARGET, "84㎡대", months=12)
    for _, row in trend.iterrows():
        bar = "█" * (row["avg_amount"] // 2000)
        print(f"  {row['month']}  {fmt_won(int(row['avg_amount'])):14s} ({row['count']:2d}건) {bar}")


if __name__ == "__main__":
    main()
