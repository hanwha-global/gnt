"""디지털자산 규제 탭: 시장별 최근 당국·언론 발표를 모은다(LLM 미사용, 표준 라이브러리만).

- Google News RSS(키 불필요): 시장별 검색어로 최근 30일 기사 제목·링크·매체·날짜
- Federal Register API(키 불필요): 미국 SEC·OCC·재무부·CFTC의 가상자산·스테이블코인 문서

결과는 digital/data/feed.json. 한 소스가 실패해도 그 시장의 이전 결과를 유지한다.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "feed.json"
UA = "HanwhaGlobalNetworkDashboard/1.0 (github.com/jeongpilchoi1992-hash/global-network-dashboard)"
KEEP_DAYS = 30
PER_MARKET = 8

# 시장별 검색어: (검색어, 언어/지역). 한국어 기사와 현지·영문 기사를 함께 본다.
QUERIES = {
    "KR": [("디지털자산기본법 OR 스테이블코인 OR 토큰증권 금융위", "ko")],
    "US": [("stablecoin OR crypto SEC OR OCC OR CFTC rule", "en")],
    "JP": [("Japan FSA crypto OR stablecoin regulation", "en"), ("일본 금융청 가상자산", "ko")],
    "VN": [("Vietnam crypto exchange license OR digital asset pilot", "en"), ("베트남 가상자산 거래소 인가", "ko")],
    "SG": [("MAS stablecoin OR digital token regulation Singapore", "en")],
    "ID": [("OJK crypto OR aset kripto OR digital asset regulation Indonesia", "en")],
    "AE": [("ADGM FSRA OR VARA digital assets OR stablecoin", "en"), ("아부다비 ADGM 디지털자산", "ko")],
}
LOCALE = {"ko": ("ko", "KR", "KR:ko"), "en": ("en-US", "US", "US:en")}
# 제목에 이 중 하나는 있어야 남긴다(무관한 기사 걸러내기).
MUST = ["crypto", "stablecoin", "digital asset", "token", "kripto", "blockchain", "virtual asset", "bitcoin",
        "가상자산", "스테이블", "디지털자산", "토큰", "코인", "블록체인", "암호자산"]


def get(url, retries=3, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def relevant(title):
    t = title.lower()
    return any(k in t for k in MUST)


def parse_rss(xml_bytes, code, now):
    """Google News RSS → [{date,title,src,url,code}] (KEEP_DAYS 이내, 관련 기사만)."""
    items = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(f" - {src}"):
            title = title[: -len(src) - 3].strip()
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if not title or not link or now - dt > timedelta(days=KEEP_DAYS) or not relevant(title):
            continue
        items.append({"date": dt.date().isoformat(), "title": title, "src": src or "Google News", "url": link, "code": code})
    return items


def google_news(q, lang):
    hl, gl, ceid = LOCALE[lang]
    qs = urllib.parse.urlencode({"q": f"{q} when:{KEEP_DAYS}d", "hl": hl, "gl": gl, "ceid": ceid})
    return get(f"https://news.google.com/rss/search?{qs}")


def federal_register(now):
    since = (now - timedelta(days=KEEP_DAYS)).date().isoformat()
    params = [("conditions[term]", "stablecoin OR crypto asset OR digital asset"),
              ("conditions[publication_date][gte]", since), ("order", "newest"), ("per_page", "20")]
    for a in ["securities-and-exchange-commission", "comptroller-of-the-currency", "treasury-department",
              "commodity-futures-trading-commission"]:
        params.append(("conditions[agencies][]", a))
    data = json.loads(get("https://www.federalregister.gov/api/v1/documents.json?" + urllib.parse.urlencode(params)))
    out = []
    for d in data.get("results", []):
        agency = ", ".join(a.get("name", "") for a in d.get("agencies", []) if a.get("name"))
        out.append({"date": d["publication_date"], "title": d["title"], "src": f"Federal Register · {d.get('type', '')} · {agency}",
                    "url": d["html_url"], "code": "US", "official": True})
    return out


def dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: (x.get("official", False), x["date"]), reverse=True):
        key = it["title"].lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def main():
    now = datetime.now(timezone.utc)
    prev = {}
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8")).get("markets", {})
    markets, errors = {}, []
    for code, qs in QUERIES.items():
        got, ok = [], False
        for q, lang in qs:
            try:
                got += parse_rss(google_news(q, lang), code, now)
                ok = True
            except Exception as e:  # 한 소스 실패는 전체 실패가 아님
                errors.append(f"{code} news: {e}")
        if code == "US":
            try:
                got += federal_register(now)
                ok = True
            except Exception as e:
                errors.append(f"US federal register: {e}")
        markets[code] = dedupe(got)[:PER_MARKET] if ok else prev.get(code, [])
    total = sum(len(v) for v in markets.values())
    if total == 0 and prev:
        print("수집 0건: 이전 feed.json 유지", errors)
        return 0
    OUT.write_text(json.dumps({"updated": now.isoformat(timespec="seconds"), "keep_days": KEEP_DAYS,
                               "errors": errors, "markets": markets}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"feed.json: {total}건", "/ 오류: " + "; ".join(errors) if errors else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
