"""진출국 전략 Takeaways: 당사 현지법인이 있는 나라마다 실행 방향 3~4줄을 규칙으로 만든다(LLM 미사용).

한눈에 보기 맨 위 박스가 읽는다. 사이트가 이미 매일·매주 모으는 공개 자료만 쓴다.
- 당사 해외자회사 손익·출자: hanwha/data/dart_subs.json (DART)
- 지수·환율·정책금리·결정 일정: hanwha/data/markets.json, macro.json, rate_calendar.json
- 나라별 구조 뉴스(MSCI·FTSE 등): site/data/global/macro_news.json
- 한국계 경쟁사 현지 뉴스: site/data/domestic/hub_news.json, news.json
- 현지 점유율·상장 증권사: site/data/global/markets.json, listed.json, (있으면) insight/data/landscape.json, idx_share.json

규칙마다 '언제 발동하는지'와 '근거 한 줄(숫자마다 기준 시점)'을 정해 두고, 나라마다 점수가 높은 순으로
카테고리가 겹치지 않게 3~4개를 고른다. 문구는 '…검토할 만합니다/점검할 만합니다'로 끝나는 자동 의견이며
회사의 공식 입장이 아니다. 회사 내부 계획·목표가 있다고 전제하는 표현은 쓰지 않는다(공개 자료만).

매일 아침(news.yml) 돈다. 그 나라에 큰 변화가 있을 때만 문구를 바꾸고, 없으면 이전 문구를 그대로 두고
확인 시각만 남긴다. 큰 변화: 새 DART 보고서, 고른 규칙·구간의 변화, 3일 안의 새 구조·경쟁사·당사 뉴스,
정책금리 변경, 지수·환율 급변, 마지막 갱신 후 14일 경과. 규칙이 하루 안 잡히면(자료 공백) 하루는 이전 줄을
그대로 두고 이틀째 빠진다(같은 날 다시 돌려도 하루로 센다. 새 공시 날이나 그 줄을 직접 건드린 사건이 있는
날은 바로 뺀다. 유예 줄도 그날의 국면·보류 조건에 맞춰 문구를 고쳐 쓰고, 어제 점수로 다른 줄과 겨룬다). 해외자회사 공시
파일이 비거나 깨진 날은 판단하지 않고 이전 문구를 유지한다. 'MSCI 결정 전까지'는 그 기관의 마지막 결정(강등 확정·
후속 기사·우려 해소) 뒤에 나온 기사가 분류·강등 결정을 앞으로의 일로 말할 때만 쓴다. 판단 상태(본 기사·직전 공시·금리 등)는
takeaways_state.json 에 따로 두어 화면이 읽는 파일을 가볍게 한다.

    python scripts/build_takeaways.py            # 갱신
    python scripts/build_takeaways.py --print    # 파일은 쓰지 않고 결과만 출력
"""
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
OUT_REL = "site/data/domestic/takeaways.json"
STATE_REL = "site/data/domestic/takeaways_state.json"
SPEC_VERSION = 2
KST = timezone(timedelta(hours=9))
MAX_STALE_DAYS = 14
NEWS_FRESH_DAYS = 3
ARCHIVE_DAYS = 61    # 규칙이 보관함을 읽는 가장 긴 창(제재·사기 60일)보다 하루 길게
HOME = "한화투자증권"

COUNTRIES = ["VN", "ID", "SG"]
KOR = {"VN": "베트남", "ID": "인도네시아", "SG": "싱가포르"}
KEYS = {"VN": ["VN"], "ID": ["CSA", "CAM"], "SG": ["SG"]}       # dart_subs·entities 키
BROKER = {"VN": "VN", "ID": "CSA", "SG": "SG"}                    # 나라별 당사 증권 법인
IX = {"VN": "VN-Index", "ID": "IDX(자카르타)", "SG": "STI(싱가포르)"}
IX_SHORT = {"VN": "VN-Index", "ID": "IDX", "SG": "STI"}
CCY = {"VN": "VND", "ID": "IDR", "SG": "SGD"}
CCY_NAME = {"VND": "동", "IDR": "루피아", "SGD": "싱가포르달러"}
LAND = {"VN": "vn", "ID": "id", "SG": "sg"}
EXCHANGE = {"VN": "HOSE·HNX", "ID": "IDX", "SG": "SGX"}

LEVERS = {"M&A·지분", "자본", "구조조정·비용", "마케팅·고객"}
RISK = "리스크·규제"

# 나라 귀속(제목 기준): 피드가 아니라 제목으로 정한다(인니 기사가 싱가포르 피드에 들어오는 일이 있음)
C_RE = {
    "VN": re.compile(r"vietnam|viet nam|베트남|vn-?index|\bhose\b", re.I),
    "ID": re.compile(r"indonesia|인도네시아|인니|\bidx\b|\bjci\b|jakarta", re.I),
    "SG": re.compile(r"singapore|싱가포르|\bsti\b|\bsgx\b", re.I),
}
MAS_RE = re.compile(r"\bMAS\b")
OFF_WATCH = re.compile(r"off (the )?watch ?list|keeps .{0,30} off", re.I)
OFF_WATCH_UPGRADE = re.compile(r"off (the )?watch ?list.{0,40}upgrad|keeps .{0,30} off.{0,40}upgrad", re.I)  # 승격 관찰대상에서 빠짐 = 호재 아님
NEUTRAL = re.compile(r"\brebut|\bdefend(s|ed)?\b|\bden(y|ies|ied)\b|반박|부인", re.I)
# 강등 우려가 걷힌 기사(강등 안 함·철회·신흥시장 유지·우려 완화)는 '관찰대상 제외 유지'처럼 안도(+1)로 본다.
# 'to avoid'처럼 피하려 애쓰는 기사는 아직 악재다. 사이는 한 절 안([^;,.:])에서만 본다('FTSE spares X; MSCI downgrade looms'는 안도 아님)
_C = r"[^;,.:]"
_K = r"[^…;,.:·]"   # 한글 제목의 한 절(… , · 로 끊음)
# 신흥시장 유지(keep·retain·maintain)는 나라·시장이 바로 목적어일 때만('keeps rates steady as EM …'·'retain gains as … upgrade'는 아님)
_OBJ = r"(?:Indonesia|Vietnam|Viet Nam|Singapore|(?:Indonesian|Vietnamese|Singaporean|Jakarta)\s+(?:stocks|equities|shares|market|bourse)|the (?:country|market|bourse)|it)(?:['’]s)?"
# 한글 안도 표현은 끝난 말(해소됐·해소에·피했다)만: '해소 위해·나서·기대·될까·진정 안 돼'는 아직 걸린 일
_KNOT = r"위해|위한|나서|역부족|기대|될까|총력|안간힘|안\s*돼|못|과제|촉구|요구|요청|가능|\?|까(?=\s|$)|지\s*주목|실패|어려|쉽지|불투명|대책|방안|노력"
RELIEF_RE = re.compile(rf"\bnot (to )?(be )?downgrad|\bno downgrade|\b(won|doesn|didn|isn|wasn|weren)['’]t (be )?downgrad|\bavoid(s|ed)\b{_C}{{0,20}}downgrad|\bspar(es|ed)\b{_C}{{0,30}}downgrad|"
                       rf"\bescap(es|ed)\b{_C}{{0,20}}downgrad|\b(dodge[sd]|averts|averted|sidestep(s|ped)|stave[sd])\b{_C}{{0,20}}downgrad|"
                       rf"\bdecid(es|ed) against\b{_C}{{0,20}}downgrad|"
                       rf"\b(avoid(s|ed)|escap(es|ed)|spar(es|ed)|dodge[sd]|averts|averted)\b{_C}{{0,20}}reclassif|\bdecid(es|ed) (against|not to)\s+reclassif|"
                       rf"\b(won|doesn|didn)['’]t (be )?reclassif(?!{_C}*\b(yet|until|before)\b)|\bno reclassification\b(?!\s+(decision|yet|before|until)\b)|"
                       r"\b(drops|dropped|abandons|abandoned|withdraws|withdrew|scraps|scrapped)\s+(its\s+|the\s+)?(plans?|proposals?|bid)\s+(to|for)\s+(\w+\s+){0,3}(downgrad|demot|cut|move|reclassif)|"
                       r"\b(drops|dropped|abandons|abandoned|withdraws|withdrew)\s+(\w+\s+){0,2}downgrade (plan|proposal)|"
                       r"\b(scrap|shelv)\w* (\w+ ){0,2}downgrad|\brules? out (\w+ ){0,3}downgrad|"
                       r"downgrade (fears?|concerns?|worr\w*) (eas|fad|reced|subsid)\w*|"
                       r"(fears?|concerns?|worr\w*) (of|over|about) (an? )?(MSCI |FTSE )?downgrade (eas|fad|reced|subsid)\w*|"
                       rf"\b(keep|retain|maintain)(s|ed)?\s+{_OBJ}\s+(as (an? )?|in (the |its )?)(emerging[- ]markets?|EM)\b(?!{_C}{{0,15}}upgrad)|"
                       r"\b(keep|retain|maintain)(s|ed)?\s+(\w+['’]s\s+|its\s+|the\s+)?((MSCI|FTSE)\s+)?emerging[- ]markets?\s+(status|classification|tag|label)|"
                       rf"remains? (in (the )?|an? )emerging[- ]market|강등\s*(결정\s*)?(철회|무산)(?!{_K}*?(?:{_KNOT}))|"
                       # 이미 피한 말(피했·피한·모면했)은 뒤의 '반등 기대·과제 남아'가 뒤집지 않는다. 맨 '모면·면해·피해가'는 애쓰는 말이 뒤에 없을 때만
                       rf"강등\s*(은|는)?\s*(위기\s*)?(을\s*|를\s*)?(\S+\s+)?(피해\s*(갔|간)|피했(?!나|을까|는지)|피한(?!다)|모면했|모면한(?!다)|면했|넘겼)(?!{_K}*?(?:아니|아냐|못|\?))|"
                       rf"강등\s*(은|는)?\s*(위기\s*)?(을\s*|를\s*)?(\S+\s+)?(피해\s*가(?=\s*$)|피한다|모면한다|모면(?=\s*(?:$|[…;,.:·]))|면해(?=\s*(?:$|[…;,.:·])))(?!{_K}*?(?:{_KNOT}))|"
                       rf"강등\s*(우려|공포|위기|리스크)\S*\s*(해소|완화|진정|일단락)(?=됐|되며|된|되자|돼(?!야)|했|하며|하자|에\s|로\s(?!\s*(이어|연결))|\s*$|\s*[…;,.:·'\"’”])(?!{_K}*?(?:{_KNOT}))", re.I)
# 'fights to keep·reforms to retain·likely to remain·hopes MSCI won't'처럼 애쓰거나 바라거나 내다보는 말이 같은 절 앞에 있으면
# 아직 안도가 아니다(기사 제목의 'Indonesia to remain in EM'은 '남는다'는 뜻이라 안도로 본다)
HEDGE_RE = re.compile(r"\b(hop(e|es|ed|ing)|bets?|betting|confiden\w*|expect\w*|likely|probably|seen|set|poised|could|may(?!\s+(review|rebalanc\w*|index|reshuffle|decision|announcement|\d))|might|would|should|can|"
                      r"why|whether|if|urg\w*|argu\w*|calls?|wants?|seeks?|aims?|fight\w*|scrambl\w*|rac(e|es|ing)|bids?|push\w*|tr(y|ies|ying)|"
                      r"struggl\w*|reforms?|plans?|moves?|steps?|measures?|efforts?|vows?|pledg\w*|works?|looks?|rush\w*|battl\w*|eye(s|ing)?|need\w*)\b", re.I)
# 'won't rule out downgrade'처럼 부정한 안도 표현은 여전히 위협이다
NOT_RELIEF_RE = re.compile(r"(\bnot|n't|\brefus\w* to|\bdeclin\w* to|\bcannot|\bunable to)\s+(\w+\s+){0,2}(rule|ruling)s? out", re.I)
# 다른 계획이 철회·보류된 기사는 호재·악재 어느 쪽도 아니다
RESOLVED = re.compile(r"\bscrap|\bshelv|rules? out", re.I)
# 승격이 미뤄지거나 무산된 기사는 호재가 아니다
DELAY_RE = re.compile(r"miss(es|ed)? out|\bdelay|postpon|\bstall|\bfades?\b|setback|\bfail|remains? on .{0,15}watch|keeps? .{0,30}\bon (the )?watch ?list|연기|불발|무산|보류", re.I)
NEG_RE = re.compile(r"downgrad|demot|standalone|\b(to|as|into) (an? |the )?frontier|\brout\b|manipulat|outflow|sell-?off|plunge|tumble|slump|angst|turmoil|강등|급락|이탈|폭락|delist", re.I)
# '급락 뒤 반등' 기사는 악재가 아니다: 반등 앞뒤의 하락 표현은 악재로 세지 않는다(그 사이의 강등 같은 구조 표현은 남긴다)
REBOUND_RE = re.compile(r"(rebound|recover|rall(y|ies|ied)|bounce)\w*\s+(from|after)\s+(?:(?!downgrad|standalone|frontier)[\w\s'-]){0,25}?(slump|plunge|tumble|sell-?off|rout)\w*|"
                        r"(급락|폭락)\S*\s*(딛고|뒤|후|끝)\s*\S*\s*반등", re.I)
# 걸려 있는 결정(강등 검토·의견수렴·경고 등 앞으로의 일)을 가리키는 말: '○○ 결정 전까지'라고 쓸 때만
PENDING_RE = re.compile(r"review|consult|propos|warn|\bfac(es?|ing)\b|\bcould\b|\bmay\b|\bmight\b|watch ?list|weigh|consider|threat|\brisks?\b|"
                        r"fears?|concern|worr|\bloom|\bdelay|postpon|\bdefer|rules? out|\bto (be )?(downgrad|reclassif)|\bto avoid\b|scrambl|\brac(es|ing)\b|ahead of|pending|await|"
                        r"decision (due|in|on|next)|검토|의견 ?수렴|경고|우려|가능성|관찰|앞두|임박|연기|유보|유예|보류|미뤄|여부|촉각|전망|결정은|D-\d", re.I)
# 걸린 결정 기사는 그 기관의 분류·강등 결정을 다뤄야 한다('승격 뒤 외국인 매도가 커질 수 있다'는 아님)
DECISION_CTX_RE = re.compile(r"downgrad|강등|standalone|frontier|프런티어|프론티어|reclassif|재분류|consult|의견 ?수렴|review|검토|watch ?list|관찰|decision|결정", re.I)
AFTER_UP_RE = re.compile(r"\b(after|despite|following|post-?)\s*(the\s+|its\s+|an?\s+)?(\w+\s+){0,2}(upgrade|inclusion)|(승격|편입)\S*\s*(후|뒤|이후|에도)", re.I)
# 이미 내려진 강등: 지수 회사가 주어이거나 프런티어·독립시장으로 옮긴 기사(증권사의 투자의견 하향 'downgrades X to neutral'은 아님).
# 'MSCI moves closer to·cuts weight of'는 결정이 아니다. 한글은 같은 절(… , · 로 끊음) 안에 연기·검토·전망 같은 말이 없을 때만
_KWAIT = (r"앞두|임박|연기|유예|보류|미뤄|미룬|연장|여부|촉각|철회|무산|전망|가능|검토|우려|경고|위기|위험|리스크|공포|대비|시나리오|D-|\?|"
          r"제안|의견\s*수렴|협의|착수|놓고|앞서|가닥|땐|\s시(?:\s|$)|되면|할\s*경우")
# '강등 확정에 시장 개혁 착수·대책 협의'처럼 확정 뒤의 대응은 기다리는 말이 아니다
_KWAIT_DONE = _KWAIT.replace("협의|착수|", "")
CONFIRMED_RE = re.compile(rf"(MSCI|FTSE){_C}{{0,25}}\b(downgrades|downgraded|reclassifies|reclassified|demotes|demoted|relegates|relegated)\b|"
                          rf"\b(downgraded|reclassified|demoted|relegated|moved|moves|cut|cuts)\b{_C}{{0,25}}\b(to|as|into) (an? |the )?(frontier|standalone)|"
                          rf"\b(demoted|relegated|downgraded)\b{_C}{{0,25}}\bby (MSCI|FTSE)|"
                          rf"(MSCI|FTSE){_C}{{0,25}}\b(confirms|confirmed|finali[sz]es|finali[sz]ed|announces|announced|completes|completed)\s+((?!potential|possible|proposed|planned|likely)\w+\s+){{0,2}}"
                          r"(downgrade|demotion|reclassification)\b(?!\s+(review|consult\w*|risks?|plans?|proposals?|talks?|process|probe|warnings?|threats?))|"
                          r"\bdowngrade (becomes|became|is now|made) official|(MSCI|FTSE)(\s+Russell)?\s+follows\s+(MSCI|FTSE)\s+in\s+(downgrad|demot)|"
                          rf"(프런티어|프론티어|독립시장|스탠드얼론)(\s*시장)?\s*(으로|로)?\s*강등(?!{_K}*?(?:{_KWAIT}))|"
                          rf"(?:강등\s*(확정(?!\s*(전|이전|직전)(?:\s|$|[…;,.:·]))|했|됐|단행)(?!적|되면|될|돼야)|결국\s*(\S+\s*)?강등(?=\s*(?:$|[…;,.:·])))(?!{_K}*?(?:{_KWAIT_DONE}))|"
                          rf"강등\s*결정(?=\s*(?:내려|내렸|했|발표|에\s|으로|$|[…;,.:·'\"’”]))(?!{_K}*?(?:{_KWAIT_DONE}))", re.I)
# 확정 표현과 같은 절에 붙은 조동사·위협·계획 표현(could be downgraded·moves to downgrade 등)은 아직 걸린 결정이다
MODAL_RE = re.compile(r"\b(could|may|might|would|to be|set to|likely to|fac(es|ing)|risks?|threat\w*|warn\w*|propos\w*|consider\w*|weigh\w*)\s+(\w+\s+){0,2}(downgrad|cut|reclassif|mov|demot)|"
                      r"\bmov\w* (closer|nearer|toward)|\bstep closer|\b(mov(es|ed|ing)?|plans?|propos\w*|seeks?|aims?|bid) to (\w+ ){0,2}(downgrad|cut|reclassif|demot|relegat|move)", re.I)
HYPO_RE = re.compile(rf"\b(if|whether|unless|in case)\b|what happens|\bdanger\b|\brisk(s|ing)? (of )?being\b|"
                     rf"\b(wasn|weren|isn|aren|won|hasn|haven)['’]t\s+(be\s+|been\s+)?(downgraded|demoted|relegated|cut|moved)|\bnot\s+(be|been)\s+(downgraded|demoted|relegated|cut|moved)|"
                     rf"\bnever\s+(been\s+)?(downgraded|demoted)|\b(prevent|avoid|stop|keep|spare|shield|save)\w*\b{_C}{{0,40}}\bbeing\b", re.I)
CLAUSE_RE = re.compile(r"[;:…·]|,\s|\.\s|\s[-–—|]\s")
# 내려진 강등의 후속 기사('… after MSCI downgrade', '강등 충격에', '… downgrade takes effect'): 결정은 이미 난 것으로 본다
# (경고·검토·우려·가능성 기사는 아님. 'on MSCI downgrade …'는 위협 기사에도 쓰여 넣지 않는다)
AFTERMATH_RE = re.compile(r"\b(after|following|post)\s+(the\s+)?(MSCI|FTSE)('s|’s)?\s+(\w+\s+)?downgrade\b"
                          r"(?!\s*(fears?|concerns?|worr\w*|risks?|threats?|warnings?|review|decision|talks?|speculation|proposals?|plans?|consult\w*|watch|probe|"
                          r"scare|jitters|angst|uncertaint\w*|prospects?|possibilit\w*|anxiety|bets?|odds|alert|spect(re|er)))|"
                          r"(MSCI|FTSE)('s|’s)?\s+(\w+\s+)?downgrade\s+(takes|took|taking) effect|"
                          r"(MSCI|FTSE)\S*\s*(\S+\s*)?강등\s*(충격|여파|후폭풍)(?!\S*\s*(우려|가능|전망))", re.I)
# 이미 결정이 난 뒤에는 새 결정 단계를 말하는 기사만 다시 '걸린 결정'으로 본다(이미 내려진 강등을 되짚는 기사는 아님)
_MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December|20\d\d)"
# ('further·additional·another·추가'는 결정 단계에 붙을 때만: 'further outflows·추가 이탈'은 결정 뒤 여파)
_STEP = r"(review|consultation|downgrade|cut|demotion|reclassification|step|warning)"
NEW_STEP_RE = re.compile(rf"review|consult|watch ?list|\bnext\b|\b(further|additional|another|fresh|new)\s+{_STEP}|"
                         rf"\b(cut|cuts|downgrad\w*|demot\w*|reclassif\w*)\s+((Indonesia|Vietnam|Singapore|it|the market|the country|Indonesian stocks)\s+)?(further|again)\b|"
                         rf"\bwarn\w*\s+(\w+\s+){{0,3}}again\b|\bagain\s+warn|\bwarn\w*\s+(of\s+)?(further|additional|fresh|new)\s+(action|steps?|measures?)|(추가|재차)\s*조치\s*경고|또다시\s*(강등|경고)|"
                         rf"\bdecision (is )?(due|expected|scheduled|slated)\b|\b(due|expected|scheduled|slated) (in|by) {_MONTH}|검토|의견 ?수렴|관찰|"
                         rf"(추가|재차)\s*(강등|검토|의견|경고)|강등\s*(추가|재차)|결정\s*(은|는)?\s*(내년|다음|\d+월|\d{{4}}년)|결정\s*예정", re.I)
UPGRADE_CTX_RE = re.compile(r"upgrad|inclusion|승격|편입|reclassif|watch ?list", re.I)
UP_WORD_RE = re.compile(r"upgrad|inclusion|승격|편입|to (secondary )?emerging|to developed", re.I)
DOWN_CTX_RE = re.compile(r"downgrad|강등|standalone", re.I)
# 인도네시아(이미 신흥시장)의 '재분류'는 강등 쪽 이야기다(베트남은 승격). 프런티어·독립시장 이동도 강등 쪽
RECLASS_RE = re.compile(r"reclassif|재분류", re.I)
ID_RECLASS_RE = re.compile(r"(indonesia\w*|인니|인도네시아)\W+(\w+\W+){0,2}(reclassif|재분류)|(reclassif\w*|재분류)\W+(\w+\W+){0,2}(indonesia|인니|인도네시아)", re.I)
FRONTIER_RE = re.compile(r"(as|into|to) (an? |the )?frontier|standalone|프런티어|프론티어|독립시장", re.I)
POS_RE = re.compile(r"upgrad|inclusion|편입|승격|상향|reclassif|index options?|derivativ|옵션|파생", re.I)
# 호재는 시장 분류·상품 제도 기사만(성장률 전망·신용등급 상향은 '시장 지위'가 아님)
STRUCT_POS_RE = re.compile(r"MSCI|FTSE|S&P Dow Jones|reclassif|market (status|upgrade|classification)|emerging market|frontier|"
                           r"index options?|derivativ|신흥시장|편입|승격|옵션|파생", re.I)
DERIV_RE = re.compile(r"index options?|derivativ|옵션|파생", re.I)
CAPITAL_RE = re.compile(r"증자|자본금|자본 ?확충|곳간|인수|지분|합병|M&A|점유율 ?전쟁|stake|acquir", re.I)
CAPITAL_HEAD_RE = re.compile(r"자본금|증자|자본 ?확충")
REG_RE = re.compile(r"manipulat|fraud|scam|과징금|과태료|경영유의|적발|시세조종|사기", re.I)
# 'sanction·fine·penalty'는 외교 제재 기사와 섞이므로 감독기관 이름이 같이 있고 외교 제재가 아닐 때만
# ban·suspend 는 처분 대상(증권사·임직원·인가)이 있을 때만('short-selling ban'·'suspends trading of shares'는 시장 조치)
_PARTY = r"(broker\w*|brokerage|securities (firm|company|companies|broker\w*)|firms?|individuals?|former|directors?|traders?|employees?|representatives?|licen[cs]es?)"
REG_FINE_RE = re.compile(rf"sanction|\bfine[ds]?\b(?!-)|penal(t|is|iz)|revok\w*\s+(\w+\s+){{0,2}}licen[cs]e|licen[cs]e\s+(revoc|revok|suspen)|"
                         rf"suspend\w*\s+(?!(\w+\s+)?(trading|shares|stocks|listing|securities)\s+(of|in)\s+(?!(\w+\s+){{0,2}}(broker\w*|securities (firm|compan))))(\w+\s+){{0,3}}{_PARTY}|(broker\w*|securities firm)\s+(\w+\s+){{0,3}}suspen|"
                         rf"\bbann?(ed|s)?\s+(\w+\s+){{0,3}}{_PARTY}|\bbanned from|reprimand|censur|insider trading", re.I)
# 한글 '제재·위반·벌금'은 감독기관 이름이 빠진 제목이 많아 외교·통상 제재만 아니면 센다
REG_KO_RE = re.compile(r"제재|위반|벌금")
# 영업정지·인가 취소·징계는 공장·체육 기사에도 나오므로 감독기관이나 증권사 말이 같이 있을 때만
REG_KO_FIRM_RE = re.compile(r"영업\s*정지|인가\s*취소|징계")
BROKER_KO_RE = re.compile(r"증권|브로커|운용사")
# 미국·통상 제재(우회수출·관세·환적) 기사: 감독기관과 증권사 말이 둘 다 있을 때만 감독 제재로 본다('미국 법인'은 아님)
DIPLO_KO_RE = re.compile(r"美|미국(?!\s*법인)|대미|관세|우회\s*수출|환적")
REGULATOR_RE = re.compile(r"\bSSC\b|\bSBV\b|\bOJK\b|\bMAS\b|\b(IDX|HOSE|SGX)\b(?![- ]listed)|regulator|watchdog|securities commission|"
                          r"감독|당국|금감원|금융위|증권위|거래소", re.I)
DIPLO_RE = re.compile(r"\biran|north korea|russia|\bOFAC\b|\bU\.?S\.? (imposes|sanction)|\bU\.?S\.? Treasury|Treasury Department|"
                      r"이란|대북|북한|北|러시아|美\s*(재무부|정부)|대미 제재", re.I)
RWA_RE = re.compile(r"RWA|토큰|STO|디지털자산|가상자산|tokeni", re.I)
BANK_RE = re.compile(r"BIDV|VietinBank|Vietcombank|Agribank|Mandiri|\bBRI\b|\bBNI\b|\bBCA\b|Danareksa", re.I)
BROKER_NAME_RE = re.compile(r"securities|sekuritas|증권", re.I)
NOT_BROKER_RE = re.compile(r"\(주1\)|asset management|investment management|fund|reksa|realty|ETF|capbridge", re.I)
# 영문 구조 뉴스 제목 → 짧은 한글 라벨(없으면 빈 문자열: 근거에는 '{매체} 보도'로 적는다)
# (정규식, 라벨, 필요한 극성 None·+1·-1·0) — 기사 극성과 어긋나는 라벨은 붙이지 않는다
LABELS = [
    (re.compile(r"index options?", re.I), "지수옵션 도입 계획", None),
    (re.compile(r"(R&I|rating).*upgrad|upgrad.*(R&I|BBB)", re.I), "신용등급 상향", None),
    (re.compile(r"market upgrade (is|was) (just|only)|(beyond|after) (the )?market upgrade|post-?upgrade", re.I), "시장 승격 이후 과제", 1),
    # 한글 '강등'은 같은 절에 검토·경고·우려 같은 말이 있을 때만(결정·안도·경쟁사 증자 기사는 제목·인용구를 그대로 쓴다)
    (re.compile(r"MSCI.*(downgrad|demot|reclassif|frontier)|(downgrad|demot|reclassif|frontier).*MSCI|MSCI.*강등[^…;,.:·]{0,12}?(검토|경고|우려|가능성|위기|앞두|임박|촉각|공포|여부|전망|연기|유예|보류)|"
                r"강등[^…;,.:·]{0,12}?(검토|경고|우려|가능성|위기|앞두|임박|촉각|공포|여부|전망|연기|유예|보류).*MSCI", re.I), "MSCI 강등 검토", -1),
    (re.compile(r"manipulat", re.I), "시세조종 대책 강화", None),
    (re.compile(r"bond premia.{0,40}(high|widen|jump|surge|soar)", re.I), "회사채 가산금리 확대", None),
    (re.compile(r"FTSE.*(upgrad|inclusion)|(upgrad|inclusion).*FTSE", re.I), "FTSE 승격", 1),
]


# ---------- 작은 도구 ----------
def load(root, rel):
    p = root / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def d(s):
    """'2026-10-26' · '20261026' · '2026.10.26' → date."""
    m = re.search(r"(\d{4})[-.]?(\d{2})[-.]?(\d{2})", str(s or ""))
    return date(*map(int, m.groups())) if m else None


def md(x):
    x = d(x) if not isinstance(x, date) else x
    return f"{x.month}/{x.day}" if x else ""


def eok(v):
    """백만원 → '12.3억원'."""
    return f"{v / 100:,.1f}억원"


def sgn(v, digits=1):
    return f"{v:+.{digits}f}%"


def month_end(ym):
    y, m = map(int, ym.split("-")[:2])
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def rep_name(period):
    name = ((period or {}).get("report") or {}).get("name", "")
    m = re.match(r"(?:\[\w+\])?(.+?)\s*\((\d{4}\.\d{2})\)", name)
    return f"{m.group(2)} {m.group(1)}" if m else name


QUOTE_RE = re.compile(r"‘([^‘’]{2,30})’|“([^“”]{2,30})”|'([^']{2,30})'|\"([^\"]{2,30})\"")


def news_label(title, src=""):
    if OFF_WATCH.search(title):
        prov = near_prov(title, OFF_WATCH.search(title))   # 관찰대상에서 뺀 기관('FTSE keeps X off watch list despite MSCI …' → FTSE)
        return f"{prov} 관찰대상 제외".strip() + (" 유지" if re.search(r"keeps?", title, re.I) else "")
    ko = bool(re.search(r"[가-힣]", title))
    # 경쟁사 증자·자본 확충 기사는 강등 이야기가 곁들여져도 그 기사 자체(인용구·제목)로 적는다
    if not (ko and CAPITAL_HEAD_RE.search(title)):
        pol = polarity(title)
        prov = next((p for p in ("FTSE", "MSCI") if p in title), "")
        if pol > 0 and relief_match(title):
            return f"{decided_by(title)} 강등 우려 해소".strip()
        if pol == 0 and prov and DELAY_RE.search(title) and UPGRADE_CTX_RE.search(title) and not DOWN_CTX_RE.search(title) \
                and (UP_WORD_RE.search(title) or "ID" not in countries_of(title)):
            return f"{prov} 승격 지연"
        if pol < 0 and prov and confirmed(title):
            return f"{decided_by(title)} 강등 결정"
        if pol < 0 and prov and AFTERMATH_RE.search(title):
            return f"{decided_by(title)} 강등 여파"
        for rx, label, need in LABELS:
            if rx.search(title) and (need is None or need == pol):
                return label
    if ko:
        # 짝이 맞는 인용구 중 자본·제재 관련 말을 먼저, 없으면 가장 긴 것(‘기지개’ 같은 수식어보다 주제를 고르게)
        qs = [next(g for g in m.groups() if g).strip() for m in QUOTE_RE.finditer(title)]
        qs = [q for q in qs if len(q) >= 2]
        if qs:
            return next((q for q in qs if CAPITAL_RE.search(q) or REG_RE.search(q)), max(qs, key=len))
        return title[:22] + "…" if len(title) > 22 else title
    return ""


def cite(it, lead=""):
    """근거 인용: "Reuters 10/25 '라벨'" · 라벨이 없으면 "Reuters 10/25 보도"."""
    lab = news_label(it["title"], it.get("src", ""))
    return f"{lead}{it.get('src', '')} {md(it.get('date'))} " + (f"'{lab}'" if lab else "보도")


def more(n, what, window=""):
    """'… 등 구조 뉴스 3건(최근 30일)' · 한 건이면 '등' 없이 '…(구조 뉴스, 최근 30일)'."""
    if n > 1:
        return f" 등 {what} {n}건" + (f"({window})" if window else "")
    return f"({what}" + (f", {window}" if window else "") + ")"


def base_label(D):
    """최신 기간을 비교한 FY 기준: 'FY2025 반기 환산 대비' · 9개월이면 '9개월 환산' · 연간끼리면 'FY2025 대비'."""
    per = {3: "분기 환산 ", 6: "반기 환산 ", 9: "9개월 환산 "}.get((D.L or {}).get("months"), "")
    return f"FY{D.B['year']} {per}대비"


def josa(word, batchim, plain):
    """앞말 끝 글자 받침에 따라 조사 고르기(과/와, 은/는 등). '법인(PTSV)'처럼 괄호가 붙으면 괄호 앞 말을 본다."""
    ch = (re.sub(r"\([^)]*\)\s*$", "", word or "").strip() or " ")[-1]
    if "가" <= ch <= "힣":
        return batchim if (ord(ch) - 0xAC00) % 28 else plain
    return batchim


def polarity(title):
    """+1 시장 지위 호재·안도 · -1 구조적 악재 · 0 중립. 안도(관찰대상 제외 유지·강등 우려 해소)는 악재를 상쇄할 뿐
    '승격'은 아니다(struct()가 relief()로 구분)."""
    if OFF_WATCH.search(title):
        return 0 if OFF_WATCH_UPGRADE.search(title) else 1
    if NEUTRAL.search(title):
        return 0
    if NOT_RELIEF_RE.search(title) and DOWN_CTX_RE.search(title):
        return -1
    if relief_match(title):
        return 1
    if RESOLVED.search(title):
        return 0
    if RECLASS_RE.search(title) and not UP_WORD_RE.search(title) and (FRONTIER_RE.search(title) or countries_of(title) == ["ID"] or ID_RECLASS_RE.search(title)):
        return -1   # 인도네시아 재분류 의견수렴·연기 등은 강등 쪽 이야기
    if NEG_RE.search(REBOUND_RE.sub(" ", title)):
        return -1
    if DELAY_RE.search(title):
        return 0
    if POS_RE.search(title) and STRUCT_POS_RE.search(title):
        return 1
    return 0


def clause_start(title, at):
    return max([0] + [x.end() for x in CLAUSE_RE.finditer(title, 0, at)])


def relief_match(title):
    """안도 표현(강등 안 함·우려 해소 등)의 첫 위치. 같은 절 앞에 애쓰거나 바라거나 내다보는 말이 있으면
    ('fights to keep·hopes MSCI won't·likely to remain') 뺀다. 'X to remain in EM'(남는다)은 안도로 둔다."""
    for m in RELIEF_RE.finditer(title):
        lead = title[clause_start(title, m.start()):m.start()]
        # 'stocks set to rally after MSCI decides against …'처럼 앞 절의 전망은 안도를 바라는 말이 아니다: 마지막 접속어 뒤만 본다
        own = re.split(r"\b(?:as|after|since|because|following)\b", lead, flags=re.I)[-1]
        # 이미 지난 일('wasn't downgraded')은 'Why …'로 시작해도 안도다
        past = re.match(r"(wasn|weren|didn)['’]t", m.group(0), re.I)
        if (HEDGE_RE.search(own) and not past) or (re.search(r"\bto\s+$", lead, re.I) and not m.group(0).lower().startswith("remain")):
            continue
        # 재분류를 피한 기사는 인도네시아(강등 쪽)만 안도다(베트남은 승격이 미뤄진 것)
        if RECLASS_RE.search(m.group(0)) and (not (countries_of(title) == ["ID"] or ID_RECLASS_RE.search(title)) or UP_WORD_RE.search(title)):
            continue
        return m
    return None


def relief(title):
    """악재가 걷혔다는 안도 기사(호재로 세되 '시장 지위 상향'은 아님)."""
    return polarity(title) > 0 and bool(OFF_WATCH.search(title) or relief_match(title))


def confirm_match(title):
    """이미 내려진 강등 표현의 위치. 같은 절에 could·faces 같은 말이 붙으면(could be downgraded) 아직 걸린 결정이다.
    다른 절의 전망('…; outflows could top $2bn')은 확정을 뒤집지 않는다."""
    for m in CONFIRMED_RE.finditer(title):
        a = clause_start(title, m.start())
        nxt = CLAUSE_RE.search(title, m.end())
        clause = title[a:nxt.start() if nxt else len(title)]
        # 'if downgraded by MSCI·what happens if·in danger of being·wasn't downgraded·moves to prevent … being downgraded'는 아직 일어나지 않은 일
        if not MODAL_RE.search(clause) and not HYPO_RE.search(title[a:m.end()]):
            return m
    return None


def confirmed(title):
    """이미 내려진 강등(could be downgraded·앞두고 등 앞으로의 일을 말하면 아님)."""
    return confirm_match(title) is not None


def near_prov(title, m):
    """표현 m 의 주인인 지수 회사: 표현 안 → 바로 앞(가장 가까운) → 뒤(가장 가까운) 순."""
    hits = [(x.start(), x.group(0)) for x in re.finditer(r"MSCI|FTSE", title)]
    inside = [p for i, p in hits if m.start() <= i < m.end()]
    before = [p for i, p in hits if i < m.start()]
    after = [p for i, p in hits if i >= m.end()]
    return (inside or before[-1:] or after[:1] or [""])[0]


def decided_by(title):
    """결정(강등 확정·그 후속 기사·우려 해소·관찰대상 제외)을 알린 기사면 그 지수 회사, 아니면 ''."""
    if polarity(title) > 0:
        m = OFF_WATCH.search(title) or relief_match(title)
        if m:
            return near_prov(title, m)
    m = confirm_match(title) or AFTERMATH_RE.search(title)
    return near_prov(title, m) if m and polarity(title) < 0 else ""


def reg_hit(title):
    """제재·사기·시세조종 기사인가(외교·통상 제재·'fine-tune'·'SGX-listed' 제외)."""
    if REG_RE.search(title):
        return True
    if DIPLO_RE.search(title):
        return False
    if DIPLO_KO_RE.search(title) and not (REGULATOR_RE.search(title) and BROKER_KO_RE.search(title)):
        return False
    if REG_KO_FIRM_RE.search(title) and (REGULATOR_RE.search(title) or BROKER_KO_RE.search(title)):
        return True
    return bool(REG_KO_RE.search(title) or (REG_FINE_RE.search(title) and REGULATOR_RE.search(title)))


def countries_of(title):
    cs = [c for c in ("VN", "ID") if C_RE[c].search(title)]
    if not cs and (C_RE["SG"].search(title) or MAS_RE.search(title)):
        cs.append("SG")
    return cs


class Data:
    """규칙이 읽는 입력. 없는 파일은 None(규칙이 알아서 건너뜀)."""

    def __init__(self, root, today, prev_state=None):
        self.root, self.today = root, today
        self.mk = load(root, "hanwha/data/markets.json") or {}
        self.macro = load(root, "hanwha/data/macro.json") or {}
        self.subs = load(root, "hanwha/data/dart_subs.json") or {}
        ents = load(root, "hanwha/data/entities.json") or {}
        self.ents = {e["key"]: e for e in ents.get("entities", [])}
        self.cal = load(root, "hanwha/data/rate_calendar.json") or {}
        self.reg = load(root, "hanwha/data/regulatory.json") or {}
        self.mnews = load(root, "site/data/global/macro_news.json") or {}
        self.hub = (load(root, "site/data/domestic/hub_news.json") or {}).get("hubs", {})
        self.news = (load(root, "site/data/domestic/news.json") or {}).get("items", [])
        self.gmk = {m["id"]: m for m in (load(root, "site/data/global/markets.json") or {}).get("markets", [])}
        self.listed = (load(root, "site/data/global/listed.json") or {}).get("markets", {})
        self.dl = load(root, "site/data/domestic/dart_latest.json") or {}
        self.subfin = (load(root, "site/data/domestic/sub_fin.json") or {}).get("firms", {})
        self.land = (load(root, "insight/data/landscape.json") or {}).get("markets")
        self.idx = load(root, "insight/data/idx_share.json")
        self.digi = load(root, "digital/data/regulation.json")
        periods = self.subs.get("periods") or []
        self.L = periods[-1] if periods else None
        self.state = prev_state or {}
        # 비교 기준 FY: 최신 기간보다 앞선 사업보고서. 수집기는 최신 사업보고서 이후만 남기므로,
        # 최신이 사업보고서인 해에는 상태에 남겨 둔 직전 FY를 쓴다(없으면 FY 비교 규칙은 건너뜀)
        fy = [p for p in periods if p.get("period") == "FY" and p is not self.L]
        kept = [p for y, p in sorted((self.state.get("fy") or {}).items()) if self.L and str(y) < str(self.L.get("year"))]
        self.B = fy[-1] if fy else (kept[-1] if kept else None)
        # 뉴스 보관함: 피드는 나라당 몇 건만 남기므로, 본 기사를 state.seen 에 모아 국면을 이어 간다
        self.archive = dict(self.state.get("seen", {}))

    def fy(self, year):
        """그 해 사업보고서(FY) 기간: 수집 파일에 없으면 상태에 남겨 둔 것."""
        for per in reversed((self.subs.get("periods") or [])):
            if per.get("period") == "FY" and str(per.get("year")) == str(year):
                return per
        return (self.state.get("fy") or {}).get(str(year))

    def peer_year(self):
        """한국계 경쟁사 종속기업 요약재무(sub_fin.json)가 읽은 사업보고서 연도(가장 많은 해, 같으면 최근)."""
        ys = [m.group(1) for f in self.subfin.values() for m in [re.match(r"(\d{4})\s*사업보고서", str(f.get("report") or ""))] if m]
        return max(set(ys), key=lambda y: (ys.count(y), y)) if ys else None

    # 당사 법인
    def label(self, key):
        return self.ents.get(key, {}).get("label") or key

    def labels(self, keys):
        return "·".join(self.label(k) for k in keys)

    def sub(self, period, key):
        return ((period or {}).get("subs") or {}).get(key) or {}

    def ix(self, c):
        return next((i for i in self.mk.get("indices", []) if i.get("name") == IX[c]), None)

    def policy(self, c):
        return next((t for t in (self.mk.get("policy") or {}).get("table", []) if t.get("key") == c), None)

    def age(self, s):
        x = d(s)
        return (self.today - x).days if x else 10 ** 6

    # 뉴스 풀: 현재 피드 + 보관함
    def macro_items(self):
        pool = {}
        for v in (self.mnews.get("countries") or {}).values():
            for it in v.get("items", []):
                pool.setdefault(it["url"], {**it, "kind": "macro"})
        for url, it in self.archive.items():
            if it.get("kind") == "macro":
                pool.setdefault(url, {**it, "url": url})
        return list(pool.values())

    def news_items(self):
        pool = {it["url"]: {**it, "kind": "news"} for it in self.news if it.get("url")}
        for url, it in self.archive.items():
            if it.get("kind") == "news":
                pool.setdefault(url, {**it, "url": url})
        return list(pool.values())

    def hub_items(self, c, home=None):
        out = []
        for k, items in self.hub.items():
            firm, _, country = k.partition("|")
            if country != KOR[c] or (home is True and firm != HOME) or (home is False and firm == HOME):
                continue
            out += [{**it, "firm": firm, "kind": "hub"} for it in items]
        return out


def cand(rule, category, weight, text, evidence, keys, variant="", bucket=(), driver=None, links=(), **extra):
    return {"rule": rule, "variant": variant, "category": category, "weight": weight, "text": text,
            "evidence": [e for e in evidence if e], "keys": list(keys), "bucket": list(bucket),
            "driver": driver.isoformat() if isinstance(driver, date) else driver,
            "links": [l for l in links if l and l.get("url")], **extra}


def link(it, label=None):
    return {"label": label or news_label(it["title"], it.get("src", "")) or it.get("src") or "기사", "url": it["url"], "title": it["title"]}


def chg(ix, k):
    """지수 등락률(%) — 기준 종가가 없으면 수집기가 None 을 쓴다."""
    v = ((ix or {}).get("chg") or {}).get(k)
    return v if isinstance(v, (int, float)) else None


# ---------- 규칙 ----------
def struct(D, c):
    """구조 뉴스 국면: POS(시장 지위 상향) · NEG(강등·급락) · None."""
    items = [it for it in D.macro_items() if it.get("priority") and D.age(it.get("date")) <= 30 and c in countries_of(it["title"])]
    for it in items:
        it["pol"] = polarity(it["title"])
    pos = events(sorted([i for i in items if i["pol"] > 0], key=lambda i: i["date"], reverse=True))
    neg = events(sorted([i for i in items if i["pol"] < 0], key=lambda i: i["date"], reverse=True))
    # '관찰대상 제외 유지'·'강등 우려 해소'는 악재를 상쇄하는 안도일 뿐 시장 지위가 오른 것은 아니다
    up = [i for i in pos if not relief(i["title"])]
    ix = D.ix(c)
    m1 = chg(ix, "1M")
    dd = drawdown(ix, 13)
    if neg and (len(pos) - len(neg) <= -2 or (m1 is not None and m1 <= -10) or (dd is not None and dd <= -0.20)):
        return "NEG", pos, neg
    if len(up) >= 2 and not neg and (m1 is None or m1 > -10):
        return "POS", up, neg
    return None, pos, neg


def events(items):
    """같은 사건을 여러 매체가 쓴 경우 한 건으로(라벨이 같거나 제목이 같으면). 최신 기사를 남긴다."""
    out, keys = [], {}
    for it in items:
        k = news_label(it["title"]) or re.sub(r"\W", "", it["title"].lower())[:40]
        if k not in keys:
            keys[k] = it
            it["same"] = []
            out.append(it)
        else:
            keys[k]["same"].append({"title": it["title"], "date": it.get("date", "")})   # 합친 기사(걸린 결정 판단에 쓴다)
    return out


def drawdown(ix, months):
    vals = [v for _, v in (ix or {}).get("monthly", [])[-months:] if isinstance(v, (int, float))]
    if not vals or not isinstance((ix or {}).get("close"), (int, float)):
        return None
    peak = max(vals)
    return ix["close"] / peak - 1 if peak else None


def peak_month(ix, months):
    return max((kv for kv in ix["monthly"][-months:] if isinstance(kv[1], (int, float))), key=lambda kv: kv[1])[0]


def own_and_peers(D, c):
    """(당사 행, 한국계 동종 행들, 현지 상장사 ROE 목록, 출처 라벨). 현지통화 자본, FY 기준."""
    key = BROKER[c]
    if D.land and LAND[c] in D.land:
        rows = D.land[LAND[c]].get("rows", [])
        own = next((r for r in rows if r.get("kind") == "korean" and r.get("firm") == HOME and r.get("broker")), None)
        peers = [r for r in rows if r.get("kind") == "korean" and r.get("broker") and r.get("firm") != HOME and r.get("equity")]
        if peers:
            top = max(r["equity"] for r in peers)
            peers = [r for r in peers if r["equity"] >= 0.01 * top]
        loc = [r["roe"] for r in rows if r.get("kind") == "local" and r.get("roe") is not None and not r.get("stale")]
        if own:
            return {"equity": own["equity"], "equity_krw": own.get("equity_krw"), "roe": own.get("roe"), "asof": own.get("asof")}, \
                [{"equity": r["equity"], "equity_krw": r.get("equity_krw"), "firm": r["firm"]} for r in peers], loc, "land"
    # 대체: 종속기업 요약재무(DART FY2025, 백만원)와 현지 상장사(listed.json)
    sB = D.sub(D.B, key)
    if not sB.get("assets"):
        return None, [], [], ""
    eq = sB["assets"] - sB["liab"]
    own = {"equity": eq, "equity_krw": eq / 100, "roe": sB["ni"] / eq * 100 if sB.get("ni") is not None and eq else None, "asof": f"{D.B['year']}-12-31"}
    peers = []
    for firm, f in D.subfin.items():
        if firm == HOME:
            continue
        for name, s in (f.get("subs") or {}).items():
            if s.get("country") != KOR[c] or not BROKER_NAME_RE.search(name) or NOT_BROKER_RE.search(name) or not s.get("equity") or not s.get("rev"):
                continue
            peers.append({"equity": s["equity"], "equity_krw": s["equity"] / 100, "firm": firm})
    loc = [r["ni"] / r["equity"] * 100 for r in (D.listed.get(LAND[c]) or {}).get("rows", [])
           if r.get("equity") and r.get("ni") is not None and not r.get("stale")]
    return own, peers, loc, "subfin"


def injection(D, key):
    """최근 출자(DART 타법인출자현황 기중 취득). 처음 공시된 보고서부터 365일 기억한다.

    기중 취득은 연초 이후 누적이라 3분기·사업보고서가 같은 출자를 다시 싣는다 → 같은 해·같은 금액이면
    처음 공시 날짜를 그대로 둔다."""
    inv = D.subs.get("invest") or {}
    row = (inv.get("rows") or {}).get(key) or {}
    rep = inv.get("report") or {}
    old = (D.state.get("injection") or {}).get(key)
    if (row.get("chg_amount") or 0) > 0:
        year = (D.L or {}).get("year")
        if old and old.get("amount") == row["chg_amount"] and (old.get("year") or str(old.get("rcept_dt", ""))[:4]) == str(year):
            return old if D.age(old.get("rcept_dt")) <= 365 else None
        return {"amount": row["chg_amount"], "rcept_no": rep.get("rcept_no"), "rcept_dt": rep.get("rcept_dt"),
                "report": rep_name({"report": rep}), "period": (D.L or {}).get("label"), "year": year}
    if old and D.age(old.get("rcept_dt")) <= 365:
        return old
    return None


def loss(D, key):
    s = D.sub(D.L, key)
    return s.get("ni") is not None and s["ni"] < 0


def flows(D, key):
    """(rev_g, cost_g, cir): 최신 기간과 FY의 반기·연 환산 비교."""
    L, B = D.sub(D.L, key), D.sub(D.B, key)
    if None in (L.get("rev"), L.get("ni"), B.get("rev"), B.get("ni")) or not L.get("rev") or not B.get("rev"):
        return None
    f = D.L["months"] / 12
    rev_g = L["rev"] / (B["rev"] * f) - 1
    cost_B = B["rev"] - B["ni"]
    cost_g = (L["rev"] - L["ni"]) / (cost_B * f) - 1 if cost_B > 0 else None
    cir = (L["rev"] - L["ni"]) / L["rev"]
    return rev_g, cost_g, cir


def r01_text(D, c, variant, cond=""):
    lab = D.label(BROKER[c])
    if variant == "acquire-gated":
        return f"{lab}의 현지 증권사 지분 인수는 {cond} 이후로 미루고, 후보 검토만 먼저 해 둘 만합니다."
    return f"{lab}은 증자만으로는 격차가 커, 현지 증권사 지분 인수로 규모·수익을 함께 키우는 방안을 검토할 만합니다."


def r04_text(c, variant, cond=""):
    if variant == "gated":
        return f"{KOR[c]} 현지 증권사 인수는 원화 비용이 낮아졌어도 {cond} 이후로 미루고, 후보 검토만 먼저 해 둘 만합니다."
    return f"{KOR[c]} 원화 기준 인수 비용이 크게 낮아진 구간이라, 현지 증권사 인수 후보 검토를 시작할 만합니다."


def mkt_text(D, c, mode, top=None):
    lab = D.label(BROKER[c])
    return {"reallocate": f"{lab} 고정비 절감분을 모바일 온보딩·디지털 수수료 프로모션에 재배분해 점유율 회복을 검토할 만합니다.",
            "targeted": f"{lab}은 전면 수수료 인하 대신 은행·핀테크 제휴와 타깃 프로모션으로 신규 고객 유입을 늘리는 방안을 검토할 만합니다.",
            "aggressive": f"{lab} 신규 계좌 유치 이벤트·수수료 프로모션을 공격적으로 확대하는 방안을 검토할 만합니다."}.get(mode) or \
        {"R16": f"모바일 온보딩·디지털 채널 제휴로 {lab} 신규 고객 유입 확대를 검토할 만합니다.",
         "R17": f"{lab}은 한국계 경쟁사와 겹치지 않는 고객군을 겨냥한 타깃 프로모션을 검토할 만합니다.",
         "R15": f"반등 구간에 맞춰 {lab} 신규 계좌 유치 이벤트를 진행하는 방안을 검토할 만합니다."}[top]


def r01_scale(D, c, ctx):
    key = BROKER[c]
    if injection(D, key) or loss(D, key):
        return None
    own, peers, loc, src = own_and_peers(D, c)
    if not own or len(peers) < 3:
        return None
    med = median(p["equity"] for p in peers)
    ratio = own["equity"] / med
    published = ctx["published"].get("R01")
    if ratio >= (0.55 if published else 0.50):
        return None
    allr = sorted([own["equity"]] + [p["equity"] for p in peers], reverse=True)
    rank, n_all = allr.index(own["equity"]) + 1, len(allr)
    lroe = median(loc) if len(loc) >= 4 else None
    thr = 0.75 if ((published or {}).get("variant") or "").startswith("acquire") else 0.7
    acquire = lroe is not None and own.get("roe") is not None and own["roe"] < thr * lroe
    lab = D.label(key)
    med_krw = median(p["equity_krw"] for p in peers if p.get("equity_krw") is not None)
    ev = [f"FY{own['asof'][:4]} 자기자본 {own['equity_krw']:,.0f}억원, 한국계 {n_all}사 중 {rank}위(당사 제외 중간값 {med_krw:,.0f}억원, DART)"]
    if acquire:
        ev.append(f"ROE {own['roe']:.1f}% vs 현지 상장사 {len(loc)}곳 중간값 {lroe:.1f}%")
        return cand("R01", "M&A·지분", 9, r01_text(D, c, "acquire"), ev, [key], "acquire", ("acquire", rank, n_all), ratio=ratio)
    text = f"{lab} 자기자본이 한국계 {n_all}사 중 {rank}위라, 증자 규모와 시점을 검토할 만합니다."
    return cand("R01", "자본", 8, text, ev, [key], "inject", ("inject", rank, n_all), ratio=ratio)


def r02_peer_capital(D, c):
    pool = {}
    for it in D.news_items():
        if KOR[c] in it.get("title", "") or (c == "ID" and "인니" in it.get("title", "")):
            if HOME not in (it.get("firms") or []):
                pool[it["url"]] = it
    for it in D.hub_items(c, home=False):
        pool.setdefault(it["url"], it)
    hits, titles = [], set()
    for it in sorted(pool.values(), key=lambda i: i.get("date", ""), reverse=True):
        if D.age(it.get("date")) > 45 or not CAPITAL_RE.search(it.get("title", "")) or HOME in it.get("title", ""):
            continue
        t = re.sub(r"\W", "", it["title"])[:30]
        if t in titles:
            continue
        titles.add(t)
        hits.append(it)
    if not hits:
        return None
    head = next((i for i in hits if CAPITAL_HEAD_RE.search(i["title"])), hits[0])
    dates = sorted(i["date"] for i in hits)
    span = f"{md(dates[0])}~{md(dates[-1])}" if dates[0] != dates[-1] else md(dates[0])
    lab = news_label(head["title"], head.get("src", ""))
    lead = f"국내 보도 '{lab}'" if lab else f"{head.get('src', '')} {md(head.get('date'))} 보도"
    # 라벨이 없으면 앞말에 이미 날짜가 있으니 한 건일 때 괄호에 다시 쓰지 않는다
    ev = lead + (f" 등 {len(hits)}건({span}, 최근 45일)" if len(hits) > 1 else f"({span}, 최근 45일)" if lab else "(최근 45일)")
    key = BROKER[c]
    text = f"한국계 경쟁사의 {KOR[c]} 자본 확충·점유율 경쟁에 맞서 {D.label(key)} 증자 규모와 시점을 검토할 만합니다."
    return cand("R02", "자본", 6, text, [ev], [key], driver=d(dates[-1]), links=[link(head)], urls=[i["url"] for i in hits], hits=hits)


def r03_partner(D, c, fired):
    if not D.land or LAND[c] not in D.land or (fired.get("R01") or {}).get("variant") == "acquire":
        return None
    # 가격 수집이 하루 실패해도(val_stale) 마지막 가격을 그대로 쓴다: 종목 수가 흔들려 문구가 바뀌지 않게
    nb = [r for r in D.land[LAND[c]].get("rows", []) if r.get("kind") == "local" and r.get("mcap_krw") and not BANK_RE.search(r.get("name", ""))]
    fin = (D.dl.get("firms") or {}).get(HOME, {})
    hw = (fin.get("financials") or {}).get("equity")
    if not nb or not hw:
        return None
    hw_eok = hw / 100
    lo, hi = min(r["mcap_krw"] for r in nb), max(r["mcap_krw"] for r in nb)
    if lo <= 0.5 * hw_eok:
        return None
    pds = sorted(r.get("price_date") or "" for r in nb if r.get("price_date"))
    pdate = (md(pds[0]) if pds[0] == pds[-1] else f"{md(pds[0])}~{md(pds[-1])}") if pds else ""
    hw_label = (fin.get("financials_report") or {}).get("label", "")
    span = f"{lo / 1e4:.1f}~{hi / 1e4:.1f}조원" if len(nb) > 1 else f"{lo / 1e4:.1f}조원"
    ev = f"{EXCHANGE[c]} 상장 증권사 {len(nb)}곳 시가총액 {span}" + (f"({pdate} 주가)" if pdate else "") + \
        f" vs 당사 자기자본 {hw_eok / 1e4:.2f}조원({hw_label} 연결, DART)"
    key = BROKER[c]
    text = f"{D.label(key)}은 현지 상장사 인수 부담이 커, 지분 인수보다 제휴·JV형 확장을 우선 검토할 만합니다."
    return cand("R03", "M&A·지분", 7, text, [ev], [key])


def r04_entry(D, c):
    ix = D.ix(c)
    fx = (D.macro.get("fx") or {}).get(CCY[c]) or {}
    dd = drawdown(ix, 13)
    if dd is None or fx.get("ytd_pct") is None or chg(ix, "YTD") is None:
        return None
    krw = (1 + chg(ix, "YTD") / 100) * (1 + fx["ytd_pct"] / 100) - 1
    if not (dd <= -0.20 and krw <= -0.25):
        return None
    ev = (f"{IX_SHORT[c]} {ix['close']:,.0f}({md(ix['date'])}), 최근 1년 고점({peak_month(ix, 13)} 월말) 대비 {sgn(dd * 100)} · "
          f"{CCY_NAME[CCY[c]]} 원화 대비 연초 이후 {sgn(fx['ytd_pct'])}(ECOS {md(fx['last'][0])}) · 원화 환산 지수 연초 대비 {sgn(krw * 100)}")
    return cand("R04", "M&A·지분", 8, r04_text(c, "open"), [ev], KEYS[c], "open", dd=dd, krw=krw)


def r05_post_injection(D, c):
    out = []
    for key in KEYS[c]:
        inj = injection(D, key)
        L, B = D.sub(D.L, key), D.sub(D.B, key)
        if not inj or not loss(D, key) or not B.get("rev") or not L.get("rev"):
            continue
        eq_L, eq_B = L["assets"] - L["liab"], B["assets"] - B["liab"]
        ry_L = L["rev"] * (12 / D.L["months"]) / eq_L
        ry_B = B["rev"] / eq_B
        if ry_L >= 0.5 * ry_B:
            continue
        ev = (f"{inj.get('period') or D.L['label']} 중 출자 {eok(inj['amount'])}(DART {inj.get('report') or rep_name(D.L)} 타법인출자현황) 후 "
              f"자본 대비 매출 {ry_L * 100:.1f}%({D.L['label']} 연환산) vs FY{D.B['year']} {ry_B * 100:.1f}%")
        text = f"{D.label(key)} 증자 자금은 한 번에 쓰기보다 단계별로 나눠 집행하고, 분기마다 매출 성과를 점검할 만합니다."
        out.append(cand("R05", "자본", 7, text, [ev], [key], bucket=(inj["amount"],), driver=d(inj["rcept_dt"]), injection=inj))
    return out


def r06_cross_sell(D, c):
    if c != "ID" or "CAM" not in D.ents:
        return None
    first = d(((D.subs.get("invest") or {}).get("rows") or {}).get("CAM", {}).get("first_date"))
    if not first or (D.today - first).days > 730:
        return None
    pol = D.policy("ID")
    rate_up = bool(pol and (pol.get("d1y_bp") or 0) >= 50 and (pol.get("now") or 0) >= 5.0)
    L = D.sub(D.L, "CAM")
    if not (rate_up or (L.get("ni") is not None and L["ni"] < 0)):
        return None
    nxt = next((e for e in sorted(D.cal.get("events", []), key=lambda e: e["date"]) if e.get("bank") == "ID" and d(e["date"]) >= D.today), None)
    ev = []
    if pol:
        nxt_txt = f", 다음 결정 {md(nxt['date'])}" if nxt else ""
        ev.append(f"BI 기준금리 {pol['now']:.2f}%({pol['month']} 기준, 1년 {pol['d1y_bp']:+d}bp{nxt_txt})")
    if L.get("rev") is not None and L.get("ni") is not None:
        ev.append(f"{D.label('CAM')} {D.L['label']} 매출 {eok(L['rev'])}·순{'손실' if L['ni'] < 0 else '이익'} {eok(abs(L['ni']))}(DART)")
    a, b = D.label("CAM"), D.label("CSA")
    if rate_up:
        text = f"BI 고금리 국면에 맞춰 {a} 채권형·MMF를 {b} 고객에게 교차판매하는 방안을 검토할 만합니다."
    else:
        text = f"{a} 펀드를 {b} 고객에게 교차판매하는 목표 설정을 검토할 만합니다."
    return cand("R06", "상품·제휴", 7, text, ev, ["CAM", "CSA"], "rate-up" if rate_up else "base", (pol and pol.get("now"),))


def r07_r08_struct(D, c):
    regime, pos, neg = struct(D, c)
    if not regime:
        return None
    ix = D.ix(c)
    key = BROKER[c]
    if regime == "POS":
        deriv = any(DERIV_RE.search(i["title"]) for i in pos)
        note = next((n[1] for n in D.ents.get(key, {}).get("notes", []) if re.search(r"FTSE|MSCI", n[1])), "")
        nd = re.search(r"\d{4}-\d{2}-\d{2}", note)
        note_short = f"FTSE 신흥시장 편입 {nd.group(0)} 발효" if nd and "FTSE" in note else ""
        head = pos[0]
        ev = [note_short, cite(head) + more(len(pos), "구조 뉴스", "최근 30일")]
        if deriv:
            lead = "FTSE 편입" if note_short else f"{KOR[c]} 파생상품 시장 확대"
            text = f"{lead}에 맞춰 {D.label(key)}의 외국인 기관 영업과 지수옵션 등 파생상품 준비를 검토할 만합니다."
        else:
            text = f"{KOR[c]} 시장 지위 상향에 맞춰 {D.label(key)}의 외국인 기관 영업·영문 리서치 강화를 검토할 만합니다."
        return cand("R07", "상품·제휴", 8, text, ev, [key], "deriv" if deriv else "base", ("POS",), driver=d(head["date"]),
                    links=[link(i) for i in pos[:2]], urls=[i["url"] for i in pos])
    head = neg[0]
    event = neg_event(pos, neg)
    text, short = r08_text(D, c, event)
    ev = [cite(head) + more(len(neg), "부정 구조 뉴스", "최근 30일")]
    if ix and chg(ix, "1M") is not None and chg(ix, "YTD") is not None:
        ev.append(f"{IX_SHORT[c]} 1개월 {sgn(chg(ix, '1M'))}, 연초 대비 {sgn(chg(ix, 'YTD'))}({md(ix['date'])})")
    return cand("R08", RISK, 9, text, ev, KEYS[c], "NEG", ("NEG", event), driver=d(head["date"]),
                links=[link(i) for i in neg[:2]], urls=[i["url"] for i in neg], event=event, short=short)


def arts(i):
    """사건 하나에 합쳐진 기사들의 (제목, 날짜)."""
    return [(i["title"], i.get("date", ""))] + [(x["title"], x.get("date", "")) for x in i.get("same", [])]


def neg_event(pos, neg):
    """악재 국면 줄의 '○○ 전까지': 걸린 MSCI 결정 > 걸린 FTSE 재분류 > 시장 불안 진정."""
    return "MSCI 결정" if pending(pos, neg, "MSCI") else "FTSE 재분류" if pending(pos, neg, "FTSE") else "시장 불안 진정"


def r08_text(D, c, event):
    """악재 국면 줄 문구와, 같은 나라에 '인수는 미루고 후보 검토만' 줄이 함께 뽑힐 때 쓰는 짧은 문구(같은 말 반복 방지)."""
    credit = [k for k in KEYS[c] if "신용공여" in D.ents.get(k, {}).get("focus", "")]
    limit = f"{D.labels(credit)} 신용공여 한도" if credit else "리스크 한도"
    text = f"{event} 전까지 {KOR[c]} 신규 출자·인수는 속도를 조절하고, {limit}를 점검할 만합니다."
    short = f"{event} 전까지 {limit}와 담보 비율을 보수적으로 점검할 만합니다." if credit else f"{event} 전까지 {limit}를 보수적으로 점검할 만합니다."
    return text, short


def pending(pos, neg, prov):
    """prov(MSCI·FTSE)의 결정이 아직 걸려 있나: 그 기관의 마지막 결정(강등 확정·우려 해소·호재) 뒤에 나온 악재 기사가
    그 기관의 분류·강등 결정을 앞으로의 일로 말할 때만. 결정 뒤 후속 기사('… after MSCI downgrade', 'MSCI's downgrade could
    trigger outflows')나 결정 전 경고 기사는 세지 않는다. 결정 뒤에는 추가 검토·의견수렴처럼 새 단계를 말하는 기사만 센다.
    같은 날짜면 결정 쪽을 따른다(피드·보관함 순서에 따라 결과가 바뀌지 않게)."""
    done = max([dt for i in pos for t, dt in arts(i) if prov in t and decided_by(t) in ("", prov)] +
               [dt for i in neg for t, dt in arts(i) if decided_by(t) == prov], default="")
    return any(dt > done and prov in t and decided_by(t) != prov and PENDING_RE.search(t) and DECISION_CTX_RE.search(t)
               and not (AFTER_UP_RE.search(t) and not DOWN_CTX_RE.search(t)) and (not done or NEW_STEP_RE.search(t))
               for i in neg for t, dt in arts(i))


def fx_pair(D, c):
    fx = (D.macro.get("fx") or {})
    y, yu = (fx.get(CCY[c]) or {}).get("ytd_pct"), (fx.get("USD") or {}).get("ytd_pct")
    rows = {r["ccy"]: r for r in (D.mk.get("fx") or {}).get("rows", [])}
    w, wu = (rows.get(CCY[c]) or {}).get("chg_1w"), (rows.get("USD") or {}).get("chg_1w")
    vs_usd = ((1 + y / 100) / (1 + yu / 100) - 1) * 100 if None not in (y, yu) else None
    w_usd = ((1 + w / 100) / (1 + wu / 100) - 1) * 100 if None not in (w, wu) else None
    return y, vs_usd, w_usd


def r09_fx(D, c, ctx):
    y, vs_usd, w_usd = fx_pair(D, c)
    if y is None or vs_usd is None:
        return None
    # 게시 중인 '추세' 줄은 달러 대비 -3%까지 유지(문턱 근처에서 깜빡이지 않게). '단기' 줄은 이틀 유예로만
    exit_ok = (ctx["published"].get("R09") or {}).get("variant") == "trend" and vs_usd <= -3
    trend = (y <= -10 and vs_usd <= -5) or exit_ok
    week = w_usd is not None and w_usd <= -1.5
    if not (trend or week):
        return None
    fx = D.macro["fx"][CCY[c]]
    unit = re.search(r"\((\d+)\D*\)", fx.get("name", ""))
    ev = f"원/{CCY_NAME[CCY[c]]} {fx['last'][1]:,}원({unit.group(1) + CCY_NAME[CCY[c]] + ' 기준, ' if unit else ''}ECOS {md(fx['last'][0])}), 연초 대비 {sgn(y)}·달러 대비 {sgn(vs_usd)}"
    if week:
        ev += f" · 최근 1주 달러 대비 {sgn(w_usd)}"
    name = CCY_NAME[CCY[c]]
    text = f"{name} {'' if trend else '단기 '}약세에 대비해 {D.labels(KEYS[c])} 원화 환산 손익 관리와 환헤지 방안을 점검할 만합니다."
    return cand("R09", RISK, 6, text, [ev], KEYS[c], "trend" if trend else "week")


def r10_reg(D, c, struct_urls):
    pool = []
    for it in D.macro_items():
        if c in countries_of(it["title"]) and D.age(it.get("date")) <= 60 and reg_hit(it["title"]):
            pool.append(it)
    for it in D.hub_items(c, home=False):
        if D.age(it.get("date")) <= 180 and reg_hit(it["title"]):
            pool.append(it)
    for it in D.news_items():
        if KOR[c] in it.get("title", "") and D.age(it.get("date")) <= 60 and reg_hit(it["title"]) and HOME not in it["title"]:
            pool.append(it)
    if not pool:
        return None
    pool.sort(key=lambda i: i.get("date", ""), reverse=True)
    if D.age(pool[0]["date"]) > 30:
        return None
    head = next((i for i in pool if i["url"] not in struct_urls), pool[0])
    t = head["title"]
    variant = "시세조종 단속 강화" if re.search(r"manipulat|시세조종", t, re.I) else \
        "고객 대상 사기 증가" if re.search(r"fraud|scam|사기", t, re.I) else "감독당국 제재 사례"
    who = f"{head['firm']} {KOR[c]} 법인 " if head.get("firm") else ""
    ev = cite(head, who) + (f" 등 {len(pool)}건" if len(pool) > 1 else "")
    what = {"시세조종 단속 강화": "이상거래 모니터링과 주문 감시 체계", "고객 대상 사기 증가": "고객 사기 방지와 이상거래 모니터링 체계"}.get(variant, "내부통제·준법 체계")
    text = f"{variant}에 맞춰 {D.labels([k for k in KEYS[c] if 'IB' in D.ents.get(k, {}).get('focus', '') or k == BROKER[c]])} {what}를 점검할 만합니다."
    return cand("R10", RISK, 6, text, [ev], [BROKER[c]], variant, (variant,), driver=d(head["date"]), links=[link(head)], urls=[i["url"] for i in pool])


def ix_window(ix, D):
    """최신 손익 기간과 같은 기간의 지수 등락(%): 전년 12월 말 → 기간 말 월말 종가."""
    if not ix or not D.L or not D.L.get("year") or not D.L.get("months"):
        return None
    m = {k: v for k, v in ix.get("monthly", []) if isinstance(v, (int, float))}
    y = int(D.L["year"])
    a, b = m.get(f"{y - 1}-12"), m.get(f"{y}-{int(D.L['months']):02d}")
    return (b / a - 1) * 100 if a and b else None


def r11_loss(D, c):
    out = []
    ix = D.ix(c)
    for key in KEYS[c]:
        L, B = D.sub(D.L, key), D.sub(D.B, key)
        if not loss(D, key) or B.get("ni") is None:
            continue
        fl = flows(D, key)
        cir = fl[2] if fl else None
        widen = B["ni"] < 0 and (L["ni"] * 12 / D.L["months"] < B["ni"] or (cir is not None and cir >= 3.0))
        flip = B["ni"] > 0
        if not (flip or widen):
            continue
        lab = D.label(key)
        b_txt = f"순이익 {eok(B['ni'])}" if B["ni"] >= 0 else f"순손실 {eok(-B['ni'])}"
        ev = [f"{D.L['label']} 순손실 {eok(-L['ni'])}(FY{D.B['year']} {b_txt}), 매출 {eok(L['rev'])}(DART {rep_name(D.L)})"]
        iw = ix_window(ix, D)
        if fl and iw is not None and iw >= 5 and fl[0] <= -0.10:
            ev.append(f"{IX_SHORT[c]} {D.L['label']} {sgn(iw)}에도 같은 기간 매출은 {base_label(D)} {sgn(fl[0] * 100)}")
        if flip:
            text = f"{lab} 적자 전환에 따라 고정비 중심의 인력·조직 효율화를 검토할 만합니다."
            out.append(cand("R11", "구조조정·비용", 9, text, ev, [key], "flip", ("flip",), driver=d(D.L["report"].get("rcept_dt")), cir=cir, rev_g=fl and fl[0]))
        else:
            focus = [x.strip() for x in D.ents.get(key, {}).get("focus", "").split(",") if x.strip()]
            mult = f"비용이 매출의 {cir:.1f}배라" if cir is not None and cir >= 3 else "적자 폭이 커져"
            # 사업이 하나뿐이면 '핵심 사업' 구분이 없으니, 고정비를 매출 규모에 맞추는 쪽으로만 말한다
            how = f"핵심인 {focus[0]} 중심으로 고정비를 줄이는" if len(focus) > 1 else "고정비를 매출 규모에 맞추는"
            text = f"{lab}{josa(lab, '은', '는')} {mult}, {how} 조직 축소·재편을 검토할 만합니다."
            out.append(cand("R11", "구조조정·비용", 9, text, ev, [key], "widen", ("widen",), driver=d(D.L["report"].get("rcept_dt")), cir=cir, rev_g=fl and fl[0]))
    return out


def peer_margin(D, c, year=None):
    ms = []
    for firm, f in D.subfin.items():
        if firm == HOME or (year and not str(f.get("report") or "").startswith(str(year))):
            continue
        for name, s in (f.get("subs") or {}).items():
            if s.get("country") == KOR[c] and BROKER_NAME_RE.search(name) and not NOT_BROKER_RE.search(name) and (s.get("rev") or 0) > 0 and (s.get("ni") or 0) > 0:
                ms.append(s["ni"] / s["rev"])
    return (median(ms), len(ms)) if len(ms) >= 3 else (None, len(ms))


def r12_jaws(D, c, ctx):
    out = []
    for key in KEYS[c]:
        L = D.sub(D.L, key)
        fl = flows(D, key)
        if not fl or L.get("ni") is None or L["ni"] <= 0 or fl[1] is None:
            continue
        rev_g, cost_g, _ = fl
        jaws = (rev_g - cost_g) * 100
        published = (ctx["published"].get("R12") or {})
        if not ((jaws <= -5 and cost_g > 0) or (published and jaws <= -2)):
            continue
        ev = [f"{D.L['label']} 비용 {sgn(cost_g * 100)} vs 매출 {sgn(rev_g * 100)}({base_label(D)}, DART)"]
        # 같은 시점끼리(경쟁사가 읽은 사업보고서 해의 FY) 비교하고, 최신 기간 값이 그 FY가 아니면 시점을 붙여 덧붙인다
        py_rep = D.peer_year()
        py = py_rep or (D.B or {}).get("year")
        P = D.fy(py) if py else None
        m_p, n = peer_margin(D, c, py_rep) if P else (None, 0)
        B = D.sub(P, key)
        if m_p is not None and B.get("rev") and B.get("ni") is not None and B["ni"] / B["rev"] < m_p:
            latest = "" if P is D.L else f"·{D.L['label']} {L['ni'] / L['rev'] * 100:.1f}%"
            ev.append(f"순이익률 FY{py} {B['ni'] / B['rev'] * 100:.1f}%{latest} vs 한국계 흑자 {n}사 FY{py} 중간값 {m_p * 100:.1f}%")
        text = f"{D.label(key)} 비용 증가율을 매출 증가율 이하로 묶는 비용 상한 관리를 검토할 만합니다."
        out.append(cand("R12", "구조조정·비용", 8, text, ev, [key], bucket=(math.floor(jaws / 5),), driver=d(D.L["report"].get("rcept_dt")), jaws=jaws))
    return out


def r13_shared(D, c):
    keys = [k for k in KEYS[c] if loss(D, k)]
    if len(keys) < 2:
        return None
    Ls = [D.sub(D.L, k) for k in keys]
    sum_ni = sum(s["ni"] for s in Ls)
    sum_rev = sum(s["rev"] or 0 for s in Ls)
    sum_cost = sum((s["rev"] or 0) - s["ni"] for s in Ls)
    ev = [f"{D.L['label']} 두 법인 순손실 {eok(-sum_ni)}, 비용 {eok(sum_cost)} vs 매출 {eok(sum_rev)}(DART {rep_name(D.L)})"]
    for k in keys:
        B = D.sub(D.B, k)
        if B.get("ni") is not None and B["ni"] > 0:
            ev.append(f"{D.label(k)} FY{D.B['year']} 순이익 {eok(B['ni'])}에서 적자 전환")
    text = f"{D.labels(keys)} 백오피스·IT·준법 통합으로 중복 고정비 축소를 검토할 만합니다."
    return cand("R13", "구조조정·비용", 9, text, ev, keys, bucket=(len(keys), round(sum_ni / 500)), driver=d(D.L["report"].get("rcept_dt")))


def r14_volume(D, c):
    if c != "ID":
        return None
    ix = D.ix(c)
    fl = flows(D, BROKER[c])
    adtv = None
    if D.idx and D.idx.get("month") and D.idx.get("ytd"):
        mo, yt = D.idx["month"], D.idx["ytd"]
        if mo.get("days") and yt.get("days"):
            adtv = (mo["total"] / mo["days"]) / (yt["total"] / yt["days"]) - 1
    ytd = chg(ix, "YTD")
    if not ((adtv is not None and adtv <= -0.15) or (ytd is not None and ytd <= -20)) or not fl or fl[0] >= 0:
        return None
    if adtv is not None:
        fact = f"IDX {D.idx['month']['month']} 일평균 거래대금 연초 이후 평균 대비 {sgn(adtv * 100, 0)}(IDX 회원사 집계)"
    else:
        fact = f"{IX_SHORT[c]} 연초 대비 {sgn(ytd)}({md(ix['date'])})"
    text = f"{D.label(BROKER[c])} 영업망은 유지하되 성과연동 보상 등 변동비 전환을 검토할 만합니다."
    return cand("R14", "구조조정·비용", 6, text, [fact], [BROKER[c]], bucket=(adtv is not None and adtv <= -0.15,), fact=fact)


def r15_momentum(D, c, regime):
    if c not in ("VN", "ID") or regime == "NEG" or "브로커리지" not in D.ents.get(BROKER[c], {}).get("focus", ""):
        return None
    ix = D.ix(c)
    if not ix:
        return None
    ch = {k: chg(ix, k) for k in ("1W", "1M", "3M")}
    if None in ch.values():
        return None
    dd = drawdown(ix, 12)
    tier = "A" if ch["3M"] >= 5 and ch["1M"] >= 0 else \
        "B" if ch["1W"] >= 3 and ch["3M"] >= 0 and dd is not None and dd >= -0.08 else None
    if not tier:
        return None
    fact = f"{IX_SHORT[c]} 1주 {sgn(ch['1W'])}·3개월 {sgn(ch['3M'])}({md(ix['date'])})" + (f", {peak_month(ix, 12)} 고점 대비 {sgn(dd * 100)}" if dd is not None else "")
    return cand("R15", "마케팅·고객", 5, "", [fact], [BROKER[c]], tier, (tier,), fact=fact)


def r16_digital(D, c):
    if c == "ID":
        if D.idx and D.idx.get("month"):
            rows = {r["code"]: r for r in D.idx["month"]["rows"]}
            dig = sum((rows.get(k) or {}).get("share", 0) for k in ("XL", "XC", "PD"))
            xl = rows.get("XL") or {}
            if dig < 15 and xl.get("rank") != 1:
                return None
            ki = rows.get("KI")
            fact = f"IDX {D.idx['month']['month']} 거래대금 점유율 디지털 3사 {dig:.1f}%(Stockbit {xl.get('rank')}위 {xl.get('share', 0):.1f}%)" + \
                (f" vs {D.label('CSA')} {ki['share']:.2f}%({ki['rank']}위)" if ki else "")
            drv = month_end(D.idx["month"]["month"]) + timedelta(days=1)
            return cand("R16", "마케팅·고객", 7, "", [fact], ["CSA"], bucket=(round(dig), xl.get("rank")), driver=drv, fact=fact)
        t = ((D.gmk.get("id") or {}).get("tables") or [{}])[0]
        top = (t.get("rows") or [{}])[0]
        if not re.search(r"Digital", top.get("name", "")):
            return None
        fact = f"IDX 거래대금 1위는 디지털 증권사 {top['name'].split(' (')[0]}({top['value']:,.1f}조 루피아, {t.get('basis', '')})"
        return cand("R16", "마케팅·고객", 7, "", [fact], ["CSA"], bucket=(top["name"],), fact=fact)
    if c == "VN":
        t = ((D.gmk.get("vn") or {}).get("tables") or [None])[0]
        if not t:
            return None
        bm = re.search(r"(\d{4})-(\d{2})", t.get("basis", ""))
        if not bm or (D.today - month_end(bm.group(0))).days > 120:
            return None
        rec = [r for r in t["rows"] if re.search(r"최고", r.get("note", ""))]
        if len(rec) < 2:
            return None
        q = re.search(r"\((\w+)\)", t.get("title", ""))
        fact = f"HOSE {q.group(1) if q else ''} 점유율 {rec[0]['name'].split(' (')[0]} {rec[0]['value']}%·{rec[1]['name']} {rec[1]['value']}%로 최고치({t['basis']})"
        return cand("R16", "마케팅·고객", 7, "", [fact], ["VN"], bucket=(t["basis"],), driver=month_end(bm.group(0)), fact=fact)
    return None


def r17_share_gap(D, c):
    if c == "VN":
        t = ((D.gmk.get("vn") or {}).get("tables") or [None])[0]
        if not t or any(re.search(r"Pinetree", r["name"], re.I) for r in t["rows"]):
            return None
        kr = [r for r in t["rows"] if r.get("korean")]
        if not kr:
            return None
        q = re.search(r"\((\w+)\)", t.get("title", ""))
        thr = min(r["value"] for r in t["rows"])
        fact = f"HOSE {q.group(1) if q else ''} 10위 진입선 {thr}%에 한국계 {len(kr)}곳, {D.label('VN')}은 10위 밖({t['basis']})"
        return cand("R17", "마케팅·고객", 6, "", [fact], ["VN"], "vn", (t["basis"],), fact=fact, korean=len(kr))
    if c == "ID" and D.idx and D.idx.get("trend"):
        tr = D.idx["trend"]
        own = tr.get("KI")
        if not own:
            return None
        cur = (D.idx.get("last_day") or "")[:7]

        def clean(pts):
            xs = [p for p in pts if p[0] != cur]
            if not xs:
                return [], None
            m0 = median(p[1] for p in xs)
            out = [p for p in xs if p[1] <= 3 * m0]
            return out, [p[0] for p in xs if p[1] > 3 * m0]
        pts, outl = clean(own["pts"])
        if len(pts) < 4:
            return None
        mshare = median(p[1] for p in pts)
        peer_top = max((median(p[1] for p in clean(v["pts"])[0]) for k, v in tr.items() if k != "KI" and clean(v["pts"])[0]), default=None)
        if not peer_top or not (mshare < 1.0 and mshare / peer_top < 0.33):
            return None
        s3 = sum(p[1] for p in pts[-3:]) / 3
        base = [p for p in pts[:-3] if p[0][5:7] <= "06" and p[0][:4] == pts[-1][0][:4]]
        s1h = sum(p[1] for p in base) / len(base) if base else None
        delta = s3 - s1h if s1h is not None else 0
        variant = "improving" if delta >= 0.15 else "falling" if delta <= -0.15 else "flat"
        span = lambda a, b: f"{int(a[0][5:7])}~{int(b[0][5:7])}월" if a != b else f"{int(a[0][5:7])}월"
        months = span(pts[-3], pts[-1])
        fact = f"{D.label('CSA')} IDX 점유율 {months} 평균 {s3:.2f}%" + (f", {span(base[0], base[-1])} {s1h:.2f}%" if s1h is not None else "") + \
            (f"({', '.join(o[5:7].lstrip('0') + '월' for o in outl)} 일회성 제외, IDX 회원사 집계)" if outl else "(IDX 회원사 집계)")
        return cand("R17", "마케팅·고객", 6, "", [fact], ["CSA"], variant, (variant,), fact=fact)
    return None


def r18_rwa(D, c):
    hits = [i for i in D.hub_items(c, home=True) if D.age(i.get("date")) <= 180 and RWA_RE.search(i.get("title", ""))]
    if not hits:
        return None
    m = next((x for x in (D.digi or {}).get("markets", []) if x.get("code") == c), None)
    sto = ((m or {}).get("status") or {}).get("sto") or {}
    if D.digi is not None and sto.get("lv") != "ok":
        return None
    head = sorted(hits, key=lambda i: i["date"], reverse=True)[0]
    key = BROKER[c]
    ev = [f"{head.get('src', '')} {d(head['date']).isoformat()} '{head['title']}'"]
    if sto:
        ev.append(f"{KOR[c]} 토큰증권 제도 {sto.get('short', '')} 시행 중(디지털자산 규제 탭)")
    focus = [x.strip() for x in D.ents.get(key, {}).get("focus", "").split(",") if x.strip()]
    biz = next((x for x in focus if "IB" in x), focus[0] if focus else "자문·IB")
    text = f"보도된 RWA 협력을 {D.label(key)} {biz} 상품으로 잇는 저비용 사업화를 검토할 만합니다."
    return cand("R18", "상품·제휴", 5, text, ev, [key], bucket=(head["url"],), driver=d(head["date"]), links=[link(head, "보도")], urls=[head["url"]])


def fallbacks(D, c):
    out = []
    key = BROKER[c]
    own, peers, _, _ = own_and_peers(D, c)
    L = D.sub(D.L, key)
    if own and peers and L.get("assets"):
        eq_now = (L["assets"] - L["liab"]) / 100
        allr = sorted([eq_now] + [p["equity_krw"] for p in peers if p.get("equity_krw") is not None], reverse=True)
        rank = allr.index(eq_now) + 1
        med = median(p["equity_krw"] for p in peers if p.get("equity_krw") is not None)
        ev = f"{D.L['label']} 자기자본 {eq_now:,.0f}억원(DART) vs 한국계 동종 중간값 {med:,.0f}억원(FY{own['asof'][:4]})"
        text = f"{D.label(key)} 자기자본은 한국계 {len(allr)}사 중 {rank}위로, 분기 공시마다 격차 추이를 점검할 만합니다."
        out.append(cand("F1", "자본", 2, text, [ev], [key], bucket=(rank,)))
    if L.get("assets") and L.get("ni") is not None:
        roe = L["ni"] * (12 / D.L["months"]) / (L["assets"] - L["liab"]) * 100
        pol = D.policy(c) if c != "SG" else None
        if c == "SG":
            kr = (D.macro.get("kr_base_rate") or [[None, None]])[-1]
            bank, rate, mon = "한국은행 기준금리", kr[1], f"{kr[0][:4]}-{kr[0][4:]}" if kr[0] else ""
        else:
            bank, rate, mon = pol and pol["name"], pol and pol["now"], pol and pol["month"]
        if rate is not None and roe < rate:
            ev = f"{D.L['label']} 연환산 ROE {roe:.1f}%(기말 자본 기준, DART) vs {bank} {rate:.2f}%({mon} 기준)"
            text = f"{D.label(key)} 연환산 ROE가 기준금리에 못 미쳐, 자본 효율 목표 설정을 검토할 만합니다."
            out.append(cand("F2", "구조조정·비용", 2, text, [ev], [key], bucket=(roe < 0,)))
    due = sorted((t for t in D.reg.get("todo", []) if t.get("status") != "done" and str(t.get("id", "")).startswith("periodic-") and t.get("due")),
                 key=lambda t: t["due"])
    nxt = next((e for e in sorted(D.cal.get("events", []), key=lambda e: e["date"]) if e.get("bank") == c and d(e["date"]) >= D.today), None)
    if due:
        t = due[0]
        name = re.sub(r"^한화투자증권\s*", "", t.get("item") or t.get("title") or "정기보고서").split(" 해외")[0]
        extra = f"와 {nxt['name']} 결정({md(nxt['date'])})" if nxt else ""
        text = f"다음 판단 시점은 {name}(기한 {md(t['due'])}){extra} 반영 후입니다."
        out.append(cand("F3", "일정", 1, text, ["대외보고 기한(한화투자증권 탭)" + (" · 중앙은행 결정 일정" if nxt else "")], [key],
                        bucket=(t["due"], nxt["date"] if nxt else None)))
    return out


# ---------- 조합·선택 ----------
def evaluate(D, c, published, pinned=(), floor=None):
    """나라 c의 발동 규칙 → 병합·조정 → 선택. (고른 bullet, 탈락 후보, 발동 규칙, 국면)

    pinned: 자료 공백으로 오늘 하루 안 잡힌 게시 중 bullet(상태에 남긴 무게·근거 날짜 포함). 오늘 발동한 줄과
    같은 점수로 겨룬다: 자료 공백이 없는 날과 같은 줄이 뽑히게(이틀째 안 잡히면 run()이 더는 넘기지 않는다).
    오늘의 국면·보류 조건에 맞춰 문구를 고쳐 쓰고, 어긋나는 줄은 지키지 않는다.
    floor: 게시 중 규칙의 어제 무게. 오늘 근거 일부가 빠져 무게가 내려가도 하루는 어제 무게로 겨룬다."""
    ctx = {"published": published}
    fired, extra = {}, []

    def put(x):
        if not x:
            return
        for y in (x if isinstance(x, list) else [x]):
            if y["rule"] in fired:
                extra.append(y)
            else:
                fired[y["rule"]] = y

    put(r01_scale(D, c, ctx))
    r02 = r02_peer_capital(D, c)
    put(r03_partner(D, c, fired))
    r04 = r04_entry(D, c)
    put(r05_post_injection(D, c))
    put(r06_cross_sell(D, c))
    st = r07_r08_struct(D, c)
    regime = ("NEG" if st["rule"] == "R08" else "POS") if st else None
    pin = {p["rule"]: p for p in pinned}   # 유예 중인 게시 줄도 합칠 곳(host)으로 본다(문구는 그대로)
    if regime is None:
        # 유예 중인 국면 줄이 있으면 그 국면으로 판단한다(인수 보류·마케팅 강도·반등 마케팅이 하루 공백에 뒤집히지 않게)
        regime = "NEG" if "R08" in pin else "POS" if "R07" in pin else None
    put(st)
    put(r09_fx(D, c, ctx))
    put(r10_reg(D, c, set(st.get("urls", [])) if st else set()))
    put(r11_loss(D, c))
    put(r12_jaws(D, c, ctx))
    r13 = r13_shared(D, c)
    r14 = r14_volume(D, c)
    mkt = [x for x in (r15_momentum(D, c, regime), r16_digital(D, c), r17_share_gap(D, c)) if x]
    put(r18_rwa(D, c))
    dropped, suppressed = [], set()   # suppressed: 합친 것이 아니라 조정으로 뺀 규칙(안 잡힘으로 센다)
    loss_rules = bool(fired.get("R11")) or bool(r13) or any(x["rule"] == "R11" for x in extra) or "R11" in pin or "R13" in pin
    gated = regime == "NEG" or loss_rules
    if st:
        event = st.get("event") or "시장 불안 진정"
    else:
        # 지수 공백 날은 오늘 뉴스로 다시 정하고, 마지막 악재 기사가 기간을 넘겨 빠진 날은 게시 때 말을 그대로 둔다(하루 뒤 빠질 줄을 고쳐 쓰지 않게)
        _, spos, sneg = struct(D, c)
        held = ((pin.get("R08") or {}).get("bucket") or [None, None])[-1]
        decided = held and any(decided_by(t) and held.startswith(decided_by(t)) for i in spos for t, _ in arts(i))
        event = neg_event(spos, sneg) if sneg or not held or decided else held
    if "R08" in pin:
        # 유예 중인 악재 줄도 오늘 뉴스로 '○○ 전까지'를 다시 정한다(지수 자료가 빈 날 강등 우려 해소 기사가 와도 맞게)
        t8, s8 = r08_text(D, c, event)
        pin["R08"] = {**pin["R08"], "text": t8, "short": s8, "event": event, "bucket": ["NEG", event]}
    parts = [x for x in (event if regime == "NEG" else "", "손익 회복" if loss_rules else "") if x]
    cond = f"{parts[0]}{josa(parts[0], '과', '와')} {parts[1]}" if len(parts) == 2 else (parts[0] if parts else event)
    key = BROKER[c]
    own = lambda x: (x.get("keys") or [key])[0] == key   # 옛 게시 줄에 keys 가 없으면 증권 법인으로 본다
    # 유예 중인 인수 줄은 오늘의 보류 조건에 맞춰 문구를 고쳐 쓴다(보류 없는 인수 줄 옆의 악재 줄, 보류 줄 옆의 호재 줄이 생기지 않게)
    if (pin.get("R01") or {}).get("variant", "").startswith("acquire"):
        v = "acquire-gated" if gated else "acquire"
        pin["R01"] = {**pin["R01"], "variant": v, "text": r01_text(D, c, v, cond)}
    if "R04" in pin:
        v = "gated" if gated else "open"
        pin["R04"] = {**pin["R04"], "variant": v, "text": r04_text(c, v, cond), "bucket": ["gated"] if gated else []}

    # M1 R02 → R01, 단독은 R01 없고 흑자·쿨다운 아닐 때만
    if r02:
        if "R01" in fired:
            fired["R01"]["evidence"].append(r02["evidence"][0])
            fired["R01"]["links"] += r02["links"]
            fired["R01"]["driver"] = max(filter(None, [fired["R01"]["driver"], r02["driver"]]), default=None)
            dropped.append(("R02", "R01에 합침"))
        elif "R01" in pin:
            dropped.append(("R02", "R01에 합침"))
        elif not loss(D, BROKER[c]) and not injection(D, BROKER[c]):
            fired["R02"] = r02
        else:
            dropped.append(("R02", "당사 법인 적자·증자 직후"))
            suppressed.add("R02")
    # M2·M8 R04: R01 acquire 에 합치거나, 게이트면 '실사만' 문구
    if r04:
        if (fired.get("R01") or {}).get("variant") == "acquire":
            fired["R01"]["evidence"].append(r04["evidence"][0])
            dropped.append(("R04", "R01에 합침"))
        elif (pin.get("R01") or {}).get("variant", "").startswith("acquire"):
            dropped.append(("R04", "R01에 합침"))
        else:
            if gated:
                r04["text"] = r04_text(c, "gated", cond)
                r04["variant"] = "gated"
                r04["bucket"][0:0] = ["gated"]
            fired["R04"] = r04
    if (fired.get("R01") or {}).get("variant") == "acquire" and gated:
        r = fired["R01"]
        r["text"] = r01_text(D, c, "acquire-gated", cond)
        r["variant"] = "acquire-gated"
    # M3·M4 R11 → R13, R14 → R13 > R11 > 단독
    if r13:
        r11s = [x for x in [fired.get("R11")] + extra if x and x["rule"] == "R11"]
        for x in r11s:
            if x["keys"][0] in r13["keys"]:
                dropped.append(("R11", "R13에 합침"))
        if fired.get("R11") and fired["R11"]["keys"][0] in r13["keys"]:
            del fired["R11"]
        extra[:] = [y for y in extra if not (y["rule"] == "R11" and y["keys"][0] in r13["keys"])]
        rest = next((y for y in extra if y["rule"] == "R11"), None)
        if rest and "R11" not in fired:
            fired["R11"] = rest
            extra.remove(rest)
        fired["R13"] = r13
    if r14:
        host = fired.get("R13") or (fired.get("R11") if fired.get("R11") and fired["R11"]["keys"][0] == BROKER[c] else None)
        if host:
            host["evidence"].append(r14["fact"])
            dropped.append(("R14", f"{host['rule']}에 합침"))
        elif "R13" in pin or "R11" in pin:
            dropped.append(("R14", "R13·R11에 합침"))
        else:
            fired["R14"] = r14
    # M5·M7 마케팅 한 줄. 오늘 근거가 안 잡혀 유예 중인 마케팅 줄도 같은 판단으로 모드를 다시 정한다(근거 규칙은 상태에 남긴 것)
    mp = pin.get("MKT")
    if mkt or mp:
        # 비용 규칙은 유예 중인 게시 줄도 본다(공시 파일이 하루 빠져도 마케팅 강도가 뒤집히지 않게)
        eff = lambda r: fired.get(r) or pin.get(r)
        r11k = next((x for x in [fired.get("R11")] + extra + [pin.get("R11")] if x and x["rule"] == "R11" and own(x)), None)
        r12k = eff("R12") if eff("R12") and own(eff("R12")) else None
        cost_rule = bool(r11k) or bool(eff("R13")) or bool(r12k) or bool(eff("R14"))
        mkt.sort(key=lambda x: -x["weight"])
        if mkt:
            comps = [x["rule"] for x in mkt]
            tierA = any(x["rule"] == "R15" and x["variant"] == "A" for x in mkt)
        else:
            # 반등 마케팅(R15)은 악재 국면에는 쓰지 않는다
            comps = [r for r in (mp.get("components") or []) if not (r == "R15" and regime == "NEG")]
            tierA = bool(mp.get("tierA")) and "R15" in comps
        if (r11k and r11k["variant"] == "widen") or (r11k and (r11k.get("cir") or 0) >= 3):
            mode = None
            dropped.append(("MKT", "적자 확대 법인이라 마케팅 지출 제안 안 함"))
            suppressed.add("MKT")
        elif (r11k and r11k["variant"] == "flip") or eff("R13"):
            mode = "reallocate"
        elif r12k:
            mode = "targeted"
        elif not cost_rule and (tierA or regime == "POS"):
            mode = "aggressive"
        else:
            mode = "base" if comps else None
        if mkt and mode:
            # 구간은 문구를 정하는 것만: 모드와(기본형이면) 맨 위 근거 규칙. 지수 1주 등락처럼 근거에만 쓰이는 값은 넣지 않는다
            fired["MKT"] = cand("MKT", "마케팅·고객", mkt[0]["weight"], mkt_text(D, c, mode, comps[0]), [x["fact"] for x in mkt][:3], [key], mode,
                                (comps[0],) if mode == "base" else (),
                                driver=max(filter(None, (x["driver"] for x in mkt)), default=None), components=comps, tierA=tierA)
        elif mp and not mode:
            del pin["MKT"]
        elif mp:
            pin["MKT"] = {**mp, "variant": mode, "text": mkt_text(D, c, mode, comps[0] if comps else None),
                          "bucket": [comps[0]] if mode == "base" else [], "components": comps, "tierA": tierA}

    # 점수와 선택: 유예 줄도 상태에 남긴 무게·근거 날짜로 같은 점수를 매겨 겨룬다(무게가 없는 옛 상태면 먼저 자리를 준다)
    floor = floor or {}

    def score(x):
        w = x.get("weight")
        if w is None:
            return 99
        s = max(w, floor.get(x["rule"], 0)) + (1 if x["category"] in LEVERS else 0)
        if x.get("driver") and 0 <= (D.today - d(x["driver"])).days <= 7:
            s += 1
        return s
    pool = list(fired.values()) + extra
    held = [dict(pin[p["rule"]]) for p in pinned if p["rule"] in pin]   # 오늘 조건에 맞춰 고쳐 쓴 유예 줄(어긋나 뺀 줄은 없음)
    for x in pool + held:
        x["score"] = score(x)
    order = lambda x: (-x["score"], -(x.get("weight") or 0), -(d(x["driver"]).toordinal() if x.get("driver") else 0), x["rule"])
    chosen, cats = [], {}
    for x in sorted(pool + held, key=order):
        if len(chosen) >= 4:
            x["why_not"] = "4개 마감"
            continue
        if cats.get(x["category"]):
            x["why_not"] = "같은 분야 선택됨" if x["category"] != RISK else "리스크 1개 제한"
            continue
        chosen.append(x)
        cats[x["category"]] = 1
    pool.sort(key=order)
    fb = fallbacks(D, c)
    if len(chosen) < 3:
        have = {x["category"] for x in chosen}
        fb.sort(key=lambda x: (x["rule"] == "F3", x["category"] in have, x["rule"]))
        for x in fb:
            if len(chosen) >= 3:
                break
            if any(y["rule"] == x["rule"] for y in chosen):
                continue
            if x["rule"] == "F3" or x["category"] not in have or len([y for y in chosen if y["rule"] != "F3"]) < 2:
                chosen.append(x)
                have.add(x["category"])
    if len(chosen) < 3:
        # 대체 줄로도 3개가 안 되면 같은 분야 두 번째 줄까지 허용(리스크·지분 인수는 서로 엇갈릴 수 있어 제외)
        for x in pool:
            if len(chosen) >= 3:
                break
            if x not in chosen and x["category"] not in (RISK, "M&A·지분"):
                chosen.append(x)
                x.pop("why_not", None)
    # 인수를 미루라는 줄이 있으면 리스크 줄은 같은 말을 반복하지 않고 한도 점검만 말한다
    r08 = next((x for x in chosen if x["rule"] == "R08" and x.get("short")), None)
    if r08 and any(x["variant"] in ("gated", "acquire-gated") for x in chosen):
        r08["text"] = r08["short"]
    losers = [{"rule": x["rule"], "variant": x["variant"], "why_not": x.get("why_not", "")} for x in pool if x not in chosen]
    losers += [{"rule": r, "variant": "", "why_not": why} for r, why in dropped]
    # 다른 줄에 합쳐졌거나 조정으로 빠진 규칙도 '발동'으로 본다(하루 안 잡힘으로 세지 않음)
    fired_ids = {x["rule"] for x in pool} | {r for r, _ in dropped if r not in suppressed} | {x["rule"] for x in fb}
    return chosen, losers, fired_ids, regime


def watch_urls(D, c):
    """이 나라의 '큰 뉴스' 후보 url: 구조 뉴스(극성 있는 것), 경쟁사 자본·M&A·제재, 당사 현지 뉴스."""
    out = []
    for it in D.macro_items():
        if it.get("priority") and c in countries_of(it["title"]) and polarity(it["title"]) != 0:
            out.append(it)
        elif c in countries_of(it["title"]) and reg_hit(it["title"]):
            out.append(it)
    for it in D.hub_items(c, home=False) + [i for i in D.news_items() if KOR[c] in i.get("title", "")]:
        if (CAPITAL_RE.search(it["title"]) or reg_hit(it["title"])) and HOME not in it["title"]:
            out.append(it)
    out += D.hub_items(c, home=True)
    return out


def fingerprint(bullets):
    key = sorted((b["rule"], b["variant"], json.dumps(b["bucket"], ensure_ascii=False)) for b in bullets)
    return hashlib.sha1(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:12]


RULE_NAME = {"R01": "규모 격차", "R02": "경쟁사 자본 확충", "R03": "현지 인수 부담", "R04": "인수 비용", "R05": "증자 후 매출",
             "R06": "교차판매", "R07": "시장 지위 상향", "R08": "구조적 악재", "R09": "환율", "R10": "제재·사기", "R11": "적자",
             "R12": "비용 증가", "R13": "중복 고정비", "R14": "거래대금 감소", "MKT": "점유율·마케팅", "R18": "디지털자산 협력",
             "F1": "자본 격차", "F2": "ROE", "F3": "다음 판단 시점"}


def archive_worthy(it):
    """보관할 기사: 세 나라 중 하나에 귀속되는 것만(다른 나라 기사는 어느 규칙도 읽지 않는다)."""
    t = it.get("title", "")
    return it.get("kind") == "hub" or bool(countries_of(t)) or any(KOR[c] in t for c in COUNTRIES) or "인니" in t


# 게시 줄에 없지만 유예 중인 줄을 다시 판단할 때 필요한 값(적자 법인의 비용/매출 배수, 마케팅 근거 규칙)
META_KEYS = ("cir", "components", "tierA", "weight", "driver")


def check_country(D, c, pc, cs, seen, dart_key, now, prev_spec=None):
    """한 나라 판정. (화면 블록, 다음 상태). 예외는 run()이 잡아 이전 블록·상태를 그대로 둔다."""
    today = now.date()
    stamp = now.isoformat(timespec="minutes")
    published = {b["rule"]: b for b in pc.get("bullets", [])}
    hard = []
    if not pc.get("bullets"):
        hard.append("첫 생성")
    if cs.get("spec", prev_spec if pc.get("bullets") else None) not in (None, SPEC_VERSION):
        hard.append("규칙 개정")
    # 공시 파일이 비거나 깨진 날(값 None)은 새 보고서가 아니라 자료 공백: 그 칸은 직전 값을 이어 쓴다
    prev_dart = cs.get("dart")
    dart_now = [k if k is not None else (prev_dart[i] if isinstance(prev_dart, list) and i < len(prev_dart) else None)
                for i, k in enumerate(dart_key)]
    if prev_dart is not None and prev_dart != dart_now:
        hard.append(f"DART {(D.L or {}).get('report', {}).get('name', '새 보고서')} 반영")
    # 사건(고른 줄과 무관): 새 뉴스·정책금리·지수 급변·정기 갱신. ev_rules = 그 사건이 직접 읽히는 규칙
    # (그 규칙이 오늘 빠졌다면 자료 공백이 아니라 사건 때문이니 유예하지 않는다)
    events_, ev_rules = [], set()
    # 새 뉴스: 이 나라가 마지막으로 제대로 확인된 시각 뒤에 처음 본 기사(실패한 실행에서 본 기사도 다음 확인 때 잡힌다)
    if cs.get("ok"):
        fresh = [it for it in watch_urls(D, c) if D.age(it.get("date")) <= NEWS_FRESH_DAYS
                 and (it["url"] not in seen or (seen[it["url"]].get("first_seen") or "") > cs["ok"])]
        if fresh:
            it = sorted(fresh, key=lambda i: i.get("date", ""), reverse=True)[0]
            events_.append(f"새 뉴스: {news_label(it['title']) or it.get('src', '') + ' 보도'}")
        for it in fresh:
            t = it["title"]
            if it.get("kind") == "macro" and it.get("priority") and polarity(t) != 0:
                ev_rules |= {"R07", "R08"}
            if reg_hit(t):
                ev_rules.add("R10")
            if it.get("kind") != "macro" and CAPITAL_RE.search(t):
                ev_rules.add("R02")
            if it.get("kind") == "hub" and it.get("firm") == HOME:
                ev_rules.add("R18")
    pol = D.policy(c)
    pol_now = pol["now"] if pol else cs.get("policy")
    if pol and cs.get("policy") is not None and cs["policy"] != pol["now"]:
        events_.append(f"정책금리 {cs['policy']:.2f}% → {pol['now']:.2f}%")
        ev_rules.add("R06")
    ix = D.ix(c)
    _, _, w_usd = fx_pair(D, c)
    w1, d1 = chg(ix, "1W"), chg(ix, "1D")
    # 지수·환율 값이 빈 날은 그 항목의 직전 판단을 그대로 둔다(자료가 돌아온 날 같은 급변을 다시 세지 않게)
    shock_ix = (abs(w1 or 0) >= 7 or (d1 or 0) <= -4) if (w1 is not None or d1 is not None) else bool(cs.get("shock_ix", cs.get("shock")))
    shock_fx = (w_usd <= -2) if w_usd is not None else bool(cs.get("shock_fx", cs.get("shock")))
    shock = shock_ix or shock_fx
    if shock and not cs.get("shock") and cs.get("ok"):
        events_.append("지수·환율 급변")
        ev_rules |= {"R04", "R07", "R08", "R09", "R14", "MKT"}
    if pc.get("changed_at") and (today - d(pc["changed_at"])).days >= MAX_STALE_DAYS:
        events_.append(f"정기 갱신({MAX_STALE_DAYS}일)")
    # 게시 중 규칙의 어제 무게(새 공시·규칙 개정 날, 그 규칙을 직접 건드린 사건이 있는 날은 쓰지 않는다)
    # 같은 날 다시 돌려도 그날 첫 실행 전 무게를 쓴다(낮·저녁 재실행이 아침에 낮아진 무게로 겨루지 않게)
    meta = cs.get("meta") or {}
    meta_base = cs.get("meta_base", meta) if cs.get("miss_date") == today.isoformat() else meta
    floor = {} if hard else {r: meta_base[r]["weight"] for r in published
                             if r not in ev_rules and isinstance((meta_base.get(r) or {}).get("weight"), (int, float))}
    chosen, losers, fired, regime = evaluate(D, c, published, floor=floor)
    # 하루 안 잡힘 세기: 같은 날 다시 돌려도 하루로 센다(그날 첫 실행 전 값에서 다시 셈)
    base = cs.get("miss_base", {}) if cs.get("miss_date") == today.isoformat() else cs.get("miss", {})
    miss = {r: n for r, n in base.items() if r in published and r not in fired}
    for r in published:
        if r not in fired:
            miss[r] = miss.get(r, 0) + 1
    # 하루만 안 잡힌 게시 줄은 자리를 지킨다(자료 공백에 다른 규칙이 그 자리를 메웠다가 다음 날 되돌아가지 않게).
    # 새 공시·규칙 개정 날, 그 줄을 직접 건드린 사건이 있는 날, 국면이 뒤집힌 날의 반대 국면 줄(R07↔R08)은 지키지 않는다
    # 지수 자료가 빈 날 악재 줄(R08)이 빠진 것은 뉴스 사건 때문이 아니라 자료 공백 때문이다(유예하고 오늘 뉴스로 문구만 고친다).
    # 호재 줄(R07)은 지수가 비면 오히려 잡히기 쉬워, 빠졌다면 뉴스 때문이다
    ix_gap = ix is None or (chg(ix, "1M") is None and drawdown(ix, 13) is None)
    grace = [r for r in published if r not in fired and miss[r] < 2 and (r not in ev_rules or (r == "R08" and ix_gap))
             and not (r == "R07" and regime == "NEG") and not (r == "R08" and regime == "POS")]
    if grace and not hard:
        # 게시 줄에 없는 판단 값(적자 법인의 비용/매출 배수, 무게·근거 날짜 등)은 상태에서 되살린다
        chosen, losers, fired, regime = evaluate(D, c, published, pinned=[{**published[r], **meta_base.get(r, meta.get(r, {}))} for r in grace], floor=floor)
    new_map = {b["rule"]: b for b in chosen}
    added = [r for r in new_map if r not in published or new_map[r]["variant"] != published[r]["variant"]]
    gone = [r for r in published if r not in new_map and r not in fired]
    sel = []
    if (added or gone) and pc.get("bullets"):
        sel.append("판단 변화: " + ", ".join([f"+{RULE_NAME.get(r, r)}" for r in added] + [f"−{RULE_NAME.get(r, r)}" for r in gone]))
    moved = [r for r in new_map if r in published and new_map[r]["variant"] == published[r]["variant"]
             and new_map[r]["bucket"] != published[r].get("bucket")]
    if moved and pc.get("bullets"):
        sel.append("구간 변화: " + ", ".join(RULE_NAME.get(r, r) for r in moved))
    reasons = hard + sel + events_
    block = {"country": KOR[c], "entities": [D.label(k) for k in KEYS[c]]}
    if reasons:
        bullets = [{**{k: b[k] for k in ("rule", "variant", "category", "text", "evidence", "links", "bucket")}, "keys": b.get("keys") or []} for b in chosen]
        hist = (pc.get("history") or [])[-59:] + [{"date": today.isoformat(), "fp": fingerprint(chosen), "rules": [b["rule"] for b in chosen], "reason": reasons}]
        block.update(regime=regime, bullets=bullets, changed_at=today.isoformat(), reason=reasons[:3], last_check="갱신", candidates=losers, history=hist)
    else:
        # 문구를 그대로 두는 날은 국면 표시도 그대로(줄과 표시가 엇갈리지 않게)
        block.update({k: pc.get(k) for k in ("regime", "bullets", "changed_at", "reason", "candidates", "history")}, last_check="큰 변화 없음")
    shown = {b["rule"] for b in block["bullets"] or []}
    meta = {r: v for r, v in (cs.get("meta") or {}).items() if r in shown}
    for b in chosen:
        m = {k: b[k] for k in META_KEYS if b.get(k) is not None}
        if b["rule"] in shown and m:
            meta[b["rule"]] = m
    ncs = {"ok": stamp, "dart": dart_now, "spec": SPEC_VERSION, "policy": pol_now, "shock": shock, "shock_ix": shock_ix, "shock_fx": shock_fx,
           "miss": {r: n for r, n in miss.items() if r in shown}, "miss_base": base, "miss_date": today.isoformat(), "meta": meta,
           "meta_base": meta if hard else meta_base}
    return block, ncs


def run(root=ROOT, now=None, prev=None):
    """prev: 직전 결과(state 포함). 없으면 takeaways.json + takeaways_state.json 을 읽는다."""
    now = now or datetime.now(KST)
    today = now.date()
    if prev is None:
        prev = load(root, OUT_REL) or {}
        st = load(root, STATE_REL)
        if st is not None:
            prev = {**prev, "state": st}
    state = prev.get("state") or {}
    D = Data(root, today, state)
    out = {"spec_version": SPEC_VERSION, "checked_at": now.isoformat(timespec="minutes"), "countries": {}, "errors": []}
    dart_key = [((D.L or {}).get("report") or {}).get("rcept_no"), ((D.subs.get("invest") or {}).get("report") or {}).get("rcept_no")]
    seen = state.get("seen") or {}
    new_state = {"countries": {}, "injection": dict(state.get("injection") or {})}
    # 공시 파일이 비거나 깨진 날: 손익·출자를 읽는 규칙이 모두 흔들리므로 판단하지 않고 이전 문구·상태를 그대로 둔다
    dart_gap = D.L is None and any(((state.get("countries") or {}).get(c) or {}).get("dart") for c in COUNTRIES)
    if dart_gap:
        out["errors"].append("DART 해외자회사 자료 없음: 이전 문구 유지")
    for c in COUNTRIES:
        pc = (prev.get("countries") or {}).get(c) or {}
        cs = (state.get("countries") or {}).get(c) or {}
        if dart_gap:
            if pc:
                out["countries"][c] = {**pc, "last_check": "확인 실패"}
            if cs:
                new_state["countries"][c] = cs
            continue
        try:
            block, ncs = check_country(D, c, pc, cs, seen, dart_key, now, prev.get("spec_version"))
            for k in KEYS[c]:
                inj = injection(D, k)
                if inj:
                    new_state["injection"][k] = inj
        except Exception as e:  # 한 나라 실패가 다른 나라를 막지 않게: 이전 블록·판단 상태를 그대로 둔다
            out["errors"].append(f"{c}: {type(e).__name__}: {e}")
            if pc:
                out["countries"][c] = {**pc, "last_check": "확인 실패"}
            if cs:
                new_state["countries"][c] = cs
            continue
        out["countries"][c] = block
        new_state["countries"][c] = ncs
    out["updated_at"] = max((b.get("changed_at") or "" for b in out["countries"].values()), default="")
    # 본 기사 보관(최근 61일, 세 나라 기사만): 다음 실행의 '새 뉴스' 판정과 구조 뉴스 국면 유지용
    seen = dict(seen)
    first = now.isoformat(timespec="minutes")
    for it in D.macro_items() + D.news_items() + [i for c in COUNTRIES for i in D.hub_items(c)]:
        if it.get("url") and it["url"] not in seen and archive_worthy(it):
            keep = {k: it.get(k) for k in ("date", "title", "src", "priority", "kind", "firms") if it.get(k) is not None}
            seen[it["url"]] = {**keep, "first_seen": first}
    new_state["seen"] = {u: v for u, v in seen.items() if D.age(v.get("date")) <= ARCHIVE_DAYS}
    # 사업보고서(FY) 손익을 두 해치 보관: 다음 사업보고서가 나와 수집 파일에 FY가 하나만 남아도 전년과 비교할 수 있게
    fy = dict(state.get("fy") or {})
    for per in D.subs.get("periods") or []:
        if per.get("period") == "FY" and per.get("year"):
            fy[str(per["year"])] = {k: per.get(k) for k in ("label", "period", "year", "months", "report", "subs")}
    new_state["fy"] = {y: fy[y] for y in sorted(fy)[-2:]}
    out["state"] = new_state
    return out


def main():
    res = run()
    if "--print" in sys.argv[1:]:
        for c, b in res["countries"].items():
            print(f"== {b['country']} · {b.get('changed_at')} · {b.get('last_check')} · {', '.join(b.get('reason') or [])}")
            for x in b.get("bullets") or []:
                print(f"  [{x['category']}] {x['text']}\n      근거: {' · '.join(x['evidence'])}")
            for x in b.get("candidates") or []:
                print(f"    (탈락 {x['rule']} {x['variant']}: {x['why_not']})")
        print("errors:", res["errors"])
        return
    state = res.pop("state")
    for rel, obj, indent in ((OUT_REL, res, 1), (STATE_REL, state, None)):
        p = ROOT / rel
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")
        tmp.replace(p)
    print(f"저장: {ROOT / OUT_REL} · " + " / ".join(f"{b['country']} {b.get('last_check')}" for b in res["countries"].values()))


if __name__ == "__main__":
    main()
