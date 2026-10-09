// Mappa del campo su canvas: contorno vero, griglia a celle o poligoni di zona, colori per vista.

const M_PER_DEG = 111320;
const OUTSIDE = 0xffff;

function b64ToU16(b64) {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Uint16Array(buf.buffer, 0, buf.length >> 1);   // little-endian come sul server
}

function inRings(x, y, rings) {            // regola pari-dispari: i buchi restano buchi
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

export class FieldMap {
  constructor(canvas, handlers = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext("2d");
    this.h = handlers;
    this.fields = [];
    this.task = null;
    this.colors = [];
    this.selected = null;
    this.hover = null;
    this.proj = null;
    this._grid = null;
    this._off = null;
    this._dirty = true;
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    new ResizeObserver(() => this.resize()).observe(canvas);
    canvas.addEventListener("mousemove", (e) => this._move(e));
    canvas.addEventListener("mouseleave", () => this._leave());
    canvas.addEventListener("click", (e) => this._click(e));
    canvas.addEventListener("touchstart", (e) => { if (e.touches[0]) this._click(e.touches[0], true); }, { passive: true });
  }

  setData(geometry, taskIndex) {
    this.fields = geometry.fields || [];
    this.task = (geometry.tasks || []).find((t) => t.index === taskIndex) || null;
    this._grid = null;
    if (this.task && this.task.grid) {
      const g = this.task.grid;
      this._grid = { ...g, cls: b64ToU16(g.cells) };
    }
    this._bounds();
    this._dirty = true;
    this.draw();
  }

  setColors(colors) { this.colors = colors || []; this._dirty = true; this.draw(); }
  setSelected(i) { this.selected = i; this._dirty = true; this.draw(); }

  hasGeometry() { return !!this.proj; }
  hasCells() { return !!(this._grid || (this.task && this.task.polygons && this.task.polygons.length)); }

  // ---- geometria ----
  _bounds() {
    let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
    const add = (x, y) => { if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; };
    for (const f of this.fields) for (const r of f.rings) for (const [x, y] of r) add(x, y);
    if (this._grid) {
      const g = this._grid;
      add(g.min_lon, g.min_lat); add(g.min_lon + g.cols * g.dlon, g.min_lat + g.rows * g.dlat);
    }
    if (this.task) for (const p of this.task.polygons || []) for (const r of p.rings) for (const [x, y] of r) add(x, y);
    this.bb = isFinite(minx) ? { minx, maxx, miny, maxy } : null;
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    const w = Math.max(10, Math.round(r.width * this.dpr)), h = Math.max(10, Math.round(r.height * this.dpr));
    if (this.cv.width !== w || this.cv.height !== h) { this.cv.width = w; this.cv.height = h; }
    this.draw();
  }

  _project() {
    const bb = this.bb;
    if (!bb) { this.proj = null; return; }
    const W = this.cv.width, H = this.cv.height, pad = 26 * this.dpr;
    const lat0 = (bb.miny + bb.maxy) / 2, kx = Math.cos((lat0 * Math.PI) / 180);
    const wm = Math.max(1e-9, (bb.maxx - bb.minx) * kx), hm = Math.max(1e-9, bb.maxy - bb.miny);
    const s = Math.min((W - 2 * pad) / wm, (H - 2 * pad) / hm);
    const ox = (W - wm * s) / 2, oy = (H - hm * s) / 2;
    this.proj = {
      s, kx,
      x: (lon) => ox + (lon - bb.minx) * kx * s,
      y: (lat) => H - oy - (lat - bb.miny) * s,
      lon: (px) => (px - ox) / (kx * s) + bb.minx,
      lat: (py) => (H - oy - py) / s + bb.miny,
    };
  }

  // ---- disegno ----
  draw() {
    const ctx = this.ctx, W = this.cv.width, H = this.cv.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    this._project();
    const P = this.proj;
    if (!P) return;
    const sel = this.selected;
    const dim = sel !== null && sel !== undefined;

    // celle di griglia
    if (this._grid) this._drawGrid(ctx, P, dim);

    // poligoni di zona
    if (this.task && this.task.polygons && this.task.polygons.length) {
      for (const p of this.task.polygons) {
        const c = this.colors[p.class];
        if (!c) continue;
        ctx.beginPath();
        for (const ring of p.rings) ring.forEach(([x, y], i) => (i ? ctx.lineTo(P.x(x), P.y(y)) : ctx.moveTo(P.x(x), P.y(y))));
        ctx.closePath();
        ctx.globalAlpha = dim && p.class !== sel ? 0.28 : 1;
        ctx.fillStyle = c;
        ctx.fill("evenodd");
        ctx.globalAlpha = 1;
        ctx.strokeStyle = "rgba(255,255,255,.85)";
        ctx.lineWidth = 1.2 * this.dpr;
        ctx.stroke();
        if (p.class === sel) { ctx.strokeStyle = "#13222e"; ctx.lineWidth = 2.6 * this.dpr; ctx.stroke(); }
      }
    } else if (!this._grid && this.task && this.colors.length === 1 && this.colors[0]) {
      // rateo unico senza geometria: tutto il campo dello stesso colore
      for (const f of this.fields) {
        ctx.beginPath();
        for (const ring of f.rings) ring.forEach(([x, y], i) => (i ? ctx.lineTo(P.x(x), P.y(y)) : ctx.moveTo(P.x(x), P.y(y))));
        ctx.closePath();
        ctx.fillStyle = this.colors[0];
        ctx.fill("evenodd");
      }
    }

    // contorno del campo
    for (const f of this.fields) {
      ctx.beginPath();
      for (const ring of f.rings) { ring.forEach(([x, y], i) => (i ? ctx.lineTo(P.x(x), P.y(y)) : ctx.moveTo(P.x(x), P.y(y)))); ctx.closePath(); }
      ctx.strokeStyle = "#0b4f80";
      ctx.lineWidth = 2.4 * this.dpr;
      ctx.lineJoin = "round";
      ctx.stroke();
    }
    this._furniture(ctx, P);
  }

  _drawGrid(ctx, P, dim) {
    const g = this._grid;
    if (!this._off || this._dirty) {
      const off = this._off || document.createElement("canvas");
      off.width = g.cols; off.height = g.rows;
      const octx = off.getContext("2d");
      const img = octx.createImageData(g.cols, g.rows);
      const rgba = this._rgba();
      const sel = this.selected;
      for (let r = 0; r < g.rows; r++) {
        const yy = g.rows - 1 - r;                    // la riga 0 del file è a SUD: in alto va il nord
        for (let c = 0; c < g.cols; c++) {
          const k = g.cls[r * g.cols + c];
          const o = (yy * g.cols + c) * 4;
          if (k === OUTSIDE || !rgba[k]) { img.data[o + 3] = 0; continue; }
          const q = rgba[k];
          img.data[o] = q[0]; img.data[o + 1] = q[1]; img.data[o + 2] = q[2];
          img.data[o + 3] = dim && k !== sel ? 70 : 255;
        }
      }
      octx.putImageData(img, 0, 0);
      this._off = off;
      this._dirty = false;
    }
    const x0 = P.x(g.min_lon), x1 = P.x(g.min_lon + g.cols * g.dlon);
    const y0 = P.y(g.min_lat + g.rows * g.dlat), y1 = P.y(g.min_lat);
    ctx.imageSmoothingEnabled = false;
    ctx.save();
    const clipped = this.fields.some((f) => !f.from_grid && f.rings.length);
    if (clipped) {                       // le celle non escono dal contorno del campo
      ctx.beginPath();
      for (const f of this.fields) if (!f.from_grid) for (const ring of f.rings) { ring.forEach(([x, y], i) => (i ? ctx.lineTo(P.x(x), P.y(y)) : ctx.moveTo(P.x(x), P.y(y)))); ctx.closePath(); }
      ctx.clip("evenodd");
    }
    ctx.drawImage(this._off, x0, y0, x1 - x0, y1 - y0);
    ctx.restore();
  }

  _rgba() {
    const cvs = document.createElement("canvas");
    cvs.width = cvs.height = 1;
    const c = cvs.getContext("2d", { willReadFrequently: true });
    return this.colors.map((col) => {
      if (!col) return null;
      c.clearRect(0, 0, 1, 1); c.fillStyle = col; c.fillRect(0, 0, 1, 1);
      const d = c.getImageData(0, 0, 1, 1).data;
      return [d[0], d[1], d[2]];
    });
  }

  _furniture(ctx, P) {
    const d = this.dpr;
    // barra della scala
    const metersPerPx = M_PER_DEG / P.s;              // metri per pixel del canvas
    const want = metersPerPx * 110 * d;
    const nice = [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000].reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a));
    const len = nice / metersPerPx;
    const x = 16 * d, y = this.cv.height - 16 * d;
    ctx.fillStyle = "rgba(255,255,255,.82)";
    ctx.fillRect(x - 6 * d, y - 22 * d, len + 12 * d, 30 * d);
    ctx.strokeStyle = "#13222e"; ctx.lineWidth = 2 * d;
    ctx.beginPath(); ctx.moveTo(x, y - 4 * d); ctx.lineTo(x, y); ctx.lineTo(x + len, y); ctx.lineTo(x + len, y - 4 * d); ctx.stroke();
    ctx.fillStyle = "#13222e"; ctx.font = `600 ${12 * d}px "Source Sans 3",sans-serif`; ctx.textBaseline = "bottom";
    ctx.fillText(nice >= 1000 ? `${nice / 1000} km` : `${nice} m`, x + 2 * d, y - 6 * d);
    // nord
    const nx = this.cv.width - 26 * d, ny = 22 * d;
    ctx.fillStyle = "rgba(255,255,255,.85)"; ctx.beginPath(); ctx.arc(nx, ny + 6 * d, 17 * d, 0, 7); ctx.fill();
    ctx.fillStyle = "#E03040"; ctx.beginPath(); ctx.moveTo(nx, ny - 8 * d); ctx.lineTo(nx - 6 * d, ny + 6 * d); ctx.lineTo(nx + 6 * d, ny + 6 * d); ctx.fill();
    ctx.fillStyle = "#13222e"; ctx.textAlign = "center"; ctx.fillText("N", nx, ny + 21 * d); ctx.textAlign = "start";
  }

  // ---- interazione ----
  _hit(e) {
    const P = this.proj;
    if (!P) return null;
    const r = this.cv.getBoundingClientRect();
    const px = (e.clientX - r.left) * this.dpr, py = (e.clientY - r.top) * this.dpr;
    const lon = P.lon(px), lat = P.lat(py);
    if (this._grid) {
      const g = this._grid;
      const c = Math.floor((lon - g.min_lon) / g.dlon), rr = Math.floor((lat - g.min_lat) / g.dlat);
      if (c >= 0 && rr >= 0 && c < g.cols && rr < g.rows) {
        const k = g.cls[rr * g.cols + c];
        if (k !== OUTSIDE && this.colors[k]) return k;
      }
      return null;
    }
    if (this.task && this.task.polygons && this.task.polygons.length) {
      const ps = this.task.polygons;
      for (let i = ps.length - 1; i >= 0; i--) if (inRings(lon, lat, ps[i].rings)) return ps[i].class;
      return null;
    }
    if (this.colors.length === 1 && this.fields.some((f) => inRings(lon, lat, f.rings))) return 0;
    return null;
  }

  _move(e) {
    const k = this._hit(e);
    this.cv.style.cursor = k === null ? "default" : "pointer";
    if (k !== this.hover) this.hover = k;
    this.h.hover && this.h.hover(k, e);
  }
  _leave() { this.hover = null; this.h.hover && this.h.hover(null, null); }
  _click(e, touch = false) {
    const k = this._hit(e);
    this.h.click && this.h.click(k, touch ? e : e);
  }
}
