// 미국 진출(브로커-딜러 설립과 인수). data/us_entry.json(사람이 원문을 읽고 쓴 요건·사례)에 자동 수집 데이터를 붙여 그린다.
// - 국내 증권사 미국 거점: ../data/domestic/consolidated.json(DART 종속회사 목록) + sub_fin.json(종속기업 요약재무정보), 국내 탭과 같은 집계 규칙
// - 미국 상장 브로커리지: ../insight/data/valuation.json(markets.us, 있으면) → 없으면 ../data/global/us_sec.json(SEC XBRL)
// - 원문 점검: ../guide/data/source_status.json(반기 점검 결과, 출처 URL별)
// 한화그룹 사례 Velocity Clearing(한화생명 75%)은 하위 탭 velocity.html(#workflow/velocity). 출처 목록은 같은 us_entry.json 을 나눠 쓴다.
// 대시보드에서는 #workflow/us 로 들어온다. 해외지분투자 절차(index.html)·Velocity 와 같은 iframe 안에서 오간다.
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
  // 출처 id(키가 src로 끝나는 배열)를 모은다. Velocity 설명(us_entry.json velocity)의 출처는 Velocity 탭 목록에
  const used = (o, out = new Set()) => {
    if (Array.isArray(o)) o.forEach((x) => used(x, out));
    else if (o && typeof o === "object") {
      for (const [k, v] of Object.entries(o)) {
        if (/src$/.test(k) && Array.isArray(v)) v.forEach((id) => typeof id === "string" && out.add(id));
        else used(v, out);
      }
    }
    return out;
  };
  const srcIds = () => { const u = used({ ...U, velocity: null, sources: null }); return Object.keys(U.sources).filter((id) => u.has(id)); };

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
      <tbody>${U.deals.map((d) => `<tr><td style="white-space:nowrap">${fmt(d.date)}</td><td><b>${esc(d.buyer)}</b> → ${esc(d.target)}${/Velocity/.test(d.target) ? ' <a href="velocity.html" data-to="velocity">Velocity 탭 →</a>' : ""}</td><td class="n">${esc(d.size)}</td><td>${esc(d.terms)}${refs(d.src)}</td><td>${esc(d.kind)}</td></tr>`).join("")}</tbody>`;
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
    const ids = srcIds();
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
      const b = e.target.closest("[data-to]");
      if (b) setParentHash(b.dataset.to === "index" ? "#workflow" : `#workflow/${b.dataset.to}`);
    });
    const fe = frame();
    if (!fe) return;
    setParentHash("#workflow/us");
    const fit = () => { fe.style.height = `${document.documentElement.scrollHeight + 4}px`; };
    fit();
    if ("ResizeObserver" in window) new ResizeObserver(fit).observe(document.body);
    // 위쪽 탭 메뉴로 '해외지분투자 Workflow'(#workflow)나 단계(#workflow/s10)를 고르면 절차 쪽으로, #workflow/velocity 는 Velocity 탭으로
    const onHash = () => {
      let h = "";
      try { h = window.parent.location.hash; } catch (_) { return; }
      if (h.startsWith("#workflow") && h !== "#workflow/us") location.replace(h === "#workflow/velocity" ? "velocity.html" : "index.html");
    };
    window.parent.addEventListener("hashchange", onHash);
    window.addEventListener("pagehide", () => { try { window.parent.removeEventListener("hashchange", onHash); } catch (_) { /* 무시 */ } });
  }

  async function load(url, optional) {
    try { const r = await fetch(url, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return await r.json(); }
    catch (e) { if (optional) return null; throw e; }
  }

  async function init() {
    let cfg, cons, sf, upd, val, sec;
    try {
      [U, W, ST, cfg, cons, sf, upd, val, sec] = await Promise.all([
        load("data/us_entry.json"), load("data/steps.json", true), load("../guide/data/source_status.json", true),
        load("../data/config.json", true), load("../data/domestic/consolidated.json", true), load("../data/domestic/sub_fin.json", true),
        load("../data/domestic/offices_update.json", true), load("../insight/data/valuation.json", true), load("../data/global/us_sec.json", true),
      ]);
    } catch (e) {
      $("#meta").textContent = `데이터를 불러오지 못했습니다(${e.message}).`;
      return;
    }
    const ids = srcIds();
    ids.forEach((id, i) => { REF[id] = i + 1; });
    const urls = ids.map((id) => U.sources[id].u);
    const done = urls.filter((u) => srcState(u)?.checked);
    // 머리 줄 원문 점검일은 실제로 비교한 날(ST.updated)까지만: 병합 때 새 출처 기준값만 잡은 날은 빼고
    const last = done.map((u) => srcState(u).checked).sort().pop();
    const checked = last && ST?.updated && ST.updated < last ? ST.updated : last;
    const revised = urls.filter((u) => (srcState(u)?.changed_at || "") > U.meta.verified_at).length;
    const nFail = urls.filter((u) => unchecked(srcState(u))).length, nWait = urls.length - done.length - nFail;
    const part = [nFail ? `자동 점검이 안 되는 ${nFail}건은 규정 검증일 기준` : "", nWait ? `${nWait}건은 다음 점검` : ""].filter(Boolean).join(" · ");
    $("#title").textContent = U.meta.title;
    $("#meta").innerHTML = `규정 검증 <b>${fmt(U.meta.verified_at)}</b> · 원문 점검 <b>${checked ? fmt(checked) : "다음 반기 점검(1·7월)"}</b>${checked && part ? `(${urls.length}건 중 ${done.length}건 · ${part})` : ""}${revised ? ` · <span class="neg">개정 감지 ${revised}건</span>` : ""} · 출처 ${urls.length}건 · 한국 측 절차는 <a href="index.html" data-to="index">해외지분투자 절차</a>, 국가 비교는 <a href="../#guide" target="_top">해외진출 유의사항 탭</a> · 한화그룹 사례는 <a href="velocity.html" data-to="velocity">Velocity(한화생명) 탭</a>`;
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
    renderKr(cfg, cons, sf, upd); renderComps(val, sec); renderDeals(); renderWf(); renderSources();
    $("#printBtn").onclick = () => window.print();
    wire();
  }
  init();
})();
