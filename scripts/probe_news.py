"""임시 조사용(커밋하지 않음): Google News RSS 원자료를 거르지 않고 _probe/raw.json 에 모은다."""
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402
import fetch_hub_news as H  # noqa: E402
from fetch_news import ENGLISH  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_probe" / "raw.json"
KST = timezone(timedelta(hours=9))
ED = {"ko": ("ko", "KR", "KR:ko"), "en": ("en-US", "US", "US:en"), "vi": ("vi", "VN", "VN:vi"), "id": ("id", "ID", "ID:id"),
      "en-sg": ("en-SG", "SG", "SG:en"), "en-in": ("en-IN", "IN", "IN:en")}


def url(q, ed, window):
    hl, gl, ceid = ED[ed]
    qq = q
    if window == "1y":
        qq += " when:365d"
    elif window == "5yw":
        qq += " when:1825d"
    elif window == "5ya":
        qq += " after:" + (datetime.now(KST) - timedelta(days=1826)).strftime("%Y-%m-%d")
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": qq, "hl": hl, "gl": gl, "ceid": ceid})


LEGAL = re.compile(r"\b(?:pt\.?|jsc|joint\s*stock\s*company|corporation|corp\.?|co\.,?|company|limited|ltd\.?|inc\.?|llc|llp|pte\.?|private|s\.a\.|cctvm|ltda\.?|utsk)(?=\s|$|,|\.)", re.I)


def local_name(n):
    if re.search(r"[가-힣]", n):
        return ""
    n = LEGAL.sub(" ", n)
    n = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", n)
    n = re.sub(r"([a-z])([A-Z])", r"\1 \2", n)
    n = re.sub(r"\(.*?\)", " ", n)
    n = LEGAL.sub(" ", n)
    return re.sub(r"[\s,.]+$", "", re.sub(r"\s+", " ", n)).strip()


def main():
    cons = json.loads((ROOT / "site/data/domestic/consolidated.json").read_text(encoding="utf-8"))["firms"]
    seed = json.loads((ROOT / "site/data/domestic/seed.json").read_text(encoding="utf-8"))["entities"]
    ents = {}
    for firm, c in cons.items():
        for x in c.get("overseas", []):
            if x.get("class") in ("영업법인", "지주회사"):
                ents.setdefault((firm, x["country"]), set()).add(x["name"])
    for e in seed:
        if e.get("name") and e["kind"] == "법인" and e["status"] == "운영" and e.get("country"):
            ents.setdefault((e["firm"], e["country"]), set()).add(e.get("dart_name") or e["name"])
    jobs = []
    for firm, country in H.hubs():
        key = f"{firm}|{country}"
        for q, lang in H.queries(firm, country):
            for w in ("1y", "none", "5yw", "5ya"):
                jobs.append((key, q, lang, w))
        names = sorted({local_name(n) for n in ents.get((firm, country), ())} - {""})
        for n in names:
            jobs.append((key, f'"{n}"', "en", "none"))
            if country == "베트남":
                jobs.append((key, f'"{n}"', "vi", "none"))
            if country == "인도네시아":
                jobs.append((key, f'"{n}"', "id", "none"))
            if country == "싱가포르":
                jobs.append((key, f'"{n}"', "en-sg", "none"))
            if country == "인도":
                jobs.append((key, f'"{n}"', "en-in", "none"))
        if country == "베트남" and firm in ENGLISH:
            brand = re.sub(r"\s*(?:&\s*)?(?:Investment\s*&\s*)?Securities$", "", ENGLISH[firm]).strip()
            jobs.append((key, f'"Chứng khoán {brand}"', "vi", "none"))
    for q, ed in [("Korean brokerage Vietnam", "en"), ("Korean brokerage Indonesia", "en"), ('"Korean securities" overseas', "en"),
                  ("Korean securities firm acquisition", "en"), ("công ty chứng khoán Hàn Quốc", "vi"), ("sekuritas Korea Selatan", "id"),
                  ("Korean broker Singapore", "en-sg"), ("Korean brokerage Hong Kong", "en"), ("Korean brokerage US", "en")]:
        for w in ("1y", "none"):
            jobs.append(("_feed", q, ed, w))
    raw, errors = [], []
    for i, (key, q, ed, w) in enumerate(jobs):
        try:
            xml = net.get(url(q, ed, w), timeout=25)
            for it in ET.fromstring(xml).iter("item"):
                try:
                    when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST).strftime("%Y-%m-%d")
                except Exception:
                    when = ""
                raw.append({"k": key, "q": q, "ed": ed, "w": w, "t": (it.findtext("title") or "").strip(),
                            "s": (it.findtext("source") or "").strip(), "su": (it.find("source").get("url") if it.find("source") is not None else ""),
                            "d": when, "u": (it.findtext("link") or "").strip()})
        except Exception as e:
            errors.append(f"{key} {q} {ed} {w}: {e}"[:200])
        time.sleep(0.3)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"at": datetime.now(KST).isoformat(timespec="minutes"), "jobs": len(jobs), "errors": errors, "raw": raw},
                              ensure_ascii=False), encoding="utf-8")
    print(f"jobs {len(jobs)} raw {len(raw)} errors {len(errors)}")


if __name__ == "__main__":
    sys.exit(main())
