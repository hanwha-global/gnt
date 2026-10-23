"""표준 라이브러리만 쓰는 간단한 HTTP 헬퍼(재시도 포함)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "HanwhaGlobalNetworkDashboard/1.0 (github.com/jeongpilchoi1992-hash/global-network-dashboard)"


def get(url, params=None, headers=None, retries=3, timeout=30):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404) or attempt == retries - 1:
                body = e.read()[:200].decode("utf-8", "replace").replace("\n", " ")
                raise RuntimeError(f"HTTP {e.code}: {body}") from None
            time.sleep(2 ** (attempt + 1))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def get_json(url, params=None, headers=None):
    return json.loads(get(url, params, headers))
