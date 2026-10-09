from __future__ import annotations

import io
import json
import mimetypes
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(BASE_DIR, "examples", "TASKDATA_demo.zip")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
MAX_ZIP_MEMBERS = 2500

# State is intentionally in memory: this is a single-user local demo, not a hosted service.
CURRENT_PACKAGE: dict[str, Any] | None = None


def local_name(tag: str) -> str:
    """Return the local part of an XML tag, with or without a namespace."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def numeric(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def safe_parse_xml(xml_bytes: bytes) -> ET.Element:
    if len(xml_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("TASKDATA.XML supera la dimensione consentita.")
    head = xml_bytes[:8192].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("Il file contiene dichiarazioni DTD/ENTITY non ammesse dalla demo.")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"XML non valido: {exc}") from exc
    if local_name(root.tag) != "ISO11783_TaskData":
        raise ValueError("Il file XML non sembra un TASKDATA ISOXML: radice ISO11783_TaskData non trovata.")
    return root


def read_package(raw: bytes, filename: str) -> tuple[dict[str, bytes], str, bool]:
    """Return package members, path to TASKDATA.XML and whether input was zipped."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Il file supera il limite demo di 25 MB.")

    files: dict[str, bytes] = {}
    was_zip = zipfile.is_zipfile(io.BytesIO(raw))
    if was_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                infos = [info for info in zf.infolist() if not info.is_dir()]
                if len(infos) > MAX_ZIP_MEMBERS:
                    raise ValueError("Il pacchetto contiene troppi file per la demo.")
                uncompressed = sum(info.file_size for info in infos)
                if uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("Il pacchetto estratto supererebbe il limite di 60 MB.")
                for info in infos:
                    path = info.filename.replace("\\", "/")
                    pure = PurePosixPath(path)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise ValueError("Il pacchetto ZIP contiene un percorso non sicuro.")
                    if info.flag_bits & 0x1:
                        raise ValueError("I file ZIP protetti da password non sono supportati.")
                    files[path] = zf.read(info)
        except zipfile.BadZipFile as exc:
            raise ValueError("Il pacchetto ZIP non è leggibile.") from exc
        candidates = [p for p in files if PurePosixPath(p).name.upper() == "TASKDATA.XML"]
        if not candidates:
            # Allow a lone XML stored under a different name only when it is clearly XML.
            xml_candidates = [p for p in files if p.lower().endswith(".xml") and b"ISO11783_TaskData" in files[p][:8192]]
            if len(xml_candidates) != 1:
                raise ValueError("Nel pacchetto ZIP non trovo un TASKDATA.XML riconoscibile.")
            taskdata_path = xml_candidates[0]
        else:
            taskdata_path = sorted(candidates, key=lambda p: (p.count("/"), len(p)))[0]
    else:
        if not filename.lower().endswith(".xml"):
            raise ValueError("Carica un file .zip/.isoxml oppure un TASKDATA.XML.")
        files["TASKDATA.XML"] = raw
        taskdata_path = "TASKDATA.XML"

    safe_parse_xml(files[taskdata_path])
    return files, taskdata_path, was_zip


def direct_children(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == tag]


def descendants(root: ET.Element, tag: str) -> list[ET.Element]:
    return [element for element in root.iter() if local_name(element.tag) == tag]


def attr(element: ET.Element, key: str, default: str = "") -> str:
    return element.attrib.get(key, default)


def pretty_num(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_summary(files: dict[str, bytes], taskdata_path: str, filename: str, was_zip: bool) -> dict[str, Any]:
    root = safe_parse_xml(files[taskdata_path])
    all_tags = [local_name(node.tag) for node in root.iter()]
    tag_counts: dict[str, int] = {}
    for tag in all_tags:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

    fields_by_id: dict[str, dict[str, Any]] = {}
    fields: list[dict[str, Any]] = []
    for node in descendants(root, "PFD"):
        area_m2 = numeric(attr(node, "D"), None)
        crop_ref = attr(node, "G")
        field = {
            "id": attr(node, "A"),
            "name": attr(node, "C") or attr(node, "B") or attr(node, "A") or "Campo senza nome",
            "area_ha": round(area_m2 / 10000, 2) if area_m2 is not None and area_m2 >= 0 else None,
            "area_m2": area_m2,
            "crop_ref": crop_ref,
            "points": [],
        }
        # Geometry preview: prefer the first closed polygon ring found under PLN/LSG.
        # Do not mix boundary vertices with independent PFD points or guidance lines.
        candidate_rings: list[list[dict[str, float]]] = []
        for polygon in descendants(node, "PLN"):
            for line_string in direct_children(polygon, "LSG"):
                ring: list[dict[str, float]] = []
                for pnt in direct_children(line_string, "PNT"):
                    lat = numeric(attr(pnt, "C"), None)
                    lon = numeric(attr(pnt, "D"), None)
                    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                        ring.append({"lat": lat, "lon": lon})
                if len(ring) >= 3:
                    candidate_rings.append(ring)
        if candidate_rings:
            # A PLN may contain outer/inner rings. For a small preview, use the longest valid ring.
            field["points"] = max(candidate_rings, key=len)
        fields.append(field)
        if field["id"]:
            fields_by_id[field["id"]] = field

    products_by_id: dict[str, str] = {}
    products: list[dict[str, Any]] = []
    for node in descendants(root, "PDT"):
        product = {"id": attr(node, "A"), "name": attr(node, "B") or attr(node, "A") or "Prodotto senza nome"}
        products.append(product)
        if product["id"]:
            products_by_id[product["id"]] = product["name"]

    crops_by_id: dict[str, str] = {}
    crops: list[dict[str, str]] = []
    for node in descendants(root, "CTP"):
        crop = {"id": attr(node, "A"), "name": attr(node, "B") or attr(node, "A") or "Coltura non specificata"}
        crops.append(crop)
        if crop["id"]:
            crops_by_id[crop["id"]] = crop["name"]
    for field in fields:
        field["crop"] = crops_by_id.get(field["crop_ref"], "Non indicata nel file")

    vpn_by_id: dict[str, dict[str, Any]] = {}
    for node in descendants(root, "VPN"):
        vpn_by_id[attr(node, "A")] = {
            "offset": numeric(attr(node, "B"), 0.0) or 0.0,
            "scale": numeric(attr(node, "C"), 1.0) or 1.0,
            "decimals": int(numeric(attr(node, "D"), 0) or 0),
            "unit": attr(node, "E"),
        }

    tasks: list[dict[str, Any]] = []
    all_zones: list[dict[str, Any]] = []
    rate_values_l_ha: list[float] = []
    for node in descendants(root, "TSK"):
        task_id = attr(node, "A")
        field_id = attr(node, "E")
        task = {
            "id": task_id,
            "name": attr(node, "B") or task_id or "Operazione senza nome",
            "status_code": attr(node, "G"),
            "field_id": field_id,
            "field_name": fields_by_id.get(field_id, {}).get("name", "Campo non collegato"),
            "zones": [],
            "products": [],
            "has_grid": bool(direct_children(node, "GRD")),
            "has_timelog": bool(direct_children(node, "TLG")) or bool(direct_children(node, "TIM")),
        }
        for pan in descendants(node, "PAN"):
            prod_id = attr(pan, "A")
            if prod_id and products_by_id.get(prod_id):
                product_name = products_by_id[prod_id]
                if product_name not in task["products"]:
                    task["products"].append(product_name)
        for zone_node in descendants(node, "TZN"):
            zone = {"code": attr(zone_node, "A"), "name": attr(zone_node, "B") or f"Zona {attr(zone_node, 'A', '?')}", "values": []}
            for pdv in direct_children(zone_node, "PDV"):
                raw_value = numeric(attr(pdv, "B"), None)
                vpn_id = attr(pdv, "E")
                presentation = vpn_by_id.get(vpn_id)
                display_value = raw_value
                unit = "valore ISOXML grezzo"
                decimals = 2
                if raw_value is not None and presentation is not None:
                    display_value = raw_value * presentation["scale"] + presentation["offset"]
                    unit = presentation["unit"] or "unità non specificata"
                    decimals = presentation["decimals"]
                product_ref = attr(pdv, "C")
                value = {
                    "ddi": attr(pdv, "A"),
                    "raw": raw_value,
                    "value": display_value,
                    "display": pretty_num(display_value, min(max(decimals, 0), 4)) if display_value is not None else "Non leggibile",
                    "unit": unit,
                    "product": products_by_id.get(product_ref, ""),
                }
                zone["values"].append(value)
                normalized_unit = unit.lower().replace(" ", "").replace("litri", "l").replace("litro", "l")
                if display_value is not None and ("l/ha" in normalized_unit or "lt/ha" in normalized_unit):
                    rate_values_l_ha.append(display_value)
            task["zones"].append(zone)
            all_zones.append({"task": task["name"], **zone})
        tasks.append(task)

    devices = []
    for node in descendants(root, "DVC"):
        devices.append({"id": attr(node, "A"), "name": attr(node, "B") or attr(node, "A") or "Dispositivo"})

    area_values = [f["area_ha"] for f in fields if f.get("area_ha") is not None]
    total_area_ha = sum(area_values) if area_values else None
    field_points = next((f["points"] for f in fields if len(f["points"]) >= 3), [])
    root_attrs = root.attrib
    has_grid = tag_counts.get("GRD", 0) > 0
    has_zones = tag_counts.get("TZN", 0) > 0
    has_recipe = has_grid or has_zones

    warnings: list[dict[str, str]] = []
    if not tasks:
        warnings.append({"level": "bad", "title": "Nessuna operazione", "detail": "Il file non contiene elementi TSK da analizzare."})
    if not fields:
        warnings.append({"level": "warn", "title": "Campo non trovato", "detail": "Non sono stati individuati elementi PFD. Le superfici e la mappa potrebbero non essere disponibili."})
    if not has_recipe:
        warnings.append({"level": "warn", "title": "Prescrizione non individuata", "detail": "Non trovo TZN/GRD: la dose dovrà essere verificata o inserita manualmente."})
    if not products:
        warnings.append({"level": "warn", "title": "Prodotti non elencati", "detail": "Il file non contiene record PDT; non è possibile mostrare il catalogo prodotti del task."})
    if root_attrs.get("VersionMajor") not in {"3", "4"}:
        warnings.append({"level": "warn", "title": "Versione da verificare", "detail": "La versione ISOXML non è una delle famiglie v3/v4 riconosciute dalla demo."})
    warnings.append({"level": "info", "title": "Validazione controller non eseguita", "detail": "La lettura XML non equivale alla convalida XSD o al test sul computer di bordo ARAG."})

    return {
        "filename": filename,
        "was_zip": was_zip,
        "package_files": len(files),
        "taskdata_path": taskdata_path,
        "root": local_name(root.tag),
        "version": f"{root_attrs.get('VersionMajor', '?')}.{root_attrs.get('VersionMinor', '?')}",
        "manufacturer": root_attrs.get("ManagementSoftwareManufacturer", "Non indicato"),
        "software_version": root_attrs.get("ManagementSoftwareVersion", ""),
        "transfer_origin": root_attrs.get("DataTransferOrigin", ""),
        "counts": {
            "tasks": len(tasks),
            "fields": len(fields),
            "products": len(products),
            "zones": tag_counts.get("TZN", 0),
            "grids": tag_counts.get("GRD", 0),
            "devices": len(devices),
            "time_logs": tag_counts.get("TLG", 0),
            "points": tag_counts.get("PNT", 0),
        },
        "fields": fields,
        "tasks": tasks,
        "products": products,
        "crops": crops,
        "devices": devices,
        "zones": all_zones,
        "target_rate_l_ha": max(rate_values_l_ha) if rate_values_l_ha else None,
        "min_rate_l_ha": min(rate_values_l_ha) if rate_values_l_ha else None,
        "total_area_ha": round(total_area_ha, 2) if total_area_ha is not None else None,
        "field_points": field_points,
        "has_recipe": has_recipe,
        "has_grid": has_grid,
        "warnings": warnings,
    }


def load_package(raw: bytes, filename: str) -> dict[str, Any]:
    files, taskdata_path, was_zip = read_package(raw, filename)
    summary = build_summary(files, taskdata_path, filename, was_zip)
    return {"files": files, "taskdata_path": taskdata_path, "was_zip": was_zip, "filename": filename, "summary": summary}


def api_import_file(raw: bytes, filename: str) -> dict[str, Any]:
    global CURRENT_PACKAGE
    CURRENT_PACKAGE = load_package(raw, filename)
    return {"ok": True, "summary": CURRENT_PACKAGE["summary"]}


def api_demo_file() -> dict[str, Any]:
    global CURRENT_PACKAGE
    with open(SAMPLE_PATH, "rb") as file_handle:
        CURRENT_PACKAGE = load_package(file_handle.read(), "TASKDATA_demo.zip")
    return {"ok": True, "summary": CURRENT_PACKAGE["summary"]}


def api_reset() -> dict[str, bool]:
    """Forget the currently uploaded package for this local demo session."""
    global CURRENT_PACKAGE
    CURRENT_PACKAGE = None
    return {"ok": True, "cleared": True}


def qualified_child_tag(parent: ET.Element, child_name: str) -> str:
    if parent.tag.startswith("{") and "}" in parent.tag:
        return parent.tag.split("}", 1)[0] + "}" + child_name
    return child_name


def add_or_update_preflight_comments(root: ET.Element, config: dict[str, Any]) -> int:
    tasks = descendants(root, "TSK")
    weather = str(config.get("weather_status", "DA VERIFICARE")).upper()
    weather_code = "VERDE" if weather == "VERDE" else ("ROSSA" if weather == "ROSSA" else "GIALLA")
    tank = int(max(0, min(99999, numeric(config.get("tank_l"), 1200) or 1200)))
    speed_min = numeric(config.get("speed_min"), 5) or 5
    speed_max = numeric(config.get("speed_max"), 10) or 10
    controller = str(config.get("controller", "")).strip()
    controller_product_code = re.sub(r"[^A-Za-z0-9]", "", controller)
    rate_control_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("rate_control_code", "")))
    flowmeter_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("flowmeter_code", "")))
    valve_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("valve_code", "")))
    actuator_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("actuator_code", "")))
    pump_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("pump_code", "")))
    nozzle_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("nozzle_code", "")))
    filter_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("filter_code", "")))
    nozzle_holder_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("nozzle_holder_code", "")))
    ecu_code = re.sub(r"[^A-Za-z0-9]", "", str(config.get("ecu_code", "")))
    if controller_product_code.startswith("467520"):
        controller_short = "D70T"
    elif controller_product_code.startswith("467530"):
        controller_short = "D80T"
    elif "400" in controller.lower() or controller_product_code.startswith("4674L07"):
        controller_short = "B400"
    elif "180" in controller.lower():
        controller_short = "B180"
    elif "isobus" in controller.lower():
        controller_short = "ISOB"
    else:
        controller_short = "ALTRO"
    # Use a real part code only if the input looks like a code, not a descriptive label.
    if controller_product_code.isdigit() or controller_product_code.startswith("4674L"):
        controller_code = controller_product_code[:9]
    else:
        controller_code = controller_short
    wind = numeric(config.get("wind_kmh"), None)
    temperature = numeric(config.get("temperature_c"), None)
    rain = numeric(config.get("rain_hours"), None)
    hardware_note = f"UM HW T{tank}L V{round(speed_min)}-{round(speed_max)} {controller_short}"[:32]
    arag_note = f"UM ARAG T{controller_code} R{rate_control_code[:9] or 'ND'}"[:32]
    flow_valve_note = f"UM FLOW F{flowmeter_code[:11] or 'ND'} V{valve_code[:9] or 'ND'}"[:32]
    actuator_pump_note = f"UM ACT A{actuator_code[:9] or 'ND'} P{pump_code[:8] or 'ND'}"[:32]
    nozzle_filter_note = f"UM NOZ N{nozzle_code[:9] or 'ND'} F{filter_code[:8] or 'ND'}"[:32]
    holder_note = f"UM HOLD {nozzle_holder_code[:20] or 'ND'}"[:32]
    ecu_note = f"UM ECU {ecu_code[:24] or 'ND'}"[:32]
    wx_values = [f"W{round(wind)}" if wind is not None else "W?",
                 f"T{round(temperature)}" if temperature is not None else "T?",
                 f"R{round(rain)}" if rain is not None else "R?"]
    weather_note = (f"UM WX {weather_code} " + " ".join(wx_values))[:32]

    changed = 0
    for task in tasks:
        desired = {
            "UM HW": hardware_note,
            "UM ARAG": arag_note,
            "UM FLOW": flow_valve_note,
            "UM ACT": actuator_pump_note,
            "UM NOZ": nozzle_filter_note,
            "UM HOLD": holder_note,
            "UM ECU": ecu_note,
            "UM WX": weather_note,
        }
        for prefix, note in desired.items():
            existing = None
            for child in direct_children(task, "CAN"):
                if attr(child, "C").startswith(prefix):
                    existing = child
                    break
            if existing is not None:
                existing.set("C", note)
            else:
                child = ET.Element(qualified_child_tag(task, "CAN"), {"C": note})
                # Add CAN before logging/control elements in the task sequence when possible.
                insert_before = {"DLT", "TIM", "TLG", "GRD", "CAT", "GAN"}
                idx = next((i for i, item in enumerate(list(task)) if local_name(item.tag) in insert_before), len(list(task)))
                task.insert(idx, child)
        changed += 1
    return changed


def api_export_package(config: dict[str, Any]) -> tuple[bytes, str, int]:
    if CURRENT_PACKAGE is None:
        raise ValueError("Nessun file caricato.")
    root = safe_parse_xml(CURRENT_PACKAGE["files"][CURRENT_PACKAGE["taskdata_path"]])
    count = add_or_update_preflight_comments(root, config)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        if CURRENT_PACKAGE["was_zip"]:
            for path, content in CURRENT_PACKAGE["files"].items():
                zout.writestr(path, xml_bytes if path == CURRENT_PACKAGE["taskdata_path"] else content)
        else:
            zout.writestr("TASKDATA.XML", xml_bytes)
    output.seek(0)
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(CURRENT_PACKAGE["filename"])[0]).strip("_") or "TASKDATA"
    return output.read(), f"{base}_ultimometro.zip", count


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "UltimoMetroDemo/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep console output small and readable for beginners.
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, max_bytes: int = MAX_UPLOAD_BYTES + 2 * 1024 * 1024) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length non valido.")
        if length < 0 or length > max_bytes:
            raise ValueError("Richiesta troppo grande. Il limite file demo è 25 MB.")
        return self.rfile.read(length)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/current":
            if CURRENT_PACKAGE is None:
                self.send_json(200, {"loaded": False})
            else:
                self.send_json(200, {"loaded": True, "summary": CURRENT_PACKAGE["summary"]})
            return
        if route == "/" or route == "/index.html":
            target = Path(BASE_DIR) / "static" / "index.html"
        elif route.startswith("/static/"):
            relative = route.removeprefix("/static/")
            target = (Path(BASE_DIR) / "static" / relative).resolve()
            static_root = (Path(BASE_DIR) / "static").resolve()
            if static_root not in target.parents or not target.is_file():
                self.send_error(404, "File non trovato")
                return
        else:
            self.send_error(404, "Risorsa non trovata")
            return
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(404, "File non trovato")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        try:
            if route == "/api/demo":
                self.read_body(100_000)
                self.send_json(200, api_demo_file())
                return
            if route == "/api/reset":
                self.read_body(100_000)
                self.send_json(200, api_reset())
                return
            if route == "/api/import":
                body = self.read_body()
                content_type = self.headers.get("Content-Type", "")
                if not content_type.lower().startswith("multipart/form-data"):
                    raise ValueError("Richiesta upload non riconosciuta: usa la selezione file dell'interfaccia.")
                message_bytes = b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
                message = BytesParser(policy=policy.default).parsebytes(message_bytes)
                uploaded = None
                filename = "TASKDATA.XML"
                if message.is_multipart():
                    for part in message.iter_parts():
                        disposition = part.get("Content-Disposition", "")
                        if part.get_param("name", header="content-disposition") == "file":
                            uploaded = part.get_payload(decode=True)
                            filename = part.get_filename() or filename
                            break
                if uploaded is None:
                    raise ValueError("Seleziona un file ISOXML da caricare.")
                if len(uploaded) > MAX_UPLOAD_BYTES:
                    raise ValueError("Il file supera il limite demo di 25 MB.")
                self.send_json(200, api_import_file(uploaded, filename))
                return
            if route == "/api/export":
                body = self.read_body(100_000)
                try:
                    config = json.loads(body.decode("utf-8") or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("Parametri di export non validi.") from exc
                zipped, filename, count = api_export_package(config if isinstance(config, dict) else {})
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(zipped)))
                self.send_header("X-Ultimo-Metro-Tasks-Annotated", str(count))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(zipped)
                return
            self.send_error(404, "Endpoint non trovato")
        except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception as exc:  # Last-resort error boundary for a live demo.
            self.send_json(500, {"error": f"Errore interno demo: {exc}"})


def run_server() -> None:
    print("\n================================================")
    print("             ULTIMO METRO - DEMO")
    print("================================================")
    print("Apri nel browser: http://127.0.0.1:5000")
    print("Server locale; non esporlo su Internet. CTRL+C per fermare.\n")
    server = ThreadingHTTPServer(("127.0.0.1", 5000), DemoHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChiusura server...")
    finally:
        server.server_close()



if __name__ == "__main__":
    run_server()
