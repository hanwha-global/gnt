"""해외 매체 기사 중 베트남어·인도네시아어 제목을 한국어로 기계 번역한다(LLM 없음, API 키 없음, 무료).

- Google 번역 무료 주소(translate.googleapis.com, client=gtx)에 같은 말 제목을 줄바꿈으로 묶어 보낸다(실행마다 몇 번만 부른다)
- Google이 막히면 그 실행 동안은 MyMemory(무료)로 한 건씩 번역하고, 다음 실행에서 Google로 다시 번역해 바꾼다
- 이미 번역한 제목은 이전 파일에서 가져와 다시 부르지 않는다(실행마다 새 제목만 번역)
- 둘 다 실패하면 번역 없이 둔다: 화면은 원문 제목과 '번역' 링크(Google 번역 페이지)를 보여 준다
- 영문 약자 회사 이름이 일반 낱말로 번역되지 않게 업종 낱말을 영어로 바꿔 보낸다(Chứng khoán NH → NH Securities: NH를 은행 약자로 읽지 않게)
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
MAX_NEW = 150     # 한 번 실행에 새로 번역하는 제목 수 상한(첫 실행·밀린 날도 몇 분 안에 끝나게)
CHUNK = 1500      # Google에 한 번에 묶어 보내는 글자 수(주소 길이 제한 안쪽)
PAUSE = 0.3
MM = "MyMemory"   # ko_by: MyMemory로 번역한 제목(Google이 되면 다시 번역)
# 'Chứng khoán NH'(NH를 은행 약자 Ngân hàng으로 읽음)처럼 영문 약자 회사 이름. 거래소·감독당국·지명 약자는 그대로 둔다
VI_FIRM = re.compile(r"Chứng [Kk]hoán ([A-Z]{2,6})(?![\w.])")
VI_NOT_FIRM = {"VN", "TP", "HCM", "TPHCM", "HN", "SSC", "HOSE", "HNX", "VSD", "VSDC", "IPO", "ETF", "UBCK", "UBCKNN", "MSCI", "FTSE"}
ID_FIRM = re.compile(r"(\b[A-Z][\w&.-]*) Sekuritas\b")


def _prep(text, sl):
    """번역에 보낼 제목: 회사 이름의 업종 낱말을 영어로(Chứng khoán NH → NH Securities, Kiwoom Sekuritas → Kiwoom Securities)."""
    text = re.sub(r"\s+", " ", text).strip()
    if sl == "vi":
        return VI_FIRM.sub(lambda m: m.group(0) if m.group(1) in VI_NOT_FIRM else f"{m.group(1)} Securities", text)
    if sl == "id":
        return ID_FIRM.sub(r"\1 Securities", text)
    return text


def _hangul(ko):
    """번역 결과. 한글이 없으면 번역이 안 된 것으로 보고 빈 문자열."""
    ko = re.sub(r"\s+", " ", ko or "").strip()
    return ko if re.search(r"[가-힣]", ko) else ""


def _google(texts, sl):
    """같은 말 제목 여러 개를 줄바꿈으로 묶어 한 번에 번역한다. 줄 수가 안 맞으면 None."""
    data = json.loads(net.get(GOOGLE, {"client": "gtx", "sl": sl, "tl": "ko", "dt": "t", "q": "\n".join(texts)},
                              retries=2, timeout=20))
    lines = "".join(seg[0] for seg in data[0] if seg and seg[0]).split("\n")
    if len(texts) == 1:
        lines = [" ".join(lines)]
    return [_hangul(k) for k in lines] if len(lines) == len(texts) else None


def _mymemory(text, sl):
    data = json.loads(net.get(MYMEMORY, {"q": text, "langpair": f"{sl}|ko"}, retries=2, timeout=15))
    out = (data.get("responseData") or {}).get("translatedText") or ""
    return "" if data.get("responseStatus") not in (200, "200") or "MYMEMORY WARNING" in out.upper() else _hangul(out)


def _chunks(texts, size=CHUNK):
    chunk = []
    for t in texts:
        if chunk and len("\n".join(chunk + [t])) > size:
            yield chunk
            chunk = []
        chunk.append(t)
    if chunk:
        yield chunk


def _google_list(texts, sl, st):
    """Google 번역 목록(안 된 줄은 ""). 한 번 막히면(429 등) 이 실행 동안은 다시 부르지 않는다."""
    if st["google_err"]:
        return [""] * len(texts)
    try:
        kos = _google([_prep(t, sl) for t in texts], sl)
    except Exception as e:
        st["google_err"] = str(e)[:120]
        return [""] * len(texts)
    finally:
        time.sleep(PAUSE)
    if kos is None:          # 묶음의 줄 수가 안 맞으면 한 건씩
        return [_google_list([t], sl, st)[0] for t in texts]
    return kos


def _mymemory_one(text, sl):
    try:
        return _mymemory(_prep(text, sl), sl)
    except Exception:
        return ""
    finally:
        time.sleep(PAUSE)


def cache_from(*lists):
    """이전에 번역한 제목: {원문: (번역, 출처)}. 같은 제목이면 Google 번역(출처 None)을 먼저 쓴다."""
    out = {}
    for items in lists:
        for x in items:
            if x.get("title") and x.get("title_ko") and out.get(x["title"], ("", MM))[1]:
                out[x["title"]] = (x["title_ko"], x.get("ko_by"))
    return out


def _known(x, cache):
    """이미 있는 번역 (번역, 출처): 기사에 붙은 것과 이전 파일 것 중 Google 번역을 먼저."""
    own = (x["title_ko"], x.get("ko_by")) if x.get("title_ko") else None
    return min(filter(None, (own, cache.get(x["title"]))), key=lambda k: bool(k[1]), default=("", None))


def _put(x, ko, by):
    x["title_ko"] = ko
    if by:
        x["ko_by"] = by
    else:
        x.pop("ko_by", None)


def add_ko(items, cache, max_new=MAX_NEW):
    """베트남어·인도네시아어 제목(lang)에 한국어 번역(title_ko)을 붙인다. 새로 번역한 수를 돌려준다.

    번역이 없는 제목을 먼저, 그다음 MyMemory로 번역해 둔 제목(Google로 다시)을 한 번에 max_new건까지 보낸다.
    """
    new, redo = {}, {}
    for x in items:
        if x.get("lang") not in LANGS:
            x.pop("title_ko", None)
            x.pop("ko_by", None)
            continue
        ko, by = _known(x, cache)
        if ko:
            _put(x, ko, by)
            cache[x["title"]] = (ko, by)
        if not ko or by:
            (redo if ko else new).setdefault(x["title"], x["lang"])
    todo = list({**new, **redo}.items())[:max_new]
    st = {"google_err": "", "google": 0, "mm": 0, "fail": 0}
    for sl in LANGS:
        for chunk in _chunks([t for t, lang in todo if lang == sl]):
            for t, ko in zip(chunk, _google_list(chunk, sl, st)):
                by = None
                if not ko and t in new:   # Google이 안 되면 새 제목만 MyMemory로(MyMemory 번역이 있는 제목은 그대로)
                    ko, by = _mymemory_one(t, sl), MM
                if ko:
                    cache[t] = (ko, by)
                    st["mm" if by else "google"] += 1
                else:
                    st["fail"] += t in new
    for x in items:
        if x.get("lang") in LANGS and x["title"] in cache:
            _put(x, *cache[x["title"]])
    if todo:
        print(f"번역: Google {st['google']}건 · MyMemory {st['mm']}건 · 실패 {st['fail']}건"
              + (f" · 남은 제목 {len(new) + len(redo) - len(todo)}건은 다음 실행" if len(new) + len(redo) > len(todo) else "")
              + (f" · Google 오류: {st['google_err']}" if st["google_err"] else ""))
    return sum(1 for t in new if t in cache)
