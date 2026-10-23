"""API 키 읽기: 환경변수 → 로컬 .env 파일 → (터미널에서 직접 실행할 때만) 화면에 안 보이는 입력창.

키는 코드·저장소에 두지 않는다.
- GitHub Actions: 저장소 Secrets가 환경변수로 들어온다. CI에서는 절대 묻지 않는다(키가 없으면 그 단계만 건너뜀).
- 내 PC: 환경변수나 저장소 루트의 .env(.gitignore에 들어 있어 커밋되지 않음)에 두거나,
  둘 다 없으면 실행할 때 getpass로 묻는다. 입력한 값은 그 실행 동안 메모리에만 있고 파일에 쓰지 않는다.

사용: from keys import get_key; key = get_key("DART_API_KEY")
"""
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 키 이름 → 입력창에 보일 설명(어디서 발급받는지)
LABELS = {
    "DART_API_KEY": "DART Open API 인증키 (opendart.fss.or.kr에서 발급)",
    "ECOS_API_KEY": "한국은행 ECOS 인증키 (ecos.bok.or.kr에서 발급)",
    "SEC_USER_AGENT": "SEC EDGAR 요청용 '이름 이메일' (키 아님, 비우면 기본값)",
    "LAW_OC": "국가법령정보센터 Open API OC 아이디 (open.law.go.kr에서 신청)",
}


def _dotenv(name):
    """저장소 루트 .env 에서 NAME=값 한 줄을 읽는다(따옴표 허용, 주석·빈 줄 무시)."""
    f = ROOT / ".env"
    if not f.exists():
        return ""
    for line in f.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.strip() == name and not k.strip().startswith("#"):
            return v.strip().strip('"').strip("'")
    return ""


def can_prompt():
    """사람이 터미널에서 직접 실행할 때만 True. CI·파이프·테스트에서는 묻지 않는다."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("GND_NO_PROMPT"):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def get_key(name, label=None):
    """키 값을 돌려준다. 없으면 빈 문자열(호출한 스크립트는 그 단계를 건너뛴다).

    환경변수가 정의돼 있으면(빈 값이어도) 그대로 쓴다. Actions에서 Secret이 없을 때와 테스트가 이 경우다.
    """
    if name in os.environ:
        return os.environ[name].strip()
    value = _dotenv(name)
    if not value and can_prompt():
        value = getpass.getpass(f"{label or LABELS.get(name, name)}\n  {name} 입력(화면에 표시되지 않음, Enter = 건너뜀): ").strip()
    if value:
        os.environ[name] = value  # 같은 실행 안에서 다른 단계가 다시 묻지 않도록(이 프로세스 메모리에만)
    return value
