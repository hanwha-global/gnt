"""해외 매체 기사 중 베트남어·인도네시아어 제목을 한국어로 기계 번역한다(LLM 없음, API 키 없음, 무료).

- Google 번역 무료 주소(translate.googleapis.com, client=gtx)를 쓰고, 실패하면 MyMemory(무료)로 한 번 더 시도한다
- 이미 번역한 제목은 이전 파일에서 가져와 다시 부르지 않는다(실행마다 새 제목만 번역)
- 둘 다 실패하면 번역 없이 둔다: 화면은 원문 제목과 '번역' 링크(Google 번역 페이지)를 보여 준다
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402

GOOGLE = "https://translate.googleapis.com/translate_a/single"
MYMEMORY = "https://api.mymemory.translated.net/get"
LANGS = ("vi", "id")
MAX_CALLS = 150   # 한 번 실행에 새로 번역하는 제목 수 상한(첫 실행·밀린 날도 몇 분 안에 끝나게)
PAUSE = 0.3


def _google(text, sl):
    data = json.loads(net.get(GOOGLE, {"client": "gtx", "sl": sl, "tl": "ko", "dt": "t", "q": text}, retries=2, timeout=15))
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def _mymemory(text, sl):
    data = json.loads(net.get(MYMEMORY, {"q": text, "langpair": f"{sl}|ko"}, retries=2, timeout=15))
    out = (data.get("responseData") or {}).get("translatedText") or ""
    return "" if data.get("responseStatus") not in (200, "200") or "MYMEMORY WARNING" in out.upper() else out


def translate(text, sl):
    """한국어 번역(실패하면 빈 문자열). 결과에 한글이 없으면 번역이 안 된 것으로 본다."""
    for fn in (_google, _mymemory):
        try:
            ko = re.sub(r"\s+", " ", fn(text, sl)).strip()
        except Exception:
            continue
        if re.search(r"[가-힣]", ko):
            return ko
    return ""


def cache_from(*lists):
    """이전에 번역한 제목: {원문: 번역}."""
    return {x["title"]: x["title_ko"] for items in lists for x in items if x.get("title_ko") and x.get("title")}


def add_ko(items, cache, max_calls=MAX_CALLS):
    """베트남어·인도네시아어 제목(lang)에 한국어 번역(title_ko)을 붙인다. 새로 번역한 수를 돌려준다."""
    calls = done = 0
    for x in items:
        if x.get("lang") not in LANGS:
            x.pop("title_ko", None)
            continue
        ko = x.get("title_ko") or cache.get(x["title"])
        if not ko and calls < max_calls:
            calls += 1
            ko = translate(x["title"], x["lang"])
            time.sleep(PAUSE)
            done += bool(ko)
        if ko:
            x["title_ko"] = cache[x["title"]] = ko
    return done
