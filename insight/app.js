// 전략 인사이트 탭. data/country.json(진출국 스코어카드), data/landscape.json(현지 경쟁 구도·밸류에이션),
// data/idx_share.json(인도네시아 거래대금 점유율)과 글로벌 탭의 HOSE 점유율(../data/global/markets.json, 수동)을 그린다.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 0) => (v == null || isNaN(v) ? "–" : Number(v).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const sgn = (v, d = 1) => (v == null ? "–" : `<span class="${v < 0 ? "neg" : v > 0 ? "pos" : ""}">${num(v, d)}</span>`);
  const dot = (s) => String(s || "").slice(0, 10).replace(/-/g, ".");
  const ym = (s) => String(s || "").slice(0, 7).replace("-", ".");
  const tmeta = (basis, unit) => `${basis ? `<span>기준 ${esc(basis)}</span>` : ""}${unit ? `<span>단위: ${esc(unit)}</span>` : ""}`;
  const tm = (basis, unit) => `<div class="tmeta">${tmeta(basis, unit)}</div>`;
  const HW = "한화투자증권";
  const HWNAME = { "Pinetree Securities Corporation": "베트남 법인(PTSV)", "Pinetree Securities Pte.Ltd.": "싱가포르 법인(PTSS)", "PT Ciptadana Sekuritas Asia": "인도네시아 증권(CSA)" };
  const label = (r) => (r.firm === HW ? `${HWNAME[r.name] || r.name}` : r.name);
  const getJSON = async (u) => { try { const r = await fetch(u, { cache: "no-cache" }); return r.ok ? r.json() : null; } catch (_) { return null; } };
  let C, L, X, G;

  // ---------- 진출국 스코어카드 ----------
  const COLS = [
    ["gdp_growth", "실질 성장률", "%", 1, true], ["gdp_growth_next", "성장률 전망", "%", 1, true], ["cpi", "물가 상승률", "%", 1, false],
    ["gdp_pc", "1인당 GDP", "USD", 0, true], ["pop", "인구", "백만 명", 1, true], ["gdp", "GDP", "십억 USD", 0, true],
    ["mcap_gdp", "시가총액/GDP", "%", 0, true], ["turnover", "주식 회전율", "%", 0, true], ["listed", "상장사 수", "개", 0, true], ["account", "금융계좌 보유율", "%", 0, true],
  ];
  const cell = (r, k) => ({ v: r[k]?.v, y: r[k]?.y, src: r[k]?.src });
  function renderCountry() {
    if (!C?.rows) { $("#cty").innerHTML = `<div class="empty">첫 자동 수집 후 표시됩니다.</div>`; return; }
    const rows = Object.values(C.rows);
    const rng = Object.fromEntries(COLS.map(([k]) => { const vs = rows.map((r) => cell(r, k).v).filter((v) => v != null); return [k, [Math.min(...vs), Math.max(...vs)]]; }));
    const heat = (k, v, good) => {
      if (v == null || !good) return "";
      const [a, b] = rng[k]; const t = b > a ? (v - a) / (b - a) : 0;
      return ` style="background:rgba(243,115,33,${(0.08 + t * 0.55).toFixed(2)})"`;
    };
    const yrs = (k) => [...new Set(rows.map((r) => cell(r, k).y).filter(Boolean))];
    const cols = COLS.filter(([k]) => rows.some((r) => r[k]?.v != null));
    const srcOf = (k) => [...new Set(rows.map((r) => r[k]?.src).filter(Boolean))].map((x) => (x === "IMF" ? "IMF" : "WB")).join("·");
    const head = cols.map(([k, t, u]) => `<th>${esc(t)}<small>${esc(u)} · ${esc(yrs(k).join("·") || "–")} ${srcOf(k)}</small></th>`).join("");
    const body = rows.map((r) => `<tr class="${r.iso === "KOR" ? "ref" : ""}"><td>${esc(r.name)}${r.iso === "KOR" ? '<span class="tag old">비교</span>' : ""}</td>${cols.map(([k, , , d, good]) => {
      const c = cell(r, k);
      const lag = c.y && yrs(k).length > 1 && c.y !== Math.max(...yrs(k).map(Number)).toString() ? `<span class="mut"> ’${String(c.y).slice(2)}</span>` : "";
      return `<td><span class="heat"${r.iso === "KOR" ? "" : heat(k, c.v, good)}>${num(c.v, d)}</span>${lag}</td>`;
    }).join("")}</tr>`).join("");
    $("#tm-cty").innerHTML = tmeta(`칸 머리의 연도(IMF = WEO 전망, WB = 세계은행 실적 최신 연도) · 확인 ${dot(C.checked_at)}`, "칸 머리 표시");
    $("#cty").innerHTML = `<table><thead><tr><th>국가</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
    $("#cty-note").innerHTML = `출처: ${C.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>`).join(" · ")}.
      성장률·물가·1인당 GDP·인구·GDP는 IMF 세계경제전망(매년 4·10월 개정)을 우선 쓰고, IMF 서버가 응답하지 않는 날은 세계은행 실적치(최신 연도)로 채웁니다. 나머지는 세계은행 세계개발지표입니다. 연도가 다른 칸은 ’연도를 붙였습니다. 색 비교는 한국을 뺀 6개국 기준(물가 제외).
      ${C.errors?.length ? `<br><span class="mut">최근 실행에서 응답하지 않은 출처 ${C.errors.length}건(${esc([...new Set(C.errors.map((e) => e.split(" ")[0]))].join("·"))}): 해당 칸은 대체 출처 또는 이전 값입니다.</span>` : ""}`;
  }

  // ---------- 현지 경쟁 구도 ----------
  const MK = [["vn", "베트남"], ["id", "인도네시아"], ["sg", "싱가포르"], ["jp", "일본"]];
  let mk = "vn";
  function brokers(m) { return m.rows.filter((r) => r.kind === "local" || r.broker); }
  function rankOf(m, firm) {
    const b = brokers(m);
    return b.map((r, i) => ({ r, i: i + 1 })).filter((x) => x.r.firm === firm).map((x) => ({ ...x, n: b.length }));
  }
  function scatter(m) {
    const pts = m.rows.filter((r) => r.kind === "local" && r.pb != null && r.roe != null);
    if (pts.length < 2) return "";
    const W = 330, H = 170, P = 26;
    const xs = pts.map((p) => p.roe), ys = pts.map((p) => p.pb);
    const x0 = Math.min(0, ...xs), x1 = Math.max(...xs) * 1.1, y1 = Math.max(...ys) * 1.15;
    const X = (v) => P + ((v - x0) / (x1 - x0 || 1)) * (W - P - 8), Y = (v) => H - P + 4 - (v / (y1 || 1)) * (H - P - 8);
    const ticks = [0, y1 / 2, y1].map((v) => `<text x="2" y="${Y(v) + 3}">${v.toFixed(1)}</text><line x1="${P}" x2="${W - 8}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/>`).join("");
    const dots = pts.map((p) => `<circle cx="${X(p.roe)}" cy="${Y(p.pb)}" r="4" fill="var(--bar)" stroke="var(--text-2)" stroke-width=".6"><title>${esc(p.name)} ROE ${p.roe}% · P/B ${p.pb}</title></circle>
      <text x="${X(p.roe) + 5}" y="${Y(p.pb) + 3}">${esc(p.ticker)}</text>`).join("");
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:440px;display:block;margin-top:6px" role="img" aria-label="ROE와 P/B 산점도">${ticks}
      <line x1="${X(0)}" x2="${X(0)}" y1="6" y2="${H - P + 4}" stroke="var(--line)"/>${dots}
      <text x="${W - 8}" y="${H - 4}" text-anchor="end">ROE(%) →</text><text x="${P}" y="10">P/B</text></svg>
      <p class="note">상장사 ROE(가로)와 P/B(세로): 오른쪽 위일수록 수익성과 시장 평가가 함께 높음.</p>`;
  }
  function renderLand() {
    $("#land-pills").innerHTML = MK.filter(([k]) => L?.markets?.[k]).map(([k, t]) => `<button class="pill" type="button" data-k="${k}" aria-pressed="${k === mk}">${t}</button>`).join("");
    $("#land-pills").onclick = (e) => { const b = e.target.closest(".pill"); if (b) { mk = b.dataset.k; renderLand(); } };
    const m = L?.markets?.[mk];
    if (!m) { $("#land").innerHTML = `<div class="empty">첫 자동 수집 후 표시됩니다.</div>`; return; }
    const b = brokers(m), others = m.rows.filter((r) => r.kind === "korean" && !r.broker);
    const max = Math.max(...b.map((r) => r.equity_krw || 0), 1);
    const cls = (r) => (r.firm === HW ? "hw" : r.kind === "korean" ? "kr" : "");
    const bars = b.map((r) => `<div class="bar ${cls(r)}"><span class="nm" title="${esc(r.name)}">${esc(label(r))}</span>
      <span class="tr"><i style="width:${Math.max(0.5, (r.equity_krw / max) * 100).toFixed(1)}%"></i></span><span class="v">${num(r.equity_krw)}</span></div>`).join("");
    const asof = [...new Set(m.rows.map((r) => r.asof).filter(Boolean))].map(dot).join("·");
    const pdate = [...new Set(m.rows.map((r) => r.price_date).filter(Boolean))].sort().pop();
    const rows = b.map((r, i) => `<tr class="${r.firm === HW ? "hw" : r.kind === "korean" ? "kr" : ""}"><td>${i + 1}</td>
      <td class="l">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(label(r))}</a>` : esc(label(r))}${r.kind === "korean" ? `<span class="tag ${r.firm === HW ? "hw" : "kr"}">${esc(r.firm)}</span>` : ""}${r.stale ? '<span class="tag old">이전 값</span>' : ""}</td>
      <td>${num(r.equity, 2)}</td><td>${num(r.equity_krw)}</td><td>${sgn(r.ni, 2)}</td><td>${sgn(r.roe)}</td>
      <td>${r.mcap_krw != null ? num(r.mcap_krw) : '<span class="mut">비상장</span>'}</td><td>${r.pb != null ? num(r.pb, 2) : "–"}</td></tr>`).join("");
    const me = rankOf(m, HW);
    const top = b.find((r) => r.kind === "korean");
    const kr = b.filter((r) => r.kind === "korean");
    const lines = [];
    if (me.length) lines.push(...me.map((x) => `<b>${esc(label(x.r))}</b> 자기자본 ${num(x.r.equity_krw)}억원으로 ${x.n}개사 중 <b>${x.i}위</b>${b[0] ? `, 1위 ${esc(label(b[0]))}의 ${num((x.r.equity_krw / b[0].equity_krw) * 100, 1)}%` : ""}`));
    if (top && kr.length > 1) lines.push(`한국계 ${kr.length}곳 중 최대: ${esc(label(top))}(${esc(top.firm)}) ${num(top.equity_krw)}억원, 전체 ${b.indexOf(top) + 1}위`);
    if (m.median_pb != null) lines.push(`상장사 P/B 중앙값 <b>${num(m.median_pb, 2)}배</b>, ROE 중앙값 ${num(m.median_roe, 1)}%`);
    $("#land").innerHTML = `${lines.length ? `<p class="why">${lines.join(" · ")}</p>` : ""}
      <div class="split"><div>
        <div class="legend"><span><i style="background:var(--bar)"></i>현지 상장 증권사</span><span><i style="background:var(--kr)"></i>한국계 현지법인</span><span><i style="background:var(--accent)"></i>당사</span></div>
        ${tm(`자본 ${asof} 결산`, "억원(결산일 환율 환산)")}<div class="bars">${bars}</div>${scatter(m)}
      </div><div class="tw">
        ${tm(`자본·순이익 ${asof} 결산 · 시가총액 ${dot(pdate)} 종가`, `현지 ${m.unit}, 원화 억원, ROE %, P/B 배`)}
        <table><thead><tr><th>#</th><th class="l">회사</th><th>자기자본<small>${esc(m.unit)}</small></th><th>자기자본<small>억원</small></th><th>순이익<small>${esc(m.unit)}</small></th><th>ROE<small>%</small></th><th>시가총액<small>억원</small></th><th>P/B<small>배</small></th></tr></thead>
        <tbody>${rows}</tbody></table>
        <p class="note">현지 상장사는 거래소 상장 증권사만(은행·외국계 비상장 대형사는 공시가 없어 빠짐). 한국계는 모회사 DART 2025 사업보고서 종속기업 요약재무정보(원화)를 연말 환율 ${num(m.fx_ye, m.fx_ye < 1 ? 4 : 2)}원/${esc(m.ccy)}로 되돌린 값.
        ${others.length ? `<br>순위 제외 한국계(운용·기타): ${others.map((r) => `${esc(r.name)}(${esc(r.firm)}, ${num(r.equity_krw)}억원)`).join(", ")}` : ""}
        ${mk === "jp" && !kr.length ? "<br>일본에는 DART 요약재무정보가 있는 한국계 증권 현지법인이 없습니다." : ""}</p>
      </div></div>`;
  }

  // ---------- 인도네시아 점유율 ----------
  let ip = "month";
  function renderIdx() {
    if (!X?.month) {
      $("#idx").innerHTML = `<div class="empty">IDX 거래 요약 자동 수집 결과가 아직 없습니다.${X?.errors?.length ? `<br><span class="mut">최근 시도 ${esc(dot(X.checked_at))}: ${/Just a moment|403/.test(X.errors[0]) ? "IDX 사이트가 자동 접속을 차단(HTTP 403)" : esc(X.errors[0].slice(0, 80))}</span>` : ""}</div>`;
      return;
    }
    $("#idx-pills").innerHTML = [["month", `최근 월(${ym(X.month.month)})`], ["ytd", `올해 누적(${X.ytd.from.slice(0, 4)})`]].map(([k, t]) => `<button class="pill" type="button" data-k="${k}" aria-pressed="${k === ip}">${t}</button>`).join("");
    $("#idx-pills").onclick = (e) => { const b = e.target.closest(".pill"); if (b) { ip = b.dataset.k; renderIdx(); } };
    const P = X[ip], top = P.rows.filter((r) => r.rank <= 15), kr = P.rows.filter((r) => r.korean && r.rank > 15);
    const max = Math.max(...P.rows.map((r) => r.share), 1);
    const bar = (r) => `<div class="bar ${r.korean === HW ? "hw" : r.korean ? "kr" : ""}"><span class="nm" title="${esc(r.name)}">${r.rank}. ${esc(r.name)} <span class="mut">${esc(r.code)}</span></span>
      <span class="tr"><i style="width:${((r.share / max) * 100).toFixed(1)}%"></i></span><span class="v">${num(r.share, 2)}%</span></div>`;
    const me = P.rows.find((r) => r.korean === HW);
    const months = [...new Set(Object.values(X.trend || {}).flatMap((t) => t.pts.map((p) => p[0])))].sort().slice(-6);
    const trend = Object.values(X.trend || {}).sort((a, b) => (b.pts.at(-1)?.[1] || 0) - (a.pts.at(-1)?.[1] || 0)).map((t) => {
      const by = Object.fromEntries(t.pts.map((p) => [p[0], p]));
      return `<tr class="${t.firm === HW ? "hw" : "kr"}"><td>${esc(t.name)}<span class="tag ${t.firm === HW ? "hw" : "kr"}">${esc(t.firm)}</span></td>${months.map((mm) => `<td>${by[mm] ? `${num(by[mm][1], 2)}<span class="mut"> ${by[mm][2]}위</span>` : "–"}</td>`).join("")}</tr>`;
    }).join("");
    $("#idx").innerHTML = `${me ? `<p class="why"><b>인도네시아 증권(CSA)</b> ${num(me.share, 2)}%, ${X.brokers}개 회원사 중 <b>${me.rank}위</b></p>` : ""}
      ${tm(`${ip === "month" ? ym(X.month.month) : `${dot(X.ytd.from)}~${dot(X.ytd.to)}`} · ${P.days}거래일 · 전체 ${num(P.total / 1e12, 1)}조 루피아`, "%(매수+매도 거래대금 비중)")}
      <div class="legend"><span><i style="background:var(--bar)"></i>현지·외국계</span><span><i style="background:var(--kr)"></i>한국계</span><span><i style="background:var(--accent)"></i>당사</span></div>
      <div class="bars">${top.map(bar).join("")}${kr.length ? `<div class="note">… 한국계</div>${kr.map(bar).join("")}` : ""}</div>
      ${trend ? `<div class="tw" style="margin-top:6px">${tm(`월별 · 마지막 거래일 ${dot(X.last_day)}`, "%, 순위")}<table><thead><tr><th>한국계 회원사</th>${months.map((mm) => `<th>${ym(mm)}${mm === X.last_day.slice(0, 7) && mm !== X.month.month ? `<small>~${X.last_day.slice(8)}일 진행 중</small>` : ""}</th>`).join("")}</tr></thead><tbody>${trend}</tbody></table></div>` : ""}
      <p class="note">출처: <a href="${esc(X.source.url)}" target="_blank" rel="noopener">${esc(X.source.label)}</a>. ${esc(X.method)}. 회원사 이름으로 한국계를 표시합니다.</p>`;
  }

  // ---------- 베트남 HOSE 점유율(글로벌 탭 수동 자료) ----------
  function renderVn() {
    const t = G?.markets?.find((m) => m.id === "vn")?.tables?.[0];
    if (!t) { $("#vn").innerHTML = `<div class="empty">자료 없음</div>`; return; }
    const max = Math.max(...t.rows.map((r) => r.value), 1);
    const krs = t.rows.map((r, i) => (r.korean ? `${r.name} ${i + 1}위` : "")).filter(Boolean);
    $("#vn").innerHTML = `<p class="why">거래소가 상위 ${t.rows.length}곳만 발표합니다. <b>베트남 법인(PTSV)</b>은 상위 ${t.rows.length}위 밖${krs.length ? `, 한국계는 ${esc(krs.join(" · "))}` : ""}.</p>
      ${tm(t.basis, t.unit)}
      <div class="legend"><span class="tag man">수동</span><span>분기 발표 후 사람이 입력(거래소 자료가 기계 판독 형식으로 공개되지 않음)</span></div>
      <div class="bars">${t.rows.map((r, i) => `<div class="bar ${r.korean ? "kr" : ""}"><span class="nm">${i + 1}. ${esc(r.name)}${r.korean ? `<span class="tag kr">${esc(r.korean)}</span>` : ""}</span>
        <span class="tr"><i style="width:${((r.value / max) * 100).toFixed(1)}%"></i></span><span class="v">${num(r.value, 2)}%</span></div>`).join("")}</div>
      <p class="note">${esc(t.title)} · 출처: <a href="${esc(t.source.url)}" target="_blank" rel="noopener">${esc(t.source.label)}</a> · <a href="../#global/vn" target="_top">글로벌 탭 베트남</a>과 같은 자료</p>`;
  }

  // ---------- 밸류에이션 ----------
  function renderVal() {
    if (!L?.markets) { $("#val-mkt").innerHTML = `<div class="empty">첫 자동 수집 후 표시됩니다.</div>`; return; }
    const order = [["kr", "한국"], ...MK];
    const pd = [...new Set(Object.values(L.markets).flatMap((m) => m.rows.map((r) => r.price_date)).filter(Boolean))].sort().pop();
    const rows = order.filter(([k]) => L.markets[k]).map(([k, t]) => {
      const m = L.markets[k], n = m.rows.filter((r) => r.pb != null).length;
      return `<tr class="${k === "kr" ? "ref" : ""}"><td>${t}</td><td>${n}</td><td>${num(m.median_pb, 2)}</td><td>${sgn(m.median_roe)}</td></tr>`;
    }).join("");
    $("#val-mkt").innerHTML = `${tm(`시가총액 ${dot(pd)} 종가 · ROE 최근 연간 결산`, "배, %")}
      <table><thead><tr><th>시장</th><th>상장 증권사<small>개</small></th><th>P/B 중앙값<small>배</small></th><th>ROE 중앙값<small>%</small></th></tr></thead><tbody>${rows}</tbody></table>
      <p class="note">해석: 현지 P/B가 국내보다 높으면 현지 증권사 인수는 장부가 대비 비싸고, 낮으면 저평가 구간입니다. 싱가포르는 상장 증권사가 2곳뿐입니다.</p>`;
    const kr = L.markets.kr;
    if (!kr?.rows?.length) { $("#val-kr").innerHTML = ""; return; }
    const body = kr.rows.map((r, i) => `<tr class="${r.name === HW ? "hw" : ""}"><td>${i + 1}</td><td class="l"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>${r.val_stale ? '<span class="tag old">이전 값</span>' : ""}</td>
      <td>${num(r.mcap_krw)}</td><td>${num(r.equity_krw)}</td><td>${num(r.pb, 2)}</td><td>${sgn(r.roe)}</td></tr>`).join("");
    const me = kr.rows.find((r) => r.name === HW);
    $("#val-kr").innerHTML = `${me ? `<p class="why"><b>한화투자증권</b> P/B ${num(me.pb, 2)}배(국내 상장 증권사 중앙값 ${num(kr.median_pb, 2)}배) · 시가총액 ${kr.rows.indexOf(me) + 1}위/${kr.rows.length}개사</p>` : ""}
      <div class="tw">${tm(`시가총액 ${dot(pd)} 종가 · 자본 최근 분기 · ROE 최근 연간`, "억원, 배, %")}
      <table><thead><tr><th>#</th><th class="l">국내 상장 증권사</th><th>시가총액<small>억원</small></th><th>자기자본<small>억원</small></th><th>P/B<small>배</small></th><th>ROE<small>%</small></th></tr></thead><tbody>${body}</tbody></table></div>
      <p class="note">한국금융지주는 한국투자증권의 상장 지주사입니다. 자본은 지배주주지분(Yahoo Finance, 각 사 공시 기반).</p>`;
  }

  // ---------- KPI ----------
  function renderKpis() {
    const k = [];
    const vn = L?.markets?.vn, id = L?.markets?.id;
    for (const [m, nm] of [[vn, "베트남"], [id, "인도네시아"]]) {
      const me = m && rankOf(m, HW)[0];
      if (me) k.push([`${nm} 자본 순위(상장사+한국계)`, `${me.i}위<small>/ ${me.n}개사</small>`, `${label(me.r)} ${num(me.r.equity_krw)}억원`]);
    }
    const cs = X?.month?.rows?.find((r) => r.korean === HW);
    if (cs) k.push([`인니 거래대금 점유율 ${ym(X.month.month)}`, `${num(cs.share, 2)}%<small>${cs.rank}위</small>`, `IDX ${X.brokers}개 회원사 중`]);
    const kr = L?.markets?.kr, me = kr?.rows?.find((r) => r.name === HW);
    if (me) k.push(["한화투자증권 P/B", `${num(me.pb, 2)}배`, `국내 증권사 중앙값 ${num(kr.median_pb, 2)}배`]);
    if (vn?.median_pb != null) k.push(["베트남 증권사 P/B 중앙값", `${num(vn.median_pb, 2)}배`, `ROE 중앙값 ${num(vn.median_roe, 1)}%`]);
    const g = C?.rows?.VNM?.gdp_growth, gi = C?.rows?.IDN?.gdp_growth, gk = C?.rows?.KOR?.gdp_growth;
    if (g?.v != null) k.push([`실질 성장률 ${g.y}(${g.src === "IMF" ? "IMF 전망" : "세계은행"})`, `${num(g.v, 1)}%<small>베트남</small>`, `인도네시아 ${num(gi?.v, 1)}% · 한국 ${num(gk?.v, 1)}%`]);
    $("#kpis").innerHTML = k.map(([a, b, c]) => `<div class="kpi"><span>${esc(a)}</span><b>${b}</b><em>${esc(c)}</em></div>`).join("");
  }

  async function init() {
    [C, L, X, G] = await Promise.all([getJSON("data/country.json"), getJSON("data/landscape.json"), getJSON("data/idx_share.json"), getJSON("../data/global/markets.json")]);
    const t = [L?.updated_at, C?.checked_at, X?.checked_at].filter(Boolean).sort().pop();
    $("#meta").textContent = t ? `자동 수집 ${new Date(t).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} KST · 공시·공개자료만 사용` : "자동 수집 전";
    renderKpis(); renderCountry(); renderLand(); renderIdx(); renderVn(); renderVal();
  }
  init();
})();
