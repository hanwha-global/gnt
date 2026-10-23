"""regulatory.json에서 30일 안에 돌아오거나 기한이 지난 항목을 골라 GitHub 이슈 본문(Markdown)을 출력한다.

출력이 비어 있으면 알릴 항목이 없다는 뜻이다. 워크플로가 이 본문으로 알림 이슈를 만들거나 고친다.
"""
import datetime as dt
import json
from pathlib import Path

REG = Path(__file__).resolve().parents[1] / "data" / "regulatory.json"
WINDOW = 30


def main():
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    reg = json.loads(REG.read_text(encoding="utf-8"))
    rows = []
    for t in reg["todo"]:
        if t["status"] == "done" or not t.get("due"):
            continue
        d = (dt.date.fromisoformat(t["due"]) - today).days
        if d <= WINDOW:
            rows.append((d, t))
    if not rows:
        return
    print(f"{today} 기준, 30일 안에 돌아오거나 기한이 지난 해외법인 보고 항목입니다.\n")
    print("| 상태 | 기한 | 대상 | 항목 | 근거 |\n|---|---|---|---|---|")
    for d, t in sorted(rows, key=lambda x: x[0]):
        tag = f"🔴 D+{-d}" if d < 0 else f"🟠 D-{d}" if d <= 7 else f"D-{d}"
        print(f"| {tag} | {t['due']} | {t['entity']} | {t['item']} | {t['basis']} |")
    print("\n완료한 항목은 `hanwha/data/regulatory.json`의 `done_ids`에 id를 추가하면 다음 실행부터 빠집니다.")
    print("\n" + ", ".join(f"`{t['id']}`" for _, t in sorted(rows, key=lambda x: x[0])))


if __name__ == "__main__":
    main()
