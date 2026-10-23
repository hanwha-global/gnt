"""regulation.json → summary.json (대시보드 '한눈에 보기' 카드용). 다가오는 일정 순으로 8개."""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAG = {"KR": "🇰🇷", "US": "🇺🇸", "JP": "🇯🇵", "VN": "🇻🇳", "SG": "🇸🇬", "ID": "🇮🇩", "AE": "🇦🇪", "EU": "🇪🇺", "UK": "🇬🇧", "HK": "🇭🇰"}


def build(reg, today):
    names = {m["code"]: m["name"] for m in reg["markets"]}
    primary = set(reg["meta"]["primary"])
    items = []
    for u in sorted(reg["upcoming"], key=lambda x: x["date"]):
        if u["date"] < today or u["code"] not in primary:
            continue
        items.append({"jurisdiction": names[u["code"]], "flag": FLAG.get(u["code"], ""), "title": u["text"],
                      "status": "예정", "date": u["date"][:7] if u.get("approx") else u["date"], "url": u["url"]})
    k = reg["takeaways"][0]["h"] if reg.get("takeaways") else ""
    return {"updated": today, "headline": k, "items": items[:8]}


def main():
    reg = json.loads((ROOT / "data" / "regulation.json").read_text(encoding="utf-8"))
    out = build(reg, date.today().isoformat())
    (ROOT / "data" / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"summary.json: {len(out['items'])}개 항목")


if __name__ == "__main__":
    main()
