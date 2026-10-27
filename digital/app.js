// 디지털자산 규제 요약 탭. data/regulation.json(사람이 출처 확인) + data/feed.json(주간 자동 수집)을 그린다.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const hi = (s) => esc(s).replace(/\[\[(.+?)\]\]/g, "<mark>$1</mark>");
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (_) { return ""; } };
  const todayStr = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date()); // KST YYYY-MM-DD
  const days = (d) => Math.round((new Date(`${d}T00:00:00`) - new Date(`${todayStr}T00:00:00`)) / 864e5);
  const fmt = (d) => (d || "").replace(/-/g, ".");
  const store = {
    get(k, f) { try { return JSON.parse(localStorage.getItem(`gnd-digital:${k}`)) ?? f; } catch (_) { return f; } },
    set(k, v) { try { localStorage.setItem(`gnd-digital:${k}`, JSON.stringify(v)); } catch (_) { /* 저장 불가 환경 */ } },
  };

  let R, F, D, M = {}, sel, showRef = store.get("ref", false);
  const LV = {};

  function chip(lv) { return `<span class="lv ${lv}">${esc(LV[lv] || lv)}</span>`; }
  function dday(d, approx) {
    const n = days(d);
    const cls = n < 0 ? "late" : n <= 14 ? "soon" : "";
    const label = n === 0 ? "D-day" : n > 0 ? `D-${n}` : `D+${-n}`;
    return `<div class="dd ${cls}">${approx ? "~" : ""}${label}<small>${fmt(d).slice(2)}${approx ? " 경" : ""}</small></div>`;
  }

  // detected.json: 공식 도메인 발표 자동 감지. 사람 검증일 이후 나온 것만 '신규'로 본다.
  const det = (code) => D?.markets?.[code] || { items: [], auto_checked: null };
  const fresh = (m, topic) => det(m.code).items.filter((x) => x.date > m.checked && (!topic || x.topics.includes(topic)));
  const AUTO_STALE = 8; // 자동 확인이 8일 넘게 안 되면 경고(매일 실행 기준)

  const tm = (...parts) => parts.filter(Boolean).map((x) => `<span>${esc(x)}</span>`).join("");

  function renderTop() {
    const m = R.meta;
    Object.assign(LV, m.legend);
    $("#legend").innerHTML = Object.keys(m.legend).map(chip).join("");
    const autoTxt = D ? ` · 당국 공식 발표 자동 확인 <b>${fmt(D.updated.slice(0, 10))}</b>` : "";
    $("#meta").innerHTML = `현황 문구 사람 검증 <b>${fmt(m.verified_at)}</b>${autoTxt} · 핵심 7개 시장(${m.primary.join("·")}) + 참고 ${m.reference.join("·")}`;
    $("#pAsof").textContent = `(${fmt(m.verified_at)} 기준)`;
    $("#tm-kt").innerHTML = tm(`기준 ${fmt(m.verified_at)} 사람 검증`, "제목·출처 클릭 시 원문");
    $("#tm-up").innerHTML = tm(`기준 오늘 ${fmt(todayStr)}(KST)`, "D-day 자동 계산");
    $("#tm-mx").innerHTML = tm("기준 판정·문구: 시장별 사람 검증일", D ? `공식 발표 자동 확인 ${fmt(D.updated.slice(0, 10))}` : "", "● 표시는 검증일 이후 감지");
    $("#tm-tl").innerHTML = tm(`기준 ${fmt(m.verified_at)} 사람 검증`, "점선은 예정");
    const ktLink = (x, body) => `<a href="${esc(x.url)}" target="_blank" rel="noopener" title="${esc(x.s)}">${body}</a>`;
    $("#kt").innerHTML = R.takeaways.map((k) => {
      const src = k.src || [];
      const h = src.length ? ktLink(src[0], `${esc(k.h)} ↗`) : esc(k.h);
      const chips = src.map((x) => ktLink(x, `${esc(x.l)}<i>${esc(x.s)}</i>`)).join("");
      return `<li><div><b>${h}</b>${esc(k.t)}${chips ? `<span class="ksrc">${chips}</span>` : ""}</div></li>`;
    }).join("");
    $("#foot").textContent = `${m.note} 기준: ${m.base}.`;
  }

  function renderUpcoming() {
    const rows = R.upcoming.filter((u) => days(u.date) >= -7).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 14);
    $("#up").innerHTML = rows.map((u) => `<li>${dday(u.date, u.approx)}<span class="code">${esc(u.code)}</span>
      <div class="x"><a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.text)}</a><span>${esc(host(u.url))}</span></div></li>`).join("")
      || '<li class="empty">예정된 일정이 없습니다.</li>';
  }

  function renderMatrix() {
    const T = R.topics;
    const mk = R.markets.filter((m) => showRef || !m.reference_only);
    $("#mx").innerHTML = `<thead><tr><th>시장</th>${T.map((t) => `<th>${esc(t.n)}</th>`).join("")}<th title="사람 검증일 / 공식 발표 자동 확인일">검증 · 자동확인</th></tr></thead><tbody>${mk.map((m) => {
      const ac = det(m.code).auto_checked;
      const stale = !!D && (!ac || -days(ac) > AUTO_STALE);
      return `<tr tabindex="0" data-code="${m.code}" class="${m.code === sel ? "sel" : ""} ${m.reference_only ? "ref" : ""}">
        <td class="nm">${esc(m.name)}<small>${esc(m.code)}${m.reference_only ? " · 참고" : ""}</small></td>
        ${T.map((t) => { const s = m.status[t.k]; if (!s) return "<td>—</td>"; const n = fresh(m, t.k).length;
          return `<td class="c" title="${esc(s.text)}">${chip(s.lv)}<span class="s">${esc(s.short)}</span>${n ? `<span class="new" title="사람 검증일 이후 공식 발표 ${n}건 자동 감지: 출처 확인 필요">● 신규 공식 발표 ${n}</span>` : ""}</td>`; }).join("")}
        <td class="ck ${stale ? "stale" : ""}" title="${stale ? `공식 발표 자동 확인이 ${AUTO_STALE}일 넘게 안 됨` : ""}">${fmt(m.checked).slice(5)}<small>자동 ${ac ? fmt(ac).slice(5) : "—"}${stale ? " ⚠" : ""}</small></td></tr>`;
    }).join("")}</tbody>`;
    $("#mx tbody").onclick = (e) => { const tr = e.target.closest("tr"); if (tr) select(tr.dataset.code, true); };
    $("#mx tbody").onkeydown = (e) => { if (e.key === "Enter") { const tr = e.target.closest("tr"); if (tr) select(tr.dataset.code, true); } };
  }

  function renderPills() {
    $("#pills").innerHTML = R.markets.filter((m) => showRef || !m.reference_only).map((m) =>
      `<button class="pill ${m.reference_only ? "ref" : ""}" role="tab" type="button" data-code="${m.code}" aria-selected="${m.code === sel}">${esc(m.name)}${fresh(m).length ? ` <span class="pnew" title="검증일 이후 공식 발표">●${fresh(m).length}</span>` : ""}</button>`).join("");
    $("#pills").onclick = (e) => { const b = e.target.closest("button"); if (b) select(b.dataset.code); };
  }

  function renderMarket() {
    const m = M[sel];
    const T = R.topics;
    const hw = m.hanwha?.length
      ? `<div class="hw"><b>한화 해외법인 관점 검토 포인트</b><ul>${m.hanwha.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
    const st = T.map((t) => { const s = m.status[t.k]; if (!s) return ""; const n = fresh(m, t.k).length;
      return `<div class="it ${n ? "has-new" : ""}"><div class="t">${esc(t.n)} ${chip(s.lv)}</div>${esc(s.text)}${n ? `<div class="new">● 검증 후 공식 발표 ${n}건, 아래 목록 확인</div>` : ""}
      ${s.url ? `<div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(host(s.url))} ↗</a></div>` : ""}</div>`; }).join("");
    const iss = m.issues.map((i, n) => `<details class="iss" ${n < 2 ? "open" : ""}><summary><span class="d">${fmt(i.date)}</span>
      <span><b>${esc(i.title)}</b><span class="o">${esc(i.summary)}</span></span></summary>
      <ul>${i.points.map((p) => `<li>${hi(p.text)} <a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.src || host(p.url))} ↗</a></li>`).join("")}</ul></details>`).join("");
    $("#mbody").innerHTML = `<div class="mhead"><h3>${esc(m.name)} <small class="code">${esc(m.en)}</small></h3><span class="reg">${esc(m.regulators)} · 검증 ${fmt(m.checked)}</span></div>
      <p>${esc(m.headline)}</p>${hw}${autoBlock(m)}<div class="tmeta">${tm(`기준 ${fmt(m.checked)} 사람 검증`, det(m.code).auto_checked ? `공식 발표 자동 확인 ${fmt(det(m.code).auto_checked)}` : "")}</div><div class="st">${st}</div>
      <h2 style="font-size:13px;margin:6px 0 2px">최근 이슈</h2><div class="tmeta">${tm(`기준 ${fmt(m.checked)} 사람 검증`, "최신순")}</div>${iss || '<p class="empty">정리된 이슈가 없습니다.</p>'}`;
    const tl = [...m.timeline].sort((a, b) => b.date.localeCompare(a.date));
    $("#tl").innerHTML = tl.map((t) => `<li class="${t.date > todayStr ? "fut" : ""}"><span class="d">${fmt(t.date)}</span>
      <span>${t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.text)}</a>` : esc(t.text)}</span></li>`).join("");
    const fd = F?.markets?.[sel] || [];
    $("#feed").innerHTML = fd.length
      ? fd.map((x) => `<li><div class="dd"><small>${fmt(x.date).slice(5)}</small></div><div class="x">${x.official ? '<span class="off">관보</span>' : ""}
          <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><span>${esc(x.src)}</span></div></li>`).join("")
      : `<li class="empty">${F ? "최근 30일 수집된 기사가 없습니다." : "자동 수집 결과가 아직 없습니다(매일 07시 갱신)."}</li>`;
    $("#tm-feed").innerHTML = F ? tm(`기준 자동 수집 ${fmt(F.updated.slice(0, 10))}`, `최근 ${F.keep_days}일`, "매일 07시") : tm("자동 수집 전");
  }

  function autoBlock(m) {
    const T = Object.fromEntries(R.topics.map((t) => [t.k, t.n]));
    const all = det(m.code).items.slice(0, 5);
    const ac = det(m.code).auto_checked;
    const head = `<h2 style="font-size:13px;margin:0 0 2px">당국 공식 발표 자동 감지</h2><div class="tmeta">${tm(ac ? `기준 자동 확인 ${fmt(ac)}` : "자동 확인 전", "공식 도메인만", "키워드로 주제 분류(판정은 바꾸지 않음)")}</div>`;
    if (!all.length) return `<div class="auto">${head}<p class="empty">${ac ? "최근 감지된 공식 발표가 없습니다." : "다음 자동 실행 후 채워집니다."}</p></div>`;
    return `<div class="auto">${head}<ul class="list">${all.map((x) => `<li class="${x.date > m.checked ? "is-new" : ""}"><div class="dd"><small>${fmt(x.date).slice(5)}</small></div>
      <span class="code">${x.date > m.checked ? "신규" : ""}</span><div class="x"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>
      <span>${esc(x.src)} · ${x.topics.map((k) => esc(T[k] || "기타")).join(", ")}</span></div></li>`).join("")}</ul></div>`;
  }

  function select(code, scroll) {
    sel = code;
    store.set("sel", code);
    document.querySelectorAll("#mx tbody tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.code === code));
    document.querySelectorAll("#pills .pill").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.code === code)));
    renderMarket();
    if (scroll) $("#detail").scrollIntoView({ block: "start", behavior: "smooth" });
  }

  async function load(url, optional) {
    try { const r = await fetch(url, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return await r.json(); }
    catch (e) { if (optional) return null; throw e; }
  }

  async function init() {
    try {
      [R, F, D] = await Promise.all([load("data/regulation.json"), load("data/feed.json", true), load("data/detected.json", true)]);
    } catch (e) {
      $("#meta").textContent = `데이터를 불러오지 못했습니다(${e.message}).`;
      return;
    }
    R.markets.forEach((m) => (M[m.code] = m));
    sel = M[store.get("sel", "")] ? store.get("sel") : R.meta.primary[0];
    if (M[sel].reference_only && !showRef) sel = R.meta.primary[0];
    $("#showRef").checked = showRef;
    $("#showRef").onchange = (e) => {
      showRef = e.target.checked; store.set("ref", showRef);
      if (!showRef && M[sel].reference_only) sel = R.meta.primary[0];
      renderMatrix(); renderPills(); renderMarket();
    };
    $("#printBtn").onclick = () => window.print();
    renderTop(); renderUpcoming(); renderMatrix(); renderPills(); renderMarket();
    fitFrame();
  }

  // 대시보드 iframe 안에 들어갈 때: 내용 높이에 맞춰 바깥 iframe 높이를 계속 맞춘다(같은 출처일 때만).
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
