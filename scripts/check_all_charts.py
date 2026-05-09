"""모든 단지·평형 차트 자동 검증 스크립트.

실행:
    python scripts/check_all_charts.py [--base URL]

옵션:
    --base : 검증할 서버 URL (기본: 라이브 사이트)

종료코드:
    0 : 모든 차트 정상 또는 거래 없음
    1 : 깨진 차트 발견
"""

import sys
import argparse
from pathlib import Path
from urllib.parse import quote
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.complexes import UNJEONG_COMPLEXES
from app.analysis.loader import load_unjeong_trades
from app.analysis.aggregate import summarize_complex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://paju-unjeong-bot.onrender.com")
    parser.add_argument("--threshold", type=int, default=20000,
                        help="이 바이트 미만이면 깨진 차트로 간주 (default 20000)")
    args = parser.parse_args()

    print(f"📡 대상 서버: {args.base}\n")

    # 로컬 데이터로 어느 단지의 어떤 평형이 있어야 하는지 파악
    print("📥 로컬 12개월 데이터 로드 중...")
    df = load_unjeong_trades(months=12)
    print(f"   → {len(df)}건\n")

    ok, fail, nodata = [], [], []
    for c in UNJEONG_COMPLEXES:
        apt = c["name"]
        summary = summarize_complex(df, apt, period="3M")
        if not summary:
            nodata.append(apt)
            continue
        for bucket in summary.keys():
            url = f"{args.base}/chart?apt_name={quote(apt)}&bucket={quote(bucket)}"
            try:
                r = requests.get(url, timeout=15)
                size = len(r.content)
                if r.status_code == 200 and size > args.threshold:
                    ok.append((apt, bucket, size))
                else:
                    fail.append((apt, bucket, r.status_code, size))
            except Exception as e:
                fail.append((apt, bucket, "ERR", str(e)))

    print(f"✅ 정상 차트: {len(ok)}개")
    print(f"❌ 깨진 차트: {len(fail)}개")
    print(f"📭 거래 없는 단지(차트 없음 정상): {len(nodata)}개\n")

    if fail:
        print("==== 깨진 차트 상세 ====")
        for apt, bucket, status, size in fail:
            print(f"  [{status}] {size}B  {apt} {bucket}")
        sys.exit(1)
    else:
        print("✨ 모든 차트 정상!")


if __name__ == "__main__":
    main()
