"""디지털자산 규제 현황 자동 확인(LLM 미사용, 표준 라이브러리만).

시장마다 감독당국·정부 공식 도메인에서 나온 발표만 모아(Google News RSS의 site: 검색 + 미 관보 API),
주제별 키워드로 분류해 digital/data/detected.json 에 쌓는다.

- 화면은 regulation.json 의 현황 문구(사람이 쓴 것)는 그대로 두고,
  그 시장의 사람 검증일 이후 나온 공식 발표가 있으면 해당 주제 칸에 '신규 공식 발표' 표시와 링크를 붙인다.
- 시장별 auto_checked 는 그 시장 공식 소스를 마지막으로 정상 조회한 날짜다. 조회가 실패하면 이전 값을 유지한다.
- 판정(시행/입법 중 등)을 자동으로 바꾸지는 않는다. 키워드 매칭은 법령 상태를 판단할 수 없기 때문이다.
"""
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_feed import federal_register, get  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "detected.json"
KEEP_DAYS = 120   # 감지 이력 보관 기간
LOOKBACK = 14     # 한 번 조회할 때 보는 기간(매일 실행 기준 여유 있게)

# 시장별 공식 도메인(감독당국·중앙은행·정부). 기사 출처가 이 도메인이어야만 남긴다.
OFFICIAL = {
    "KR": ["fsc.go.kr", "fss.or.kr", "korea.kr", "bok.or.kr", "moef.go.kr", "kofiu.go.kr"],
    "US": ["sec.gov", "occ.gov", "treasury.gov", "home.treasury.gov", "cftc.gov", "federalreserve.gov", "fdic.gov", "federalregister.gov", "whitehouse.gov"],
    "JP": ["fsa.go.jp", "boj.or.jp"],
    "VN": ["mof.gov.vn", "ssc.gov.vn", "sbv.gov.vn", "chinhphu.vn", "baochinhphu.vn"],
    "SG": ["mas.gov.sg"],
    "ID": ["ojk.go.id", "bi.go.id", "kemenkeu.go.id"],
    "AE": ["adgm.com", "vara.ae", "centralbank.ae", "sca.gov.ae"],
    "EU": ["esma.europa.eu", "eba.europa.eu", "ecb.europa.eu", "finance.ec.europa.eu"],
    "UK": ["fca.org.uk", "gov.uk", "bankofengland.co.uk"],
    "HK": ["hkma.gov.hk", "sfc.hk", "info.gov.hk"],
}
LANG = {"KR": "ko", "JP": "en", "VN": "en", "ID": "en"}

# 디지털자산 관련 글인지(하나는 있어야 함)
DIGITAL = ["crypto", "stablecoin", "digital asset", "virtual asset", "token", "blockchain", "distributed ledger", "dlt",
           "bitcoin", "e-money token", "fiat-referenced", "mica", "aset kripto", "kripto", "tài sản số", "tài sản mã hóa",
           "가상자산", "디지털자산", "스테이블", "토큰", "암호자산", "블록체인", "코인"]
# 주제별 키워드(소문자 비교). 한 글이 여러 주제에 걸릴 수 있다.
TOPICS = {
    "vasp": ["licen", "exchange", "vasp", "casp", "service provider", "dpt", "dtsp", "vatp", "registration", "사업자", "거래소", "인가", "신고"],
    "stable": ["stablecoin", "stable coin", "e-money token", "fiat-referenced", "payment token", "genius", "스테이블"],
    "sto": ["tokeni", "security token", "digital securit", "tokenized", "토큰증권", "sto", "dlt pilot"],
    "etf": ["etf", "etp", "exchange-traded", "exchange traded", "상장지수"],
    "tax": ["tax", "과세", "세제", "소득세", "pajak", "thuế", "dac8", "1099-da"],
    "aml": ["aml", "anti-money", "money laundering", "travel rule", "sanction", "자금세탁", "트래블룰", "fiu", "외환"],
    "broker": ["broker", "securities firm", "custody", "custodian", "dealer", "증권사", "수탁", "겸영", "금가분리"],
}


def is_official(code, src_url):
    host = urllib.parse.urlparse(src_url or "").hostname or ""
    host = host.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in OFFICIAL[code])


def _hit(text, word):
    # 짧은 영문 약어(sto, etf, aml 등)는 단어 경계로만 찾는다(stock·store 같은 오탐 방지).
    if len(word) <= 4 and word.isascii() and word.isalpha():
        return re.search(rf"\b{word}\b", text) is not None
    return word in text


def classify(title):
    t = title.lower()
    if not any(_hit(t, k) for k in DIGITAL):
        return []
    return [k for k, words in TOPICS.items() if any(_hit(t, w) for w in words)] or ["general"]


def parse_official(xml_bytes, code, now):
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
        if now - dt > timedelta(days=LOOKBACK) or not is_official(code, src_url):
            continue
        topics = classify(title)
        if not topics:
            continue
        out.append({"date": dt.date().isoformat(), "title": title, "url": (it.findtext("link") or "").strip(),
                    "src": src_name or urllib.parse.urlparse(src_url).hostname, "topics": topics})
    return out


def search_official(code):
    lang = LANG.get(code, "en")
    hl, gl, ceid = ("ko", "KR", "KR:ko") if lang == "ko" else ("en-US", "US", "US:en")
    sites = " OR ".join(f"site:{d}" for d in OFFICIAL[code])
    terms = "가상자산 OR 디지털자산 OR 스테이블코인 OR 토큰증권" if lang == "ko" else "crypto OR stablecoin OR \"digital asset\" OR token"
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
            got += parse_official(search_official(code), code, now)
            ok = True
        except Exception as e:  # 한 시장 실패는 전체 실패가 아님
            errors.append(f"{code}: {e}")
        if code == "US":
            try:
                for d in federal_register(now):
                    topics = classify(d["title"])
                    if topics and (now.date() - datetime.strptime(d["date"], "%Y-%m-%d").date()).days <= LOOKBACK:
                        got.append({"date": d["date"], "title": d["title"], "url": d["url"], "src": d["src"], "topics": topics})
                ok = True
            except Exception as e:
                errors.append(f"US federal register: {e}")
        markets[code] = {"auto_checked": today if ok else p.get("auto_checked"),
                         "items": merge(p.get("items", []), got, now)}
    if not any(m["auto_checked"] == today for m in markets.values()) and prev:
        print("모든 소스 조회 실패: 이전 detected.json 유지", errors)
        return 0
    OUT.write_text(json.dumps({"updated": now.isoformat(timespec="seconds"), "keep_days": KEEP_DAYS,
                               "official_domains": OFFICIAL, "errors": errors, "markets": markets},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(m["items"]) for m in markets.values())
    print(f"detected.json: {n}건", "/ 오류: " + "; ".join(errors) if errors else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
