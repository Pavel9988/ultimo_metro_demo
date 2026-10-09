"""Server HTTP (solo libreria standard) con una sessione separata per ogni visitatore."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from email.parser import BytesParser
from email.policy import HTTP as HTTP_POLICY
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from . import __version__, isoxml, netinfo, service
from .service import ServiceError, SessionStore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEFAULT_PORT = 8765
MAX_JSON_BYTES = 2 * 1024 * 1024
COOKIE = "um_sid"

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "font-src 'self'; connect-src 'self' https://api.open-meteo.com https://geocoding-api.open-meteo.com; "
       "frame-ancestors 'self'; base-uri 'none'; form-action 'self'")

STORE = SessionStore()


class UmServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


class Handler(BaseHTTPRequestHandler):
    server_version = f"UltimoMetro/{__version__}"
    protocol_version = "HTTP/1.1"

    # ---- utilità ---------------------------------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:       # log compatto, solo errori e API
        line = fmt % args
        if " 200 " in line or " 304 " in line:
            return
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} {line}\n")

    def _session(self):
        raw = self.headers.get("Cookie")
        sid = None
        if raw:
            try:
                sid = SimpleCookie(raw).get(COOKIE).value        # type: ignore[union-attr]
            except Exception:
                sid = None
        sess, is_new = STORE.get(sid)
        self._new_sid = sess.sid if is_new else None
        return sess

    def _headers_common(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        sid = getattr(self, "_new_sid", None)
        if sid:
            self.send_header("Set-Cookie", f"{COOKIE}={sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=21600")
            self._new_sid = None

    def _send(self, status: int, body: bytes, ctype: str, *, extra: Optional[dict[str, str]] = None, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self._headers_common()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _fail(self, status: int, message: str, *, close: bool = False) -> None:
        if close:
            self.close_connection = True
        self._json({"ok": False, "error": message}, status)

    def _read_body(self, limit: int) -> Optional[bytes]:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            self._fail(400, "Richiesta non valida.", close=True)
            return None
        if n > limit:
            self._fail(413, f"File troppo grande (massimo {limit // (1024 * 1024)} MB).", close=True)
            return None
        data = self.rfile.read(n) if n else b""
        if len(data) != n:
            self._fail(400, "Caricamento interrotto.", close=True)
            return None
        return data

    def _json_body(self) -> Optional[dict[str, Any]]:
        raw = self._read_body(MAX_JSON_BYTES)
        if raw is None:
            return None
        if not raw:
            return {}
        try:
            val = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._fail(400, "JSON non valido.")
            return None
        if not isinstance(val, dict):
            self._fail(400, "Richiesta non valida.")
            return None
        return val

    # ---- routing ---------------------------------------------------------------------------------

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/healthz":
                return self._json({"ok": True, "version": __version__, "sessions": STORE.count()})
            if path == "/api/examples":
                self._session()
                return self._json({"ok": True, "examples": service.list_examples()})
            if path == "/api/network":
                return self._json(self._network_payload())
            if path == "/api/session":
                sess = self._session()
                with sess.lock:
                    if sess.rx is None:
                        return self._json({"ok": True, "loaded": False})
                    return self._json({"loaded": True, "filename": sess.filename, **service.import_payload(sess.rx)})
            if path.startswith("/api/"):
                return self._fail(404, "Percorso non trovato.")
            return self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception:                                        # noqa: BLE001
            self._internal_error()

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            sess = self._session()
            if path == "/api/import":
                return self._import(sess)
            if path == "/api/reset":
                with sess.lock:
                    sess.raw, sess.rx, sess.filename = None, None, ""
                self._read_body(MAX_JSON_BYTES)
                return self._json({"ok": True})
            if path in ("/api/example", "/api/evaluate", "/api/export", "/api/report"):
                body = self._json_body()
                if body is None:
                    return
                with sess.lock:
                    if path == "/api/example":
                        return self._json(service.load_example(sess, str(body.get("id", ""))))
                    if path == "/api/evaluate":
                        return self._json(service.evaluate_payload(sess, body))
                    if path == "/api/export":
                        data, name, summary = service.build_export(sess, body)
                        return self._send(200, data, "application/zip", extra={
                            "Content-Disposition": f'attachment; filename="{name}"',
                            "X-UM-Summary": urllib.parse.quote(json.dumps(summary, ensure_ascii=False, separators=(",", ":")), safe=""),
                            "Access-Control-Expose-Headers": "X-UM-Summary, Content-Disposition"})
                    html = service.build_report(sess, body)
                    return self._send(200, html, "text/html; charset=utf-8",
                                      extra={"Content-Disposition": 'inline; filename="piano_di_lavoro.html"'})
            return self._fail(404, "Percorso non trovato.", close=True)
        except (ServiceError, isoxml.IsoxmlError) as exc:
            self._fail(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception:                                        # noqa: BLE001
            self._internal_error()

    # ---- gestori ---------------------------------------------------------------------------------

    def _import(self, sess) -> None:
        ctype = self.headers.get("Content-Type", "")
        raw = self._read_body(isoxml.MAX_UPLOAD_BYTES + 1024 * 64)
        if raw is None:
            return
        name = "TASKDATA.zip"
        if ctype.lower().startswith("multipart/form-data"):
            msg = BytesParser(policy=HTTP_POLICY).parsebytes(b"Content-Type: " + ctype.encode("latin-1", "ignore") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
            payload = None
            for part in msg.iter_parts():
                if part.get_filename():
                    name = part.get_filename()
                    payload = part.get_payload(decode=True)
                    break
            if payload is None:
                return self._fail(400, "Nessun file ricevuto.")
            raw = payload
        else:
            hdr = self.headers.get("X-Filename")
            if hdr:
                name = urllib.parse.unquote(hdr)
        name = os.path.basename(name.replace("\\", "/")) or "TASKDATA.zip"
        if len(raw) > isoxml.MAX_UPLOAD_BYTES:
            return self._fail(413, f"File troppo grande (massimo {isoxml.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
        with sess.lock:
            self._json(service.load_into(sess, raw, name))

    def _network_payload(self) -> dict[str, Any]:
        port = self.server.server_address[1]
        addrs = netinfo.lan_addresses()
        host_hdr = self.headers.get("Host", "")
        return {"ok": True, "port": port, "this_host": host_hdr,
                "addresses": [{**a, "url": f"http://{a['ip']}:{port}/"} for a in addrs],
                "hostname_url": (f"http://{netinfo.local_hostname_url()}:{port}/" if netinfo.local_hostname_url() else ""),
                "bound": self.server.server_address[0]}

    def _static(self, path: str) -> None:
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        full = os.path.abspath(os.path.join(STATIC_DIR, rel))
        root = os.path.abspath(STATIC_DIR)
        if not (full == root or full.startswith(root + os.sep)):
            return self._fail(403, "Accesso negato.")
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            if "." not in os.path.basename(rel):          # percorsi "puliti": torno alla pagina principale
                full = os.path.join(STATIC_DIR, "index.html")
            else:
                return self._fail(404, "File non trovato.")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            body = fh.read()
        immutable = full.endswith((".woff2", ".woff")) or "/vendor/" in full.replace(os.sep, "/")
        cache = "public, max-age=86400" if immutable else "no-cache"
        self._send(200, body, ctype, cache=cache)

    def _internal_error(self) -> None:
        traceback.print_exc()
        try:
            self._fail(500, "Errore interno: riprova; se si ripete, copia il messaggio nella finestra del terminale.", close=True)
        except Exception:                                        # noqa: BLE001
            pass


# --------------------------------------------------------------------------- avvio

def _env_int(*names: str) -> Optional[int]:
    for n in names:
        v = os.environ.get(n)
        if v and v.strip().isdigit():
            return int(v.strip())
    return None


def make_server(host: str, port: int, tries: int = 25) -> UmServer:
    last: Optional[OSError] = None
    for p in range(port, port + tries):
        try:
            return UmServer((host, p), Handler)
        except OSError as exc:
            last = exc
    raise OSError(f"Nessuna porta libera tra {port} e {port + tries - 1}: {last}")


def banner(server: UmServer) -> str:
    port = server.server_address[1]
    host = server.server_address[0]
    lines = ["", "  ULTIMO METRO  ·  server avviato", "  " + "─" * 58,
             f"  Su questo computer:   http://localhost:{port}/"]
    if host in ("0.0.0.0", "::", ""):
        addrs = netinfo.lan_addresses()
        if addrs:
            lines.append("  Per gli amici (stessa rete Wi-Fi/LAN):")
            for a in addrs[:4]:
                mark = "  <-- questo" if a["primary"] else ""
                lines.append(f"      http://{a['ip']}:{port}/    ({a['note']}){mark}")
            h = netinfo.local_hostname_url()
            if h:
                lines.append(f"      http://{h}:{port}/    (nome del Mac)")
            lines.append("  Se non riescono ad aprirlo: firewall (vedi LEGGIMI) oppure rete ospiti/isolata.")
        else:
            lines.append("  Nessuna rete rilevata: collega il computer al Wi-Fi/LAN per condividere.")
    else:
        lines.append("  (server in ascolto solo su questo computer)")
    lines += ["  " + "─" * 58, "  Per chiudere: Ctrl+C oppure chiudi questa finestra.", ""]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if sys.version_info < (3, 9):
        print("Serve Python 3.9 o più recente (https://www.python.org/downloads/).")
        return 1
    host = os.environ.get("ULTIMO_METRO_HOST", "0.0.0.0")
    port = _env_int("ULTIMO_METRO_PORT", "PORT") or DEFAULT_PORT
    open_browser = not (os.environ.get("NO_BROWSER") or "--no-browser" in args)
    if "--local" in args:
        host = "127.0.0.1"
    for a in args:
        if a.startswith("--port="):
            try:
                port = int(a.split("=", 1)[1])
            except ValueError:
                pass
    try:
        server = make_server(host, port)
    except OSError as exc:
        print(f"Impossibile avviare il server: {exc}")
        return 1
    actual = server.server_address[1]
    if actual != port:
        print(f"  (la porta {port} era occupata: uso la {actual})")
    print(banner(server))
    sys.stdout.flush()
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{actual}/")).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nChiuso.")
    finally:
        server.server_close()
    return 0
