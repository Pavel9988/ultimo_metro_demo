// Chiamate al server. Gli errori diventano eccezioni con un messaggio leggibile.

async function parse(res) {
  const ct = res.headers.get("Content-Type") || "";
  if (ct.includes("application/json")) {
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || `Errore ${res.status}`);
    return data;
  }
  if (!res.ok) throw new Error(`Errore ${res.status}`);
  return res;
}

async function request(url, opts = {}) {
  let res;
  try {
    res = await fetch(url, { credentials: "same-origin", ...opts });
  } catch (e) {
    throw new Error("Non riesco a raggiungere il server. È ancora acceso?");
  }
  return parse(res);
}

const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  session: () => request("/api/session"),
  examples: () => request("/api/examples"),
  network: () => request("/api/network"),
  example: (id) => request("/api/example", json({ id })),
  reset: () => request("/api/reset", json({})),
  upload: (file) => request("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
    body: file,
  }),
  evaluate: (body, signal) => request("/api/evaluate", { ...json(body), signal }),
  async exportFile(body) {
    const res = await request("/api/export", json(body));
    const blob = await res.blob();
    let name = "ISOXML_NORDSON.zip";
    const cd = res.headers.get("Content-Disposition") || "";
    const m = /filename="?([^";]+)"?/.exec(cd);
    if (m) name = m[1];
    let summary = null;
    try { summary = JSON.parse(decodeURIComponent(res.headers.get("X-UM-Summary") || "")); } catch { /* facoltativo */ }
    return { blob, name, summary };
  },
  async report(body) {
    const res = await request("/api/report", json(body));
    return res.text();
  },
  catalog: async () => (await fetch("/data/arag_catalog.json")).json(),
};
