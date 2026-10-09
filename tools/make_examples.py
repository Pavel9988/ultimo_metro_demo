#!/usr/bin/env python3
"""Genera i pacchetti ISOXML di esempio (sintetici ma strutturalmente corretti e georeferenziati).

Uso:  python3 tools/make_examples.py
Scrive in examples/ i file .zip e manifest.json. Non servono librerie esterne.

Convenzioni identiche a quelle del lettore (um/isoxml.py):
* GRD con A/B = lat/lon minime (angolo sud-ovest), C/D = dimensione cella in gradi,
  celle in ordine di riga, da ovest a est, prima riga a sud;
* DDI 0001 = volume per area; con VPN scala 0,01 e unità «L/ha» il valore intero è in centesimi di L/ha.
"""

from __future__ import annotations

import json
import math
import os
import random
import struct
import zipfile
from typing import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "examples")
M_PER_DEG = 111_320.0


# ---------------------------------------------------------------- geometria locale

class Frame:
    """Sistema locale in metri (x = est, y = nord) attorno a un punto di riferimento."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = M_PER_DEG * math.cos(math.radians(lat0))
        self.ky = M_PER_DEG

    def ll(self, x: float, y: float) -> tuple[float, float]:
        return self.lat0 + y / self.ky, self.lon0 + x / self.kx


def polygon_area(pts: list[tuple[float, float]]) -> float:
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def inside(pts: list[tuple[float, float]], x: float, y: float) -> bool:
    ins = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def clip_halfplane(pts: list[tuple[float, float]], nx: float, ny: float, c: float, keep_ge: bool) -> list[tuple[float, float]]:
    """Taglia il poligono con il semipiano  nx*x + ny*y >= c  (o <= c)."""
    def side(p: tuple[float, float]) -> float:
        v = nx * p[0] + ny * p[1] - c
        return v if keep_ge else -v
    out = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sa, sb = side(a), side(b)
        if sa >= 0:
            out.append(a)
        if (sa >= 0) != (sb >= 0):
            t = sa / (sa - sb)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def rotate(pts: list[tuple[float, float]], deg: float) -> list[tuple[float, float]]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def circle(cx: float, cy: float, r: float, n: int = 28) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


# ---------------------------------------------------------------- XML

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def pnt(frame: Frame, p: tuple[float, float], t: int = 2) -> str:
    lat, lon = frame.ll(*p)
    return f'<PNT A="{t}" C="{lat:.7f}" D="{lon:.7f}"/>'


def pln_xml(frame: Frame, rings: list[list[tuple[float, float]]], ptype: int, name: str, indent: str) -> str:
    lines = [f'{indent}<PLN A="{ptype}" B="{esc(name)}">']
    for i, ring in enumerate(rings):
        lines.append(f'{indent}  <LSG A="{1 if i == 0 else 2}">')
        for p in ring + [ring[0]]:
            lines.append(f"{indent}    {pnt(frame, p)}")
        lines.append(f"{indent}  </LSG>")
    lines.append(f"{indent}</PLN>")
    return "\n".join(lines)


def header(extra: str = "") -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ISO11783_TaskData VersionMajor="4" VersionMinor="3" ManagementSoftwareManufacturer="xFarm (file di esempio)" '
            'ManagementSoftwareVersion="esempio-0.6" DataTransferOrigin="1"' + extra + '>\n')


def pfd_xml(frame: Frame, pid: str, code: str, name: str, ring: list[tuple[float, float]], crop: str = "CTP1") -> str:
    area = polygon_area(ring)
    return (f'  <PFD A="{pid}" B="{code}" C="{esc(name)}" D="{int(round(area))}" E="CTR1" F="FRM1" G="{crop}">\n'
            f'{pln_xml(frame, [ring], 1, "Confine", "    ")}\n  </PFD>\n')


def common(crop: str = "Pomodoro da industria", products: tuple[str, ...] = ("Formulato A (prodotto di esempio)",)) -> str:
    s = '  <CTR A="CTR1" B="Azienda Esempio"/>\n  <FRM A="FRM1" B="Azienda Agricola Esempio" I="CTR1"/>\n'
    s += f'  <CTP A="CTP1" B="{esc(crop)}"/>\n'
    for i, p in enumerate(products, 1):
        s += f'  <PDT A="PDT{i}" B="{esc(p)}"/>\n'
    return s


def vpn_lha() -> str:
    # valore intero in centesimi di L/ha -> scala 0,01
    return '  <VPN A="VPN1" B="0" C="0.01" D="2" E="L/ha"/>\n'


def tzn(code: int, name: str, rate: float, vpn: bool = True, polys: str = "") -> str:
    raw = int(round(rate * 100)) if vpn else int(round(rate * 100))       # mm³/m² = 100 · L/ha, centesimi con VPN scala 0,01: stesso intero
    e = ' E="VPN1"' if vpn else ""
    return f'    <TZN A="{code}" B="{esc(name)}">\n      <PDV A="0001" B="{raw}"{e}/>\n{polys}    </TZN>\n'


def grid_attrs(frame: Frame, minx: float, miny: float, cell: float, cols: int, rows: int, name: str, gtype: int, template: int | None = None, geo: bool = True) -> str:
    lat, lon = frame.ll(minx, miny)
    dlat, dlon = cell / frame.ky, cell / frame.kx
    a = f'A="{lat:.7f}" B="{lon:.7f}" C="{dlat:.8f}" D="{dlon:.8f}" ' if geo else ""
    t = f' J="{template}"' if template is not None else ""
    return f'    <GRD {a}E="{cols}" F="{rows}" G="{name}" I="{gtype}"{t}/>\n'


def write_zip(name: str, files: dict[str, bytes | str]) -> None:
    path = os.path.join(OUT, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn, content in files.items():
            info = zipfile.ZipInfo(fn, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, content if isinstance(content, bytes) else content.encode("utf-8"))


# ---------------------------------------------------------------- campi

def field_a(frame: Frame) -> list[tuple[float, float]]:
    """Campo irregolare di circa 22 ha."""
    base = [(-260, -190), (240, -210), (330, 40), (180, 230), (-120, 250), (-300, 60)]
    return base


def field_b(frame: Frame) -> list[tuple[float, float]]:
    """Campo rettangolare ruotato, circa 16 ha."""
    rect = [(-200, -130), (200, -130), (200, 130), (-200, 130)]
    return [(x + 20, y - 10) for x, y in rotate(rect, 17)]


def field_c(frame: Frame) -> list[tuple[float, float]]:
    return [(-170, -110), (150, -140), (190, 90), (-20, 160), (-190, 70)]


def noise_fn(seed: int) -> Callable[[float, float], float]:
    rnd = random.Random(seed)
    waves = [(rnd.uniform(0.004, 0.012), rnd.uniform(0, math.tau), rnd.uniform(0, math.tau), rnd.uniform(0.5, 1.0)) for _ in range(5)]
    blobs = [(rnd.uniform(-200, 200), rnd.uniform(-150, 150), rnd.uniform(50, 110), rnd.choice([-1, 1]) * rnd.uniform(0.5, 1.0)) for _ in range(4)]

    def f(x: float, y: float) -> float:
        v = 0.0
        for k, ph1, ph2, amp in waves:
            v += amp * math.sin(k * x + ph1) * math.cos(k * 0.8 * y + ph2)
        for bx, by, r, a in blobs:
            v += a * 1.6 * math.exp(-((x - bx) ** 2 + (y - by) ** 2) / (2 * r * r))
        return v
    return f


def make_grid(frame: Frame, ring: list[tuple[float, float]], cell: float, seed: int, lo: float, hi: float,
              buffer_m: float = 0.0) -> tuple[float, float, int, int, list[float]]:
    """Restituisce (minx, miny, cols, rows, rates) con rates in ordine SO→NE; 0 fuori dal campo."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    minx, miny = math.floor(min(xs) / cell) * cell, math.floor(min(ys) / cell) * cell
    cols = int(math.ceil((max(xs) - minx) / cell))
    rows = int(math.ceil((max(ys) - miny) / cell))
    f = noise_fn(seed)
    samples = [f(minx + (c + .5) * cell, miny + (r + .5) * cell) for r in range(rows) for c in range(cols)]
    vmin, vmax = min(samples), max(samples)
    out = []
    for r in range(rows):
        for c in range(cols):
            x, y = minx + (c + .5) * cell, miny + (r + .5) * cell
            if not inside(ring, x, y):
                out.append(0.0)
                continue
            t = (f(x, y) - vmin) / (vmax - vmin)
            out.append(lo + (hi - lo) * t)
    if buffer_m > 0:
        # fascia di rispetto lungo il lato sud: nessun trattamento
        for r in range(rows):
            for c in range(cols):
                x, y = minx + (c + .5) * cell, miny + (r + .5) * cell
                if inside(ring, x, y) and y < min(ys) + buffer_m:
                    out[r * cols + c] = 0.0
    return minx, miny, cols, rows, out


# ---------------------------------------------------------------- esempi

def ex_zone_poligonali() -> tuple[dict, dict]:
    fr = Frame(44.9120, 9.9840)
    ring = field_a(fr)
    # tre fasce ruotate + una macchia ad alto vigore dentro la fascia centrale
    ang = 12
    nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))        # normale alle fasce
    c1, c2 = -60.0, 70.0
    z_low = clip_halfplane(ring, nx, ny, c1, keep_ge=False)
    mid = clip_halfplane(clip_halfplane(ring, nx, ny, c1, keep_ge=True), nx, ny, c2, keep_ge=False)
    z_high = clip_halfplane(ring, nx, ny, c2, keep_ge=True)
    mxs = [p[0] for p in mid]
    patch_c = (sum(mxs) / len(mxs) + 10, (c1 + c2) / 2 / ny)
    patch = circle(patch_c[0], patch_c[1], 38)
    assert all(inside(mid, x, y) for x, y in patch), "la macchia deve stare nella fascia centrale"
    zones = [
        (1, "Vigore basso", 150.0, [[p for p in z_low]], ),
        (2, "Vigore medio", 220.0, [[p for p in mid], patch]),
        (3, "Vigore alto", 300.0, [[p for p in z_high]]),
        (4, "Macchia vigorosa", 340.0, [patch]),
    ]
    body = header() + common() + pfd_xml(fr, "PFD1", "NORD", "Campo Pomodoro Nord", ring) + vpn_lha()
    body += '  <TSK A="TSK1" B="Trattamento fungicida pomodoro" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    for code, name, rate, rings in zones:
        body += tzn(code, name, rate, polys=pln_xml(fr, rings, 2, name, "      ") + "\n")
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "zone_poligonali", "file": "01_zone_poligonali_pomodoro.zip",
            "title": "01 · Pomodoro · 4 zone poligonali (150–340 L/ha)",
            "description": "Campo di 23 ha con quattro zone TZN disegnate come poligoni (una macchia con buco). "
                           "Le zone più dense superano la portata di un AFC11002 a 8 km/h: ottimo per vedere che cosa cambia cambiando ugello."}
    return meta, {"TASKDATA.XML": body}


def ex_griglia_tipo1() -> tuple[dict, dict]:
    fr = Frame(44.8620, 10.2210)
    ring = field_b(fr)
    cell = 20.0
    minx, miny, cols, rows, rates = make_grid(fr, ring, cell, seed=11, lo=0, hi=1, buffer_m=45)
    # quantizzo in 4 classi (codice zona) ; 0 = fuori campo / fascia di rispetto
    edges = [0.25, 0.5, 0.75]
    codes = bytearray()
    for r in rates:
        if r == 0.0:
            codes.append(0)
        else:
            codes.append(1 + sum(r > e for e in edges))
    zone_rate = {0: 0.0, 1: 120.0, 2: 180.0, 3: 250.0, 4: 310.0}
    zone_name = {0: "Fuori campo / fascia di rispetto", 1: "Basso", 2: "Medio", 3: "Alto", 4: "Molto alto"}
    body = header() + common("Frumento tenero", ("Formulato B (prodotto di esempio)",)) + pfd_xml(fr, "PFD1", "EST", "Campo Frumento Est", ring) + vpn_lha()
    body += '  <TSK A="TSK1" B="Trattamento frumento · griglia a zone" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    for c in sorted(zone_rate):
        body += tzn(c, zone_name[c], zone_rate[c])
    body += grid_attrs(fr, minx, miny, cell, cols, rows, "GRD00001", 1)
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "griglia_tipo1", "file": "02_griglia_tipo1_frumento.zip",
            "title": "02 · Frumento · griglia a zone con fascia di rispetto",
            "description": "Griglia GRD tipo 1 (celle da 20 m con codice zona) a quattro ratei, più una fascia a sud a dose zero."}
    return meta, {"TASKDATA.XML": body, "GRD00001.bin": bytes(codes)}


def ex_griglia_tipo2() -> tuple[dict, dict]:
    fr = Frame(44.6540, 10.6120)
    ring = field_c(fr)
    cell = 12.0
    minx, miny, cols, rows, rates = make_grid(fr, ring, cell, seed=5, lo=70, hi=360)
    raw = b"".join(struct.pack("<i", int(round(r * 100))) for r in rates)         # centesimi di L/ha
    body = header() + common("Mais da granella", ("Formulato C (prodotto di esempio)",)) + pfd_xml(fr, "PFD1", "SUD", "Campo Mais Sud", ring) + vpn_lha()
    body += '  <TSK A="TSK1" B="Trattamento mais · mappa continua" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    body += tzn(1, "Modello", 0.0)
    body += grid_attrs(fr, minx, miny, cell, cols, rows, "GRD00001", 2, template=1)
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "griglia_tipo2", "file": "03_griglia_tipo2_mappa_continua.zip",
            "title": "03 · Mais · mappa continua (70–360 L/ha)",
            "description": "Griglia GRD tipo 2: un valore diverso per ogni cella da 12 m, come in una mappa di vigore. Molte classi, utile per le fasce di dosaggio."}
    return meta, {"TASKDATA.XML": body, "GRD00001.bin": raw}


def ex_uniforme() -> tuple[dict, dict]:
    fr = Frame(45.0210, 9.7120)
    ring = field_c(fr)
    body = header() + common("Vite", ("Formulato D (prodotto di esempio)",)) + pfd_xml(fr, "PFD1", "OVEST", "Campo Ovest", ring) + vpn_lha()
    body += '  <TSK A="TSK1" B="Trattamento a rateo unico" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    body += tzn(1, "Rateo unico", 200.0)
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "uniforme", "file": "04_rateo_uniforme.zip", "title": "04 · Rateo unico 200 L/ha",
            "description": "Una sola zona senza geometria: tutto il campo allo stesso rateo. Serve a verificare la fattibilità di un valore costante."}
    return meta, {"TASKDATA.XML": body}


def ex_due_task() -> tuple[dict, dict]:
    fr = Frame(44.7480, 10.1020)
    ring_a = field_b(fr)
    ring_b = [(x + 620, y + 40) for x, y in field_c(fr)]
    # task 1: zone poligonali nel campo A (due fasce); task 2: griglia tipo 1 nel campo B
    nx, ny = 0.0, 1.0
    z1 = clip_halfplane(ring_a, nx, ny, 0.0, keep_ge=False)
    z2 = clip_halfplane(ring_a, nx, ny, 0.0, keep_ge=True)
    cell = 20.0
    minx, miny, cols, rows, rates = make_grid(fr, ring_b, cell, seed=23, lo=0, hi=1)
    codes = bytes(0 if r == 0.0 else (1 if r < 0.5 else 2) for r in rates)
    body = header() + common("Girasole", ("Formulato E (prodotto di esempio)", "Formulato F (prodotto di esempio)"))
    body += pfd_xml(fr, "PFD1", "A", "Campo Girasole A", ring_a) + pfd_xml(fr, "PFD2", "B", "Campo Girasole B", ring_b) + vpn_lha()
    body += '  <TSK A="TSK1" B="Diserbo · campo A" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    body += tzn(1, "Zona sud", 140.0, polys=pln_xml(fr, [z1], 2, "Zona sud", "      ") + "\n")
    body += tzn(2, "Zona nord", 210.0, polys=pln_xml(fr, [z2], 2, "Zona nord", "      ") + "\n")
    body += "  </TSK>\n"
    body += '  <TSK A="TSK2" B="Insetticida · campo B" C="CTR1" D="FRM1" E="PFD2" G="1">\n    <PAN A="PDT2"/>\n'
    body += tzn(0, "Fuori campo", 0.0) + tzn(1, "Bassa pressione parassita", 110.0) + tzn(2, "Alta pressione parassita", 260.0)
    body += grid_attrs(fr, minx, miny, cell, cols, rows, "GRD00002", 1)
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "due_task", "file": "05_due_campi_due_task.zip", "title": "05 · Due campi, due operazioni",
            "description": "Un file con due appezzamenti e due task (zone poligonali + griglia). Il selettore di operazione compare in alto."}
    return meta, {"TASKDATA.XML": body, "GRD00002.bin": codes}


def ex_senza_geometria() -> tuple[dict, dict]:
    fr = Frame(44.5510, 11.0420)
    ring = field_a(fr)
    body = header() + common("Pomodoro da industria") + pfd_xml(fr, "PFD1", "SUD", "Campo Sud", ring) + vpn_lha()
    body += '  <TSK A="TSK1" B="Zone senza geometria" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    body += tzn(1, "Zona 1", 130.0) + tzn(2, "Zona 2", 190.0) + tzn(3, "Zona 3", 330.0)
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "senza_geometria", "file": "06_zone_senza_geometria.zip", "title": "06 · Zone senza geometria nel file",
            "description": "Tre ratei ma nessuna posizione (né poligoni né griglia): l'app lo dichiara e non disegna zone inventate."}
    return meta, {"TASKDATA.XML": body}


def ex_senza_georef() -> tuple[dict, dict]:
    fr = Frame(44.9930, 10.4410)
    ring = field_b(fr)
    cell = 25.0
    minx, miny, cols, rows, rates = make_grid(fr, ring, cell, seed=31, lo=0, hi=1)
    codes = bytes(0 if r == 0.0 else (1 if r < 0.5 else 2) for r in rates)
    body = header() + common("Orzo") + pfd_xml(fr, "PFD1", "N", "Campo Orzo", ring) + vpn_lha()
    body += '  <TSK A="TSK1" B="Griglia senza coordinate" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    body += tzn(0, "Fuori campo", 0.0) + tzn(1, "Zona bassa", 160.0) + tzn(2, "Zona alta", 240.0)
    body += grid_attrs(fr, minx, miny, cell, cols, rows, "GRD00001", 1, geo=False)
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "senza_georef", "file": "07_griglia_senza_coordinate.zip", "title": "07 · Griglia senza coordinate (A–D mancanti)",
            "description": "Alcuni software omettono la posizione della griglia: l'app la adatta al campo e lo segnala."}
    return meta, {"TASKDATA.XML": body, "GRD00001.bin": codes}


def ex_xfr_senza_vpn() -> tuple[dict, dict]:
    fr = Frame(44.8210, 9.8230)
    ring = field_c(fr)
    # campo in file esterno (XFR) e dosi senza VPN: valore intero in mm³/m² (1 L/ha = 100)
    pfd = header() + pfd_xml(fr, "PFD1", "XFR", "Campo da file esterno", ring) + "</ISO11783_TaskData>\n"
    z1 = clip_halfplane(ring, 1, 0, -10, keep_ge=False)
    z2 = clip_halfplane(ring, 1, 0, -10, keep_ge=True)
    body = header() + common("Soia") + '  <XFR A="PFD00001" B="1"/>\n'
    body += '  <TSK A="TSK1" B="Dosi senza VPN, campo in XFR" C="CTR1" D="FRM1" E="PFD1" G="1">\n    <PAN A="PDT1"/>\n'
    body += tzn(1, "Ovest", 90.0, vpn=False, polys=pln_xml(fr, [z1], 2, "Ovest", "      ") + "\n")
    body += tzn(2, "Est", 175.0, vpn=False, polys=pln_xml(fr, [z2], 2, "Est", "      ") + "\n")
    body += "  </TSK>\n</ISO11783_TaskData>\n"
    meta = {"id": "xfr_senza_vpn", "file": "08_file_esterno_e_dosi_senza_vpn.zip", "title": "08 · Campo in file esterno (XFR) e dosi senza VPN",
            "description": "Caso reale frequente: il campo sta in un XML esterno e i ratei sono interi in mm³/m² senza tabella VPN."}
    return meta, {"TASKDATA.XML": body, "PFD00001.XML": pfd}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for fn in os.listdir(OUT):
        if fn.endswith(".zip") or fn == "manifest.json":
            os.remove(os.path.join(OUT, fn))
    manifest = []
    for fn in (ex_zone_poligonali, ex_griglia_tipo1, ex_griglia_tipo2, ex_uniforme, ex_due_task, ex_senza_geometria,
               ex_senza_georef, ex_xfr_senza_vpn):
        meta, files = fn()
        write_zip(meta["file"], files)
        manifest.append(meta)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print(f"Scritti {len(manifest)} esempi in {OUT}")


if __name__ == "__main__":
    main()
