"""주요 지수 종가 처리(fetch_markets.yahoo_points)를 네트워크 없이 검증한다. 숫자는 가상 값."""
import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hanwha" / "scripts"))

import fetch_markets  # noqa: E402

UTC = dt.timezone.utc


def ts(y, m, d, h=0, mi=0):
    return int(dt.datetime(y, m, d, h, mi, tzinfo=UTC).timestamp())


def kospi(now_reg_day, bars, meta_time, meta_price):
    """서울(UTC+9) 지수: 정규장 09:00~15:30 KST = 00:00~06:30 UTC."""
    y, m, d = now_reg_day
    return {
        "meta": {"gmtoffset": 32400, "regularMarketTime": meta_time, "regularMarketPrice": meta_price,
                 "currentTradingPeriod": {"regular": {"start": ts(y, m, d, 0), "end": ts(y, m, d, 6, 30)}}},
        "timestamp": [t for t, _ in bars],
        "indicators": {"quote": [{"close": [c for _, c in bars]}]},
    }


BARS = [(ts(2026, 11, 12), 100.0), (ts(2026, 11, 13), 101.0)]


class YahooPointsTest(unittest.TestCase):
    def test_closed_day_missing_from_bars_is_added_from_meta(self):
        # 월요일 장 마감 뒤(02:17 KST 화) 일봉에 월요일이 아직 없어도 meta 종가로 채운다
        res = kospi((2026, 11, 16), BARS, ts(2026, 11, 16, 6, 30), 102.5)
        pts = fetch_markets.yahoo_points(res, now=ts(2026, 11, 16, 17, 17))
        self.assertEqual(pts[-1], ("2026-11-16", 102.5))
        self.assertEqual(pts[-2], ("2026-11-13", 101.0))

    def test_intraday_bar_is_not_shown_as_close(self):
        # 장중(11:19 KST)에는 당일 봉·meta 가격 모두 빼고 직전 종가를 쓴다
        bars = BARS + [(ts(2026, 11, 16), 99.0)]
        res = kospi((2026, 11, 16), bars, ts(2026, 11, 16, 2, 19), 99.0)
        pts = fetch_markets.yahoo_points(res, now=ts(2026, 11, 16, 2, 19))
        self.assertEqual(pts[-1], ("2026-11-13", 101.0))

    def test_bar_already_present_is_kept(self):
        bars = BARS + [(ts(2026, 11, 16), 102.0)]
        res = kospi((2026, 11, 16), bars, ts(2026, 11, 16, 6, 30), 102.5)
        pts = fetch_markets.yahoo_points(res, now=ts(2026, 11, 16, 9, 0))
        self.assertEqual(pts[-1], ("2026-11-16", 102.0))
        self.assertEqual(len(pts), 3)

    def test_before_open_uses_previous_close(self):
        # 다음 날 장 시작 전: 정규장 정보는 오늘(17일), meta는 16일 마감 값
        res = kospi((2026, 11, 17), BARS, ts(2026, 11, 16, 6, 30), 102.5)
        pts = fetch_markets.yahoo_points(res, now=ts(2026, 11, 16, 23, 0))
        self.assertEqual(pts[-1], ("2026-11-16", 102.5))


if __name__ == "__main__":
    unittest.main()
