"""Motore di valutazione e specializzazione.

Idea di fondo, volutamente semplice e verificabile a mano:

* per ogni classe di rateo R (L/ha) la portata richiesta per ugello è  q = R · v · s / 600
  (v in km/h, s = interasse in m, q in L/min);
* ogni ugello del catalogo ha una curva portata/pressione Q(p): la pressione che serve è l'inverso di Q;
* senza PWM la portata si regola solo con la pressione (finestra stretta: Q varia come √p);
  con PWM Flowtron la pressione resta quella di riferimento e si varia il duty (finestra molto più larga);
* con un portaugello SELETRON si può commutare fra più ugelli montati sullo stesso corpo;
* la velocità può essere adattata dentro il campo [min, max] scelto dall'operatore.

Per ogni classe si cerca, in quest'ordine, la soluzione che disturba meno l'operatore:
ugello principale a velocità di lavoro -> altro ugello -> altra velocità -> altro ugello e altra velocità.
Se nessuna soluzione raggiunge il rateo, si registra il rateo migliore ottenibile (sotto- o sovradosaggio).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .hardware import Catalog, Chain, HwConfig, Nozzle

STATUS_RANK = {"ok": 0, "adapt": 1, "under": 2, "over": 2, "novra": 3, "nodata": 4, "off": 0}


# --------------------------------------------------------------------------- calcolo base

@dataclass
class Reach:
    ok: bool
    p: float = 0.0
    duty: float = 1.0
    q: float = 0.0                       # portata per ugello (L/min)


def q_required(rate: float, v: float, spacing: float) -> float:
    return rate * v * spacing / 600.0


def rate_from_q(q: float, v: float, spacing: float) -> float:
    return q * 600.0 / (v * spacing)


def flow_limits(n: Nozzle, cfg: HwConfig, chain: Chain) -> Optional[tuple[float, float]]:
    """Portata minima e massima per ugello (L/min) ottenibile con la catena selezionata."""
    plo, phi = chain.window(n)
    if plo >= phi - 1e-9:
        return None
    qhi = n.flow(phi)
    if chain.pwm:
        return cfg.duty_min_pct / 100.0 * n.flow(plo), qhi
    return n.flow(plo), qhi


def reach(n: Nozzle, rate: float, v: float, cfg: HwConfig, chain: Chain) -> Reach:
    lim = flow_limits(n, cfg, chain)
    if lim is None:
        return Reach(False)
    qmin, qmax = lim
    q = q_required(rate, v, cfg.spacing)
    eps = 1e-9
    if q < qmin - eps or q > qmax + eps:
        return Reach(False, q=min(max(q, qmin), qmax))
    plo, phi = chain.window(n)
    if not chain.pwm:
        return Reach(True, p=n.pressure_for_flow(q), duty=1.0, q=q)
    pset = min(max(cfg.pressure_set, plo), phi)
    qset = n.flow(pset)
    dmin = cfg.duty_min_pct / 100.0
    if q > qset + eps:
        return Reach(True, p=n.pressure_for_flow(q), duty=1.0, q=q)
    d = q / qset
    if d >= dmin - eps:
        return Reach(True, p=pset, duty=min(d, 1.0), q=q)
    # duty troppo basso alla pressione di riferimento: abbasso la pressione finché il duty arriva al minimo
    p = max(plo, n.pressure_for_flow(q / dmin))
    return Reach(True, p=p, duty=min(q / n.flow(p), 1.0), q=q)


def speed_candidates(cfg: HwConfig) -> list[float]:
    if not cfg.allow_speed_adapt:
        return [cfg.speed_nom]
    vals = {round(cfg.speed_nom, 3), round(cfg.speed_min, 3), round(cfg.speed_max, 3)}
    k = 0
    v = cfg.speed_min
    while v <= cfg.speed_max + 1e-9 and k < 200:
        vals.add(round(v, 3))
        v += 0.5
        k += 1
    return sorted(vals, key=lambda x: (abs(x - cfg.speed_nom), x))


# --------------------------------------------------------------------------- piano per classe

@dataclass
class Plan:
    rate: Optional[float]
    status: str
    delivered: Optional[float] = None
    dev_pct: Optional[float] = None
    nozzle: str = ""
    nozzle_index: int = 0
    speed: Optional[float] = None
    pressure: Optional[float] = None
    duty: Optional[float] = None
    q_nozzle: Optional[float] = None
    q_total: Optional[float] = None
    fines: Optional[float] = None
    drop_class: Optional[str] = None
    flags: list[str] = field(default_factory=list)
    explain: str = ""
    hint: str = ""

    def to_json(self) -> dict[str, Any]:
        r = lambda x, d=2: None if x is None else round(x, d)
        return {"rate": r(self.rate), "status": self.status, "delivered": r(self.delivered), "dev_pct": r(self.dev_pct, 1),
                "nozzle": self.nozzle, "speed": r(self.speed, 1), "pressure": r(self.pressure, 2),
                "duty": r(self.duty * 100 if self.duty is not None else None, 0), "q_nozzle": r(self.q_nozzle, 3),
                "q_total": r(self.q_total, 1), "fines": r(self.fines, 0), "drop_class": self.drop_class,
                "flags": self.flags, "explain": self.explain, "hint": self.hint}


def _fmt(v: Optional[float], d: int = 1) -> str:
    return "—" if v is None else f"{v:.{d}f}".replace(".", ",")


def plan_rate(rate: Optional[float], cfg: HwConfig, chain: Chain, cat: Optional[Catalog] = None, *, with_hint: bool = True) -> Plan:
    if rate is None:
        return Plan(rate=None, status="nodata", explain="Rateo non leggibile nel file.")
    if rate <= 0:
        return Plan(rate=0.0, status="off", delivered=0.0, dev_pct=0.0, explain="Nessun trattamento prescritto.")
    nozzles = chain.nozzles
    if not nozzles:
        return Plan(rate=rate, status="nodata", explain="Nessun ugello valido selezionato.")
    s, N = cfg.spacing, cfg.n_nozzles
    speeds = speed_candidates(cfg)
    nom = cfg.speed_nom
    tol = cfg.tolerance_pct / 100.0

    # 1) soluzioni che raggiungono esattamente il rateo, a livelli di "disturbo" crescenti
    tiers: dict[int, list[tuple[float, float, int, float, Reach, Nozzle]]] = {0: [], 1: [], 2: [], 3: []}
    for ni, n in enumerate(nozzles):
        for v in speeds:
            r = reach(n, rate, v, cfg, chain)
            if not r.ok:
                continue
            at_nom = abs(v - nom) < 1e-9
            tier = (0 if ni == 0 else 1) if at_nom else (2 if ni == 0 else 3)
            _, fines = n.droplets(r.p)
            tiers[tier].append((abs(v - nom), fines if fines is not None else 999.0, ni, v, r, n))
    chosen = None
    chosen_tier = -1
    for t in (0, 1, 2, 3):
        if tiers[t]:
            chosen = sorted(tiers[t], key=lambda x: (x[0], x[1], x[2]))[0]
            chosen_tier = t
            break

    if chosen is not None:
        _, _, ni, v, r, n = chosen
        status = "ok" if chosen_tier == 0 else "adapt"
        plan = _fill(rate, rate, status, n, ni, v, r, cfg, chain)
        if chosen_tier in (1, 3):
            plan.flags.append("switch")
        if chosen_tier in (2, 3):
            plan.flags.append("speed")
        plan.explain = _explain_ok(plan, n, cfg, chain, chosen_tier)
        return plan

    # 2) nessuna soluzione esatta: miglior rateo ottenibile
    best = None
    for ni, n in enumerate(nozzles):
        lim = flow_limits(n, cfg, chain)
        if lim is None:
            continue
        for v in speeds:
            q = min(max(q_required(rate, v, s), lim[0]), lim[1])
            r_ach = rate_from_q(q, v, s)
            key = (abs(r_ach - rate), abs(v - nom), ni)
            if best is None or key < best[0]:
                best = (key, ni, n, v, r_ach)
    if best is None:
        return Plan(rate=rate, status="nodata", explain="Nessun ugello utilizzabile con la finestra di pressione impostata.")
    _, ni, n, v, r_ach = best
    rr = reach(n, r_ach, v, cfg, chain)
    status = "under" if r_ach < rate else "over"
    within = abs(r_ach - rate) / rate <= tol
    if within:
        status = "adapt"
    plan = _fill(rate, r_ach, status, n, ni, v, rr, cfg, chain)
    plan.flags.append("limit")
    if ni > 0:
        plan.flags.append("switch")
    if abs(v - nom) > 1e-9:
        plan.flags.append("speed")
    plan.explain = _explain_limited(plan, rate, n, cfg, chain)
    if with_hint and cat is not None and not within:
        plan.hint = _hint_nozzle(rate, cfg, chain, cat)
    return plan


def _fill(rate: float, delivered: float, status: str, n: Nozzle, ni: int, v: float, r: Reach,
          cfg: HwConfig, chain: Chain) -> Plan:
    dc, fines = n.droplets(r.p)
    plan = Plan(rate=rate, status=status, delivered=delivered, dev_pct=(delivered - rate) / rate * 100.0,
                nozzle=n.code, nozzle_index=ni, speed=v, pressure=r.p, duty=r.duty, q_nozzle=r.q,
                q_total=r.q * cfg.n_nozzles, fines=fines, drop_class=dc)
    if chain.meter_range is not None:
        lo, hi = chain.meter_range
        if plan.q_total is not None and plan.q_total < lo:
            plan.flags.append("meter_low")
        elif plan.q_total is not None and plan.q_total > hi:
            plan.flags.append("meter_high")
    if chain.pump_flow and plan.q_total and plan.q_total > 0.8 * chain.pump_flow:
        plan.flags.append("pump")
    plo, phi = chain.window(n)
    if phi > plo and (r.p - plo < 0.05 * (phi - plo) or phi - r.p < 0.05 * (phi - plo)) and not chain.pwm:
        plan.flags.append("edge")
    return plan


def _explain_ok(plan: Plan, n: Nozzle, cfg: HwConfig, chain: Chain, tier: int) -> str:
    base = f"{_fmt(plan.rate, 0)} L/ha a {_fmt(plan.speed)} km/h: {_fmt(plan.q_nozzle, 2)} L/min per ugello con {n.code} a {_fmt(plan.pressure)} bar"
    if chain.pwm and plan.duty is not None:
        base += f" (duty PWM {_fmt(plan.duty * 100, 0)} %)"
    if tier == 1:
        base += f". Serve commutare sull'ugello {n.code} (SELETRON)."
    elif tier == 2:
        base += f". Serve guidare a {_fmt(plan.speed)} km/h invece di {_fmt(cfg.speed_nom)}."
    elif tier == 3:
        base += f". Serve commutare su {n.code} e guidare a {_fmt(plan.speed)} km/h."
    else:
        base += "."
    return base


def _explain_limited(plan: Plan, rate: float, n: Nozzle, cfg: HwConfig, chain: Chain) -> str:
    q_req = q_required(rate, plan.speed or cfg.speed_nom, cfg.spacing)
    head = (f"{_fmt(rate, 0)} L/ha richiedono {_fmt(q_req, 2)} L/min per ugello a {_fmt(plan.speed)} km/h; ")
    if plan.status == "over":
        return (head + f"il minimo ottenibile con {n.code} è {_fmt(plan.q_nozzle, 2)} L/min. "
                f"Non si riesce a scendere sotto circa {_fmt(plan.delivered, 0)} L/ha (+{_fmt(abs(plan.dev_pct or 0), 0)} %).")
    return (head + f"il massimo ottenibile con {n.code} è {_fmt(plan.q_nozzle, 2)} L/min. "
            f"Con questo hardware si eroga al più {_fmt(plan.delivered, 0)} L/ha (-{_fmt(abs(plan.dev_pct or 0), 0)} %).")


def _hint_nozzle(rate: float, cfg: HwConfig, chain: Chain, cat: Catalog) -> str:
    """Suggerisce l'ugello singolo del catalogo che raggiunge il rateo alla velocità di lavoro."""
    base = chain.nozzles[0]
    best = None
    for n in cat.nozzles():
        if base.angle is not None and n.angle is not None and abs(n.angle - base.angle) > 1:
            continue
        if base.low_drift and not n.low_drift:
            continue
        r = reach(n, rate, cfg.speed_nom, cfg, chain)
        if not r.ok:
            continue
        _, fines = n.droplets(r.p)
        plo, phi = chain.window(n)
        margin = min(r.p - plo, phi - r.p)
        key = (fines if fines is not None else 999.0, -margin)
        if best is None or key < best[0]:
            best = (key, n, r)
    if best is None:
        return "Nessun ugello del catalogo raggiunge questo rateo con la finestra di pressione e la velocità impostate."
    _, n, r = best
    return f"Con {n.code} il rateo sarebbe raggiungibile a {_fmt(cfg.speed_nom)} km/h ({_fmt(r.p)} bar)."


# --------------------------------------------------------------------------- valutazione di un'intera prescrizione

@dataclass
class ClassIn:
    idx: int
    rate: Optional[float]
    area: Optional[float]


def evaluate(classes: list[ClassIn], cfg: HwConfig, chain: Chain, cat: Catalog, *, variable_file: bool) -> list[Plan]:
    plans: list[Plan] = []
    cache: dict[Optional[float], Plan] = {}
    for c in classes:
        key = None if c.rate is None else round(c.rate, 4)
        if key in cache:
            plans.append(cache[key])
            continue
        plan = plan_rate(c.rate, cfg, chain, cat)
        if variable_file and not chain.vra and plan.status in ("ok", "adapt", "under", "over"):
            plan = Plan(**{**plan.__dict__, "status": "novra", "flags": plan.flags + ["novra"],
                           "explain": "Con questa catena non è dimostrata l'esecuzione di ratei variabili: serve un rateo unico (la specializzazione lo propone)."})
        cache[key] = plan
        plans.append(plan)
    return plans


def weights(classes: list[ClassIn]) -> tuple[list[float], str]:
    if classes and all(c.area is not None for c in classes):
        return [float(c.area) for c in classes], "area"          # type: ignore[arg-type]
    return [1.0 for _ in classes], "zone"


def kpis(classes: list[ClassIn], plans: list[Plan]) -> dict[str, Any]:
    w, by = weights(classes)
    treated = [i for i, c in enumerate(classes) if c.rate and c.rate > 0]
    tw = sum(w[i] for i in treated)
    off = sum(w[i] for i, c in enumerate(classes) if c.rate == 0)

    def share(statuses: tuple[str, ...]) -> float:
        return (sum(w[i] for i in treated if plans[i].status in statuses) / tw * 100.0) if tw > 0 else 0.0

    out: dict[str, Any] = {
        "weighted_by": by, "treated": round(tw, 3), "off": round(off, 3),
        "ok_pct": round(share(("ok",)), 1), "adapt_pct": round(share(("adapt",)), 1),
        "on_target_pct": round(share(("ok", "adapt")), 1),
        "under_pct": round(share(("under",)), 1), "over_pct": round(share(("over",)), 1),
        "novra_pct": round(share(("novra",)), 1),
        "classes_off_target": sum(1 for i in treated if plans[i].status in ("under", "over", "novra")),
        "classes_treated": len(treated),
    }
    if by == "area":
        vp = sum(w[i] * (classes[i].rate or 0) for i in treated)
        vd = sum(w[i] * (plans[i].delivered or 0) for i in treated if plans[i].delivered is not None)
        out["volume_prescribed_l"] = round(vp, 1)
        out["volume_delivered_l"] = round(vd, 1)
        out["volume_delta_pct"] = round((vd - vp) / vp * 100.0, 1) if vp > 0 else 0.0
    known = [i for i in treated if plans[i].fines is not None]
    kw = sum(w[i] for i in known)
    if kw > 0:
        out["fines_avg_pct"] = round(sum(w[i] * plans[i].fines for i in known) / kw, 1)    # type: ignore[operator]
        out["fines_coverage_pct"] = round(kw / tw * 100.0, 0) if tw > 0 else 0
    else:
        out["fines_avg_pct"] = None
        out["fines_coverage_pct"] = 0
    runnable = [i for i in treated if plans[i].status in ("ok", "adapt")]
    out["switch_pct"] = round(sum(w[i] for i in runnable if "switch" in plans[i].flags) / tw * 100.0, 1) if tw > 0 else 0.0
    out["speed_pct"] = round(sum(w[i] for i in runnable if "speed" in plans[i].flags) / tw * 100.0, 1) if tw > 0 else 0.0
    return out


def envelope(cfg: HwConfig, chain: Chain) -> dict[str, Any]:
    """Campo di rateo (L/ha) raggiungibile da ciascun ugello e dall'insieme, alla velocità di lavoro e a qualunque velocità."""
    items = []
    for n in chain.nozzles:
        lim = flow_limits(n, cfg, chain)
        if lim is None:
            continue
        plo, phi = chain.window(n)
        vlo = cfg.speed_min if cfg.allow_speed_adapt else cfg.speed_nom
        vhi = cfg.speed_max if cfg.allow_speed_adapt else cfg.speed_nom
        items.append({
            "code": n.code, "name": n.name, "q_min": round(lim[0], 3), "q_max": round(lim[1], 3),
            "p_min": round(plo, 2), "p_max": round(phi, 2), "estimated": n.estimated,
            "nom": [round(rate_from_q(lim[0], cfg.speed_nom, cfg.spacing), 1), round(rate_from_q(lim[1], cfg.speed_nom, cfg.spacing), 1)],
            "any": [round(rate_from_q(lim[0], vhi, cfg.spacing), 1), round(rate_from_q(lim[1], vlo, cfg.spacing), 1)],
            "boom_flow": [round(lim[0] * cfg.n_nozzles, 1), round(lim[1] * cfg.n_nozzles, 1)],
        })
    return {"nozzles": items, "pwm": chain.pwm}


# --------------------------------------------------------------------------- specializzazione

@dataclass
class Specialisation:
    strategy: str
    new_rate: dict[int, float]
    plans_after: list[Plan]
    kpi_after: dict[str, Any]
    agronomic: dict[str, Any]
    changed: list[int]
    uniform_rate: Optional[float] = None


def specialise(classes: list[ClassIn], plans: list[Plan], cfg: HwConfig, chain: Chain, cat: Catalog) -> Specialisation:
    positive = [c for c in classes if c.rate and c.rate > 0]
    distinct = {round(c.rate, 2) for c in positive}          # type: ignore[arg-type]
    strategy = cfg.strategy
    if strategy == "auto":
        strategy = "variable" if (chain.vra or len(distinct) <= 1) else "uniform"
    if strategy == "variable" and not chain.vra and len(distinct) > 1:
        strategy = "uniform"                                  # l'hardware non può eseguire un rateo variabile

    new_rate: dict[int, float] = {}
    uniform_rate = None
    if strategy == "uniform":
        w, _ = weights(classes)
        tw = sum(w[i] for i, c in enumerate(classes) if c.rate and c.rate > 0)
        if cfg.uniform_rate and cfg.uniform_rate > 0:
            target = cfg.uniform_rate
        elif tw > 0:
            target = sum(w[i] * (c.rate or 0) for i, c in enumerate(classes) if c.rate and c.rate > 0) / tw
        else:
            target = 0.0
        if target > 0:
            p = plan_rate(target, cfg, chain, cat, with_hint=False)
            uniform_rate = round(p.delivered if p.delivered is not None else target, 2)
        for c in classes:
            if c.rate and c.rate > 0 and uniform_rate:
                new_rate[c.idx] = uniform_rate
    else:
        for c, p in zip(classes, plans):
            if c.rate and c.rate > 0 and p.status in ("under", "over") and p.delivered:
                new_rate[c.idx] = round(p.delivered, 2)

    # classi effettivamente cambiate (oltre l'arrotondamento al centesimo)
    changed = [c.idx for c in classes if c.idx in new_rate and c.rate and abs(new_rate[c.idx] - c.rate) > 0.005]
    after_classes = [ClassIn(c.idx, new_rate.get(c.idx, c.rate) if c.idx in changed else c.rate, c.area) for c in classes]
    plans_after = evaluate(after_classes, cfg, chain, cat, variable_file=False)
    kpi_after = kpis(after_classes, plans_after)

    w, by = weights(classes)
    treated = [i for i, c in enumerate(classes) if c.rate and c.rate > 0]
    tw = sum(w[i] for i in treated)
    tol = cfg.tolerance_pct / 100.0
    moved = sum(w[i] for i in treated if classes[i].idx in changed and abs(after_classes[i].rate - classes[i].rate) / classes[i].rate > tol)   # type: ignore[operator]
    agr: dict[str, Any] = {
        "weighted_by": by,
        "changed_classes": len(changed),
        "moved_beyond_tolerance_pct": round(moved / tw * 100.0, 1) if tw > 0 else 0.0,
    }
    if by == "area":
        vp = sum(w[i] * classes[i].rate for i in treated)                                   # type: ignore[operator]
        vn = sum(w[i] * after_classes[i].rate for i in treated)                             # type: ignore[operator]
        agr["volume_original_l"] = round(vp, 1)
        agr["volume_specialised_l"] = round(vn, 1)
        agr["volume_delta_pct"] = round((vn - vp) / vp * 100.0, 1) if vp > 0 else 0.0
    return Specialisation(strategy=strategy, new_rate=new_rate, plans_after=plans_after, kpi_after=kpi_after,
                          agronomic=agr, changed=changed, uniform_rate=uniform_rate)


# --------------------------------------------------------------------------- confronto e suggerimenti

def compare(classes: list[ClassIn], a: list[Plan], b: list[Plan]) -> list[str]:
    """Per classe: 'better' | 'worse' | 'same' passando da A a B."""
    out = []
    for c, pa, pb in zip(classes, a, b):
        if not c.rate or c.rate <= 0:
            out.append("same")
            continue
        ra, rb = STATUS_RANK.get(pa.status, 4), STATUS_RANK.get(pb.status, 4)
        da, db = abs(pa.dev_pct or 0.0), abs(pb.dev_pct or 0.0)
        if rb < ra or (rb == ra and db < da - 1.0):
            out.append("better")
        elif rb > ra or (rb == ra and db > da + 1.0):
            out.append("worse")
        else:
            out.append("same")
    return out


def _compress(classes: list[ClassIn], max_bins: int = 60) -> list[ClassIn]:
    """Riduce i ratei a pochi contenitori pesati per area (solo per i suggerimenti)."""
    pos = [c for c in classes if c.rate and c.rate > 0]
    if len(pos) <= max_bins:
        return classes
    pos.sort(key=lambda c: c.rate)    # type: ignore[arg-type, return-value]
    step = len(pos) / max_bins
    out = []
    for b in range(max_bins):
        grp = pos[int(b * step):int((b + 1) * step)] or pos[-1:]
        a = [g.area if g.area is not None else 1.0 for g in grp]
        tot = sum(a) or 1.0
        out.append(ClassIn(b, sum((g.rate or 0) * x for g, x in zip(grp, a)) / tot, tot))
    return out


def suggest(classes: list[ClassIn], cfg: HwConfig, chain: Chain, cat: Catalog, limit: int = 3) -> dict[str, Any]:
    """Cerca gli ugelli (singoli e coppie su SELETRON) che migliorano la copertura dei ratei richiesti."""
    base = chain.nozzles[0] if chain.nozzles else None
    if base is None or not any(c.rate and c.rate > 0 for c in classes):
        return {"singles": [], "pairs": []}
    comp = _compress(classes)

    def pool() -> list[Nozzle]:
        out = []
        for n in cat.nozzles():
            if base.angle is not None and n.angle is not None and abs(n.angle - base.angle) > 1:
                continue
            if base.low_drift and not n.low_drift:
                continue
            if flow_limits(n, cfg, Chain(**{**chain.__dict__, "nozzles": [n]})) is None:
                continue
            out.append(n)
        return out

    candidates = [n for n in pool() if not n.estimated or n.code == base.code]
    if not candidates:
        candidates = pool()

    def score(nozs: list[Nozzle]) -> dict[str, Any]:
        ch = Chain(**{**chain.__dict__, "nozzles": nozs})
        pl = evaluate(comp, cfg, ch, cat, variable_file=False)
        k = kpis(comp, pl)
        return {"nozzles": [n.code for n in nozs], "on_target_pct": k["on_target_pct"], "ok_pct": k["ok_pct"],
                "adapt_pct": k["adapt_pct"], "fines_avg_pct": k["fines_avg_pct"],
                "under_pct": k["under_pct"], "over_pct": k["over_pct"]}

    base_flow = base.flow(cfg.pressure_set)

    def sort_key(x: dict[str, Any]) -> tuple:
        # prima la copertura, poi meno adattamenti, poi meno gocce fini, poi l'ugello più simile a quello attuale
        dist = min(abs(cat.nozzle(c).flow(cfg.pressure_set) - base_flow) for c in x["nozzles"])  # type: ignore[union-attr]
        return (-x["on_target_pct"], x["adapt_pct"], x["fines_avg_pct"] if x["fines_avg_pct"] is not None else 999, len(x["nozzles"]), dist)

    singles = sorted((score([n]) for n in candidates), key=sort_key)
    pairs: list[dict[str, Any]] = []
    if chain.ways >= 2 and cat.caps(cfg.actuator).get("selective_nozzle_control"):
        # coppie: limito il pool agli ugelli più sensati (stessa famiglia della base, al massimo 14)
        pool_pairs = sorted(candidates, key=lambda n: n.flow(3.0))
        if len(pool_pairs) > 14:
            step = len(pool_pairs) / 14.0
            pool_pairs = [pool_pairs[int(i * step)] for i in range(14)]
            if base not in pool_pairs:
                pool_pairs.append(base)
        for i in range(len(pool_pairs)):
            for j in range(i + 1, len(pool_pairs)):
                pairs.append(score([pool_pairs[i], pool_pairs[j]]))
        pairs.sort(key=sort_key)
        # una coppia ha senso solo se batte il miglior ugello singolo
        if singles:
            top = singles[0]
            pairs = [p for p in pairs if (p["on_target_pct"], -p["adapt_pct"]) > (top["on_target_pct"], -top["adapt_pct"])]
    current = score(chain.nozzles)
    return {"current": current, "singles": singles[:limit], "pairs": pairs[:limit]}
