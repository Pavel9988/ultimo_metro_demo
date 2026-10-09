// Pannello hardware: legge il catalogo ARAG/Nordson, costruisce i campi e avvisa a ogni modifica.

import { $, esc, fmt } from "./util.js";

export const PRESETS = [
  {
    id: "full1", label: "Nordson IBX completo · 1 ugello (AFC11002)",
    cfg: { terminal: "4675204", rate_control: "4679013", ecu: "", actuator: "4063T95A0", flowmeter: "46211P40000", valve: "853T04A55", pump: "97055201", nozzles: ["AFC11002"] },
  },
  {
    id: "full2", label: "Nordson IBX completo · 2 ugelli commutabili (SELETRON)",
    cfg: { terminal: "4675204", rate_control: "4679013", ecu: "", actuator: "4063T95A0", flowmeter: "46211P40000", valve: "853T04A55", pump: "97055201", nozzles: ["AFC11002", "AFC11006"] },
  },
  {
    id: "valve", label: "Terminale ISOBUS + valvola + flussimetro (senza Flowtron)",
    cfg: { terminal: "4675202", rate_control: "", ecu: "", actuator: "", flowmeter: "46211P40000", valve: "853T04A55", pump: "97055201", nozzles: ["WRC110025"] },
  },
  {
    id: "bare", label: "Terminale ISOBUS senza controllo di portata",
    cfg: { terminal: "4675202", rate_control: "", ecu: "", actuator: "", flowmeter: "", valve: "", pump: "", nozzles: ["WRC110025"] },
  },
];

export const DEFAULTS = {
  pressure_set: 3, pressure_min: null, pressure_max: null, boom_width: 24, spacing: 0.5, nozzle_count: null,
  speed_nom: 8, speed_min: 6, speed_max: 10, tolerance_pct: 5, duty_min_pct: 20, spray_height: 0.5,
  allow_speed_adapt: true, strategy: "auto", uniform_rate: null,
};

export function presetConfig(id) {
  const p = PRESETS.find((x) => x.id === id) || PRESETS[0];
  return { ...DEFAULTS, ...JSON.parse(JSON.stringify(p.cfg)) };
}

const CAT_LABEL = {
  terminal: "Terminale / computer di bordo", rate_control: "Controllo rateo (Flowtron / IBX)", ecu: "Centralina irroratrice",
  actuator: "Attuatore / portaugello", flowmeter: "Flussimetro", valve: "Valvola di regolazione", pump: "Pompa",
};
const CAT_OF = { terminal: "controller", rate_control: "rate_control", ecu: "ecu", actuator: "actuator", flowmeter: "flowmeter", valve: "valve", pump: "pump" };
const NONE = { terminal: "— nessun terminale —", rate_control: "— nessuno —", ecu: "— nessuna —", actuator: "— portaugello normale —", flowmeter: "— nessuno —", valve: "— nessuna —", pump: "— non indicata —" };

export class HwPanel {
  constructor(catalog, onChange) {
    this.cat = catalog;
    this.byCode = new Map(catalog.products.map((p) => [p.code, p]));
    this.onChange = onChange;
    this.cfg = presetConfig("full1");
    this.ways = 1;
    this._build();
  }

  nozzleProduct(code) { return this.byCode.get(code); }

  // ---- costruzione ----
  _build() {
    const bn = $("#b-nozzles"), bc = $("#b-chain"), bw = $("#b-work"), bs = $("#b-spec");
    bn.innerHTML = `<div id="nozslots"></div><button class="btn sm" id="noz-add" type="button" style="margin-top:10px">+ Aggiungi un secondo ugello</button>
      <p class="nozinfo" id="noz-help"></p>`;
    bc.innerHTML = Object.keys(CAT_OF).map((k) => `<label class="f" for="hw-${k}">${CAT_LABEL[k]}</label><select id="hw-${k}" data-k="${k}"></select><p class="nozinfo" id="info-${k}"></p>`).join("");
    for (const k of Object.keys(CAT_OF)) {
      const sel = $(`#hw-${k}`);
      const items = this.cat.products.filter((p) => p.category === CAT_OF[k]);
      sel.innerHTML = `<option value="">${NONE[k]}</option>` + items.map((p) => `<option value="${esc(p.code)}">${esc(p.code)} · ${esc(p.name)}</option>`).join("");
      sel.addEventListener("change", () => { this._read(); this._changed(true); });
    }
    bw.innerHTML = `
      <div class="row2"><div><label class="f" for="w-boom">Larghezza barra (m)</label><input id="w-boom" type="number" min="1" max="60" step="0.5"></div>
      <div><label class="f" for="w-spacing">Interasse ugelli (m)</label><input id="w-spacing" type="number" min="0.2" max="1" step="0.05"></div></div>
      <label class="f" for="w-count">Numero di ugelli <span class="mut">(vuoto = calcolato)</span></label><input id="w-count" type="number" min="1" max="200" step="1" placeholder="calcolato">
      <div class="row3"><div><label class="f" for="w-vnom">Velocità km/h</label><input id="w-vnom" type="number" min="1" max="30" step="0.5"></div>
      <div><label class="f" for="w-vmin">Minima</label><input id="w-vmin" type="number" min="1" max="30" step="0.5"></div>
      <div><label class="f" for="w-vmax">Massima</label><input id="w-vmax" type="number" min="1" max="30" step="0.5"></div></div>
      <label class="check"><input type="checkbox" id="w-adapt"><span>Posso variare la velocità per raggiungere un rateo<br><span class="mut small">se spento, tutto si calcola alla velocità indicata</span></span></label>
      <div class="row2"><div><label class="f" for="w-tol">Tolleranza (±%)</label><input id="w-tol" type="number" min="0" max="50" step="1"></div>
      <div><label class="f" for="w-duty">Duty PWM minimo (%)</label><input id="w-duty" type="number" min="1" max="100" step="1"></div></div>
      <div class="row2"><div><label class="f" for="w-pmin">Pressione min. (bar)</label><input id="w-pmin" type="number" min="0.5" max="20" step="0.5" placeholder="da catalogo"></div>
      <div><label class="f" for="w-pmax">Pressione max. (bar)</label><input id="w-pmax" type="number" min="1" max="30" step="0.5" placeholder="da catalogo"></div></div>`;
    bs.innerHTML = `
      <label class="f" for="s-strategy">Come specializzare il file</label>
      <select id="s-strategy"><option value="auto">Automatica (consigliata)</option><option value="variable">Mantieni ratei variabili</option><option value="uniform">Rateo unico</option></select>
      <p class="nozinfo" id="s-help"></p>
      <div id="s-uni" hidden><label class="f" for="s-urate">Rateo unico (L/ha) <span class="mut">(vuoto = media pesata)</span></label><input id="s-urate" type="number" min="1" max="2000" step="1"></div>`;
    for (const el of [...bw.querySelectorAll("input"), ...bs.querySelectorAll("input,select")]) {
      el.addEventListener("input", () => { this._read(); this._changed(false); });
      el.addEventListener("change", () => { this._read(); this._changed(false); });
    }
    $("#noz-add").addEventListener("click", () => {
      if (this.cfg.nozzles.length < this.ways) { this.cfg.nozzles.push(this._nextNozzle()); this._renderNozzles(); this._changed(true); }
    });
  }

  _nextNozzle() {
    const used = new Set(this.cfg.nozzles);
    const base = this.byCode.get(this.cfg.nozzles[0]);
    const fam = base ? base.name.split(" · ")[0] : "";
    const pool = this.cat.products.filter((p) => p.category === "nozzle");
    const same = pool.filter((p) => p.name.startsWith(fam) && !used.has(p.code));
    return (same.find((p) => this._flow3(p) > this._flow3(base)) || same[0] || pool.find((p) => !used.has(p.code))).code;
  }

  _flow3(p) { return p ? Number(p.capabilities.flow_l_min_at_3_bar) || 0 : 0; }

  // ---- ugelli ----
  _nozzleOptions() {
    const noz = this.cat.products.filter((p) => p.category === "nozzle");
    const groups = new Map();
    for (const p of noz) {
      const g = p.name.split(" · ")[0];
      if (!groups.has(g)) groups.set(g, { short: p.short, items: [] });
      groups.get(g).items.push(p);
    }
    let html = "";
    for (const [g, v] of groups) {
      v.items.sort((a, b) => this._flow3(a) - this._flow3(b));
      html += `<optgroup label="${esc(g)} — ${esc(v.short)}">` +
        v.items.map((p) => `<option value="${esc(p.code)}">${esc(p.code)} · ${fmt(this._flow3(p), 2)} L/min a 3 bar</option>`).join("") + "</optgroup>";
    }
    return html;
  }

  _renderNozzles() {
    const slots = $("#nozslots");
    const opts = this._nozzleOptions();
    slots.innerHTML = this.cfg.nozzles.map((c, i) => `
      <div class="nozrow"><select data-i="${i}" aria-label="Ugello ${i + 1}">${opts}</select>
      ${i > 0 ? `<button class="btn sm" type="button" data-rm="${i}" aria-label="Togli ugello ${i + 1}">✕</button>` : ""}</div>
      <p class="nozinfo" id="ni-${i}"></p>`).join("");
    slots.querySelectorAll("select").forEach((s) => {
      s.value = this.cfg.nozzles[Number(s.dataset.i)];
      s.addEventListener("change", () => { this.cfg.nozzles[Number(s.dataset.i)] = s.value; this._nozzleInfo(); this._changed(true); });
    });
    slots.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => {
      this.cfg.nozzles.splice(Number(b.dataset.rm), 1); this._renderNozzles(); this._changed(true);
    }));
    this._nozzleInfo();
    const add = $("#noz-add");
    add.hidden = !(this.ways > 1 && this.cfg.nozzles.length < this.ways);
    $("#noz-help").textContent = this.ways > 1
      ? `Il portaugello ha ${this.ways} vie: puoi montare fino a ${this.ways} ugelli diversi e farli commutare dal SELETRON in base al rateo.`
      : "Con un portaugello normale c'è un solo ugello per posizione. Per commutare tra ugelli serve un SELETRON.";
  }

  _nozzleInfo() {
    this.cfg.nozzles.forEach((c, i) => {
      const p = this.byCode.get(c), el = $(`#ni-${i}`);
      if (!p || !el) return;
      const k = p.capabilities;
      const bits = [];
      const q = k.flow_l_min_by_pressure_bar;
      bits.push(q ? `${fmt(Math.min(...Object.values(q)), 2)}–${fmt(Math.max(...Object.values(q)), 2)} L/min` : `${fmt(k.flow_l_min_at_3_bar, 2)} L/min a 3 bar (stima √p)`);
      bits.push(`${fmt(k.pressure_min_bar, 1)}–${fmt(k.pressure_max_bar, 1)} bar`);
      bits.push(k.low_drift ? "antideriva" : "standard");
      if (k.droplet_dataset_available) bits.push("dati gocce da tabella");
      el.innerHTML = esc(bits.join(" · ")) + (p.official_url ? ` · <a href="${esc(p.official_url)}" target="_blank" rel="noopener">scheda</a>` : "");
    });
  }

  // ---- lettura / scrittura ----
  _num(id) { const v = $(id).value.trim().replace(",", "."); return v === "" ? null : Number(v); }

  _read() {
    const c = this.cfg;
    for (const k of Object.keys(CAT_OF)) {
      const key = k === "terminal" ? "terminal" : k;
      c[key] = $(`#hw-${k}`).value;
    }
    c.boom_width = this._num("#w-boom") ?? DEFAULTS.boom_width;
    c.spacing = this._num("#w-spacing") ?? DEFAULTS.spacing;
    c.nozzle_count = this._num("#w-count");
    c.speed_nom = this._num("#w-vnom") ?? DEFAULTS.speed_nom;
    c.speed_min = this._num("#w-vmin") ?? DEFAULTS.speed_min;
    c.speed_max = this._num("#w-vmax") ?? DEFAULTS.speed_max;
    c.allow_speed_adapt = $("#w-adapt").checked;
    c.tolerance_pct = this._num("#w-tol") ?? DEFAULTS.tolerance_pct;
    c.duty_min_pct = this._num("#w-duty") ?? DEFAULTS.duty_min_pct;
    c.pressure_min = this._num("#w-pmin");
    c.pressure_max = this._num("#w-pmax");
    c.strategy = $("#s-strategy").value;
    c.uniform_rate = this._num("#s-urate");
  }

  write(cfg) {
    this.cfg = { ...DEFAULTS, ...JSON.parse(JSON.stringify(cfg)) };
    for (const k of Object.keys(CAT_OF)) $(`#hw-${k}`).value = this.cfg[k] || "";
    $("#w-boom").value = this.cfg.boom_width; $("#w-spacing").value = this.cfg.spacing;
    $("#w-count").value = this.cfg.nozzle_count ?? "";
    $("#w-vnom").value = this.cfg.speed_nom; $("#w-vmin").value = this.cfg.speed_min; $("#w-vmax").value = this.cfg.speed_max;
    $("#w-adapt").checked = !!this.cfg.allow_speed_adapt;
    $("#w-tol").value = this.cfg.tolerance_pct; $("#w-duty").value = this.cfg.duty_min_pct;
    $("#w-pmin").value = this.cfg.pressure_min ?? ""; $("#w-pmax").value = this.cfg.pressure_max ?? "";
    $("#s-strategy").value = this.cfg.strategy; $("#s-urate").value = this.cfg.uniform_rate ?? "";
    this._afterChain();
    this._renderNozzles();
    this._summaries();
  }

  get() { return JSON.parse(JSON.stringify(this.cfg)); }

  // ---- logica di contorno ----
  _afterChain() {
    const act = this.byCode.get(this.cfg.actuator);
    const name = act ? `${act.name} ${act.short}`.toLowerCase() : "";
    let ways = 1;
    if (act) {
      const w = act.capabilities && act.capabilities.ways;
      ways = w ? Number(w) : name.includes("quadruplo") ? 4 : name.includes("triplo") ? 3 : name.includes("doppio") ? 2 : 1;
    }
    this.ways = ways;
    if (this.cfg.nozzles.length > ways) this.cfg.nozzles = this.cfg.nozzles.slice(0, ways);
    if (!this.cfg.nozzles.length) this.cfg.nozzles = [this._firstNozzle()];
    for (const k of Object.keys(CAT_OF)) {
      const p = this.byCode.get(this.cfg[k]), el = $(`#info-${k}`);
      el.innerHTML = p ? `${esc(p.short || "")}${p.official_url ? ` · <a href="${esc(p.official_url)}" target="_blank" rel="noopener">scheda ufficiale</a>` : ""}` : "";
    }
    $("#s-uni").hidden = this.cfg.strategy !== "uniform";
    $("#s-help").textContent = {
      auto: "Se l'impianto esegue ratei variabili, riscrive solo le zone che non riesce a erogare; altrimenti propone un rateo unico.",
      variable: "Mantiene la mappa a zone: ogni rateo che l'hardware non raggiunge viene portato al valore più vicino possibile.",
      uniform: "Sostituisce la mappa con un solo rateo, per macchine che non eseguono ratei variabili.",
    }[this.cfg.strategy];
  }

  _firstNozzle() { return this.cat.products.find((p) => p.category === "nozzle").code; }

  _summaries() {
    const c = this.cfg;
    const nm = (code) => { const p = this.byCode.get(code); return p ? p.name.split(" · ")[0] : ""; };
    $("#s-nozzles").textContent = c.nozzles.join(" + ");
    const bits = [];
    if (c.rate_control) bits.push("Flowtron");
    if (c.actuator) bits.push(nm(c.actuator).replace("SELETRON", "SELETRON"));
    $("#s-chain").textContent = [nm(c.terminal), ...bits].filter(Boolean).join(" · ") || "da completare";
    $("#s-work").textContent = `${fmt(c.boom_width, 0)} m · ${fmt(c.speed_nom, 0)} km/h`;
    $("#s-spec").textContent = { auto: "automatica", variable: "ratei variabili", uniform: "rateo unico" }[c.strategy];
  }

  _changed(structural) {
    this._afterChain();
    if (structural) this._renderNozzles();
    this._summaries();
    this.onChange(this.get());
  }

  showAlerts(chain) {
    const box = $("#hw-alerts");
    let html = "";
    if (chain.blockers && chain.blockers.length)
      html += `<div class="alert red"><b>Con questo impianto il file non si può eseguire</b><ul>${chain.blockers.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></div>`;
    if (chain.warnings && chain.warnings.length)
      html += `<div class="alert amber"><b>Da controllare</b><ul>${chain.warnings.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></div>`;
    if (chain.vra && !(chain.blockers && chain.blockers.length))
      html += `<div class="alert"><b>${chain.pwm ? "Regolazione PWM per ugello" : "Regolazione a pressione"}</b>` +
        `Finestra di pressione ${fmt(chain.pressure_window[0], 1)}–${fmt(chain.pressure_window[1], 1)} bar · ${chain.n_nozzles} ugelli sulla barra.</div>`;
    box.innerHTML = html;
  }
}
