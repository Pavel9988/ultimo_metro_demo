"""Lettura e scrittura di pacchetti ISOXML (ISO 11783-10) per prescrizioni di irrorazione.

Questo modulo fa tre cose:

1. apre in modo sicuro uno ZIP/XML ISOXML (anche con file esterni referenziati da XFR);
2. costruisce un modello neutro della prescrizione: campo, task, "classi di rateo"
   (zone TZN o valori distinti di una griglia GRD) con la loro geometria reale;
3. riscrive i ratei modificati nei PDV e nel binario GRD lasciando intatto il resto.

Convenzioni usate (da ISO 11783-10, come le intende l'autore: vanno verificate con un
export reale del proprio FMIS):

* GRD: A/B = latitudine/longitudine minime (angolo sud-ovest), C/D = altezza/larghezza
  della cella in gradi, E = colonne, F = righe, G = nome file (senza estensione, .bin),
  I = tipo (1 = un byte con il codice zona, 2 = un int32 little-endian per ogni PDV della
  zona modello), J = codice della zona modello (tipo 2).
* Celle in ordine di riga, da ovest a est, con la prima riga a sud.
* PDV: A = DDI esadecimale, B = valore intero, E = riferimento alla VPN.
  DDI 0001 = volume per area (mm³/m², cioè 1 L/ha = 100).
"""

from __future__ import annotations

import array
import base64
import io
import math
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterator, Optional

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_ZIP_MEMBERS = 2500
MAX_GRID_CELLS = 4_000_000
DISPLAY_MAX_CELLS = 360_000      # oltre questa soglia la griglia inviata al browser viene sottocampionata
MAX_DISTINCT_RATES = 4000        # oltre questa soglia i ratei di una GRD tipo 2 vengono raggruppati a 0,5 L/ha
OUTSIDE = 0xFFFF                 # cella fuori dal campo / senza dato

M_PER_DEG = 111_320.0


class IsoxmlError(ValueError):
    """Errore comprensibile all'utente."""


# --------------------------------------------------------------------------- utilità XML

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def attr(el: ET.Element, key: str, default: str = "") -> str:
    return el.attrib.get(key, default)


def children(el: ET.Element, tag: str) -> list[ET.Element]:
    return [c for c in list(el) if local(c.tag) == tag]


def descendants(el: ET.Element, tag: str) -> list[ET.Element]:
    return [c for c in el.iter() if local(c.tag) == tag]


def parse_xml(data: bytes) -> ET.Element:
    if len(data) > MAX_UPLOAD_BYTES:
        raise IsoxmlError("Il file XML supera la dimensione consentita.")
    head = data[:16384].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise IsoxmlError("Il file contiene dichiarazioni DTD/ENTITY, non ammesse per sicurezza.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise IsoxmlError(f"XML non valido: {exc}") from exc
    return root


# --------------------------------------------------------------------------- pacchetto

@dataclass
class Doc:
    path: str
    root: ET.Element


@dataclass
class Package:
    filename: str
    was_zip: bool
    files: dict[str, bytes]
    docs: list[Doc]
    modes: dict[str, int] = field(default_factory=dict)   # permessi unix originali (non usati se assenti)

    @property
    def main(self) -> Doc:
        return self.docs[0]

    def all(self, tag: str) -> Iterator[ET.Element]:
        for d in self.docs:
            for el in d.root.iter():
                if local(el.tag) == tag:
                    yield el

    def find_file(self, name: str) -> Optional[str]:
        """Cerca un file del pacchetto per nome (senza distinzione maiuscole/minuscole)."""
        target = name.lower()
        hits = [p for p in self.files if PurePosixPath(p).name.lower() == target]
        if not hits:
            return None
        return sorted(hits, key=lambda p: (p.count("/"), len(p)))[0]


def read_package(raw: bytes, filename: str) -> Package:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise IsoxmlError("Il file supera il limite di 25 MB.")
    files: dict[str, bytes] = {}
    was_zip = zipfile.is_zipfile(io.BytesIO(raw))
    if was_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]
                if len(infos) > MAX_ZIP_MEMBERS:
                    raise IsoxmlError("Il pacchetto contiene troppi file.")
                if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
                    raise IsoxmlError("Il pacchetto estratto supererebbe il limite consentito.")
                for info in infos:
                    path = info.filename.replace("\\", "/")
                    pure = PurePosixPath(path)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise IsoxmlError("Il pacchetto ZIP contiene un percorso non sicuro.")
                    if info.flag_bits & 0x1:
                        raise IsoxmlError("I file ZIP protetti da password non sono supportati.")
                    files[path] = zf.read(info)
        except zipfile.BadZipFile as exc:
            raise IsoxmlError("Il pacchetto ZIP non è leggibile.") from exc
        candidates = [p for p in files if PurePosixPath(p).name.upper() == "TASKDATA.XML"]
        if candidates:
            main_path = sorted(candidates, key=lambda p: (p.count("/"), len(p)))[0]
        else:
            xmls = [p for p in files if p.lower().endswith(".xml") and b"ISO11783_TaskData" in files[p][:16384]]
            if len(xmls) != 1:
                raise IsoxmlError("Nel pacchetto ZIP non trovo un TASKDATA.XML riconoscibile.")
            main_path = xmls[0]
    else:
        if not filename.lower().endswith((".xml", ".isoxml")):
            raise IsoxmlError("Carica un pacchetto .zip oppure un TASKDATA.XML.")
        main_path = "TASKDATA.XML"
        files[main_path] = raw

    main_root = parse_xml(files[main_path])
    if local(main_root.tag) != "ISO11783_TaskData":
        raise IsoxmlError("Questo XML non è un TASKDATA ISOXML (manca la radice ISO11783_TaskData).")
    docs = [Doc(main_path, main_root)]

    # File esterni referenziati da XFR (un solo livello).
    base_dir = str(PurePosixPath(main_path).parent)
    for xfr in descendants(main_root, "XFR"):
        name = attr(xfr, "A")
        if not name:
            continue
        wanted = name if name.lower().endswith(".xml") else name + ".xml"
        found = None
        for p in files:
            if PurePosixPath(p).name.lower() == wanted.lower() and str(PurePosixPath(p).parent) == base_dir:
                found = p
                break
        if found is None:
            found = next((p for p in files if PurePosixPath(p).name.lower() == wanted.lower()), None)
        if found and all(d.path != found for d in docs):
            ext_root = parse_xml(files[found])
            if local(ext_root.tag) == "ISO11783_TaskData":
                docs.append(Doc(found, ext_root))
    return Package(filename=filename, was_zip=was_zip, files=files, docs=docs)


# --------------------------------------------------------------------------- unità e conversioni

@dataclass
class RateConv:
    """Conversione tra valore intero ISOXML e L/ha."""
    offset: float = 0.0
    scale: float = 1.0
    factor: float = 0.01          # 1 mm³/m² = 0,01 L/ha; per VPN già in L/ha vale 1
    decimals: int = 2
    unit: str = "L/ha"

    def to_lha(self, raw: float) -> float:
        return (float(raw) + self.offset) * self.scale * self.factor

    def to_raw(self, lha: float) -> int:
        denom = self.scale * self.factor
        if denom == 0:
            raise IsoxmlError("Una VPN con scala 0 non può essere riscritta.")
        raw = round(float(lha) / denom - self.offset)
        if raw < -2_147_483_648 or raw > 2_147_483_647:
            raise IsoxmlError("Il rateo calcolato esce dal range intero ISOXML.")
        return int(raw)


_VPN_CACHE_ATTR = "_um_vpn"


def _norm_unit(unit: str) -> str:
    u = unit.lower().replace(" ", "").replace("litri", "l").replace("litro", "l").replace("³", "3").replace("²", "2")
    return u.replace("lt/", "l/")


def vpn_table(pkg: Package) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for vpn in pkg.all("VPN"):
        out[attr(vpn, "A")] = {
            "offset": num(attr(vpn, "B"), 0.0) or 0.0,
            "scale": num(attr(vpn, "C"), 1.0) if num(attr(vpn, "C"), 1.0) is not None else 1.0,
            "decimals": int(num(attr(vpn, "D"), 0) or 0),
            "unit": attr(vpn, "E"),
        }
    return out


def rate_conv_for(pdv: ET.Element, vpns: dict[str, dict[str, Any]]) -> Optional[RateConv]:
    """Restituisce la conversione se il PDV è un rateo di volume per area, altrimenti None."""
    ddi_txt = attr(pdv, "A").strip()
    try:
        ddi = int(ddi_txt, 16) if ddi_txt else -1
    except ValueError:
        ddi = -1
    vpn = vpns.get(attr(pdv, "E"))
    if vpn is not None:
        unit = _norm_unit(vpn["unit"])
        if unit in ("l/ha",) or unit.startswith("l/ha"):
            return RateConv(vpn["offset"], vpn["scale"], 1.0, vpn["decimals"], "L/ha")
        if "mm3/m2" in unit:
            return RateConv(vpn["offset"], vpn["scale"], 0.01, max(vpn["decimals"], 0), "L/ha")
        if ddi == 0x0001:
            # VPN con unità non riconosciuta ma DDI di volume per area: valore standard mm³/m²
            return RateConv(vpn["offset"], vpn["scale"], 0.01, 2, "L/ha")
        return None
    if ddi == 0x0001:
        return RateConv(0.0, 1.0, 0.01, 2, "L/ha")
    return None


# --------------------------------------------------------------------------- geometria

def _ring_from_lsg(lsg: ET.Element) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for pnt in children(lsg, "PNT"):
        lat, lon = num(attr(pnt, "C")), num(attr(pnt, "D"))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        ring.append((lon, lat))
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    return ring


def polygon_rings(pln: ET.Element) -> list[list[tuple[float, float]]]:
    """Anelli di un PLN: prima gli esterni (LSG tipo 1), poi gli interni (tipo 2)."""
    exteriors, interiors = [], []
    for lsg in children(pln, "LSG"):
        ring = _ring_from_lsg(lsg)
        if len(ring) < 3:
            continue
        t = attr(lsg, "A")
        (interiors if t == "2" else exteriors).append(ring)
    return exteriors + interiors


def ring_area_m2(ring: list[tuple[float, float]], lat0: float) -> float:
    k = math.cos(math.radians(lat0))
    area = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0] * M_PER_DEG * k, ring[i][1] * M_PER_DEG
        x2, y2 = ring[(i + 1) % n][0] * M_PER_DEG * k, ring[(i + 1) % n][1] * M_PER_DEG
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def rings_area_ha(rings: list[list[tuple[float, float]]], lat0: float) -> float:
    """Area con regola pari-dispari: primo anello esterno meno gli altri se contenuti (approssimazione)."""
    if not rings:
        return 0.0
    total = 0.0
    for i, ring in enumerate(rings):
        a = ring_area_m2(ring, lat0)
        total += a if i == 0 or not _ring_inside(ring, rings[0]) else -a
    return max(total, 0.0) / 10_000.0


def _ring_inside(inner: list[tuple[float, float]], outer: list[tuple[float, float]]) -> bool:
    return _point_in_ring(inner[0][0], inner[0][1], outer)


def _point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def row_intervals(rings: list[list[tuple[float, float]]], y: float) -> list[tuple[float, float]]:
    """Intervalli di longitudine all'interno dei poligoni alla latitudine y (pari-dispari su tutti gli anelli)."""
    xs: list[float] = []
    for ring in rings:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y):
                xs.append((xj - xi) * (y - yi) / (yj - yi) + xi)
            j = i
    xs.sort()
    return [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]


# --------------------------------------------------------------------------- modello

@dataclass
class Klass:
    """Una classe di rateo: una zona TZN oppure un valore (raggruppato) di una griglia a valori."""
    idx: int
    label: str
    zone_code: Optional[str]
    rate: Optional[float]            # L/ha della variabile principale; None se non leggibile
    area_ha: Optional[float]
    cells: int = 0
    raws: list[int] = field(default_factory=list)
    pdvs: list[ET.Element] = field(default_factory=list)
    conv: Optional[RateConv] = None
    color: str = ""


@dataclass
class GridModel:
    cols: int
    rows: int
    min_lat: float
    min_lon: float
    dlat: float
    dlon: float
    geo: bool
    gtype: int
    path: str                        # percorso del .bin nel pacchetto
    element: ET.Element
    cell_class: array.array          # uint16 per cella (OUTSIDE = fuori campo)
    template_pdvs: list[ET.Element] = field(default_factory=list)
    primary_var: int = 0
    raw_by_cell: Optional[array.array] = None   # int32 del rateo principale (solo tipo 2)
    cell_area_ha: float = 0.0


@dataclass
class TaskModel:
    index: int
    id: str
    name: str
    field_id: str
    field_name: str
    element: ET.Element
    products: list[str]
    kind: str                        # grid1 | grid2 | zones_geo | zones_nogeo | none
    classes: list[Klass]
    grid: Optional[GridModel] = None
    polygons: list[dict[str, Any]] = field(default_factory=list)
    extra_rate_vars: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def treated_area_ha(self) -> Optional[float]:
        if any(c.area_ha is None for c in self.classes):
            return None
        return sum(c.area_ha for c in self.classes if c.rate and c.rate > 0)  # type: ignore[misc]


@dataclass
class FieldModel:
    id: str
    name: str
    area_ha: Optional[float]
    crop: str
    rings: list[list[tuple[float, float]]]
    boundary_from_grid: bool = False


@dataclass
class Rx:
    pkg: Package
    fields: list[FieldModel]
    tasks: list[TaskModel]
    products: list[dict[str, str]]
    devices: list[dict[str, Any]]
    warnings: list[dict[str, str]]
    meta: dict[str, Any]


ZONE_COLORS = ["#007AC9", "#2E9E5B", "#F2A33A", "#8E5BD6", "#E03040", "#17A2B8", "#B5651D", "#6C7A89"]


# --------------------------------------------------------------------------- analisi

def analyse(pkg: Package) -> Rx:
    vpns = vpn_table(pkg)
    root = pkg.main.root

    # prodotti e colture
    products = [{"id": attr(p, "A"), "name": attr(p, "B") or attr(p, "A")} for p in pkg.all("PDT")]
    product_name = {p["id"]: p["name"] for p in products}
    crops = {attr(c, "A"): attr(c, "B") or attr(c, "A") for c in pkg.all("CTP")}

    # campi
    fields: list[FieldModel] = []
    for pfd in pkg.all("PFD"):
        rings: list[list[tuple[float, float]]] = []
        for pln in children(pfd, "PLN"):
            ptype = attr(pln, "A")
            if ptype in ("", "1"):
                rings.extend(polygon_rings(pln))
        area_m2 = num(attr(pfd, "D"))
        area_ha = round(area_m2 / 10_000.0, 2) if area_m2 is not None and area_m2 >= 0 else None
        fields.append(FieldModel(
            id=attr(pfd, "A"),
            name=attr(pfd, "C") or attr(pfd, "B") or attr(pfd, "A") or "Campo senza nome",
            area_ha=area_ha,
            crop=crops.get(attr(pfd, "G"), ""),
            rings=rings,
        ))
    field_by_id = {f.id: f for f in fields}

    devices = []
    for dvc in pkg.all("DVC"):
        devices.append({
            "id": attr(dvc, "A"),
            "name": attr(dvc, "B") or attr(dvc, "A") or "Dispositivo",
            "software": attr(dvc, "C"),
            "serial": attr(dvc, "E"),
            "elements": len(descendants(dvc, "DET")),
        })

    warnings: list[dict[str, str]] = []
    tasks: list[TaskModel] = []
    for tsk in pkg.all("TSK"):
        task = _build_task(pkg, tsk, len(tasks), vpns, field_by_id, product_name, warnings)
        tasks.append(task)

    # campi senza confine ma con griglia georeferenziata: usa il rettangolo della griglia
    for task in tasks:
        fld = field_by_id.get(task.field_id)
        if task.grid and task.grid.geo and fld is not None and not fld.rings:
            g = task.grid
            fld.rings = [[(g.min_lon, g.min_lat), (g.min_lon + g.cols * g.dlon, g.min_lat),
                          (g.min_lon + g.cols * g.dlon, g.min_lat + g.rows * g.dlat), (g.min_lon, g.min_lat + g.rows * g.dlat)]]
            fld.boundary_from_grid = True
            warnings.append({"level": "warn", "title": "Confine del campo assente",
                             "detail": f"Il campo «{fld.name}» non ha un contorno nel file: uso il rettangolo della griglia."})

    attrs = root.attrib
    meta = {
        "root": local(root.tag),
        "version": f"{attrs.get('VersionMajor', '?')}.{attrs.get('VersionMinor', '?')}",
        "manufacturer": attrs.get("ManagementSoftwareManufacturer", ""),
        "software_version": attrs.get("ManagementSoftwareVersion", ""),
        "origin": attrs.get("DataTransferOrigin", ""),
        "docs": [d.path for d in pkg.docs],
        "package_files": len(pkg.files),
    }
    if not tasks:
        warnings.append({"level": "bad", "title": "Nessuna operazione", "detail": "Il file non contiene elementi TSK."})
    if not any(t.classes for t in tasks):
        warnings.append({"level": "warn", "title": "Nessun rateo L/ha leggibile",
                         "detail": "Non trovo ratei di volume per area (DDI 0001 o VPN in L/ha) nelle zone o nelle griglie."})
    return Rx(pkg=pkg, fields=fields, tasks=tasks, products=products, devices=devices, warnings=warnings, meta=meta)


def _build_task(pkg: Package, tsk: ET.Element, index: int, vpns: dict[str, dict[str, Any]],
                field_by_id: dict[str, FieldModel], product_name: dict[str, str],
                warnings: list[dict[str, str]]) -> TaskModel:
    task_name = attr(tsk, "B") or attr(tsk, "A") or f"Operazione {index + 1}"
    field_id = attr(tsk, "E")
    fld = field_by_id.get(field_id)
    products = []
    for pan in children(tsk, "PAN"):
        n = product_name.get(attr(pan, "A"))
        if n and n not in products:
            products.append(n)

    zones: list[dict[str, Any]] = []
    extra_vars = 0
    for tzn in children(tsk, "TZN"):
        pdv_list = children(tzn, "PDV")
        convs = [(p, rate_conv_for(p, vpns)) for p in pdv_list]
        rate_pdvs = [(p, c) for p, c in convs if c is not None]
        extra_vars = max(extra_vars, max(0, len(rate_pdvs) - 1))
        polys = []
        for pln in children(tzn, "PLN"):
            rings = polygon_rings(pln)
            if rings:
                polys.append(rings)
        zones.append({"el": tzn, "code": attr(tzn, "A"), "name": attr(tzn, "B"),
                      "pdv": rate_pdvs[0][0] if rate_pdvs else None,
                      "conv": rate_pdvs[0][1] if rate_pdvs else None,
                      "all_pdvs": pdv_list, "polys": polys})

    grd = next(iter(children(tsk, "GRD")), None)
    task = TaskModel(index=index, id=attr(tsk, "A"), name=task_name, field_id=field_id,
                     field_name=fld.name if fld else "Campo non collegato", element=tsk,
                     products=products, kind="none", classes=[], extra_rate_vars=extra_vars)
    if extra_vars:
        task.notes.append("Sono presenti più variabili di rateo per zona (ad es. un secondo prodotto): "
                          "viene valutata e specializzata solo la prima, le altre restano invariate.")

    lat0 = _field_lat0(fld) if fld else 45.0

    if grd is not None:
        _build_grid_task(pkg, task, grd, zones, fld, lat0)
    elif zones and any(z["pdv"] is not None for z in zones):
        _build_zone_task(task, zones, fld, lat0)
    return task


def _field_lat0(fld: FieldModel) -> float:
    pts = [p for ring in fld.rings for p in ring]
    return sum(p[1] for p in pts) / len(pts) if pts else 45.0


def _zone_label(z: dict[str, Any]) -> str:
    return z["name"] or (f"Zona {z['code']}" if z["code"] != "" else "Zona")


def _build_zone_task(task: TaskModel, zones: list[dict[str, Any]], fld: Optional[FieldModel], lat0: float) -> None:
    usable = [z for z in zones if z["pdv"] is not None]
    has_geo = all(z["polys"] for z in usable)
    task.kind = "zones_geo" if has_geo else "zones_nogeo"
    for i, z in enumerate(usable):
        raw = num(attr(z["pdv"], "B"))
        rate = z["conv"].to_lha(raw) if raw is not None else None
        area = None
        if has_geo:
            area = sum(rings_area_ha(r, lat0) for r in z["polys"])
            for rings in z["polys"]:
                task.polygons.append({"class": i, "rings": [[list(p) for p in ring] for ring in rings]})
        elif len(usable) == 1 and fld and fld.area_ha is not None:
            area = fld.area_ha
        task.classes.append(Klass(idx=i, label=_zone_label(z), zone_code=z["code"], rate=rate, area_ha=area,
                                  pdvs=[z["pdv"]], conv=z["conv"], color=ZONE_COLORS[i % len(ZONE_COLORS)]))
    if not has_geo and len(usable) > 1:
        task.notes.append("Le zone di trattamento non hanno una geometria nel file (né poligoni né griglia): "
                          "i ratei sono noti ma non si può dire dove si applicano. La mappa mostra solo il contorno del campo.")
    # se c'è un campo e più zone con geometria, nessuna correzione necessaria


def _grid_dims(grd: ET.Element) -> tuple[int, int]:
    try:
        cols, rows = int(float(attr(grd, "E"))), int(float(attr(grd, "F")))
    except ValueError as exc:
        raise IsoxmlError("La griglia GRD ha numero di colonne/righe non valido.") from exc
    if cols <= 0 or rows <= 0:
        raise IsoxmlError("La griglia GRD deve avere colonne e righe positive.")
    if cols * rows > MAX_GRID_CELLS:
        raise IsoxmlError(f"La griglia ha {cols * rows:,} celle: oltre il limite di {MAX_GRID_CELLS:,}.".replace(",", "."))
    return cols, rows


def _build_grid_task(pkg: Package, task: TaskModel, grd: ET.Element, zones: list[dict[str, Any]],
                     fld: Optional[FieldModel], lat0: float) -> None:
    cols, rows = _grid_dims(grd)
    gtype = int(num(attr(grd, "I"), 0) or 0)
    fname = attr(grd, "G")
    bin_path = pkg.find_file(fname + ".bin") if fname else None
    if bin_path is None:
        raise IsoxmlError(f"La griglia {fname or '(senza nome)'} è dichiarata in TASKDATA.XML ma il file .bin non è nel pacchetto.")
    data = pkg.files[bin_path]

    min_lat, min_lon = num(attr(grd, "A")), num(attr(grd, "B"))
    dlat, dlon = num(attr(grd, "C")), num(attr(grd, "D"))
    geo = None not in (min_lat, min_lon, dlat, dlon) and (dlat or 0) > 0 and (dlon or 0) > 0
    if not geo:
        # Posizionamento di ripiego: il riquadro del campo
        pts = [p for ring in (fld.rings if fld else []) for p in ring]
        if pts:
            lons, lats = [p[0] for p in pts], [p[1] for p in pts]
            min_lat, min_lon = min(lats), min(lons)
            dlat, dlon = (max(lats) - min_lat) / rows, (max(lons) - min_lon) / cols
            task.notes.append("La griglia non ha coordinate (attributi A–D): è stata adattata al riquadro del campo, solo per la visualizzazione.")
        else:
            min_lat, min_lon, dlat, dlon = 0.0, 0.0, 0.0001, 0.0001
            task.notes.append("La griglia non ha coordinate né esiste un contorno del campo: la posizione sulla mappa è puramente indicativa.")
    assert min_lat is not None and min_lon is not None and dlat is not None and dlon is not None
    cell_area_ha = (dlat * M_PER_DEG) * (dlon * M_PER_DEG * math.cos(math.radians(min_lat + rows * dlat / 2))) / 10_000.0
    n = cols * rows
    cell_class = array.array("H", [OUTSIDE]) * n

    grid = GridModel(cols=cols, rows=rows, min_lat=min_lat, min_lon=min_lon, dlat=dlat, dlon=dlon, geo=bool(geo),
                     gtype=gtype, path=bin_path, element=grd, cell_class=cell_class, cell_area_ha=cell_area_ha)
    task.grid = grid

    mask = _grid_mask(grid, fld.rings if fld else [])

    if gtype == 1:
        if len(data) != n:
            raise IsoxmlError(f"Griglia {fname}: attesi {n} byte (uno per cella), trovati {len(data)}.")
        by_code = {z["code"]: z for z in zones}
        counts: dict[int, int] = {}
        for i in range(n):
            if mask[i]:
                c = data[i]
                counts[c] = counts.get(c, 0) + 1
        # ordina per codice e crea le classi anche per zone senza celle
        codes = sorted(set(counts) | {int(z["code"]) for z in zones if z["code"].isdigit() and z["pdv"] is not None})
        idx_of: dict[int, int] = {}
        for c in codes:
            z = by_code.get(str(c))
            rate = None
            conv = None
            pdvs: list[ET.Element] = []
            if z is not None and z["pdv"] is not None:
                raw = num(attr(z["pdv"], "B"))
                conv = z["conv"]
                rate = conv.to_lha(raw) if raw is not None else None
                pdvs = [z["pdv"]]
            label = _zone_label(z) if z is not None else f"Codice {c} (senza zona)"
            k = Klass(idx=len(task.classes), label=label, zone_code=str(c), rate=rate,
                      area_ha=counts.get(c, 0) * cell_area_ha, cells=counts.get(c, 0), pdvs=pdvs, conv=conv,
                      color=ZONE_COLORS[len(task.classes) % len(ZONE_COLORS)])
            idx_of[c] = k.idx
            task.classes.append(k)
        for i in range(n):
            if mask[i]:
                cell_class[i] = idx_of[data[i]]
        task.kind = "grid1"
        return

    if gtype == 2:
        template_code = attr(grd, "J")
        template = next((z for z in zones if z["code"] == template_code), None)
        if template is None:
            raise IsoxmlError(f"Griglia {fname}: la zona modello (GRD.J = {template_code!r}) non esiste tra le TZN del task.")
        pdvs = template["all_pdvs"]
        if not pdvs:
            raise IsoxmlError(f"Griglia {fname}: la zona modello non contiene variabili PDV.")
        expected = n * len(pdvs) * 4
        if len(data) != expected:
            raise IsoxmlError(f"Griglia {fname}: attesi {expected} byte ({n} celle × {len(pdvs)} variabili × 4), trovati {len(data)}.")
        vpns = vpn_table(pkg)
        convs = [rate_conv_for(p, vpns) for p in pdvs]
        primary = next((i for i, c in enumerate(convs) if c is not None), None)
        if primary is None:
            raise IsoxmlError(f"Griglia {fname}: nessuna variabile della zona modello è un rateo in L/ha.")
        conv = convs[primary]
        assert conv is not None
        grid.template_pdvs = pdvs
        grid.primary_var = primary
        raws = array.array("i", [0]) * n
        stride = len(pdvs)
        fmt = "<" + "i" * (n * stride)
        all_vals = struct.unpack(fmt, data) if n * stride <= 8_000_000 else None
        for i in range(n):
            raws[i] = all_vals[i * stride + primary] if all_vals is not None else struct.unpack_from("<i", data, (i * stride + primary) * 4)[0]
        grid.raw_by_cell = raws
        distinct = sorted({raws[i] for i in range(n) if mask[i]})
        binned = len(distinct) > MAX_DISTINCT_RATES
        class_of_raw: dict[int, int] = {}
        key_to_class: dict[float, int] = {}
        area_by_class: dict[int, int] = {}
        for raw in distinct:
            rate = conv.to_lha(raw)
            key = round(round(rate / 0.5) * 0.5, 2) if binned else round(rate, 3)
            if key not in key_to_class:
                k = Klass(idx=len(task.classes), label=f"{_fmt_rate(rate if not binned else key)} L/ha", zone_code=None,
                          rate=rate if not binned else key, area_ha=0.0, conv=conv, color="")
                key_to_class[key] = k.idx
                task.classes.append(k)
            class_of_raw[raw] = key_to_class[key]
            task.classes[key_to_class[key]].raws.append(raw)
        for i in range(n):
            if mask[i]:
                ci = class_of_raw[raws[i]]
                cell_class[i] = ci
                area_by_class[ci] = area_by_class.get(ci, 0) + 1
        for ci, cnt in area_by_class.items():
            task.classes[ci].cells = cnt
            task.classes[ci].area_ha = cnt * cell_area_ha
        # ordina le classi per rateo crescente (comodo per tabelle e legenda) e rimappa le celle
        order = sorted(range(len(task.classes)), key=lambda c: task.classes[c].rate or 0)
        remap = {old: new for new, old in enumerate(order)}
        task.classes = [task.classes[o] for o in order]
        for new, k in enumerate(task.classes):
            k.idx = new
        for i in range(n):
            if cell_class[i] != OUTSIDE:
                cell_class[i] = remap[cell_class[i]]
        task.kind = "grid2"
        return

    raise IsoxmlError(f"Griglia {fname}: tipo GRD.I = {attr(grd, 'I')!r} non riconosciuto (attesi 1 o 2).")


def _fmt_rate(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _grid_mask(grid: GridModel, rings: list[list[tuple[float, float]]]) -> list[bool]:
    n = grid.cols * grid.rows
    if not rings:
        return [True] * n
    mask = [False] * n
    for r in range(grid.rows):
        y = grid.min_lat + (r + 0.5) * grid.dlat
        for x0, x1 in row_intervals(rings, y):
            c0 = max(0, int(math.ceil((x0 - grid.min_lon) / grid.dlon - 0.5)))
            c1 = min(grid.cols - 1, int(math.floor((x1 - grid.min_lon) / grid.dlon - 0.5)))
            base = r * grid.cols
            for c in range(c0, c1 + 1):
                mask[base + c] = True
    return mask


# --------------------------------------------------------------------------- scrittura

def apply_rates(rx: Rx, task: TaskModel, new_rate: dict[int, float]) -> dict[str, int]:
    """Riscrive nel pacchetto (in memoria) i ratei delle classi indicate. Restituisce i conteggi."""
    values = 0
    cells = 0
    changed_classes = {i for i, r in new_rate.items() if task.classes[i].rate is not None and abs(r - task.classes[i].rate) > 1e-9}  # type: ignore[operator]
    if not changed_classes:
        return {"values": 0, "cells": 0, "zones": 0}

    if task.kind in ("grid1", "zones_geo", "zones_nogeo"):
        for i in changed_classes:
            k = task.classes[i]
            assert k.conv is not None
            raw = k.conv.to_raw(new_rate[i])
            for pdv in k.pdvs:
                if str(raw) != attr(pdv, "B"):
                    pdv.set("B", str(raw))
                    values += 1
        cells = sum(task.classes[i].cells for i in changed_classes)
        return {"values": values, "cells": cells, "zones": len(changed_classes)}

    if task.kind == "grid2" and task.grid is not None and task.grid.raw_by_cell is not None:
        g = task.grid
        conv = next(k.conv for k in task.classes if k.conv is not None)
        data = bytearray(rx.pkg.files[g.path])
        stride = len(g.template_pdvs)
        new_raw_of_class = {i: conv.to_raw(new_rate[i]) for i in changed_classes}
        for ci in range(g.cols * g.rows):
            cls = g.cell_class[ci]
            if cls != OUTSIDE and cls in new_raw_of_class:
                nr = new_raw_of_class[cls]
                off = (ci * stride + g.primary_var) * 4
                if struct.unpack_from("<i", data, off)[0] != nr:
                    struct.pack_into("<i", data, off, nr)
                    cells += 1
                    values += 1
        rx.pkg.files[g.path] = bytes(data)
        return {"values": values, "cells": cells, "zones": len(changed_classes)}
    return {"values": 0, "cells": 0, "zones": 0}


def verify_task(old: TaskModel, new: TaskModel, mapping: dict[int, float], tol: float = 0.02) -> list[str]:
    """Confronta il task riletto dal file prodotto con quello originale: solo le classi in `mapping` devono essere cambiate."""
    errs: list[str] = []
    if new.kind != old.kind:
        return [f"il tipo di prescrizione è cambiato ({old.kind} → {new.kind})"]
    if old.kind == "grid2" and old.grid is not None and new.grid is not None:
        conv = next((k.conv for k in old.classes if k.conv is not None), None)
        if conv is None or old.grid.raw_by_cell is None or new.grid.raw_by_cell is None:
            return ["impossibile verificare la griglia"]
        new_raw = {i: conv.to_raw(r) for i, r in mapping.items()}
        bad = 0
        for ci in range(old.grid.cols * old.grid.rows):
            cls = old.grid.cell_class[ci]
            if cls == OUTSIDE:
                continue
            expected = new_raw.get(cls, old.grid.raw_by_cell[ci])
            if new.grid.raw_by_cell[ci] != expected:
                bad += 1
        if bad:
            errs.append(f"{bad} celle della griglia non corrispondono ai ratei attesi")
        return errs
    if len(new.classes) != len(old.classes):
        return [f"numero di zone diverso ({len(old.classes)} → {len(new.classes)})"]
    for k_old, k_new in zip(old.classes, new.classes):
        want = mapping.get(k_old.idx, k_old.rate)
        if want is None and k_new.rate is None:
            continue
        if want is None or k_new.rate is None or abs(k_new.rate - want) > tol + 1e-9:
            errs.append(f"zona «{k_old.label}»: atteso {want}, letto {k_new.rate}")
    return errs


def add_note(task: TaskModel, text: str) -> None:
    """Aggiunge (o aggiorna) un unico commento libero CAN al task, max 32 caratteri."""
    text = text[:32]
    for can in children(task.element, "CAN"):
        if attr(can, "C").startswith("UM "):
            can.set("C", text)
            return
    ns = task.element.tag.split("}")[0] + "}" if task.element.tag.startswith("{") else ""
    can = ET.Element(ns + "CAN", {"C": text})
    # posizione: dopo gli ultimi PAN/DAN/CNN/WAN se presenti, altrimenti all'inizio
    pos = 0
    for i, el in enumerate(list(task.element)):
        if local(el.tag) in ("PAN", "DAN", "CNN", "WAN", "OTP", "TIM", "DLT"):
            pos = i + 1
    task.element.insert(pos, can)


def serialize(rx: Rx) -> dict[str, bytes]:
    out = dict(rx.pkg.files)
    for d in rx.pkg.docs:
        body = ET.tostring(d.root, encoding="unicode")
        out[d.path] = ('<?xml version="1.0" encoding="UTF-8"?>\n' + body).encode("utf-8")
    return out


def build_zip(files: dict[str, bytes], executable: Optional[set[str]] = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if executable and path in executable else 0o644) << 16
            zf.writestr(info, content)
    return buf.getvalue()


# --------------------------------------------------------------------------- vista per il browser

def _b64(arr: array.array) -> str:
    a = arr
    if sys.byteorder != "little":
        a = array.array(arr.typecode, arr)
        a.byteswap()
    return base64.b64encode(a.tobytes()).decode("ascii")


def public_geometry(rx: Rx) -> dict[str, Any]:
    fields = [{"id": f.id, "name": f.name, "rings": [[list(p) for p in ring] for ring in f.rings],
               "from_grid": f.boundary_from_grid} for f in rx.fields]
    tasks = []
    for t in rx.tasks:
        item: dict[str, Any] = {"index": t.index, "kind": t.kind, "polygons": t.polygons, "grid": None}
        if t.grid is not None:
            g = t.grid
            stride = 1
            if g.cols * g.rows > DISPLAY_MAX_CELLS:
                stride = int(math.ceil(math.sqrt(g.cols * g.rows / DISPLAY_MAX_CELLS)))
            cols, rows = (g.cols + stride - 1) // stride, (g.rows + stride - 1) // stride
            if stride == 1:
                cells = g.cell_class
            else:
                cells = array.array("H", [OUTSIDE]) * (cols * rows)
                for r in range(rows):
                    for c in range(cols):
                        cells[r * cols + c] = g.cell_class[(r * stride) * g.cols + c * stride]
            item["grid"] = {"cols": cols, "rows": rows, "min_lat": g.min_lat, "min_lon": g.min_lon,
                            "dlat": g.dlat * stride, "dlon": g.dlon * stride, "geo": g.geo,
                            "type": g.gtype, "cells": _b64(cells), "decimated": stride > 1}
        tasks.append(item)
    return {"fields": fields, "tasks": tasks}


def public_summary(rx: Rx) -> dict[str, Any]:
    tasks = []
    for t in rx.tasks:
        treated = [k for k in t.classes if k.rate and k.rate > 0]
        areas = [k.area_ha for k in treated]
        total_area = sum(k.area_ha for k in t.classes) if all(k.area_ha is not None for k in t.classes) and t.classes else None
        if treated and all(a is not None for a in areas) and sum(areas) > 0:  # type: ignore[arg-type]
            mean = sum(k.rate * k.area_ha for k in treated) / sum(areas)  # type: ignore[operator, arg-type]
        else:
            mean = sum(k.rate for k in treated) / len(treated) if treated else None  # type: ignore[misc]
        tasks.append({
            "index": t.index, "id": t.id, "name": t.name, "field_id": t.field_id, "field_name": t.field_name,
            "products": t.products, "kind": t.kind, "notes": t.notes, "extra_rate_vars": t.extra_rate_vars,
            "area_ha": round(total_area, 2) if total_area is not None else None,
            "rate_min": min((k.rate for k in treated), default=None),
            "rate_max": max((k.rate for k in treated), default=None),
            "rate_mean": mean,
            "classes": [{"i": k.idx, "label": k.label, "code": k.zone_code, "rate": k.rate,
                         "area_ha": round(k.area_ha, 3) if k.area_ha is not None else None,
                         "cells": k.cells, "color": k.color} for k in t.classes],
            "grid": ({"cols": t.grid.cols, "rows": t.grid.rows, "type": t.grid.gtype, "geo": t.grid.geo,
                      "cell_m": [round(t.grid.dlat * M_PER_DEG, 1),
                                 round(t.grid.dlon * M_PER_DEG * math.cos(math.radians(t.grid.min_lat)), 1)]}
                     if t.grid else None),
        })
    total_ha = sum(f.area_ha for f in rx.fields if f.area_ha is not None) if any(f.area_ha is not None for f in rx.fields) else None
    return {
        "filename": rx.pkg.filename, "was_zip": rx.pkg.was_zip, **rx.meta,
        "fields": [{"id": f.id, "name": f.name, "area_ha": f.area_ha, "crop": f.crop, "has_boundary": bool(f.rings),
                    "boundary_from_grid": f.boundary_from_grid} for f in rx.fields],
        "total_area_ha": round(total_ha, 2) if total_ha is not None else None,
        "products": rx.products, "devices": rx.devices, "tasks": tasks, "warnings": rx.warnings,
    }
