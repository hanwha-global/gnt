"""국내 증권사 해외진출 뉴스: Google News RSS(키 불필요, LLM 미사용)에서 공신력 있는 매체 기사만 모은다.

- 검색어: 증권사별 '해외·현지법인·글로벌' 조합과 업계 전체 검색어
- 국내 주요 언론(SOURCES, 이름)과 해외 공신력 있는 매체·감독당국·거래소(FOREIGN_SITES, 도메인) 기사만 남기고,
  제목에 증권사(또는 증권업계)와 해외 관련 단어가 함께 있어야 한다. 외국어 제목은 회사 소식만(시황·종목 추천 제외)
- 거점 뉴스(fetch_hub_news.py)가 진출국 현지 매체에서 현지 법인 이름으로 찾은 기사도 싣는다("foreign": true)
- 제목이 거의 같은 기사(통신사 전재 등)는 하나만 남긴다

결과는 site/data/domestic/news.json. 매일 아침 GitHub Actions(news.yml)가 돌린다. 수집이 비면 이전 파일을 유지한다.
"""
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "domestic" / "news.json"
CONFIG = ROOT / "site" / "data" / "config.json"
KEEP_DAYS = 90
MAX_ITEMS = 60
KST = timezone(timedelta(hours=9))

# 공신력 있는 매체(Google News 표기 기준, 부분 일치). 국내 매체와 예전부터 쓰던 해외 매체 이름. 여기 없는 매체 기사는 버린다.
DOMESTIC = [
    "연합뉴스", "연합인포맥스", "뉴스1", "뉴시스", "한국경제", "한경", "매일경제", "머니투데이", "서울경제", "이데일리",
    "파이낸셜뉴스", "헤럴드경제", "아시아경제", "조선비즈", "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문",
    "한국일보", "서울신문", "국민일보", "문화일보", "세계일보", "아주경제", "이투데이", "더벨", "비즈니스포스트", "뉴데일리",
    "글로벌이코노믹", "데일리안", "머니S", "디지털타임스", "전자신문", "KBS", "MBC", "SBS", "YTN", "SBS Biz", "한국경제TV",
    "MBN", "Korea Times", "Korea Herald", "Korea JoongAng Daily", "Yonhap",
]
LEGACY_FOREIGN = ["Bloomberg", "Reuters", "Financial Times", "Nikkei", "DealStreetAsia", "Business Times", "The Straits Times",
                  "VnExpress", "Jakarta Globe"]
SOURCES = DOMESTIC + LEGACY_FOREIGN
# 해외 공신력 있는 매체·기관(기사 주소의 도메인, 하위 도메인 포함): 글로벌 통신·경제지, 진출국 전국 단위 주요 언론,
# 감독당국·거래소·지수 회사. 매체 이름은 같은 이름의 제휴판(Bloomberg Technoz 등)과 헷갈려 도메인으로 본다.
# 인도네시아어 매체(제목 언어 판별에도 쓴다)
ID_PRESS = ["kontan.co.id", "bisnis.com", "cnbcindonesia.com", "kompas.com", "kompas.id", "tempo.co", "antaranews.com", "investor.id",
            "katadata.co.id", "idxchannel.com", "detik.com", "cnnindonesia.com", "bloombergtechnoz.com", "beritasatu.com", "liputan6.com"]
FOREIGN_SITES = [
    # 글로벌 통신·경제지
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "nikkei.com", "cnbc.com", "economist.com", "apnews.com",
    "barrons.com", "marketwatch.com", "nytimes.com", "bbc.com", "bbc.co.uk", "theguardian.com", "fortune.com", "axios.com",
    # 아시아·금융 전문
    "straitstimes.com", "businesstimes.com.sg", "channelnewsasia.com", "theedgesingapore.com", "scmp.com", "thestandard.com.hk",
    "caixinglobal.com", "japantimes.co.jp", "kyodonews.net", "dealstreetasia.com", "financeasia.com", "asiaasset.com",
    "theasset.com", "euromoney.com", "thebanker.com", "institutionalinvestor.com", "risk.net", "globalcapital.com",
    "thestar.com.my", "bangkokpost.com", "khmertimeskh.com", "phnompenhpost.com", "thenationalnews.com", "gulfnews.com",
    "arabnews.com", "zawya.com",
    # 베트남
    "vnexpress.net", "vir.com.vn", "theinvestor.vn", "vietnamnews.vn", "vietnamplus.vn", "tuoitre.vn", "thanhnien.vn",
    "vneconomy.vn", "baodautu.vn", "tinnhanhchungkhoan.vn", "thoibaotaichinhvietnam.vn", "tapchitaichinh.vn", "cafef.vn",
    "nld.com.vn", "laodong.vn", "dantri.com.vn", "vietnamnet.vn", "vtv.vn", "sggp.org.vn", "bbw.vn", "vietstock.vn",
    # 인도네시아(영문 매체 jakartaglobe·thejakartapost 포함)
    *ID_PRESS, "jakartaglobe.id", "thejakartapost.com",
    # 인도·몽골·브라질·그리스
    "economictimes.indiatimes.com", "livemint.com", "business-standard.com", "moneycontrol.com", "thehindubusinessline.com",
    "financialexpress.com", "cnbctv18.com", "ndtvprofit.com", "montsame.mn", "valor.globo.com", "exame.com", "ekathimerini.com",
    # 감독당국·거래소·지수 회사
    "msci.com", "lseg.com", "ftserussell.com", "mas.gov.sg", "ojk.go.id", "idx.co.id", "ssc.gov.vn", "sfc.hk", "hkex.com.hk",
    "sebi.gov.in", "rbi.org.in", "sec.gov", "finra.org", "fca.org.uk",
]
# 제목에 있어야 하는 해외 관련 단어
OVERSEAS = ["해외", "현지법인", "현지 법인", "글로벌", "진출", "인수", "법인 설립", "지분 투자", "지분투자", "뉴욕", "홍콩", "런던",
            "싱가포르", "베트남", "인도네시아", "인도", "미국", "일본", "중동", "아부다비", "두바이", "사우디", "몽골", "브라질",
            "태국", "유럽", "월가", "overseas", "global", "abroad", "expansion", "acquisition", "acquire", "subsidiary",
            "vietnam", "indonesia", "hong kong", "new york", "india", "singapore", "london", "asia", "japan", "tokyo", "mongolia",
            "brazil", "europe", "middle east", "abu dhabi", "dubai", "saudi", "jakarta", "hanoi", "ho chi minh"]
# 홍보·시황성 기사 제외
NOISE = ["이벤트", "경품", "추천주", "특징주", "목표가", "목표주가", "매수 유지", "투자의견", "리포트", "[마감시황]", "시황",
         "해외주식 거래", "해외주식·", "글로벌 데스크", "수수료 혜택", "부고", "인사]", "퇴직연금", "中 증권사", "中증권", "中,", "중국 증권사",
         "베트남 증권사", "AI사업"]
ENGLISH = {"미래에셋증권": "Mirae Asset Securities", "한국투자증권": "Korea Investment & Securities", "NH투자증권": "NH Investment & Securities",
           "삼성증권": "Samsung Securities", "키움증권": "Kiwoom Securities", "KB증권": "KB Securities",
           "신한투자증권": "Shinhan Securities", "하나증권": "Hana Securities", "한화투자증권": "Hanwha Investment & Securities",
           "토스증권": "Toss Securities"}


# 제목에서 증권사를 알아보는 표기(약칭 포함). 설정 파일의 회사 이름은 항상 포함한다.
ALIASES = {"미래에셋증권": ["미래에셋"], "한국투자증권": ["한투", "한국투자"], "NH투자증권": ["NH투자", "NH證"],
           "삼성증권": [], "키움증권": ["키움"], "KB증권": [], "신한투자증권": ["신한투자", "신한證"], "하나증권": [],
           "한화투자증권": ["한화투자", "한화證"], "토스증권": []}


def firms_and_aliases():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    return {f["name"]: [f["name"], *ALIASES.get(f["name"], []), *([ENGLISH[f["name"]]] if f["name"] in ENGLISH else [])]
            for f in cfg["firms"]}


def queries(aliases):
    qs = [("증권사 해외법인", "ko"), ("증권사 해외 진출", "ko"), ("증권사 현지법인", "ko"), ("증권업계 글로벌 사업", "ko"),
          ("Korean brokerage overseas expansion", "en"), ("Korean securities firm acquisition overseas", "en")]
    for firm in aliases:
        qs.append((f"{firm} 해외법인 OR 현지법인 OR 해외 진출", "ko"))
        if firm in ENGLISH:
            qs.append((f'"{ENGLISH[firm]}"', "en"))
    return qs


# Google News 판(언어·지역): 진출국 기사는 그 나라 판에서 찾는다
EDITIONS = {"ko": ("ko", "KR", "KR:ko"), "en": ("en-US", "US", "US:en"), "vi": ("vi", "VN", "VN:vi"), "id": ("id", "ID", "ID:id"),
            "en-sg": ("en-SG", "SG", "SG:en"), "en-in": ("en-IN", "IN", "IN:en"), "en-gb": ("en-GB", "GB", "GB:en")}


def rss_url(q, lang, days=60):
    hl, gl, ceid = EDITIONS.get(lang, EDITIONS["en"])
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"{q} when:{days}d", "hl": hl, "gl": gl, "ceid": ceid})


def host(url):
    return (urllib.parse.urlparse(url or "").hostname or "").lower()


def foreign_site(site):
    """해외 공신력 있는 매체·기관 도메인인지(site: 주소 또는 호스트 이름)."""
    h = host(site) if "://" in (site or "") else (site or "").lower()
    return bool(h) and any(h == d or h.endswith("." + d) for d in FOREIGN_SITES)


def trusted(src, site=""):
    """국내 매체(이름) 또는 해외 공신력 있는 매체·기관(도메인)."""
    s = (src or "").lower()
    return any(t.lower() in s for t in SOURCES) or foreign_site(site)


def is_foreign(src, site=""):
    """해외 매체·기관 기사인지(국내 언론사의 영문판은 국내로 본다)."""
    s = (src or "").lower()
    if re.search(r"[가-힣]", s) or any(t.lower() in s for t in DOMESTIC):
        return False
    return foreign_site(site) or any(t.lower() in s for t in LEGACY_FOREIGN)


def source_url(it):
    """RSS <source url="…"> (매체 홈 주소)."""
    el = it.find("source")
    return el.get("url", "") if el is not None else ""


# 베트남어에만 있는 글자(â·ê·ô는 포르투갈어·프랑스어에도 있어 뺀다). 'Việt Nam'은 영문 기사에도 써서 세지 않는다
VI_CHARS = re.compile(r"[ăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)
# 인도네시아어 낱말(회사 이름에 들어가는 sekuritas·saham 같은 낱말은 뺀다). dan·di·ke는 영문 이름(Dan 등)과 겹쳐 약한 신호로만 센다
ID_STRONG = re.compile(r"\b(?:yang|dari|untuk|dengan|pada|ini|itu|usai|jadi|akan|tak|bisa|belum|sudah|masih|lebih|dalam|resmi|raih"
                       r"|sabet|tembus|naik|turun|oleh|bagi|lewat|atas|hingga|soal|kini|baru|kata|buka|suara|dorong|ungkap|catat|capai"
                       r"|bidik|incar|genjot|perkuat|jalin|gandeng|sepakat|kerja sama|kinerja|laba|izin|sanksi|denda|nasabah|kasus|dugaan"
                       r"|kantor|tahun|juta|miliar|triliun|nama|ganti|akuisisi|milik|selatan|tumbuh|melonjak|nilai|kena|serangan|lumpuh"
                       r"|intip|prospek|bisnis|profil|kronologi|begini|nasib|seremoni|aplikasi|pengguna|transaksi|paruh|pertama|\w{4,}kan)\b", re.I)
# 인도네시아어 접사(perubahan·peluncuran, diretas·digeledah, …nya)
ID_AFFIX = re.compile(r"\bpe[a-z]{3,}an\b|\bdi[a-z]{3,}(?:kan|i|as|ah)\b|\b[a-z]{3,}nya\b", re.I)
ID_WEAK = re.compile(r"\b(?:dan|di|ke)\b", re.I)
EN_STOP = re.compile(r"\b(?:the|of|for|and|to|in|on|with|as|at|by|from|after|its|is|are|new|over|amid)\b", re.I)


def lang_of(title, site=""):
    """제목 언어(ko·vi·id·en): 화면의 '번역' 링크를 베트남어·인도네시아어 제목에만 붙인다.

    인도네시아어 매체(ID_PRESS·.id 주소, 영문판 en.* 제외) 기사는 영어 낱말이 둘 이상이 아니면 인도네시아어 흔적 하나로 'id'로 본다.
    """
    if re.search(r"[가-힣]", title):
        return "ko"
    if VI_CHARS.search(re.sub(r"Vi[eệ]t\s?Nam", " ", title, flags=re.I)):
        return "vi"
    strong = len({m.lower() for m in ID_STRONG.findall(title)})
    weak = len({m.lower() for m in ID_WEAK.findall(title)})
    en = len({m.lower() for m in EN_STOP.findall(title)})
    if strong >= 2 or (not en and strong >= 1) or (not en and strong + weak >= 2):
        return "id"
    local = site and not re.match(r"en(?:glish)?\.", site) and (site.endswith(".id") or any(site == d or site.endswith("." + d) for d in ID_PRESS))
    return "id" if local and en < 2 and (strong + weak or ID_AFFIX.search(title)) else "en"


# 외국어 제목은 회사 소식(실적·출시·제휴·인수·증자·인허가·제재·수사·수상·경영진·확장·전략)만 남긴다
EVENT = re.compile(
    r"\b(?:profits?|earnings|net income|loss(?:es)?|revenues?|launch\w*|unveil\w*|debut\w*|introduc\w*|rolls? out|enables?|partner\w*|mou"
    r"|tie-?up|ties up|alliance|joins?|joined|acquir\w*|acquisition|merger|merges?|consolidat\w*|stakes?|buys?|invests?|capital|rights issue|raises?"
    r"|funding|licen[cs]e\w*|nod|approv\w*|permit|fined?|sanction\w*|penalt\w*|probe\w*|raid\w*|suspen\w*|bans?|award\w*|wins?"
    r"|renam\w*|rebrand\w*|appoint\w*|ceo|chief executive|names? new|expan\w*|enters?|entry|offices?|branch\w*|subsidiar(?:y|ies)|sets? up|establish\w*"
    r"|underwrit\w*|mandates?|cyber\w*|hack\w*|outage|strateg\w*|plans?|bets? on|focus(?:es)? on)\b"
    r"|laba|rugi|pendapatan|kinerja|luncur|rilis|kerja ?sama|kolaborasi|kemitraan|gandeng|sepakat|akuisisi|caplok|ambil alih|modal"
    r"|izin|lisensi|sanksi|denda|teguran|beku|geledah|gerebek|diretas|siber|\bojk\b|polri|bareskrim|dugaan|penyidikan|diusut|kasus"
    r"|goreng|klarifikasi|penghargaan|raih|sabet|ganti nama|perubahan nama|direktur (?:utama )?baru|direksi baru|(?:angkat|tunjuk|rombak)\w* direk"
    r"|\brups\b|ekspansi|cabang|kantor|mandat|penjamin|\baum\b|dana kelolaan|targetkan|resmi|konsolidasi|andalkan|fokus|strategi|genjot"
    r"|bidik|incar|perkuat|tumbuh"
    r"|lãi(?! suất| vay| tiết kiệm| tiền gửi| margin)|lợi nhuận|lỗ|doanh thu|kết quả kinh doanh|ra mắt|triển khai|hợp tác|ký kết|bắt tay|đối tác|tăng vốn|góp (?:vốn|thêm)"
    r"|rót vốn|bơm vốn|phát hành"
    r"|vốn điều lệ|cổ phần|giấy phép|cấp phép|thu hồi|xử phạt|bị phạt|án phạt|đình chỉ|giải thưởng|nhận giải|vinh danh|đổi tên|chủ tịch"
    r"|tổng giám đốc|bổ nhiệm|kế hoạch|mở rộng|chi nhánh|cổ đông|mua lại|thâu tóm|sáp nhập|thành lập|khai trương|chiến lược|xếp hạng"
    r"|phân phối|(?:cổ phiếu|cp) ưu đãi", re.I)
# 외국어 제목의 시황·종목 추천·애널리스트 코멘트·회사 소개 페이지·워런트 상장
FOREIGN_NOISE = re.compile(
    r"\b(?:target price|price target|stocks? to buy|worth buying|buy rating|top picks?|recommend\w*|says|explains|answers|decodes|predicts"
    r"|sees|upside|downside|bullish|bearish|multibagger|analysts?|chart|technical (?:analysis|view|chart)s?|technicals|nifty|sensex"
    r"|share price|upgrades?|downgrades?|podcast|webinar"
    r"|rekomendasi\w*|saham pilihan|target harga|stop loss|ihsg|jci|proyeksi|prediksi|analis|jagokan|optimistis|soroti)\b"
    r"|khuyến nghị|nhận định|chuyên gia|gọi tên|điểm tên|cổ phiếu tiềm năng|vn-?index|chứng quyền|\((?:otc|hose|hnx|upcom)\)"
    r"|ban lãnh đạo|cổ đông lớn|lịch sử giá|^cw\.|\blive:"
    # 'Buy Abbott India; target of Rs …', '… Pertahankan Rating Buy BSDE' 같은 종목 의견
    r"|^(?:buy|sell|hold|accumulate|reduce)\b|\brating (?:buy|hold|sell|trading buy)\b|\btarget of\b"
    # 판촉·행사(수수료·이자 면제, 경품, 세미나·대회). '우선주(cổ phiếu ưu đãi)'는 자본 소식이라 남긴다
    r"|miễn (?:phí|lãi)|hoàn (?:\d+% )?phí|khuyến mãi|\bcombo\b|gói vay|cuộc thi|hội thảo|quà tặng|happy monday|(?:chương trình|gói) ưu đãi"
    r"|ưu đãi (?:cực|lớn)|\bpromo\w*|cashback|\bdiskon\b|\bgratis\b|coaching clinic|giveaway", re.I)
# 'WOORICBV:Công ty…', 'BSI: Cổ đông lớn' 같은 종목 페이지(감독당국·거래소 이름으로 시작하는 제목은 뺀다)
TICKER_HEAD = re.compile(r"^(?!OJK|BEI|IDX|SSC|MSCI|FTSE|SEC|MAS)[A-Z0-9]{3,10}\s?:\s?")


def foreign_ok(title, event=True):
    """외국어 제목이 회사 소식인지(시황·추천·종목 페이지가 아니고 사건 낱말이 있는지).

    event=False(국내 영문 매체: Korea Herald 등)는 사건 낱말 없이 잡음·종목 페이지만 거른다.
    """
    return (not event or bool(EVENT.search(title))) and not FOREIGN_NOISE.search(title) and not TICKER_HEAD.match(title)


DATA = ROOT / "site" / "data" / "domestic"


def overseas_entities():
    """(증권사, 나라) → 현지 법인 정식 이름: 사이트 법인 집계(consolidated.json 금융업 영업법인·중간지주)와 관계사·지분투자 법인."""
    out = {}
    cons = DATA / "consolidated.json"
    firms = json.loads(cons.read_text(encoding="utf-8")).get("firms", {}) if cons.exists() else {}
    for firm, c in firms.items():
        for x in c.get("overseas", []):
            if x.get("class") in ("영업법인", "지주회사") and x.get("country"):
                out.setdefault((firm, x["country"]), []).append(x.get("name") or "")
    for e in json.loads((DATA / "seed.json").read_text(encoding="utf-8"))["entities"]:
        if e.get("name") and e["kind"] == "법인" and e["status"] == "운영" and e.get("country") and (
                e["relation"] in ("관계사", "지분투자") or e["firm"] not in firms):
            out.setdefault((e["firm"], e["country"]), []).append(e.get("dart_name") or e["name"])
    return out


LEGAL = re.compile(r"\b(?:pt\.?|jsc|joint\s*stock\s*company|corporation|corp\.?|co\.,?|company|limited|ltd\.?|inc\.?|llc|llp|pte\.?"
                   r"|private|s\.a\.|cctvm|ltda\.?|utsk)(?=\s|$|,|\.)", re.I)
REGION = re.compile(r"\b(?:indonesia|vietnam|viet nam|asia|mongolia|india|ifsc|singapore|hong kong|hk|usa|us|america|uk|europe|eu"
                    r"|japan|brasil|brazil)\b", re.I)
INDUSTRY = re.compile(r"\b(?:investment\s*&\s*securities|investment\s*&\s*sekuritas|securities\s*&\s*investments|securities finance"
                      r"|securities investment|securities|sekuritas|holdings|financial services|investment services|capital markets"
                      r"|asset management|investment management)\b", re.I)
GENERIC = {"asset", "management", "investment", "investments", "securities", "sekuritas", "holdings", "finance", "financial", "capital",
           "markets", "services", "partners", "global", "group", "&"}
# 정식 이름에서 나오지 않는 현지 약칭(대문자 그대로 맞춘다)
LOCAL_SHORT = {("KB증권", "베트남"): ["KBSV"], ("NH투자증권", "베트남"): ["NHSV"], ("한국투자증권", "베트남"): ["KIS Việt Nam", "KIS Vietnam"],
               ("한화투자증권", "인도네시아"): ["Ciptadana AM"]}
# 단어 하나짜리 표기(Pinetree 등)는 금융 문맥 낱말이 같이 있어야 한다
# 'stock·share·IPO·fund' 같은 낱말은 커피·기술주 기사에도 나와 넣지 않는다(증권사·운용사·시장 제도 낱말만)
FIN_CTX = re.compile(r"\b(?:securities|sekuritas|chứng khoán|ctck|broker\w*|broking|saham|pasar modal|reksa ?dana|cổ phiếu|quỹ"
                     r"|asset management|aset manajemen|manajer investasi|wealth management|trading (?:app|platform)|giao dịch|margin"
                     r"|bursa|ojk|ssc|ubck|nbfc|demat|tokeni\w*)\b", re.I)


def _squash(s):
    return re.sub(r"\s+", " ", s).strip(" ,.&")


def _plain(name):
    n = LEGAL.sub(" ", name)
    n = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", n)  # BIDVSecurities → BIDV Securities
    n = re.sub(r"([a-z])([A-Z])", r"\1 \2", n)
    n = re.sub(r"\(.*?\)", " ", n)
    return _squash(LEGAL.sub(" ", n))


def _brand(firm):
    return _norm(INDUSTRY.sub(" ", ENGLISH.get(firm, "")))


def brand_ctx(firm):
    """한 낱말 표기의 금융 문맥으로 쳐 줄 모회사 이름(Mirae Asset … Sharekhan). 'Korea'처럼 흔한 낱말이면 영문 이름 앞 두 낱말을 쓴다."""
    b = _brand(firm)
    return " ".join(_norm(ENGLISH.get(firm, "")).split()[:2]) if b == "korea" else b


def brand_only(firm, phrase):
    """표기가 모회사 이름 + 일반 낱말뿐인지(Hana Asset Management 등: 국내 계열사와 헷갈린다)."""
    btok = set(_brand(firm).split())
    return not [w for w in _norm(phrase).split() if w not in GENERIC and w not in btok]


def local_phrases(firm, country, names):
    """현지 법인 정식 이름에서 기사 제목에 쓰이는 표기를 만든다: [(표기, 나라 표기 필요, 금융 문맥 필요)].

    - 모회사 이름과 같은 표기(Mirae Asset Securities 등)는 빼고(국문·영문 회사 검색이 맡는다)
    - 모회사 이름 + 일반 낱말뿐인 표기(Hana Asset Management 등)는 국내 계열사와 헷갈리므로 제목에 그 나라 표기가 있어야 한다
    - 현지어 업종 표기(… Sekuritas, Chứng khoán …)는 그 나라 법인이다
    """
    eng, brand = _norm(ENGLISH.get(firm, "")), _brand(firm)
    out, local = {}, {}
    for name in names:
        if not name or re.search(r"[가-힣]", name):
            continue
        base = _squash(REGION.sub(" ", _plain(name)))
        core = _squash(INDUSTRY.sub(" ", base))
        for c in (core, base):
            if not c or _norm(c) in (eng, brand):
                continue
            toks = _norm(c).split()
            if len(toks) < 2 and len(c) < 5:
                continue
            out.setdefault(_norm(c), (c, brand_only(firm, c), len(toks) == 1))
        if country == "인도네시아" and re.search(r"sekuritas", base, re.I):
            local[_norm(base)] = base
        if country == "베트남" and core and re.search(r"securities", base, re.I):
            local[_norm(f"Chứng khoán {core}")] = f"Chứng khoán {core}"
    for s in LOCAL_SHORT.get((firm, country), []):
        local[_norm(s)] = s
    out.update({k: (v, False, False) for k, v in local.items()})
    return sorted(out.values())


def _norm(s):
    return re.sub(r"\s+", " ", s.replace("&", " & ")).lower().strip()


def local_hit(title, phrases, place=None, lang=None, brand=""):
    """외국어 제목에 현지 법인 표기가 나오는지(국문 제목은 기존 규칙이 본다).

    나라 표기가 필요한 표기는 제목에 그 나라 이름(place 정규식)이 있거나 제목이 그 나라 말(lang)이면 된다.
    금융 문맥이 필요한 한 낱말 표기는 금융 낱말이나 모회사 이름(brand)이 같이 있으면 된다.
    """
    if re.search(r"[가-힣]", title):
        return False
    t = _norm(title)
    ctx = bool(FIN_CTX.search(title) or (brand and re.search(rf"(?<![\w]){re.escape(brand)}(?![\w])", t)))
    for ph, need_place, need_ctx in phrases:
        if ph.isupper() and len(ph) <= 7:
            hit = re.search(rf"(?<![\w]){re.escape(ph)}(?![\w])", title)
        else:
            hit = re.search(rf"(?<![\w]){re.escape(_norm(ph))}(?![\w])", t)
        if not hit or (need_ctx and not ctx):
            continue
        if not need_place or (place and re.search(place, title)) or (lang and lang_of(title) == lang):
            return True
    return False


def local_queries(firm, country, phrases, limit=3):
    """현지 법인 표기 검색어: 현지어 표기 먼저, 그다음 짧은 표기(긴 표기를 포함하는 짧은 표기가 있으면 긴 표기는 뺀다)."""
    ed = {"베트남": "vi", "인도네시아": "id", "싱가포르": "en-sg", "인도": "en-in", "영국": "en-gb"}.get(country, "en")
    # 한 낱말(Pinetree 등)은 검색어로 쓰지 않고 맞추기만 한다. 두 나라에 걸친 표기(나라 표기 필요)도 검색어로는 쓴다
    # 현지어 표기(Mirae Asset Sekuritas 등)는 모회사 이름 + 일반 낱말이어도 그 나라 법인이라 검색하고, 나머지는 모회사 이름뿐이면 뺀다
    pool = [p for p, _, one in phrases if not one]
    local = [p for p in pool if p.startswith("Chứng khoán") or re.search(r"sekuritas", p, re.I)]
    rest = sorted((p for p in pool if p not in local and not brand_only(firm, p)), key=len)
    rest = [p for p in rest if not any(q != p and _norm(q) in _norm(p) for q in rest)]
    return [(f'"{p}"', ed) for p in (local + rest)[:limit]]


def mentions(title, aliases):
    t = title.lower()
    return [firm for firm, names in aliases.items() if any(n.lower() in t for n in names)]


def relevant(title, firms, foreign=True):
    t = title.lower()
    if any(n.lower() in t for n in NOISE):
        return False
    if not re.search(r"[가-힣]", title) and not foreign_ok(title, event=foreign):
        return False
    who = firms or re.search(r"증권사|증권업계|증권가|brokerage|securities firm", t)
    return bool(who) and any(k in t for k in OVERSEAS)


def norm_title(t):
    """같은 기사 판별 키. 외국어 제목은 앞부분이 긴 법인 이름(Mirae Asset Sekuritas Indonesia …)이라 더 길게, 악센트 글자도 살려 본다."""
    if re.search(r"[가-힣]", t):
        return re.sub(r"[^0-9a-z가-힣]", "", t.lower())[:28]
    return re.sub(r"[\W_]", "", t.casefold())[:60]


def parse(xml_bytes, aliases, since):
    items = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        for _ in range(2):  # 'OO - 머니투데이 - 머니투데이' 처럼 매체명이 두 번 붙는 경우
            if src and title.endswith(f" - {src}"):
                title = title[: -len(src) - 3].strip()
        # 국내 매체의 영문 번역판은 같은 기사가 두 번 나오므로 뺀다
        if re.search(r"[가-힣]", src) and not re.search(r"[가-힣]", title):
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:
            continue
        site = host(source_url(it))
        if when < since or not trusted(src, site):
            continue
        firms = mentions(title, aliases)
        if not relevant(title, firms, is_foreign(src, site)):
            continue
        items.append(mark({"date": when.strftime("%Y-%m-%d"), "time": when.strftime("%H:%M"), "title": title, "src": src,
                           "url": (it.findtext("link") or "").strip(), "site": site, "firms": firms}))
    return items


def mark(x):
    """해외 매체 기사 표시(foreign)와 제목 언어(lang: 베트남어·인도네시아어면 화면에 '번역' 링크)."""
    x = {k: v for k, v in x.items() if k not in ("foreign", "lang", "old")}
    if is_foreign(x.get("src"), x.get("site", "")):
        x["foreign"] = True
    lang = lang_of(x["title"], x.get("site", ""))
    if lang in ("vi", "id"):
        x["lang"] = lang
    return x


def hub_foreign(since, prev=()):
    """거점 뉴스(fetch_hub_news.py, 아침 06:30)가 현지 법인 이름으로 찾은 해외 매체 기사: 이 피드에도 싣는다.

    거점 파일은 칸마다 최근 몇 건만 두므로, 이 피드에 이미 실린 거점 기사(prev)도 기간 안이면 이어 둔다.
    둘 다 지금 거점 규칙으로 다시 거른다(규칙이 바뀌었거나 거점 수집이 실패해 파일이 오래됐을 때).
    """
    import fetch_hub_news as hub  # 함수 안에서: fetch_hub_news가 이 모듈을 import한다
    path = DATA / "hub_news.json"
    hubs = json.loads(path.read_text(encoding="utf-8")).get("hubs", {}) if path.exists() else {}
    day = since.strftime("%Y-%m-%d")
    phrases = hub.hub_phrases()
    out = []
    for x in [{**x, "hub": key} for key, items in hubs.items() for x in items] + [x for x in prev if x.get("hub")]:
        firm, _, country = x["hub"].partition("|")
        src, site = x.get("src"), x.get("site", "")
        if (x.get("old") or x.get("date", "") < day or not is_foreign(src, site) or not trusted(src, site)
                or not hub.relevant(x["title"], firm, country, phrases.get((firm, country), ()))):
            continue
        out.append(mark({**x, "time": x.get("time", ""), "firms": [firm]}))
    return out


def main():
    now = datetime.now(KST)
    since = now - timedelta(days=KEEP_DAYS)
    aliases = firms_and_aliases()
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    found, errors = [], []
    for q, lang in queries(aliases):
        try:
            found += parse(net.get(rss_url(q, lang), timeout=25), aliases, since)
        except Exception as e:
            errors.append(f"{q}: {e}")
    # 이전 수집분도 기간 안이면 이어 붙인다(검색 결과에서 밀려난 기사 보존)
    # 필터 규칙이 바뀌어도 맞도록 이전 기사도 같은 규칙으로 다시 거른다. 거점 뉴스에서 온 기사는 거점 파일에서 다시 가져온다
    found += [mark(x) for x in prev.get("items", []) if not x.get("hub") and x.get("date", "") >= since.strftime("%Y-%m-%d")
              and trusted(x.get("src"), x.get("site", "")) and relevant(x["title"], x.get("firms") or [], is_foreign(x.get("src"), x.get("site", "")))
              and not (re.search(r"[가-힣]", x.get("src", "")) and not re.search(r"[가-힣]", x["title"]))]
    found += hub_foreign(since, prev.get("items", []))
    seen, items = set(), []
    for x in sorted(found, key=lambda x: (x["date"], x.get("time", "")), reverse=True):
        k = norm_title(x["title"])
        if k in seen:
            continue
        seen.add(k)
        items.append(x)
    items = items[:MAX_ITEMS]
    if not items:
        print("수집된 기사 없음: 이전 파일 유지", errors[:3])
        return 0
    OUT.write_text(json.dumps({"updated_at": now.isoformat(timespec="minutes"), "source": "Google News RSS · 국내 주요 언론 + 해외 매체·기관",
                               "sources": DOMESTIC, "foreign_sites": FOREIGN_SITES, "items": items, "errors": errors[:10]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {OUT.name}: {len(items)}건(해외 매체 {sum(1 for x in items if x.get('foreign'))}건) (오류 {len(errors)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
