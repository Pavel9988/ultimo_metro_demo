// Componenti di presentazione: esito, indicatori, legenda, dettaglio, tabelle, ugelli e spiegazioni.

import { $, esc, fmt, STATUS, STATUS_BY_KEY, DIFF, badge, rampColor } from "./util.js";

// ---------- colori per vista ----------
export function colorsFor(view, result, task) {
  const n = task.classes.length;
  if (view === "rx") {
    const pos = task.classes.map((c) => c.rate).filter((r) => r && r > 0);
    const lo = Math.min(...pos), hi = Math.max(...pos);
    return task.classes.map((c) => (c.rate && c.rate > 0 ? rampColor(hi > lo ? (c.rate - lo) / (hi - lo) : 0.6) : "#e3e9ee"));
  }
  if (!result) return Array(n).fill("#cfd7de");
  const flat = (codes, map) => Array.from({ length: n }, (_, i) => (map[codes[i]] || map.n || {}).color || "#cfd7de");
  if (view === "hw") return flat(result.plans.s, STATUS);
  if (view === "after") return flat(result.specialisation.s_after, STATUS);
  if (view === "diff" && result.reference) {
    return Array.from({ length: n }, (_, i) => {
      const r = task.classes[i].rate;
      if (!r || r <= 0) return "#e3e9ee";
      return DIFF[result.reference.cmp[i]].color;
    });
  }
  return Array(n).fill("#cfd7de");
}

export function legendHtml(view, task, result) {
  const sw = (c, t) => `<span><i style="background:${c}"></i>${esc(t)}</span>`;
  if (view === "rx") {
    const pos = task.classes.map((c) => c.rate).filter((r) => r && r > 0);
    if (!pos.length) return sw("#e3e9ee", "Nessun trattamento");
    const lo = Math.min(...pos), hi = Math.max(...pos);
    const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => rampColor(t)).join(",");
    return `<span>${fmt(lo, 0)} L/ha</span><span class="ramp" style="background:linear-gradient(90deg,${stops})"></span><span>${fmt(hi, 0)} L/ha</span>` +
      (task.classes.some((c) => c.rate === 0) ? sw("#e3e9ee", "non trattare") : "");
  }
  if (view === "diff") return sw(DIFF.b.color, DIFF.b.name) + sw(DIFF.w.color, DIFF.w.name) + sw(DIFF.s.color, DIFF.s.name) + sw("#e3e9ee", "non trattare");
  const used = new Set((view === "after" ? result.specialisation.s_after : result.plans.s).split(""));
  const order = ["o", "a", "u", "v", "x", "f", "n"];
  return order.filter((k) => used.has(k)).map((k) => sw(STATUS[k].color, STATUS[k].name)).join("");
}

// ---------- esito ----------
const pct = (v) => `${fmt(v, 0)} %`;

export function renderVerdict(result, task) {
  const el = $("#verdict");
  const c = result.chain, k = result.kpi, ka = result.specialisation.kpi_after;
  const byArea = k.weighted_by === "area";
  const unit = byArea ? "del campo" : "delle zone";
  let cls = "mid", title, body;
  if (c.blockers.length) {
    cls = "bad";
    title = "Con questo impianto il file non si può eseguire";
    body = `<p>${esc(c.blockers[0])}${c.blockers.length > 1 ? ` (e altri ${c.blockers.length - 1} problemi)` : ""}</p>`;
  } else if (k.classes_treated === 0) {
    title = "Il file non contiene ratei da distribuire";
    body = "<p>Tutte le zone hanno rateo zero o non leggibile.</p>";
  } else {
    const off = k.under_pct + k.over_pct + (k.novra_pct || 0);
    const fixed = ka.on_target_pct;
    if (off < 0.05) {
      cls = "good";
      title = `Il tuo hardware tratta bene tutto il campo`;
      body = `<p>${pct(k.ok_pct)} ${unit} esattamente al rateo richiesto${k.adapt_pct > 0 ? `, ${pct(k.adapt_pct)} con piccoli adattamenti (cambio ugello o velocità)` : ""}.</p>`;
    } else {
      cls = k.on_target_pct >= 85 ? "mid" : "bad";
      title = `Sul tuo hardware il ${pct(k.on_target_pct)} ${unit} è trattato bene, il ${pct(off)} no`;
      const parts = [];
      if (k.under_pct > 0.05) parts.push(`${pct(k.under_pct)} resterebbe sotto-dosato (l'impianto non arriva al rateo richiesto)`);
      if (k.over_pct > 0.05) parts.push(`${pct(k.over_pct)} sarebbe sovra-dosato (non riesce a scendere abbastanza)`);
      if (k.novra_pct > 0.05) parts.push(`${pct(k.novra_pct)} richiede un rateo variabile che questo impianto non esegue`);
      body = `<p>${parts.join("; ")}.</p><p><b>Il file che scarichi</b> porta questi ratei a ciò che la macchina riesce a erogare: ${pct(fixed)} ${unit} entro la tolleranza.</p>`;
    }
  }
  el.className = `verdict ${cls}`;
  el.innerHTML = `<div><h2>${esc(title)}</h2>${body}</div>`;
}

const chip = (d, unit = "punti", lowerIsBetter = false) => {
  if (d === null || d === undefined || Math.abs(d) < 0.05) return "";
  const good = lowerIsBetter ? d < 0 : d > 0;
  return `<span class="delta ${good ? "up" : "down"}">${d > 0 ? "+" : "−"}${fmt(Math.abs(d), 0)} ${unit}</span>`;
};

export function renderKpis(result, task) {
  const k = result.kpi, ref = result.reference ? result.reference.kpi : null, ka = result.specialisation.kpi_after;
  const byArea = k.weighted_by === "area";
  const off = k.under_pct + k.over_pct + (k.novra_pct || 0);
  const offRef = ref ? ref.under_pct + ref.over_pct + (ref.novra_pct || 0) : null;
  const cards = [];
  cards.push(`<div class="kpi blue"><small>Trattato bene</small><b>${pct(k.on_target_pct)}${ref ? chip(k.on_target_pct - ref.on_target_pct) : ""}</b><em>entro ±${fmt(result.tolerance ?? 5, 0)} % del rateo richiesto</em></div>`);
  cards.push(`<div class="kpi red"><small>Fuori bersaglio</small><b>${pct(off)}${offRef !== null ? chip(off - offRef, "punti", true) : ""}</b><em>sotto ${pct(k.under_pct)} · sopra ${pct(k.over_pct)}</em></div>`);
  cards.push(`<div class="kpi"><small>Con adattamento</small><b>${pct(k.adapt_pct)}</b><em>cambio ugello ${pct(k.switch_pct)} · velocità ${pct(k.speed_pct)}</em></div>`);
  if (byArea && k.volume_prescribed_l) {
    cards.push(`<div class="kpi"><small>Miscela</small><b>${fmt(k.volume_delivered_l, 0)} L</b><em>prescritti ${fmt(k.volume_prescribed_l, 0)} L (${k.volume_delta_pct > 0 ? "+" : ""}${fmt(k.volume_delta_pct, 1)} %)</em></div>`);
  }
  if (k.fines_avg_pct !== null && k.fines_avg_pct !== undefined) {
    cards.push(`<div class="kpi"><small>Gocce fini &lt; 136 µm</small><b>${pct(k.fines_avg_pct)}</b><em>media sul trattato, dati catalogo per ${pct(k.fines_coverage_pct)}</em></div>`);
  }
  cards.push(`<div class="kpi green"><small>Con il file specializzato</small><b>${pct(ka.on_target_pct)}</b><em>${result.specialisation.n_changed} ${result.specialisation.n_changed === 1 ? "classe riscritta" : "classi riscritte"}</em></div>`);
  $("#kpis").innerHTML = cards.join("");
}

// ---------- cosa è cambiato rispetto a prima ----------
export function describeChange(prev, cur, byCode) {
  if (!prev) return [];
  const nm = (code) => { const p = byCode.get(code); return p ? p.name.split(" · ")[0] : code; };
  const out = [];
  if (JSON.stringify(prev.nozzles) !== JSON.stringify(cur.nozzles))
    out.push(`ugelli ${prev.nozzles.join(" + ") || "—"} → ${cur.nozzles.join(" + ") || "—"}`);
  const lab = { terminal: "terminale", rate_control: "controllo rateo", ecu: "centralina", actuator: "attuatore", flowmeter: "flussimetro", valve: "valvola", pump: "pompa" };
  for (const k of Object.keys(lab)) if (prev[k] !== cur[k]) out.push(`${lab[k]}: ${prev[k] ? nm(prev[k]) : "nessuno"} → ${cur[k] ? nm(cur[k]) : "nessuno"}`);
  const nums = { boom_width: "barra (m)", spacing: "interasse (m)", speed_nom: "velocità", speed_min: "vel. min", speed_max: "vel. max", tolerance_pct: "tolleranza", duty_min_pct: "duty min", pressure_min: "p min", pressure_max: "p max", nozzle_count: "n. ugelli" };
  for (const k of Object.keys(nums)) if ((prev[k] ?? null) !== (cur[k] ?? null)) out.push(`${nums[k]}: ${prev[k] ?? "auto"} → ${cur[k] ?? "auto"}`);
  if (prev.allow_speed_adapt !== cur.allow_speed_adapt) out.push(cur.allow_speed_adapt ? "velocità adattabile" : "velocità fissa");
  if (prev.strategy !== cur.strategy) out.push(`strategia: ${prev.strategy} → ${cur.strategy}`);
  return out;
}

export function renderChangebar(result, task, changes, locked) {
  const el = $("#changebar");
  if (!result.reference) { el.hidden = true; return; }
  const ref = result.reference, k = result.kpi;
  const w = task.classes.map((c) => (k.weighted_by === "area" ? c.area_ha || 0 : 1));
  const tot = w.reduce((a, b) => a + b, 0) || 1;
  let better = 0, worse = 0, nb = 0, nw = 0;
  ref.cmp.split("").forEach((x, i) => {
    if (!task.classes[i].rate || task.classes[i].rate <= 0) return;
    if (x === "b") { better += w[i]; nb++; }
    if (x === "w") { worse += w[i]; nw++; }
  });
  const dOn = k.on_target_pct - ref.kpi.on_target_pct;
  const unit = k.weighted_by === "area" ? "del campo" : "delle zone";
  let msg;
  if (nb === 0 && nw === 0) msg = `<b>Nessuna differenza</b> rispetto a ${locked ? "il riferimento fissato" : "prima della modifica"}: ogni zona viene trattata come prima.`;
  else {
    const parts = [];
    if (nb) parts.push(`<b style="color:#0f6b38">${nb} ${nb === 1 ? "zona va" : "zone vanno"} meglio</b> (${pct((better / tot) * 100)} ${unit})`);
    if (nw) parts.push(`<b style="color:#a3182a">${nw} ${nw === 1 ? "zona va" : "zone vanno"} peggio</b> (${pct((worse / tot) * 100)} ${unit})`);
    msg = `${parts.join(" · ")}. Trattato bene: ${pct(ref.kpi.on_target_pct)} → <b>${pct(k.on_target_pct)}</b> ${chip(dOn)}`;
  }
  el.hidden = false;
  el.innerHTML = `<div class="txt"><div class="small mut">${locked ? "Confronto con il riferimento fissato" : "Rispetto a prima della modifica"}${changes.length ? ": " + esc(changes.join(" · ")) : ""}</div>${msg}</div>
    <button class="btn sm" type="button" id="cb-diff">Vedi sulla mappa</button>
    <button class="btn sm" type="button" id="cb-lock">${locked ? "Rilascia il riferimento" : "Fissa come riferimento"}</button>`;
}

// ---------- dettaglio di una classe ----------
export function renderDetail(sel, result, task, detail) {
  const el = $("#detail");
  if (sel === null || sel === undefined) {
    el.innerHTML = `<p class="mut small" style="margin:10px 0 0">Tocca una zona della mappa o una riga della tabella per vedere perché viene trattata così.</p>`;
    return;
  }
  const c = task.classes[sel];
  const p = detail && detail.i === sel ? detail.plan : null;
  const after = detail && detail.i === sel ? detail.after : null;
  const code = result.plans.s[sel];
  const st = STATUS[code] || STATUS.n;
  const bits = [];
  if (p) {
    if (p.nozzle) bits.push(`ugello ${esc(p.nozzle)}`);
    if (p.speed) bits.push(`${fmt(p.speed, 1)} km/h`);
    if (p.pressure) bits.push(`${fmt(p.pressure, 1)} bar`);
    if (p.duty !== null && p.duty !== undefined) bits.push(`duty PWM ${fmt(p.duty, 0)} %`);
    if (p.drop_class) bits.push(`gocce ${esc(p.drop_class)}${p.fines !== null ? `, ${fmt(p.fines, 0)} % fini` : ""}`);
  }
  const newRate = detail && detail.i === sel ? detail.new_rate : result.specialisation.new_rate[sel];
  el.innerHTML = `<div class="alert ${st.key === "under" || st.key === "novra" ? "red" : st.key === "adapt" || st.key === "over" ? "amber" : ""}" style="margin-bottom:0">
    <b><span class="sw" style="background:${c.color || "#999"}"></span>${esc(c.label)} · ${c.area_ha !== null ? fmt(c.area_ha, 2) + " ha · " : ""}richiesti ${fmt(c.rate, 0)} L/ha &nbsp;${badge(code)}</b>
    ${p ? `<div>${esc(p.explain)}</div>${p.hint ? `<div class="small" style="margin-top:4px">💡 ${esc(p.hint)}</div>` : ""}` : "<div class='mut'>Calcolo del dettaglio…</div>"}
    ${bits.length ? `<div class="small mut" style="margin-top:4px">Impostazioni per l'operatore: ${bits.join(" · ")}</div>` : ""}
    <div class="small" style="margin-top:4px">${newRate ? `Nel file specializzato questa zona passa da <b>${fmt(c.rate, 0)}</b> a <b>${fmt(newRate, 0)} L/ha</b>${after ? " e viene eseguita " + (STATUS_BY_KEY[after.status] || STATUS.n).name.toLowerCase() : ""}.` : "Nel file specializzato il rateo resta quello della prescrizione."}</div></div>`;
}

// ---------- tabella delle zone ----------
export function renderZones(result, task, selected) {
  const t = result.table, ref = !!result.reference;
  if (t.mode === "bands") {
    const rows = t.rows.map((r) => `<tr><td>${esc(r.label)}</td><td class="n">${fmt(r.area_ha, 2)}</td><td class="n">${r.n_classes}</td><td class="n">${fmt(r.rate, 0)}</td>
      <td class="n">${pct(r.ok)}</td><td class="n">${pct(r.adapt)}</td><td class="n">${pct(r.under)}</td><td class="n">${pct(r.over)}</td></tr>`).join("");
    $("#tab-zones").innerHTML = `<p class="mut small" style="margin-top:0">Mappa continua con ${task.classes.length} valori diversi: li raggruppo in fasce di rateo con uguale superficie. Il dettaglio di ogni punto lo vedi toccando la mappa.</p>
      <div class="tw"><table class="t"><thead><tr><th>Fascia di rateo</th><th class="n">ha</th><th class="n">valori</th><th class="n">media L/ha</th><th class="n">perfetto</th><th class="n">adattato</th><th class="n">sotto</th><th class="n">sopra</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    return;
  }
  const cmpTxt = { better: '<span class="delta up">meglio</span>', worse: '<span class="delta down">peggio</span>', same: '<span class="delta eq">uguale</span>' };
  const rows = t.rows.map((r) => {
    const p = r.plan, st = STATUS_BY_KEY[p.status] || STATUS.n;
    const off = !r.rate || r.rate <= 0;
    return `<tr data-i="${r.i}" class="${selected === r.i ? "sel" : ""}"><td><span class="sw" style="background:${task.classes[r.i].color || "#999"}"></span>${esc(r.label)}</td>
      <td class="n">${r.area_ha !== null ? fmt(r.area_ha, 2) : "—"}</td><td class="n">${off ? "0" : fmt(r.rate, 0)}</td>
      <td>${off ? '<span class="badge off">Non trattare</span>' : `<span class="badge ${st.cls}">${esc(st.name)}</span>`}</td>
      <td class="n">${off ? "—" : fmt(p.delivered, 0)}</td><td>${off ? "—" : esc(p.nozzle || "—")}</td>
      <td class="n">${off ? "—" : fmt(p.speed, 1)}</td><td class="n">${off ? "—" : fmt(p.pressure, 1)}</td>
      <td class="n">${off || p.duty === null ? "—" : fmt(p.duty, 0)}</td>
      <td class="n">${r.new_rate ? `<b>${fmt(r.new_rate, 0)}</b>` : "invariato"}</td>${ref ? `<td>${r.cmp ? cmpTxt[r.cmp] : ""}</td>` : ""}</tr>`;
  }).join("");
  $("#tab-zones").innerHTML = `<div class="tw"><table class="t"><thead><tr><th>Zona</th><th class="n">ha</th><th class="n">Richiesto L/ha</th><th>Esito</th><th class="n">Erogato L/ha</th><th>Ugello</th><th class="n">km/h</th><th class="n">bar</th><th class="n">Duty %</th><th class="n">Nel file</th>${ref ? "<th>Vs prima</th>" : ""}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ---------- ugelli e portate ----------
function niceMax(v) { const steps = [100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1500, 2000]; return steps.find((s) => s >= v) || Math.ceil(v / 500) * 500; }

export function renderNozzles(result, task, onApply) {
  const env = result.envelope.nozzles;
  const rates = task.classes.map((c, i) => ({ r: c.rate, s: result.plans.s[i] })).filter((x) => x.r && x.r > 0);
  const hiRate = Math.max(...rates.map((x) => x.r), 0);
  const max = niceMax(Math.max(hiRate * 1.08, ...env.map((e) => e.any[1]), 100));
  const pos = (v) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const bars = env.map((e) => {
    const ticks = rates.map((x) => `<span class="tick ${"oa".includes(x.s) ? "ok" : ""}" style="left:${pos(x.r)};opacity:${rates.length > 40 ? 0.3 : 0.85}"></span>`).join("");
    return `<div><b>${esc(e.code)}</b> <span class="mut small">${esc(e.name)}${e.estimated ? " · portata stimata" : ""}</span>
      <div class="bar" aria-hidden="true"><span class="rng any" style="left:${pos(e.any[0])};width:calc(${pos(e.any[1])} - ${pos(e.any[0])})"></span>
      <span class="rng" style="left:${pos(e.nom[0])};width:calc(${pos(e.nom[1])} - ${pos(e.nom[0])})"></span>${ticks}</div>
      <div class="axis"><span>0</span><span>${fmt(max / 2, 0)}</span><span>${fmt(max, 0)} L/ha</span></div>
      <div class="small">Alla velocità di lavoro: <b>${fmt(e.nom[0], 0)}–${fmt(e.nom[1], 0)} L/ha</b>${result.envelope.pwm ? " (con PWM)" : ""}. Adattando la velocità: ${fmt(e.any[0], 0)}–${fmt(e.any[1], 0)} L/ha. Portata per ugello ${fmt(e.q_min, 2)}–${fmt(e.q_max, 2)} L/min, ${fmt(e.p_min, 1)}–${fmt(e.p_max, 1)} bar.</div></div>`;
  }).join("");
  const sugg = result.suggestions;
  let sh = "";
  if (sugg) {
    const cur = sugg.current;
    const card = (o, best, pair) => {
      const d = o.on_target_pct - cur.on_target_pct;
      const bad = Math.max(0, 100 - o.on_target_pct);
      return `<div class="opt ${best ? "best" : ""}"><b>${o.nozzles.map(esc).join(" + ")}</b>
        <div class="small mut">${pair ? "commutati dal SELETRON" : "ugello singolo"}</div>
        <div class="meter" title="perfetto / adattato / fuori"><i style="width:${o.ok_pct}%;background:#1f9d55"></i><i style="width:${o.adapt_pct}%;background:#e0a100"></i><i style="width:${bad}%;background:#E03040"></i></div>
        <div>Trattato bene <b>${pct(o.on_target_pct)}</b> ${chip(d)}</div>
        <div class="small mut">${o.fines_avg_pct !== null ? `gocce fini ${pct(o.fines_avg_pct)} · ` : ""}perfetto ${pct(o.ok_pct)}</div>
        <button class="btn sm primary" type="button" data-apply='${esc(JSON.stringify(o.nozzles))}' style="margin-top:8px">Provalo</button></div>`;
    };
    sh = `<h3 style="margin-top:22px">Ugelli che potrebbero fare meglio</h3>
      <p class="mut small" style="margin:4px 0 0">Calcolati sull'intera prescrizione, con la tua catena di controllo. Adesso: <b>${cur.nozzles.join(" + ")}</b> → ${pct(cur.on_target_pct)} trattato bene.</p>
      <div class="sug">${sugg.singles.map((o, i) => card(o, i === 0, false)).join("")}${sugg.pairs.map((o, i) => card(o, false, true)).join("")}</div>
      ${!sugg.singles.length && !sugg.pairs.length ? "<p>Nessun altro ugello del catalogo migliora il risultato.</p>" : ""}`;
  } else if (result.chain.blockers.length) {
    sh = `<p class="mut">Completa prima la catena di controllo per ottenere suggerimenti.</p>`;
  } else {
    sh = `<p class="mut"><span class="spin"></span> Cerco gli ugelli migliori per questa prescrizione…</p>`;
  }
  $("#tab-nozzles").innerHTML = `<p class="mut small" style="margin-top:0">Ogni barra mostra i ratei che l'ugello può erogare: la parte piena alla velocità di lavoro, la tratteggiata cambiando velocità. I trattini sono i ratei della prescrizione (verde = raggiunti, rosso = no).</p>
    <div class="bars">${bars || "<p>Seleziona un ugello.</p>"}</div>${sh}`;
  $("#tab-nozzles").querySelectorAll("[data-apply]").forEach((b) => b.addEventListener("click", () => onApply(JSON.parse(b.dataset.apply))));
}

// ---------- come si calcola ----------
export function renderHow() {
  $("#tab-how").innerHTML = `
    <h3>Come arrivo ai numeri</h3>
    <p><b>Portata richiesta</b> per ugello: <code>q = rateo × velocità × interasse / 600</code> (L/min con L/ha, km/h, m). La portata dell'ugello dipende dalla pressione secondo la <b>curva del catalogo</b> (interpolata fra i punti pubblicati; se c'è un solo punto la curva è stimata con √pressione e viene segnalato).</p>
    <p><b>Con Flowtron (PWM)</b> la pressione resta fissa e cambia la percentuale di apertura di ciascun ugello; il duty minimo è un'ipotesi che puoi modificare. <b>Senza PWM</b> il rateo si regola solo con la pressione, quindi la portata cambia con la radice della pressione. Con un <b>SELETRON</b> si può commutare fra più ugelli del portaugello.</p>
    <p><b>Ordine dei tentativi</b>: ugello principale alla velocità di lavoro → ugello alternativo → altra velocità consentita → entrambi. Se nessuno arriva, il piano si ferma al valore più vicino possibile e la zona risulta sotto- o sovra-dosata.</p>
    <p><b>Controlli sulla catena</b>: serve un terminale con Task Controller; i terminali Delta IBX funzionano solo con centraline IBX; per i ratei variabili servono Flowtron oppure valvola + flussimetro; la finestra di pressione è il minimo fra attuatore, pompa e valvola.</p>
    <h3 style="margin-top:18px">Cosa fa il file specializzato</h3>
    <p>Riscrive nel TASKDATA solo i ratei che l'impianto non può erogare, portandoli al valore più vicino che riesce a distribuire (oppure a un rateo unico, se la macchina non esegue ratei variabili). Le zone già raggiungibili restano identiche. Prima di scaricare vedi il volume totale che cambia e devi confermare. Il file prodotto viene riletto dal server per verificare che i ratei scritti coincidano con quelli attesi.</p>
    <h3 style="margin-top:18px">Limiti da conoscere</h3>
    <ul>
      <li>Il file non contiene comandi proprietari Nordson/ARAG: ugello, pressione e velocità sono <b>indicazioni per l'operatore</b>, non istruzioni scritte nel file.</li>
      <li>Le compatibilità vengono dal catalogo pubblico: confermale con scheda tecnica o assistenza prima di lavorare.</li>
      <li>L'orientamento delle griglie GRD (riga 0 a sud, colonne da ovest) segue la lettura della norma: da confermare con un tuo file reale.</li>
      <li>Non è stato provato su un terminale Delta reale.</li>
    </ul>`;
}
