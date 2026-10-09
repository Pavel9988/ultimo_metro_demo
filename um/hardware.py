"""Catalogo hardware Nordson / ARAG e modello idraulico di ugelli e catena di controllo."""

from __future__ import annotations

import bisect
import json
import math
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "data", "arag_catalog.json")

_lock = threading.Lock()
_catalog_cache: Optional["Catalog"] = None


def num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- catalogo

class Catalog:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.products: dict[str, dict[str, Any]] = {str(p["code"]): p for p in data.get("products", [])}
        self._nozzles: dict[str, "Nozzle"] = {}

    def get(self, code: Any) -> Optional[dict[str, Any]]:
        return self.products.get(str(code)) if code not in (None, "") else None

    def caps(self, code: Any) -> dict[str, Any]:
        p = self.get(code)
        return (p or {}).get("capabilities", {}) or {}

    def nozzle(self, code: Any) -> Optional["Nozzle"]:
        p = self.get(code)
        if not p or p.get("category") != "nozzle":
            return None
        key = str(code)
        if key not in self._nozzles:
            self._nozzles[key] = Nozzle.from_product(p)
        return self._nozzles[key]

    def nozzles(self) -> list["Nozzle"]:
        out = []
        for code, p in self.products.items():
            if p.get("category") == "nozzle":
                n = self.nozzle(code)
                if n:
                    out.append(n)
        return out


def load_catalog(force: bool = False) -> Catalog:
    global _catalog_cache
    with _lock:
        if _catalog_cache is None or force:
            with open(CATALOG_PATH, "r", encoding="utf-8") as fh:
                _catalog_cache = Catalog(json.load(fh))
        return _catalog_cache


# --------------------------------------------------------------------------- ugello

@dataclass
class Nozzle:
    code: str
    name: str
    low_drift: bool
    angle: Optional[float]
    p_min: float
    p_max: float
    ps: list[float]                      # pressioni della curva (crescenti)
    qs: list[float]                      # portate L/min (crescenti)
    estimated: bool                      # True: curva ricavata con √p da un solo punto
    drop_class: dict[float, str] = field(default_factory=dict)
    fines: dict[float, float] = field(default_factory=dict)
    url: str = ""

    @staticmethod
    def from_product(p: dict[str, Any]) -> "Nozzle":
        c = p.get("capabilities", {}) or {}
        p_min = num(c.get("pressure_min_bar"), 1.5) or 1.5
        p_max = num(c.get("pressure_max_bar"), 8.0) or 8.0
        curve = c.get("flow_l_min_by_pressure_bar") or {}
        pts = sorted((float(k), float(v)) for k, v in curve.items())
        estimated = False
        if len(pts) < 2:
            q3 = num(c.get("flow_l_min_at_3_bar"), None)
            if not q3:
                raise ValueError(f"Ugello {p.get('code')} senza dati di portata")
            estimated = True
            grid = sorted({p_min, 2.0, 3.0, 4.0, 5.0, 6.0, p_max})
            pts = [(g, q3 * math.sqrt(g / 3.0)) for g in grid if p_min <= g <= p_max]
        ps = [a for a, _ in pts]
        qs = [b for _, b in pts]
        return Nozzle(
            code=str(p["code"]), name=str(p.get("name", p["code"])), low_drift=bool(c.get("low_drift")),
            angle=num(c.get("spray_angle_deg")), p_min=max(p_min, ps[0]), p_max=min(p_max, ps[-1]),
            ps=ps, qs=qs, estimated=estimated,
            drop_class={float(k): str(v) for k, v in (c.get("drop_class_by_pressure_bar") or {}).items()},
            fines={float(k): float(v) for k, v in (c.get("percent_under_136um_by_pressure_bar") or {}).items()},
            url=str(p.get("official_url", "")),
        )

    def flow(self, pressure: float) -> float:
        """Portata per ugello (L/min) alla pressione data, per interpolazione lineare della curva."""
        ps, qs = self.ps, self.qs
        if pressure <= ps[0]:
            return qs[0]
        if pressure >= ps[-1]:
            return qs[-1]
        i = bisect.bisect_right(ps, pressure)
        p0, p1, q0, q1 = ps[i - 1], ps[i], qs[i - 1], qs[i]
        return q0 + (q1 - q0) * (pressure - p0) / (p1 - p0)

    def pressure_for_flow(self, q: float) -> float:
        """Pressione che produce la portata q (inverso della curva, monotona crescente)."""
        ps, qs = self.ps, self.qs
        if q <= qs[0]:
            return ps[0]
        if q >= qs[-1]:
            return ps[-1]
        i = bisect.bisect_right(qs, q)
        p0, p1, q0, q1 = ps[i - 1], ps[i], qs[i - 1], qs[i]
        return p0 + (p1 - p0) * (q - q0) / (q1 - q0)

    def droplets(self, pressure: float) -> tuple[Optional[str], Optional[float]]:
        """Classe di gocce e % di gocce < 136 µm dalla tabella (valore al punto di tabella più vicino)."""
        if not self.drop_class and not self.fines:
            return None, None
        keys = sorted(set(self.drop_class) | set(self.fines), key=lambda k: abs(k - pressure))
        k = keys[0]
        return self.drop_class.get(k), self.fines.get(k)

    @property
    def has_droplet_data(self) -> bool:
        return bool(self.fines)


# --------------------------------------------------------------------------- configurazione

@dataclass
class HwConfig:
    terminal: str = ""
    rate_control: str = ""
    ecu: str = ""
    actuator: str = ""
    flowmeter: str = ""
    valve: str = ""
    pump: str = ""
    nozzles: list[str] = field(default_factory=list)
    pressure_set: float = 3.0
    pressure_min: Optional[float] = None
    pressure_max: Optional[float] = None
    boom_width: float = 24.0
    spacing: float = 0.5
    nozzle_count: Optional[int] = None
    speed_nom: float = 8.0
    speed_min: float = 6.0
    speed_max: float = 10.0
    tolerance_pct: float = 5.0
    duty_min_pct: float = 20.0
    spray_height: float = 0.5
    allow_speed_adapt: bool = True
    strategy: str = "auto"               # auto | variable | uniform
    uniform_rate: Optional[float] = None

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "HwConfig":
        d = d or {}
        nozzles = [str(c) for c in (d.get("nozzles") or []) if str(c).strip()]
        cfg = HwConfig(
            terminal=str(d.get("terminal", "") or ""), rate_control=str(d.get("rate_control", "") or ""),
            ecu=str(d.get("ecu", "") or ""), actuator=str(d.get("actuator", "") or ""),
            flowmeter=str(d.get("flowmeter", "") or ""), valve=str(d.get("valve", "") or ""),
            pump=str(d.get("pump", "") or ""), nozzles=nozzles,
            pressure_set=num(d.get("pressure_set"), 3.0) or 3.0,
            pressure_min=num(d.get("pressure_min")), pressure_max=num(d.get("pressure_max")),
            boom_width=num(d.get("boom_width"), 24.0) or 24.0, spacing=num(d.get("spacing"), 0.5) or 0.5,
            nozzle_count=int(num(d.get("nozzle_count"))) if num(d.get("nozzle_count")) else None,
            speed_nom=num(d.get("speed_nom"), 8.0) or 8.0, speed_min=num(d.get("speed_min"), 6.0) or 6.0,
            speed_max=num(d.get("speed_max"), 10.0) or 10.0,
            tolerance_pct=num(d.get("tolerance_pct"), 5.0) if num(d.get("tolerance_pct"), 5.0) is not None else 5.0,
            duty_min_pct=num(d.get("duty_min_pct"), 20.0) or 20.0,
            spray_height=num(d.get("spray_height"), 0.5) or 0.5,
            allow_speed_adapt=bool(d.get("allow_speed_adapt", True)),
            strategy=str(d.get("strategy", "auto") or "auto"), uniform_rate=num(d.get("uniform_rate")),
        )
        return cfg

    def problems(self) -> list[str]:
        out = []
        if not (self.boom_width > 0 and self.spacing > 0):
            out.append("Larghezza barra e interasse devono essere positivi.")
        if not (0 < self.speed_min <= self.speed_nom <= self.speed_max):
            out.append("Le velocità devono rispettare: minima ≤ di lavoro ≤ massima.")
        if not (1 <= self.duty_min_pct <= 100):
            out.append("Il duty minimo PWM deve essere fra 1 e 100 %.")
        if not (0 <= self.tolerance_pct <= 50):
            out.append("La tolleranza deve essere fra 0 e 50 %.")
        if self.strategy not in ("auto", "variable", "uniform"):
            out.append("Strategia non riconosciuta.")
        return out

    @property
    def n_nozzles(self) -> int:
        return self.nozzle_count if self.nozzle_count and self.nozzle_count > 0 else max(1, round(self.boom_width / self.spacing))


# --------------------------------------------------------------------------- catena di controllo

@dataclass
class Chain:
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    task_controller: bool = False
    vra: bool = False
    pwm: bool = False
    individual_nozzle: bool = False
    ways: int = 1
    nozzles: list[Nozzle] = field(default_factory=list)
    p_lo: float = 1.0
    p_hi: float = 8.0
    meter_range: Optional[tuple[float, float]] = None
    pump_flow: Optional[float] = None
    names: dict[str, str] = field(default_factory=dict)

    def window(self, nozzle: Nozzle) -> tuple[float, float]:
        return max(self.p_lo, nozzle.p_min), min(self.p_hi, nozzle.p_max)


def _ways(product: Optional[dict[str, Any]]) -> int:
    if not product:
        return 1
    c = product.get("capabilities", {}) or {}
    if c.get("ways"):
        return int(c["ways"])
    text = (str(product.get("name", "")) + " " + str(product.get("short", ""))).lower()
    for word, n in (("quadruplo", 4), ("triplo", 3), ("doppio", 2)):
        if word in text:
            return n
    return 1


def resolve_chain(cfg: HwConfig, cat: Catalog) -> Chain:
    ch = Chain()
    term, rc, ecu, act = cat.get(cfg.terminal), cat.get(cfg.rate_control), cat.get(cfg.ecu), cat.get(cfg.actuator)
    for label, p in (("Terminale", term), ("Controllo rateo", rc), ("Centralina", ecu), ("Attuatore", act),
                     ("Flussimetro", cat.get(cfg.flowmeter)), ("Valvola", cat.get(cfg.valve)), ("Pompa", cat.get(cfg.pump))):
        if p:
            ch.names[label] = f"{p['code']} · {p['name']}"

    tcaps, rcaps, acaps = (term or {}).get("capabilities", {}) or {}, (rc or {}).get("capabilities", {}) or {}, (act or {}).get("capabilities", {}) or {}
    # terminale
    if not term:
        ch.blockers.append("Seleziona il terminale/computer di bordo: senza Task Controller il file ISOXML non può essere eseguito.")
    elif not tcaps.get("task_controller"):
        ch.blockers.append(f"Il terminale {term['name']} ({term['code']}) non risulta dotato di Task Controller nel catalogo: non importa prescrizioni ISOXML.")
    else:
        ch.task_controller = True
    # famiglia IBX
    has_ibx_unit = bool(rc) or bool(ecu)
    if term and tcaps.get("ibx_only") and not has_ibx_unit:
        ch.blockers.append("I terminali Delta IBX funzionano solo con centraline ARAG IBX: aggiungi IBX100 Flowtron o IBX50.")
    if rc and rcaps.get("pwm") and term and not tcaps.get("ibx_only"):
        ch.warnings.append("Flowtron IBX100 è una centralina IBX: il catalogo la associa ai terminali Delta IBX. Verifica con ARAG la combinazione scelta.")

    # PWM
    pwm_actuator = bool(act) and bool(acaps.get("pwm_valve") or acaps.get("selective_nozzle_control"))
    ch.pwm = bool(rc and rcaps.get("pwm") and pwm_actuator)
    if rc and rcaps.get("pwm") and not pwm_actuator:
        ch.warnings.append("Flowtron selezionato ma senza portaugello/valvola per ugello (SELETRON o FCV): il PWM per ugello non è possibile, uso la regolazione a pressione.")
    ch.individual_nozzle = bool((rc and rcaps.get("nozzle_by_nozzle")) or acaps.get("selective_nozzle_control"))
    ch.ways = _ways(act) if act else 1

    # regolazione di portata (rateo variabile)
    regulation = bool(rc) or bool(cat.get(cfg.valve) and cat.get(cfg.flowmeter))
    ch.vra = ch.task_controller and regulation and not ch.blockers
    if ch.task_controller and not regulation:
        ch.warnings.append("Nessuna regolazione di portata dimostrata (serve Flowtron oppure valvola + flussimetro): il rateo variabile non è garantito.")

    # ugelli installati
    nozzles = []
    for code in cfg.nozzles:
        n = cat.nozzle(code)
        if n is not None:
            nozzles.append(n)
    if len(nozzles) > ch.ways:
        ch.warnings.append(f"Hai scelto {len(nozzles)} ugelli ma il portaugello selezionato ha {ch.ways} vie: considero solo i primi {ch.ways}.")
        nozzles = nozzles[:ch.ways]
    if not nozzles:
        ch.blockers.append("Seleziona almeno un ugello del catalogo.")
    ch.nozzles = nozzles
    if len(nozzles) > 1 and not (act and acaps.get("selective_nozzle_control")):
        ch.warnings.append("Più ugelli selezionati senza un selettore SELETRON: la commutazione elettrica fra ugelli non è dimostrata, considero solo il primo.")
        ch.nozzles = nozzles[:1]
    if any(n.estimated for n in ch.nozzles):
        ch.warnings.append("Per almeno un ugello la portata è stimata con la legge √pressione da un solo punto del catalogo: verifica la scheda tecnica.")

    # finestra di pressione di sistema
    caps_max = []
    for p in (act, cat.get(cfg.pump), cat.get(cfg.valve)):
        v = num(((p or {}).get("capabilities", {}) or {}).get("max_pressure_bar"))
        if v:
            caps_max.append(v)
    ch.p_hi = cfg.pressure_max if cfg.pressure_max else (min(caps_max) if caps_max else 8.0)
    ch.p_lo = cfg.pressure_min if cfg.pressure_min else 1.0
    if ch.p_lo >= ch.p_hi:
        ch.blockers.append("La finestra di pressione è vuota (minima ≥ massima).")

    fm = cat.caps(cfg.flowmeter)
    if fm.get("range_min_l_min") is not None and fm.get("range_max_l_min") is not None:
        ch.meter_range = (float(fm["range_min_l_min"]), float(fm["range_max_l_min"]))
    ch.pump_flow = num(cat.caps(cfg.pump).get("nominal_flow_l_min"))
    return ch
