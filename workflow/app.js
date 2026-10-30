// 해외지분투자 Workflow 탭. data/steps.json 하나로 흐름도·기한 요약·단계 설명을 그린다.
// 대시보드에서 #workflow/s10 처럼 들어오면 해당 단계로 이동한다.
// ../guide/data/source_status.json(반기 원문 점검 결과)으로 원문 점검일·개정 감지·조문 자동 대조를 표시한다.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const host = (u) => { try { return new URL(u, location.href).hostname.replace(/^www\./, ""); } catch (_) { return ""; } };
  const fmt = (d) => (d || "").replace(/-/g, ".");
  const tmeta = (basis, unit) => `${basis ? `<span>기준 ${esc(basis)}</span>` : ""}${unit ? `<span>단위: ${esc(unit)}</span>` : ""}`;
  const LANES = ["in", "deal", "ext"];
  let W, ST;

  const num = (s) => W.steps.indexOf(s) + 1;
  // 조문 자동 대조(assert)가 원문에서 문구를 찾으면 요확인을 지운다
  const auto = (s) => ST?.rows?.[s.id]?.assert;
  const isOk = (s) => s.ok || auto(s)?.ok === true;
  const warn = (s) => (isOk(s) ? "" : `<span class="chk" title="${esc(s.why || "원문을 다시 확인하지 못함: 진행 전 원문 확인")}">요확인</span>`);
  const revised = (s) => (ST?.rows?.[s.id]?.changed || []).filter((x) => x.at > W.meta.verified_at);

  function renderFlow() {
    const P = W.meta.phases;
    let h = `<div></div>${P.map((p, i) => `<div class="ph">${esc(p)}<small>${i + 1}단계</small></div>`).join("")}`;
    for (const ln of LANES) {
      h += `<div class="lane ${ln}">${esc(W.meta.lanes[ln])}</div>`;
      for (let ph = 1; ph <= P.length; ph += 1) {
        const ns = W.steps.filter((s) => s.lane === ln && s.phase === ph);
        h += `<div class="cell">${ns.map((s) => `<button class="node ${ln}" type="button" data-id="${s.id}" title="${esc(s.when)}">
          <b>${num(s)}</b><span>${esc(s.title)}</span><small>${esc(s.due || s.when)}</small></button>`).join("")}</div>`;
      }
    }
    $("#flow").innerHTML = h;
    $("#flow").onclick = (e) => { const b = e.target.closest(".node"); if (b) go(b.dataset.id); };
  }

  function renderDeadlines() {
    $("#dl").innerHTML = W.steps.filter((s) => s.due).map((s) =>
      `<a href="#${s.id}" data-id="${s.id}"><b>${esc(s.due)}</b><span>${num(s)}. ${esc(s.title)}</span></a>`).join("");
    $("#dl").onclick = (e) => { const a = e.target.closest("a"); if (a) { e.preventDefault(); go(a.dataset.id); } };
  }

  function renderSteps() {
    $("#steps").innerHTML = W.steps.map((s) => `<article class="st ${s.lane}" id="${s.id}">
      <header><span class="n">${String(num(s)).padStart(2, "0")}</span><h3>${esc(s.title)}</h3><span class="who">${esc(W.meta.lanes[s.lane])}</span>${warn(s)}<span class="when">${esc(s.when)}</span></header>
      ${revised(s).length ? `<p class="rev">● 개정 감지·검토 필요: ${revised(s).map((x) => `<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t)}</a> (${fmt(x.at)})`).join(", ")}</p>` : ""}
      <ul>${s.body.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
      ${isOk(s) ? (auto(s)?.ok ? `<p class="auto">원문 자동 대조: 제${s.assert?.jo}조에서 '${esc(s.assert?.has)}' 확인 (${esc(auto(s).via)}, ${fmt(auto(s).checked)})</p>` : "") : s.why ? `<p class="why">요확인 사유: ${esc(s.why)}</p>` : ""}
      <div class="ft">${s.out.length ? `<span class="out">산출물: ${s.out.map(esc).join(" · ")}</span>` : ""}
        ${s.src.map((r) => r.u.startsWith("../")
          ? `<a href="${esc(r.u)}" target="_top">${esc(r.t)} ↗</a>`
          : `<a href="${esc(r.u)}" target="_blank" rel="noopener" title="${esc(r.t)}">${esc(r.t.split("(")[0])} · ${esc(r.d)} ↗</a>`).join("")}</div>
    </article>`).join("");
  }

  // iframe 안에서는 바깥 페이지를 스크롤해야 한다(같은 출처일 때만)
  function go(id) {
    const el = document.getElementById(id);
    if (!el) return;
    let fe = null;
    try { fe = window.frameElement; } catch (_) { fe = null; }
    if (fe) {
      const top = fe.getBoundingClientRect().top + window.parent.scrollY + el.offsetTop - 70;
      window.parent.scrollTo({ top, behavior: "smooth" });
    } else {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1600);
  }

  // 대시보드 주소(#workflow/s10)나 이 페이지 주소(#s10)에 단계가 있으면 그 단계로. #workflow/us 는 미국 진출(us.html)
  function fromHash() {
    let h = location.hash.slice(1);
    try { if (window.frameElement) h = window.parent.location.hash.split("/")[1] || ""; } catch (_) { /* 교차 출처 */ }
    if (h === "us") { location.replace("us.html"); return; }
    if (h) setTimeout(() => go(h), 150);
  }

  function fitFrame() {
    let fe = null;
    try { fe = window.frameElement; } catch (_) { return; }
    if (!fe) return;
    const fit = () => { fe.style.height = `${document.documentElement.scrollHeight + 4}px`; };
    fit();
    if ("ResizeObserver" in window) new ResizeObserver(fit).observe(document.body);
    window.parent.addEventListener("hashchange", fromHash);
    // 미국 진출 쪽으로 넘어가면 이 페이지의 리스너를 떼고, 대시보드 주소를 #workflow/us 로 맞춘다(hashchange 없이)
    window.addEventListener("pagehide", () => { try { window.parent.removeEventListener("hashchange", fromHash); } catch (_) { /* 무시 */ } });
    document.querySelector('[data-to="us"]')?.addEventListener("click", () => {
      try { if (window.parent.location.hash.startsWith("#workflow")) window.parent.history.replaceState(null, "", "#workflow/us"); } catch (_) { /* 교차 출처 */ }
    });
  }

  async function init() {
    try {
      const r = await fetch("data/steps.json", { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      W = await r.json();
      ST = await fetch("../guide/data/source_status.json", { cache: "no-cache" }).then((x) => (x.ok ? x.json() : null)).catch(() => null);
    } catch (e) {
      $("#meta").textContent = `데이터를 불러오지 못했습니다(${e.message}).`;
      return;
    }
    const nOk = W.steps.filter((s) => !isOk(s)).length;
    const src = ST ? ` · 원문 점검 <b>${fmt(ST.updated)}</b>` : "";
    $("#meta").innerHTML = `규정 검증 <b>${fmt(W.meta.verified_at)}</b>${src} · ${W.steps.length}단계 · 요확인 ${nOk}건 · 국가별 현지 요건은 <a href="../#guide" target="_top">해외진출 유의사항 탭</a>`;
    $("#foot").textContent = W.meta.note;
    $("#tm-flow").innerHTML = tmeta(`규정 검증 ${fmt(W.meta.verified_at)}${ST ? ` · 원문 점검 ${fmt(ST.updated)}` : ""}`);
    $("#tm-dl").innerHTML = tmeta(`규정 검증 ${fmt(W.meta.verified_at)}`, "일·개월(기산점은 단계 설명)");
    renderFlow(); renderDeadlines(); renderSteps();
    $("#printBtn").onclick = () => window.print();
    fitFrame();
    fromHash();
  }
  init();
})();
