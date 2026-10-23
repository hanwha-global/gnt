"""공통 규칙: 해외법인 국가 추정, 펀드·신탁·SPV 제외 판정, 법인명 정규화."""
import re

COUNTRY_ALIASES = {"중국(홍콩)": "홍콩", "Hong Kong": "홍콩", "UAE": "아랍에미리트"}

# 법인명 키워드 → 국가 (먼저 맞는 규칙 우선)
COUNTRY_RULES = [
    # 국가명이 직접 들어간 경우를 먼저 본다
    (r"abu dhabi|adgm|dubai|\buae\b", "아랍에미리트"),
    (r"hong ?kong|\(h\.?k\.?\)|\(hk\)", "홍콩"),
    (r"singapore", "싱가포르"),
    (r"viet ?nam", "베트남"),
    (r"indonesia|sekuritas", "인도네시아"),
    (r"mongolia", "몽골"),
    (r"cambodia", "캄보디아"),
    (r"kazakh|almaty|astana|zharyk zhol", "카자흐스탄"),  # Zharyk Zhol Company 2007 LLP: 한화 출자, 카자흐스탄(사용자 확인 2026-10-21)
    (r"thailand", "태국"),
    (r"bras[iz]l", "브라질"),
    (r"greece", "그리스"),
    (r"india\b", "인도"),
    (r"japan|tokyo|株式会社", "일본"),
    (r"china|shanghai|beijing|shenzhen|북경|상해|심천|유한공사", "중국"),
    (r"america|\(usa?\)|\busa\b|new york", "미국"),
    (r"\(uk\)|london|europe", "영국"),
    # 국내 공시가 한글로 적은 해외 법인명(예: '신한투자증권 아메리카', '○○ 베트남 법인')
    (r"베트남", "베트남"), (r"인도네시아|인니", "인도네시아"), (r"싱가포르|싱가폴", "싱가포르"), (r"홍콩", "홍콩"),
    (r"아메리카|미국|뉴욕", "미국"), (r"런던|영국|유럽", "영국"), (r"일본|도쿄|동경", "일본"), (r"인도(?!네시아)", "인도"),
    (r"몽골", "몽골"), (r"브라질", "브라질"), (r"카자흐", "카자흐스탄"),
    # 국가명이 없으면 법인 형태(접미사)로 추정
    (r"\bpte\.?\b", "싱가포르"),
    (r"\bjsc\b|joint stock", "베트남"),
    (r"^pt\.? ", "인도네시아"),
    (r"private limited", "인도"),
    (r"\bllc\b|\binc\.?$|\bus,? inc", "미국"),
]

# 펀드·신탁·투자기구(Vehicle) 판정: 법인명 또는 업종
FUND_NAME = re.compile(
    r"펀드|fund|신탁|trust|투자조합|조합$|사모|기금|vehicle|\bspc\b|\bspv\b|유동화|"
    r"제\s?(\d+|[일이삼사오육칠팔구십]+)\s?차|\d+\s?호\b|\bl\.?p\.?f?\b|\bpef\b|securiti[sz]ation|bvi \d|"
    r"리츠|reit|feeder|private ?equity|capital ?partners|co-?investment|l\.p\.?$|offshore|special opportunities|"
    r"strateg(y|ies)|investment [a-z]?\d+\b|investment[a-z]\d+",
    re.I,
)
FUND_BIZ = re.compile(r"집합투자기구|투자신탁|투자기구|특수목적|신탁업자|유동화", re.I)


def normalize_country(c):
    c = (c or "").strip()
    return COUNTRY_ALIASES.get(c, c) or None


def guess_country(name):
    n = (name or "").lower()
    for pat, country in COUNTRY_RULES:
        if re.search(pat, n):
            return country
    return None


def classify_entity(name, business=None):
    """('법인' | '제외', 제외사유) 를 돌려준다."""
    if name and FUND_NAME.search(name):
        return "제외", "펀드·신탁·투자기구(법인명)"
    if business and FUND_BIZ.search(business):
        return "제외", "펀드·신탁·투자기구(업종)"
    return "법인", None


# 금융업 법인으로 보이는 이름(증권·투자·자산운용·지주·자문 등). DART 신규 출자 법인을 자동 반영할 때 쓴다
FIN_NAME = re.compile(r"securit|sekuritas|invest|asset|capital|holding|advis|financ|broker|wealth|fund ?management|"
                      r"증권|투자|자산운용|금융|자문|캐피탈|지주", re.I)


def auto_new_entity(h):
    """DART 타법인출자현황에 새로 나온 해외 출자 중 바로 네트워크에 넣을 법인인지와 그 이유.

    경영참여 목적·지분 50% 이상, 펀드·신탁·Vehicle이 아니고, 나라를 알 수 있으며, 이름이 금융업 법인일 때만 자동 반영한다.
    나머지는 '신규 후보'로 남겨 화면에 확인 필요로 표시한다.
    """
    name = h.get("name") or ""
    if "경영" not in (h.get("purpose") or ""):
        return False, "단순·일반투자"
    if (h.get("share_pct") or 0) < 50:
        return False, "지분 50% 미만"
    if classify_entity(name)[0] != "법인":
        return False, "펀드·신탁·Vehicle"
    if not (h.get("country_guess") or guess_country(name)):
        return False, "소재국 확인 필요"
    if not FIN_NAME.search(name):
        return False, "업종 확인 필요"
    return True, None


def is_overseas_name(name):
    """한글 국내 법인명(주식회사, ㈜ 등)이 아닌 해외 법인명인지 추정한다."""
    if not name:
        return False
    if re.search(r"주식회사|\(주\)|㈜|유한회사", name) and not re.search(r"유한공사", name):
        return False
    if guess_country(name):
        return True
    # 한글이 없는 로마자 법인명은 국가를 못 맞혀도 해외 법인 후보로 본다
    return not re.search(r"[가-힣]", name) and re.search(r"[A-Za-z]{3,}", name) is not None


def norm_name(name):
    n = (name or "").lower().replace("&", "and")
    n = re.sub(r"\b(co|corp|corporation|company|ltd|limited|inc|llc|pte|pt|jsc|tbk)\b\.?", " ", n)
    return re.sub(r"[^0-9a-z가-힣]+", "", n)


GENERIC = {"securities", "security", "investment", "investments", "ltd", "limited", "inc", "co", "corp",
           "corporation", "company", "pt", "pte", "the", "and", "llc", "jsc", "tbk", "group"}
SYNONYMS = {"kis": "korea", "ki&s": "korea", "nhi": "nh", "securitas": "sekuritas", "nvestment": "investment",
            "singapore": "singapore", "싱가폴": "singapore"}


def tokens(name):
    """법인명에서 브랜드·국가 등 구분력 있는 토큰만 뽑는다."""
    n = (name or "").lower().replace("(", " ").replace(")", " ").replace(",", " ").replace(".", " ")
    out = set()
    for t in re.findall(r"[a-z&]+|[가-힣]+", n):
        t = SYNONYMS.get(t, t)
        if len(t) >= 2 and t not in GENERIC:
            out.add(t)
    return out


INSTRUMENT = re.compile(r"\s*(\((c|r|rc)ps\)|\brc?ps\b|보통주|우선주)\s*", re.I)


def clean_holding_name(name):
    """'XXX(CPS)', 'XXX 보통주' 같은 증권 종류 표기를 떼어 낸다."""
    return re.sub(r"\s+", " ", INSTRUMENT.sub(" ", name or "")).strip()
