// 국가별 해외진출 유의사항 탭. data/countries.json(사람이 출처 확인) + data/detected.json(매일 자동 감지)을 그린다.
// 국내사 현지법인 수는 국내 탭과 같은 기준 데이터(../data/domestic/seed.json)에서 센다.
// data/source_status.json 은 반기 1회 원문 점검 결과(.github/workflows/source-check.yml): 원문 점검일과 개정 감지 표시에 쓴다.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const host = (u) => { try { return new URL(u, location.href).hostname.replace(/^www\./, ""); } catch (_) { return ""; } };
  const todayStr = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date());
  const days = (d) => Math.round((new Date(`${todayStr}T00:00:00`) - new Date(`${d}T00:00:00`)) / 864e5);
  const fmt = (d) => (d || "").replace(/-/g, ".");
  const tmeta = (basis, unit) => `${basis ? `<span>기준 ${esc(basis)}</span>` : ""}${unit ? `<span>단위: ${esc(unit)}</span>` : ""}`;
  const store = {
    get(k, f) { try { return JSON.parse(localStorage.getItem(`gnd-guide:${k}`)) ?? f; } catch (_) { return f; } },
    set(k, v) { try { localStorage.setItem(`gnd-guide:${k}`, JSON.stringify(v)); } catch (_) { /* 저장 불가 환경 */ } },
  };
  const AUTO_STALE = 8; // 매일 실행 기준, 8일 넘게 자동 확인이 안 되면 경고
  const COLS = [["own", "외국인 지분"], ["lic", "인가·감독"], ["cap", "최소 자본"], ["local", "현지 임원·거주"], ["fx", "송금·외환·세금"]];

  let G, D, WF, ST, KR = {}, filter = store.get("f", "all"), open = null;
  const det = (code) => D?.markets?.[code] || { items: [], auto_checked: null };
  const fresh = (c) => det(c.code).items.filter((x) => x.date > c.checked);
  const chip = (lv) => `<span class="lv ${lv}">${esc(G.meta.legend[lv] || lv)}</span>`;
  const warn = (f) => (f.ok ? "" : `<span class="chk" title="${esc(f.why || "원문을 다시 확인하지 못함: 진행 전 현지 원문 확인")}">요확인</span>`);
  const why = (f) => (f.ok || !f.why ? "" : `<small class="why">요확인 사유: ${esc(f.why)}</small>`);
  // 반기 원문 점검에서 사람 검증일 이후 바뀐 출처
  const revised = (id, checked) => (ST?.rows?.[id]?.changed || []).filter((x) => x.at > checked);
  const srcChk = (id) => ST?.rows?.[id]?.checked;

  // 국내 탭과 같은 기준: 운영 중인 법인(지분투자 제외)만 센다
  function countKorea(seed) {
    if (!seed) return;
    for (const e of seed.entities || []) {
      if (e.kind !== "법인" || e.status !== "운영" || e.relation === "지분투자") continue;
      const k = (KR[e.country] ||= { n: 0, firms: new Set(), off: 0 });
      k.n += 1; k.firms.add(e.firm);
    }
    for (const o of seed.offices || []) (KR[o.country] ||= { n: 0, firms: new Set(), off: 0 }).off += 1;
  }

  function renderTop() {
    const m = G.meta;
    $("#legend").innerHTML = Object.keys(m.legend).map(chip).join(" ");
    const auto = D ? ` · 감독당국 공식 발표 자동 확인 <b>${fmt(D.updated.slice(0, 10))}</b>` : "";
    const src = ST ? ` · 원문 점검 <b>${fmt(ST.updated)}</b>` : "";
    $("#meta").innerHTML = `사람 검증 <b>${fmt(m.verified_at)}</b>${src}${auto} · ${G.countries.length}개 시장`;
    $("#pAsof").textContent = `(${fmt(m.verified_at)} 기준)`;
    $("#foot").textContent = m.note;
    $("#tm-mx").innerHTML = tmeta(`사람 검증 ${fmt(m.verified_at)}${ST ? ` · 원문 점검 ${fmt(ST.updated)}` : ""}`, "국내사 법인 개 · 자본금은 각국 현지통화");
    $("#tm-lim").innerHTML = tmeta(`사람 검증 ${fmt(m.verified_at)}`);
    if (WF) $("#tm-kr").innerHTML = tmeta(`규정 검증 ${fmt(WF.meta.verified_at)}`, "기한은 사유 발생일부터");
    // 한국 측 절차는 해외지분투자 Workflow 탭이 원본: 대외 신고·보고 단계만 기한과 함께 링크로 보여준다
    const ext = (WF?.steps || []).filter((x) => x.lane === "ext");
    $("#steps").innerHTML = ext.length
      ? ext.map((x) => `<li><b>${esc(x.due || "")}</b><span><a class="in" href="../#workflow/${x.id}" target="_top">${esc(x.title)} ↗</a> ${esc(x.when)}</span></li>`).join("")
      : '<li><span><a class="in" href="../#workflow" target="_top">해외지분투자 Workflow 탭에서 전체 절차 보기 ↗</a></span></li>';
    if (WF) $("#krAsof").innerHTML = `모든 국가 공통 · <a href="../#workflow" target="_top">전체 절차 흐름도는 해외지분투자 Workflow 탭</a> · 당사 기한은 <a href="../#hanwha" target="_top">한화투자증권 탭</a>`;
    const lim = G.countries.filter((c) => c.lv !== "open").sort((a, b) => (a.lv === "cap" ? -1 : 1) - (b.lv === "cap" ? -1 : 1));
    $("#lim").innerHTML = lim.map((c) => `<li><b>${esc(c.name)}</b><span>${chip(c.lv)} ${esc(c.headline)}</span></li>`).join("");
  }

  function visible() {
    return G.countries.filter((c) => filter === "all" || (filter === "kr" ? KR[c.seed]?.n : c.hanwha));
  }

  function row(c) {
    const k = KR[c.seed];
    const ac = det(c.code).auto_checked;
    const stale = !!D && (!ac || days(ac) > AUTO_STALE);
    const n = fresh(c).length;
    const rv = revised(c.code, c.checked);
    const sc = srcChk(c.code);
    const cells = COLS.map(([key]) => {
      const f = c[key];
      return `<td class="${key}">${key === "own" ? chip(c.lv) : ""}<span class="t">${esc(f.v)}</span>${warn(f)}</td>`;
    }).join("");
    return `<tr class="r ${c.hanwha ? "hw" : ""} ${c.ref ? "ref" : ""} ${open === c.code ? "open" : ""}" tabindex="0" data-code="${c.code}">
      <td class="nm"><b>${esc(c.name)}</b><small>${esc(c.regulator)}</small>${c.annex ? `<a class="annex" href="${esc(c.annex.u)}" target="_top" title="${esc(c.annex.t)}">별첨: 설립 vs 인수 ↗</a>` : ""}${n ? `<span class="new" title="검증일 이후 감독당국 공식 발표 ${n}건 자동 감지: 내용 확인 필요">● 신규 공식 발표 ${n}</span>` : ""}${rv.length ? `<span class="new rev" title="반기 원문 점검에서 출처 ${rv.length}건이 바뀜: 행을 열어 확인">● 개정 감지·검토 필요</span>` : ""}</td>
      <td class="kr">${k?.n || "—"}<small>${k ? `${k.firms.size}개사${k.off ? ` · 사무소 ${k.off}` : ""}` : "진출 없음"}</small></td>
      ${cells}
      <td class="ck ${stale ? "stale" : ""}">${fmt(c.checked).slice(2)}<small>원문 ${sc ? fmt(sc).slice(2) : "—"}</small><small>발표 ${ac ? fmt(ac).slice(5) : "—"}${stale ? " ⚠" : ""}</small></td></tr>`;
  }

  function detail(c) {
    const src = c.sources.map((s, i) => `<li>[${i + 1}] <a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a> <small>${esc(s.d)} · ${esc(host(s.u))}</small></li>`).join("");
    const refs = (f) => f.src.map((i) => `[${i + 1}]`).join("");
    const items = det(c.code).items.slice(0, 6);
    const auto = items.length
      ? `<ul>${items.map((x) => `<li>${x.date > c.checked ? "<b>신규</b> " : ""}<small>${fmt(x.date)}</small> <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a> <small>${esc(x.src)}</small></li>`).join("")}</ul>`
      : `<p class="empty">${det(c.code).auto_checked ? "최근 감지된 공식 발표가 없습니다." : "다음 자동 실행(매일 07:10) 후 채워집니다."}</p>`;
    return `<tr class="det"><td colspan="${COLS.length + 3}"><div class="dg">
      <div>${c.hanwha ? `<div class="hwbox"><b>당사 사례</b> · ${esc(c.hanwha)}</div>` : ""}
        ${c.annex ? `<div class="hwbox"><a href="${esc(c.annex.u)}" target="_top"><b>${esc(c.annex.t)} ↗</b></a></div>` : ""}
        <h4>${esc(c.headline)}</h4>
        <ul>${COLS.map(([k, n]) => `<li><b>${n}</b> ${esc(c[k].v)} <small>${refs(c[k])}</small>${warn(c[k])}${why(c[k])}</li>`).join("")}</ul></div>
      <div><h4>추가 유의사항</h4><ul>${c.quirks.map((q) => `<li>${esc(q.v)} <small>${refs(q)}</small>${warn(q)}${why(q)}</li>`).join("")}</ul>
        <h4 style="margin-top:6px">출처 <small>사람 검증 ${fmt(c.checked)}${srcChk(c.code) ? ` · 원문 점검 ${fmt(srcChk(c.code))}` : ""}</small></h4><ul>${src}</ul>
        ${revised(c.code, c.checked).length ? `<h4 style="margin-top:6px">개정 감지·검토 필요</h4><ul>${revised(c.code, c.checked).map((x) => `<li><small>${fmt(x.at)}</small> <a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t)}</a> 원문이 바뀜</li>`).join("")}</ul>` : ""}</div>
      <div><h4>감독당국 공식 발표 자동 감지 <small>공식 도메인만 · 진입 규제 키워드</small></h4>${auto}</div>
    </div></td></tr>`;
  }

  function renderTable() {
    const rows = visible();
    $("#mx").innerHTML = `<colgroup><col style="width:118px"><col style="width:64px">${COLS.map(() => "<col>").join("")}<col style="width:62px"></colgroup>
      <thead><tr><th>국가 · 감독당국</th><th title="국내 탭 기준 데이터: 운영 중인 국내 증권사 현지법인 수">국내사 법인</th>${COLS.map(([, n]) => `<th>${n}</th>`).join("")}<th title="사람 검증일 / 반기 원문 점검일 / 공식 발표 자동 확인일">검증·점검</th></tr></thead>
      <tbody>${rows.map((c) => row(c) + (open === c.code ? detail(c) : "")).join("") || `<tr><td colspan="${COLS.length + 3}" class="empty">해당하는 국가가 없습니다.</td></tr>`}</tbody>`;
    document.querySelectorAll("#filters .pill").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.f === filter)));
  }

  function toggle(code) {
    open = open === code ? null : code;
    renderTable();
  }

  async function load(url, optional) {
    try { const r = await fetch(url, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return await r.json(); }
    catch (e) { if (optional) return null; throw e; }
  }

  async function init() {
    let seed;
    try {
      [G, D, seed, WF, ST] = await Promise.all([load("data/countries.json"), load("data/detected.json", true), load("../data/domestic/seed.json", true), load("../workflow/data/steps.json", true), load("data/source_status.json", true)]);
    } catch (e) {
      $("#meta").textContent = `데이터를 불러오지 못했습니다(${e.message}).`;
      return;
    }
    countKorea(seed);
    renderTop();
    renderTable();
    $("#mx").onclick = (e) => { const tr = e.target.closest("tr.r"); if (tr && !e.target.closest("a")) toggle(tr.dataset.code); };
    $("#mx").onkeydown = (e) => { const tr = e.target.closest("tr.r"); if (tr && e.key === "Enter") toggle(tr.dataset.code); };
    $("#filters").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; filter = b.dataset.f; store.set("f", filter); renderTable(); };
    $("#printBtn").onclick = () => window.print();
    fitFrame();
  }

  // 대시보드 iframe 안에서: 내용 높이에 맞춰 바깥 iframe 높이를 맞춘다(같은 출처일 때만)
  function fitFrame() {
    let fe = null;
    try { fe = window.frameElement; } catch (_) { return; }
    if (!fe) return;
    const fit = () => { fe.style.height = `${document.documentElement.scrollHeight + 4}px`; };
    fit();
    if ("ResizeObserver" in window) new ResizeObserver(fit).observe(document.body);
  }
  init();
})();
