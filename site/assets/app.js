/* 글로벌네트워크팀 Weekly Dashboard — 빌드 도구 없이 동작하는 정적 앱 */
(() => {
  "use strict";

  // 대상 회사·약칭·그룹은 data/config.json 에서 읽는다(init 참고)
  let HANWHA = "한화투자증권";
  let FIRM_ORDER = [];
  let SHORT = {};

  // per: 표마다 고른 공시 기간(드롭다운). 빈 값이면 기본(최신 공시) 화면
  const state = { data: null, filters: { firm: "", country: "", relation: "", q: "", off: false }, sort: null, per: {} };

  // ---------- 유틸 ----------
  const $ = (sel, el = document) => el.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n, d = 0) => (n == null || Number.isNaN(n) ? "–" : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: d, minimumFractionDigits: d }));
  const eok = (m) => (m == null ? "–" : fmt(m / 100, Math.abs(m) < 1000 ? 1 : 0)); // 백만원 → 억원
  const jo = (m) => (m == null ? "–" : fmt(m / 1e6, 2));                              // 백만원 → 조원
  const signCls = (n) => (n == null ? "" : n < 0 ? "neg" : "pos");
  // 이름 목록 + 은/는(마지막 글자 받침 기준, 한글이 아니면 '는')
  const topic = (names) => { const w = names.join("·"), c = w.charCodeAt(w.length - 1) - 0xac00; return `${w}${c >= 0 && c < 11172 && c % 28 ? "은" : "는"}`; };
  const ymd = (s) => (s && s.length === 8 ? `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6)}` : s || "");

  async function getJSON(path, optional = false) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${path} ${r.status}`);
      return await r.json();
    } catch (e) {
      if (optional) return null;
      throw e;
    }
  }

  // ---------- 데이터 병합 ----------
  // '2026 반기보고서' → '1H26'(손익) / '26.6말'(잔액), '2025 사업보고서' → 'FY2025' / '25.12말'
  function repShort(rep, balance = false) {
    if (!rep) return "";
    const y = rep.bsns_year, yy = String(y).slice(2);
    const m = { "11011": ["FY" + y, `${yy}.12말`], "11012": [`1H${yy}`, `${yy}.6말`], "11013": [`1Q${yy}`, `${yy}.3말`], "11014": [`3Q${yy}`, `${yy}.9말`] }[rep.reprt_code];
    return m ? m[balance ? 1 : 0] : rep.label;
  }

  function merge(seed, dart, subFin, cons) {
    const firms = seed.firms.map((f) => ({ ...f }));
    const entities = seed.entities.map((e) => ({ ...e }));
    const byName = new Map(entities.filter((e) => e.name).map((e) => [e.name, e]));
    const changes = [];
    const excluded = [];
    if (dart && dart.firms) {
      for (const [firmName, d] of Object.entries(dart.firms)) {
        const f = firms.find((x) => x.firm === firmName);
        // 재무는 전 사를 같은 시점으로: 자산·부채·자본은 최신 정기보고서, 손익은 최근 사업보고서(연간) + 최신 누적 순이익
        if (f) {
          const fin = d.financials, ann = d.financials_annual;
          for (const k of ["assets", "liabilities", "equity", "op_income", "net_income"]) f[k] = null;
          if (fin) {
            ["assets", "liabilities", "equity"].forEach((k) => (f[k] = fin[k] ?? null));
            f.bs_basis = repShort(d.financials_report, true);
            f.basis = `${d.financials_report.label}(${fin.fs_div})`;
            f.latest = true;
          } else {
            f.basis = "DART 정기보고서 없음";
          }
          const pl = ann || fin, plRep = ann ? d.financials_annual_report : d.financials_report;
          if (pl) {
            f.op_income = pl.op_income ?? null;
            f.net_income = pl.net_income ?? null;
            f.pl_basis = repShort(plRep);
          }
          // 가장 최근 정기보고서의 누적 순이익과, 같은 보고서로 낸 ROE(누적 순이익 연환산 ÷ 기말 자본, 연결)
          if (fin) {
            const months = { "11013": 3, "11012": 6, "11014": 9, "11011": 12 }[d.financials_report.reprt_code] || 12;
            f.ni_latest = fin.net_income ?? null;
            f.ni_basis = repShort(d.financials_report);
            f.roe_basis = months === 12 ? f.ni_basis : `${f.ni_basis} 연환산`;
            if (fin.net_income != null && fin.equity > 0) f.roe = ((fin.net_income * 12) / months / fin.equity) * 100;
          }
        }
        const candidates = new Set(d.new_candidates || []);
        for (const h of d.overseas_direct || []) {
          const e = h.seed_name && byName.get(h.seed_name);
          if (!e && !candidates.has(h.name)) continue; // 단순·일반투자 지분은 네트워크에서 제외
          if (e && e.latest && (e.latest.share ?? 0) >= (h.share_pct ?? 0)) continue; // 같은 법인에 여러 행이면 지분이 큰 행
          if (e) {
            e.latest = { share: h.share_pct, total_assets: h.total_assets, net_income: h.net_income, report: d.holdings_report?.label };
            e.first_acquired = h.first_acquired;
            // 최신 사업보고서 타법인출자현황 값(자산총계·순이익)으로 바꾼다. 부채·자본·영업이익은 공시에 없어 비운다
            if (h.net_income != null || h.total_assets != null) {
              Object.assign(e, { assets: h.total_assets, net_income: h.net_income, liabilities: null, equity: null, op_income: null,
                basis: `${d.holdings_report?.label} 타법인출자현황`, fresh: true });
            }
          } else {
            // DART에 새로 나온 해외 출자: 금융업 법인은 바로 운영 법인으로 반영(update_dart.py 규칙), 나머지는 후보
            const auto = (d.new_entities || []).includes(h.name);
            const why = d.candidate_reasons?.[h.name];
            const ne = {
              firm: firmName, group: f?.group || "", name: h.name, parent: firmName, business: null,
              country: h.country_guess || "미상", established: h.first_acquired, entry_mode: null,
              note: auto ? `DART ${d.holdings_report?.label || ""} 타법인출자현황(경영참여 ${fmt(h.share_pct)}%)에서 확인해 자동 반영`
                : `DART ${d.holdings_report?.label || ""} 타법인출자현황에서 새로 확인 · ${why || "검토 필요"}`,
              relation: "종속(자회사)", status: auto ? "운영" : "신규 후보", auto, kind: "법인", basis: d.holdings_report?.label,
              assets: h.total_assets, net_income: h.net_income, fresh: true,
              latest: { share: h.share_pct, total_assets: h.total_assets, net_income: h.net_income, report: d.holdings_report?.label },
            };
            entities.push(ne);
            changes.push({ firm: firmName, name: h.name, type: auto ? "자동 반영" : "신규 후보", why });
          }
        }
        for (const x of d.excluded || []) excluded.push({ firm: firmName, ...x });
      }
    }
    // 해외 종속회사 전수 목록(사업보고서 연결대상 종속회사 현황·연결 주석 종속기업 현황, 손자회사 포함, 감사보고서만 내는 토스 포함).
    // 규칙: 금융업(증권·운용·자문·IT) 영업법인만 법인 수에 넣고, 중간지주는 표시만, 펀드·SPV·부동산·휴면·역외 투자기구는 뺀다
    for (const [firmName, c] of Object.entries(cons?.firms || {})) {
      const f = firms.find((x) => x.firm === firmName);
      const rep = String(c.report || "").replace(/^(\d{4}) (사업|감사)보고서$/, "FY$1 $2보고서");
      if (f) Object.assign(f, { list_basis: rep, holdings: 0 });
      // 이름 없는 원자료 행(토스 등)은 DART 목록으로 대신한다
      for (let i = entities.length - 1; i >= 0; i--) if (entities[i].firm === firmName && !entities[i].name) entities.splice(i, 1);
      const seen = new Set();
      for (const x of c.overseas || []) {
        const keep = x.class === "영업법인" || x.class === "지주회사";
        let e = (x.seed_name && entities.find((y) => y.firm === firmName && y.name === x.seed_name)) ||
          entities.find((y) => y.firm === firmName && y.country === x.country && keyName(y.name) === keyName(x.name));
        if (!e && !keep) continue;
        if (!e) {
          e = { firm: firmName, group: f?.group || "", name: x.name, parent: firmName, business: x.business, country: x.country,
            established: x.established, entry_mode: null, relation: "종속(자회사)", kind: "법인", status: "운영", auto: true,
            note: `DART ${rep} 종속회사 목록에서 확인해 자동 반영`, basis: rep, fresh: false };
          entities.push(e); // 손자회사 등 목록으로 새로 잡힌 법인(새로 생긴 법인은 위 타법인출자 비교가 '변동'으로 따로 잡는다)
        }
        seen.add(e);
        e.dart_name = x.name;
        e.in_list = true;
        if (!keep) {
          // 원자료에는 있으나 규칙상 네트워크가 아닌 법인(부동산·발행 SPV 등)
          Object.assign(e, { status: "제외", exclude_reason: x.why, note: `${e.note ? `${e.note} · ` : ""}${rep} 업종 '${x.business || "-"}' → 규칙상 제외(${x.why})` });
          // 업종을 DART 목록으로 확인했으니 '확인 필요' 후보에서 내린다
          for (let i = changes.length - 1; i >= 0; i--) if (changes[i].firm === firmName && changes[i].name === e.name) changes.splice(i, 1);
          continue;
        }
        e.holding = x.class === "지주회사";
        if (e.holding && f) f.holdings += 1;
        if (e.status === "신규 후보") e.status = "운영";
        if (!e.business && x.business) e.business = x.business;
      }
      // 종속회사였는데 목록에 없는 법인(매각·청산 등). 관계회사·지분투자는 이 목록 대상이 아니라 그대로 둔다
      for (const e of entities) {
        if (e.firm === firmName && e.relation === "종속(자회사)" && e.status === "운영" && !seen.has(e)) {
          Object.assign(e, { status: "제외", exclude_reason: "최근 보고서 종속회사 목록에 없음", note: `${e.note ? `${e.note} · ` : ""}${rep} 종속회사 목록에 없음` });
        }
      }
    }
    // 남은 법인(손자회사 등 직접 출자가 아닌 법인)은 사업보고서 주석 '종속기업 요약재무정보'의 같은 해 값으로 채운다.
    // 이 표에는 자산·부채·순이익이 모두 있어, 타법인출자현황(자산·순이익만)보다 먼저 쓴다
    for (const [firmName, sf] of Object.entries(subFin?.firms || {})) {
      const rep = (sf.report || "").replace(/(\d{4}) 사업보고서/, "$1 사업보고서");
      for (const [nm, x] of Object.entries(sf.subs || {})) {
        const e = (x.seed_name && entities.find((y) => y.firm === firmName && y.name === x.seed_name)) ||
          entities.find((y) => y.firm === firmName && y.name && keyName(y.name) === keyName(nm) && (!x.country || y.country === x.country));
        if (!e || x.ni == null) continue;
        Object.assign(e, { assets: x.assets ?? e.assets, liabilities: x.liab ?? null, equity: x.equity ?? null, net_income: x.ni,
          op_income: null, basis: `${rep} 종속기업 요약재무정보`, fresh: true });
      }
    }
    return { firms, entities, offices: seed.offices, changes, excluded, meta: seed.meta };
  }

  const counted = (e) => e.kind === "법인" && e.status === "운영" && e.relation !== "지분투자" && !e.holding;

  // fetch_consolidated.py key_name 과 같은 정규화(대소문자·띄어쓰기·법인 형태·각주 표시 무시)
  function keyName(name) {
    let n = String(name || "").toLowerCase().replace(/\s*(\(\*\d*\)|\(주\d*\)|㈜|\(구[,.]?[^)]*\))\s*/g, "").replace(/&/g, "and")
      .replace(/\((bsc|kisi|ptsv|ptss)\)/g, "").replace(/[^0-9a-z가-힣]+/g, "").replace(/^pt/, "");
    const suf = ["jointstockcompany", "privatelimited", "corporation", "company", "limited", "ltda", "ltd", "inc", "llc", "llp", "pte", "plc", "jsc", "corp", "co", "sa"];
    for (let changed = true; changed;) {
      changed = false;
      for (const x of suf) if (n.endsWith(x) && n.length > x.length + 4) { n = n.slice(0, -x.length); changed = true; }
    }
    return n;
  }

  // ---------- 라우팅 ----------
  function route() {
    const [section = "overview", sub = ""] = location.hash.replace(/^#/, "").split("/");
    const valid = ["overview", "global", "domestic", "hanwha", "insight", "digital", "guide", "workflow"].includes(section) ? section : "overview";
    document.querySelectorAll(".tabs a").forEach((a) => a.setAttribute("aria-selected", String(a.dataset.section === valid)));
    // 브라우저 탭 제목에 현재 화면 이름(북마크·탭 구분용)
    const tabName = document.querySelector(`.tabs a[data-section="${valid}"]`)?.textContent.trim();
    document.title = `${tabName ? `${tabName} · ` : ""}글로벌네트워크팀 Weekly Dashboard`;
    document.querySelectorAll(".section").forEach((s) => (s.hidden = s.id !== `section-${valid}`));
    if (valid === "overview") renderOverview();
    if (valid === "global") renderGlobal(sub || "all");
    if (valid === "domestic") renderDomestic(sub);
    if (valid === "hanwha") renderFrame("hanwha");
    if (valid === "insight") renderFrame("insight");
    if (valid === "digital") renderFrame("digital");
    if (valid === "guide") renderFrame("guide");
    if (valid === "workflow") renderFrame("workflow");
    try { localStorage.setItem("gnd:last", location.hash); } catch (_) { /* 저장 불가 환경 */ }
  }

  // 표 오른쪽 위 작은 표기: 기준 시점 · 단위(모든 표 공통)
  const tmeta = (basis, unit) => basis || unit
    ? `<div class="tmeta">${basis ? `<span>기준 ${esc(basis)}</span>` : ""}${unit ? `<span>단위: ${esc(unit)}</span>` : ""}</div>` : "";

  // 기간 선택 드롭다운: 표 오른쪽 위 '기준' 자리에 둔다. 고르면 그 표만 전 사 같은 보고서 값으로 다시 그린다
  const perSel = (id, opts, title) => `<select class="psel" data-per="${id}" title="${esc(title || "공시 기간 선택")}" aria-label="${esc(title || "공시 기간 선택")}">${opts.map((o) =>
    `<option value="${esc(o.v)}"${(state.per[id] || "") === o.v ? " selected" : ""}>${esc(o.l)}</option>`).join("")}</select>`;
  const tmetaSel = (sel, note, unit) => `<div class="tmeta"><span>기준 ${sel}${note ? ` ${esc(note)}` : ""}</span>${unit ? `<span>단위: ${esc(unit)}</span>` : ""}</div>`;

  // 국내 증권사 재무: 기간을 고르면 fin_hist.json(정기보고서 주요계정, 연결 우선)의 그 보고서 값으로 바꾼다
  function finPeriod() {
    const h = state.data.finHist, key = state.per.fin;
    return key ? (h?.periods || []).find((p) => p.key === key) || null : null;
  }
  function finFirms() {
    const P = finPeriod();
    if (!P) return state.data.domestic.firms;
    return state.data.domestic.firms.map((f) => {
      const x = state.data.finHist.firms?.[f.firm]?.[P.key];
      const pl = P.months === 12 ? P.label : `${P.label} 누적`;
      return { ...f, assets: x?.assets ?? null, liabilities: x?.liabilities ?? null, equity: x?.equity ?? null, op_income: x?.op_income ?? null,
        net_income: x?.net_income ?? null, ni_latest: x?.net_income ?? null, latest: !!x,
        roe: x?.net_income != null && x?.equity > 0 ? ((x.net_income * 12) / P.months / x.equity) * 100 : null,
        bs_basis: P.bs, pl_basis: pl, ni_basis: pl, roe_basis: P.months === 12 ? P.label : `${P.label} 연환산`,
        basis: x ? `${P.label} 보고서(${x.fs_div})` : `${P.label} 보고서 미제출` };
    });
  }
  function finOpts() {
    const h = state.data.finHist, total = Object.keys(h?.firms || {}).length;
    return [{ v: "", l: "최신 공시" }, ...(h?.periods || []).map((p) => ({ v: p.key, l: `${p.label}${p.n < total ? ` (${p.n}/${total}사 제출)` : ""}` }))];
  }

  // 네트워크 집계 기준(종속회사 목록 보고서)과 재무 잔액 기준 시점
  const netBasis = () => [...new Set(state.data.domestic.firms.map((f) => f.list_basis).filter(Boolean).map((b) => b.slice(0, 6)))].map((b) => `${b} 사업보고서`).join("·") || "공시";
  const bsBasis = () => [...new Set(state.data.domestic.firms.map((f) => f.bs_basis).filter(Boolean))].join("·");
  // 국내 전체 증권사 자기자본(별도) 순위: broker_rank.py 가 매주 DART 주요계정으로 만든다(정기보고서 제출사)
  function brokerRank(key = "") {
    const b = (key && (state.data.brokerHist?.periods || []).find((p) => `${p.bsns_year}-${p.reprt_code}` === key)) || state.data.brokerRank;
    const rows = (b?.rows || []).filter((r) => r.equity_ofs != null).sort((x, y) => y.equity_ofs - x.equity_ofs);
    const rank = rows.findIndex((r) => r.name === HANWHA) + 1;
    if (!rank) return null;
    const by = (k) => [...rows].filter((r) => r[k] != null).sort((x, y) => y[k] - x[k]);
    const cfs = by("equity_cfs").findIndex((r) => r.name === HANWHA) + 1;
    return { b, rows, rank, cfs, short: b.period.replace("보고서", ""), basis: `${b.as_of} · ${b.period} 별도` };
  }

  // ---------- 글로벌 ----------
  function rankTable(rows, { unit, digits = 1, hw = () => false, limit = 0, mini = false, basis = "" }) {
    const max = Math.max(...rows.map((r) => Math.abs(r.value ?? 0)), 1);
    const shown = limit ? rows.slice(0, limit) : rows;
    return `${tmeta(basis, unit)}<table class="rank${mini ? " rank--mini" : ""}"><tbody>${shown.map((r, i) => {
      const cls = hw(r) ? "is-hanwha" : r.korean ? "is-kr" : "";
      const tag = hw(r) ? '<span class="tag tag--hw">당사</span>' : r.korean ? `<span class="tag tag--kr">${mini ? "" : "한국계 · "}${esc(SHORT[r.korean] || r.korean)}</span>` : "";
      return `<tr class="${cls}"><td class="rank__no">${r.value == null ? "–" : i + 1}</td>
        <td class="rank__name">${esc(r.name)}${tag}${r.note ? `<span class="rank__note">${esc(r.note)}</span>` : ""}</td>
        <td class="rank__bar"><div class="bar"><span style="width:${r.value == null ? 0 : Math.max(2, (Math.abs(r.value) / max) * 100)}%"></span></div></td>
        <td class="rank__val">${r.value == null ? "수집 대기" : fmt(r.value, digits)} <span class="sub">${r.value == null || mini ? "" : esc(unit)}</span></td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function koreanPresence(country) {
    const list = state.data.domestic.entities.filter((e) => e.country === country && counted(e));
    if (!list.length) return '<p class="sub">공시상 국내 증권사의 현지 법인은 없습니다.</p>';
    const byFirm = {};
    list.forEach((e) => (byFirm[e.firm] = byFirm[e.firm] || []).push(e));
    return `<div class="chips">${FIRM_ORDER.filter((f) => byFirm[f]).map((f) =>
      `<span class="chip"${f === HANWHA ? ' style="background:var(--accent-soft)"' : ""}><b>${esc(SHORT[f])}</b> ${byFirm[f].length}</span>`).join("")}</div>
      <ul class="list">${list.slice(0, 12).map((e) => `<li>${esc(e.name || "(법인명 원자료 미기재)")} <span class="sub">${esc(SHORT[e.firm] || e.firm)}</span></li>`).join("")}</ul>
      ${list.length > 12 ? `<p class="sub">외 ${list.length - 12}개 · <a href="#domestic/detail" data-country="${esc(country)}" class="jump">전체 보기</a></p>` : `<p class="sub"><a href="#domestic/detail" data-country="${esc(country)}" class="jump">국내 › 해외법인 상세에서 보기</a></p>`}`;
  }

  function outboundRank(opts = {}) {
    const ents = state.data.domestic.entities.filter(counted);
    const rows = FIRM_ORDER.map((f) => {
      const mine = ents.filter((e) => e.firm === f);
      return { name: f, value: mine.length, note: `${new Set(mine.map((e) => e.country)).size}개국` };
    }).filter((r) => r.value).sort((a, b) => b.value - a.value);
    return rankTable(rows.map((r) => (opts.mini ? { ...r, name: SHORT[r.name] || r.name } : r)),
      { unit: "개", digits: 0, basis: netBasis(), hw: (r) => r.name === HANWHA || r.name === SHORT[HANWHA], ...opts });
  }

  // 해외 상장 증권사 자동 순위(listed.json: Yahoo Finance·stockanalysis, 매주 자동 수집)
  function listedOf(id) {
    const x = state.data.listed?.markets?.[id];
    return x && x.rows?.length ? x : null;
  }
  function listedRows(x) {
    return x.rows.map((r) => ({ name: r.name, value: r.equity,
      note: [r.ni != null ? `순이익 ${fmt(r.ni, 1)}` : "", r.asof ? `${String(r.asof).slice(0, 7)} 기준` : "", r.stale ? "이전 값(수집 실패)" : ""].filter(Boolean).join(" · ") }));
  }
  const MANUAL_WHY = { ad: "수동 관리: 아부다비(ADX·ADGM)에는 상장 증권사가 없고 회원사 순위도 공표되지 않아 자동 수집할 원천이 없습니다." };

  // 시장 하나를 순위 행으로 요약(한눈에 보기·글로벌 전체 보기 공용)
  function marketSummary(m) {
    if (m.auto === "dart") {
      const firms = [...state.data.domestic.firms].filter((f) => f.equity != null).sort((a, b) => b.equity - a.equity);
      return { title: "자기자본 (조원)", rows: firms.map((f) => ({ name: SHORT[f.firm] || f.firm, value: f.equity / 1e6 })), unit: "조원", digits: 2, basis: bsBasis(),
        meta: `DART ${[...new Set(firms.map((f) => f.basis))][0] || ""}`, hw: (r) => r.name === SHORT[HANWHA] };
    }
    if (m.auto === "sec") {
      const rows = (state.data.us?.rows || []).filter((r) => r.equity).map((r) => ({ name: r.name, value: r.equity.value / 1e9 }))
        .sort((a, b) => b.value - a.value);
      return { title: "자본총계 ($B)", rows, unit: "십억달러", digits: 1, basis: "각 사 최근 공시", meta: state.data.us ? `SEC EDGAR · ${state.data.us.updated_at.slice(0, 10)}` : "SEC 수집 전" };
    }
    const lx = listedOf(m.id);
    if (lx) {
      return { title: `상장 증권사 자기자본 (${lx.unit})`, rows: listedRows(lx), unit: lx.unit, digits: 1, basis: "각 사 최근 연간 공시",
        meta: `자동 수집 ${state.data.listed.updated_at.slice(0, 10)} · 각 사 최근 연간 공시` };
    }
    if (m.tables?.length) {
      const t = m.tables[0];
      return { title: t.title, rows: t.rows, unit: t.unit, digits: t.unit === "%" ? 2 : 1, meta: t.basis, basis: t.basis };
    }
    return null;
  }

  function koreanChips(country) {
    const list = state.data.domestic.entities.filter((e) => e.country === country && counted(e));
    if (!list.length) return '<p class="sub">없음</p>';
    const byFirm = {};
    list.forEach((e) => (byFirm[e.firm] = (byFirm[e.firm] || 0) + 1));
    return `<div class="chips">${FIRM_ORDER.filter((f) => byFirm[f]).map((f) =>
      `<span class="chip"${f === HANWHA ? ' style="background:var(--accent-soft)"' : ""}><b>${esc(SHORT[f])}</b> ${byFirm[f]}</span>`).join("")}</div>`;
  }

  function marketCard(m, limit = 5) {
    const sum = marketSummary(m);
    let body = "";
    if (sum && sum.rows.length) body = `<p class="card__meta">${esc(sum.title)} · ${esc(sum.meta || "")}</p>${rankTable(sum.rows, { ...sum, limit, mini: true })}`;
    else if (sum) body = `<p class="card__meta">${esc(sum.meta || "")}</p><div class="empty-state">다음 자동 수집 때 채워집니다.</div>`;
    else if (m.players) body = `<p class="card__meta">${esc(m.players_title || "주요 플레이어")}</p><ul class="list">${m.players.slice(0, limit).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
    if (m.news?.length) body += `<ul class="list">${m.news.slice(0, 2).map((n) => `<li><span class="sub">${esc(n.date)}</span> <a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.text)}</a></li>`).join("")}</ul>`;
    const chips = m.auto === "dart" ? "" : `<p class="card__meta" style="margin-top:8px">국내 증권사 현지법인</p>${koreanChips(m.country)}`;
    return `<div class="card mkt"><h3><a href="#global/${esc(m.id)}"><span aria-hidden="true">${m.flag}</span> ${esc(m.label)}</a></h3>${body}${chips}</div>`;
  }

  function renderGlobal(id) {
    const { markets } = state.data.markets;
    const m = id === "all" ? null : markets.find((x) => x.id === id) || markets[0];
    $("#market-pills").innerHTML = `<a class="pill" role="tab" href="#global/all" aria-selected="${!m}">전체</a>` + markets.map((x) =>
      `<a class="pill" role="tab" href="#global/${x.id}" aria-selected="${x.id === m?.id}"><span aria-hidden="true">${x.flag}</span>${esc(x.label)}</a>`).join("");
    if (!m) {
      $("#market-view").innerHTML = `<p class="lead">7개 시장의 상위 증권사를 한 화면에 모았습니다. 시장 이름을 누르면 전체 순위와 출처를 볼 수 있습니다.</p>
        <div class="mkts mkts--4">${markets.map((x) => marketCard(x, 10)).join("")}</div>`;
      return;
    }

    let main = "";
    if (m.auto === "dart") {
      const firms = [...finFirms()].sort((a, b) => (b.equity ?? -1) - (a.equity ?? -1));
      const bases = [...new Set(firms.filter((f) => f.equity != null).map((f) => f.basis))];
      const P = finPeriod();
      // 기간 드롭다운은 rankTable의 기준 줄을 대신한다(같은 표 안은 전 사 같은 보고서)
      const finMeta = state.data.finHist?.periods?.length ? tmetaSel(perSel("fin", finOpts()), P ? `· 자본 ${P.bs}` : `· 자본 ${bsBasis()}`, "조원") : "";
      main = `<div class="card"><h3>자기자본 순위 (조원)</h3><p class="card__meta">${esc(bases.join(" · "))} · 출처 DART</p>
        ${finMeta}${rankTable(firms.map((f) => ({ name: f.firm, value: f.equity == null ? null : f.equity / 1e6,
          note: f.net_income == null ? (P ? `${P.label} 보고서 없음` : "") : `자본 ${f.bs_basis || f.basis} · 순이익 ${eok(f.net_income)}억(${f.pl_basis || ""}) · 해외법인 ${state.data.domestic.entities.filter((e) => e.firm === f.firm && counted(e)).length}개` })),
          { unit: finMeta ? "" : "조원", digits: 2, basis: finMeta ? "" : bsBasis(), hw: (r) => r.name === HANWHA })}</div>`;
      const br = brokerRank(state.per.rank);
      if (br) {
        const jo = (v) => (v == null ? "–" : `${fmt(v / 1e6, 2)}조`);
        const hist = state.data.brokerHist?.periods || [];
        const rankMeta = hist.length > 1 ? tmetaSel(perSel("rank", [{ v: "", l: `최신 (${state.data.brokerRank.period.replace("보고서", "")})` },
          ...hist.filter((p) => p.as_of !== state.data.brokerRank.as_of).map((p) => ({ v: `${p.bsns_year}-${p.reprt_code}`, l: `${p.as_of.slice(0, 7).replace("-", ".")} ${p.period.replace(/^\d{4} /, "").replace("보고서", "")}` }))]),
          `· ${br.b.as_of} 별도`, "조원") : "";
        main += `<div class="card"><h3>국내 전체 증권사 자기자본 순위 (조원)</h3><p class="card__meta">DART ${esc(br.b.period)}를 낸 증권사 ${br.rows.length}곳 · 별도 자본총계 · 당사 ${br.rank}위(연결 ${br.cfs}위) · 매주 월요일 자동 계산 · 정기보고서가 없는 회사·외국계 지점은 빠짐${state.per.rank ? " · 지난 기간은 최신 순위에 든 회사 기준" : ""}</p>
          ${rankMeta}${rankTable(br.rows.map((r) => ({ name: r.name, value: r.equity_ofs / 1e6, note: `연결 ${jo(r.equity_cfs)} · 자본금 ${jo(r.capital_ofs ?? r.capital_cfs)}` })),
            { unit: rankMeta ? "" : "조원", digits: 2, basis: rankMeta ? "" : br.basis, hw: (r) => r.name === HANWHA })}</div>`;
      }
    } else if (m.auto === "sec") {
      const us = state.data.us;
      const rows = (us?.rows || []).map((r) => ({
        name: r.name, value: r.equity ? r.equity.value / 1e9 : null,
        note: [r.model, r.net_income_fy ? `FY 순이익 $${fmt(r.net_income_fy.value / 1e9, 1)}B` : "", r.equity ? `${r.equity.end} 기준` : ""].filter(Boolean).join(" · "),
      }));
      const okCount = rows.filter((r) => r.value != null).length;
      const warn = us && okCount < rows.length
        ? `<div class="empty-state" style="margin-bottom:10px">${rows.length - okCount}개사 수집 실패로 ‘수집 대기’로 표시합니다. 다음 주간 수집 때 다시 시도합니다.${us.errors?.length ? `<br><span class="sub">사유: ${esc(String(us.errors[0]).slice(0, 80))}</span>` : ""}</div>` : "";
      main = `<div class="card"><h3>자본총계 순위 (십억달러)</h3><p class="card__meta">${us ? `SEC EDGAR · 수집 시도 ${esc(us.updated_at.slice(0, 10))} · 성공 ${okCount}/${rows.length}` : "SEC 수집 전"}</p>
        ${warn}${rows.length ? rankTable(rows, { unit: "십억달러", digits: 1, basis: "각 사 최근 공시" }) : '<div class="empty-state">아직 수집된 데이터가 없습니다. 다음 자동 수집 때 채워집니다.</div>'}</div>`;
    } else {
      const lx = listedOf(m.id);
      if (lx) {
        const L = state.data.listed;
        const stale = lx.rows.filter((r) => r.stale).length;
        main = `<div class="card"><h3>상장 증권사 자기자본 순위 (${esc(lx.unit)})</h3>
          <p class="card__meta">자동 수집 ${esc(L.updated_at.slice(0, 10))}(매주 월) · 각 사 최근 연간 공시 · 출처 Yahoo Finance·stockanalysis(회사명 옆 링크)${stale ? ` · ${stale}개사는 수집 실패로 이전 값` : ""}</p>
          ${rankTable(listedRows(lx), { unit: lx.unit, digits: 1, basis: "각 사 최근 연간 공시" })}
          <p class="src">${lx.rows.map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.ticker)}</a>`).join(" · ")}</p></div>`;
      }
    }
    if (MANUAL_WHY[m.id]) main = `<div class="empty-state" style="margin-bottom:10px">${esc(MANUAL_WHY[m.id])}</div>` + main;
    if (m.tables) {
      main += m.tables.map((t) => `<div class="card"><h3>${esc(t.title)} <span class="tag tag--muted">수동·참고</span></h3><p class="card__meta">${esc(t.basis)} · 출처 <a href="${esc(t.source.url)}" target="_blank" rel="noopener">${esc(t.source.label)}</a></p>
        ${rankTable(t.rows, { unit: t.unit, digits: t.unit === "%" ? 2 : 1, basis: t.basis })}</div>`).join("");
    }
    if (m.players) {
      main += `<div class="card"><h3>${esc(m.players_title || "주요 플레이어")}</h3><ul class="list">${m.players.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
        ${m.source ? `<p class="src">출처 <a href="${esc(m.source.url)}" target="_blank" rel="noopener">${esc(m.source.label)}</a></p>` : ""}</div>`;
    }
    if (m.news) {
      main += `<div class="card"><h3>한국계 동향</h3><ul class="feed">${m.news.map((n) =>
        `<li><span class="d">${esc(n.date)}</span><span></span><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.text)}</a></li>`).join("")}</ul></div>`;
    }
    const aside = m.auto === "dart"
      ? `<aside class="card"><h3>증권사별 해외 현지법인 수</h3><p class="card__meta">종속회사 목록의 금융업 영업법인(손자회사 포함) · <a href="#domestic/matrix">국가별 보기</a></p>${outboundRank()}</aside>`
      : `<aside class="card"><h3>국내 증권사 현지 법인</h3><p class="card__meta">${esc(m.country)} · ${esc(netBasis())} 종속회사 목록 기준</p>${koreanPresence(m.country)}</aside>`;
    $("#market-view").innerHTML = `<p class="lead">${esc(m.headline)}</p><div class="grid2"><div>${main}</div>${aside}</div>`;
  }

  // ---------- 국내 ----------
  function renderKpis() {
    const d = state.data.domestic;
    const corps = d.entities.filter(counted);
    const offices = d.offices.reduce((s, o) => s + o.count, 0);
    const countries = new Set([...corps.map((e) => e.country), ...d.offices.map((o) => o.country)]);
    const firmsWith = new Set(corps.map((e) => e.firm));
    const top = Object.entries(corps.reduce((m, e) => ((m[e.country] = (m[e.country] || 0) + 1), m), {})).sort((a, b) => b[1] - a[1])[0];
    $("#kpis").innerHTML = [
      ["해외 현지법인", corps.length, `${firmsWith.size}개 증권사 · FY2025 종속회사 목록 자동 집계`],
      ["해외 사무소", offices, "회사 공개 자료 · 수동 확인"],
      ["진출 국가", countries.size, `최다 ${top ? `${top[0]} ${top[1]}개` : "–"}`],
      ["변동 감지", d.changes.length, d.changes.length ? changeNote(d.changes) : "최근 수집 기준 변동 없음"],
    ].map(([l, v, n]) => `<div class="kpi"><div class="kpi__label"><abbr title="${esc(TIPS[l] || "")}">${l}</abbr></div><div class="kpi__value">${fmt(v)}</div><div class="kpi__note">${esc(n)}</div></div>`).join("");
  }

  const TIPS = {
    "해외 현지법인": "각 사 FY2025 사업보고서(토스는 연결감사보고서) 연결 종속회사 목록에서 금융업(증권·운용·자문·IT) 영업법인을 손자회사까지 자동으로 셉니다. 중간지주·펀드·신탁·SPV·부동산·휴면·역외 투자기구와 단순 지분투자는 뺍니다. 관계회사(하나 BSC)는 넣습니다.",
    "해외 사무소": "영업을 하지 않는 연락·조사 사무소(법인 아님).",
    "진출 국가": "현지법인 또는 사무소가 하나 이상 있는 국가 수.",
    "변동 감지": "DART 최신 정기보고서 타법인출자현황에 새로 나온 경영참여 해외 출자 수. 금융업 법인(증권·투자·자산운용·지주 등)은 자동으로 현지법인 수·진출 현황 표·지도·해외법인 상세에 반영하고, 소재국이나 업종을 알 수 없는 출자는 확인 필요 후보로 남깁니다. 뉴스에만 나온 진출 소식은 '보도' 표시만 하고 세지 않습니다.",
  };

  function heat(n, max) {
    if (!n) return 0;
    return Math.min(4, Math.max(1, Math.ceil((n / max) * 4)));
  }

  // 국가 × 증권사: 현지법인 표와 사무소 표를 따로, 같은 열 구성으로 위아래에 둔다
  function renderMatrix(el, opts = {}) {
    const d = state.data.domestic;
    const firms = FIRM_ORDER.filter((f) => d.firms.some((x) => x.firm === f));
    const corp = {}, off = {};
    const add = (m, c, f, n) => { m[c] = m[c] || {}; m[c][f] = (m[c][f] || 0) + n; };
    d.entities.filter(counted).forEach((e) => add(corp, e.country, e.firm, 1));
    d.offices.forEach((o) => add(off, o.country, o.firm, o.count));
    const get = (m, c, f) => m[c]?.[f] || 0;
    const groups = [["비은행계", firms.filter((f) => d.firms.find((x) => x.firm === f)?.group === "비은행계" && f !== HANWHA)],
      ["은행계", firms.filter((f) => d.firms.find((x) => x.firm === f)?.group === "은행계")], ["당사", firms.filter((f) => f === HANWHA)]];
    const cols = groups.flatMap((g) => g[1]);
    const sum = (xs) => xs.reduce((s, n) => s + n, 0);
    const countriesOf = (m) => Object.keys(m).sort((a, b) => sum(Object.values(m[b])) - sum(Object.values(m[a])) || a.localeCompare(b, "ko"));

    // link: 칸을 누르면 상세 표로(현지법인만). unit: 툴팁 단위
    const table = (m, countries, { link, unit, label }) => {
      const max = Math.max(1, ...countries.flatMap((c) => cols.map((f) => get(m, c, f))));
      const colSum = (f) => sum(countries.map((c) => get(m, c, f)));
      return `<div class="scroll"><table class="matrix${opts.mini ? " matrix--mini" : ""}">
        <thead>${opts.mini ? "" : `<tr><th></th>${groups.filter((g) => g[1].length).map(([g, fs]) => `<th class="grp" colspan="${fs.length}">${g}</th>`).join("")}<th></th></tr>`}
        <tr><th style="text-align:left">${label}</th>${cols.map((f) => `<th class="${f === HANWHA ? "hw" : ""}">${esc(SHORT[f])}</th>`).join("")}<th>계</th></tr></thead>
        <tbody>${countries.map((c) => `<tr data-c="${esc(c)}"><th>${esc(c)}</th>${cols.map((f) => {
            const n = get(m, c, f);
            if (!n) return '<td class="empty">0</td>';
            const attrs = link ? ` tabindex="0" data-firm="${esc(f)}" data-country="${esc(c)}"` : ' class="nolink"';
            return `<td${attrs} data-h="${heat(n, max)}" title="${esc(SHORT[f])} · ${esc(c)} ${unit} ${n}">${n}</td>`;
          }).join("")}<td class="total">${sum(cols.map((f) => get(m, c, f)))}</td></tr>`).join("")}
        <tr class="total"><th>합계</th>${cols.map((f) => `<td>${colSum(f) || ""}</td>`).join("")}<td>${sum(cols.map(colSum))}</td></tr></tbody>
      </table></div>`;
    };
    const allCorp = countriesOf(corp);
    const corpCountries = opts.limit ? allCorp.slice(0, opts.limit) : allCorp;
    const offCountries = countriesOf(off);
    const offTotal = sum(offCountries.flatMap((c) => Object.values(off[c])));
    const corpTotal = sum(allCorp.flatMap((c) => Object.values(corp[c])));
    const head = (t, n, u) => `<h4 class="mx__h">${t} <span>${n}${u}</span></h4>${tmeta(t === "사무소" ? "회사 공개 자료(수동)" : netBasis(), u)}`;
    const corpTable = table(corp, corpCountries, { link: true, unit: "현지법인", label: opts.mini ? "" : "국가" });
    const offTable = table(off, offCountries, { link: false, unit: "사무소", label: opts.mini ? "" : "국가" });
    const legend = `<span class="legend">적음 <i style="background:var(--heat-1)"></i><i style="background:var(--heat-2)"></i><i style="background:var(--heat-3)"></i><i style="background:var(--heat-4)"></i> 많음</span>`;
    if (opts.mini) {
      el.innerHTML = head("현지법인", corpTotal, "개") + corpTable +
        (allCorp.length > corpCountries.length ? `<p class="src">상위 ${corpCountries.length}개국 · 전체 ${allCorp.length}개국은 국내 탭에서</p>` : "") +
        head("사무소", offTotal, "곳") + offTable;
      bindMatrixCells(el);
      return;
    }

    el.innerHTML = `<div class="card">
      <div class="toolbar">${legend}<span class="sub" style="margin-left:auto">칸을 누르면 해당 법인 목록으로 이동합니다</span></div>
      ${head("현지법인", corpTotal, "개")}${corpTable}
      ${head("사무소", offTotal, "곳")}${offTable}
      <p class="src">현지법인: 각 사 FY2025 사업보고서(토스는 연결감사보고서) 연결 종속회사 목록의 금융업 영업법인(손자회사 포함, 매주 자동), 중간지주·펀드·SPV·부동산·휴면·역외 투자기구·단순 지분투자 제외, 관계회사 포함. 사무소: 지분이 없어 DART에 나오지 않아 <b>수동 관리</b>, 원자료에 회사 공개 자료 정정 반영${
        state.data.officesUpdate ? ` + 이후 확인·정정 ${state.data.officesUpdate.items.length}건(${state.data.officesUpdate.items.map((x) => `${esc(SHORT[x.firm])} ${esc(x.city)}, ${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.source)}</a>` : esc(x.source)}`).join(" · ")}). 참고로 금감원 집계 증권업계 해외 사무소는 ${state.data.officesUpdate.industry.offices}곳입니다(<a href="${esc(state.data.officesUpdate.industry.url)}" target="_blank" rel="noopener">${esc(state.data.officesUpdate.industry.label)}</a>, 2025년 말)` : ""}. ${
        d.meta.corrections.length ? `원자료 보정 ${d.meta.corrections.length}건: ${d.meta.corrections.map((c) => `${esc(c.name)} ${esc(c.from)}→${esc(c.to)}`).join(", ")}.` : ""}</p>
    </div>`;
    bindMatrixCells(el);
  }

  function bindMatrixCells(el) {
    const go = (td) => {
      Object.assign(state.filters, { firm: td.dataset.firm, country: td.dataset.country, relation: "", q: "" });
      if (location.hash === "#domestic/detail") route(); else location.hash = "#domestic/detail";
    };
    el.querySelectorAll("td[data-firm]").forEach((td) => {
      td.addEventListener("click", () => go(td));
      td.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(td); } });
    });
  }

  const COLS = [
    ["firm", "증권사"], ["name", "법인명"], ["country", "국가"], ["business", "업종"], ["entry_mode", "진출방식"],
    ["established", "설립·취득"], ["assets", "총자산(억원)", true], ["net_income", "순이익(억원)", true], ["basis", "기준"], ["note", "비고"],
  ];

  function filtered() {
    const f = state.filters;
    const q = f.q.trim().toLowerCase();
    let rows = state.data.domestic.entities.filter((e) =>
      (f.off || e.status === "운영" || e.status === "신규 후보") &&
      (!f.firm || e.firm === f.firm) && (!f.country || e.country === f.country) &&
      (!f.relation || e.relation === f.relation) &&
      (!q || [e.name, e.parent, e.business, e.note, e.firm].some((v) => String(v || "").toLowerCase().includes(q))));
    if (state.sort) {
      const [k, dir] = state.sort;
      rows = [...rows].sort((a, b) => {
        const x = a[k], y = b[k];
        if (x == null) return 1;
        if (y == null) return -1;
        return (typeof x === "number" ? x - y : String(x).localeCompare(String(y), "ko")) * dir;
      });
    } else {
      rows = [...rows].sort((a, b) => FIRM_ORDER.indexOf(a.firm) - FIRM_ORDER.indexOf(b.firm) || String(a.country).localeCompare(String(b.country), "ko"));
    }
    return rows;
  }

  const basisShort = (b) => String(b || "").replace(" 타법인출자현황", "").replace(" 종속기업 요약재무정보", "").replace(/^(\d{4}) 사업보고서$/, "FY$1").replace(/^FY(\d{4}) 사업보고서.*$/, "FY$1");

  function renderDetail(el) {
    const d = state.data.domestic;
    const f = state.filters;
    const opts = (vals, cur, all) => `<option value="">${all}</option>${vals.map((v) => `<option ${v === cur ? "selected" : ""}>${esc(v)}</option>`).join("")}`;
    const countries = [...new Set(d.entities.map((e) => e.country))].sort((a, b) => a.localeCompare(b, "ko"));
    const relations = [...new Set(d.entities.map((e) => e.relation))];
    el.innerHTML = `<div class="card">
      <div class="filters">
        <select id="f-firm" aria-label="증권사">${opts(FIRM_ORDER.filter((x) => d.firms.some((y) => y.firm === x)), f.firm, "전체 증권사")}</select>
        <select id="f-country" aria-label="국가">${opts(countries, f.country, "전체 국가")}</select>
        <select id="f-rel" aria-label="관계">${opts(relations, f.relation, "전체 관계")}</select>
        <input id="f-q" type="search" placeholder="법인명·업종·비고 검색" value="${esc(f.q)}" aria-label="검색">
        <label class="sub" style="display:flex;align-items:center;gap:4px"><input id="f-off" type="checkbox" ${f.off ? "checked" : ""}> 매각·제외 포함</label>
        <button class="btn" id="f-reset" type="button">초기화</button>
        <button class="btn btn--accent" id="f-csv" type="button">CSV 다운로드</button>
      </div>
      <div style="display:flex;align-items:baseline;gap:8px"><p class="count" id="f-count"></p><div style="margin-left:auto">${tmeta("행마다 ‘기준’ 칸", "억원(총자산·순이익)")}</div></div>
      <div class="scroll tall" style="max-height:72vh"><table class="data"><thead><tr>${COLS.map(([k, l, n]) => `<th class="${n ? "num" : ""}" data-k="${k}">${l}${state.sort && state.sort[0] === k ? (state.sort[1] > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
      <tbody id="f-body"></tbody></table></div>
      <p class="src">총자산·순이익은 각 사 ${esc(pnlBasis())} 사업보고서 연결 주석 '종속기업 요약재무정보'(손자회사 포함)와 타법인출자현황 값(법인 전체 100%, 억원)으로 매주 자동 갱신합니다. 두 공시에 모두 없는 법인(지분법 관계회사 등)만 원자료 값을 두고 기준 칸에 <span class="stale">주황색</span>으로 표시합니다.</p>
    </div>`;
    const draw = () => {
      const rows = filtered();
      $("#f-count", el).textContent = `${rows.length}개 법인`;
      $("#f-body", el).innerHTML = rows.map((e) => {
        const tags = [
          e.firm === HANWHA ? '<span class="tag tag--hw">당사</span>' : "",
          e.relation !== "종속(자회사)" ? `<span class="tag tag--muted">${esc(e.relation)}</span>` : "",
          e.status === "신규 후보" ? '<span class="tag tag--new">신규 후보</span>' : "",
          e.status === "매각" ? '<span class="tag tag--muted">매각</span>' : "",
          e.status === "제외" ? `<span class="tag tag--muted" title="${esc(e.exclude_reason || "")}">제외</span>` : "",
          e.holding ? '<span class="tag tag--muted" title="중간지주회사: 법인 수에서 제외">중간지주</span>' : "",
          e.event ? `<span class="tag tag--new" title="${esc(e.event.text)}">${esc(e.event.tag)}</span>` : "",
        ].join("");
        const latest = e.latest ? `<div class="sub">지분 ${fmt(e.latest.share, 1)}%</div>` : "";
        return `<tr class="${e.firm === HANWHA ? "is-hanwha" : ""} ${e.status === "매각" || e.status === "제외" ? "is-off" : ""}">
          <td>${esc(SHORT[e.firm] || e.firm)}</td>
          <td><div class="name">${esc(e.name || "(법인명 원자료 미기재)")}${tags}</div>${e.parent && e.parent !== e.firm ? `<div class="sub">모회사 ${esc(e.parent)}</div>` : ""}${latest}</td>
          <td>${esc(e.country)}</td><td>${esc(e.business || "–")}</td><td>${esc(e.entry_mode || "–")}</td><td>${esc(e.established || "–")}</td>
          <td class="num">${eok(e.assets)}</td><td class="num ${signCls(e.net_income)}">${eok(e.net_income)}</td>
          <td class="sub${e.fresh ? "" : " stale"}">${esc(basisShort(e.basis))}</td>
          <td class="sub">${esc(e.note || "")}</td></tr>`;
      }).join("") || `<tr><td colspan="${COLS.length}"><div class="empty-state">조건에 맞는 법인이 없습니다.</div></td></tr>`;
    };
    const bind = (id, key, ev = "change", get = (t) => t.value) => $(id, el).addEventListener(ev, (e) => { state.filters[key] = get(e.target); draw(); });
    bind("#f-firm", "firm");
    bind("#f-country", "country");
    bind("#f-rel", "relation");
    bind("#f-q", "q", "input");
    bind("#f-off", "off", "change", (t) => t.checked);
    $("#f-reset", el).addEventListener("click", () => { state.filters = { firm: "", country: "", relation: "", q: "", off: false }; state.sort = null; renderDetail(el); });
    $("#f-csv", el).addEventListener("click", () => downloadCsv(filtered()));
    el.querySelectorAll("th[data-k]").forEach((th) => th.addEventListener("click", () => {
      const k = th.dataset.k;
      state.sort = state.sort && state.sort[0] === k ? (state.sort[1] > 0 ? [k, -1] : null) : [k, 1];
      renderDetail(el);
    }));
    draw();
  }

  // ---------- 해외법인 5개년 손익 추이(엑셀 양식 '글로벌 거점별 손익 현황'을 DART 공시·뉴스로 자동화) ----------
  const perShort = (p) => (p.startsWith("1H") ? `1H${p.slice(4)}` : p);
  const fyShort = (p) => `FY${p.slice(4)}`;
  const trendState = { firm: "", all: false, q: "" };

  // 영업수익(선)과 순이익(0 기준 위·아래 막대) 미니 그래프
  function spark(e, fy) {
    const rev = fy.map((p) => e.values[p]?.rev ?? null), ni = fy.map((p) => e.values[p]?.ni ?? null);
    const W = 88, step = W / Math.max(fy.length, 1), x = (i) => step * i + step / 2;
    const rv = rev.filter((v) => v != null), rMin = Math.min(...rv), rMax = Math.max(...rv);
    const ry = (v) => (rMax === rMin ? 7 : 12 - ((v - rMin) / (rMax - rMin)) * 10);
    const pts = rev.map((v, i) => (v == null ? null : `${x(i).toFixed(1)},${ry(v).toFixed(1)}`)).filter(Boolean);
    const nMax = Math.max(...ni.map((v) => Math.abs(v ?? 0)), 1);
    const bars = ni.map((v, i) => {
      if (v == null) return "";
      const h = Math.max(v === 0 ? 0 : 1, (Math.abs(v) / nMax) * 7);
      return `<rect x="${(x(i) - step * 0.3).toFixed(1)}" y="${(v < 0 ? 23 : 23 - h).toFixed(1)}" width="${(step * 0.6).toFixed(1)}" height="${h.toFixed(1)}" fill="var(${v < 0 ? "--neg" : "--pos"})"/>`;
    }).join("");
    return `<svg class="spark" width="${W}" height="31" viewBox="0 0 ${W} 31" role="img" aria-label="영업수익·순이익 추이">
      ${pts.length > 1 ? `<polyline points="${pts.join(" ")}" fill="none" stroke="var(--accent)" stroke-width="1.6"/>` : ""}${pts.map((p) => `<circle cx="${p.split(",")[0]}" cy="${p.split(",")[1]}" r="1.4" fill="var(--accent)"/>`).join("")}
      <line x1="0" x2="${W}" y1="23" y2="23" stroke="var(--line)"/>${bars}</svg>`;
  }

  // 숫자로만 만드는 한 줄 요약(흑자·적자 전환과 연속, 영업수익 연평균 증감, 순이익 전년 대비)
  function trendNote(e, fyAll) {
    // 이 법인의 마지막 사업연도 값 기준(3월처럼 새 사업보고서를 아직 안 낸 회사는 그 전 해까지)
    const end = fyAll.reduce((k, p, i) => (e.values[p]?.ni != null ? i : k), -1);
    const fy = fyAll.slice(0, end + 1);
    const ni = fy.map((p) => e.values[p]?.ni ?? null), rev = fy.map((p) => e.values[p]?.rev ?? null);
    const k = ni.length - 1, L = ni[k], P = ni[k - 1], out = [];
    if (L != null && P != null && L > 0 && P <= 0) out.push(`<b class="pos">${fyShort(fy[k])} 흑자 전환</b>`);
    else if (L != null && P != null && L < 0 && P >= 0) out.push(`<b class="neg">${fyShort(fy[k])} 적자 전환</b>`);
    else if (L) {
      let n = 0;
      for (let i = k; i >= 0 && ni[i] != null && Math.sign(ni[i]) === Math.sign(L); i--) n++;
      if (n >= 2) out.push(`<span class="${L > 0 ? "pos" : "neg"}">${n}년 연속 ${L > 0 ? "흑자" : "적자"}</span>`);
    }
    const i0 = rev.findIndex((v) => v > 0);
    if (i0 >= 0 && i0 < k && rev[k] > 0) {
      const g = (Math.pow(rev[k] / rev[i0], 1 / (k - i0)) - 1) * 100;
      out.push(`영업수익 연평균 ${g >= 0 ? "+" : ""}${fmt(g, 0)}%${i0 ? `(${fyShort(fy[i0])}~)` : ""}`);
    }
    if (L > 0 && P > 0) out.push(`순이익 전년비 ${L >= P ? "+" : ""}${fmt((L / P - 1) * 100, 0)}%`);
    if (e.holding && e.children) out.push(`중간지주(자회사 ${e.children}곳)`);
    if (e.consolidated) out.push("자회사 포함 연결 값");
    return out.join("<br>");
  }

  function trendRows() {
    const st = state.data.subTrend;
    const fy = st.periods.filter((p) => p.startsWith("FY"));
    const last = (e) => Math.abs(e.values[fy[fy.length - 1]]?.rev ?? e.values[fy[fy.length - 2]]?.rev ?? 0);
    const out = [];
    for (const firm of FIRM_ORDER) {
      const ents = (st.firms[firm]?.entities || []).filter((e) => Object.keys(e.values).length);
      if (!ents.length) continue;
      const top = new Set(ents.filter((e) => !e.ref).sort((a, b) => last(b) - last(a)).slice(0, 3).map((e) => e.name));
      // 거점(나라)끼리 모으고, 거점은 큰 순서, 안에서는 중간지주 → 영업수익 큰 순서. 관계사·지분투자 참고 행은 끝에
      const hubSize = {};
      for (const e of ents) if (!e.ref) hubSize[e.country] = Math.max(hubSize[e.country] || 0, last(e));
      ents.sort((a, b) => (a.ref - b.ref) || ((hubSize[b.country] || 0) - (hubSize[a.country] || 0)) || String(a.country).localeCompare(String(b.country), "ko")
        || (b.holding - a.holding) || (last(b) - last(a)));
      for (const e of ents) out.push({ ...e, firm, major: top.has(e.name) || e.ref || firm === HANWHA });
    }
    const q = trendState.q.trim().toLowerCase();
    return out.filter((e) => (!trendState.firm || e.firm === trendState.firm) && (trendState.all || trendState.firm || e.major)
      && (!q || [e.name, e.country, e.business, SHORT[e.firm]].some((v) => String(v || "").toLowerCase().includes(q))));
  }

  function hubNews(firm, country) {
    return state.data.hubNews?.hubs?.[`${firm}|${country}`] || [];
  }

  function renderTrend(el) {
    const st = state.data.subTrend;
    if (!st?.periods?.length) {
      el.innerHTML = `<div class="card"><h3>해외법인 5개년 손익 추이</h3><div class="empty-state">첫 자동 수집 후 표시됩니다(DART 사업보고서·반기보고서).</div></div>`;
      return;
    }
    const pers = st.periods, fy = pers.filter((p) => p.startsWith("FY")), h1 = pers.find((p) => p.startsWith("1H"));
    const named = (pred) => FIRM_ORDER.filter((f) => st.firms[f]?.entities?.length && pred(st.firms[f])).map((f) => SHORT[f] || f);
    const h1Missing = h1 ? named((x) => x.reports?.[h1] && !x.reports[h1].rows) : [];
    const h1None = h1 ? named((x) => x.audit && !x.reports?.[h1]) : [];
    const revNet = named((x) => x.rev_net);
    const fil = (p) => st.filing?.[p];
    const span = (p) => (fil(p) ? `${ymd(fil(p).first).slice(2)}~${ymd(fil(p).last).slice(5)}` : "");
    const next = (() => {
      const y = Number(fy[fy.length - 1].slice(2)), hy = h1 ? Number(h1.slice(2)) : 0;
      return hy > y ? `FY${hy} 사업보고서(${hy + 1}년 3월, 기한 3/31)` : `${y + 1} 반기보고서(${y + 1}년 8월, 기한 8/14)`;
    })();
    el.innerHTML = `<div class="card">
      <h3>해외법인 5개년 손익 추이 · 거점 뉴스</h3>
      <p class="card__meta">DART 사업보고서(토스는 감사보고서)·반기보고서 주석 ‘종속기업 요약재무정보’의 법인별 값(각 법인 100%) · 법인은 위 네트워크 법인(손자회사·중간지주 포함)과 관계사·지분투자 참고 행 · 공시 시즌(3~4월·8월)에는 매일 07:00, 그 밖에는 매주 월요일 새 보고서 확인
        · 최근 접수 ${esc(fyShort(fy[fy.length - 1]))} ${esc(span(fy[fy.length - 1]))}${h1 ? ` · ${esc(perShort(h1))} ${esc(span(h1))}` : ""} · 다음 ${esc(next)}</p>
      <div class="filters" style="margin-top:8px">
        <select id="t-firm" aria-label="증권사"><option value="">전체 증권사</option>${FIRM_ORDER.filter((f) => st.firms[f]?.entities?.length).map((f) => `<option value="${esc(f)}" ${f === trendState.firm ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>
        <select id="t-all" aria-label="범위"><option value="">주요 법인(증권사별 영업수익 상위 3곳)</option><option value="1" ${trendState.all ? "selected" : ""}>전체 법인</option></select>
        <input id="t-q" type="search" placeholder="법인명·국가·업종 검색" value="${esc(trendState.q)}" aria-label="검색">
        <button class="btn btn--accent" id="t-csv" type="button" title="엑셀 양식처럼 법인마다 영업수익·순이익 두 줄, 백만원">CSV 다운로드</button>
      </div>
      <div style="display:flex;align-items:baseline;gap:8px"><p class="count" id="t-count"></p><div style="margin-left:auto">${tmeta(`${fy[0]}~${fy[fy.length - 1]} 사업보고서${h1 ? ` · ${perShort(h1)} 반기 누적` : ""} · 뉴스 최근 1년`, "억원")}</div></div>
      <div class="scroll tall" style="max-height:78vh"><table class="data trend"><thead><tr><th>증권사</th><th>해외법인 · 업종 · 설립 · 지배 구조</th><th>소재지</th><th>지표</th>
        ${pers.map((p) => `<th class="num${p === h1 ? " h1" : ""}">${esc(perShort(p))}</th>`).join("")}<th>추이</th><th>추이 요약(자동)</th><th>거점 뉴스(자동)</th></tr></thead><tbody id="t-body"></tbody></table></div>
      <p class="src">영업수익은 공시 표의 영업수익(매출)입니다${revNet.length ? `(${esc(topic(revNet))} 표에 영업수익 칸이 없어 순영업손익)` : ""}. 중간지주(예: 미래에셋 홍콩법인)의 값은 별도재무제표라 자회사 배당이 섞일 수 있고, 토스 미국 지주는 자회사 포함 연결 값입니다.${h1Missing.length ? ` ${esc(topic(h1Missing))} 반기보고서에서 법인별 손익 표를 찾지 못해 ${esc(perShort(h1))} 칸이 비어 있습니다.` : ""}${h1None.length ? ` ${esc(topic(h1None))} DART에 반기보고서가 없습니다(감사보고서만 공시).` : ""} 이름이 바뀐 법인은 예전 연도가 비어 보일 수 있습니다.
        거점 뉴스는 주요 언론 기사 중 제목에 증권사와 그 나라가 함께 나온 것만 매일 자동으로 모읍니다(같은 그룹 운용사·은행 기사, 시황·홍보 기사 제외). 추이 요약은 숫자로만 만듭니다.</p>
    </div>`;
    const draw = () => {
      const rows = trendRows();
      $("#t-count", el).textContent = `${rows.length}개 법인`;
      // 엑셀 양식처럼 증권사 칸과 거점(증권사 × 나라) 뉴스 칸은 이어지는 행을 하나로 합친다
      const spans = (key) => {
        const out = {};
        for (let i = 0, n; i < rows.length; i += n) {
          for (n = 1; i + n < rows.length && key(rows[i + n]) === key(rows[i]); n++);
          out[i] = n;
        }
        return out;
      };
      const firmSpan = spans((r) => r.firm), hubSpan = spans((r) => `${r.firm}|${r.country}`);
      const two = (a, b, cls = "") => `<div>${a}</div><div class="${cls}">${b}</div>`;
      $("#t-body", el).innerHTML = rows.map((e, i) => {
        const tags = [
          e.holding ? '<span class="tag tag--muted" title="중간지주회사: 법인 수에서 제외">중간지주</span>' : "",
          e.ref ? `<span class="tag tag--muted" title="지분 50% 미만: 법인 수·ROE에서 제외, 참고로만 표시">참고(지분투자)</span>` : "",
          e.firm === HANWHA ? '<span class="tag tag--hw">당사</span>' : "",
        ].join("");
        const gov = e.parent_entity ? `모회사 ${e.parent_entity}${e.own != null && e.own < 100 ? ` ${fmt(e.own, 1)}%` : ""}`
          : e.ref ? "관계사·지분투자" : `${SHORT[e.firm] || e.firm} 직접 출자${e.own != null && e.own < 100 ? ` ${fmt(e.own, 1)}%` : ""}`;
        const sub = [e.business, e.established ? `설립 ${e.established}` : "", gov].filter(Boolean).map(esc).join(" · ");
        const news = hubNews(e.firm, e.country).slice(0, 3);
        const cells = pers.map((p) => {
          const v = e.values[p];
          return `<td class="num${p === h1 ? " h1" : ""}">${v ? two(eok(v.rev), eok(v.ni), signCls(v.ni)) : two("–", "–")}</td>`;
        }).join("");
        return `<tr class="${e.firm === HANWHA ? "is-hanwha" : ""}">
          ${i in firmSpan ? `<td class="trend__firm" rowspan="${firmSpan[i]}"><b>${esc(SHORT[e.firm] || e.firm)}</b></td>` : ""}
          <td class="trend__name"><div class="name">${esc(e.name)}${tags}</div><div class="sub">${sub}</div></td>
          <td>${esc(e.country || "–")}</td><td class="sub">${two("영업수익", "순이익")}</td>${cells}
          <td>${spark(e, fy)}</td><td class="sub trend__note">${trendNote(e, fy) || "–"}</td>
          ${i in hubSpan ? `<td rowspan="${hubSpan[i]}" class="trend__news">${news.length ? `<ul>${news.map((x) => `<li><span class="news__d">${esc(x.date.slice(2).replaceAll("-", "."))}</span> <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a> <span class="sub">${esc(x.src)}</span></li>`).join("")}</ul>` : '<span class="sub">최근 1년 기사 없음</span>'}</td>` : ""}</tr>`;
      }).join("") || `<tr><td colspan="${pers.length + 7}"><div class="empty-state">조건에 맞는 법인이 없습니다.</div></td></tr>`;
    };
    $("#t-firm", el).addEventListener("change", (ev) => { trendState.firm = ev.target.value; draw(); });
    $("#t-all", el).addEventListener("change", (ev) => { trendState.all = !!ev.target.value; draw(); });
    $("#t-q", el).addEventListener("input", (ev) => { trendState.q = ev.target.value; draw(); });
    $("#t-csv", el).addEventListener("click", () => trendCsv(trendRows(), pers, fy));
    draw();
  }

  // 엑셀 양식과 같은 모양: 법인마다 영업수익·순이익 두 줄, 백만원
  function trendCsv(rows, pers, fy) {
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const head = ["국내 증권사", "해외법인", "업종", "소재지", "설립일", "지배 구조", "수익성 지표", ...pers.map((p) => `${perShort(p)}(백만원)`), "추이 요약", "거점 뉴스(최근)"];
    const lines = [head.map(q).join(",")];
    for (const e of rows) {
      const gov = e.parent_entity ? `모회사 ${e.parent_entity}` : e.ref ? "관계사·지분투자" : "직접 출자";
      const note = trendNote(e, fy).replace(/<br>/g, " / ").replace(/<[^>]+>/g, "");
      const news = hubNews(e.firm, e.country).slice(0, 3).map((x) => `${x.date} ${x.title} (${x.src}) ${x.url}`).join("\n");
      for (const [k, label] of [["rev", "영업수익"], ["ni", "당기순이익"]]) {
        lines.push([e.firm, e.name, e.business, e.country, e.established, gov, label, ...pers.map((p) => e.values[p]?.[k]),
          k === "rev" ? note : "", k === "rev" ? news : ""].map(q).join(","));
      }
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
    a.download = `해외법인_5개년_손익추이_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function downloadCsv(rows) {
    const head = ["증권사", "그룹", "법인명", "모회사", "국가", "업종", "진출방식", "설립·취득", "관계", "상태",
      "자산(백만원)", "부채(백만원)", "자본(백만원)", "영업이익(백만원)", "순이익(백만원)", "기준", "비고"];
    const keys = ["firm", "group", "name", "parent", "country", "business", "entry_mode", "established", "relation", "status",
      "assets", "liabilities", "equity", "op_income", "net_income", "basis", "note"];
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = "﻿" + [head.map(q).join(","), ...rows.map((r) => keys.map((k) => q(r[k])).join(","))].join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = `해외법인_상세_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function feedCard(limit = 40, link = false) {
    const dart = state.data.dart;
    const feed = dart?.feed || [];
    return `<div class="card"><h3>${link ? '<a href="#domestic/feed">' : ""}최근 120일 해외·출자 관련 공시${link ? "</a>" : ""}</h3>
      <p class="card__meta">${dart ? `DART 자동 수집 ${esc(dart.updated_at.slice(0, 10))} · ${feed.length}건` : "DART 키 등록 후 첫 자동 수집 때 채워집니다"}</p>
      ${feed.length ? `${tmeta(`DART 접수일 · 최근 120일`, "")}<ul class="feed">${feed.slice(0, limit).map((r) => `<li><span class="d">${esc(ymd(r.date))}</span><span>${esc(SHORT[r.firm] || r.firm)}</span>
        <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></li>`).join("")}</ul>` : '<div class="empty-state">표시할 공시가 없습니다.</div>'}
      ${dart?.errors?.length ? `<p class="src">수집 경고: ${dart.errors.map(esc).join(" · ")}</p>` : ""}</div>`;
  }

  // DART 신규 해외 출자 요약: 자동 반영 n · 확인 필요 m
  const changeNote = (cs) => [cs.filter((c) => c.type === "자동 반영").length && `자동 반영 ${cs.filter((c) => c.type === "자동 반영").length}`,
    cs.filter((c) => c.type !== "자동 반영").length && `확인 필요 ${cs.filter((c) => c.type !== "자동 반영").length}`].filter(Boolean).join(" · ");
  const changeTag = (c) => c.type === "자동 반영" ? '<span class="status status--up">자동 반영</span>' : `<span class="status status--soon" title="${esc(c.why || "")}">확인 필요${c.why ? ` · ${esc(c.why)}` : ""}</span>`;

  function changesCard(link = false) {
    const d = state.data.domestic;
    return `<div class="card"><h3>${link ? '<a href="#domestic/feed">' : ""}변동 감지 · DART 신규 해외법인${link ? "</a>" : ""}</h3><p class="card__meta">DART 최신 보고서에 새로 나온 경영참여 목적 해외 출자 · 금융업 법인은 자동 반영, 나머지는 확인 필요</p>
      ${d.changes.length ? `<ul class="list">${d.changes.map((c) => `<li><span class="tag tag--new" style="margin:0 6px 0 0">${esc(SHORT[c.firm])}</span>${esc(c.name)} ${changeTag(c)}</li>`).join("")}</ul>` : '<p class="sub">감지된 변동이 없습니다.</p>'}</div>`;
  }

  // 제외 목록은 보여 주지 않고 건수만 주석으로 남긴다
  function excludedNote() {
    const n = state.data.domestic.excluded.length;
    return `<p class="src">※ 펀드·신탁·Vehicle(투자조합·사모·SPC/SPV·유동화 등)은 법인명·업종 규칙으로 자동 제외했습니다${n ? `(최근 수집 ${n}건)` : ""}.</p>`;
  }

  // 국내 탭은 한 페이지: 위쪽 매트릭스와 공시·변동, 아래쪽 상세 표. 바로 가기는 해당 위치로 스크롤
  function renderDomestic(view) {
    renderKpis();
    document.querySelectorAll("#section-domestic .pill").forEach((p) => p.setAttribute("aria-selected", String(p.dataset.view === view)));
    const el = $("#domestic-view");
    el.innerHTML = `<div class="dir"><div id="dom-matrix" class="anchor"></div>
      <div id="dom-feed" class="anchor">${newsCard(20).replace("span4 ", "")}${changesCard()}${feedCard(25)}${excludedNote()}</div></div>
      <div id="dom-detail" class="anchor" style="margin-top:12px"></div>
      <div id="dom-trend" class="anchor" style="margin-top:12px"></div>`;
    renderMatrix($("#dom-matrix", el));
    renderDetail($("#dom-detail", el));
    renderTrend($("#dom-trend", el));
    const target = view && $(`#dom-${view}`, el);
    if (target) requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
    else window.scrollTo(0, 0);
  }

  // ---------- 한눈에 보기 ----------
  const dday = (iso) => Math.ceil((new Date(`${iso}T00:00:00+09:00`) - Date.now()) / 864e5);

  // 0을 가운데 두고 왼쪽 (-), 오른쪽 (+)로 그리는 막대
  function divBar(v, max) {
    const w = v == null || !max ? 0 : Math.min(50, Math.max(v === 0 ? 0 : 2, (Math.abs(v) / max) * 50));
    return `<div class="dbar" title="${v == null ? "" : fmt(v / 100, 1)}억원"><span class="dbar__axis"></span>${
      v == null ? "" : `<span class="dbar__fill ${v < 0 ? "is-neg" : "is-pos"}" style="${v < 0 ? "right" : "left"}:50%;width:${w}%"></span>`}</div>`;
  }

  // 당사 해외자회사 공시값: hanwha/data/dart_subs.json(DART 사업·반기·분기보고서 주석 '종속기업 요약재무정보', 백만원).
  // periods는 오래된 것부터 쌓이고 마지막이 최신 정기보고서. 예전 형식(report·subs 한 기간)도 읽는다
  const HW_MONTHS = { FY: 12, "1H": 6, "9M": 9, "1Q": 3 };
  const hwKey = (n) => String(n || "").toLowerCase().replace(/\(주\d*\)/g, "").replace(/^pt\s+/, "").replace(/[^a-z0-9]/g, "");
  function hwPublic(hw, pick = "") {
    const ds = hw.subs;
    let periods = ds?.periods || [];
    // 기간 선택: dart_subs.json history(정기보고서마다 같은 요약재무정보, 오래된 것 → 최신)에서 고른 기간까지만 쓴다
    const hist = ds?.history || [];
    const at = pick ? hist.findIndex((p) => p.label === pick) : -1;
    if (at >= 0) periods = hist.slice(0, at + 1);
    if (!periods.length && ds?.report && ds?.subs) {
      const p = ds.report.period, y = Number(ds.report.year);
      periods = [{ label: p === "FY" ? `FY${y}` : `${p}${String(y).slice(2)}`, period: p, year: y, months: HW_MONTHS[p] || 12, report: ds.report, subs: ds.subs }];
    }
    if (!periods.length) return null;
    const latest = periods[periods.length - 1];
    const fy = [...periods].reverse().find((x) => x.period === "FY" && x !== latest);
    const meta = hw.entities?.entities || [];
    const order = (k) => { const i = meta.findIndex((x) => x.key === k); return i < 0 ? meta.length : i; };
    const ents = Object.keys(latest.subs).sort((a, b) => order(a) - order(b)).map((key) => {
      const m = meta.find((x) => x.key === key) || {};
      return { key, label: m.label || String(latest.subs[key].name).replace(/\s*\(주\d*\)/g, ""), name: m.name || latest.subs[key].name, country: m.country, stake: ds.stakes?.[key] };
    });
    const eq = (s) => (s?.assets != null && s?.liab != null ? s.assets - s.liab : null);
    const ann = (per, s) => (s?.ni == null ? null : (s.ni * 12) / (per.months || 12));
    const own = (per, k) => (per.subs[k]?.ni == null || ents.find((e) => e.key === k)?.stake == null ? null : (per.subs[k].ni * ents.find((e) => e.key === k).stake) / 100);
    const sum = (vals) => (vals.some((v) => v != null) ? vals.reduce((a, v) => a + (v || 0), 0) : null);
    const total = (per) => ({
      ni: sum(ents.map((e) => per.subs[e.key]?.ni)),
      own: ents.every((e) => e.stake != null) ? sum(ents.map((e) => own(per, e.key))) : null,
      equity: sum(ents.map((e) => eq(per.subs[e.key]))),
      roe: (() => {
        const rows = ents.map((e) => per.subs[e.key]).filter((x) => x?.ni != null && eq(x) > 0);
        const e = rows.reduce((a, x) => a + eq(x), 0);
        return e ? (rows.reduce((a, x) => a + ann(per, x), 0) / e) * 100 : null;
      })(),
    });
    return { periods, latest, fy, ents, eq, ann, own, total };
  }
  const hwBasis = (per) => `${per.label} ${String(per.report?.name || "").replace(/\s*\(.*\)$/, "")}${per.period === "FY" ? "" : " 누적"}`;

  function hanwhaCard(hw) {
    const hist = hw.subs?.history || [];
    const hp = hwPublic(hw, state.per.hw);
    if (!hp) return `<div class="card span7"><h3><a href="#hanwha">당사 해외자회사</a></h3><div class="empty-state">한화투자증권 탭 데이터 준비 중</div></div>`;
    const { latest, fy, ents } = hp;
    const cols = [latest, fy].filter(Boolean);
    const max = Math.max(...cols.flatMap((per) => ents.map((e) => Math.abs(per.subs[e.key]?.ni || 0))), 1);
    const roe = (per, s) => { const q = hp.eq(s); return q > 0 && s?.ni != null ? (hp.ann(per, s) / q) * 100 : null; };
    const tl = hp.total(latest);
    const tf = fy ? hp.total(fy) : null;
    return `<div class="card span7"><h3><a href="#hanwha">당사 해외자회사 실적 (DART ${esc(latest.label)})</a></h3>
      <p class="card__meta">DART ${esc(cols.map((per) => per.report?.name || per.label).join(" · "))} 연결재무제표 주석 ‘종속기업 요약재무정보’ · 법인별은 법인 전체(100%) · 막대는 0을 기준으로 왼쪽 손실(−), 오른쪽 이익(+)</p>
      ${hist.length > 1 ? tmetaSel(perSel("hw", [{ v: "", l: `최신 (${(hw.subs.periods || []).at(-1)?.label || ""})` },
        ...[...hist].reverse().map((p) => ({ v: p.label, l: `${p.label} ${p.period === "FY" ? "사업" : p.period === "1H" ? "반기" : "분기"}보고서` }))], "당사 해외자회사 공시 기간"),
        `· ${cols.map(hwBasis).join(" · ")}`, "억원 · %") : tmeta(cols.map(hwBasis).join(" · "), "억원 · %")}<div class="scroll"><table class="mini"><thead><tr><th>법인</th>${cols.map((per) => `<th colspan="2">${esc(per.label)} 순이익 (−  0  +)</th>`).join("")}<th class="num">자본</th><th class="num">ROE</th><th class="num">지분율</th></tr></thead><tbody>
      ${ents.map((e) => {
        const s = latest.subs[e.key];
        return `<tr><td><b>${esc(e.label)}</b></td>${cols.map((per) => { const v = per.subs[e.key]?.ni; return `<td class="dcell">${divBar(v, max)}</td><td class="num ${signCls(v)}">${eok(v)}</td>`; }).join("")}
          <td class="num">${eok(hp.eq(s))}</td><td class="num ${signCls(roe(latest, s))}">${roe(latest, s) == null ? "–" : fmt(roe(latest, s), 1)}</td><td class="num">${e.stake == null ? "–" : fmt(e.stake, e.stake % 1 ? 2 : 0)}</td></tr>`;
      }).join("")}
      <tr class="is-total"><td><b>4사 합계(100%)</b></td>${cols.map((per) => { const v = hp.total(per).ni; return `<td></td><td class="num ${signCls(v)}"><b>${eok(v)}</b></td>`; }).join("")}<td class="num"><b>${eok(tl.equity)}</b></td><td class="num ${signCls(tl.roe)}"><b>${tl.roe == null ? "–" : fmt(tl.roe, 1)}</b></td><td></td></tr>
      ${tl.own != null ? `<tr class="is-total"><td><b>지배지분 합계</b></td>${cols.map((per) => { const v = hp.total(per).own; return `<td></td><td class="num ${signCls(v)}"><b>${eok(v)}</b></td>`; }).join("")}<td></td><td></td><td></td></tr>` : ""}
      </tbody></table></div>
      <p class="src">자본 = 자산 − 부채(${esc(latest.label)} 말) · ROE = 순이익 × 12/${latest.months}개월 ÷ 기말 자본(4사 합계는 자본 가중) · 지배지분 = 순이익 × 당사 지분율(DART 타법인출자현황${state.per.hw ? ", 지분율은 최신 공시값" : ""})${tf?.roe != null ? ` · ${esc(fy.label)} 4사 ROE ${fmt(tf.roe, 1)}%` : ""} · 새 정기보고서가 공시되면 자동으로 바뀝니다</p></div>`;
  }

  function todoCard(hw) {
    const todo = hw.reg?.todo || [];
    // 자동 계산 항목이 늘어나므로 기한 가까운 순으로 6건, 완료는 최근 2건만 보이고 나머지는 한화 탭에서
    // 내부 일정(law=내부)은 대외보고 마감에서 뺀다
    const allOpen = todo.filter((t) => t.status !== "done" && t.law !== "내부").sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999"));
    const allDone = todo.filter((t) => t.status === "done");
    const open = allOpen.slice(0, 7);
    const done = allDone.slice(0, 2);
    const more = allOpen.length - open.length + allDone.length - done.length;
    return `<div class="card span5"><h3><a href="#hanwha">필수 대외보고 To-do</a></h3><p class="card__meta">진행 ${allOpen.length}건 · 완료 ${allDone.length}건</p>
      ${tmeta(`오늘(${new Date().toISOString().slice(0, 10).replaceAll("-", ".")}) D-day`, "")}<table class="mini"><tbody>${open.map((t) => {
        const d = t.due ? dday(t.due) : null;
        const st = d == null ? '<span class="status status--up">예정</span>' : `<span class="status ${d < 0 ? "status--soon" : d <= 45 ? "status--soon" : "status--up"}">${d < 0 ? `D+${-d}` : `D-${d}`}</span>`;
        return `<tr><td>${st}</td><td><b>${esc(t.entity)}</b> ${esc(t.item)}${t.law === "내부" ? ' <span class="tag tag--muted">내부</span>' : ""}<div class="sub">${esc(t.due ? t.due.replaceAll("-", ".") : t.note || "")}</div></td></tr>`;
      }).join("")}${done.map((t) => `<tr><td><span class="status status--done">완료</span></td><td class="sub">${esc(t.entity)} ${esc(t.item)}</td></tr>`).join("")}</tbody></table>
      ${more > 0 ? `<p class="src"><a href="#hanwha">외 ${more}건은 한화투자증권 탭에서</a></p>` : ""}</div>`;
  }

  function digitalCard(dg) {
    const items = dg?.items || [];
    return `<div class="card span5"><h3><a href="#digital">디지털자산 규제 요약</a></h3>
      <p class="card__meta">${dg ? `${esc(dg.updated || "")} 기준${dg.headline ? ` · ${esc(dg.headline)}` : ""}` : "주요국 가상자산·STO·스테이블코인 규제"}</p>
      ${items.length ? `${tmeta(dg.updated || "", "")}<table class="mini"><tbody>${items.slice(0, 8).map((x) => `<tr><td style="white-space:nowrap">${esc(x.flag || "")} <b>${esc(x.jurisdiction)}</b></td>
        <td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)}${x.date ? ` <span class="sub">${esc(x.date)}</span>` : ""}</td>
        <td>${x.status ? `<span class="status status--up">${esc(x.status)}</span>` : ""}</td></tr>`).join("")}</tbody></table>`
        : '<div class="empty-state">준비 중입니다. 디지털자산 규제 탭이 채워지면 국가별 요약이 여기에 보입니다.</div>'}</div>`;
  }

  // 데이터에서 규칙으로 뽑는 핵심 포인트(LLM 없이 매주 같이 바뀜)
  function insights(hw, corps) {
    const d = state.data.domestic;
    const out = [];
    const byFirm = {};
    corps.forEach((e) => (byFirm[e.firm] = byFirm[e.firm] || []).push(e));
    const firmRank = Object.entries(byFirm).sort((a, b) => b[1].length - a[1].length);
    const top = firmRank[0];
    const myIdx = firmRank.findIndex(([f]) => f === HANWHA);
    if (top) out.push(`<b>네트워크</b> ${esc(SHORT[top[0]])}이 현지법인 ${top[1].length}개·${new Set(top[1].map((e) => e.country)).size}개국으로 최다입니다. 당사는 ${byFirm[HANWHA]?.length || 0}개로 ${myIdx + 1}위입니다.`);
    const byCountry = {};
    corps.forEach((e) => (byCountry[e.country] = byCountry[e.country] || []).push(e));
    const mineC = [...new Set((byFirm[HANWHA] || []).map((e) => e.country))];
    const crowd = mineC.map((c) => [c, byCountry[c].length, new Set(byCountry[c].map((e) => e.firm)).size]).sort((a, b) => b[1] - a[1]);
    if (crowd.length) out.push(`<b>당사 진출국 경쟁</b> ${crowd.map(([c, n, f]) => `${esc(c)} 한국계 ${n}개 법인(${f}개사)`).join(", ")}. 동남아 3개국 모두 국내 대형사와 직접 경쟁합니다.`);
    const pnl = firmPnl(corps).filter((r) => r.value != null);
    const losers = corps.filter((e) => e.fresh && e.net_income != null && e.net_income < 0);
    if (pnl.length) out.push(`<b>해외 손익(${esc(pnlBasis())})</b> 해외법인 순이익 합계는 ${esc(SHORT[pnl[0].name])} ${eok(pnl[0].value * 100)}억원이 1위입니다. 적자 해외법인은 ${losers.length}개(${[...new Set(losers.map((e) => SHORT[e.firm]))].join("·")})입니다.`);
    const hp = hwPublic(hw);
    if (hp) {
      const { latest } = hp, t = hp.total(latest);
      const ni = (e) => latest.subs[e.key]?.ni;
      const best = [...hp.ents].filter((e) => ni(e) != null).sort((a, b) => ni(b) - ni(a))[0];
      const loss = hp.ents.filter((e) => ni(e) < 0);
      out.push(`<b>당사 실적(${esc(latest.label)} 공시)</b> 해외자회사 ${hp.ents.length}사 순이익은 ${t.own != null ? `지배지분 ${eok(t.own)}억원(100% 기준 ${eok(t.ni)}억원)` : `${eok(t.ni)}억원(100% 기준)`}입니다.${best && ni(best) > 0 ? ` 가장 큰 곳은 ${esc(best.label)} ${eok(ni(best))}억원이고,` : ""}${loss.length ? ` 적자 법인은 ${loss.map((e) => esc(e.label)).join("·")}입니다.` : ` ${hp.ents.length}사 모두 흑자입니다.`}`);
    }
    const next = (hw.reg?.todo || []).filter((t) => t.status !== "done" && t.due && t.law !== "내부").sort((a, b) => a.due.localeCompare(b.due))[0];
    if (d.changes.length || next) out.push(`<b>이번 주 확인</b> ${d.changes.length ? `DART 신규 해외 출자 ${d.changes.length}건(${d.changes.map((c) => `${esc(SHORT[c.firm])} ${esc(c.name)}${c.type === "자동 반영" ? " 반영" : " 확인 필요"}`).join(", ")}).` : ""}${next ? ` 다음 대외보고는 ${esc(next.entity)} ${esc(next.item)}, 기한 ${esc(next.due.replaceAll("-", "."))}(D-${dday(next.due)})입니다.` : ""}`);
    return out.concat(macroPoints());
  }

  // 국가별 매크로 줄: 한화 탭 YTD Macro가 모으는 정책금리(BIS)·지수(Yahoo)·환율(ECOS)과 금리 결정 일정,
  // 국가별 주요 헤드라인(macro_news.json, 주요 매체 RSS)을 규칙으로 엮는다(LLM 없음)
  const MACRO_ROWS = [
    { key: "KR", label: "한국", rate: "KR", idx: ["코스피"], fx: "USD", fxName: "원/달러" },
    { key: "US", label: "미국", rate: "US", idx: ["S&P 500"], dxy: true },
    { key: "ID", label: "인도네시아", rate: "ID", idx: ["IDX(자카르타)"], fx: "IDR", fxName: "루피아" },
    { key: "VN", label: "베트남", rate: "VN", idx: ["VN-Index"], fx: "VND", fxName: "동" },
    { key: "JP", label: "일본·중국", rate: "JP", idx: ["Nikkei 225", "상해종합", "항셍"], fx: "JPY", fxName: "엔", news: ["JP", "CN"] },
  ];
  function macroPoints() {
    const mk = state.data.macro, cal = state.data.rateCal, mn = state.data.macroNews;
    if (!mk && !mn) return [];
    const today = new Date().toISOString().slice(0, 10);
    const pct = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${fmt(v, 1)}%`);
    const bp = (v) => `${v > 0 ? "+" : ""}${fmt(v)}bp`;
    const md = (s) => `${+s.slice(5, 7)}/${+s.slice(8, 10)}`;
    const head = (x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a> <span class="sub">${esc(x.src)} ${md(x.date)}</span>`;
    const out = MACRO_ROWS.map((r) => {
      const bits = [];
      const pr = mk?.policy?.table?.find((t) => t.key === r.rate);
      if (pr) bits.push(`${esc(pr.name.split(" ").pop().replace(/\(.*\)/, ""))} ${fmt(pr.now, 2)}%(1년 ${bp(pr.d1y_bp)})`);
      r.idx.forEach((n) => {
        const ix = mk?.indices?.find((i) => i.name === n);
        if (ix) bits.push(`${esc(n.replace(/\(.*\)/, ""))} YTD <b class="${signCls(ix.chg.YTD)}">${pct(ix.chg.YTD)}</b>(1M ${pct(ix.chg["1M"])})`);
      });
      const fx = r.fx && mk?.fx?.rows?.find((x) => x.ccy === r.fx);
      if (fx && r.fx === "USD") bits.push(`원/달러 ${fmt(fx.krw, 1)}(1W ${pct(fx.chg_1w)})`);
      else if (fx) bits.push(`${r.fxName} 대비 원화 1W ${pct(-fx.chg_1w)}`);
      if (r.dxy) { const d = mk?.indices?.find((i) => i.symbol === "DX-Y.NYB"); if (d) bits.push(`DXY ${fmt(d.close, 1)}(YTD ${pct(d.chg.YTD)})`); }
      const nx = (cal?.events || []).find((e) => e.bank === r.rate && e.date >= today);
      if (nx) bits.push(`다음 결정 ${md(nx.date)}`);
      const news = (r.news || [r.key]).map((k) => mn?.countries?.[k]?.items?.[0]).filter(Boolean).sort((a, b) => b.priority - a.priority || b.date.localeCompare(a.date))[0];
      if (!bits.length && !news) return null;
      return `<b>${r.label}</b> ${bits.join(" · ")}${news ? `.<br>${news.priority ? '<span class="status status--soon">구조</span> ' : ""}${head(news)}` : ""}`;
    }).filter(Boolean);
    // 글로벌·기타 나라의 주요 헤드라인(지수 분류·강등 같은 구조적 뉴스 먼저)
    const rest = ["GL", "SG", "IN"].flatMap((k) => (mn?.countries?.[k]?.items || []).slice(0, 1).map((x) => ({ ...x, label: mn.countries[k].label })));
    if (rest.length) out.push(`<b>글로벌 뉴스</b> ${rest.map((x) => `[${esc(x.label)}] ${head(x)}`).join("<br>")}`);
    return out;
  }

  // 지난 수집 대비 변화(update_dart.py 가 dart_latest.json 의 diff 로 남김)
  function changesWeekCard() {
    const dart = state.data.dart;
    const diff = dart?.diff;
    const feed = dart?.feed || [];
    const since = diff?.prev_at ? diff.prev_at.slice(0, 10) : null;
    const li = (tag, cls, text) => `<li><span class="status ${cls}">${tag}</span> ${text}</li>`;
    const items = [];
    if (diff) {
      diff.entities_added.forEach((x) => items.push(li("신규 법인", "status--soon", `${esc(SHORT[x.firm])} ${esc(x.name)}`)));
      diff.entities_removed.forEach((x) => items.push(li("소멸·매각", "status--done", `${esc(SHORT[x.firm])} ${esc(x.name)}`)));
      diff.candidates_added.forEach((x) => items.push(li("검토 후보", "status--soon", `${esc(SHORT[x.firm])} ${esc(x.name)}`)));
      diff.rank_moves.forEach((x) => items.push(li("순위", "status--up", `${esc(SHORT[x.firm])} 자기자본 ${x.from}위 → ${x.to}위`)));
      diff.new_reports.forEach((x) => items.push(li("새 보고서", "status--up", `${esc(SHORT[x.firm])} ${esc(x.label)} 반영`)));
      diff.new_filings.slice(0, 6).forEach((r) => items.push(li("새 공시", "status--up", `${esc(SHORT[r.firm])} <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a> <span class="sub">${esc(ymd(r.date))}</span>`)));
      if (diff.new_filings.length > 6) items.push(`<li class="sub">새 공시 외 ${diff.new_filings.length - 6}건</li>`);
    } else {
      // 비교할 지난 수집이 없을 때: 최근 7일 공시와 기준 데이터 대비 신규 후보
      const cut = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10).replaceAll("-", "");
      state.data.domestic.changes.forEach((c) => items.push(c.type === "자동 반영" ? li("신규 법인", "status--up", `${esc(SHORT[c.firm])} ${esc(c.name)}`) : li("검토 후보", "status--soon", `${esc(SHORT[c.firm])} ${esc(c.name)}`)));
      feed.filter((r) => r.date >= cut).slice(0, 8).forEach((r) => items.push(li("새 공시", "status--up", `${esc(SHORT[r.firm])} <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a> <span class="sub">${esc(ymd(r.date))}</span>`)));
    }
    return `<div class="card span4 week"><h3><a href="#domestic/feed">이번 주 바뀐 것</a></h3>
      <p class="card__meta">${since ? `지난 수집(${esc(since)}) 대비 · DART 자동 비교` : "기준 데이터 대비 신규 후보와 최근 30일 공시 · 다음 주간 수집부터 지난주 대비로 비교"}</p>
      ${items.length ? `<ul class="list week__list">${items.join("")}</ul>` : '<p class="sub">지난 수집 대비 바뀐 해외법인·순위·공시가 없습니다.</p>'}</div>`;
  }

  // 법인·사무소 신설·인수 보도(뉴스만으로는 세지 않고 표시만 한다)
  const NEW_ENTITY_NEWS = /지분.{0,3}인수|인수 계약|(법인|사무소|지점|자회사|증권사).{0,14}(설립|개설|출범|인가|인수|신설|오픈)|(설립|개설|출범|신설|인수).{0,10}(법인|사무소|지점)|acquir|subsidiary|opens? .{0,20}office/i;

  // 국내 증권사 해외진출 뉴스(news.json: Google News RSS, 매체 화이트리스트, 매일 아침 자동 수집)
  function newsCard(limit = 14) {
    const n = state.data.news;
    const items = (n?.items || []).slice(0, limit);
    const at = n?.updated_at ? `${n.updated_at.slice(5, 10).replace("-", ".")} ${n.updated_at.slice(11, 16)}` : "";
    return `<div class="card span4 news"><h3>국내 증권사 해외진출 뉴스</h3>
      <p class="card__meta">주요 언론 ${n?.sources?.length || ""}곳만 · 매일 06:30(평일 12:30·17:30 추가) 자동 수집${at ? ` · 최근 ${esc(at)}` : ""}</p>
      ${items.length ? `<ul class="news__list">${items.map((x) => `<li><span class="news__d">${esc(x.date.slice(5).replace("-", "."))}</span>
        <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>
        <span class="news__m">${esc(x.src)}${NEW_ENTITY_NEWS.test(x.title) ? ` <span class="tag tag--new" title="뉴스 보도만으로는 세지 않습니다. DART 공시나 확인 후 반영됩니다.">신규 진출 보도·미확인</span>` : ""}${(x.firms || []).map((f) => ` <span class="tag${f === HANWHA ? " tag--hw" : ""}">${esc(SHORT[f] || f)}</span>`).join("")}</span></li>`).join("")}</ul>`
        : '<div class="empty-state">첫 자동 수집 후 표시됩니다.</div>'}</div>`;
  }

  // 증권사별 해외 종속기업 가중평균 ROE = 순이익 합계 ÷ 자본(자산−부채) 합계, 사업보고서 종속기업 요약재무정보
  function roeBlock() {
    const sf = state.data.subFin, st = state.data.subTrend;
    // 기간 선택: 기본은 sub_fin.json(최근 사업보고서), 고르면 5개년 추이 수집분(sub_trend.json roe, 같은 계산 규칙)
    const per = (st?.periods || []).includes(state.per.roe) ? state.per.roe : "";
    const pick = (f) => (per ? st.firms?.[f]?.roe?.[per] && { ...st.firms[f].roe[per], subs: {}, report: st.firms[f].reports?.[per]?.label } : sf?.firms?.[f]);
    const rows = FIRM_ORDER.map((f) => ({ f, x: pick(f) })).filter((r) => r.x && r.x.roe != null).sort((a, b) => b.x.roe - a.x.roe);
    if (!rows.length && !per) return "";
    const rep = per ? per.replace(/^1H(\d{4})$/, "1H$1 연환산") : [...new Set(rows.map((r) => r.x.report))].join("·").replace(/(\d{4}) (사업|감사)보고서/g, "FY$1");
    const repU = [...new Set(rep.split("·"))].join("·");
    const sfRep = [...new Set(FIRM_ORDER.map((f) => sf?.firms?.[f]?.report).filter(Boolean).map((r) => r.replace(/(\d{4}) (사업|감사)보고서/, "FY$1")))].join("·");
    const opts = st?.periods?.length ? [{ v: "", l: `${sfRep} (최신 사업보고서)` },
      ...[...st.periods].reverse().filter((p) => p !== sfRep).map((p) => ({ v: p, l: p.startsWith("1H") ? `${p} 반기 (연환산)` : p }))] : null;
    // 자본이 아주 작은 법인(예: 토스 미국 중간지주)이 막대 눈금을 끌지 않도록 30%에서 자른다
    const max = Math.min(30, Math.max(...rows.map((r) => Math.abs(r.x.roe)), 1));
    const dartFirms = new Set(state.data.domestic.firms.filter((f) => f.latest && (!per || st.firms?.[f.firm]?.reports?.[per])).map((f) => f.firm));
    const missing = FIRM_ORDER.filter((f) => dartFirms.has(f) && !rows.some((r) => r.f === f)).map((f) => SHORT[f] || f);
    // 네트워크 법인 중 요약재무 표에 없는 법인(예: 연말 직전 취득)
    const cnt = (f) => state.data.domestic.entities.filter((e) => e.firm === f && counted(e) && e.relation === "종속(자회사)").length;
    const inSf = (f, e) => Object.entries((per ? {} : sf.firms[f]?.subs) || {}).some(([nm, x]) => x.seed_name === e.name || e.dart_name === nm || (!x.seed_name && keyName(nm) === keyName(e.name) && (!x.country || x.country === e.country)));
    // 중간지주 자본에서 뺀 자회사 몫(fetch_sub_fin.py summarize)
    const nested = rows.filter(({ x }) => x.overlap > 0).map(({ f, x }) => `${SHORT[f] || f} −${eok(x.overlap)}억(중간지주 ${x.holdcos.length}곳)`);
    // 자회사까지 든 연결 값으로 실린 중간지주(토스 미국 지주): 같은 나라 자회사는 그 행에 들어 있다
    const consHold = (f) => Object.entries((per ? {} : sf.firms[f]?.subs) || {}).filter(([, x]) => x.consolidated && x.seed_name);
    const inHold = (f, e) => consHold(f).some(([, x]) => x.country === e.country);
    const consNote = rows.flatMap(({ f }) => consHold(f).map(([nm]) => `${SHORT[f] || f} ${nm.replace(/\s*\(\*\d*\)/g, "")}`));
    const gaps = per ? [] : rows.flatMap(({ f }) => state.data.domestic.entities.filter((e) => e.firm === f && counted(e) && e.relation === "종속(자회사)" && !inSf(f, e) && !inHold(f, e))
      .map((e) => `${SHORT[f] || f} ${e.name}${e.first_acquired && /^\d{4}\.(1[0-2])/.test(e.first_acquired) ? `(${e.first_acquired} 취득)` : ""}`));
    return `<h4 class="mx__h" style="margin-top:10px">해외 종속기업 가중평균 ROE <span>${esc(repU)}</span></h4>
      <p class="card__meta">사업보고서(토스는 감사보고서) 주석 ‘종속기업 요약재무정보’ 중 위 네트워크 법인(손자회사·중간지주 포함, 펀드·SPV·부동산 제외) · ROE = 순이익 합계 ÷ 자본(자산−부채, 중간지주의 자회사 몫 제외) 합계, 기말 자본가중 평균 · 억원 · 매주 자동 수집</p>
      ${opts ? tmetaSel(perSel("roe", opts), "", "억원 · ROE %") : tmeta(repU, "억원 · ROE %")}${per ? `<p class="src">${esc(per)} ${per.startsWith("1H") ? "반기보고서 표(순이익 × 2 연환산)" : "사업보고서 표"} · 법인 목록은 현재 네트워크 기준이라 그해 표에 없던 법인은 빠집니다 · 5개년 손익 추이와 같은 원문</p>` : ""}${rows.length ? "" : '<div class="empty-state">이 기간 보고서에는 해외 종속기업 요약재무 표가 없습니다.</div>'}<div class="scroll"><table class="mini fin"><thead><tr><th>증권사</th><th class="num">법인</th><th class="num">자본 합계</th><th class="num">순이익 합계${per.startsWith("1H") ? "<small class=\"asof\">6개월</small>" : ""}</th><th class="dcell">ROE</th><th></th></tr></thead><tbody>
      ${rows.map(({ f, x }) => `<tr class="${f === HANWHA ? "is-hw" : ""}"><td><b>${esc(SHORT[f] || f)}</b>${f === HANWHA ? ' <span class="tag tag--hw">당사</span>' : ""}</td>
        <td class="num">${x.n}${cnt(f) > x.n ? `<small class="sub">/${cnt(f)}</small>` : ""}</td><td class="num">${eok(x.equity)}</td><td class="num ${signCls(x.ni)}">${eok(x.ni)}</td>
        <td class="dcell">${divBar(x.roe, max).replace(/title="[^"]*"/, `title="ROE ${fmt(x.roe, 1)}%"`)}</td><td class="num"><b class="${signCls(x.roe)}">${fmt(x.roe, 1)}%</b>${x.equity < 10000 ? "<sup>*</sup>" : ""}</td></tr>`).join("")}
      </tbody></table></div>${rows.some(({ x }) => x.equity < 10000) ? `<p class="src">* 해외 자본 합계가 100억원 미만이라(${esc(rows.filter(({ x }) => x.equity < 10000).map(({ f, x }) => `${SHORT[f] || f} ${eok(x.equity)}억`).join(", "))}) 작은 손익에도 ROE가 크게 움직입니다.</p>` : ""}${gaps.length ? `<p class="src">법인 칸 ‘3/4’는 요약재무 표에 실린 법인 수/네트워크 법인 수입니다. 표에 없어 ROE에서 빠진 법인: ${esc(gaps.join(" · "))}.</p>` : ""}${missing.length ? `<p class="src">${esc(missing.join("·"))}: ${per && per.startsWith("1H") ? "반기" : "사업"}보고서 요약재무 표에 해외 현지법인이 없거나 읽지 못해 제외했습니다.</p>` : ""}<p class="src">중간지주(예: 미래에셋 홍콩법인) 자본에 든 자회사 몫(자회사 자본 × 지분율)은 빼고 한 번만 셉니다${nested.length ? `: ${esc(nested.join(", "))}` : ""}.${consNote.length ? ` ${esc(consNote.join(", "))}는 자회사를 포함한 연결 값으로 실려 그대로 씁니다.` : ""} 지분 구조는 같은 보고서의 종속기업 현황 표·각주에서 자동으로 읽고, 순이익에 섞인 자회사 배당은 공시로 가를 수 없어 그대로 둡니다.</p>`;
  }

  // 국내 증권사 재무(DART 최신 정기보고서, 백만원 → 자산·부채·자본 조원, 손익 억원)
  function firmFinCard() {
    const P = finPeriod();
    const firms = [...finFirms()].sort((a, b) => (b.equity ?? -1) - (a.equity ?? -1));
    const maxEq = Math.max(...firms.map((f) => f.equity || 0), 1);
    const one = (k) => [...new Set(firms.map((f) => f[k]).filter(Boolean))].join("·") || "–";
    const miss = P ? firms.filter((f) => f.equity == null && state.data.dart?.firms?.[f.firm]?.financials).map((f) => SHORT[f.firm] || f.firm) : [];
    return `<div class="card span6"><h3><a href="#global/kr">국내 증권사 재무 현황</a></h3>
      <p class="card__meta">DART 정기보고서(연결) · ROE = ${P ? "그 보고서" : "최근"} 누적 순이익 연환산 ÷ 기말 자본 · 매주 자동 수집${P ? ` · ${esc(P.label)} 보고서 값(손익은 ${P.months}개월 누적)` : ""}</p>
      ${state.data.finHist?.periods?.length ? tmetaSel(perSel("fin", finOpts()), P ? "" : "· 열마다 표시", "조원(자산·부채·자본) · 억원(손익)") : tmeta("열마다 표시", "조원(자산·부채·자본) · 억원(손익)")}<div class="scroll"><table class="mini fin"><thead><tr><th></th><th>증권사</th><th class="num">자산<small class="asof">${esc(one("bs_basis"))}</small></th><th class="num">부채<small class="asof">${esc(one("bs_basis"))}</small></th><th>자본<small class="asof">${esc(one("bs_basis"))}</small></th><th class="num">영업이익<small class="asof">${esc(one("pl_basis"))}</small></th><th class="num">ROE<small class="asof">${esc(one("roe_basis"))}</small></th><th class="num">순이익<small class="asof">${esc(one("ni_basis"))}</small></th><th class="num">해외법인</th></tr></thead><tbody>
      ${firms.map((f, i) => `<tr class="${f.firm === HANWHA ? "is-hw" : ""}"><td class="sub">${f.equity == null ? "–" : i + 1}</td>
        <td><b>${esc(SHORT[f.firm] || f.firm)}</b>${f.firm === HANWHA ? ' <span class="tag tag--hw">당사</span>' : ""}</td>
        <td class="num">${jo(f.assets)}</td><td class="num">${jo(f.liabilities)}</td>
        <td><div class="eq"><div class="bar"><span style="width:${f.equity ? Math.max(2, (f.equity / maxEq) * 100) : 0}%"></span></div><b>${jo(f.equity)}</b></div></td>
        <td class="num ${signCls(f.op_income)}">${eok(f.op_income)}</td>
        <td class="num ${signCls(f.roe)}"><b>${f.roe == null ? "–" : `${fmt(f.roe, 1)}%`}</b></td>
        <td class="num ${signCls(f.ni_latest)}">${eok(f.ni_latest)}</td>
        <td class="num">${state.data.domestic.entities.filter((e) => e.firm === f.firm && counted(e)).length}${f.holdings ? `<small class="sub" title="중간지주회사(법인 수에서 제외)"> +지주${f.holdings}</small>` : ""}</td></tr>`).join("")}
      </tbody></table></div>${miss.length ? `<p class="src">${esc(miss.join("·"))}: ${esc(P.label)} 보고서 주요계정이 아직 DART에 없습니다(제출 전이거나 기한 전).</p>` : ""}${P ? '<p class="src">해외법인 수는 기간과 관계없이 현재(최근 사업보고서) 기준입니다.</p>' : ""}${worldMapBlock()}
      <div class="duo"><div><h4 class="mx__h"><a href="#domestic/detail">증권사별 해외 현지법인 수</a> <span>운영 중</span></h4>${outboundRank({ mini: true })}</div>
        <div><h4 class="mx__h"><a href="#domestic/detail">해외법인 순이익 합계</a> <span>억원 · ${esc(pnlBasis())}</span></h4>
        ${rankTable(firmPnl(state.data.domestic.entities.filter(counted)).map((r) => ({ ...r, name: SHORT[r.name] || r.name })), { unit: "억원", digits: 0, mini: true, basis: pnlBasis(), hw: (r) => r.name === SHORT[HANWHA] })}
        <p class="src">타법인출자현황 · 직접 출자 해외법인 전체(100%) 순이익 · 한화 탭(4사 종속기업 요약재무정보)과 기준 다름</p></div></div></div>`;
  }

  // ---------- 진출 지도: 나라별 진출 국내 증권사 수. 지도 경로는 data/global/worldmap.json(Natural Earth 110m, 저장소에 포함) ----------
  // 나라 이름 → [ISO 숫자 코드, 표시 경도, 위도]. 홍콩·싱가포르는 110m 지도에 영역이 없어 점만 찍는다
  const GEO = {
    미국: ["840", -98, 39], 브라질: ["076", -51, -11], 영국: ["826", -2, 54], 그리스: ["300", 22, 39], 인도: ["356", 78, 22],
    몽골: ["496", 103, 47], 중국: ["156", 106, 34], 홍콩: ["344", 114.2, 22.3], 일본: ["392", 139, 37], 베트남: ["704", 106, 15],
    싱가포르: ["702", 103.8, 1.35], 인도네시아: ["360", 114, -2], 태국: ["764", 101, 15], 캄보디아: ["116", 105, 12.5],
    아랍에미리트: ["784", 54, 24], 카자흐스탄: ["398", 67, 48], 호주: ["036", 134, -25], 독일: ["276", 10, 51], 프랑스: ["250", 2, 47], 캐나다: ["124", -100, 56],
  };

  function presence() {
    const d = state.data.domestic;
    const by = {};
    const add = (c, firm, k, n) => {
      const x = (by[c] = by[c] || { firms: new Set(), corp: 0, off: 0 });
      x.firms.add(firm);
      x[k] += n;
    };
    d.entities.filter(counted).forEach((e) => add(e.country, e.firm, "corp", 1));
    d.offices.forEach((o) => add(o.country, o.firm, "off", o.count));
    return by;
  }

  function worldMapBlock() {
    return `<h4 class="mx__h" style="margin-top:10px">진출 지도 <span>나라별 진출 국내 증권사 수(현지법인·사무소)</span></h4>
      ${tmeta(`${netBasis()} · 사무소 수동`, "개사")}<div class="wmap" id="ov-map"></div><p class="wmap__cap sub" id="ov-map-cap">숫자에 마우스를 올리면 오른쪽 진출 현황 표의 해당 나라가 표시됩니다.</p>`;
  }

  function renderWorldMap(el, matrixEl) {
    const wm = state.data.worldmap;
    if (!el) return;
    if (!wm) { el.innerHTML = '<div class="empty-state">지도 데이터를 불러오지 못했습니다.</div>'; return; }
    const by = presence();
    const pt = (lon, lat) => [(lon - wm.lon0) * wm.k, (wm.lat0 - lat) * wm.k];
    const here = Object.entries(by).filter(([c]) => GEO[c]);
    const ids = new Map(here.map(([c, x]) => [GEO[c][0], [c, x]]));
    const maxN = Math.max(1, ...here.map(([, x]) => x.firms.size));
    const shapes = Object.entries(wm.countries).map(([id, dd]) => {
      const hit = ids.get(id);
      return hit ? `<path class="wm__land is-in" data-c="${esc(hit[0])}" style="--o:${(0.35 + 0.55 * (hit[1].firms.size / maxN)).toFixed(2)}" d="${dd}"/>`
        : `<path class="wm__land${id === "410" ? " is-home" : ""}" d="${dd}"/>`;
    }).join("");
    const dots = here.sort((a, b) => a[1].firms.size - b[1].firms.size).map(([c, x]) => {
      const [, lon, lat] = GEO[c];
      const [cx, cy] = pt(lon, lat);
      const r = 8 + x.firms.size * 0.9;
      const names = FIRM_ORDER.filter((f) => x.firms.has(f)).map((f) => SHORT[f] || f).join("·");
      return `<g class="wm__dot" data-c="${esc(c)}" tabindex="0"><title>${esc(c)} · ${x.firms.size}개사(${esc(names)}) · 현지법인 ${x.corp} · 사무소 ${x.off}</title>
        <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}"/><text x="${cx.toFixed(1)}" y="${(cy + 3.6).toFixed(1)}">${x.firms.size}</text></g>`;
    }).join("");
    const [hx, hy] = pt(127.5, 36.5);
    // 진출국이 모인 경도 −130°~150°, 위도 72°N~40°S만 보여 준다
    const [x0, y0] = pt(-130, 72), [x1, y1] = pt(152, -40);
    el.innerHTML = `<svg viewBox="${x0.toFixed(0)} ${y0.toFixed(0)} ${(x1 - x0).toFixed(0)} ${(y1 - y0).toFixed(0)}" role="img" aria-label="국내 증권사 해외 진출 지도">
      <g>${shapes}</g><circle class="wm__home" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="3.2"/>${dots}</svg>`;
    const cap = $("#ov-map-cap");
    const capDefault = cap?.innerHTML;
    const glow = (c, on) => {
      el.querySelectorAll(`[data-c="${CSS.escape(c)}"]`).forEach((n) => n.classList.toggle("is-on", on));
      matrixEl?.querySelectorAll(`tr[data-c="${CSS.escape(c)}"]`).forEach((tr) => tr.classList.toggle("is-glow", on));
      matrixEl?.querySelectorAll("table.matrix").forEach((t) => t.classList.toggle("has-glow", on && !!t.querySelector(`tr[data-c="${CSS.escape(c)}"]`)));
      if (cap) {
        const x = by[c];
        cap.innerHTML = on && x ? `<b>${esc(c)}</b> 국내 증권사 ${x.firms.size}곳 · ${esc(FIRM_ORDER.filter((f) => x.firms.has(f)).map((f) => SHORT[f] || f).join(" · "))} · 현지법인 ${x.corp}개 · 사무소 ${x.off}곳` : capDefault;
      }
    };
    const bind = (root, sel) => {
      root.addEventListener("mouseover", (ev) => { const g = ev.target.closest(sel); if (g) glow(g.dataset.c, true); });
      root.addEventListener("mouseout", (ev) => { const g = ev.target.closest(sel); if (g && !g.contains(ev.relatedTarget)) glow(g.dataset.c, false); });
      root.addEventListener("focusin", (ev) => { const g = ev.target.closest(sel); if (g) glow(g.dataset.c, true); });
      root.addEventListener("focusout", (ev) => { const g = ev.target.closest(sel); if (g) glow(g.dataset.c, false); });
    };
    bind(el, "[data-c]");
    // 반대로 표의 나라 줄에 올려도 지도에 표시
    if (matrixEl) bind(matrixEl, "tr[data-c]");
  }

  // 전 사 같은 기준(최근 사업보고서 타법인출자현황)인 법인만 합산한다
  const pnlBasis = () => basisShort(state.data.domestic.entities.find((e) => e.fresh)?.basis || "");
  function firmPnl(corps) {
    return FIRM_ORDER.map((f) => {
      const mine = corps.filter((e) => e.firm === f && e.fresh && e.net_income != null);
      return { name: f, value: mine.length ? mine.reduce((s, e) => s + e.net_income, 0) / 100 : null, note: `${mine.length}개 법인` };
    }).filter((r) => r.value != null).sort((a, b) => b.value - a.value);
  }

  // 당사 진출국마다 한국계 경쟁사와 현지 순위를 한 표로
  function arenaCard(hw, corps) {
    const mine = corps.filter((e) => e.firm === HANWHA);
    const countries = [...new Set(mine.map((e) => e.country))];
    // 한화 탭 공시값의 법인명과 종속회사 목록의 법인명은 '(주1)'·마침표 등 표기만 달라 영문자·숫자만 맞춘다
    const hp = hwPublic(hw);
    const plFor = (e) => hp?.ents.find((x) => hwKey(x.name) === hwKey(e.name) || hwKey(hp.latest.subs[x.key]?.name) === hwKey(e.name));
    const rows = countries.map((c) => {
      const peers = corps.filter((e) => e.country === c && e.firm !== HANWHA);
      const peerFirms = FIRM_ORDER.filter((f) => peers.some((e) => e.firm === f));
      const m = state.data.markets.markets.find((x) => x.country === c);
      const t = m?.tables?.[0];
      const ks = t ? t.rows.map((r, i) => [r, i + 1]).filter(([r]) => r.korean) : [];
      const myEnts = mine.filter((e) => e.country === c);
      const myNi = myEnts.map(plFor).filter(Boolean);
      const peerNi = peers.filter((e) => e.fresh && e.net_income != null);
      return `<tr><td><b>${esc(c)}</b>${m ? ` <a class="sub" href="#global/${esc(m.id)}">순위</a>` : ""}</td>
        <td>${myEnts.map((e) => esc(plFor(e)?.label || e.name)).join(", ")}${myNi.length ? `<div class="sub">${esc(hp.latest.label)} 순이익 ${myNi.map((e) => `${eok(hp.latest.subs[e.key]?.ni)}억`).join(" / ")}</div>` : ""}</td>
        <td class="num">${peers.length}</td>
        <td>${peerFirms.map((f) => esc(SHORT[f])).join(" · ") || "–"}${peerNi.length ? `<div class="sub">한국계 평균 순이익 ${eok(peerNi.reduce((s, e) => s + e.net_income, 0) / peerNi.length)}억(${esc(pnlBasis())})</div>` : ""}</td>
        <td>${ks.length ? ks.map(([r, i]) => `${esc(SHORT[r.korean] || r.korean)} ${i}위`).join(", ") : '<span class="sub">공개 상위권에 한국계 없음</span>'}${t ? `<div class="sub">${esc(t.title)}</div>` : ""}</td></tr>`;
    });
    return `<div class="card span12"><h3><a href="#domestic/detail">당사 진출국 경쟁 지도</a></h3><p class="card__meta">당사 현지법인이 있는 나라의 한국계 경쟁사와 현지 순위</p>
      ${tmeta(`${netBasis()} · 순이익 ${pnlBasis()}${hp ? ` · 당사 ${hwBasis(hp.latest)}` : ""}`, "개 · 억원")}<div class="scroll"><table class="mini"><thead><tr><th>국가</th><th>당사 법인</th><th class="num">한국계 법인</th><th>진출 경쟁사</th><th>현지 순위 속 한국계</th></tr></thead><tbody>${rows.join("")}</tbody></table></div></div>`;
  }

  function renderOverview() {
    const d = state.data.domestic;
    const hw = state.data.hanwha;
    const corps = d.entities.filter(counted);
    const offices = d.offices.reduce((s, o) => s + o.count, 0);
    const countries = new Set([...corps.map((e) => e.country), ...d.offices.map((o) => o.country)]);
    const eqRank = [...d.firms].filter((f) => f.equity != null).sort((a, b) => b.equity - a.equity);
    const myRank = eqRank.findIndex((f) => f.firm === HANWHA) + 1;
    const br = brokerRank();
    const mine = corps.filter((e) => e.firm === HANWHA);
    const hp = hwPublic(hw);
    const ht = hp ? hp.total(hp.latest) : null;
    const next = (hw.reg?.todo || []).filter((t) => t.status !== "done" && t.due && t.law !== "내부").sort((a, b) => a.due.localeCompare(b.due))[0];
    const kpi = (l, v, n, cls = "", unit = "") => `<div class="kpi ${cls}"><div class="kpi__label">${l}</div><div class="kpi__value">${v}${unit ? `<small>${unit}</small>` : ""}</div><div class="kpi__note" title="${esc(n)}">${esc(n)}</div></div>`;
    $("#ov-kpis").innerHTML = [
      kpi('<abbr title="' + esc(TIPS["해외 현지법인"]) + '">국내사 해외 현지법인</abbr>', fmt(corps.length), `${new Set(corps.map((e) => e.firm)).size}개 증권사`, "", "개"),
      kpi("진출 국가", fmt(countries.size), `사무소 ${offices}개 포함`, "", "개국"),
      kpi('<abbr title="' + esc(TIPS["변동 감지"]) + '">DART 신규 해외법인</abbr>', fmt(d.changes.length), d.changes.length ? `${changeNote(d.changes)} · ${[...new Set(d.changes.map((c) => SHORT[c.firm]))].join("·")}` : "변동 없음", "", "건"),
      kpi("최근 해외·출자 공시", fmt(state.data.dart?.feed?.length ?? 0), "최근 120일 DART", "", "건"),
      br ? kpi(`<abbr title="${esc(`DART 정기보고서를 낸 국내 증권사 ${br.rows.length}곳의 별도 자본총계 순위(연결 기준 ${br.cfs}위). 매주 월요일 자동 계산, 전체 표는 글로벌 › 한국`)}">당사 자기자본 순위</abbr>`, fmt(br.rank),
          `${br.rows.length}곳 중 · 대형사 ${eqRank.length}곳 중 ${myRank}위 · ${br.short} 별도`, "kpi--hw", "위")
        : kpi("당사 자기자본 순위", myRank ? fmt(myRank) : "–", `${eqRank.length}개사 중 · ${eqRank[myRank - 1]?.basis || ""}`, "kpi--hw", "위"),
      kpi("당사 해외 현지법인", fmt(mine.length), `${new Set(mine.map((e) => e.country)).size}개국 · 사무소 ${d.offices.filter((o) => o.firm === HANWHA).reduce((s, o) => s + o.count, 0)}`, "kpi--hw", "개"),
      kpi(`당사 해외자회사 ${hp ? esc(hp.latest.label) : ""} 순이익${ht?.own != null ? "(지배지분)" : ""}`, ht ? eok(ht.own ?? ht.ni) : "–",
        hp ? `${hp.ents.length}사 · DART ${hp.latest.report?.name || hp.latest.label}${ht.own != null ? ` · 100% 기준 ${eok(ht.ni)}억` : ""}` : "준비 중", "kpi--hw", "억원"),
      next ? kpi("다음 대외보고", `D-${dday(next.due)}`, `${next.entity} ${next.item}`, "kpi--hw")
        : kpi("당사 해외자회사 ROE", ht?.roe == null ? "–" : fmt(ht.roe, 1), hp ? `${hp.latest.label} 연환산 · 4사 자본 가중 · DART` : "", "kpi--hw", "%"),
    ].join("");

    const markets = state.data.markets.markets.filter((m) => m.auto !== "dart");
    const pts = insights(hw, corps);
    $("#overview-view").innerHTML = `<div class="ov">
      <div class="ov__label ov__label--first"><h2>국내 증권사 글로벌 네트워크</h2><span>FY2025 사업보고서 종속회사 목록 · 금융업 영업법인(손자회사 포함) · 지주·펀드·SPV 제외</span>
        <button type="button" class="print-btn" id="ov-print" title="한눈에 보기를 A4 가로로 인쇄(1~2쪽)">인쇄</button></div>
      ${firmFinCard()}
      <div class="card span6"><h3><a href="#domestic/matrix">국가별 진출 현황 (현지법인 · 사무소)</a></h3><p class="card__meta">칸을 누르면 해당 법인 목록으로 이동</p><div id="ov-matrix"></div>${roeBlock()}</div>
      ${arenaCard(hw, corps)}

      <div class="ov__label"><h2>이번 주 동향</h2><span>국내 증권사 해외진출 뉴스와 국가별 매크로 · 매일 자동 수집</span></div>
      ${newsCard(14)}
      <div class="card span8 insight"><h3>이번 주 핵심 포인트</h3><p class="card__meta">공시·순위·매크로 데이터에서 규칙으로 자동 작성(LLM 없음) · 정책금리 BIS, 지수 Yahoo, 환율 한국은행, 금리 결정 일정은 각 중앙은행, 헤드라인은 주요 매체 RSS · 매일 자동 갱신</p>
        <ol>${pts.map((t) => `<li>${t}</li>`).join("")}</ol></div>

      <div class="ov__label"><h2>한화투자증권</h2><span>당사 해외자회사 실적과 대외보고 일정</span></div>
      ${hanwhaCard(hw)}${todoCard(hw)}

      <div class="ov__label"><h2>권역별 증권사 순위</h2><span>미국은 SEC, 그 밖의 시장은 거래소·언론 발표 기준</span></div>
      <div class="span12"><div class="mkts mkts--3">${markets.map((m) => marketCard(m, 5)).join("")}</div></div>

      <div class="ov__label"><h2>규제·공시 동향</h2><span>주요국 디지털자산 규제와 DART 해외·출자 공시, 매주 자동 수집</span></div>
      ${digitalCard(state.data.digital)}
      <div class="span7">${feedCard(10, true)}</div>
    </div>`;
    renderMatrix($("#ov-matrix"), { mini: true, limit: 12 });
    renderWorldMap($("#ov-map"), $("#ov-matrix"));
    $("#ov-print")?.addEventListener("click", () => window.print());
    // 인쇄 대상 표시: 1쪽 = 지표·네트워크(재무·지도·진출 현황), 2쪽 = 뉴스·핵심 포인트·한화
    const labels = [...document.querySelectorAll("#overview-view .ov__label")];
    const mark = (label, n, page, withLabel) => {
      if (!label) return;
      if (withLabel) label.dataset.pp = page;
      let el = label.nextElementSibling;
      for (let i = 0; i < n && el; i++, el = el.nextElementSibling) el.dataset.pp = page;
    };
    mark(labels[0], 2, "1", true);
    mark(labels[1], 2, "2", false);
    mark(labels[2], 2, "2", true);
  }

  // ---------- 인쇄: 한눈에 보기를 A4 가로 2쪽으로. 쪽마다 내용을 복제해 한 쪽에 맞게 축소한다 ----------
  const PAGE_W = 1062, PAGE_H = 718; // A4 가로(297×210mm)에서 여백 8mm를 뺀 CSS px(96dpi), 머리글 몫 약간 제외
  function buildPrint() {
    document.getElementById("print-root")?.remove();
    if ($("#section-overview").hidden) return;
    const root = document.createElement("div");
    root.id = "print-root";
    const stamp = $("#updated")?.textContent || "";
    const pages = [["1", [$("#ov-kpis")]], ["2", []]];
    pages.forEach(([n, extra]) => {
      const pg = document.createElement("section");
      pg.className = "pp";
      pg.innerHTML = `<div class="pp__head"><b>글로벌네트워크팀 Weekly Dashboard · 한눈에 보기</b><span>${esc(stamp)} · ${n}/2</span></div><div class="pp__body"><div class="ov"></div></div>`;
      const grid = $(".ov", pg);
      extra.forEach((el) => el && $(".pp__body", pg).insertBefore(el.cloneNode(true), grid));
      document.querySelectorAll(`#overview-view [data-pp="${n}"]`).forEach((el) => grid.appendChild(el.cloneNode(true)));
      root.appendChild(pg);
    });
    root.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
    document.body.appendChild(root);
    // 화면 폭 1400px 기준으로 배치한 뒤, 쪽 크기에 맞게 줄인다
    root.querySelectorAll(".pp__body").forEach((b) => {
      const z = Math.min(PAGE_W / b.scrollWidth, (PAGE_H - 22) / b.scrollHeight, 1);
      b.style.zoom = z.toFixed(3);
    });
  }
  window.addEventListener("beforeprint", buildPrint);
  window.addEventListener("afterprint", () => document.getElementById("print-root")?.remove());

  // ---------- 한화투자증권(hanwha/), 디지털자산 규제(digital/): 각 폴더의 index.html 을 끼워 넣는다 ----------
  const FRAMES = {
    hanwha: { title: "한화투자증권 글로벌네트워크 현황", desc: "해외자회사 4곳 공시 실적(DART), 해외법인·출자 현황, 필수 대외보고 To-do가 이 탭에 들어옵니다." },
    insight: { title: "전략 인사이트", desc: "진출국 전략 Takeaways, 진출국 스코어카드, 현지 경쟁사 자본·P/B, 시장점유율이 이 탭에 들어옵니다." },
    digital: { title: "디지털자산 규제 요약", desc: "주요국 디지털자산(가상자산·STO·스테이블코인) 규제 현황과 해외법인 전략 시사점이 이 탭에 들어옵니다." },
    workflow: { title: "해외지분투자 Workflow", desc: "국내 증권사의 해외 지분투자 절차 흐름도와 단계별 신고·보고 기한이 이 탭에 들어옵니다." },
    guide: { title: "국가별 해외진출 유의사항", desc: "국가별 외국인 지분 한도·인가·자본금·현지 임원·송금 규제와 한국 측 공통 절차가 이 탭에 들어옵니다." },
  };

  async function renderFrame(key) {
    const el = $(`#${key}-view`);
    if (el.dataset.ready) return;
    el.dataset.ready = "1";
    let ok = false;
    try { ok = (await fetch(`${key}/index.html`, { method: "HEAD", cache: "no-cache" })).ok; } catch (_) { ok = false; }
    el.innerHTML = ok
      ? `<iframe class="frame" src="${key}/index.html" title="${esc(FRAMES[key].title)}"></iframe>`
      : `<div class="section__head"><h2>${esc(FRAMES[key].title)}</h2><p>${esc(FRAMES[key].desc)}</p></div>
         <div class="empty-state">준비 중입니다.</div>`;
    if (ok) {
      const f = $("iframe", el);
      // 탭 안 페이지는 데이터를 load 이후에 그리므로, 내용 크기가 바뀔 때마다 높이를 다시 맞춘다
      f.addEventListener("load", () => {
        try {
          const doc = f.contentDocument;
          const fit = () => { f.style.height = `${doc.documentElement.scrollHeight + 20}px`; };
          fit();
          new ResizeObserver(fit).observe(doc.body);
        } catch (_) { /* 교차 출처 */ }
      });
    }
  }

  // ---------- 시작 ----------
  async function init() {
    try {
      const [config, seed, dart, markets, us, meta, hwSubs, hwEnts, reg, digital, offUpd, news, subFin, listed, worldmap, macroNews, macro, rateCal, cons, subTrend, hubNews, brokerRank, finHist, brokerHist] = await Promise.all([
        getJSON("data/config.json"), getJSON("data/domestic/seed.json"), getJSON("data/domestic/dart_latest.json", true),
        getJSON("data/global/markets.json"), getJSON("data/global/us_sec.json", true), getJSON("data/meta.json", true),
        // 한눈에 보기용: 다른 탭 폴더의 데이터(없으면 빈칸)
        getJSON("hanwha/data/dart_subs.json", true), getJSON("hanwha/data/entities.json", true), getJSON("hanwha/data/regulatory.json", true),
        getJSON("digital/data/summary.json", true), getJSON("data/domestic/offices_update.json", true),
        getJSON("data/domestic/news.json", true), getJSON("data/domestic/sub_fin.json", true), getJSON("data/global/listed.json", true),
        getJSON("data/global/worldmap.json", true), getJSON("data/global/macro_news.json", true),
        getJSON("hanwha/data/markets.json", true), getJSON("hanwha/data/rate_calendar.json", true),
        getJSON("data/domestic/consolidated.json", true), getJSON("data/domestic/sub_trend.json", true), getJSON("data/domestic/hub_news.json", true),
        getJSON("data/domestic/broker_rank.json", true),
        getJSON("data/domestic/fin_hist.json", true), getJSON("data/domestic/broker_rank_hist.json", true),
      ]);
      HANWHA = config.home;
      FIRM_ORDER = config.firms.map((f) => f.name);
      SHORT = Object.fromEntries(config.firms.map((f) => [f.name, f.short]));
      // 사무소: 기준 데이터에 확인된 변동(offices_update.json)을 더한다
      const added = (offUpd?.items || []).filter((x) => x.change === "추가").map((x) => ({ firm: x.firm, country: x.country, count: x.count, extra: x }));
      // 정정: 원자료 사무소의 나라를 회사 공개 자료 기준으로 고친다
      const offices = seed.offices.map((o) => {
        const fix = (offUpd?.items || []).find((x) => x.change === "정정" && x.firm === o.firm && x.from === o.country);
        return fix ? { ...o, country: fix.country, extra: fix } : o;
      });
      const seedAll = { ...seed, offices: [...offices, ...added] };
      const domestic = merge(seedAll, dart, subFin, cons);
      // 사업보고서 기준일 이후 매각·이전(보도 확인분): 태그와 비고만, 법인 수는 공시 기준 유지
      for (const ev of offUpd?.entity_events || []) {
        const e = domestic.entities.find((y) => y.firm === ev.firm && keyName(y.name) === keyName(ev.name));
        if (e) Object.assign(e, { event: ev, note: `${e.note ? `${e.note} · ` : ""}${ev.text}` });
      }
      state.data = { officesUpdate: offUpd, news, subFin, subTrend, hubNews, brokerRank, finHist, brokerHist, listed, worldmap, macroNews, macro, rateCal, domestic, cons, dart, markets, us, hanwha: { subs: hwSubs, entities: hwEnts, reg }, digital };
      // 머리글 시각(KST): 매일 수집(뉴스·한화 시장 지표)과 매주 월요일 DART 수집을 나눠 보인다.
      // SEC 순위는 배포 때마다 다시 받으므로 '공시 수집' 시각에 넣지 않는다.
      const when = (s) => { const t = s ? new Date(String(s).replace(" KST", "+09:00").replace(/^(\d{4}-\d\d-\d\d) /, "$1T")) : null; return t && !isNaN(t) ? t : null; };
      const latest = (...xs) => xs.map(when).filter(Boolean).sort((a, b) => b - a)[0];
      const kst = (t) => { const k = new Date(t.getTime() + 9 * 36e5), p = (n) => String(n).padStart(2, "0"); return `${k.getUTCMonth() + 1}.${p(k.getUTCDate())} ${p(k.getUTCHours())}:${p(k.getUTCMinutes())}`; };
      const daily = latest(news?.updated_at, hubNews?.updated_at, macroNews?.updated_at, macro?.updated);
      const weekly = latest(dart?.updated_at), built = latest(meta?.built_at);
      $("#updated").textContent = [daily && `매일 수집 ${kst(daily)}`, weekly ? `DART 공시 ${kst(weekly)}(매주 월)` : "DART 공시 수집 전",
        built && `페이지 갱신 ${kst(built)}`].filter(Boolean).join(" · ");
    } catch (e) {
      $("#app").innerHTML = `<div class="empty-state">데이터를 불러오지 못했습니다: ${esc(e.message)}</div>`;
      return;
    }
    document.addEventListener("click", (ev) => {
      const a = ev.target.closest("a.jump");
      if (a) Object.assign(state.filters, { firm: "", country: a.dataset.country, relation: "", q: "" });
    });
    // 표의 기간 드롭다운: 고른 값을 기억하고 지금 화면을 다시 그린다(스크롤 위치 유지)
    document.addEventListener("change", (ev) => {
      const sel = ev.target.closest("select.psel");
      if (!sel) return;
      state.per[sel.dataset.per] = sel.value;
      const y = window.scrollY;
      route();
      window.scrollTo(0, y);
      document.querySelector(`select.psel[data-per="${sel.dataset.per}"]`)?.focus({ preventScroll: true });
    });
    window.addEventListener("hashchange", route);
    if (!location.hash) {
      let last = null;
      try { last = localStorage.getItem("gnd:last"); } catch (_) { /* 무시 */ }
      history.replaceState(null, "", last || "#overview");
    }
    route();
  }

  init();
})();
