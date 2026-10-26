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
  // 규모(자기자본, 로그 눈금) × 수익성(ROE) 지도: 현지 상장사·한국계·당사를 한 판에
  function mapChart(m, b) {
    const pts = b.filter((r) => r.roe != null && r.equity_krw > 0);
    if (pts.length < 3) return "";
    const W = 460, H = 250, L0 = 34, B0 = 22;
    const lx = pts.map((p) => Math.log10(p.equity_krw)), ys = pts.map((p) => Math.max(-30, Math.min(40, p.roe)));
    const x0 = Math.floor(Math.min(...lx) * 2) / 2, x1 = Math.ceil(Math.max(...lx) * 2) / 2;
    const y0 = Math.min(0, Math.floor(Math.min(...ys) / 5) * 5), y1 = Math.ceil(Math.max(...ys) / 5) * 5 || 5;
    const X = (v) => L0 + ((Math.log10(v) - x0) / (x1 - x0 || 1)) * (W - L0 - 10);
    const Y = (v) => H - B0 - ((Math.max(-30, Math.min(40, v)) - y0) / (y1 - y0 || 1)) * (H - B0 - 10);
    const med = (a) => { const s = [...a].sort((p, q) => p - q); return s.length ? s[Math.floor((s.length - 1) / 2)] : null; };
    const mx = med(pts.map((p) => p.equity_krw)), my = med(pts.map((p) => p.roe));
    const xt = [];
    for (let e = Math.ceil(x0); e <= x1; e += 1) xt.push(10 ** e);
    const grid = xt.map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="8" y2="${H - B0}" stroke="var(--line)" stroke-dasharray="2 3"/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${v >= 1e4 ? `${v / 1e4}조` : `${num(v)}억`}</text>`).join("")
      + [y0, 0, y1].filter((v, i, a) => a.indexOf(v) === i).map((v) => `<line x1="${L0}" x2="${W - 10}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"${v === 0 ? "" : ' stroke-dasharray="2 3"'}/><text x="${L0 - 4}" y="${Y(v) + 3}" text-anchor="end">${v}%</text>`).join("");
    const medl = `<line x1="${X(mx)}" x2="${X(mx)}" y1="8" y2="${H - B0}" stroke="var(--accent)" stroke-opacity=".35"/><line x1="${L0}" x2="${W - 10}" y1="${Y(my)}" y2="${Y(my)}" stroke="var(--accent)" stroke-opacity=".35"/>`;
    const col = (r) => (r.firm === HW ? "var(--accent)" : r.kind === "korean" ? "var(--kr)" : "var(--bar)");
    const order = [...pts].sort((p, q) => (p.firm === HW) - (q.firm === HW) || (p.kind === "korean") - (q.kind === "korean"));
    const topN = new Set(b.slice(0, 4));
    const dots = order.map((p) => {
      const lab = p.firm === HW ? label(p) : p.kind === "korean" ? (p.firm || "").replace(/증권|투자증권/g, "") : topN.has(p) ? p.ticker : "";
      return `<circle cx="${X(p.equity_krw).toFixed(1)}" cy="${Y(p.roe).toFixed(1)}" r="${p.firm === HW ? 6 : 4}" fill="${col(p)}" fill-opacity="${p.kind === "local" ? .75 : .95}" stroke="var(--bg)" stroke-width="1"><title>${esc(label(p))}: 자기자본 ${num(p.equity_krw)}억원 · ROE ${p.roe}%</title></circle>`
        + (lab ? `<text x="${(X(p.equity_krw) + 7).toFixed(1)}" y="${(Y(p.roe) + 3).toFixed(1)}"${p.firm === HW ? ' style="fill:var(--accent-ink);font-weight:700"' : p.kind === "korean" ? ' style="fill:var(--kr)"' : ""}>${esc(lab)}</text>` : "");
    }).join("");
    return `${tm("자기자본·ROE 최근 연간 결산", "가로 억원(로그 눈금), 세로 ROE %")}
      <svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block" role="img" aria-label="규모와 수익성 지도">${grid}${medl}${dots}
      <text x="${W - 10}" y="18" text-anchor="end" style="fill:var(--accent-ink)">크고 잘 버는 곳 ↗</text></svg>
      <p class="note">점 하나가 증권사 하나입니다. 주황 옅은 선은 비교 대상의 자본·ROE 중앙값(${num(mx)}억원 · ${num(my, 1)}%). ROE는 −30~40% 밖이면 끝에 붙였습니다.</p>`;
  }

  // 당사 법인 포지션: 순위 하나가 아니라 여러 각도로
  function position(m, b) {
    const me = b.find((r) => r.firm === HW);
    if (!me) return "";
    const n = b.length, rank = b.indexOf(me) + 1;
    const roeRows = b.filter((r) => r.roe != null).sort((p, q) => q.roe - p.roe);
    const roeRank = me.roe != null ? roeRows.indexOf(me) + 1 : null;
    const top10 = b.slice(0, 10), avg10 = top10.reduce((a, r) => a + r.equity_krw, 0) / top10.length;
    const total = b.reduce((a, r) => a + (r.equity_krw || 0), 0);
    const tgt = (k) => (b[k - 1] && rank > k ? Math.max(0, b[k - 1].equity_krw - me.equity_krw) : null);
    const grow = b.filter((r) => r.growth != null).map((r) => r.growth).sort((p, q) => p - q);
    const gmed = grow.length ? grow[Math.floor((grow.length - 1) / 2)] : null;
    const cells = [
      ["자기자본 순위", `${rank}위<small>/ ${n}곳</small>`, `상위 ${num((rank / n) * 100)}% · 비교 대상 자본 합계의 ${num((me.equity_krw / total) * 100, 2)}%`],
      ["수익성(ROE) 순위", roeRank ? `${roeRank}위<small>/ ${roeRows.length}곳</small>` : "–", `ROE ${num(me.roe, 1)}% · 중앙값 ${num(roeRows[Math.floor((roeRows.length - 1) / 2)]?.roe, 1)}%`],
      ["상위 10곳 평균 자본", `${num(avg10 / me.equity_krw, 1)}배<small>당사 대비</small>`, `평균 ${num(avg10)}억원 vs 당사 ${num(me.equity_krw)}억원`],
      ...[20, 10].filter((k) => tgt(k) != null).slice(0, 1).map((k) => [`${k}위 진입까지 자본`, `+${num(tgt(k))}억<small>원</small>`, `${k}위 ${esc(label(b[k - 1]))} ${num(b[k - 1].equity_krw)}억원 수준${k === 20 && tgt(10) != null ? ` · 10위까지 +${num(tgt(10))}억원` : ""}`]),
    ];
    if (gmed != null) cells.push(["상장사 자본 증가율(1년)", `${num(gmed, 1)}%<small>중앙값</small>`, `최대 ${esc(b.filter((r) => r.growth != null).sort((p, q) => q.growth - p.growth)[0].name)} ${num(grow.at(-1), 1)}% · 증자 경쟁 강도`]);
    return `<div class="posn">${cells.map(([a, v, c]) => `<div><span>${esc(a)}</span><b>${v}</b><em>${c}</em></div>`).join("")}</div>`;
  }

  function renderLand() {
    $("#land-pills").innerHTML = MK.filter(([k]) => L?.markets?.[k]).map(([k, t]) => `<button class="pill" type="button" data-k="${k}" aria-pressed="${k === mk}">${t}</button>`).join("");
    $("#land-pills").onclick = (e) => { const b = e.target.closest(".pill"); if (b) { mk = b.dataset.k; renderLand(); } };
    const m = L?.markets?.[mk];
    if (!m) { $("#land").innerHTML = `<div class="empty">첫 자동 수집 후 표시됩니다.</div>`; return; }
    const b = brokers(m), others = m.rows.filter((r) => r.kind === "korean" && !r.broker);
    const nLocal = b.filter((r) => r.kind === "local").length, kr = b.filter((r) => r.kind === "korean");
    const max = Math.max(...b.map((r) => r.equity_krw || 0), 1);
    const asof = [...new Set(m.rows.map((r) => r.asof).filter(Boolean))].sort().map(dot).join("·");
    const pdate = [...new Set(m.rows.map((r) => r.price_date).filter(Boolean))].sort().pop();
    const hasG = b.some((r) => r.growth != null);
    const rows = b.map((r, i) => `<tr class="${r.firm === HW ? "hw" : r.kind === "korean" ? "kr" : ""}"><td>${i + 1}</td>
      <td class="l">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(label(r))}</a>` : esc(label(r))}${r.kind === "korean" ? `<span class="tag ${r.firm === HW ? "hw" : "kr"}">${esc(r.firm)}</span>` : ""}${r.stale ? '<span class="tag old">이전 값</span>' : ""}</td>
      <td class="ib"><i style="width:${Math.max(1, (r.equity_krw / max) * 100).toFixed(1)}%"></i><span>${num(r.equity_krw)}</span></td><td>${num(r.equity, 2)}</td>
      ${hasG ? `<td>${r.growth != null ? sgn(r.growth) : '<span class="mut">–</span>'}</td>` : ""}<td>${sgn(r.ni, 2)}</td><td>${sgn(r.roe)}</td>
      <td>${r.mcap_krw != null ? num(r.mcap_krw) : r.kind === "korean" ? '<span class="mut">비상장</span>' : "–"}</td><td>${r.pb != null ? num(r.pb, 2) : "–"}</td></tr>`).join("");
    const top = kr[0];
    const lines = [];
    if (top && kr.length > 1) lines.push(`한국계 ${kr.length}곳 중 최대: ${esc(label(top))}(${esc(top.firm)}) ${num(top.equity_krw)}억원, ${b.indexOf(top) + 1}위`);
    if (m.median_pb != null) lines.push(`상장사 P/B 중앙값 <b>${num(m.median_pb, 2)}배</b>, ROE 중앙값 ${num(m.median_roe, 1)}%`);
    $("#land").innerHTML = `<p class="scope"><b>비교 대상</b> 현지 상장 증권사 ${nLocal}곳 + 한국계 현지법인 ${kr.length}곳 = ${b.length}곳.
        비상장 현지사(은행 계열 등)는 공시 재무를 자동으로 받을 수 없어 빠지므로, 여기 순위는 <b>시장 전체 순위보다 앞에</b> 나옵니다${mk === "vn" ? " (베트남은 은행 계열 등 비상장 증권사가 많아 전체 기준 순위는 이보다 뒤)" : ""}.</p>
      ${position(m, b)}
      ${lines.length ? `<p class="why">${lines.join(" · ")}</p>` : ""}
      <div class="split"><div>
        <div class="legend"><span><i style="background:var(--bar)"></i>현지 상장 증권사</span><span><i style="background:var(--kr)"></i>한국계 현지법인</span><span><i style="background:var(--accent)"></i>당사</span></div>
        ${mapChart(m, b)}
      </div><div>
        ${tm(`자본·순이익 ${asof} 결산${pdate ? ` · 시가총액 ${dot(pdate)} 종가` : ""}`, `원화 억원·현지 ${m.unit}, 증가율·ROE %, P/B 배`)}
        <div class="tw tall"><table><thead><tr><th>#</th><th class="l">회사</th><th>자기자본<small>억원</small></th><th>자기자본<small>${esc(m.unit)}</small></th>${hasG ? "<th>자본 증가율<small>1년, %</small></th>" : ""}<th>순이익<small>${esc(m.unit)}</small></th><th>ROE<small>%</small></th><th>시가총액<small>억원</small></th><th>P/B<small>배</small></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
        <p class="note">상장사 재무: 글로벌 탭과 같은 Yahoo Finance 수집${mk === "vn" ? " + 나머지 HOSE·HNX·UPCoM 증권사는 TCBS 공개 재무(각 사 공시 기반)" : ""}. 한국계는 모회사 DART 2025 사업보고서 종속기업 요약재무정보(원화)를 연말 환율 ${num(m.fx_ye, m.fx_ye < 1 ? 4 : 2)}원/${esc(m.ccy)}로 되돌린 값.
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
      if (me) k.push([`${nm} 자본 순위(상장사+한국계 ${me.n}곳 중)`, `${me.i}위<small>/ ${me.n}곳</small>`, `${label(me.r)} ${num(me.r.equity_krw)}억원 · 비상장 현지사 제외`]);
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
