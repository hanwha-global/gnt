// 전략 인사이트 탭. 진출국 전략 Takeaways(../data/domestic/takeaways.json, scripts/build_takeaways.py 가 매일 아침 생성),
// data/country.json(진출국 스코어카드), data/landscape.json(현지 경쟁 구도·밸류에이션),
// data/idx_share.json(인도네시아 거래대금 점유율), data/vn_hose.json(HOSE 발표 상위 10곳, 수동)·data/vn_brokerage.json(상장사 분기 중개수익, 자동),
// data/valuation.json(나라·시장별 상장 증권사 밸류에이션)을 그린다.
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
  // 법인 형태 꼬리(JSC·Corporation·Co., Ltd 등)를 떼고, 대문자 이름은 단어 첫 글자만 크게(3자 이하 약어는 그대로)
  const ACR = { Vpbank: "VPBank", Lpbank: "LPBank", Vndirect: "VNDirect", Mbs: "MBS" };
  const shortName = (n) => {
    let x = String(n || "").replace(/\s+/g, " ").trim().replace(/\s*[–-]\s*[^–-]*branch$/i, "").replace(/^PT\.?\s+/i, "")
      .replace(/[\s,.-]*(joint[\s-]*stock|join stock)?\s*(company|corporation|corporatio|corp|incorporated|jsc|co\.?,?\s*ltd)\.?$/i, "").trim();
    if (x === x.toUpperCase()) x = x.split(" ").map((w) => (w.length <= 3 ? w : ACR[w[0] + w.slice(1).toLowerCase()] || w[0] + w.slice(1).toLowerCase())).join(" ");
    return x;
  };
  const label = (r) => (r.firm === HW ? `${HWNAME[r.name] || r.name}` : shortName(r.name));
  const getJSON = async (u) => { try { const r = await fetch(u, { cache: "no-cache" }); return r.ok ? await r.json() : null; } catch (_) { return null; } };
  const median = (a) => { const v = a.filter((x) => x != null && !isNaN(x)).sort((p, q) => p - q), n = v.length; return n ? (n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2) : null; };
  let C, L, X, G, T, VH, VB, V;

  // ---------- 진출국 전략 Takeaways ----------
  // 나라마다 큰 변화가 있을 때만 문구가 바뀌고, 없으면 이전 문구에 '아침 확인' 표시만 붙는다.
  const TK_CAT = { "M&A·지분": "ma", "자본": "cap", "구조조정·비용": "cost", "마케팅·고객": "mkt", "상품·제휴": "prod", "리스크·규제": "risk" };
  function renderTk() {
    const order = ["VN", "ID", "SG"].filter((c) => T?.countries?.[c]?.bullets?.length);
    if (!order.length) return;
    const md = (s) => (s ? `${+s.slice(5, 7)}/${+s.slice(8, 10)}` : "");
    const flag = (c) => G?.markets?.find((m) => m.id === c.toLowerCase())?.flag || "";
    const checked = T.checked_at ? `${md(T.checked_at)} ${T.checked_at.slice(11, 16)}` : "";
    $("#tk").innerHTML = order.map((c) => {
      const b = T.countries[c];
      const regime = b.regime === "NEG" ? '<span class="st neg">구조적 악재</span>' : b.regime === "POS" ? '<span class="st pos">시장 지위 상향</span>' : "";
      const items = b.bullets.map((x) => `<li><span class="tk-cat ${TK_CAT[x.category] || ""}">${esc(x.category)}</span>${esc(x.text)}
        <div class="tk-ev">${esc(x.evidence.join(" · "))}${(x.links || []).filter((l) => /^https?:\/\//.test(l.url || "")).slice(0, 1).map((l) => ` <a href="${esc(l.url)}" target="_blank" rel="noopener" title="${esc(l.title || l.label)}">기사</a>`).join("")}</div></li>`).join("");
      // 그날 확인에 실패한 나라는 '큰 변화 없음'이라 하지 않고 이전 문구를 유지한다고만 적는다
      const quiet = !checked ? "" : b.last_check === "큰 변화 없음" ? ` · ${checked} 확인, 큰 변화 없음`
        : b.last_check === "확인 실패" ? ` · ${checked} 확인 실패(이전 문구 유지)` : "";
      return `<section class="tk-col"><h3><span aria-hidden="true">${flag(c)}</span>${esc(b.country)}<small>${esc(b.entities.join(" · "))}</small>${regime}</h3>
        <ol class="tk-list">${items}</ol><p class="tk-foot">${md(b.changed_at)} 갱신(${esc((b.reason || []).join(", "))})${quiet}</p></section>`;
    }).join("");
    $("#tm-tk").innerHTML = tmeta(`줄마다 근거의 시점${checked ? ` · 마지막 확인 ${checked} KST` : ""}`, "");
    $("#tk-card").hidden = false;
  }

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
    const mx = median(pts.map((p) => p.equity_krw)), my = median(pts.map((p) => p.roe));
    const xt = [];
    for (let e = Math.ceil(x0); e <= x1; e += 1) xt.push(10 ** e);
    const grid = xt.map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="8" y2="${H - B0}" stroke="var(--line)" stroke-dasharray="2 3"/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${v >= 1e4 ? `${v / 1e4}조` : `${num(v)}억`}</text>`).join("")
      + [y0, 0, y1].filter((v, i, a) => a.indexOf(v) === i).map((v) => `<line x1="${L0}" x2="${W - 10}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"${v === 0 ? "" : ' stroke-dasharray="2 3"'}/><text x="${L0 - 4}" y="${Y(v) + 3}" text-anchor="end">${v}%</text>`).join("");
    const medl = `<line x1="${X(mx)}" x2="${X(mx)}" y1="8" y2="${H - B0}" stroke="var(--accent)" stroke-opacity=".35"/><line x1="${L0}" x2="${W - 10}" y1="${Y(my)}" y2="${Y(my)}" stroke="var(--accent)" stroke-opacity=".35"/>`;
    const col = (r) => (r.firm === HW ? "var(--accent)" : r.kind === "korean" ? "var(--kr)" : "var(--bar)");
    const order = [...pts].sort((p, q) => (p.firm === HW) - (q.firm === HW) || (p.kind === "korean") - (q.kind === "korean"));
    const topN = new Set(b.slice(0, 4));
    const dots = order.map((p) => `<circle cx="${X(p.equity_krw).toFixed(1)}" cy="${Y(p.roe).toFixed(1)}" r="${p.firm === HW ? 6 : 4}" fill="${col(p)}" fill-opacity="${p.kind === "local" ? .75 : .95}" stroke="var(--bg)" stroke-width="1"><title>${esc(label(p))}: 자기자본 ${num(p.equity_krw)}억원 · ROE ${p.roe}%</title></circle>`).join("");
    // 라벨: 당사 → 한국계 → 상위 4곳 순으로 놓고, 겹치면 위아래로 비켜 놓는다(점 옆 글자가 서로 덮지 않게)
    const placed = [];
    const labs = [...order].reverse().map((p) => {
      const t = p.firm === HW ? label(p) : p.kind === "korean" ? (p.firm || "").replace(/투자증권|증권/g, "") : topN.has(p) ? p.ticker : "";
      if (!t) return "";
      const w = [...t].reduce((a, c) => a + (c.charCodeAt(0) > 255 ? 10 : 6), 0), x = X(p.equity_krw) + 7, cy = Y(p.roe) + 3;
      const flip = x + w > W - 4;
      const bx = flip ? X(p.equity_krw) - 7 - w : x;
      for (const dy of [0, -11, 11, -22, 22, -33, 33]) {
        const y = cy + dy;
        if (!placed.some((q) => bx < q.x + q.w && q.x < bx + w && Math.abs(y - q.y) < 10.5)) {
          placed.push({ x: bx, y, w });
          const lead = dy ? `<line x1="${X(p.equity_krw).toFixed(1)}" y1="${Y(p.roe).toFixed(1)}" x2="${(flip ? bx + w : bx).toFixed(1)}" y2="${(y - 3).toFixed(1)}" stroke="var(--line)"/>` : "";
          return `${lead}<text x="${(flip ? bx + w : bx).toFixed(1)}" y="${y.toFixed(1)}"${flip ? ' text-anchor="end"' : ""}${p.firm === HW ? ' style="fill:var(--accent-ink);font-weight:700"' : p.kind === "korean" ? ' style="fill:var(--kr)"' : ""}>${esc(t)}</text>`;
        }
      }
      return "";
    }).join("");
    return `${tm("자기자본·ROE 최근 연간 결산", "가로 억원(로그 눈금), 세로 ROE %")}
      <svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block" role="img" aria-label="규모와 수익성 지도">${grid}${medl}${dots}${labs}</svg>
      <p class="note">점 하나가 증권사 하나이고, 오른쪽 위로 갈수록 크고 잘 버는 곳입니다. 주황 옅은 선은 비교 대상의 자본·ROE 중앙값(${num(mx)}억원 · ${num(my, 1)}%). ROE는 −30~40% 밖이면 끝에 붙였습니다.</p>`;
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
    const gmed = median(grow), emed = median(b.map((r) => r.equity_krw));
    const cells = [
      ["자기자본 순위", `${rank}위<small>/ ${n}곳</small>`, `중앙값(${num(emed)}억원)의 ${num(me.equity_krw / emed, 2)}배 · 자본 합계의 ${num((me.equity_krw / total) * 100, 2)}%`],
      ["수익성(ROE) 순위", roeRank ? `${roeRank}위<small>/ ${roeRows.length}곳</small>` : "–", `ROE ${num(me.roe, 1)}% · ${roeRows.length}곳 중앙값 ${num(median(roeRows.map((r) => r.roe)), 1)}%`],
      ["상위 10곳 평균 자본", `${num(avg10 / me.equity_krw, 1)}배<small>당사 대비</small>`, `평균 ${num(avg10)}억원 vs 당사 ${num(me.equity_krw)}억원`],
      ...[20, 10].filter((k) => tgt(k) != null).slice(0, 1).map((k) => [`${k}위 진입까지 자본`, `+${num(tgt(k))}억<small>원</small>`, `${k}위 ${esc(label(b[k - 1]))} ${num(b[k - 1].equity_krw)}억원 수준${k === 20 && tgt(10) != null ? ` · 10위까지 +${num(tgt(10))}억원` : ""}`]),
    ];
    if (gmed != null) cells.push(["상장사 자본 증가율(1년)", `${num(gmed, 1)}%<small>중앙값</small>`, `최대 ${esc(label(b.filter((r) => r.growth != null).sort((p, q) => q.growth - p.growth)[0]))} ${num(grow.at(-1), 1)}% · 증자 경쟁 강도`]);
    // 올해 들어서도 자본을 늘리는지: 최근 분기 자본 ÷ 연말 자본(현지 통화, 같은 분기를 낸 상장사만)
    const qd = b.map((r) => r.q_date).filter(Boolean).sort().pop();
    const qs = b.filter((r) => r.q_date === qd && r.q_equity && r.equity && r.q_date > r.asof);
    if (qs.length >= 5) {
      const g = (qs.reduce((a, r) => a + r.q_equity, 0) / qs.reduce((a, r) => a + r.equity, 0) - 1) * 100;
      cells.push([`올해 상장사 자본 증가(${ym(qd)}까지)`, `${g >= 0 ? "+" : ""}${num(g, 1)}%<small>합계</small>`, `${qs.length}곳 연말 대비 · 당사 법인은 연간 공시만 있어 비교 제외`]);
    }
    return `<div class="posn">${cells.map(([a, v, c]) => `<div><span>${esc(a)}</span><b>${v}</b><em>${c}</em></div>`).join("")}</div>`;
  }

  // 시장 구조: 자본·마진 잔고·중개수익이 상위 5곳에 얼마나 몰렸나(베트남은 상장사 공시 항목까지)
  function structure(b) {
    const share = (rows, k) => {
      const v = rows.map((r) => r[k]).filter((x) => x > 0).sort((p, q) => q - p), t = v.reduce((a, x) => a + x, 0);
      return v.length > 5 ? { top: (v.slice(0, 5).reduce((a, x) => a + x, 0) / t) * 100, n: v.length, t } : null;
    };
    const loc = b.filter((r) => r.kind === "local");
    const items = [["자기자본", share(b, "equity_krw"), "상장사+한국계"], ["마진·대출 잔고", share(loc, "loans_krw"), "상장사"], ["중개수수료 수익", share(loc, "brokerage_krw"), "상장사"]].filter(([, v]) => v);
    if (!items.length) return "";
    const lev = loc.filter((r) => r.loans_krw && r.equity_krw > 0).map((r) => r.loans_krw / r.equity_krw).sort((p, q) => p - q);
    const asof = [...new Set(loc.map((r) => r.asof).filter(Boolean))].sort().pop();
    return `${tm(`${dot(asof)} 연간 결산`, "%, 억원")}
      <div class="bars">${items.map(([t, v, who]) => `<div class="bar"><span class="nm">${t} <span class="mut">상위 5곳</span></span><span class="tr"><i style="width:${v.top.toFixed(1)}%"></i></span><span class="v">${num(v.top, 1)}%</span></div>
        <div class="note" style="margin:0 0 3px">${who} ${v.n}곳 합계 ${num(v.t)}억원 중 상위 5곳 몫</div>`).join("")}</div>
      ${lev.length ? `<p class="note">마진·대출 잔고 ÷ 자기자본 중앙값 <b>${num(median(lev), 2)}배</b>(최대 ${num(lev.at(-1), 2)}배): 자본을 신용공여에 얼마나 쓰는지. 베트남은 마진 대출 합계를 자기자본의 2배 이내로 묶습니다(재무부 Circular 121/2020).</p>` : ""}`;
  }

  const SORTS = [["equity_krw", "자기자본"], ["roe", "ROE"], ["growth", "자본 증가율"], ["loans_krw", "마진·대출 잔고"], ["brokerage_krw", "중개수익"], ["pb", "P/B"]];
  let sk = "equity_krw";
  function renderLand() {
    $("#land-pills").innerHTML = MK.filter(([k]) => L?.markets?.[k]).map(([k, t]) => `<button class="pill" type="button" data-k="${k}" aria-pressed="${k === mk}">${t}</button>`).join("");
    $("#land-pills").onclick = (e) => { const b = e.target.closest(".pill"); if (b) { mk = b.dataset.k; sk = "equity_krw"; renderLand(); } };
    const m = L?.markets?.[mk];
    if (!m) { $("#land").innerHTML = `<div class="empty">첫 자동 수집 후 표시됩니다.</div>`; return; }
    const b = brokers(m), others = m.rows.filter((r) => r.kind === "korean" && !r.broker);
    const nLocal = b.filter((r) => r.kind === "local").length, kr = b.filter((r) => r.kind === "korean");
    const vnd = m.rows.some((r) => r.via === "vndirect");
    const max = Math.max(...b.map((r) => r.equity_krw || 0), 1);
    const asof = [...new Set(m.rows.map((r) => r.asof).filter(Boolean))].sort().map(dot).join("·");
    const pdate = [...new Set(m.rows.map((r) => r.price_date).filter(Boolean))].sort().pop();
    const has = (k) => b.some((r) => r[k] != null);
    const hasG = has("growth"), hasL = has("loans_krw"), hasB = has("brokerage_krw");
    const bsum = b.reduce((a, r) => a + (r.brokerage_krw || 0), 0);
    const sorts = SORTS.filter(([k]) => has(k));
    if (!sorts.some(([k]) => k === sk)) sk = "equity_krw";
    const list = [...b].sort((p, q) => (q[sk] ?? -Infinity) - (p[sk] ?? -Infinity));
    const loc = (r, k) => (r[k] != null ? `${num(r[k], 2)} ${m.unit}` : "–");
    const rows = list.map((r) => `<tr class="${r.firm === HW ? "hw" : r.kind === "korean" ? "kr" : ""}" title="자기자본 ${loc(r, "equity")} · 순이익 ${loc(r, "ni")}${r.note ? ` · ${r.note}` : ""}"><td>${r[sk] != null ? list.indexOf(r) + 1 : "–"}</td>
      <td class="l">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(label(r))}</a>` : esc(label(r))}${r.kind === "korean" ? `<span class="tag ${r.firm === HW ? "hw" : "kr"}">${esc(r.firm)}</span>` : r.ticker ? `<span class="mut"> ${esc(r.ticker)}</span>` : ""}${r.stale ? '<span class="tag old">이전 값</span>' : ""}</td>
      <td class="ib"><i style="width:${Math.max(1, (r.equity_krw / max) * 100).toFixed(1)}%"></i><span>${num(r.equity_krw)}</span></td>
      ${hasG ? `<td>${r.growth != null ? sgn(r.growth) : '<span class="mut">–</span>'}</td>` : ""}<td>${sgn(r.roe)}</td>
      ${hasL ? `<td${r.loans_krw && r.equity_krw > 0 ? ` title="잔고 ÷ 자기자본 ${num(r.loans_krw / r.equity_krw, 2)}배"` : ""}>${num(r.loans_krw)}</td>` : ""}
      ${hasB ? `<td>${r.brokerage_krw ? num((r.brokerage_krw / bsum) * 100, 2) : "–"}</td>` : ""}
      <td>${r.mcap_krw != null ? num(r.mcap_krw) : r.kind === "korean" ? '<span class="mut">비상장</span>' : "–"}</td><td>${r.pb != null ? num(r.pb, 2) : "–"}</td></tr>`).join("");
    const top = kr[0];
    const lines = [];
    if (top && kr.length > 1) lines.push(`한국계 ${kr.length}곳 중 최대: ${esc(label(top))}(${esc(top.firm)}) ${num(top.equity_krw)}억원, ${b.indexOf(top) + 1}위`);
    if (m.median_pb != null) lines.push(`상장사 P/B 중앙값 <b>${num(m.median_pb, 2)}배</b>, ROE 중앙값 ${num(m.median_roe, 1)}%`);
    const scope = vnd
      ? `<b>비교 대상</b> 베트남 거래소(HOSE·HNX·UPCoM)에 상장된 증권사 전체 ${nLocal}곳(VNDirect 공개 재무, 매일 자동) + 한국계 현지법인 ${kr.length}곳(DART) = ${b.length}곳.
        비상장 증권사(은행·외국계 자회사 다수)는 최근 재무를 기계로 받을 출처가 없어 빠지므로, 비상장사까지 넣은 시장 전체 순위는 여기보다 뒤입니다.`
      : `<b>비교 대상</b> 현지 상장 증권사 ${nLocal}곳 + 한국계 현지법인 ${kr.length}곳 = ${b.length}곳. 비상장 현지사는 공시 재무를 자동으로 받을 수 없어 빠지므로, 여기 순위는 시장 전체 순위보다 앞에 나옵니다.`;
    $("#land").innerHTML = `<p class="scope">${scope}</p>
      ${position(m, b)}
      <div class="split"><div>
        <div class="legend"><span><i style="background:var(--bar)"></i>현지 상장 증권사</span><span><i style="background:var(--kr)"></i>한국계 현지법인</span><span><i style="background:var(--accent)"></i>당사</span></div>
        ${mapChart(m, b)}
        ${structure(b)}
        ${lines.length ? `<p class="why" style="margin-top:6px">${lines.join(" · ")}</p>` : ""}
      </div><div>
        <div class="pills noprint" id="land-sort" role="group" aria-label="정렬"><span class="mut" style="font-size:11px;align-self:center">정렬</span>${sorts.map(([k, t]) => `<button class="pill" type="button" data-s="${k}" aria-pressed="${k === sk}">${t}</button>`).join("")}</div>
        ${tm(`자본·순이익·잔고·수익 ${asof} 결산${pdate ? ` · 시가총액 ${dot(pdate)} 종가` : ""}`, "억원(원화 환산), %, 배")}
        <div class="tw tall"><table><thead><tr><th>#</th><th class="l">회사</th><th>자기자본<small>억원</small></th>${hasG ? "<th>자본 증가율<small>1년, %</small></th>" : ""}<th>ROE<small>%</small></th>
          ${hasL ? "<th>마진·대출 잔고<small>억원</small></th>" : ""}${hasB ? "<th>중개수익 비중<small>상장사 합계 대비 %</small></th>" : ""}<th>시가총액<small>억원</small></th><th>P/B<small>배</small></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
        <p class="note">${vnd ? "베트남 상장사: VNDirect 공개 재무(각 사 감사 재무제표, 증권사 양식의 자기자본·지배주주 순이익·마진 대출·중개수수료 수익)와 시가총액·P/B." : "상장사 재무: 글로벌 탭과 같은 Yahoo Finance 수집."}
        한국계는 모회사 DART 2025 사업보고서 종속기업 요약재무정보(원화)${hasL || hasB ? "라 잔고·중개수익 칸이 비고" : "이고"}, 현지 통화 값은 연말 환율 ${num(m.fx_ye, m.fx_ye < 1 ? 4 : 2)}원/${esc(m.ccy)}로 되돌렸습니다. 행에 마우스를 올리면 현지 통화(${esc(m.unit)}) 값이 보입니다.
        ${hasB ? "중개수익 비중은 거래대금 점유율이 아니라 상장사 중개수수료 수익 합계 대비 몫입니다(점유율 대용)." : ""}
        ${others.length ? `<br>순위 제외 한국계(운용·기타): ${others.map((r) => `${esc(r.name)}(${esc(r.firm)}, ${num(r.equity_krw)}억원)`).join(", ")}` : ""}
        ${mk === "jp" && !kr.length ? "<br>일본에는 DART 요약재무정보가 있는 한국계 증권 현지법인이 없습니다." : ""}</p>
      </div></div>`;
    $("#land-sort").onclick = (e) => { const x = e.target.closest(".pill"); if (x) { sk = x.dataset.s; renderLand(); } };
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

  // ---------- 베트남 점유율: 거래소 발표 상위 10곳(수동) + 상장사 전체 분기 중개수익(자동) ----------
  const qlab = (d) => `${Math.ceil(+d.slice(5, 7) / 3)}Q${d.slice(2, 4)}`;  // 2026-09-30 → 3Q26
  const spark = (vals) => {  // 작은 추이선(분기 점유율)
    const ok = vals.filter((x) => x != null);
    if (ok.length < 2) return "";
    const W = 64, H = 16, mn = Math.min(...ok), mx = Math.max(...ok), sx = W / (vals.length - 1);
    const pts = vals.map((x, i) => (x == null ? null : `${(i * sx).toFixed(1)},${(H - 2 - ((x - mn) / (mx - mn || 1)) * (H - 4)).toFixed(1)}`)).filter(Boolean).join(" ");
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true" style="vertical-align:middle"><polyline points="${pts}" fill="none" stroke="var(--bar)" stroke-width="1.5"/></svg>`;
  };
  function renderVn() {
    const cur = VH?.quarters?.[0], prv = VH?.quarters?.[1];
    let a = "", b = "";
    if (cur) {
      const pr = Object.fromEntries((prv?.rows || []).map((r, i) => [r.name, { v: r.value, i: i + 1 }]));
      const max = Math.max(...cur.rows.map((r) => r.value), 1);
      // 다음 분기 발표 시기(분기 말 + 보름)가 지났는데 입력이 없으면 화면에 드러낸다
      const qn = +cur.q.slice(5), nq = (qn % 4) + 1, ny = +cur.q.slice(0, 4) + (qn === 4 ? 1 : 0);
      const late = Date.now() > Date.UTC(ny, nq * 3, 15);
      const out = (prv?.rows || []).filter((r) => !cur.rows.some((c) => c.name === r.name)).map((r) => r.name);
      const krs = cur.rows.map((r, i) => (r.korean ? `${shortName(r.name)} ${i + 1}위${pr[r.name] ? (pr[r.name].i > i + 1 ? `(▲${pr[r.name].i - i - 1})` : pr[r.name].i < i + 1 ? `(▼${i + 1 - pr[r.name].i})` : "") : "(신규)"}` : "")).filter(Boolean);
      const rows = cur.rows.map((r, i) => {
        const p = pr[r.name], mv = p ? p.i - (i + 1) : null;
        return `<tr class="${r.korean ? "kr" : ""}"><td>${i + 1}</td><td class="l">${esc(r.name)}${r.korean ? `<span class="tag kr">${esc(r.korean)}</span>` : ""}</td>
          <td class="ib"><i style="width:${((r.value / max) * 100).toFixed(1)}%"></i><span>${num(r.value, 2)}</span></td><td>${p ? num(p.v, 2) : "–"}</td>
          <td>${p ? sgn(r.value - p.v, 2) : '<span class="mut">신규</span>'}</td><td>${mv == null ? '<span class="mut">신규</span>' : mv > 0 ? `<span class="pos">▲${mv}</span>` : mv < 0 ? `<span class="neg">▼${-mv}</span>` : '<span class="mut">–</span>'}</td></tr>`;
      }).join("");
      a = `<p class="why"><b>베트남 법인(PTSV)</b>은 상위 10위 밖 · 한국계 ${esc(krs.join(" · "))} · 상위 10곳 합계 ${num(cur.top10, 2)}%${prv ? `(${esc(prv.label)} ${num(prv.top10, 2)}%)` : ""}</p>
        ${tm(`${cur.label} · ${dot(cur.published)} HOSE 발표`, "%(중개 거래대금 비중), %p")}
        <div class="legend"><span class="tag man">수동</span><span>거래소가 상위 10곳만 기계 판독이 어려운 형식으로 발표 → 발표 뒤 두 매체 대조해 입력</span>${late ? `<span class="tag old">${nq}Q${String(ny).slice(2)} 발표분 입력 필요</span>` : ""}</div>
        <div class="tw"><table><thead><tr><th>#</th><th class="l">HOSE 회원사</th><th>${esc(cur.label)}<small>%</small></th><th>${esc(prv?.label || "전 분기")}<small>%</small></th><th>증감<small>%p</small></th><th>순위<small>전 분기 대비</small></th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="note">${out.length ? `10위 밖으로: ${esc(out.join(", "))} · ` : ""}출처: ${cur.sources.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>`).join(" · ")}${prv ? ` · ${esc(prv.label)}: ${prv.sources.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>`).join(" · ")}` : ""}</p>`;
    }
    if (VB?.rows?.length) {
      const qs = VB.quarters, last = qs.at(-1), pq = qs.at(-2), yq = qs.find((q) => q === `${+last.slice(0, 4) - 1}${last.slice(4)}`);
      const hose = Object.fromEntries((cur?.rows || []).filter((r) => r.code).map((r, i) => [r.code, i + 1]));
      const have = VB.rows.filter((r) => r.share[last] != null), miss = VB.rows.filter((r) => r.share[last] == null);
      const max = Math.max(...have.map((r) => r.share[last]), 1);
      const top5 = have.slice(0, 5).reduce((x, r) => x + r.share[last], 0);
      const rows = have.map((r, i) => `<tr><td>${i + 1}</td><td class="l">${esc(shortName(r.name))} <span class="mut">${esc(r.code)}</span>${hose[r.code] ? `<span class="tag old">HOSE ${hose[r.code]}위</span>` : ""}</td>
        <td class="ib"><i style="width:${((r.share[last] / max) * 100).toFixed(1)}%"></i><span>${num(r.share[last], 2)}</span></td>
        <td>${num(r.share[pq], 2)}</td>${yq ? `<td>${num(r.share[yq], 2)}</td>` : ""}<td>${num(r.ytd, 2)}</td><td>${spark(qs.map((q) => r.share[q]))}</td></tr>`).join("");
      b = `<h3 class="sub">11위 이하까지: 상장 증권사 중개수익 점유율 <span class="tag auto">자동</span></h3>
        <p class="why">거래소는 상위 10곳 밖을 공개하지 않아, 상장 증권사 ${have.length}곳의 분기 중개수수료 수익 비중으로 순위를 끝까지 잇습니다. 상위 5곳 ${num(top5, 1)}%.</p>
        ${tm(`${qlab(last)} 분기 재무(상장 ${VB.reported[last]}곳 보고, 합계 ${num(VB.total_bn[last])}십억동) · 올해 누적 ${qlab(VB.ytd_quarters[0])}~${qlab(last)}`, "%(상장 증권사 중개수수료 수익 합계 대비)")}
        <div class="tw vnb"><table><thead><tr><th>#</th><th class="l">상장 증권사</th><th>${qlab(last)}<small>%</small></th><th>${pq ? qlab(pq) : "전 분기"}<small>%</small></th>${yq ? `<th>${qlab(yq)}<small>전년 동기</small></th>` : ""}<th>올해 누적<small>%</small></th><th>추이<small>${qlab(qs[0])}~${qlab(last)}</small></th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="note">${esc(VB.method)}. 한국계(KIS·미래에셋·KB·신한·NH)와 PTSV는 비상장이라 빠집니다.${miss.length ? ` 아직 ${qlab(last)} 재무를 안 낸 곳: ${esc(miss.map((r) => r.code).join(", "))}.` : ""}${VB.pending ? ` ${qlab(VB.pending.q)}은 ${esc(VB.pending.missing.slice(0, 4).join(", "))}${VB.pending.missing.length > 4 ? ` 등 ${VB.pending.missing.length}곳` : ""}이 아직 안 내 집계 대기(${VB.pending.reported}곳 보고), 모이면 자동 반영.` : ""} 출처: <a href="${esc(VB.source.url)}" target="_blank" rel="noopener">${esc(VB.source.label)}</a></p>`;
    }
    $("#vn").innerHTML = a || b ? a + b : `<div class="empty">자료 없음</div>`;
  }

  // ---------- 밸류에이션: 나라·시장별 상장 증권사 ----------
  const VGROUP = ["국내", "진출국", "아시아", "미주·유럽"];
  let vk = "kr", vsort = "mcap_krw";
  // 겹치지 않게 라벨 놓기: 점 오른쪽 → 위아래로 비켜 → 그래도 겹치면 생략
  function svgLabels(items, W) {
    const placed = [];
    return items.map((p) => {
      const w = [...p.t].reduce((a, c) => a + (c.charCodeAt(0) > 255 ? 10 : 6), 0);
      const flip = p.x + p.r + 3 + w > W - 4, bx = flip ? p.x - p.r - 3 - w : p.x + p.r + 3;
      for (const dy of [0, -11, 11, -22, 22]) {
        const y = p.y + 3 + dy;
        if (!placed.some((q) => bx < q.x + q.w && q.x < bx + w && Math.abs(y - q.y) < 10.5)) {
          placed.push({ x: bx, y, w });
          return `<text x="${(flip ? bx + w : bx).toFixed(1)}" y="${y.toFixed(1)}"${flip ? ' text-anchor="end"' : ""}${p.style ? ` style="${p.style}"` : ""}>${esc(p.t)}</text>`;
        }
      }
      return "";
    }).join("");
  }
  function bubble(ms, me) {
    const pts = ms.filter(([, m]) => m.median_pb != null && m.median_roe != null);
    if (pts.length < 3) return "";
    const W = 460, H = 250, L0 = 30, B0 = 22, T0 = 10, R0 = 12;
    const xs = pts.map(([, m]) => m.median_roe).concat(me?.roe != null ? [me.roe] : []), ys = pts.map(([, m]) => m.median_pb);
    const x0 = Math.min(0, Math.floor(Math.min(...xs) / 5) * 5), x1 = Math.max(5, Math.ceil(Math.max(...xs) / 5) * 5);
    const y1 = Math.max(1, Math.ceil(Math.max(...ys) * 2) / 2);
    const X = (v) => L0 + ((v - x0) / (x1 - x0)) * (W - L0 - R0), Y = (v) => H - B0 - (v / y1) * (H - B0 - T0);
    const big = Math.max(...pts.map(([, m]) => m.mcap_krw || 0), 1), R = (v) => 3 + Math.sqrt((v || 0) / big) * 15;
    const col = (g) => (g === "국내" ? "var(--accent)" : g === "진출국" ? "var(--kr)" : "var(--bar)");
    const xstep = x1 - x0 > 30 ? 10 : 5, ystep = y1 > 3 ? 1 : 0.5;
    let grid = "";
    for (let v = x0; v <= x1; v += xstep) grid += `<line x1="${X(v)}" x2="${X(v)}" y1="${T0}" y2="${H - B0}" stroke="var(--line)"${v === 0 ? "" : ' stroke-dasharray="2 3"'}/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${v}%</text>`;
    for (let v = 0; v <= y1 + 1e-9; v += ystep) grid += `<line x1="${L0}" x2="${W - R0}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"${v === 0 ? "" : ' stroke-dasharray="2 3"'}/><text x="${L0 - 4}" y="${Y(v) + 3}" text-anchor="end">${num(v, 1)}</text>`;
    grid += `<line x1="${L0}" x2="${W - R0}" y1="${Y(1)}" y2="${Y(1)}" stroke="var(--accent)" stroke-opacity=".35"/><text x="${W - R0}" y="${Y(1) - 3}" text-anchor="end" style="fill:var(--accent-ink)">P/B 1배</text>`;
    const order = [...pts].sort(([, p], [, q]) => (q.mcap_krw || 0) - (p.mcap_krw || 0));
    const dots = order.map(([k, m]) => `<circle cx="${X(m.median_roe).toFixed(1)}" cy="${Y(m.median_pb).toFixed(1)}" r="${R(m.mcap_krw).toFixed(1)}" fill="${col(m.group)}" fill-opacity="${m.group === "아시아" || m.group === "미주·유럽" ? .45 : .8}" stroke="${k === vk ? "var(--text)" : "var(--bg)"}" stroke-width="${k === vk ? 1.5 : 1}"><title>${esc(m.name)}: P/B 중앙값 ${num(m.median_pb, 2)}배 · ROE 중앙값 ${num(m.median_roe, 1)}% · ${m.n}곳 시가총액 ${num(m.mcap_krw / 1e4, 1)}조원</title></circle>`).join("");
    const meDot = me?.roe != null && me.pb != null ? `<rect x="${(X(me.roe) - 4).toFixed(1)}" y="${(Y(me.pb) - 4).toFixed(1)}" width="8" height="8" transform="rotate(45 ${X(me.roe).toFixed(1)} ${Y(me.pb).toFixed(1)})" fill="var(--accent)" stroke="var(--bg)"><title>한화투자증권 P/B ${num(me.pb, 2)}배 · ROE ${num(me.roe, 1)}%</title></rect>` : "";
    const labs = svgLabels([
      ...(meDot ? [{ x: X(me.roe), y: Y(me.pb), r: 5, t: "한화투자증권", style: "fill:var(--accent-ink);font-weight:700" }] : []),
      ...order.map(([, m]) => ({ x: X(m.median_roe), y: Y(m.median_pb), r: R(m.mcap_krw), t: m.name.replace(/\(.*\)/, ""), style: m.group === "국내" ? "fill:var(--accent-ink);font-weight:700" : m.group === "진출국" ? "fill:var(--kr)" : "" })),
    ], W);
    return `${tm("시장별 중앙값 · 원 크기 = 시가총액 합계", "가로 ROE %, 세로 P/B 배")}
      <svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block" role="img" aria-label="시장별 P/B와 ROE">${grid}${dots}${meDot}${labs}</svg>
      <div class="legend"><span><i style="background:var(--accent)"></i>한국(◆ 한화투자증권)</span><span><i style="background:var(--kr)"></i>진출국</span><span><i style="background:var(--bar)"></i>그 밖의 시장</span></div>`;
  }
  function renderVal() {
    if (!V?.markets) { renderValL(); return; }
    const ms = Object.entries(V.markets).filter(([, m]) => m.rows?.length);
    if (!ms.find(([k]) => k === vk)) vk = ms[0][0];
    const me = V.markets.kr?.rows?.find((r) => r.name === HW);
    const pbmax = Math.max(...ms.map(([, m]) => m.median_pb || 0), 1);
    const pd = ms.map(([, m]) => m.price_date).filter(Boolean).sort().pop();
    const body = VGROUP.map((g) => {
      const gm = ms.filter(([, m]) => m.group === g);
      return gm.length ? `<tr class="grp"><td colspan="7">${esc(g)}</td></tr>` + gm.map(([k, m]) => `<tr class="mk${k === vk ? " sel" : ""}${g === "국내" ? " home" : ""}" data-k="${k}" tabindex="0"><td class="l">${esc(m.name)}</td><td>${m.n}</td><td>${num(m.mcap_krw / 1e4, 1)}</td>
        <td class="ib"><i style="width:${(((m.median_pb || 0) / pbmax) * 100).toFixed(1)}%"></i><span>${num(m.median_pb, 2)}</span></td><td>${sgn(m.median_roe)}</td><td>${num(m.median_pe, 1)}</td>
        <td class="l">${esc(shortName(m.rows[0]?.name || ""))}</td></tr>`).join("") : "";
    }).join("");
    const kr = V.markets.kr;
    $("#val-mkt").innerHTML = `${tm(`시가총액 ${dot(pd)} 종가 · 자본 최근 분기 · ROE·P/E 최근 4개 분기`, "개, 조원(원화 환산), 배, %")}
      <div class="tw"><table class="mtab"><thead><tr><th class="l">시장<small>줄을 누르면 오른쪽 표</small></th><th>회사<small>개</small></th><th>시가총액 합계<small>조원</small></th><th>P/B 중앙값<small>배</small></th><th>ROE 중앙값<small>%</small></th><th>P/E 중앙값<small>배</small></th><th class="l">시가총액 1위</th></tr></thead><tbody>${body}</tbody></table></div>
      ${bubble(ms, me)}
      <p class="note">읽는 법: 오른쪽 위로 갈수록 시장이 수익성을 높게 쳐 주는 곳입니다. ${kr ? `한국 증권사는 P/B 중앙값 ${num(kr.median_pb, 2)}배로 ` : ""}P/B 1배 선보다 아래에 있으면 장부가보다 싸게 거래된다는 뜻이고, 현지 P/B가 높을수록 현지 증권사를 인수할 때 장부가 대비 웃돈이 큽니다.</p>`;
    $("#val-mkt").onclick = (e) => { const t = e.target.closest("tr.mk"); if (t) { vk = t.dataset.k; renderVal(); } };
    $("#val-mkt").onkeydown = (e) => { const t = e.target.closest("tr.mk"); if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); vk = t.dataset.k; renderVal(); } };

    const m = V.markets[vk];
    const SORT = [["mcap_krw", "시가총액"], ["pb", "P/B"], ["roe", "ROE"], ["pe", "P/E"]];
    const list = [...m.rows].sort((p, q) => (q[vsort] ?? -Infinity) - (p[vsort] ?? -Infinity));
    const mine = vk === "kr" && me;
    const rows = list.map((r, i) => `<tr class="${r.name === HW ? "hw" : ""}" title="${esc([r.name_y, r.symbol, r.ccy && r.fccy && r.ccy !== r.fccy ? `주가 ${r.ccy} · 재무 ${r.fccy}` : r.ccy].filter(Boolean).join(" · "))}"><td>${r[vsort] != null ? i + 1 : "–"}</td>
      <td class="l">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(shortName(r.name))}</a>` : esc(shortName(r.name))}${r.note ? `<span class="mut"> ${esc(r.note)}</span>` : ""}${r.stale ? '<span class="tag old">이전 값</span>' : ""}</td>
      <td>${num(r.mcap_krw)}</td><td>${num(r.equity_krw)}</td><td>${r.pb != null ? num(r.pb, 2) : "–"}</td><td>${sgn(r.roe)}${r.roe_basis === "연간" ? '<span class="mut">ᵃ</span>' : ""}</td><td>${r.pe != null ? num(r.pe, 1) : r.roe != null && r.roe <= 0 ? '<span class="mut">적자</span>' : "–"}</td><td class="mut">${ym(r.eq_asof)}</td></tr>`).join("");
    $("#val-kr").innerHTML = `<div class="pills noprint" id="val-pills" role="group" aria-label="시장">${ms.map(([k, x]) => `<button class="pill" type="button" data-k="${k}" aria-pressed="${k === vk}">${esc(x.name.replace(/\(.*\)/, ""))}</button>`).join("")}</div>
      <p class="why"><b>${esc(m.name)}</b> 상장 증권사 ${m.n}곳 · P/B 중앙값 <b>${num(m.median_pb, 2)}배</b> · ROE ${num(m.median_roe, 1)}% · P/E ${num(m.median_pe, 1)}배${mine ? ` · <b>한화투자증권</b> P/B ${num(me.pb, 2)}배, 시가총액 ${m.rows.indexOf(me) + 1}위/${m.n}곳` : ""}</p>
      <div class="pills sm noprint" id="val-sort" role="group" aria-label="정렬"><span class="mut" style="font-size:11px;align-self:center">정렬</span>${SORT.map(([k, t]) => `<button class="pill" type="button" data-s="${k}" aria-pressed="${k === vsort}">${t}</button>`).join("")}</div>
      ${tm(`시가총액 ${dot(m.price_date)} 종가 · 자본 최근 분기(줄 끝 날짜) · ROE·P/E 최근 4개 분기 순이익(ᵃ 표시는 최근 연간)`, "억원(원화 환산), 배, %")}
      <div class="tw tall"><table><thead><tr><th>#</th><th class="l">회사</th><th>시가총액<small>억원</small></th><th>자기자본<small>억원</small></th><th>P/B<small>배</small></th><th>ROE<small>%</small></th><th>P/E<small>배</small></th><th>자본 기준</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="note">${vk === "kr" ? "한국금융지주는 한국투자증권의 상장 지주사입니다. " : ""}${vk === "hk" ? "본토 증권사 H주는 같은 회사의 A주(중국 본토 줄)보다 싸게 거래되는 일이 많습니다. " : ""}${vk === "vn" ? "베트남은 현지 경쟁 구도와 같은 VNDirect 값입니다. " : ""}출처: <a href="${esc(V.source.url)}" target="_blank" rel="noopener">${esc(V.source.label)}</a>. ${esc(V.method)}.${V.errors?.length ? ` 이번 수집에서 받지 못한 종목 ${V.errors.length}곳은 이전 값을 쓰거나 뺐습니다.` : ""}</p>`;
    $("#val-pills").onclick = (e) => { const x = e.target.closest(".pill"); if (x) { vk = x.dataset.k; renderVal(); } };
    $("#val-sort").onclick = (e) => { const x = e.target.closest(".pill"); if (x) { vsort = x.dataset.s; renderVal(); } };
  }

  // valuation.json 이 아직 없을 때(첫 수집 전): 현지 경쟁 구도 파일의 값으로 간단히
  function renderValL() {
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
    const kr = V?.markets?.kr || L?.markets?.kr, me = kr?.rows?.find((r) => r.name === HW);
    if (me) k.push(["한화투자증권 P/B", `${num(me.pb, 2)}배`, `국내 증권사 중앙값 ${num(kr.median_pb, 2)}배`]);
    if (vn?.median_pb != null) k.push(["베트남 증권사 P/B 중앙값", `${num(vn.median_pb, 2)}배`, `ROE 중앙값 ${num(vn.median_roe, 1)}%`]);
    const g = C?.rows?.VNM?.gdp_growth, gi = C?.rows?.IDN?.gdp_growth, gk = C?.rows?.KOR?.gdp_growth;
    if (g?.v != null) k.push([`실질 성장률 ${g.y}(${g.src === "IMF" ? "IMF 전망" : "세계은행"})`, `${num(g.v, 1)}%<small>베트남</small>`, `인도네시아 ${num(gi?.v, 1)}% · 한국 ${num(gk?.v, 1)}%`]);
    $("#kpis").innerHTML = k.map(([a, b, c]) => `<div class="kpi"><span>${esc(a)}</span><b>${b}</b><em>${esc(c)}</em></div>`).join("");
  }

  async function init() {
    [C, L, X, G, T, VH, VB, V] = await Promise.all([getJSON("data/country.json"), getJSON("data/landscape.json"), getJSON("data/idx_share.json"), getJSON("../data/global/markets.json"),
      getJSON("../data/domestic/takeaways.json"), getJSON("data/vn_hose.json"), getJSON("data/vn_brokerage.json"), getJSON("data/valuation.json")]);
    const t = [L?.updated_at, C?.checked_at, X?.checked_at, V?.updated_at].filter(Boolean).sort().pop();
    $("#meta").textContent = t ? `자동 수집 ${new Date(t).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} KST · 공시·공개자료만 사용` : "자동 수집 전";
    renderTk(); renderKpis(); renderCountry(); renderLand(); renderIdx(); renderVn(); renderVal();
  }
  init();
})();
