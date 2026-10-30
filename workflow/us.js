// 미국 진출(브로커-딜러 설립과 인수). data/us_entry.json(사람이 원문을 읽고 쓴 요건·사례)에 자동 수집 데이터를 붙여 그린다.
// - 국내 증권사 미국 거점: ../data/domestic/consolidated.json(DART 종속회사 목록) + sub_fin.json(종속기업 요약재무정보), 국내 탭과 같은 집계 규칙
// - 미국 상장 브로커리지: ../insight/data/valuation.json(markets.us, 있으면) → 없으면 ../data/global/us_sec.json(SEC XBRL)
// - 원문 점검: ../guide/data/source_status.json(반기 점검 결과, 출처 URL별)
// - Velocity Clearing(한화생명 75%): data/velocity.json(workflow/scripts/fetch_velocity.py 매일 수집: BrokerCheck·EDGAR·SEC XBRL·뉴스)
// 대시보드에서는 #workflow/us 로 들어온다. 해외지분투자 절차(index.html)와 같은 iframe 안에서 오간다.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const host = (u) => { try { return new URL(u, location.href).hostname.replace(/^www\./, ""); } catch (_) { return ""; } };
  const fmt = (d) => (d || "").replace(/-/g, ".");
  const tmeta = (basis, unit) => `${basis ? `<span>기준 ${esc(basis)}</span>` : ""}${unit ? `<span>단위: ${esc(unit)}</span>` : ""}`;
  const num = (v, d = 0) => {
    if (v == null || Number.isNaN(v)) return "—";
    const r = Math.round(v * 10 ** d) / 10 ** d;
    return (r === 0 ? 0 : r).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  const sign = (v, d = 0) => (v == null ? "—" : `<span class="${Math.round(v * 10 ** d) < 0 ? "neg" : ""}">${num(v, d)}</span>`);
  const chipS = { "+": '<span class="chip s-p">+</span>', "-": '<span class="chip s-m">−</span>', "=": '<span class="chip s-e">=</span>' };
  let U, W, ST, REF = {};

  const frame = () => { try { return window.frameElement; } catch (_) { return null; } };
  // 출처 번호 [n]: 누르면 아래 출처 목록으로
  const refs = (ids) => (ids && ids.length
    ? `<sup class="r">${ids.filter((id) => REF[id]).map((id) => `<a href="#src-${id}" data-go="src-${id}" title="${esc(U.sources[id].t)}">[${REF[id]}]</a>`).join("")}</sup>` : "");
  const step = (id) => W?.steps.find((s) => s.id === id);
  const stepNo = (id) => (W ? W.steps.findIndex((s) => s.id === id) + 1 : 0);
  const wfChip = (id) => {
    const s = step(id);
    return `<a class="chip wf" href="index.html#${id}" data-wf="${id}" title="${esc(s ? `${s.title} · ${s.when}` : "해외지분투자 절차")}">WF ${stepNo(id) || ""}${s?.due ? ` · ${esc(s.due)}` : ""}</a>`;
  };

  // ---------- 고정 내용(us_entry.json) ----------
  function renderKpis() {
    $("#kpis").innerHTML = U.kpis.map((k) => `<div class="kpi"><b>${esc(k.v)}</b><span>${esc(k.t)}${refs(k.src)}</span><small>${esc(k.d)}</small></div>`).join("");
  }

  function renderCompare() {
    const P = U.pros_cons;
    $("#cmp").innerHTML = `<colgroup><col style="width:110px"><col><col></colgroup>
      <thead><tr><th>구분</th><th>${esc(P.est.name)}</th><th>${esc(P.acq.name)}</th></tr></thead>
      <tbody>${U.compare.map((r) => r.both
        ? `<tr><td class="k">${esc(r.k)}</td><td colspan="2">${esc(r.both.t)} ${(r.both.wf || []).map(wfChip).join("")}</td></tr>`
        : `<tr><td class="k">${esc(r.k)}</td>${["est", "acq"].map((x) => `<td>${chipS[r[x].s] || ""}${esc(r[x].t)}${refs(r[x].src)}</td>`).join("")}</tr>`).join("")}</tbody>`;
    $("#pc").innerHTML = ["est", "acq"].map((x) => `<div><h4>${esc(P[x].name)}</h4>
      <ul>${P[x].pros.map((t) => `<li class="p">${esc(t)}</li>`).join("")}${P[x].cons.map((t) => `<li class="m">${esc(t)}</li>`).join("")}</ul>
      <p class="fit"><b>적합한 경우</b> · ${esc(P[x].fit)}</p></div>`).join("");
  }

  function renderTimeline() {
    const T = U.timeline;
    const item = (it) => `<li>${esc(it.t)}${it.rule ? ` <span class="chip rule">${esc(it.rule)}</span>` : ""}${it.wf ? ` ${wfChip(it.wf)}` : ""}${refs(it.src)}</li>`;
    const cell = (p) => `<div><span class="w">${esc(p.p)} · ${esc(p.w)}</span><ul>${p.items.map(item).join("")}</ul></div>`;
    let h = `<div class="h"></div><div class="h">${esc(T.est.name)}<small>${esc(T.est.span)}</small></div><div class="h">${esc(T.acq.name)}<small>${esc(T.acq.span)}</small></div>`;
    T.est.phases.forEach((p, i) => {
      h += `<div class="ph">${i + 1}단계<small>${esc(p.p)} / ${esc(T.acq.phases[i]?.p || "")}</small></div>${cell(p)}${T.acq.phases[i] ? cell(T.acq.phases[i]) : "<div></div>"}`;
    });
    $("#tl").innerHTML = h;
  }

  function renderModels() {
    const M = U.models;
    $("#cap").innerHTML = `<thead><tr><th>업무 범위</th><th>내용</th><th class="n">최소 순자본</th><th>조항${refs(["c15c31"])}</th><th>FINOP${refs(["f1220"])}</th></tr></thead>
      <tbody>${M.rows.map((r) => `<tr><td class="k">${esc(r.m)}</td><td>${esc(r.d)}</td><td class="n"><b>${esc(r.cap)}</b></td><td style="white-space:nowrap">${esc(r.p)}</td><td>${esc(r.finop)}</td></tr>`).join("")}</tbody>`;
    $("#capNotes").innerHTML = M.notes.map((n) => `<li>${esc(n.t)}${refs(n.src)}</li>`).join("");
    $("#stages").innerHTML = M.stages.map((s) => `<div class="stg"><b>${esc(s.n)}. ${esc(s.t)}</b><span class="chip rule">${esc(s.r)}</span>${refs(s.src)}<p>${esc(s.d)}</p></div>`).join("");
    $("#stageNote").textContent = M.stage_note;
  }

  function renderPeople() {
    const P = U.people;
    $("#ppl").innerHTML = `<thead><tr><th>역할</th><th class="n">인원</th><th>자격</th><th>비고</th></tr></thead>
      <tbody>${P.rows.map((r) => `<tr><td class="k">${esc(r.r)}</td><td class="n">${esc(r.n)}</td><td>${esc(r.x)}</td><td>${esc(r.note)}${refs(r.src)}</td></tr>`).join("")}</tbody>`;
    $("#ex").innerHTML = `<thead><tr>${P.exams.map((e) => `<th class="n">${esc(e.x)}</th>`).join("")}</tr></thead>
      <tbody><tr>${P.exams.map((e) => `<td class="n">${e.q}문항<br><small>${esc(e.time)}</small></td>`).join("")}</tr></tbody>`;
    $("#pplNotes").innerHTML = P.notes.map((n) => `<li>${esc(n.t)}${refs(n.src)}</li>`).join("");
  }

  function renderNma() {
    const N = U.nma;
    $("#std").innerHTML = N.standards.map((t) => `<li>${esc(t)}</li>`).join("");
    $("#docs").innerHTML = N.docs.map((t) => `<li>${esc(t)}</li>`).join("");
    $("#docsRef").innerHTML = `Rule 1013(a)${refs(N.docs_src)}`;
    $("#itv").innerHTML = `${esc(N.interview)}${refs(["f1013"])}`;
    $("#h-nma small").innerHTML = `Rule 1014(a)${refs(N.standards_src)}`;
  }

  function renderSetup() {
    $("#setup").innerHTML = `<thead><tr><th>단계</th><th>근거</th><th>내용</th></tr></thead>
      <tbody>${U.setup.map((r) => `<tr><td class="k">${esc(r.s)}</td><td><span class="chip rule">${esc(r.rule)}</span></td><td>${esc(r.t)}${refs(r.src)}</td></tr>`).join("")}</tbody>`;
  }

  function renderDeals() {
    $("#deal").innerHTML = `<thead><tr><th>발표</th><th>인수자 → 대상</th><th class="n">규모</th><th>조건</th><th>성격</th></tr></thead>
      <tbody>${U.deals.map((d) => `<tr><td style="white-space:nowrap">${fmt(d.date)}</td><td><b>${esc(d.buyer)}</b> → ${esc(d.target)}</td><td class="n">${esc(d.size)}</td><td>${esc(d.terms)}${refs(d.src)}</td><td>${esc(d.kind)}</td></tr>`).join("")}</tbody>`;
    $("#dealNote").textContent = U.deals_note;
  }

  function renderWf() {
    if (!W) { $("#wfl").innerHTML = '<p class="empty">해외지분투자 절차 데이터를 불러오지 못했습니다.</p>'; return; }
    $("#wfl").innerHTML = U.wf_steps.map(step).filter(Boolean).map((s) =>
      `<a href="index.html#${s.id}" data-wf="${s.id}"><b>${esc(s.due || s.when)}</b><span>${stepNo(s.id)}. ${esc(s.title)}</span></a>`).join("");
  }

  // 출처: 반기 원문 점검(source_status.json)의 출처별 점검일·개정 감지를 붙인다
  function srcState(u) { return ST?.sources?.[u] || null; }
  // 점검 실패 사유: 404는 주소 문제, 403·429·503·봇 확인은 사이트가 자동 접속을 막은 경우, 인증서, 그 밖은 일시 오류
  const failNote = (err) => (/^HTTP (404|410)/.test(err) ? "주소 확인 필요(404)"
    : /^HTTP (403|429|503)|봇 확인/.test(err) ? "사이트가 자동 접속을 막음"
    : /CERTIFICATE|SSL/.test(err) ? "사이트 보안 인증서 오류" : "일시 오류");
  const unchecked = (st) => !!st?.err && !st.checked;  // 한 번도 자동 점검이 안 된 출처
  function renderSources() {
    const ids = Object.keys(U.sources);
    $("#src").innerHTML = ids.map((id) => {
      const s = U.sources[id], st = srcState(s.u);
      const rev = st?.changed_at && st.changed_at > U.meta.verified_at;
      const chk = st?.checked ? ` · ${st.kind === "원문" ? "원문 점검" : "링크 확인"} ${fmt(st.checked)}${st.err ? ` · 최근 점검 실패(${failNote(st.err)})` : ""}`
        : unchecked(st) ? ` · 자동 점검 안 됨(${failNote(st.err)})` : "";
      return `<li id="src-${id}"><a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a> <small>${esc(s.d)} · ${esc(host(s.u))}${chk}</small>${rev ? ` <span class="rev">● 개정 감지·검토 필요(${fmt(st.changed_at)})</span>` : ""}</li>`;
    }).join("");
  }

  // ---------- 국내 증권사 미국 거점(DART 자동) ----------
  // 국내 탭 merge()와 같은 규칙: 종속회사 목록의 금융업 영업법인만 법인 수에, 중간지주는 표시만. 재무는 같은 사업보고서의 종속기업 요약재무정보.
  // keyName 은 site/assets/app.js·scripts/fetch_consolidated.py 의 정규화와 같다
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

  function usFootprint(cfg, cons, sf, upd) {
    const order = (cfg?.firms || []).map((f) => f.name);
    const short = Object.fromEntries((cfg?.firms || []).map((f) => [f.name, f.short || f.name]));
    const rows = [];
    for (const [firm, c] of Object.entries(cons?.firms || {})) {
      const subs = sf?.firms?.[firm]?.subs || {};
      const rep = String(sf?.firms?.[firm]?.report || c.report || "");
      for (const x of c.overseas || []) {
        if (x.country !== "미국" || !["영업법인", "지주회사"].includes(x.class)) continue;
        const k = keyName(x.name);
        const fin = Object.entries(subs).find(([nm, v]) => (x.seed_name && v.seed_name === x.seed_name) || keyName(nm) === k)?.[1] || null;
        const ev = (upd?.entity_events || []).find((e) => e.firm === firm && keyName(e.name) === k);
        rows.push({ firm, short: short[firm] || firm, name: x.name, business: x.business, holding: x.class === "지주회사",
          equity: fin?.equity ?? null, ni: fin?.ni ?? null, own: fin?.own ?? null, consolidated: !!fin?.consolidated, rep, ev });
      }
    }
    // 자회사 포함 연결 값으로만 나오는 법인(토스 등): 같은 회사 중간지주 행에 들어 있다고 적는다
    for (const r of rows) r.inHolding = r.equity == null && !r.holding && rows.some((h) => h.firm === r.firm && h.holding && h.consolidated);
    const offices = (upd?.items || []).filter((x) => x.country === "미국" && x.change === "추가");
    rows.sort((a, b) => (a.holding - b.holding) || ((b.equity ?? -1e15) - (a.equity ?? -1e15)) || order.indexOf(a.firm) - order.indexOf(b.firm));
    return { rows, offices };
  }

  function renderKr(cfg, cons, sf, upd) {
    if (!cons?.firms) { $("#kr").innerHTML = '<p class="empty">국내 탭 데이터를 불러오지 못했습니다. <a href="../#domestic/detail" target="_top">국내 › 해외법인 상세</a>에서 미국을 고르면 같은 목록을 볼 수 있습니다.</p>'; return; }
    const { rows, offices } = usFootprint(cfg, cons, sf, upd);
    const ops = rows.filter((r) => !r.holding);
    const reps = [...new Set(rows.map((r) => r.rep).filter(Boolean))];
    const roe = (r) => (r.ni != null && r.equity > 0 ? (r.ni / r.equity) * 100 : null);
    // 단위: 원자료 백만원 → 억원
    const eok = (v) => (v == null ? null : v / 100);
    $("#tm-kr").innerHTML = tmeta(`${reps.map((r) => r.replace(/^(\d{4}) /, "FY$1 ")).join("·")} 종속기업 요약재무정보(법인별 별도)`, "억원 · %");
    $("#kr").innerHTML = `<p class="small" style="margin:0 0 4px">현지법인 <b>${ops.length}개</b>(${new Set(ops.map((r) => r.firm)).size}개사) · 중간지주 ${rows.length - ops.length}개(법인 수 제외)${offices.length ? ` · 사무소 ${offices.length}개` : ""}</p>
      <table><thead><tr><th>증권사</th><th>법인</th><th>업종(DART)</th><th class="n">자본</th><th class="n">순이익</th><th class="n">ROE</th><th>비고</th></tr></thead>
      <tbody>${rows.map((r) => `<tr${r.holding ? ' style="color:var(--muted)"' : ""}><td class="k">${esc(r.short)}</td><td>${esc(r.name.replace(/\(\*\)$/, ""))}${r.holding ? '<span class="tag">중간지주</span>' : ""}</td><td>${esc(r.business || "—")}</td>
        <td class="n">${sign(eok(r.equity))}</td><td class="n">${sign(eok(r.ni))}</td><td class="n">${r.holding ? "—" : sign(roe(r), 1)}</td>
        <td>${[r.own != null && r.own < 100 ? `지분 ${num(r.own, 1)}%` : "", r.consolidated ? "자회사 포함 연결 값" : "", r.inHolding ? "재무는 중간지주 연결 값에 포함" : "", r.ev ? `<a href="${esc(r.ev.url)}" target="_blank" rel="noopener" title="${esc(r.ev.text)}">${esc(r.ev.tag)}</a>` : ""].filter(Boolean).join(" · ") || ""}</td></tr>`).join("")}
      ${offices.map((o) => `<tr><td class="k">${esc(o.firm.replace(/증권$|투자증권$/, ""))}</td><td colspan="5">${esc(o.name)}<span class="tag">사무소</span></td><td><a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.source)}</a></td></tr>`).join("")}</tbody></table>
      <p class="small">ROE = 순이익 ÷ 기말 자본(같은 사업보고서). 중간지주 행은 자회사 지분이 자본에 들어 있어 합산하지 않습니다. 목록 기준은 <a href="../#domestic/detail" target="_top">국내 › 해외법인 상세</a>와 같습니다.</p>`;
  }

  // ---------- 미국 상장 브로커리지 ----------
  function renderComps(val, sec) {
    const V = val?.markets?.us;
    if (V?.rows?.length) {
      $("#compSrc").textContent = "Yahoo Finance 시세·재무 · 평일 자동";
      $("#tm-comp").innerHTML = tmeta(`시세 ${fmt(V.price_date)} · 자본 ${fmt(V.eq_asof)}`, "조원 · 배 · %");
      $("#comp").innerHTML = `<table><thead><tr><th>회사</th><th class="n">시가총액</th><th class="n">P/B</th><th class="n">P/E</th><th class="n">ROE</th></tr></thead>
        <tbody>${V.rows.map((r) => `<tr${r.stale ? ' style="color:var(--muted)"' : ""}><td><a href="${esc(r.url)}" target="_blank" rel="noopener"><b>${esc(r.symbol)}</b></a> ${esc(r.name)}${r.note ? ` <small>${esc(r.note)}</small>` : ""}</td>
          <td class="n">${num(r.mcap_krw != null ? r.mcap_krw / 1e4 : null, 1)}</td><td class="n">${num(r.pb, 2)}</td><td class="n">${num(r.pe, 1)}</td><td class="n">${sign(r.roe, 1)}</td></tr>`).join("")}
        <tr><td class="k">중앙값(${V.rows.length}개사)</td><td></td><td class="n"><b>${num(V.median_pb, 2)}</b></td><td class="n"><b>${num(V.median_pe, 1)}</b></td><td class="n"><b>${num(V.median_roe, 1)}</b></td></tr></tbody></table>
        <p class="small">P/B = 시가총액 ÷ 최근 분기 자본, ROE는 최근 4개 분기 순이익 기준(없으면 연간). 같은 값이 <a href="../#insight" target="_top">전략 인사이트 탭</a> 밸류에이션 비교에도 쓰입니다.</p>`;
      return;
    }
    const rows = (sec?.rows || []).filter((r) => r.ok);
    if (!rows.length) { $("#comp").innerHTML = '<p class="empty">SEC 수집 데이터를 불러오지 못했습니다.</p>'; return; }
    $("#compSrc").textContent = "SEC EDGAR XBRL · 매주 월요일 자동";
    const bn = (x) => (x?.value == null ? null : x.value / 1e9);
    const ends = (k) => [...new Set(rows.map((r) => r[k]?.end).filter(Boolean))].sort();
    $("#tm-comp").innerHTML = tmeta(`손익 최근 사업연도(10-K, 결산월 회사별) · 자본 최근 분기말 ${fmt(ends("equity").pop())}`, "US$ bn");
    $("#comp").innerHTML = `<table><thead><tr><th>회사</th><th>사업 모델</th><th class="n">순영업수익</th><th class="n">순이익</th><th class="n">자본</th></tr></thead>
      <tbody>${rows.sort((a, b) => (b.equity?.value || 0) - (a.equity?.value || 0)).map((r) => `<tr><td class="k">${esc(r.name)}</td><td>${esc(r.model)}</td>
        <td class="n" title="${esc(r.revenue_fy?.end || "")}">${num(bn(r.revenue_fy), 1)}</td><td class="n" title="${esc(r.net_income_fy?.end || "")}">${sign(bn(r.net_income_fy), 1)}</td>
        <td class="n" title="${esc(r.equity?.end || "")}">${num(bn(r.equity), 1)}</td></tr>`).join("")}</tbody></table>
      <p class="small">사업연도 끝: ${[...new Set(rows.map((r) => r.net_income_fy?.end).filter(Boolean))].sort().map(fmt).join(", ")}. P/B·P/E는 전략 인사이트 탭 밸류에이션 수집이 붙으면 이 자리에 자동으로 나옵니다.</p>`;
  }

  // ---------- Velocity Clearing(한화생명 75%) ----------
  // 설명(개요·인수 경과·라이선스 문구)은 us_entry.json velocity, 숫자·목록은 data/velocity.json(fetch_velocity.py 매일 수집)
  const mUsd = (v) => (v == null ? null : v / 1e6);
  const short = (v) => (v == null ? "—" : v >= 1e9 ? `$${num(v / 1e9, 1)}bn` : `$${num(v / 1e6, 0)}m`);
  const SRO_SHORT = [[/^New York Stock Exchange/i, "NYSE"], [/^NYSE Arca/i, "NYSE Arca"], [/^NYSE American/i, "NYSE American"],
    [/^Nasdaq Stock Market/i, "Nasdaq"], [/^Cboe Exchange/i, "Cboe(옵션)"], [/^Investors' Exchange/i, "IEX"],
    [/^Long-Term Stock Exchange/i, "LTSE"], [/^MIAX PEARL/i, "MIAX Pearl"], [/^24X National/i, "24X"]];
  const sroName = (n) => SRO_SHORT.find(([re]) => re.test(n))?.[1] || n.replace(/,?\s+(Inc\.|LLC|L\.L\.C\.)$/i, "").replace(/\s+Exchange$/i, "");
  // Form BD 업무 종류(BrokerCheck 표기) → 한국어. 목록에 없는 표기는 영어 그대로
  const BIZ = [[/inter-dealer markets in corporat/i, "장외 주식 딜러 간 시장조성"], [/retailing corporate equity/i, "장외 주식 리테일 중개"],
    [/selling corporate debt/i, "회사채 중개"], [/^Mutual fund retailer/i, "뮤추얼펀드 판매"], [/government securities broker/i, "미 국채 중개"],
    [/government securities dealer/i, "미 국채 딜러"], [/^Municipal securities broker/i, "지방채 중개"], [/^Municipal securities dealer/i, "지방채 딜러"],
    [/^Put and call broker/i, "옵션 중개·발행"], [/^Non-exchange member arranging/i, "거래소 비회원 상장증권 거래 주선"],
    [/^Trading securities for own account/i, "자기매매"], [/^Exchange member engaged in exchange commission/i, "거래소 위탁매매"],
    [/^Exchange member engaged in floor/i, "거래소 플로어 업무"], [/^Underwriter or selling group/i, "인수·판매단 참여"],
    [/^Private placements/i, "사모 주선"], [/^Investment advisory/i, "투자자문"], [/^Broker or dealer selling variable/i, "변액상품 판매"],
    [/^Solicitor of time deposits/i, "예금 권유"], [/^Broker or dealer selling oil/i, "석유·가스 권익 판매"], [/^Commodities/i, "상품"]];
  const bizName = (t) => (/^Other\s*-/i.test(t) ? "기타(대리 청산·대차·포트폴리오 마진·프라임 브로커리지·옵션 청산·RP 등)"
    : BIZ.find(([re]) => re.test(t))?.[1] || t);
  const POS = [[/^CHIEF EXECUTIVE/, "CEO"], [/^CO[- ]?PRESIDENT/, "공동 사장"], [/^PRESIDENT/, "사장"], [/^CHIEF FINANCIAL OFFICER\/FINOP/, "CFO·FINOP"],
    [/^CHIEF FINANCIAL/, "CFO"], [/^CHIEF OPERATING/, "COO"], [/^CHIEF OPERATIONS/, "운영 책임자"], [/^CHIEF COMPLIANCE/, "CCO"],
    [/^CHIEF TECHNOLOGY/, "CTO"], [/^CHIEF RISK/, "CRO"]];
  const person = (n) => { // 'LOGAN, MICHAEL JAMES' → 'Michael Logan'
    const [last, rest = ""] = String(n).split(/,\s*/);
    const tc = (s) => s.toLowerCase().replace(/(^|[\s'-])\p{L}/gu, (c) => c.toUpperCase());
    return `${tc(rest.split(/\s+/)[0] || "")} ${tc(last)}`.trim();
  };

  // 미국 상장 브로커리지 + Velocity: 자본·총자산 순위(같은 날짜)
  function velRank(V, last) {
    const P = V?.peers;
    if (!last || !P?.rows?.length || P.date !== last.period) return null;
    const rows = P.rows.filter((r) => r.equity?.value != null).map((r) => ({ ...r, eq: r.equity.value, as: r.assets?.value ?? null }));
    if (!rows.length) return null;
    rows.push({ name: "Velocity Clearing", ticker: "비상장", model: "자체청산 BD(한화생명 75%)", eq: last.equity, as: last.assets, me: true });
    rows.sort((a, b) => b.eq - a.eq);
    const byAs = rows.filter((r) => r.as != null).sort((a, b) => b.as - a.as);
    const me = rows.find((r) => r.me);
    return { rows, n: rows.length, eq: rows.indexOf(me) + 1, as: byAs.indexOf(me) + 1, nAs: byAs.length, byAs };
  }

  function renderVelocity(V) {
    const M = U.velocity;
    if (!M) return;
    const bc = V?.brokercheck || {}, ed = V?.edgar || {}, n = bc.counts || {};
    const fin = (ed.fin || []).slice().sort((a, b) => (a.period < b.period ? -1 : 1)).slice(-5);
    const last = fin[fin.length - 1], prev = fin[fin.length - 2];
    // 감사보고서보다 새 재무상태표(회사 누리집 반기 미감사)가 있으면 KPI·순위는 그 날짜로
    const it = V?.interim && last && V.interim.period > last.period ? V.interim : null;
    const cur = it || last, nc = cur?.net_capital != null ? cur : last;
    const R = velRank(V, cur);
    const yr = (p) => `FY${String(p).slice(0, 4)}`;
    const ym = (p) => `${String(p).slice(0, 4)}.${String(p).slice(5, 7)}`;
    const itAud = it?.audited === false ? "미감사" : it?.audited ? "감사" : ""; // 파일 이름 기준
    const itLab = it ? `${ym(it.period)}${itAud ? ` ${itAud}` : ""}` : "";
    $("#velSrc").textContent = V ? `FINRA BrokerCheck·SEC EDGAR·뉴스 매일 자동 · 설명 원문 검증 ${fmt(M.verified_at)}` : `설명 원문 검증 ${fmt(M.verified_at)}`;
    $("#velLead").textContent = M.lead;

    const k = [
      { v: "75%", t: "한화생명 지분", d: "모회사 Nexus Clearing 지분 · 2025.07.30 인수 완료", src: ["v_done"] },
      { v: short(cur?.equity), t: "자본(회원 지분)", d: it ? `${itLab} · ${yr(last.period)} ${short(last.equity)}` : last ? `${yr(last.period)} 감사 · 전년 ${short(prev?.equity)}` : "" },
      { v: short(cur?.assets), t: "총자산", d: it ? `${itLab} · ${yr(last.period)} ${short(last.assets)}` : last ? `${yr(last.period)} · 전년 ${short(prev?.assets)}` : "" },
      { v: short(nc?.net_capital), t: "순자본(15c3-1)", d: nc?.required ? `${nc === it ? `${ym(it.period)} · ` : ""}최소 요건 ${short(nc.required)}의 ${num(nc.net_capital / nc.required, 1)}배` : "" },
      { v: R ? `${R.eq}위 / ${R.n}` : "—", t: "미국 상장 브로커리지 대비 자본", d: R ? `총자산 ${R.as}위 / ${R.nAs} · ${fmt(cur.period)} 기준` : "상장사 값은 다음 자동 수집 때" },
    ];
    $("#velKpis").innerHTML = k.map((x) => `<div class="kpi"><b>${esc(x.v)}</b><span>${esc(x.t)}${refs(x.src)}</span><small>${esc(x.d)}</small></div>`).join("");

    // 개요(+ 경영진: BrokerCheck 자동)
    const groups = [];
    for (const o of bc.officers || []) {
      const lab = POS.find(([re]) => re.test(String(o.position || "").toUpperCase()))?.[1];
      if (!lab || !/,/.test(o.name || "")) continue; // 법인 소유자(SOLE MEMBER 등)는 소유 구조 줄에
      const g = groups.find((x) => x.lab === lab) || (groups.push({ lab, names: [] }), groups[groups.length - 1]);
      g.names.push(person(o.name));
    }
    const prof = M.profile.map((r) => `<tr><td class="k">${esc(r.k)}</td><td>${esc(r.t)}${refs(r.src)}</td></tr>`);
    if (groups.length) prof.push(`<tr><td class="k">경영진</td><td>${groups.map((g) => `${esc(g.lab)} ${esc(g.names.join("·"))}`).join(" · ")}${refs(M.officers_src)}</td></tr>`);
    $("#velProfile").innerHTML = `<colgroup><col style="width:72px"><col></colgroup><tbody>${prof.join("")}</tbody>`;
    $("#tm-velp").innerHTML = tmeta(`원문 검증 ${fmt(M.verified_at)}${bc.checked ? ` · 경영진 BrokerCheck ${fmt(bc.checked)}` : ""}`);
    $("#velTl").innerHTML = `<colgroup><col style="width:78px"><col></colgroup><tbody>${M.timeline.map((r) => `<tr><td class="d">${fmt(r.d)}</td><td>${esc(r.t)}${refs(r.src)}</td></tr>`).join("")}</tbody>`;
    $("#tm-velt").innerHTML = tmeta("발표·공시일(미국 시각)");

    // 라이선스·등록: 개수·목록은 BrokerCheck 자동, 설명은 사람이 쓴 문구
    const sros = bc.sros || [];
    const auto = {
      sec: () => `${bc.sec_file ? `SEC 파일 ${esc(bc.sec_file)} · ` : ""}`,
      finra: () => [bc.crd ? `CRD ${esc(bc.crd)}` : "", bc.finra_since ? `${fmt(bc.finra_since)} 승인` : "",
        bc.size ? `규모 분류 '${esc({ Small: "소형", Mid: "중형", Large: "대형" }[bc.size] || bc.size)}'` : ""].filter(Boolean).join(" · "),
      sro: () => `<b>${n.sro ?? sros.length}곳</b>${sros.length ? `: ${sros.map((s) => `<span title="${esc(s.name)} · ${fmt(s.since)} 승인">${esc(sroName(s.name))}</span>`).join(", ")}` : ""} · `,
      states: () => `<b>${n.states ?? "—"}곳</b> · `,
      types: () => `<b>${n.types ?? "—"}종</b>${(bc.types || []).length ? `: ${bc.types.map((t) => `<span title="${esc(t)}">${esc(bizName(t))}</span>`).join(", ")}` : ""}`,
      // 건수·진행 상태·가장 최근 개시일은 자동, 사건 설명은 사람이 쓴 문구(그보다 새 공시가 올라오면 날짜만 보여 줌)
      disc: (r) => {
        const st = Object.values(bc.disc_status || {}), open = st.reduce((a, x) => a + (x.pending || 0) + (x.appeal || 0), 0);
        const L = r.latest, newer = bc.disc_latest && L && bc.disc_latest > L.d;
        return `<b>${Object.values(bc.disclosures || {}).reduce((a, b) => a + (b || 0), 0)}건</b>(BrokerCheck 규제 공시)`
          + (st.length ? (open ? `, 진행 중 <b>${open}건</b>` : ", 모두 종결") : "")
          + (newer ? ` · 가장 최근 ${fmt(bc.disc_latest)} 개시 건(내용은 BrokerCheck 보고서)` : L ? ` · 가장 최근은 ${fmt(L.d)} ${esc(L.t)}` : "");
      },
    };
    $("#velLic").innerHTML = `<colgroup><col style="width:84px"><col></colgroup><tbody>${M.licenses.map((r) =>
      `<tr><td class="k">${esc(r.k)}</td><td>${r.auto && auto[r.auto] ? auto[r.auto](r) : ""}${esc(r.t)}${refs(r.src)}</td></tr>`).join("")}</tbody>`;
    $("#tm-vell").innerHTML = tmeta(bc.checked ? `FINRA BrokerCheck ${fmt(bc.checked)}${bc.sros_checked && bc.sros_checked !== bc.checked ? ` · 거래소 목록 ${fmt(bc.sros_checked)}` : ""}` : "FINRA BrokerCheck", "곳 · 종 · 건");

    // 재무 추이: 연도별 공개분 PDF로 연결(+ 그보다 새 누리집 재무상태표 한 칸)
    const rowsF = [["총자산", "assets"], ["부채", "liab"], ["자본(회원 지분)", "equity"], ["순자본", "net_capital"], ["최소 순자본", "required"], ["초과 순자본", "excess"]];
    const cols = it ? [...fin, it] : fin;
    const head = (f) => (f === it
      ? `<th class="n"><a href="${esc(it.url)}" target="_blank" rel="noopener" title="회사 누리집 재무상태표">${ym(it.period)}</a>${itAud ? `<span class="sub">${itAud}</span>` : ""}</th>`
      : `<th class="n"><a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.acc || "")}${f.filed ? ` · ${fmt(f.filed)} 공시` : ""}">${yr(f.period)}</a></th>`);
    $("#velFin").innerHTML = fin.length ? `<thead><tr><th>항목</th>${cols.map(head).join("")}</tr></thead>
      <tbody>${rowsF.map(([lab, key]) => `<tr><td class="k">${lab}</td>${cols.map((f) => `<td class="n">${key === "equity" ? `<b>${num(mUsd(f[key]), 1)}</b>` : num(mUsd(f[key]), 1)}</td>`).join("")}</tr>`).join("")}</tbody>` : "";
    if (!fin.length) $("#velFin").outerHTML = '<p class="empty" id="velFin">연차 감사보고서 데이터를 불러오지 못했습니다.</p>';
    $("#tm-velf").innerHTML = tmeta(`각 연도 12월 31일 감사받은 재무상태표${it ? ` · ${itLab}: 회사 누리집 재무상태표` : ""}`, "US$ m");
    $("#velFinNote").innerHTML = `${esc(M.fin_note)}${refs(M.fin_src)}`;

    // 미국 상장 브로커리지 대비 위치
    if (R) {
      const d = cur.period;
      $("#velRank").innerHTML = `<thead><tr><th class="n">순위</th><th>회사</th><th>사업 모델</th><th class="n">자본</th><th class="n">총자산</th></tr></thead>
        <tbody>${R.rows.map((r, i) => `<tr${r.me ? ' class="me"' : ""}><td class="rk">${i + 1}</td><td class="k">${esc(r.name)} <small>${esc(r.ticker)}</small></td><td>${esc(r.model)}</td>
          <td class="n"${r.equity?.end && r.equity.end !== d ? ` title="${esc(r.equity.end)} 기준"` : ""}>${num(mUsd(r.eq), 0)}${r.equity?.end && r.equity.end !== d ? "*" : ""}</td>
          <td class="n">${r.as == null ? "—" : num(mUsd(r.as), 0)}</td></tr>`).join("")}</tbody>`;
      const odd = R.rows.filter((r) => r.equity?.end && r.equity.end !== d);
      $("#velRankNote").innerHTML = `자본 기준 <b>${R.n}곳 중 ${R.eq}위</b>, 총자산 기준 ${R.nAs}곳 중 ${R.as}위. 상장사는 미국 본사 NYSE·NYSE American·나스닥 상장사 중 증권 중개·청산·시장조성·자산관리 중개가 주업인 ${R.n - 1}곳(자문 전업 IB·거래소·보험 겸업사 제외). ${esc(M.rank_note)}${odd.length ? ` *는 결산월이 달라 가장 가까운 분기말 값(${odd.map((r) => `${esc(r.ticker)} ${fmt(r.equity.end)}`).join(", ")}).` : ""}${refs(M.rank_src)}`;
      $("#tm-velr").innerHTML = tmeta(`${fmt(d)} · 상장사 SEC XBRL(10-K·10-Q)${V.peers.checked ? ` ${fmt(V.peers.checked)} 수집` : ""}`, "US$ m");
    } else {
      $("#velRank").outerHTML = '<p class="empty" id="velRank">상장사 비교 값은 다음 자동 수집(SEC XBRL) 때 채워집니다.</p>';
      $("#tm-velr").innerHTML = tmeta("SEC XBRL", "US$ m");
    }

    // 최근 공시·뉴스
    const fins = new Map(fin.map((f) => [f.acc, f]));
    const fl = (ed.filings || []).slice(0, 6);
    $("#velFilings").innerHTML = fl.length ? fl.map((f) => `<li><time>${fmt(f.filed)}</time><span><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.form)} 연차 감사보고서${/\/A$/.test(f.form) ? "(정정)" : ""} · ${yr(f.period)}</a>${fins.get(f.acc)?.url ? ` <small><a href="${esc(fins.get(f.acc).url)}" target="_blank" rel="noopener">PDF</a></small>` : ""}</span></li>`).join("")
      : '<li class="empty">공시 목록을 불러오지 못했습니다.</li>';
    $("#tm-vele").innerHTML = tmeta(ed.checked ? `EDGAR ${fmt(ed.checked)} 확인` : "EDGAR");
    const nw = V?.news || [];
    $("#velNews").innerHTML = nw.length ? nw.map((x) => `<li><time>${fmt(x.date)}</time><span><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><small>${esc(x.src)}</small></span></li>`).join("")
      : '<li class="empty">최근 2년 안 기사가 없습니다.</li>';
    $("#tm-veln").innerHTML = tmeta(V?.news_checked ? `최근 2년 · ${fmt(V.news_checked)} 확인` : "최근 2년");
  }

  // ---------- iframe 안 이동 ----------
  function go(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const fe = frame();
    if (fe) {
      const top = fe.getBoundingClientRect().top + window.parent.scrollY + el.getBoundingClientRect().top + window.scrollY - 70;
      window.parent.scrollTo({ top, behavior: "smooth" });
    } else {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1600);
  }

  // 대시보드 주소를 지금 화면에 맞춘다(#workflow/us). hashchange 를 일으키지 않게 replaceState
  function setParentHash(h) {
    try { if (frame() && window.parent.location.hash.startsWith("#workflow")) window.parent.history.replaceState(null, "", h); } catch (_) { /* 교차 출처 */ }
  }

  function wire() {
    document.addEventListener("click", (e) => {
      const g = e.target.closest("[data-go]");
      if (g) { e.preventDefault(); go(g.dataset.go); return; }
      const w = e.target.closest("[data-wf]");
      if (w && frame()) { setParentHash(`#workflow/${w.dataset.wf}`); return; } // index.html 이 대시보드 주소의 단계로 이동
      const b = e.target.closest('[data-to="index"]');
      if (b) setParentHash("#workflow");
    });
    const fe = frame();
    if (!fe) return;
    setParentHash("#workflow/us");
    const fit = () => { fe.style.height = `${document.documentElement.scrollHeight + 4}px`; };
    fit();
    if ("ResizeObserver" in window) new ResizeObserver(fit).observe(document.body);
    // 위쪽 탭 메뉴로 '해외지분투자 Workflow'(#workflow)나 단계(#workflow/s10)를 고르면 절차 쪽으로 돌아간다
    const onHash = () => {
      let h = "";
      try { h = window.parent.location.hash; } catch (_) { return; }
      if (h.startsWith("#workflow") && h !== "#workflow/us") location.replace("index.html");
    };
    window.parent.addEventListener("hashchange", onHash);
    window.addEventListener("pagehide", () => { try { window.parent.removeEventListener("hashchange", onHash); } catch (_) { /* 무시 */ } });
  }

  async function load(url, optional) {
    try { const r = await fetch(url, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return await r.json(); }
    catch (e) { if (optional) return null; throw e; }
  }

  async function init() {
    let cfg, cons, sf, upd, val, sec, vel;
    try {
      [U, W, ST, cfg, cons, sf, upd, val, sec, vel] = await Promise.all([
        load("data/us_entry.json"), load("data/steps.json", true), load("../guide/data/source_status.json", true),
        load("../data/config.json", true), load("../data/domestic/consolidated.json", true), load("../data/domestic/sub_fin.json", true),
        load("../data/domestic/offices_update.json", true), load("../insight/data/valuation.json", true), load("../data/global/us_sec.json", true),
        load("data/velocity.json", true),
      ]);
    } catch (e) {
      $("#meta").textContent = `데이터를 불러오지 못했습니다(${e.message}).`;
      return;
    }
    Object.keys(U.sources).forEach((id, i) => { REF[id] = i + 1; });
    const urls = Object.values(U.sources).map((s) => s.u);
    const done = urls.filter((u) => srcState(u)?.checked);
    // 머리 줄 원문 점검일은 실제로 비교한 날(ST.updated)까지만: 병합 때 새 출처 기준값만 잡은 날은 빼고
    const last = done.map((u) => srcState(u).checked).sort().pop();
    const checked = last && ST?.updated && ST.updated < last ? ST.updated : last;
    const revised = urls.filter((u) => (srcState(u)?.changed_at || "") > U.meta.verified_at).length;
    const nFail = urls.filter((u) => unchecked(srcState(u))).length, nWait = urls.length - done.length - nFail;
    const part = [nFail ? `자동 점검이 안 되는 ${nFail}건은 규정 검증일 기준` : "", nWait ? `${nWait}건은 다음 점검` : ""].filter(Boolean).join(" · ");
    $("#title").textContent = U.meta.title;
    $("#meta").innerHTML = `규정 검증 <b>${fmt(U.meta.verified_at)}</b> · 원문 점검 <b>${checked ? fmt(checked) : "다음 반기 점검(1·7월)"}</b>${checked && part ? `(${urls.length}건 중 ${done.length}건 · ${part})` : ""}${revised ? ` · <span class="neg">개정 감지 ${revised}건</span>` : ""} · 출처 ${urls.length}건 · 한국 측 절차는 <a href="index.html" data-to="index">해외지분투자 절차</a>, 국가 비교는 <a href="../#guide" target="_top">해외진출 유의사항 탭</a> · 한화그룹 사례 <a href="#velocity" data-go="velocity">Velocity Clearing ↓</a>`;
    $("#note").textContent = `${U.meta.scope} ${U.meta.note}`;
    const v = `규정 검증 ${fmt(U.meta.verified_at)}`;
    $("#tm-cmp").innerHTML = tmeta(v);
    $("#tm-tl").innerHTML = tmeta(`검토안 일정(T = 영업 개시·거래 종결) · ${v}`, "개월");
    $("#tm-cap").innerHTML = tmeta(`17 CFR 240.15c3-1 현행 · ${v}`, "US$");
    $("#tm-ppl").innerHTML = tmeta(`FINRA 규칙 현행 · ${v}`, "명");
    $("#tm-ex").innerHTML = tmeta(`FINRA 시험 안내 · ${v}`, "문항 · 시간");
    $("#tm-nma").innerHTML = tmeta(`FINRA Rule 1013·1014 현행 · ${v}`);
    $("#tm-setup").innerHTML = tmeta(`뉴욕주 법·연방 규칙 현행 · ${v}`);
    $("#tm-deal").innerHTML = tmeta("각 사 발표일", "US$(bn = 10억, m = 100만)");
    $("#tm-wf").innerHTML = tmeta(W ? `Workflow 규정 검증 ${fmt(W.meta.verified_at)}` : "", "일 · 개월");
    $("#srcMeta").textContent = `${urls.length}건 · 공식 원문은 반기마다 변경 점검, 기사·발표문은 링크 확인`;
    renderKpis(); renderCompare(); renderTimeline(); renderModels(); renderPeople(); renderNma(); renderSetup();
    renderKr(cfg, cons, sf, upd); renderVelocity(vel); renderComps(val, sec); renderDeals(); renderWf(); renderSources();
    $("#printBtn").onclick = () => window.print();
    wire();
  }
  init();
})();
