"""내 PC에서 자동 수집을 한 번에 돌린다(GitHub Actions의 update-data.yml과 같은 순서).

시작할 때 필요한 API 키를 한 번만 묻는다. 환경변수나 저장소 루트 .env에 이미 있으면 묻지 않는다.
입력은 화면에 표시되지 않고(getpass), 파일에 저장하지 않으며, 이 실행이 끝나면 사라진다.
키를 비워 두면(Enter) 그 키가 필요한 단계만 건너뛴다.

사용: python scripts/run_local.py            # 전체
      python scripts/run_local.py --only dart # 이름에 dart가 든 단계만
      python scripts/run_local.py --build     # 끝나고 _site 빌드
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# (단계 이름, 실행할 스크립트, 필요한 키)
STEPS = [
    ("dart 해외법인·재무·공시", "scripts/update_dart.py", ["DART_API_KEY"]),
    ("dart 종속회사 전수 목록", "scripts/fetch_consolidated.py", ["DART_API_KEY"]),
    ("dart 해외 종속기업 요약재무(ROE)", "scripts/fetch_sub_fin.py", ["DART_API_KEY"]),
    ("dart 해외법인 5개년 손익 추이", "scripts/fetch_sub_trend.py", ["DART_API_KEY"]),
    ("dart 국내 전체 증권사 자기자본 순위", "scripts/broker_rank.py", ["DART_API_KEY"]),
    ("news 해외진출 뉴스", "scripts/fetch_news.py", []),
    ("news 국가별 매크로 뉴스", "scripts/fetch_macro_news.py", []),
    ("news 해외 거점별 뉴스", "scripts/fetch_hub_news.py", []),
    ("sec 미국 순위", "scripts/update_sec.py", ["SEC_USER_AGENT"]),
    ("listed 해외 상장 증권사 순위", "scripts/update_listed.py", []),
    ("hanwha dart 해외자회사 공시", "hanwha/scripts/fetch_dart_subs.py", ["DART_API_KEY"]),
    ("hanwha 대외보고 기한", "hanwha/scripts/build_deadlines.py", []),
    ("hanwha ecos 매크로", "hanwha/scripts/fetch_macro.py", ["ECOS_API_KEY"]),
    # 위 단계들이 갱신한 공시·지수·환율·뉴스를 읽으므로 맨 끝
    ("news 진출국 전략 Takeaways", "scripts/build_takeaways.py", []),
]


def main():
    ap = argparse.ArgumentParser(description="로컬 자동 수집(API 키는 실행 중 숨김 입력)")
    ap.add_argument("--only", default="", help="이름에 이 글자가 든 단계만 실행(예: dart, news, hanwha)")
    ap.add_argument("--build", action="store_true", help="끝나고 scripts/build_site.py 실행")
    args = ap.parse_args()
    steps = [s for s in STEPS if args.only.lower() in s[0].lower()]
    needed = sorted({k for _, _, ks in steps for k in ks})
    if needed:
        print("필요한 API 키를 입력합니다. 이미 환경변수나 .env에 있으면 묻지 않습니다.\n")
    env = dict(os.environ)
    for k in needed:
        v = get_key(k)
        env[k] = v  # 빈 값이면 하위 스크립트는 묻지 않고 그 단계를 건너뛴다
        print(f"  {k}: {'입력됨' if v else '없음 → 해당 단계 건너뜀'}")
    env["GND_NO_PROMPT"] = "1"  # 하위 스크립트에서 다시 묻지 않게
    failed = []
    for name, script, _ in steps:
        print(f"\n▶ {name} ({script})")
        if subprocess.run([sys.executable, script], cwd=ROOT, env=env).returncode != 0:
            failed.append(name)
    if args.build:
        subprocess.run([sys.executable, "scripts/build_site.py"], cwd=ROOT, env=env)
    print("\n완료" + (f" · 실패 {len(failed)}단계: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
