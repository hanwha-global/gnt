"""site/ 와 hanwha/·insight/·digital/·guide/·workflow/(있으면)를 _site/ 로 모으고 데이터 파일을 검증한다."""
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
REQUIRED = ["index.html", "assets/app.js", "assets/styles.css", "assets/theme.css", "data/config.json", "data/domestic/seed.json", "data/global/markets.json"]


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    for part in ("hanwha", "insight", "digital", "guide", "workflow"):  # 다른 스레드가 채우는 탭 폴더
        if (ROOT / part).is_dir():
            shutil.copytree(ROOT / part, OUT / part)
    missing = [p for p in REQUIRED if not (OUT / p).exists()]
    if missing:
        sys.exit(f"필수 파일 없음: {missing}")
    for p in OUT.rglob("*.json"):
        json.loads(p.read_text(encoding="utf-8"))  # 깨진 JSON이면 빌드 실패
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (OUT / "data" / "meta.json").write_text(json.dumps(
        {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": sha}), encoding="utf-8")
    (OUT / ".nojekyll").touch()
    print(f"_site 생성: {sum(1 for _ in OUT.rglob('*') if _.is_file())}개 파일")


if __name__ == "__main__":
    main()
