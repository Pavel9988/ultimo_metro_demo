// Schede accessorie: etichette (dati inseriti dall'utente), meteo (Open-Meteo) e condivisione in rete.

import { $, esc, fmt, toast } from "./util.js";
import { api } from "./api.js";

const OFFICIAL_DB = "https://www.fitosanitari.salute.gov.it/fitosanitariws_new/";

// ---------------------------------------------------------------- Etichette
function loadLabels() {
  try { return JSON.parse(localStorage.getItem("um_labels") || "{}"); } catch { return {}; }
}
function saveLabels(all) {
  try { localStorage.setItem("um_labels", JSON.stringify(all)); } catch { /* storage non disponibile: i dati restano in pagina */ }
}
const keyOf = (name) => name.trim().toLowerCase().replace(/\s+/g, " ");

export function renderLabels(summary, task, result) {
  const el = $("#tab-labels");
  const all = loadLabels();
  const prods = (task.products && task.products.length ? task.products : summary.products.map((p) => p.name));
  const rates = task.classes.map((c) => c.rate).filter((r) => r && r > 0);
  const lo = rates.length ? Math.min(...rates) : null, hi = rates.length ? Math.max(...rates) : null;
  const afterNew = result ? result.specialisation.new_rate.filter((x) => x) : [];
  const hiAfter = rates.length ? Math.max(hi, ...afterNew) : null;
  const card = (name) => {
    const d = all[keyOf(name)] || {};
    return `<div class="lbl" data-p="${esc(keyOf(name))}">
      <b>${esc(name)}</b>
      <div class="row2"><div><label class="f">Volume di miscela in etichetta, min (L/ha)</label><input type="number" data-f="vmin" value="${esc(d.vmin ?? "")}" min="0" step="1"></div>
      <div><label class="f">…massimo (L/ha)</label><input type="number" data-f="vmax" value="${esc(d.vmax ?? "")}" min="0" step="1"></div></div>
      <div class="row3"><div><label class="f">Dose prodotto (min–max)</label><input type="text" data-f="dose" value="${esc(d.dose ?? "")}" placeholder="es. 1,5–2 L/ha"></div>
      <div><label class="f">Intervallo di sicurezza (gg)</label><input type="text" data-f="phi" value="${esc(d.phi ?? "")}"></div>
      <div><label class="f">Max trattamenti</label><input type="text" data-f="maxn" value="${esc(d.maxn ?? "")}"></div></div>
      <label class="f">Note dall'etichetta</label><input type="text" data-f="note" value="${esc(d.note ?? "")}" placeholder="ugelli, pressione, vento, avvertenze…">
      <div class="lblcheck small" style="margin-top:8px"></div>
      <p class="small" style="margin:8px 0 0"><a href="${OFFICIAL_DB}" target="_blank" rel="noopener">Cerca “${esc(name)}” nella banca dati ufficiale ↗</a></p></div>`;
  };
  el.innerHTML = `<div class="alert"><b>Etichetta e legge vengono prima di tutto</b>Non ho un archivio di etichette: non invento autorizzazioni né dosi. Qui annoti i dati letti sull'etichetta ufficiale e li confronto con la tua prescrizione. I dati restano solo in questo browser.</div>
    <p class="mut small">Nel file i ratei sono in L/ha di miscela applicata: ${lo !== null ? `da <b>${fmt(lo, 0)}</b> a <b>${fmt(hi, 0)} L/ha</b>${hiAfter > hi ? ` (nel file specializzato fino a ${fmt(hiAfter, 0)} L/ha)` : ""}` : "nessun rateo positivo"}. Non è la dose del formulato.</p>
    ${prods.length ? prods.map(card).join("") : '<p class="mut">Il file non indica prodotti.</p>'}
    <p style="margin-top:14px"><a class="btn sm" href="${OFFICIAL_DB}" target="_blank" rel="noopener">Banca dati prodotti fitosanitari · Ministero della Salute ↗</a></p>`;
  const refresh = (box) => {
    const d = all[box.dataset.p] || {};
    const vmin = Number(d.vmin), vmax = Number(d.vmax);
    const out = box.querySelector(".lblcheck");
    const msgs = [];
    if (d.vmax && hiAfter !== null && hiAfter > vmax) msgs.push(`<span style="color:#a3182a">⚠ Il rateo massimo del file (${fmt(hiAfter, 0)} L/ha) supera il massimo di etichetta (${fmt(vmax, 0)} L/ha).</span>`);
    if (d.vmin && lo !== null && lo < vmin) msgs.push(`<span style="color:#a3182a">⚠ Il rateo minimo del file (${fmt(lo, 0)} L/ha) è sotto il minimo di etichetta (${fmt(vmin, 0)} L/ha).</span>`);
    if (!msgs.length && (d.vmin || d.vmax)) msgs.push(`<span style="color:#0f6b38">✓ I ratei del file stanno nel volume indicato.</span>`);
    out.innerHTML = msgs.join("<br>");
  };
  el.querySelectorAll(".lbl").forEach((box) => {
    refresh(box);
    box.querySelectorAll("input").forEach((inp) => inp.addEventListener("input", () => {
      const k = box.dataset.p;
      all[k] = { ...(all[k] || {}), [inp.dataset.f]: inp.value };
      saveLabels(all); refresh(box);
    }));
  });
}

// ---------------------------------------------------------------- Meteo
function centroid(geometry) {
  let sx = 0, sy = 0, n = 0;
  for (const f of geometry.fields || []) for (const ring of f.rings) for (const [x, y] of ring) { sx += x; sy += y; n++; }
  if (!n && geometry.tasks) for (const t of geometry.tasks) if (t.grid) return { lon: t.grid.min_lon + (t.grid.cols * t.grid.dlon) / 2, lat: t.grid.min_lat + (t.grid.rows * t.grid.dlat) / 2 };
  return n ? { lon: sx / n, lat: sy / n } : null;
}

function classify(h) {
  // soglie orientative di buona pratica: verifica sempre etichetta e norme locali
  const why = [];
  let level = "go";
  if (h.wind > 20 || h.gust > 30) { level = "stop"; why.push("vento forte"); }
  else if (h.wind > 12 || h.gust > 20) { level = "warn"; why.push("vento"); }
  if (h.rain > 0.1) { level = "stop"; why.push("pioggia"); }
  if (h.temp !== null && (h.temp > 28 || h.temp < 3)) { level = level === "stop" ? "stop" : "warn"; why.push(h.temp > 28 ? "caldo" : "freddo"); }
  if (h.rh !== null && h.rh < 40) { level = level === "stop" ? "stop" : "warn"; why.push("aria secca"); }
  return { level, why };
}

export async function renderWeather(geometry, fines) {
  const el = $("#tab-weather");
  const pt = centroid(geometry);
  el.innerHTML = `<p class="mut small" style="margin-top:0">Previsioni orarie sul baricentro del campo${pt ? ` (${fmt(pt.lat, 4)}, ${fmt(pt.lon, 4)})` : ""}, dati <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a>. Servono internet sul tuo dispositivo. Le soglie sono orientative.</p>
    <div id="wx-out"><span class="spin"></span> Carico le previsioni…</div>`;
  const out = $("#wx-out");
  if (!pt) { out.innerHTML = manualForm(fines, "Il file non ha coordinate del campo."); wireManual(fines); return; }
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${pt.lat.toFixed(4)}&longitude=${pt.lon.toFixed(4)}&hourly=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_gusts_10m&forecast_days=2&timezone=auto&wind_speed_unit=kmh`;
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 7000);
    const res = await fetch(url, { signal: ctl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error("meteo");
    const j = await res.json();
    const H = j.hourly;
    const now = new Date();
    const rows = [];
    for (let i = 0; i < H.time.length; i++) {
      const d = new Date(H.time[i]);
      if (d < new Date(now.getTime() - 3600e3)) continue;
      const hr = d.getHours();
      if (hr < 5 || hr > 21) continue;
      rows.push({ d, temp: H.temperature_2m[i], rh: H.relative_humidity_2m[i], rain: H.precipitation[i], wind: H.wind_speed_10m[i], gust: H.wind_gusts_10m[i] });
      if (rows.length >= 24) break;
    }
    const tiles = rows.map((r) => {
      const c = classify(r);
      return `<div class="h ${c.level}"><b>${r.d.toLocaleDateString("it-IT", { weekday: "short" })} ${String(r.d.getHours()).padStart(2, "0")}:00</b><br>
        vento ${fmt(r.wind, 0)} km/h (raffiche ${fmt(r.gust, 0)})<br>${fmt(r.temp, 0)} °C · UR ${fmt(r.rh, 0)} %${r.rain > 0 ? `<br>pioggia ${fmt(r.rain, 1)} mm` : ""}${c.why.length ? `<br><span class="small">${esc(c.why.join(", "))}</span>` : ""}</div>`;
    }).join("");
    const good = rows.filter((r) => classify(r).level === "go");
    out.innerHTML = `${driftNote(fines, Math.max(0, ...rows.slice(0, 8).map((r) => r.wind)))}
      <p><b>${good.length ? `Ore favorevoli nelle prossime 24 ore di luce: ${good.length}` : "Nessuna ora chiaramente favorevole nelle prossime ore."}</b></p>
      <div class="wx">${tiles}</div>
      <p class="small mut">Verde = condizioni buone · giallo = attenzione · rosso = meglio non trattare. Rispetta sempre le avvertenze in etichetta e le norme locali sulla deriva.</p>`;
  } catch {
    out.innerHTML = `<div class="alert amber"><b>Previsioni non raggiungibili</b>Probabilmente manca internet o il servizio non risponde. Puoi inserire a mano le condizioni di oggi.</div>${manualForm(fines)}`;
    wireManual(fines);
  }
}

function driftNote(fines, wind) {
  if (fines === null || fines === undefined) return "";
  if (wind > 10 && fines > 15)
    return `<div class="alert amber"><b>Attenzione alla deriva</b>Con il tuo hardware circa il ${fmt(fines, 0)} % delle gocce è sotto i 136 µm e le prossime ore hanno fino a ${fmt(wind, 0)} km/h di vento: valuta un ugello antideriva o una finestra più calma.</div>`;
  return "";
}

function manualForm(fines, note = "") {
  return `${note ? `<p class="mut">${esc(note)}</p>` : ""}<div class="row3"><div><label class="f">Vento (km/h)</label><input id="m-wind" type="number" min="0" step="1"></div>
    <div><label class="f">Temperatura (°C)</label><input id="m-temp" type="number" step="1"></div>
    <div><label class="f">Umidità relativa (%)</label><input id="m-rh" type="number" min="0" max="100" step="1"></div></div>
    <label class="check"><input type="checkbox" id="m-rain"><span>Piove o sta per piovere</span></label><div id="m-out" style="margin-top:8px"></div>`;
}

function wireManual(fines) {
  const upd = () => {
    const g = (id) => { const v = $(id).value; return v === "" ? null : Number(v); };
    const h = { wind: g("#m-wind") ?? 0, gust: (g("#m-wind") ?? 0) * 1.5, temp: g("#m-temp"), rh: g("#m-rh"), rain: $("#m-rain").checked ? 1 : 0 };
    const c = classify(h);
    const word = { go: "Condizioni buone per trattare.", warn: "Attenzione: " + c.why.join(", ") + ".", stop: "Meglio non trattare: " + c.why.join(", ") + "." }[c.level];
    $("#m-out").innerHTML = `<div class="alert ${c.level === "go" ? "" : c.level === "warn" ? "amber" : "red"}"><b>${word}</b></div>${driftNote(fines, h.wind)}`;
  };
  ["#m-wind", "#m-temp", "#m-rh", "#m-rain"].forEach((s) => $(s).addEventListener("input", upd));
}

// ---------------------------------------------------------------- Condivisione
export async function openShare() {
  const dlg = $("#share-dlg"), body = $("#share-body");
  body.innerHTML = '<span class="spin"></span> Cerco gli indirizzi di rete…';
  if (!dlg.open) dlg.showModal();
  try {
    const n = await api.network();
    const here = location.origin;
    const urls = n.addresses.map((a) => ({ url: a.url, note: a.note, primary: a.primary }));
    if (n.hostname_url) urls.push({ url: n.hostname_url, note: "nome del Mac (iPhone e Mac)", primary: false });
    const isLocal = /^(localhost|127\.|\[::1\])/.test(location.hostname);
    let html = "";
    if (!isLocal) html += `<div class="alert"><b>Stai usando ${esc(here)}</b>Gli altri possono usare lo stesso indirizzo se sono sulla stessa rete.</div>`;
    if (!urls.length) html += `<div class="alert red"><b>Nessuna rete trovata</b>Collega il computer al Wi-Fi o al cavo e riapri questa finestra.</div>`;
    html += urls.map((u, i) => `<div class="urlrow"><span class="url">${esc(u.url)}</span><span class="mut small">${esc(u.note)}</span><button class="btn sm" data-copy="${esc(u.url)}" type="button">Copia</button>${i === 0 ? "" : ""}</div>`).join("");
    html += `<div id="qr"></div><p class="small mut" style="text-align:center;margin:0">Inquadra con la fotocamera del telefono</p>
      <div class="alert amber" style="margin-top:14px"><b>Se l'amico non riesce ad aprire la pagina</b><ul>
      <li>Deve essere sulla <b>stessa rete Wi-Fi</b> (non dati mobili, non “rete ospiti” isolata).</li>
      <li>Su Windows, la prima volta, scegli <b>Consenti accesso</b> nella finestra del firewall (oppure lancia <code>apri_firewall_windows.bat</code>).</li>
      <li>Se ci sono più indirizzi, prova prima il primo; quelli “virtuali” di solito non funzionano.</li>
      <li>Per condividere via internet (fuori casa) serve un tunnel: vedi il file LEGGIMI.</li></ul></div>`;
    body.innerHTML = html;
    body.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); toast("Indirizzo copiato"); } catch { toast(b.dataset.copy); }
    }));
    if (urls.length && window.qrcode) {
      const qr = window.qrcode(0, "M"); qr.addData(urls[0].url); qr.make();
      $("#qr").innerHTML = qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
    }
  } catch (e) {
    body.innerHTML = `<div class="alert red"><b>Non riesco a leggere gli indirizzi</b>${esc(e.message)}</div>`;
  }
}
