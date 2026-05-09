"""우리 단지명을 네이버 단지(hscpNo)에 매칭하고 현재 매물 요약을 반환.

전략:
1. MANUAL_NAVER_OVERRIDES 의 수동 매핑 우선 (확실한 단지)
2. 자동 이름 매칭 (정확/괄호제거/마을N단지 키워드)
3. 매칭된 단지의 매물 요약(개수, 가격범위, 면적범위) + 네이버 링크 반환
"""

import re
from typing import Optional, Dict

from app.api.naver_land import fetch_all_unjeong_complexes

# 32개 단지의 네이버 hscpNo 전체 매핑 (하드코딩).
# 네이버 API가 차단되어 실시간 매물 데이터를 못 받아도, 단지명만 알면
# 즉시 네이버 매물 페이지 URL을 만들 수 있게 함.
NAVER_HSCP_MAP: Dict[str, str] = {
    # 동패동
    "한울마을1단지운정신도시IPARK": "119854",       # 운정신도시아이파크
    "한울마을2단지운정벽산블루밍아파트": "8385",     # 한울마을2단지운정벽산블루밍
    "초롱꽃마을8단지중흥S클래스": "126334",          # 초롱꽃8단지중흥S-클래스
    "초롱꽃마을12단지e편한세상운정어반프라임": "127134",
    "초롱꽃마을13단지디에트르더퍼스트": "126349",     # 파주운정신도시디에트르더퍼스트
    "초롱꽃마을6단지금강펜테리움": "145184",          # 금강펜테리움센트럴파크
    "운정자이시그니처": "158619",
    # 목동동
    "산내마을9단지힐스테이트운정": "113942",
    "산내마을7단지화성파크드림": "119518",            # 운정화성파크드림시그니처
    "산내마을6단지한라비발디": "102613",
    "산내마을8단지월드메르디앙(114-37)": "3722",
    "산내마을2단지센트럴리움(공공임대)": "168338",
    "운정신도시 센트럴 푸르지오": "111541",          # 운정신도시센트럴푸르지오
    "해솔마을1단지두산위브(647)": "27721",
    "해솔마을2단지월드메르디앙(2-117)": "3446",
    "해솔마을3단지운정현대": "3456",
    "해솔마을4단지벽산우남연리지(667)": "27719",
    "해솔마을5단지삼부르네상스(679)": "27667",
    # 다율동
    "해오름마을14단지푸르지오파르세나": "144843",     # 운정신도시푸르지오파르세나
    "해오름마을10단지파크푸르지오": "126347",         # 운정신도시파크푸르지오
    "운정신도시한라비발디파크젠해오름마을13단지": "144947",
    "청석마을9단지대원효성": "17753",                 # 청석마을대원효성
    "청석마을8단지동문굿모닝힐": "17281",             # 청석마을운정동문디이스트
    # 야당동
    "한빛마을2단지휴먼빌": "9066",                    # 한빛마을2단지휴먼빌레이크팰리스
    "한빛마을4단지롯데캐슬Ⅱ": "111493",               # 롯데캐슬파크타운Ⅱ
    "한빛마을5단지캐슬앤칸타빌": "100751",
    "한빛마을7단지(한신휴플러스)": "132882",
    "한빛마을9단지롯데캐슬1차": "110323",             # 롯데캐슬파크타운
    "운정아모리움": "27751",                          # 운정아모리움한빛마을
    # 와동동
    "해솔마을7단지롯데캐슬": "103338",
    "힐스테이트더운정": "179760",
    "가람마을8단지동문굿모닝힐": "3451",
}

# 호환성: 기존 코드가 MANUAL_NAVER_OVERRIDES 를 참조하던 자리를
# 동일 객체로 유지 (위 전체 맵이 곧 override 역할).
MANUAL_NAVER_OVERRIDES = NAVER_HSCP_MAP


def find_naver_complex(apt_name: str, dong: str) -> Optional[Dict]:
    """우리 단지명에 매칭되는 네이버 단지 dict 반환. 없으면 None."""
    all_complexes = fetch_all_unjeong_complexes()

    # 1. 수동 오버라이드
    if apt_name in MANUAL_NAVER_OVERRIDES:
        target_id = str(MANUAL_NAVER_OVERRIDES[apt_name])
        for d_complexes in all_complexes.values():
            for c in d_complexes:
                if str(c.get("hscpNo")) == target_id:
                    return c
        # override 가리키는 ID가 없으면 자동 매칭 시도

    candidates = all_complexes.get(dong, [])

    # 2. 정확히 일치
    found = next(
        (c for c in candidates if c.get("hscpNm") == apt_name),
        None,
    )
    if found:
        return found

    # 3. 괄호 제거 후 부분 일치
    clean = apt_name.split("(")[0].strip()
    if clean:
        found = next(
            (
                c for c in candidates
                if c.get("hscpNm")
                and (clean == c["hscpNm"]
                     or clean in c["hscpNm"]
                     or c["hscpNm"] in clean)
            ),
            None,
        )
        if found:
            return found

    # 4. "마을X단지" 키워드 매칭
    m = re.match(r'(\S+마을\d+단지)', apt_name)
    if m:
        keyword = m.group(1)
        found = next(
            (c for c in candidates if keyword in (c.get("hscpNm") or "")),
            None,
        )
        if found:
            return found

    return None


def _clean_price(raw):
    """HTML 태그 제거 (예: '7<em>억</em>' → '7억')."""
    if not raw:
        return ""
    return re.sub(r"<[^>]+>", "", str(raw)).strip()


def get_listings_summary(apt_name: str, dong: str) -> Optional[Dict]:
    """단지의 현재 매물 요약.

    네이버 API가 차단되거나 실패해도, 하드코딩된 hscpNo가 있으면
    최소한 네이버 매물 페이지 URL은 반환한다. (매물 수·가격 등 라이브
    데이터는 has_live_data=False 로 표시)

    반환 dict 주요 필드:
        has_live_data (bool): True 면 deal_count, price_min/max 등 사용 가능
        naver_url (str): 클릭 가능한 네이버 모바일 매물 페이지 URL
        naver_id (str): hscpNo
        naver_name (str): 네이버 정식 명칭 (없으면 우리 단지명)
        그 외 deal_count/lease_count/rent_count/price_min/price_max/
        area_min/area_max/has_small_medium 은 has_live_data 일 때만 의미 있음
    """
    # 1) 하드코딩된 hscpNo 우선 (네이버 차단 시에도 URL 보장)
    hscp_no = NAVER_HSCP_MAP.get(apt_name)

    # 2) 라이브 데이터 시도 (실패해도 페이지 응답에 영향 없음)
    found = None
    try:
        found = find_naver_complex(apt_name, dong)
    except Exception as e:
        print(f"⚠️  네이버 라이브 매물 조회 실패 ({apt_name}): {e}")

    # 라이브 데이터가 있으면 hscpNo도 거기서 사용 (혹시 매핑이 비어있을 경우 대비)
    if found and not hscp_no:
        hscp_no = found.get("hscpNo")

    if not hscp_no:
        # 단지에 매핑된 네이버 단지가 전혀 없음 → 매물 섹션 자체 표시 안 함
        return None

    naver_url = f"https://m.land.naver.com/complex/info/{hscp_no}?tradTpCd=A1"

    # 라이브 데이터 있는 경우: 풀 응답
    if found:
        try:
            min_spc = float(found.get("minSpc") or 0)
            max_spc = float(found.get("maxSpc") or 0)
        except (TypeError, ValueError):
            min_spc, max_spc = 0.0, 0.0

        return {
            "has_live_data": True,
            "deal_count": int(found.get("dealCnt") or 0),
            "lease_count": int(found.get("leaseCnt") or 0),
            "rent_count": int(found.get("rentCnt") or 0),
            "price_min": _clean_price(found.get("dealPrcMin")),
            "price_max": _clean_price(found.get("dealPrcMax")),
            "area_min": min_spc,
            "area_max": max_spc,
            "has_small_medium": 0 < min_spc <= 80.0,
            "naver_url": naver_url,
            "naver_id": str(hscp_no),
            "naver_name": found.get("hscpNm") or apt_name,
        }

    # 라이브 데이터 없는 경우: 최소 정보 (URL만)
    return {
        "has_live_data": False,
        "naver_url": naver_url,
        "naver_id": str(hscp_no),
        "naver_name": apt_name,
    }
