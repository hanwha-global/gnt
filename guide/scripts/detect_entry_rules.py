"""국가별 해외진출 유의사항: 감독당국 공식 발표 자동 감지(LLM 미사용, 표준 라이브러리만).

나라마다 감독당국·정부 공식 도메인에서 나온 발표 중 진입 규제(외국인 지분, 인가, 자본금, 증권사 규정 등)
키워드가 걸린 것만 모아 guide/data/detected.json 에 쌓는다(Google News RSS 의 site: 검색, 키 불필요).

- 화면은 countries.json 의 요약(사람이 쓴 것)을 그대로 두고, 그 나라 검증일 이후 공식 발표가 있으면 '신규 공식 발표' 표시를 붙인다.
- 나라별 auto_checked 는 마지막으로 정상 조회한 날짜다. 조회가 실패하면 이전 값을 유지한다.
"""
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "scripts"))
from net import get  # noqa: E402

OUT = ROOT / "data" / "detected.json"
KEEP_DAYS = 180
LOOKBACK = 14

# 나라별 공식 도메인(감독당국·정부). 기사 출처가 이 도메인이어야만 남긴다. KR 은 한국 측 공통 절차용.
OFFICIAL = {
    "KR": ["fsc.go.kr", "fss.or.kr", "moef.go.kr"],
    "VN": ["ssc.gov.vn", "mof.gov.vn", "chinhphu.vn", "baochinhphu.vn"],
    "ID": ["ojk.go.id", "bkpm.go.id", "setneg.go.id"],
    "SG": ["mas.gov.sg"],
    "AE": ["adgm.com", "sca.gov.ae"],
    "US": ["sec.gov", "finra.org"],
    "JP": ["fsa.go.jp"],
    "HK": ["sfc.hk", "info.gov.hk"],
    "CN": ["csrc.gov.cn", "safe.gov.cn", "gov.cn"],
    "GB": ["fca.org.uk"],
    "IN": ["sebi.gov.in", "rbi.org.in", "dpiit.gov.in"],
    "MN": ["frc.mn"],
    "BR": ["bcb.gov.br", "gov.br"],
    "TH": ["sec.or.th"],
    "KH": ["serc.gov.kh"],
}
LANG = {"KR": "ko"}

# 진입 규제 관련 글인지(하나는 있어야 함, 소문자 비교)
ENTRY = ["foreign ownership", "foreign investor", "foreign investment", "foreign shareholding", "licens", "capital requirement",
         "minimum capital", "charter capital", "paid-up capital", "securities compan", "securities firm", "broker", "change in control",
         "controller", "investment firm", "prudential", "kepemilikan asing", "perusahaan efek", "modal", "công ty chứng khoán",
         "vốn điều lệ", "外资", "证券公司", "해외진출", "해외직접투자", "외국환", "현지법인"]


def _hit(text, word):
    if len(word) <= 4 and word.isascii() and word.isalpha():
        return re.search(rf"\b{word}\b", text) is not None
    return word in text


def relevant(title):
    t = title.lower()
    return any(_hit(t, k) for k in ENTRY)


def is_official(code, src_url):
    h = (urllib.parse.urlparse(src_url or "").hostname or "").lower().removeprefix("www.")
    return any(h == d or h.endswith("." + d) for d in OFFICIAL[code])


def parse(xml_bytes, code, now):
    out = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        src_el = it.find("source")
        src_name = (src_el.text or "").strip() if src_el is not None else ""
        src_url = src_el.get("url", "") if src_el is not None else ""
        if src_name and title.endswith(f" - {src_name}"):
            title = title[: -len(src_name) - 3].strip()
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if now - dt > timedelta(days=LOOKBACK) or not is_official(code, src_url) or not relevant(title):
            continue
        out.append({"date": dt.date().isoformat(), "title": title, "url": (it.findtext("link") or "").strip(),
                    "src": src_name or urllib.parse.urlparse(src_url).hostname})
    return out


def search(code):
    ko = LANG.get(code) == "ko"
    hl, gl, ceid = ("ko", "KR", "KR:ko") if ko else ("en-US", "US", "US:en")
    sites = " OR ".join(f"site:{d}" for d in OFFICIAL[code])
    terms = "해외진출 OR 해외직접투자 OR 외국환거래 OR 현지법인" if ko else \
        '"foreign ownership" OR licensing OR "capital requirement" OR "securities company" OR "foreign investor"'
    qs = urllib.parse.urlencode({"q": f"({terms}) ({sites}) when:{LOOKBACK}d", "hl": hl, "gl": gl, "ceid": ceid})
    return get(f"https://news.google.com/rss/search?{qs}")


def merge(prev_items, new_items, now):
    cutoff = (now - timedelta(days=KEEP_DAYS)).date().isoformat()
    seen, out = set(), []
    for it in sorted(new_items + prev_items, key=lambda x: x["date"], reverse=True):
        key = it["title"].lower()[:80]
        if key in seen or it["date"] < cutoff:
            continue
        seen.add(key)
        out.append(it)
    return out


def main():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    prev = json.loads(OUT.read_text(encoding="utf-8")).get("markets", {}) if OUT.exists() else {}
    markets, errors = {}, []
    for code in OFFICIAL:
        p = prev.get(code, {})
        got, ok = [], False
        try:
            got = parse(search(code), code, now)
            ok = True
        except Exception as e:  # 한 나라 실패는 전체 실패가 아님
            errors.append(f"{code}: {e}")
        markets[code] = {"auto_checked": today if ok else p.get("auto_checked"), "items": merge(p.get("items", []), got, now)}
    if prev and not any(m["auto_checked"] == today for m in markets.values()):
        print("모든 소스 조회 실패: 이전 detected.json 유지", errors)
        return 0
    OUT.write_text(json.dumps({"updated": now.isoformat(timespec="seconds"), "keep_days": KEEP_DAYS, "official_domains": OFFICIAL,
                               "errors": errors, "markets": markets}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"detected.json: {sum(len(m['items']) for m in markets.values())}건", "/ 오류: " + "; ".join(errors) if errors else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
