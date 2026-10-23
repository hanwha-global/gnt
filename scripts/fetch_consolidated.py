"""증권사별 해외 종속회사 전수 목록: 최근 사업보고서 'I. 회사의 개요 > 연결대상 종속회사 현황' 표를 읽는다(DART, LLM 미사용).

타법인출자현황은 직접 출자만, 종속기업 요약재무정보는 회사마다 범위가 달라 빠지는 법인이 생긴다.
연결대상 종속회사 현황은 손자회사까지 모든 종속회사를 상호·주소·주요사업·자산총액과 함께 싣는다.
여기서 소재지가 해외인 법인을 모으고, 주요사업과 상호로 아래처럼 나눈다.

  영업법인   증권·자산운용·투자자문·IB·리서치·IT 등 금융서비스를 영위(네트워크 개수에 포함)
  지주회사   다른 해외법인 지분을 보유하는 중간지주(holdings, 개수에는 포함하되 표시)
  제외       펀드·신탁·투자조합·SPC/SPV·부동산·호텔·프로젝트 회사 등 투자기구

결과: site/data/domestic/consolidated.json (회사별 목록과 분류, 사업보고서 접수번호)
비상장사(신한·KB·하나 등)는 이 표를 생략하므로 연결재무제표 주석의 '종속기업 현황' 표를 읽고,
사업보고서가 없는 회사(토스증권)는 연결감사보고서의 같은 주석을 읽는다.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402
from fetch_sub_fin import audit_report, document_texts, tables, to_num  # noqa: E402
from gnd import FUND_BIZ, FUND_NAME, guess_country  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "site" / "data" / "domestic"
OUT = DATA / "consolidated.json"

# 주소에서 나라를 찾는다(영문·한글). 한국 주소는 국내
ADDRESS_COUNTRY = [
    (r"^한국$|^국내$|korea|대한민국|서울|경기|부산|인천|대구|대전|광주|울산|세종|제주|강원|충청|전라|경상|여의도", "한국"),
    (r"hong ?kong|홍콩|kowloon|구룡", "홍콩"),
    (r"singapore|싱가포르|싱가폴", "싱가포르"),
    (r"viet ?nam|베트남|ho chi minh|hanoi|하노이|호치민", "베트남"),
    (r"indonesia|인도네시아|jakarta|자카르타", "인도네시아"),
    (r"mongolia|몽골|ulaanbaatar", "몽골"),
    (r"india\b|인도(?!네시아)|mumbai|뭄바이|delhi|bangalore|bengaluru", "인도"),
    (r"united kingdom|\buk\b|london|런던|영국|england", "영국"),
    (r"greece|그리스|athens|marousi", "그리스"),
    (r"brazil|brasil|브라질|sao paulo|são paulo", "브라질"),
    (r"japan|일본|tokyo|도쿄|동경", "일본"),
    (r"china|중국|beijing|북경|베이징|shanghai|상해|상하이|shenzhen|심천|선전|guangzhou|광저우", "중국"),
    (r"u\.?s\.?a|united states|미국|new york|뉴욕|delaware|델라웨어|california|캘리포니아|hawaii|하와이|texas|"
     r"illinois|chicago|new jersey|massachusetts|boston|san francisco|los angeles|washington|nevada|florida|georgia|"
     r"connecticut|virginia|colorado|wilmington", "미국"),
    (r"cayman|케이만", "케이맨제도"),
    (r"british virgin|\bbvi\b|버진", "영국령버진아일랜드"),
    (r"luxembourg|룩셈부르크", "룩셈부르크"),
    (r"ireland|아일랜드|dublin", "아일랜드"),
    (r"netherlands|네덜란드|amsterdam", "네덜란드"),
    (r"germany|독일|frankfurt", "독일"),
    (r"france|프랑스|paris", "프랑스"),
    (r"spain|스페인|madrid", "스페인"),
    (r"italy|이탈리아|milan", "이탈리아"),
    (r"australia|호주|sydney|melbourne", "호주"),
    (r"canada|캐나다|toronto|vancouver", "캐나다"),
    (r"thailand|태국|bangkok", "태국"),
    (r"cambodia|캄보디아|phnom penh", "캄보디아"),
    (r"kazakhstan|카자흐|almaty|astana", "카자흐스탄"),
    (r"u\.?a\.?e|united arab|아랍에미리트|abu dhabi|아부다비|dubai|두바이", "아랍에미리트"),
    (r"saudi|사우디", "사우디아라비아"),
    (r"malaysia|말레이시아|kuala lumpur", "말레이시아"),
    (r"philippines|필리핀|manila", "필리핀"),
    (r"taiwan|대만|taipei", "대만"),
    (r"mauritius|모리셔스", "모리셔스"),
    (r"marshall|마셜", "마셜제도"),
    (r"bermuda|버뮤다", "버뮤다"),
    (r"jersey|guernsey|저지", "채널제도"),
]
# 영업법인으로 보는 업종(주요사업 칸)과 상호. '투자업'만으로는 투자기구와 구별이 안 돼 상호도 함께 본다
STRONG_BIZ = re.compile(r"증권|금융투자업|중개|위탁매매|고유재산|자산운용|집합투자업|투자자문|투자일임|여신|기타금융|선물|"
                        r"broker|securities|asset management|advis|it\s?서비스|it\(|핀테크|정보제공|소프트웨어|시스템", re.I)
STRONG_NAME = re.compile(r"securit|sekuritas|asset management|investment management|capital markets|partners|advis|"
                         r"financial services|broker|trading|technology|증권|자산운용|투자자문|선물|futures", re.I)
HOLD = re.compile(r"지주|holding|홀딩", re.I)
EXCLUDE_BIZ = re.compile(r"부동산|임대|호텔|숙박|리조트|골프|개발|건설|프로젝트|발전|에너지|태양광|풍력|자원|광업|선박|항공기|교육|"
                         r"real estate|property|hotel|resort|energy|power|solar|wind|shipping|aircraft|수익증권|집합투자증권|"
                         r"특수목적|spc|spv|유동화|투자기구|사모|조합|신탁|펀드|fund|trust", re.I)
VEHICLE_NAME = re.compile(r"\breit\b|\bjv\b|owner llc|propert|realty|hotel|\bbvi\b|funding", re.I)
DORMANT = re.compile(r"휴면|청산|dormant|liquidat", re.I)
OFFSHORE = {"케이맨제도", "영국령버진아일랜드", "버뮤다", "마셜제도", "채널제도"}
BIZ_ONLY = re.compile(r"^[가-힣\s,·및]+(업|중개|매매)$|^(교육|휴면|기타|홍콩|미국|영국|인도|싱가포르)$")  # 상호 칸에 업종이 밀려 들어온 행


def classify(name, biz, country=None):
    """('영업법인'|'지주회사'|'제외', 사유). 규칙은 화면 주석과 같다."""
    biz = biz or ""
    if FUND_NAME.search(name or "") or FUND_BIZ.search(biz):
        return "제외", "펀드·신탁·투자기구"
    if DORMANT.search(biz):
        return "제외", f"휴면·청산({biz[:12]})"
    if EXCLUDE_BIZ.search(biz) and not re.search(r"증권|자산운용|securit|asset management", biz, re.I):
        return "제외", f"투자기구·비금융({biz[:20]})"
    if VEHICLE_NAME.search(name or ""):
        return "제외", "부동산·SPV 법인"
    if country in OFFSHORE and not re.search(r"위탁매매|중개|broker|자산운용", biz, re.I):
        return "제외", f"역외 투자기구({country})"
    if HOLD.search(f"{name} {biz}") and not re.search(r"증권업|자산운용업|브로커|위탁매매", biz, re.I):
        return "지주회사", None
    if STRONG_BIZ.search(biz) or STRONG_NAME.search(name or ""):
        return "영업법인", None
    return "제외", f"업종 불명({(biz or '-')[:20]})"


def clean_name(name):
    n = re.sub(r"\s*(\(\*\d*\)|\(주\d*\)|㈜|\(주석\d*\))\s*", "", name or "")
    return re.sub(r"\s*\(구[,.]?\s*[^)]*\)", "", n).strip()


SUFFIXES = ("jointstockcompany", "privatelimited", "corporation", "company", "limited", "ltda", "ltd", "inc", "llc", "llp",
            "pte", "plc", "jsc", "corp", "co", "sa")


def key_name(name):
    """같은 법인을 다르게 쓴 표기(대소문자·띄어쓰기·법인 형태·약칭 괄호)를 하나로 본다. 나라와 함께 쓴다."""
    n = clean_name(name).lower().replace("&", "and")
    n = re.sub(r"\((bsc|kisi|ptsv|ptss)\)", "", n)
    n = re.sub(r"[^0-9a-z가-힣]+", "", n)
    n = re.sub(r"^pt", "", n)
    changed = True
    while changed:
        changed = False
        for suf in SUFFIXES:
            if n.endswith(suf) and len(n) > len(suf) + 4:
                n, changed = n[: -len(suf)], True
    return n


def name_country(name, fallback):
    """상호 괄호 안 지명(예: '(Shenzhen)')이 주소와 다르면 상호를 따른다."""
    for place in re.findall(r"\(([^)]+)\)", name or ""):
        c = guess_country(place)
        if c:
            return c
    return fallback


def seed_match(seeds, name, country):
    """기준 데이터 법인과 같은 법인: 같은 나라에서 정규화 이름이 같거나, 한쪽이 다른 쪽으로 시작(12자 이상)."""
    k = key_name(RENAMED.get(name, name))
    same = [s for s in seeds if s["country"] == country]
    exact = [s for s in same if key_name(s["name"]) == k]
    if len(exact) == 1:
        return exact[0]["name"]
    pre = [s for s in same if len(min(k, key_name(s["name"]), key=len)) >= 12
           and (key_name(s["name"]).startswith(k) or k.startswith(key_name(s["name"])))]
    if len(pre) == 1:
        return pre[0]["name"]
    # 원자료 나라가 다르게 적힌 경우(예: 홍콩 ↔ 영국령버진아일랜드)는 이름이 완전히 같을 때만
    anywhere = [s for s in seeds if key_name(s["name"]) == k]
    return anywhere[0]["name"] if len(anywhere) == 1 else None


def finalize(subs, seeds=()):
    """해외 법인만 남기고, 같은 법인(주석 표·개요 표 중복)은 개요 표 값으로 합친 뒤 분류한다."""
    merged = {}
    for s in subs:
        name = clean_name(s["name"])
        if not name or BIZ_ONLY.search(name):
            continue
        c = name_country(name, s.get("country") or guess_country(name))
        if c in (None, "한국"):
            continue
        k = (key_name(name), c)
        cur = merged.get(k)
        row = {**s, "name": name, "country": c}
        if cur is None:
            merged[k] = row
        else:  # 개요 표(list)는 자산총액·주소가 있어 우선, 빈 칸은 다른 표로 채운다
            first, second = (row, cur) if row.get("table") == "list" and cur.get("table") != "list" else (cur, row)
            merged[k] = {**{x: v for x, v in second.items() if v not in (None, "", "-")},
                         **{x: v for x, v in first.items() if v not in (None, "", "-")}, "table": "list+note"}
    out = []
    for row in merged.values():
        cls, why = classify(row["name"], row.get("business"), row["country"])
        sn = seed_match(seeds, row["name"], row["country"])
        out.append({**row, "class": cls, "why": why, "seed_name": sn})
    return out


# 사명 변경으로 이름만으로는 이어지지 않는 법인(공시·보도자료 확인분)
RENAMED = {"GTX UK LLP": "Goldenberg Hehmeyer LLP", "GTX EU Investment Services S.A.": "GHCO Europe Investment Services S.A."}


NAME_HEAD = ("상호", "회사명", "법인명", "피투자회사", "종속기업명", "종속회사명", "기업명")
BIZ_HEAD = ("주요사업", "업종", "사업내용", "주요영업")


def _header(rows):
    for i, r in enumerate(rows[:3]):
        h = [c.replace(" ", "") for c in r]
        if any(any(k in c for k in NAME_HEAD) for c in h) and any(any(k in c for k in BIZ_HEAD) for c in h):
            return i, h
    return None, None


def row_country(r, addr_i):
    """주소 칸이 있으면 그 칸, 없으면 행의 모든 칸에서 나라를 찾는다(소재지 칸이 병합 셀로 밀려도 잡힌다)."""
    cells = ([r[addr_i]] if addr_i is not None and 0 <= addr_i < len(r) else []) + r
    for c in cells:
        for pat, country in ADDRESS_COUNTRY:
            if re.search(pat, (c or "").lower(), re.I):
                return country
    return None


def parse_consolidated(texts):
    """종속회사 목록 표 → [{name, established, address, business, assets(백만원), control, major, country, table}].

    두 가지 표를 읽는다.
      list  사업보고서 'I. 회사의 개요' 연결대상 종속회사 현황(상세): 상장사가 싣는다(손자회사·주소·자산총액 포함)
      note  연결재무제표 주석 '종속기업 현황': 비상장사(신한·KB·하나 등)와 감사보고서도 싣는다(소재지·업종)
    같은 이름은 처음 나온 값을 쓴다(list 표가 문서 앞쪽에 있다).
    """
    rows_out, seen = [], set()
    for text in texts:
        for before, rows in tables(text):
            if len(rows) < 2:
                continue
            hi, h = _header(rows)
            if hi is None:
                continue
            ctx = before[-300:] + " " + " ".join(rows[0])
            if not re.search(r"연결대상|종속회사|종속기업", ctx) or re.search(r"관계기업|공동기업", before[-120:]) and "종속" not in before[-120:]:
                continue
            kind = "list" if "주요종속" in "".join(h) or "자산총액" in "".join(h) else "note"
            col = lambda *ks: next((i for i, c in enumerate(h) if any(k in c for k in ks)), None)  # noqa: E731
            ci = {"name": next(i for i, c in enumerate(h) if any(k in c for k in NAME_HEAD) and "투자회사" != c),
                  "est": col("설립일"), "addr": col("주소", "소재지", "소재국"), "biz": col(*BIZ_HEAD),
                  "assets": col("자산총액"), "ctrl": col("지배관계"), "major": col("주요종속")}
            unit = 1e-6 if re.search(r"단위\s*[:：]?\s*원\b", before[-200:]) else 1e-3 if "천원" in before[-200:] else 1
            for r in rows[hi + 1:]:
                if len(r) < 3:
                    continue
                # 병합 셀: 칸이 모자라면(앞쪽 '투자회사' 칸 생략) 왼쪽으로, 많으면(지분율 당기·전기) 그대로 읽는다
                shift = max(0, len(h) - len(r))
                g = lambda k: None if ci[k] is None or not (0 <= ci[k] - shift < len(r)) else r[ci[k] - shift]  # noqa: E731
                name = re.sub(r"\(\*\d+\)|\(주\d+\)", "", g("name") or "").strip()
                if not name or re.search(r"^(합계|소계|계|합 계|당기말|전기말|-)$", name) or name in seen or to_num(name) is not None:
                    continue
                seen.add(name)
                a = to_num(g("assets"))
                rows_out.append({"name": name, "established": g("est"), "address": g("addr"), "business": g("biz"),
                                 "assets": None if a is None else round(a * unit, 1), "control": g("ctrl"), "major": g("major"),
                                 "country": row_country(r, None if ci["addr"] is None else ci["addr"] - shift), "table": kind})
    return rows_out


def seed_by_firm():
    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    out = {}
    for e in seed["entities"]:
        if e.get("name"):
            out.setdefault(e["firm"], []).append({"name": e["name"], "country": e["country"]})
    return out


def reclassify():
    """저장된 목록을 규칙만 바꿔 다시 분류한다(DART 호출 없음)."""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    seeds = seed_by_firm()
    for firm, v in data["firms"].items():
        v["overseas"] = finalize(v["overseas"], seeds.get(firm, []))
        report(firm, v)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def report(firm, v):
    overseas = v["overseas"]
    n = {k: sum(1 for x in overseas if x["class"] == k) for k in ("영업법인", "지주회사", "제외")}
    print(f"{firm}: 종속회사 {v['total']} · 해외 {len(overseas)} (영업 {n['영업법인']}, 지주 {n['지주회사']}, 제외 {n['제외']})")
    for x in overseas:  # 대사용으로 항상 찍는다(공시 원문 내용, 키·개인정보 없음)
        print(f"   [{x['class']}] {x['name']} | {x['country']} | {(x.get('business') or '')[:30]} | {x.get('assets')} | {x.get('table')}"
              f" | {x.get('why') or ''} | seed={x.get('seed_name')}")


def main():
    if "--reclassify" in sys.argv:
        return reclassify()
    key = get_key("DART_API_KEY")
    if not key:
        print("DART_API_KEY 없음: consolidated.json 갱신 건너뜀")
        return 0
    dart = json.loads((DATA / "dart_latest.json").read_text(encoding="utf-8"))
    seeds = seed_by_firm()
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"firms": {}}
    result = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": "DART 사업보고서 연결대상 종속회사 현황·연결재무제표 주석 종속기업 현황(감사보고서 포함)", "firms": {}, "errors": []}
    for firm, d in dart.get("firms", {}).items():
        rep = d.get("financials_annual_report") or (d.get("corp_code") and audit_report(key, d["corp_code"]))
        if not rep:
            result["errors"].append(f"{firm}: 사업보고서·감사보고서 없음")
            continue
        try:
            subs = parse_consolidated(document_texts(key, rep["rcept_no"]))
        except Exception as e:  # 한 회사가 실패해도 나머지는 계속
            result["errors"].append(f"{firm}: {e}")
            subs = []
        if not subs:
            if firm in prev.get("firms", {}):
                result["firms"][firm] = prev["firms"][firm]
            result["errors"].append(f"{firm}: 연결대상 종속회사 현황 표를 못 찾음")
            continue
        overseas = finalize(subs, seeds.get(firm, []))
        result["firms"][firm] = {"report": rep["label"], "rcept_no": rep["rcept_no"], "total": len(subs), "overseas": overseas}
        report(firm, result["firms"][firm])
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
