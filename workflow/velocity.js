// Velocity Clearing(한화생명 75%) 하위 탭. 숫자는 data/velocity.json(workflow/scripts/fetch_velocity.py 매일 수집:
// FINRA BrokerCheck·SEC EDGAR·회사 누리집 재무상태표·SEC XBRL 상장사·한화생명 DART·뉴스), 설명 문구는 data/us_entry.json 의 velocity
// (사람이 원문을 읽고 씀, 출처 목록도 같은 파일). 대시보드에서는 #workflow/velocity 로 들어온다(해외지분투자 절차·미국 진출과 같은 iframe).
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const host = (u) => { try { return new URL(u, location.href).hostname.replace(/^www\./, ""); } catch (_) { return ""; } };
  const fmt = (d) => (d || "").replace(/-/g, ".");
  const ymd = (s) => (/^\d{8}$/.test(s || "") ? `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6)}` : fmt(s));
  const tmeta = (basis, unit) => `${basis ? `<span>기준 ${esc(basis)}</span>` : ""}${unit ? `<span>단위: ${esc(unit)}</span>` : ""}`;
  const num = (v, d = 0) => {
    if (v == null || Number.isNaN(v)) return "—";
    const r = Math.round(v * 10 ** d) / 10 ** d;
    return (r === 0 ? 0 : r).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  const sign = (v, d = 0) => (v == null ? "—" : `<span class="${Math.round(v * 10 ** d) < 0 ? "neg" : ""}">${num(v, d)}</span>`);
  const median = (xs) => { const s = xs.filter((x) => x != null).sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null; };
  const mUsd = (v) => (v == null ? null : v / 1e6);
  const usd = (v) => (v == null ? "—" : v >= 1e9 ? `$${num(v / 1e9, 2)}bn` : `$${num(v / 1e6, 1)}m`);
  const eok = (v) => (v == null ? null : v / 100); // DART 백만원 → 억원
  const ym = (p) => `${String(p).slice(0, 4)}.${String(p).slice(5, 7)}`;
  const yr = (p) => `FY${String(p).slice(0, 4)}`;
  let U, M, V, ST, REF = {};

  const frame = () => { try { return window.frameElement; } catch (_) { return null; } };
  // 출처 번호 [n]: 누르면 아래 출처 목록으로
  const refs = (ids) => (ids && ids.length
    ? `<sup class="r">${ids.filter((id) => REF[id]).map((id) => `<a href="#src-${id}" data-go="src-${id}" title="${esc(U.sources[id].t)}">[${REF[id]}]</a>`).join("")}</sup>` : "");
  // us_entry.json velocity 안에서 쓰는 출처(키가 src로 끝나는 배열)만 이 페이지 출처 목록에
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

  // ---------- 재무 공통 ----------
  // 연차 감사보고서(최근 5년) + 그보다 새 누리집 재무상태표(반기 미감사)
  function bsCols() {
    const fin = (V?.edgar?.fin || []).slice().sort((a, b) => (a.period < b.period ? -1 : 1)).slice(-5);
    const last = fin[fin.length - 1];
    const it = V?.interim && last && V.interim.period > last.period ? V.interim : null;
    return { fin, last, prev: fin[fin.length - 2], it, cur: it || last };
  }
  const audLab = (it) => (it?.audited === false ? "미감사" : it?.audited ? "감사" : ""); // 파일 이름 기준

  // 한화생명 공시: 기간(오래된 것부터)과 쓸 법인 행. Velocity 행이 있으면 그 행, 없으면 미국 중간 법인(연결) 행.
  // 요약재무정보는 각 법인 단독·그 해 1월부터 누적(인수 전 달 포함)이라 기간마다 연환산하면 된다
  function dart() {
    const P = (V?.dart?.periods || []).slice().sort((a, b) => (a.end < b.end ? -1 : 1));
    const k = ["vel", "hold", "nexus"].find((x) => P.some((p) => p.subs?.[x]?.ni != null)) || null;
    const bookP = [...P].reverse().find((p) => p.book?.book != null) || null; // 별도 주석 장부금액이 있는 가장 최근 기간
    return { P, k, row: (p) => (k ? p?.subs?.[k] : null), bookP };
  }
  // ROE(연환산) = 누적 순이익 × 12 / 개월 수 ÷ 기말 자본
  const roeOf = (s, p) => (s?.ni != null && s?.equity > 0 ? (s.ni * 12 / p.months / s.equity) * 100 : null);
  // 소유 구조 지분율: 사람이 적은 값(감사보고서·BrokerCheck), 없으면 한화생명 공시(출자현황 → 종속기업 현황)
  const stakeNum = (c) => {
    if (c.s) return parseFloat(c.s);
    return V?.dart?.invest?.rows?.[c.k]?.end_stake ?? [...(V?.dart?.periods || [])].reverse().find((p) => p.stakes?.[c.k] != null)?.stakes?.[c.k] ?? null;
  };
  // 실효 지분 = 사슬 지분율의 곱(한화생명 → … → Velocity). 하나라도 모르면 사람이 적은 값
  function effStake() {
    const xs = (M.chain || []).slice(1).map(stakeNum);
    return xs.length && xs.every((x) => x != null) ? xs.reduce((a, x) => a * x / 100, 100) : parseFloat(M.stake) || null;
  }

  // 미국 상장 브로커리지 + Velocity: 같은 날짜 자본·총자산 순위, ROE(상장사 최근 12개월 순이익 ÷ 자본)
  function peerRows(cur, vRoe) {
    const P = V?.peers;
    if (!cur || !P?.rows?.length || P.date !== cur.period) return null;
    const rows = P.rows.filter((r) => r.equity?.value != null).map((r) => ({ ...r, eq: r.equity.value, as: r.assets?.value ?? null,
      roe: r.ni?.value != null && r.equity.value > 0 ? (r.ni.value / r.equity.value) * 100 : null }));
    if (!rows.length) return null;
    rows.push({ name: "Velocity Clearing", ticker: "비상장", model: "자체청산 브로커-딜러(한화생명 실효 75%)", eq: cur.equity, as: cur.assets, roe: vRoe, me: true });
    rows.sort((a, b) => b.eq - a.eq);
    const byAs = rows.filter((r) => r.as != null).sort((a, b) => b.as - a.as);
    const byRoe = rows.filter((r) => r.roe != null).sort((a, b) => b.roe - a.roe);
    const me = rows.find((r) => r.me);
    return { rows, n: rows.length, eq: rows.indexOf(me) + 1, as: byAs.indexOf(me) + 1, nAs: byAs.length,
      roe: me.roe != null ? byRoe.indexOf(me) + 1 : null, nRoe: byRoe.length, date: P.date, checked: P.checked,
      medRoe: median(rows.filter((r) => !r.me).map((r) => r.roe)), medEq: median(rows.filter((r) => !r.me).map((r) => r.eq)) };
  }

  // ---------- 핵심 수치 ----------
  function renderKpis(ctx) {
    const { cur, last, it, R, D, dl, eff } = ctx;
    const s = D.row(dl), bc = V?.brokercheck || {};
    const disc = Object.values(bc.disclosures || {}).reduce((a, b) => a + (b || 0), 0);
    const st = Object.values(bc.disc_status || {}), open = st.reduce((a, x) => a + (x.pending || 0) + (x.appeal || 0), 0);
    const L = (M.licenses || []).find((r) => r.auto === "disc")?.latest;
    const nc = cur?.net_capital != null ? cur : last;
    const bk = ctx.book;
    const k = [
      { t: "한화생명 실효 지분", v: eff != null ? `${num(eff, eff % 1 ? 1 : 0)}%` : "—", d: "Nexus Clearing 지분 인수 · 2025.07.30 완료", src: ["v_done"] },
      { t: "출자 장부가", v: bk ? `${num(eok(bk.book))}억원` : "—",
        d: bk ? `${D.bookP.label} 한화생명 별도 · ${bk.prev_book != null && bk.prev_book !== bk.book ? `전기말 ${num(eok(bk.prev_book))}억원` : "취득 후 변동 없음"}` : "한화생명 공시(DART) 수집 전" },
      { t: "순이익", v: s?.ni != null ? `${num(eok(s.ni))}억원` : "—",
        d: s ? `${dl.label} 누적${eff != null ? ` · 한화생명 몫 ${num(eok(s.ni * eff / 100))}억원` : ""}` : "한화생명 공시(DART) 수집 전", neg: s?.ni < 0 },
      { t: "ROE(연환산)", v: ctx.vRoeLatest != null ? `${num(ctx.vRoeLatest, 1)}%` : "—",
        d: ctx.vRoeLatest != null ? `${dl.label} · 상장사 중앙값 ${R?.medRoe != null ? `${num(R.medRoe, 1)}%` : "—"}` : "한화생명 공시(DART) 수집 전" },
      { t: "자본(회원 지분)", v: usd(cur?.equity), d: it ? `${ym(it.period)} ${audLab(it)} · ${yr(last.period)} ${usd(last.equity)}` : last ? `${yr(last.period)} 감사` : "" },
      { t: "순자본(15c3-1)", v: usd(nc?.net_capital), d: nc?.required ? `최소 요건 ${usd(nc.required)}의 ${num(nc.net_capital / nc.required, 1)}배` : "" },
      { t: "상장 브로커리지 대비", v: R ? (R.roe ? `ROE ${R.roe}위 · 자본 ${R.eq}위` : `자본 ${R.eq}위`) : "—",
        d: R ? `${R.n}곳 중 · 총자산 ${R.as}위 · ${fmt(R.date)}` : "상장사 값은 다음 자동 수집 때" },
      { t: "규제 공시", v: disc ? `${disc}건${st.length ? (open ? ` · 진행 ${open}` : " 종결") : ""}` : "—",
        d: bc.disc_latest && L && bc.disc_latest > L.d ? `가장 최근 ${fmt(bc.disc_latest)} 개시` : L ? `최근 ${fmt(L.d)} 합의(벌금 $1.0m)` : "", src: ["v_bcpdf"] },
    ];
    $("#kpis").innerHTML = k.map((x) => `<div class="kpi"><span>${esc(x.t)}${refs(x.src)}</span><b${x.neg ? ' class="neg"' : ""}>${esc(x.v)}</b><small>${esc(x.d)}</small></div>`).join("");
  }

  // ---------- 투자·소유 구조 ----------
  function renderInvest(ctx) {
    const { D, dl, eff } = ctx;
    const chain = M.chain || [];
    const pctTxt = (v) => (v == null ? "" : `${num(v, v % 1 ? 1 : 0)}%`);
    $("#chain").innerHTML = chain.map((c, i) => `${i ? `<i>${esc(pctTxt(stakeNum(c)))}</i>` : ""}<span class="${i === 0 ? "hw" : i === chain.length - 1 ? "me" : ""}" title="${esc(c.full || c.n)}">${esc(c.n)}</span>`).join("")
      + (M.chain_src ? refs(M.chain_src) : "") + (M.chain_note ? `<small class="cn">${esc(M.chain_note)}</small>` : "");
    const bP = D.bookP, bk = ctx.book, s = D.row(dl);
    const I = V?.dart?.invest, ir = ctx.inv;
    $("#tm-inv").innerHTML = tmeta(bP ? `${bP.label} ${bP.report.name.replace(/\s*\(.*\)$/, "")}(${ymd(bP.report.rcept_dt)} 공시)` : "DART", "억원 · %");
    const rows = [];
    if (bk) rows.push(`<tr><td class="k">출자 장부가</td><td class="n"><b>${num(eok(bk.book))}</b></td><td><a href="${esc(bP.report.url)}" target="_blank" rel="noopener">${esc(bk.name)}</a>${bk.activity ? `(${esc(bk.activity)})` : ""} · 한화생명 별도재무제표 주석 종속기업투자${bk.stake != null ? ` · 지분 ${num(bk.stake, bk.stake % 1 ? 1 : 0)}%` : ""}${bk.prev_book != null ? ` · 전기말 ${num(eok(bk.prev_book))}` : ""}</td></tr>`);
    if (s?.ni != null && eff != null) rows.push(`<tr><td class="k">한화생명 몫 순이익</td><td class="n"><b>${sign(eok(s.ni * eff / 100))}</b></td><td>${esc(dl.label)} 누적 · Velocity 순이익 ${num(eok(s.ni))} × 실효 지분 ${num(eff, eff % 1 ? 1 : 0)}%(사업결합 공정가치 조정 전)</td></tr>`);
    if (bk && s?.ni != null && eff != null) rows.push(`<tr><td class="k">출자 대비 연환산</td><td class="n">${sign((s.ni * eff / 100) * 12 / dl.months / bk.book * 100, 1)}%</td><td>한화생명 몫 순이익 × 12/${dl.months} ÷ 출자 장부가</td></tr>`);
    $("#inv").innerHTML = rows.length ? `<table><tbody>${rows.join("")}</tbody></table>`
      : '<p class="empty">한화생명 별도재무제표 주석(DART)의 출자 장부가는 다음 자동 수집 때 채워집니다.</p>';
    // 같은 보고서 '타법인 출자현황'과 금액이 다르면 원문 그대로 함께 적는다(1백만원 넘게 차이날 때만)
    const diff = bk && ir?.end_book != null && Math.abs(ir.end_book - bk.book) > 1;
    $("#deal").innerHTML = `${M.deal ? `${esc(M.deal.t)}${refs(M.deal.src)}` : ""}${diff
      ? ` <span class="sub2">${esc(I.label)} 보고서 '타법인 출자현황' 표에는 같은 법인 장부가액이 ${num(eok(ir.end_book))}억원${ir.first_date ? `(최초 취득 ${fmt(ir.first_date)})` : ""}으로 적혀 있어 주석과 ${num(eok(Math.abs(bk.book - ir.end_book)))}억원 다르다. 위 표는 감사·검토를 받는 재무제표 주석 값.</span>` : ""}`;
  }

  // ---------- 손익(한화생명 공시) ----------
  function renderPL(ctx) {
    const { D, eff } = ctx;
    const P = D.P.filter((p) => D.row(p)).slice(-5);
    if (!P.length) {
      $("#pl").innerHTML = '<p class="empty">한화생명 분기·반기·사업보고서(DART)의 미국 법인 손익은 다음 자동 수집 때 채워집니다.</p>';
      $("#tm-pl").innerHTML = tmeta("DART", "억원");
      return;
    }
    const s0 = D.row(P[P.length - 1]);
    const who = D.k === "vel" ? `${s0.name} 단독` : `${s0.name}(Velocity 포함 연결)`;
    $("#tm-pl").innerHTML = tmeta(`${who} · 각 기간 1월부터 누적`, "억원 · %");
    const head = P.map((p) => `<th class="n"><a href="${esc(p.report.url)}" target="_blank" rel="noopener" title="${esc(p.report.name)} · ${ymd(p.report.rcept_dt)} 공시">${esc(p.label)}</a></th>`).join("");
    const line = (lab, f, bold) => `<tr><td class="k">${lab}</td>${P.map((p) => { const v = f(D.row(p), p); return `<td class="n">${bold ? `<b>${sign(v)}</b>` : sign(v)}</td>`; }).join("")}</tr>`;
    $("#pl").innerHTML = `<table><thead><tr><th>항목</th>${head}</tr></thead><tbody>
      ${line("영업수익", (s) => eok(s.rev))}${line("당기순이익", (s) => eok(s.ni), true)}
      ${D.k === "vel" && eff != null ? line(`한화생명 몫(${num(eff, eff % 1 ? 1 : 0)}%)`, (s) => (s.ni == null ? null : eok(s.ni * eff / 100))) : ""}
      ${line("자본", (s) => eok(s.equity))}${line("자산", (s) => eok(s.assets))}
      <tr><td class="k">ROE(연환산)</td>${P.map((p) => `<td class="n">${sign(roeOf(D.row(p), p), 1)}</td>`).join("")}</tr></tbody></table>`;
    // 분기 순이익: 같은 해 바로 앞 기간 누적과의 차이(1Q는 그대로). 석 달이 아닌 구간(첫 공시 9개월 등)은 막대에서 뺀다
    const all = D.P.filter((p) => D.row(p)?.ni != null);
    const q = all.map((p) => {
      const before = all.filter((x) => x.year === p.year && x.months < p.months).pop();
      const span = (p.months - (before ? before.months : 0)) / 3;
      const ok = span === 1 && (before || p.months === 3);
      const rev = D.row(p).rev != null && (!before || D.row(before).rev != null) ? eok(D.row(p).rev - (before ? D.row(before).rev : 0)) : null;
      return ok ? { lab: `${p.months / 3}Q${p.year.slice(2)}`, v: eok(D.row(p).ni - (before ? D.row(before).ni : 0)), rev } : null;
    }).filter(Boolean).slice(-6);
    $("#plq").innerHTML = q.length > 1 ? qbars(q) : "";
    $("#plNote").innerHTML = `${esc(M.pl_note || "")}${refs(M.pl_src)}`;
  }

  // 분기 순이익 막대(0선 기준 위 양수·아래 음수, 값은 막대 끝). 마우스를 올리면 영업수익도
  function qbars(q) {
    const W = 460, H = 88, T = 13, B = 15;
    const hi = Math.max(0, ...q.map((x) => x.v)), lo = Math.min(0, ...q.map((x) => x.v));
    const sc = (H - T - B) / ((hi - lo) || 1), z = T + hi * sc;
    const gap = (W - 20) / q.length, bw = Math.min(46, gap - 14);
    const bars = q.map((x, i) => {
      const cx = 10 + gap * (i + .5), h = Math.max(1, Math.abs(x.v) * sc), y = x.v >= 0 ? z - h : z;
      return `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="var(${x.v < 0 ? "--neg" : "--pos"})" fill-opacity=".85"><title>${esc(x.lab)} 순이익 ${num(x.v)}억원${x.rev != null ? ` · 영업수익 ${num(x.rev)}억원` : ""}</title></rect>`
        + `<text class="lab" x="${cx.toFixed(1)}" y="${(x.v >= 0 ? y - 3 : y + h + 10).toFixed(1)}" text-anchor="middle">${num(x.v)}</text>`
        + `<text x="${cx.toFixed(1)}" y="${H - 3}" text-anchor="middle">${esc(x.lab)}</text>`;
    }).join("");
    return `<h3>분기 순이익 <small style="font-weight:400;color:var(--muted)">누적 차이로 계산 · 억원</small></h3>
      <svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;max-width:${W}px" role="img" aria-label="분기 순이익">
      <line x1="4" x2="${W - 4}" y1="${z.toFixed(1)}" y2="${z.toFixed(1)}" stroke="var(--line)"/>${bars}</svg>`;
  }

  // ---------- 재무상태(감사보고서·누리집) ----------
  function renderBS(ctx) {
    const { fin, it } = ctx;
    const rowsF = [["총자산", "assets"], ["부채", "liab"], ["자본(회원 지분)", "equity"], ["순자본", "net_capital"], ["최소 순자본", "required"], ["초과 순자본", "excess"]];
    const cols = it ? [...fin, it] : fin;
    const head = (f) => (f === it
      ? `<th class="n"><a href="${esc(it.url)}" target="_blank" rel="noopener" title="회사 누리집 재무상태표">${ym(it.period)}</a>${audLab(it) ? `<span class="sub">${audLab(it)}</span>` : ""}</th>`
      : `<th class="n"><a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.acc || "")}${f.filed ? ` · ${fmt(f.filed)} 공시` : ""}">${yr(f.period)}</a></th>`);
    if (!fin.length) { $("#bs").outerHTML = '<p class="empty" id="bs">연차 감사보고서 데이터를 불러오지 못했습니다.</p>'; return; }
    $("#bs").innerHTML = `<thead><tr><th>항목</th>${cols.map(head).join("")}</tr></thead>
      <tbody>${rowsF.map(([lab, key]) => `<tr><td class="k">${lab}</td>${cols.map((f) => `<td class="n">${key === "equity" ? `<b>${num(mUsd(f[key]), 1)}</b>` : num(mUsd(f[key]), 1)}</td>`).join("")}</tr>`).join("")}</tbody>`;
    $("#tm-bs").innerHTML = tmeta(`각 연도 12월 31일 감사받은 재무상태표${it ? ` · ${ym(it.period)}${audLab(it) ? ` ${audLab(it)}` : ""}: 회사 누리집` : ""} · Velocity 단독`, "US$ m");
    $("#bsNote").innerHTML = `${esc(M.fin_note)}${refs(M.fin_src)}`;
  }

  // ---------- 순위 ----------
  function renderRank(ctx) {
    const { R, cur } = ctx;
    if (!R) {
      $("#rank").outerHTML = '<p class="empty" id="rank">상장사 비교 값은 다음 자동 수집(SEC XBRL) 때 채워집니다.</p>';
      $("#tm-rank").innerHTML = tmeta("SEC XBRL", "US$ m · %");
      return;
    }
    const d = cur.period;
    const odd = (r) => r.equity?.end && r.equity.end !== d;
    $("#rank").innerHTML = `<thead><tr><th class="n">순위</th><th>회사 <small style="font-weight:400">(마우스: 사업 모델)</small></th><th class="n">자본</th><th class="n">총자산</th><th class="n">ROE</th></tr></thead>
      <tbody>${R.rows.map((r, i) => `<tr${r.me ? ' class="me"' : ""}><td class="rk">${i + 1}</td><td class="k" title="${esc(r.model || "")}">${esc(r.name)} <small>${esc(r.ticker)}</small></td>
        <td class="n"${odd(r) ? ` title="${esc(r.equity.end)} 기준"` : ""}>${num(mUsd(r.eq), 0)}${odd(r) ? "*" : ""}</td>
        <td class="n">${r.as == null ? "—" : num(mUsd(r.as), 0)}</td><td class="n"${r.ni?.how ? ` title="${esc(`${r.ni.tag} · ${r.ni.how}`)}"` : ""}>${sign(r.roe, 1)}</td></tr>`).join("")}</tbody>`;
    const oddRows = R.rows.filter(odd);
    $("#rankNote").innerHTML = `자본 <b>${R.n}곳 중 ${R.eq}위</b>, 총자산 ${R.nAs}곳 중 ${R.as}위${R.roe ? `, ROE ${R.nRoe}곳 중 ${R.roe}위` : ""}. 상장사는 미국 본사 NYSE·NYSE American·나스닥 상장사 중 증권 중개·청산·시장조성·자산관리 중개가 주업인 ${R.n - 1}곳(자문 전업 IB·거래소·보험 겸업사 제외). ${esc(M.rank_note)} 상장사 ROE는 같은 날로 끝나는 최근 12개월 순이익 ÷ 자본(비지배지분 포함 자본이면 순이익도 포함)${ctx.vRoe != null ? `, Velocity ROE는 ${esc(ctx.dq.label)} 한화생명 공시 연환산` : ""}.${oddRows.length ? ` *는 결산월이 달라 가장 가까운 분기말 값(${oddRows.map((r) => `${esc(r.ticker)} ${fmt(r.equity.end)}`).join(", ")}).` : ""}${refs(M.rank_src)}`;
    $("#tm-rank").innerHTML = tmeta(`${fmt(d)} · 상장사 SEC XBRL(10-K·10-Q)${R.checked ? ` ${fmt(R.checked)} 수집` : ""}`, "US$ m · %");
  }

  // ---------- 위치: 규모(자본, 로그 눈금) × 수익성(ROE) 사분면 ----------
  // 가로·세로 가운데 선은 상장사 16곳 중앙값. 오른쪽 위 = 크고 잘 버는 곳(전략 인사이트 탭 지도와 같은 틀)
  function renderQuad(ctx) {
    const { R } = ctx;
    const pts = (R?.rows || []).filter((r) => r.roe != null && r.eq > 0);
    if (pts.filter((r) => !r.me).length < 3) {
      $("#quad").innerHTML = '<p class="empty">상장사 순이익(SEC XBRL)은 다음 자동 수집 때 채워집니다.</p>';
      $("#tm-quad").innerHTML = tmeta("SEC XBRL", "가로 US$(로그 눈금) · 세로 ROE %");
      return;
    }
    const W = 460, H = 270, L0 = 34, B0 = 20, T0 = 8, R0 = 8, LO = -20, HI = 60;
    const clampY = (v) => Math.max(LO, Math.min(HI, v));
    const lx = pts.map((p) => Math.log10(p.eq)), ys = pts.map((p) => clampY(p.roe));
    const x0 = Math.floor(Math.min(...lx) * 2) / 2, x1 = Math.ceil(Math.max(...lx) * 2) / 2;
    const y0 = Math.min(0, Math.floor(Math.min(...ys) / 10) * 10), y1 = Math.max(10, Math.ceil(Math.max(...ys) / 10) * 10);
    const X = (v) => L0 + ((Math.log10(v) - x0) / (x1 - x0 || 1)) * (W - L0 - R0);
    const Y = (v) => H - B0 - ((clampY(v) - y0) / (y1 - y0 || 1)) * (H - B0 - T0);
    const mx = R.medEq, my = R.medRoe;
    const xt = [];
    for (let e = Math.ceil(x0); e <= x1; e += 1) xt.push(10 ** e);
    const tick = (v) => (v >= 1e9 ? `$${v / 1e9}bn` : `$${v / 1e6}m`);
    let grid = xt.map((v) => `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${T0}" y2="${H - B0}" stroke="var(--line)" stroke-dasharray="2 3"/><text x="${X(v).toFixed(1)}" y="${H - 6}" text-anchor="middle">${tick(v)}</text>`).join("");
    for (let v = y0; v <= y1; v += 10) grid += `<line x1="${L0}" x2="${W - R0}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line)"${v === 0 ? "" : ' stroke-dasharray="2 3"'}/><text x="${L0 - 4}" y="${(Y(v) + 3).toFixed(1)}" text-anchor="end">${v}%</text>`;
    const med = `<line x1="${X(mx).toFixed(1)}" x2="${X(mx).toFixed(1)}" y1="${T0}" y2="${H - B0}" stroke="var(--accent)" stroke-opacity=".4"/><line x1="${L0}" x2="${W - R0}" y1="${Y(my).toFixed(1)}" y2="${Y(my).toFixed(1)}" stroke="var(--accent)" stroke-opacity=".4"/>`;
    // 네 칸 이름(모서리)
    const qn = [[L0 + 4, T0 + 10, "start", "소형 · 고수익"], [W - R0 - 4, T0 + 10, "end", "대형 · 고수익"], [L0 + 4, H - B0 - 5, "start", "소형 · 저수익"], [W - R0 - 4, H - B0 - 5, "end", "대형 · 저수익"]]
      .map(([x, y, a, t]) => `<text x="${x}" y="${y}" text-anchor="${a}" style="fill:var(--accent-ink);fill-opacity:.75;font-weight:600">${t}</text>`).join("");
    const me = pts.find((p) => p.me), peers = pts.filter((p) => !p.me);
    const tip = (p) => `${p.name}${p.me ? "" : `(${p.ticker})`}: 자본 ${usd(p.eq)} · ROE ${num(p.roe, 1)}%${p.roe !== clampY(p.roe) ? "(눈금 끝에 붙임)" : ""}`;
    const dots = peers.map((p) => `<circle cx="${X(p.eq).toFixed(1)}" cy="${Y(p.roe).toFixed(1)}" r="4.5" fill="var(--muted)" fill-opacity=".9" stroke="var(--surface)" stroke-width="1.5"><title>${esc(tip(p))}</title></circle>`).join("");
    const meDot = me ? `<rect x="${(X(me.eq) - 5.5).toFixed(1)}" y="${(Y(me.roe) - 5.5).toFixed(1)}" width="11" height="11" transform="rotate(45 ${X(me.eq).toFixed(1)} ${Y(me.roe).toFixed(1)})" fill="var(--accent)" stroke="var(--surface)" stroke-width="1.5"><title>${esc(tip(me))}</title></rect>` : "";
    const labs = svgLabels([
      ...(me ? [{ x: X(me.eq), y: Y(me.roe), r: 7, t: "Velocity", style: "fill:var(--accent-ink);font-weight:700" }] : []),
      ...peers.slice().sort((a, b) => b.eq - a.eq).map((p) => ({ x: X(p.eq), y: Y(p.roe), r: 4.5, t: p.ticker })),
    ], W);
    $("#tm-quad").innerHTML = tmeta(`${fmt(R.date)} 자본 · ROE(상장사 최근 12개월${me ? `, Velocity ${ctx.dq.label} 연환산` : ""})`, "가로 US$(로그 눈금) · 세로 %");
    $("#quad").innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block" role="img" aria-label="미국 상장 브로커리지 대비 규모와 수익성">${grid}${med}${qn}${dots}${meDot}${labs}</svg>
      <div class="legend"><span><i style="background:var(--muted)"></i>미국 상장 브로커리지 ${peers.length}곳</span><span><i class="dia" style="background:var(--accent)"></i>Velocity</span><span><i style="background:var(--accent);opacity:.45;border-radius:0;height:2px;width:12px;vertical-align:3px"></i>상장사 중앙값(자본 ${usd(mx)} · ROE ${num(my, 1)}%)</span></div>
      <p class="small">${me ? `Velocity는 <b>${esc(quadName(me, mx, my))}</b> 칸: 자본은 중앙값의 ${num(me.eq / mx, 2)}배, ROE는 중앙값보다 ${num(Math.abs(me.roe - my), 1)}%p ${me.roe >= my ? "높음" : "낮음"}. ` : "Velocity ROE는 재무상태 날짜와 같은 기간의 한화생명 공시가 들어오면 점으로 나옵니다. "}자본은 상장사 그룹 연결(비지배지분 포함)·Velocity 브로커-딜러 단독, ROE는 ${LO}~${HI}% 밖이면 끝에 붙였습니다. 표는 왼쪽 순위 표와 같습니다.</p>`;
  }
  const quadName = (p, mx, my) => `${p.eq >= mx ? "대형" : "소형"} · ${p.roe >= my ? "고수익" : "저수익"}`;

  // 겹치지 않게 라벨 놓기: 점 오른쪽 → 위아래로 비켜 → 그래도 겹치면 생략(전략 인사이트 탭과 같은 규칙)
  function svgLabels(items, W) {
    const placed = [];
    return items.map((p) => {
      const w = [...p.t].reduce((a, c) => a + (c.charCodeAt(0) > 255 ? 10 : 6), 0);
      const flip = p.x + p.r + 3 + w > W - 4, bx = flip ? p.x - p.r - 3 - w : p.x + p.r + 3;
      for (const dy of [0, -11, 11, -22, 22]) {
        const y = p.y + 3 + dy;
        if (!placed.some((q) => bx < q.x + q.w && q.x < bx + w && Math.abs(y - q.y) < 10.5)) {
          placed.push({ x: bx, y, w });
          return `<text x="${(flip ? bx + w : bx).toFixed(1)}" y="${y.toFixed(1)}"${flip ? ' text-anchor="end"' : ""}${p.style ? ` style="${p.style}"` : ' class="lab"'}>${esc(p.t)}</text>`;
        }
      }
      return "";
    }).join("");
  }

  // ---------- 라이선스·등록(개수·목록은 BrokerCheck 자동, 설명은 사람이 쓴 문구) ----------
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
  function renderLic() {
    const bc = V?.brokercheck || {}, n = bc.counts || {}, sros = bc.sros || [];
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
    $("#lic").innerHTML = `<tbody>${M.licenses.map((r) =>
      `<tr><td class="k">${esc(r.k)}</td><td>${r.auto && auto[r.auto] ? auto[r.auto](r) : ""}${esc(r.t)}${refs(r.src)}</td></tr>`).join("")}</tbody>`;
    $("#tm-lic").innerHTML = tmeta(bc.checked ? `FINRA BrokerCheck ${fmt(bc.checked)}${bc.sros_checked && bc.sros_checked !== bc.checked ? ` · 거래소 목록 ${fmt(bc.sros_checked)}` : ""}` : "FINRA BrokerCheck", "곳 · 종 · 건");
  }

  // ---------- 인수 경과·개요 ----------
  const POS = [[/^CHIEF EXECUTIVE/, "CEO"], [/^CO[- ]?PRESIDENT/, "공동 사장"], [/^PRESIDENT/, "사장"], [/^CHIEF FINANCIAL OFFICER\/FINOP/, "CFO·FINOP"],
    [/^CHIEF FINANCIAL/, "CFO"], [/^CHIEF OPERATING/, "COO"], [/^CHIEF OPERATIONS/, "운영 책임자"], [/^CHIEF COMPLIANCE/, "CCO"],
    [/^CHIEF TECHNOLOGY/, "CTO"], [/^CHIEF RISK/, "CRO"]];
  const person = (n) => { // 'LOGAN, MICHAEL JAMES' → 'Michael Logan'
    const [last, rest = ""] = String(n).split(/,\s*/);
    const tc = (s) => s.toLowerCase().replace(/(^|[\s'-])\p{L}/gu, (c) => c.toUpperCase());
    return `${tc(rest.split(/\s+/)[0] || "")} ${tc(last)}`.trim();
  };
  function renderStory() {
    const bc = V?.brokercheck || {};
    $("#tl").innerHTML = `<tbody>${M.timeline.map((r) => `<tr><td class="d">${fmt(r.d)}</td><td>${esc(r.t)}${refs(r.src)}</td></tr>`).join("")}</tbody>`;
    $("#tm-tl").innerHTML = tmeta(`원문 검증 ${fmt(M.verified_at)}`);
    const groups = [];
    for (const o of bc.officers || []) {
      const lab = POS.find(([re]) => re.test(String(o.position || "").toUpperCase()))?.[1];
      if (!lab || !/,/.test(o.name || "")) continue; // 법인 소유자(SOLE MEMBER 등)는 소유 구조 줄에
      const g = groups.find((x) => x.lab === lab) || (groups.push({ lab, names: [] }), groups[groups.length - 1]);
      g.names.push(person(o.name));
    }
    const prof = M.profile.map((r) => `<tr><td class="k">${esc(r.k)}</td><td>${esc(r.t)}${refs(r.src)}</td></tr>`);
    if (groups.length) prof.push(`<tr><td class="k">경영진</td><td>${groups.map((g) => `${esc(g.lab)} ${esc(g.names.join("·"))}`).join(" · ")}${refs(M.officers_src)}</td></tr>`);
    $("#prof").innerHTML = `<tbody>${prof.join("")}</tbody>`;
    $("#tm-prof").innerHTML = tmeta(`원문 검증 ${fmt(M.verified_at)}${bc.checked ? ` · 경영진 BrokerCheck ${fmt(bc.checked)}` : ""}`);
  }

  function renderFeed(ctx) {
    const ed = V?.edgar || {}, fins = new Map(ctx.fin.map((f) => [f.acc, f]));
    const fl = (ed.filings || []).slice(0, 5);
    $("#filings").innerHTML = fl.length ? fl.map((f) => `<li><time>${fmt(f.filed)}</time><span><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.form)} 연차 감사보고서${/\/A$/.test(f.form) ? "(정정)" : ""} · ${yr(f.period)}</a>${fins.get(f.acc)?.url ? ` <small><a href="${esc(fins.get(f.acc).url)}" target="_blank" rel="noopener">PDF</a></small>` : ""}</span></li>`).join("")
      : '<li class="empty">공시 목록을 불러오지 못했습니다.</li>';
    const nw = V?.news || [];
    $("#news").innerHTML = nw.length ? nw.map((x) => `<li><time>${fmt(x.date)}</time><span><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><small>${esc(x.src)}</small></span></li>`).join("")
      : '<li class="empty">최근 2년 안 기사가 없습니다.</li>';
    $("#tm-feed").innerHTML = tmeta([ed.checked ? `EDGAR ${fmt(ed.checked)}` : "", V?.news_checked ? `뉴스 ${fmt(V.news_checked)} 확인(최근 2년)` : ""].filter(Boolean).join(" · "));
  }

  // ---------- 출처(반기 원문 점검 결과를 붙인다) ----------
  const srcState = (u) => ST?.sources?.[u] || null;
  // 점검 실패 사유: 404는 주소 문제, 403·429·503·봇 확인은 사이트가 자동 접속을 막은 경우, 인증서, 그 밖은 일시 오류
  const failNote = (err) => (/^HTTP (404|410)/.test(err) ? "주소 확인 필요(404)"
    : /^HTTP (403|429|503)|봇 확인/.test(err) ? "사이트가 자동 접속을 막음"
    : /CERTIFICATE|SSL/.test(err) ? "사이트 보안 인증서 오류" : "일시 오류");
  function renderSources(ids, ctx) {
    const auto = [...new Map([...ctx.D.P.map((p) => p.report), ...(V?.dart?.invest ? [V.dart.invest.report] : [])].map((r) => [r.rcept_no, r])).values()];
    $("#src").innerHTML = ids.map((id) => {
      const s = U.sources[id], st = srcState(s.u);
      const rev = st?.changed_at && st.changed_at > M.verified_at;
      const chk = st?.checked ? ` · ${st.kind === "원문" ? "원문 점검" : "링크 확인"} ${fmt(st.checked)}${st.err ? ` · 최근 점검 실패(${failNote(st.err)})` : ""}`
        : st?.err ? ` · 자동 점검 안 됨(${failNote(st.err)})` : "";
      return `<li id="src-${id}"><a href="${esc(s.u)}" target="_blank" rel="noopener">${esc(s.t)}</a> <small>${esc(s.d)} · ${esc(host(s.u))}${chk}</small>${rev ? ` <span class="rev">● 개정 감지·검토 필요(${fmt(st.changed_at)})</span>` : ""}</li>`;
    }).join("") + auto.map((r) => `<li><a href="${esc(r.url)}" target="_blank" rel="noopener">한화생명 ${esc(r.name)}</a> <small>${ymd(r.rcept_dt)} 공시 · dart.fss.or.kr · 종속기업 요약재무정보·종속기업투자·타법인 출자현황 자동 수집</small></li>`).join("");
    $("#srcMeta").textContent = `${ids.length + auto.length}건 · 공식 원문은 반기마다 변경 점검, 기사·발표문은 링크 확인, DART 보고서는 매일 새 공시 확인`;
  }

  // ---------- 배치: 카드를 중요한 순서대로 가장 짧은 칸 아래에(빈칸 최소화) ----------
  let CARDS = [], lastW = 0;
  function layout(force) {
    const host = $("#mason");
    const w = host.clientWidth;
    if (!force && Math.abs(w - lastW) < 2) return;
    lastW = w;
    const n = w >= 1180 ? 3 : w >= 760 ? 2 : 1;
    const cols = Array.from({ length: n }, () => Object.assign(document.createElement("div"), { className: "col" }));
    host.replaceChildren(...cols);
    for (const c of CARDS) cols.reduce((a, b) => (b.offsetHeight < a.offsetHeight ? b : a)).appendChild(c);
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
  // 대시보드 주소를 지금 화면에 맞춘다(#workflow/velocity). hashchange 를 일으키지 않게 replaceState
  function setParentHash(h) {
    try { if (frame() && window.parent.location.hash.startsWith("#workflow")) window.parent.history.replaceState(null, "", h); } catch (_) { /* 교차 출처 */ }
  }
  function wire() {
    document.addEventListener("click", (e) => {
      const g = e.target.closest("[data-go]");
      if (g) { e.preventDefault(); go(g.dataset.go); return; }
      const b = e.target.closest("[data-to]");
      if (b) setParentHash(b.dataset.to === "index" ? "#workflow" : `#workflow/${b.dataset.to}`);
    });
    let raf = 0;
    window.addEventListener("resize", () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => layout()); });
    window.addEventListener("beforeprint", () => layout(true));
    document.fonts?.ready?.then(() => layout(true));
    const fe = frame();
    if (!fe) return;
    setParentHash("#workflow/velocity");
    const fit = () => { fe.style.height = `${document.documentElement.scrollHeight + 4}px`; };
    fit();
    if ("ResizeObserver" in window) new ResizeObserver(fit).observe(document.body);
    // 위쪽 탭 메뉴로 '해외지분투자 Workflow'(#workflow)·단계(#workflow/s10)·미국 진출(#workflow/us)을 고르면 그쪽으로
    const onHash = () => {
      let h = "";
      try { h = window.parent.location.hash; } catch (_) { return; }
      if (h.startsWith("#workflow") && h !== "#workflow/velocity") location.replace(h === "#workflow/us" ? "us.html" : "index.html");
    };
    window.parent.addEventListener("hashchange", onHash);
    window.addEventListener("pagehide", () => { try { window.parent.removeEventListener("hashchange", onHash); } catch (_) { /* 무시 */ } });
  }

  async function load(url, optional) {
    try { const r = await fetch(url, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return await r.json(); }
    catch (e) { if (optional) return null; throw e; }
  }

  async function init() {
    try {
      [U, V, ST] = await Promise.all([load("data/us_entry.json"), load("data/velocity.json", true), load("../guide/data/source_status.json", true)]);
    } catch (e) {
      $("#meta").textContent = `데이터를 불러오지 못했습니다(${e.message}).`;
      return;
    }
    M = U.velocity;
    const ids = Object.keys(U.sources).filter((id) => used(M).has(id));
    ids.forEach((id, i) => { REF[id] = i + 1; });
    const b = bsCols(), D = dart();
    const dl = [...D.P].reverse().find((p) => D.row(p)?.ni != null) || null; // 가장 최근 공시 기간
    // 사분면·순위의 Velocity ROE는 재무상태 날짜와 같은 기간(없으면 그 전 90일 안 기간)의 공시로
    const dq = b.cur ? [...D.P].reverse().find((p) => D.row(p)?.ni != null && p.end <= b.cur.period && (new Date(b.cur.period) - new Date(p.end)) / 864e5 <= 92) : null;
    const vRoe = dq ? roeOf(D.row(dq), dq) : null;
    const R = peerRows(b.cur, vRoe);
    const inv = (() => { const r = V?.dart?.invest?.rows || {}; return r.hold || r.nexus || Object.values(r)[0] || null; })();
    const ctx = { ...b, D, dl, dq, vRoe, vRoeLatest: dl ? roeOf(D.row(dl), dl) : null, R, inv, book: D.bookP?.book || null, eff: effStake() };
    $("#lead").textContent = M.lead;
    const parts = [V?.brokercheck?.checked ? `BrokerCheck ${fmt(V.brokercheck.checked)}` : "", V?.edgar?.checked ? `EDGAR ${fmt(V.edgar.checked)}` : "",
      dl ? `한화생명 DART ${dl.label}(${ymd(dl.report.rcept_dt)} 공시)` : "", V?.peers?.checked ? `상장사 SEC XBRL ${fmt(V.peers.checked)}` : "", V?.news_checked ? `뉴스 ${fmt(V.news_checked)}` : ""].filter(Boolean);
    $("#meta").innerHTML = `자동 수집 <b>${esc(parts.join(" · ") || "—")}</b> · 설명 원문 검증 <b>${fmt(M.verified_at)}</b> · 미국 측 설립·인수 요건은 <a href="us.html" data-to="us">미국 진출</a>`;
    renderKpis(ctx); renderInvest(ctx); renderPL(ctx); renderBS(ctx); renderRank(ctx); renderQuad(ctx); renderLic(); renderStory(); renderFeed(ctx); renderSources(ids, ctx);
    $("#printBtn").onclick = () => window.print();
    CARDS = [...$("#mason").children];
    layout(true);
    wire();
  }
  init();
})();
