"""우리 단지명을 네이버 단지(hscpNo)에 매칭하고 현재 매물 요약을 반환.

전략:
1. MANUAL_NAVER_OVERRIDES 의 수동 매핑 우선 (확실한 단지)
2. 자동 이름 매칭 (정확/괄호제거/마을N단지 키워드)
3. 매칭된 단지의 매물 요약(개수, 가격범위, 면적범위) + 네이버 링크 반환
"""

import re
from typing import Optional, Dict

from app.api.naver_land import fetch_all_unjeong_complexes

# 자동 매칭으로 안 잡히는 단지의 수동 hscpNo 매핑
# (네이버 단지명이 아예 다르거나 우리 명칭과 형식이 달라서)
MANUAL_NAVER_OVERRIDES: Dict[str, str] = {
    # 동패동
    "한울마을1단지운정신도시IPARK": "119854",   # 운정신도시아이파크
    "초롱꽃마을8단지중흥S클래스": "126334",      # 초롱꽃8단지중흥S-클래스
    "초롱꽃마을13단지디에트르더퍼스트": "126349",  # 파주운정신도시디에트르더퍼스트
    "초롱꽃마을6단지금강펜테리움": "145184",      # 금강펜테리움센트럴파크
    # 목동동
    "운정신도시 센트럴 푸르지오": "111541",       # 운정신도시센트럴푸르지오
    "산내마을7단지화성파크드림": "119518",        # 운정화성파크드림시그니처
    # 다율동
    "해오름마을14단지푸르지오파르세나": "144843",  # 운정신도시푸르지오파르세나
    "해오름마을10단지파크푸르지오": "126347",      # 운정신도시파크푸르지오
    "청석마을9단지대원효성": "17753",              # 청석마을대원효성
    "청석마을8단지동문굿모닝힐": "17281",          # 청석마을운정동문디이스트
    # 야당동
    "한빛마을4단지롯데캐슬Ⅱ": "111493",            # 롯데캐슬파크타운Ⅱ
    "한빛마을9단지롯데캐슬1차": "110323",           # 롯데캐슬파크타운
}


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


def get_listings_summary(apt_name: str, dong: str) -> Optional[Dict]:
    """단지의 현재 매물 요약. 매칭 실패 시 None.

    반환 dict:
        deal_count (int): 현재 매매 매물 수
        lease_count (int): 전세 매물 수
        rent_count (int): 월세 매물 수
        price_min, price_max (str): 매매 가격 범위 (HTML <em> 태그 포함된 원본)
        area_min, area_max (float): 면적 범위 (전용면적 m²)
        has_small_medium (bool): 59~74㎡대(전용 80㎡이하) 매물이 있을 가능성
        naver_url (str): 사용자가 클릭할 수 있는 네이버 모바일 매물 페이지
        naver_id (str): hscpNo
        naver_name (str): 네이버에서의 정식 명칭
    """
    found = find_naver_complex(apt_name, dong)
    if not found:
        return None

    hscp_no = found.get("hscpNo")
    try:
        min_spc = float(found.get("minSpc") or 0)
        max_spc = float(found.get("maxSpc") or 0)
    except (TypeError, ValueError):
        min_spc, max_spc = 0.0, 0.0

    # 가격 범위에서 HTML 태그 제거 (예: "7<em class='txt_unit'>억</em>" → "7억")
    def clean_price(raw):
        if not raw:
            return ""
        return re.sub(r"<[^>]+>", "", str(raw)).strip()

    return {
        "deal_count": int(found.get("dealCnt") or 0),
        "lease_count": int(found.get("leaseCnt") or 0),
        "rent_count": int(found.get("rentCnt") or 0),
        "price_min": clean_price(found.get("dealPrcMin")),
        "price_max": clean_price(found.get("dealPrcMax")),
        "area_min": min_spc,
        "area_max": max_spc,
        "has_small_medium": 0 < min_spc <= 80.0,
        "naver_url": (
            f"https://m.land.naver.com/complex/info/{hscp_no}?tradTpCd=A1"
        ),
        "naver_id": str(hscp_no) if hscp_no else "",
        "naver_name": found.get("hscpNm") or "",
    }
