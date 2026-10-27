"""해외 매체 기사 중 베트남어·인도네시아어 제목을 한국어로 기계 번역한다(LLM 없음, API 키 없음, 무료).

- 무료 번역 주소를 차례로 쓴다: Google 번역(translate.googleapis.com, client=gtx) → Microsoft 번역(Edge 브라우저 번역 주소)
  → MyMemory. 앞의 두 곳은 같은 말 제목을 묶어 보내 실행마다 몇 번만 부른다
- GitHub Actions 서버에서는 Google이 자주 막힌다(HTTP 429). 어느 곳이든 한 번 막히면 그 실행 동안은 다시 부르지 않는다
- MyMemory 번역은 숫자 단위(tỷ = 10억 등)를 자주 틀려 예비로만 쓴다(ko_by). 다음 실행에서 Google·Microsoft로 다시 번역해 바꾼다
- 이미 번역한 제목은 이전 파일에서 가져와 다시 부르지 않는다(실행마다 새 제목만 번역)
- 모두 실패하면 번역 없이 둔다: 화면은 원문 제목과 '번역' 링크(Google 번역 페이지)를 보여 준다
- 영문 약자 회사 이름이 일반 낱말로 번역되지 않게 업종 낱말을 영어로 바꿔 보낸다(Chứng khoán NH → NH Securities: NH를 은행 약자로 읽지 않게)
"""
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402

GOOGLE = "https://translate.googleapis.com/translate_a/single"
EDGE_AUTH = "https://edge.microsoft.com/translate/auth"       # 키 없는 임시 토큰(Edge 브라우저 번역 기능이 쓰는 주소)
EDGE = "https://api-edge.cognitive.microsofttranslator.com/translate"
MYMEMORY = "https://api.mymemory.translated.net/get"
LANGS = ("vi", "id")
MAX_NEW = 150     # 한 번 실행에 새로 번역하는 제목 수 상한(첫 실행·밀린 날도 몇 분 안에 끝나게)
CHUNK = 1500      # 한 번에 묶어 보내는 글자 수(주소 길이 제한 안쪽)
PAUSE = 0.3
MM = "MyMemory"   # ko_by: MyMemory로 번역한 제목(예비 번역: 다음 실행에서 다시 번역)
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


def _google(texts, sl, st):
    """같은 말 제목 여러 개를 줄바꿈으로 묶어 한 번에 번역한다. 줄 수가 안 맞으면 None."""
    data = json.loads(net.get(GOOGLE, {"client": "gtx", "sl": sl, "tl": "ko", "dt": "t", "q": "\n".join(texts)},
                              retries=1, timeout=10))
    lines = "".join(seg[0] for seg in data[0] if seg and seg[0]).split("\n")
    if len(texts) == 1:
        lines = [" ".join(lines)]
    return [_hangul(k) for k in lines] if len(lines) == len(texts) else None


def _microsoft(texts, sl, st):
    """Microsoft 번역(Edge 번역 주소): 제목 목록을 한 번에 보낸다. 토큰은 실행마다 한 번 받는다."""
    if not st.get("edge_token"):
        st["edge_token"] = net.get(EDGE_AUTH, retries=1, timeout=10).decode().strip()
    body = json.dumps([{"Text": t} for t in texts]).encode()
    data = json.loads(net.get(EDGE, {"from": sl, "to": "ko", "api-version": "3.0"}, data=body, retries=1, timeout=15,
                              headers={"Authorization": f"Bearer {st['edge_token']}", "Content-Type": "application/json"}))
    if not isinstance(data, list) or len(data) != len(texts):
        return None
    return [_hangul(((d.get("translations") or [{}])[0]).get("text")) for d in data]


def _mymemory(text, sl):
    """MyMemory 번역. 한도(MYMEMORY WARNING)·오류 응답이면 예외."""
    data = json.loads(net.get(MYMEMORY, {"q": text, "langpair": f"{sl}|ko"}, retries=1, timeout=10))
    out = (data.get("responseData") or {}).get("translatedText") or ""
    if data.get("responseStatus") not in (200, "200") or "MYMEMORY WARNING" in out.upper():
        raise RuntimeError(f"MyMemory {data.get('responseStatus')}: {out[:60]}")
    return _hangul(html.unescape(out))


ENGINES = (("Google", _google), ("Microsoft", _microsoft))


def _chunks(texts, size=CHUNK):
    chunk = []
    for t in texts:
        if chunk and len("\n".join(chunk + [t])) > size:
            yield chunk
            chunk = []
        chunk.append(t)
    if chunk:
        yield chunk


def _batch(name, fn, texts, sl, st):
    """묶음 번역 목록(안 된 줄은 ""). 묶음의 줄 수가 안 맞으면 한 건씩. 한 번 막히면 이 실행 동안은 다시 부르지 않는다."""
    if st["err"].get(name):
        return [""] * len(texts)
    try:
        kos = fn([_prep(t, sl) for t in texts], sl, st)
    except Exception as e:
        st["err"][name] = str(e)[:120]
        return [""] * len(texts)
    finally:
        time.sleep(PAUSE)
    if kos is None:
        return [_batch(name, fn, [t], sl, st)[0] for t in texts] if len(texts) > 1 else [""]
    return kos


def _mymemory_one(text, sl, st):
    """MyMemory 번역 한 건(안 되면 ""). 한 번 막히면(한도·오류) 이 실행 동안은 다시 부르지 않는다."""
    if st["err"].get(MM):
        return ""
    try:
        return _mymemory(_prep(text, sl), sl)
    except Exception as e:
        st["err"][MM] = str(e)[:120]
        return ""
    finally:
        time.sleep(PAUSE)


def cache_from(*lists):
    """이전에 번역한 제목: {원문: (번역, 출처)}. 같은 제목이면 예비 번역(MyMemory)이 아닌 것을 먼저 쓴다."""
    out = {}
    for items in lists:
        for x in items:
            if x.get("title") and x.get("title_ko") and out.get(x["title"], ("", MM))[1]:
                out[x["title"]] = (x["title_ko"], x.get("ko_by"))
    return out


def _known(x, cache):
    """이미 있는 번역 (번역, 출처): 기사에 붙은 것과 이전 파일 것 중 예비 번역이 아닌 것을 먼저."""
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

    번역이 없는 제목을 먼저, 그다음 MyMemory로 예비 번역해 둔 제목(Google·Microsoft로 다시)을 한 번에 max_new건까지 보낸다.
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
    st = {"err": {}, "n": {}, "fail": 0}
    for sl in LANGS:
        for chunk in _chunks([t for t, lang in todo if lang == sl]):
            got = dict.fromkeys(chunk, "")
            for name, fn in ENGINES:
                left = [t for t in chunk if not got[t]]
                if left:
                    for t, ko in zip(left, _batch(name, fn, left, sl, st)):
                        if ko:
                            got[t] = ko
                            st["n"][name] = st["n"].get(name, 0) + 1
            for t in chunk:
                ko, by = got[t], None
                if not ko and t in new:   # 앞의 두 곳이 안 되면 새 제목만 MyMemory로(예비 번역이 있는 제목은 그대로)
                    ko, by = _mymemory_one(t, sl, st), MM
                    st["n"][MM] = st["n"].get(MM, 0) + bool(ko)
                if ko:
                    cache[t] = (ko, by)
                else:
                    st["fail"] += t in new
    for x in items:
        if x.get("lang") in LANGS and x["title"] in cache:
            _put(x, *cache[x["title"]])
    if todo:
        left = len(new) + len(redo) - len(todo)
        print("번역: " + " · ".join(f"{name} {st['n'].get(name, 0)}건" for name in [e for e, _ in ENGINES] + [MM])
              + f" · 실패 {st['fail']}건" + (f" · 남은 제목 {left}건은 다음 실행" if left else "")
              + "".join(f" · {name} 오류: {err}" for name, err in st["err"].items()))
    return sum(1 for t in new if t in cache)
