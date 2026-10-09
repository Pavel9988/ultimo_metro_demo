"""Servizi applicativi: importazione, valutazione live, esportazione e rapporto."""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from . import isoxml
from .engine import ClassIn, Plan, compare, envelope, evaluate, kpis, specialise, suggest
from .hardware import Catalog, HwConfig, load_catalog, resolve_chain
from .isoxml import Rx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(BASE_DIR, "examples")

STATUS_CODE = {"ok": "o", "adapt": "a", "under": "u", "over": "v", "off": "f", "nodata": "n", "novra": "x"}


class ServiceError(ValueError):
    pass


# --------------------------------------------------------------------------- sessioni

@dataclass
class Session:
    sid: str
    created: float = field(default_factory=time.time)
    last: float = field(default_factory=time.time)
    raw: Optional[bytes] = None
    filename: str = ""
    rx: Optional[Rx] = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class SessionStore:
    """Una sessione per visitatore (cookie): gli amici non si sovrascrivono più i file a vicenda."""

    def __init__(self, ttl: float = 6 * 3600, max_sessions: int = 80):
        self._lock = threading.Lock()
        self._items: dict[str, Session] = {}
        self.ttl = ttl
        self.max_sessions = max_sessions

    def get(self, sid: Optional[str]) -> tuple[Session, bool]:
        now = time.time()
        with self._lock:
            for k in [k for k, s in self._items.items() if now - s.last > self.ttl]:
                del self._items[k]
            if sid and sid in self._items:
                s = self._items[sid]
                s.last = now
                return s, False
            if len(self._items) >= self.max_sessions:
                oldest = min(self._items.values(), key=lambda s: s.last)
                del self._items[oldest.sid]
            s = Session(sid=uuid.uuid4().hex)
            self._items[s.sid] = s
            return s, True

    def count(self) -> int:
        with self._lock:
            return len(self._items)


# --------------------------------------------------------------------------- importazione

def load_into(session: Session, raw: bytes, filename: str) -> dict[str, Any]:
    pkg = isoxml.read_package(raw, filename)
    rx = isoxml.analyse(pkg)
    session.raw, session.filename, session.rx = raw, filename, rx
    return import_payload(rx)


def import_payload(rx: Rx) -> dict[str, Any]:
    return {"ok": True, "summary": isoxml.public_summary(rx), "geometry": isoxml.public_geometry(rx)}


def list_examples() -> list[dict[str, Any]]:
    import json
    path = os.path.join(EXAMPLES_DIR, "manifest.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def load_example(session: Session, example_id: str) -> dict[str, Any]:
    item = next((e for e in list_examples() if e.get("id") == example_id), None)
    if not item:
        raise ServiceError("Esempio non riconosciuto.")
    path = os.path.abspath(os.path.join(EXAMPLES_DIR, item["file"]))
    if not path.startswith(os.path.abspath(EXAMPLES_DIR) + os.sep) or not os.path.isfile(path):
        raise ServiceError("Pacchetto di esempio non trovato.")
    with open(path, "rb") as fh:
        data = fh.read()
    out = load_into(session, data, os.path.basename(path))
    out["example"] = {"id": item["id"], "title": item.get("title", ""), "description": item.get("description", ""),
                      "suggested_config": item.get("suggested_config")}
    return out


# --------------------------------------------------------------------------- valutazione

def _task(session: Session, index: Any) -> isoxml.TaskModel:
    if session.rx is None:
        raise ServiceError("Carica prima un file ISOXML.")
    try:
        return session.rx.tasks[int(index or 0)]
    except (IndexError, ValueError, TypeError):
        raise ServiceError("Operazione non trovata nel file.")


def _classes_in(task: isoxml.TaskModel) -> list[ClassIn]:
    return [ClassIn(k.idx, k.rate, k.area_ha) for k in task.classes]


def _is_variable(task: isoxml.TaskModel) -> bool:
    return len({round(k.rate, 2) for k in task.classes if k.rate and k.rate > 0}) > 1


def _columns(plans: list[Plan]) -> dict[str, Any]:
    codes: list[str] = []
    idx_of: dict[str, int] = {}
    nz = []
    for p in plans:
        if p.nozzle not in idx_of:
            idx_of[p.nozzle] = len(codes)
            codes.append(p.nozzle)
        nz.append(idx_of[p.nozzle])
    r = lambda x, d=1: None if x is None else round(x, d)
    return {
        "s": "".join(STATUS_CODE.get(p.status, "n") for p in plans),
        "delivered": [r(p.delivered) for p in plans],
        "dev": [r(p.dev_pct) for p in plans],
        "nozzle": nz, "nozzle_codes": codes,
        "speed": [r(p.speed) for p in plans], "pressure": [r(p.pressure, 2) for p in plans],
        "duty": [r(p.duty * 100 if p.duty is not None else None, 0) for p in plans],
        "fines": [r(p.fines, 0) for p in plans],
        "flags": [",".join(p.flags) for p in plans],
    }


def _table_rows(task: isoxml.TaskModel, plans: list[Plan], spec_new: dict[int, float], cmp: Optional[list[str]]) -> dict[str, Any]:
    """Righe per la tabella: una per classe (≤ 40) oppure per fascia di rateo se le classi sono molte."""
    ks = task.classes
    if len(ks) <= 40:
        rows = []
        for k, p in zip(ks, plans):
            row = {"i": k.idx, "label": k.label, "code": k.zone_code, "area_ha": round(k.area_ha, 2) if k.area_ha is not None else None,
                   "rate": k.rate, "plan": p.to_json(), "new_rate": spec_new.get(k.idx), "cmp": cmp[k.idx] if cmp else None}
            rows.append(row)
        return {"mode": "classes", "rows": rows}
    order = sorted(range(len(ks)), key=lambda i: ks[i].rate or 0)
    tot = sum((ks[i].area_ha or 1.0) for i in order) or 1.0
    bins: list[list[int]] = [[] for _ in range(12)]
    acc = 0.0
    for i in order:
        b = min(11, int(acc / tot * 12))
        bins[b].append(i)
        acc += ks[i].area_ha or 1.0
    rows = []
    for b in bins:
        if not b:
            continue
        area = sum(ks[i].area_ha or 0.0 for i in b)
        w = [(ks[i].area_ha or 1.0) for i in b]
        sw = sum(w) or 1.0
        pct = lambda sts: round(sum(wi for wi, i in zip(w, b) if plans[i].status in sts) / sw * 100.0)
        rates = [ks[i].rate for i in b if ks[i].rate is not None]
        rows.append({"label": f"{min(rates):.0f}–{max(rates):.0f} L/ha" if rates else "—", "area_ha": round(area, 2) if area else None,
                     "n_classes": len(b), "rate": sum(r * wi for r, wi in zip(rates, w)) / sw if rates else None,
                     "ok": pct(("ok",)), "adapt": pct(("adapt",)), "under": pct(("under",)), "over": pct(("over",)), "off": pct(("off",)),
                     "new_rate": None, "cmp": None})
    return {"mode": "bands", "rows": rows}


def _run(task: isoxml.TaskModel, cfg: HwConfig, cat: Catalog) -> dict[str, Any]:
    chain = resolve_chain(cfg, cat)
    cin = _classes_in(task)
    plans = evaluate(cin, cfg, chain, cat, variable_file=_is_variable(task))
    return {"chain": chain, "cin": cin, "plans": plans, "kpi": kpis(cin, plans)}


def evaluate_payload(session: Session, body: dict[str, Any]) -> dict[str, Any]:
    task = _task(session, body.get("task"))
    cat = load_catalog()
    cfg = HwConfig.from_dict(body.get("config") or {})
    probs = cfg.problems()
    if probs:
        raise ServiceError(" ".join(probs))
    cur = _run(task, cfg, cat)
    chain, cin, plans = cur["chain"], cur["cin"], cur["plans"]

    spec = specialise(cin, plans, cfg, chain, cat)
    out: dict[str, Any] = {
        "ok": True,
        "chain": {"blockers": chain.blockers, "warnings": chain.warnings, "vra": chain.vra, "pwm": chain.pwm,
                  "individual_nozzle": chain.individual_nozzle, "ways": chain.ways, "names": chain.names,
                  "pressure_window": [round(chain.p_lo, 2), round(chain.p_hi, 2)],
                  "nozzles": [n.code for n in chain.nozzles], "n_nozzles": cfg.n_nozzles},
        "envelope": envelope(cfg, chain),
        "plans": _columns(plans),
        "kpi": cur["kpi"],
        "specialisation": {
            "strategy": spec.strategy, "uniform_rate": spec.uniform_rate,
            "new_rate": [spec.new_rate.get(c.idx) if c.idx in spec.changed else None for c in cin],
            "s_after": "".join(STATUS_CODE.get(p.status, "n") for p in spec.plans_after),
            "kpi_after": spec.kpi_after, "agronomic": spec.agronomic, "n_changed": len(spec.changed),
        },
    }
    ref_cmp = None
    if body.get("reference"):
        rcfg = HwConfig.from_dict(body["reference"])
        ref = _run(task, rcfg, cat)
        ref_cmp = compare(cin, ref["plans"], plans)
        out["reference"] = {"plans": _columns(ref["plans"]), "kpi": ref["kpi"], "cmp": "".join({"better": "b", "worse": "w", "same": "s"}[c] for c in ref_cmp),
                            "chain": {"blockers": ref["chain"].blockers, "nozzles": [n.code for n in ref["chain"].nozzles]},
                            "envelope": envelope(rcfg, ref["chain"])}
    out["table"] = _table_rows(task, plans, {i: spec.new_rate[i] for i in spec.changed}, ref_cmp)
    if body.get("suggest") and not chain.blockers:
        out["suggestions"] = suggest(cin, cfg, chain, cat)
    det = body.get("detail")
    if isinstance(det, int) and 0 <= det < len(plans):
        out["detail"] = {"i": det, "plan": plans[det].to_json(), "after": spec.plans_after[det].to_json(),
                         "new_rate": spec.new_rate.get(cin[det].idx) if cin[det].idx in spec.changed else None}
    return out


# --------------------------------------------------------------------------- esportazione

def _note_text(strategy: str, cfg: HwConfig) -> str:
    noz = cfg.nozzles[0] if cfg.nozzles else "ND"
    return f"UM NORDSON {'VRA' if strategy == 'variable' else 'UNI'} {noz}"[:32]


def build_export(session: Session, body: dict[str, Any]) -> tuple[bytes, str, dict[str, Any]]:
    if session.raw is None or session.rx is None:
        raise ServiceError("Carica prima un file ISOXML.")
    cat = load_catalog()
    cfg = HwConfig.from_dict(body.get("config") or {})
    probs = cfg.problems()
    if probs:
        raise ServiceError(" ".join(probs))
    chain = resolve_chain(cfg, cat)
    if chain.blockers:
        raise ServiceError("Hardware non compatibile con l'esecuzione di un file ISOXML: " + " ".join(chain.blockers))

    # lavoro su una copia fresca del pacchetto: la sessione resta intatta
    pkg = isoxml.read_package(session.raw, session.filename)
    rx = isoxml.analyse(pkg)
    summary: list[dict[str, Any]] = []
    total_changed = 0
    expected: dict[int, dict[int, float]] = {}
    for task in rx.tasks:
        cin = _classes_in(task)
        if not any(c.rate and c.rate > 0 for c in cin):
            continue
        plans = evaluate(cin, cfg, chain, cat, variable_file=_is_variable(task))
        spec = specialise(cin, plans, cfg, chain, cat)
        counts = isoxml.apply_rates(rx, task, {i: spec.new_rate[i] for i in spec.changed})
        isoxml.add_note(task, _note_text(spec.strategy, cfg))
        total_changed += len(spec.changed)
        expected[task.index] = {i: spec.new_rate[i] for i in spec.changed}
        summary.append({"task": task.name, "strategy": spec.strategy, "changed_classes": len(spec.changed), **counts,
                        "kpi_before": kpis(cin, plans), "kpi_after": spec.kpi_after, "agronomic": spec.agronomic})
    if total_changed and not body.get("approve"):
        raise ServiceError("La specializzazione modifica dei ratei: controlla l'anteprima e conferma prima di scaricare.")

    files_out = isoxml.serialize(rx)
    # verifica: rileggo il file prodotto e controllo che i ratei siano quelli attesi
    check_pkg = isoxml.read_package(isoxml.build_zip(files_out), "verifica.zip")
    check = isoxml.analyse(check_pkg)
    problems = []
    for t_idx, mapping in expected.items():
        for msg in isoxml.verify_task(rx.tasks[t_idx], check.tasks[t_idx], mapping):
            problems.append(f"{rx.tasks[t_idx].name}: {msg}")
    if problems:
        raise ServiceError("Verifica del file prodotto fallita: " + "; ".join(problems[:3]))

    if session.rx.pkg.was_zip:
        zip_bytes = isoxml.build_zip(files_out)
    else:
        zip_bytes = isoxml.build_zip({"TASKDATA.XML": files_out[rx.pkg.main.path]})
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(session.filename)[0]).strip("_") or "TASKDATA"
    return zip_bytes, f"{base}_NORDSON.zip", {"tasks": summary, "changed_classes": total_changed}


def build_report(session: Session, body: dict[str, Any]) -> bytes:
    from .report import render_report
    task = _task(session, body.get("task"))
    cat = load_catalog()
    cfg = HwConfig.from_dict(body.get("config") or {})
    chain = resolve_chain(cfg, cat)
    cin = _classes_in(task)
    plans = evaluate(cin, cfg, chain, cat, variable_file=_is_variable(task))
    spec = specialise(cin, plans, cfg, chain, cat)
    return render_report(session, task, cfg, chain, cat, cin, plans, spec).encode("utf-8")
