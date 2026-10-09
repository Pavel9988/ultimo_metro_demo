// Utilità comuni: selettori, formattazione italiana, toast, debounce, stato dei piani.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const nf = new Map();
export function fmt(v, d = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (!nf.has(d)) nf.set(d, new Intl.NumberFormat("it-IT", { minimumFractionDigits: d, maximumFractionDigits: d }));
  return nf.get(d).format(v);
}

export function debounce(fn, ms) {
  let t = null;
  const f = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  f.cancel = () => clearTimeout(t);
  return f;
}

let toastTimer = null;
export function toast(msg, isErr = false, ms = 4200) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}

// Stato di una classe sul tuo hardware (codici di una lettera inviati dal server)
export const STATUS = {
  o: { key: "ok", name: "Perfetto", color: "#1f9d55", cls: "ok" },
  a: { key: "adapt", name: "Con adattamento", color: "#e0a100", cls: "adapt" },
  u: { key: "under", name: "Sotto-dosato", color: "#E03040", cls: "under" },
  v: { key: "over", name: "Sovra-dosato", color: "#7b3fb8", cls: "over" },
  f: { key: "off", name: "Non trattare", color: "#cfd7de", cls: "off" },
  n: { key: "nodata", name: "Dato mancante", color: "#98a4ae", cls: "off" },
  x: { key: "novra", name: "Rateo variabile non eseguibile", color: "#3b4650", cls: "novra" },
};
export const STATUS_BY_KEY = Object.fromEntries(Object.values(STATUS).map((s) => [s.key, s]));
export const DIFF = {
  b: { name: "Va meglio", color: "#1f9d55" },
  w: { name: "Va peggio", color: "#E03040" },
  s: { name: "Invariato", color: "#d9e2e8" },
};

export function badge(code) {
  const s = STATUS[code] || STATUS.n;
  return `<span class="badge ${s.cls}">${esc(s.name)}</span>`;
}

// Rampa blu per i ratei (chiaro = poco, scuro = tanto)
export function rampColor(t) {
  t = Math.max(0, Math.min(1, t));
  const a = [219, 238, 250], b = [0, 58, 102];
  const mid = [0, 122, 201];
  let c;
  if (t < 0.5) c = a.map((x, i) => x + (mid[i] - x) * (t / 0.5));
  else c = mid.map((x, i) => x + (b[i] - x) * ((t - 0.5) / 0.5));
  return `rgb(${c.map(Math.round).join(",")})`;
}
