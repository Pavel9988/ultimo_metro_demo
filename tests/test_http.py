"""Prova il server vero (porta libera casuale): sessioni, caricamento, valutazione, esportazione, rete."""
import http.client
import io
import json
import threading
import unittest
import zipfile

from tests.helpers import FULL, read_example
from um import isoxml, netinfo
from um.server import Handler, UmServer


class Client:
    """Un 'browser': tiene il proprio cookie di sessione."""

    def __init__(self, host, port):
        self.host, self.port, self.cookie = host, port, None

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection(self.host, self.port, timeout=10)
        h = dict(headers or {})
        if self.cookie:
            h["Cookie"] = self.cookie
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        sc = r.getheader("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0]
        out = (r.status, dict(r.getheaders()), data)
        c.close()
        return out

    def post_json(self, path, obj):
        return self.req("POST", path, json.dumps(obj).encode(), {"Content-Type": "application/json"})


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.log_message = lambda self, *a, **k: None
        cls.srv = UmServer(("0.0.0.0", 0), Handler)
        cls.port = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def client(self):
        return Client("127.0.0.1", self.port)

    def upload(self, c, name):
        return c.req("POST", "/api/import", read_example(name),
                     {"Content-Type": "application/octet-stream", "X-Filename": name})


class Basics(ServerCase):
    def test_home_and_assets_have_right_types(self):
        c = self.client()
        st, h, body = c.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("text/html", h["Content-Type"])
        self.assertIn(b"Ultimo Metro", body)
        self.assertIn("javascript", c.req("GET", "/js/main.js")[1]["Content-Type"])
        self.assertEqual(c.req("GET", "/fonts/source-sans-3-latin-400-normal.woff2")[1]["Content-Type"], "font/woff2")
        self.assertEqual(c.req("GET", "/data/arag_catalog.json")[0], 200)

    def test_no_external_resources_in_page(self):
        _, _, html = self.client().req("GET", "/")
        text = html.decode()
        self.assertNotIn("fonts.googleapis", text)
        self.assertNotIn("cdn.", text)

    def test_path_traversal_is_blocked(self):
        c = self.client()
        for p in ("/../app.py", "/%2e%2e/um/engine.py", "/..%2f..%2fetc/passwd"):
            self.assertNotEqual(c.req("GET", p)[0], 200, p)
        self.assertNotIn(b"def main", c.req("GET", "/%2e%2e/um/server.py")[2])

    def test_listening_on_all_interfaces(self):
        self.assertEqual(self.srv.server_address[0], "0.0.0.0")
        for a in netinfo.lan_addresses():           # raggiungibile dall'indirizzo di rete, non solo da localhost
            st, _, _ = Client(a["ip"], self.port).req("GET", "/healthz")
            self.assertEqual(st, 200)


class Sessions(ServerCase):
    def test_two_visitors_do_not_see_each_other(self):
        a, b = self.client(), self.client()
        self.assertEqual(self.upload(a, "01_zone_poligonali_pomodoro.zip")[0], 200)
        self.assertEqual(self.upload(b, "04_rateo_uniforme.zip")[0], 200)
        sa = json.loads(a.req("GET", "/api/session")[2])
        sb = json.loads(b.req("GET", "/api/session")[2])
        self.assertEqual(sa["filename"], "01_zone_poligonali_pomodoro.zip")
        self.assertEqual(sb["filename"], "04_rateo_uniforme.zip")

    def test_new_visitor_starts_empty(self):
        self.assertFalse(json.loads(self.client().req("GET", "/api/session")[2])["loaded"])

    def test_cookie_flags(self):
        c = self.client()
        _, h, _ = c.req("GET", "/api/session")
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertIn("SameSite=Lax", h["Set-Cookie"])


class Flow(ServerCase):
    def test_import_evaluate_export_roundtrip(self):
        c = self.client()
        st, _, body = self.upload(c, "01_zone_poligonali_pomodoro.zip")
        self.assertEqual(st, 200)
        imp = json.loads(body)
        self.assertEqual(imp["summary"]["tasks"][0]["kind"], "zones_geo")
        st, _, body = c.post_json("/api/evaluate", {"task": 0, "config": FULL})
        ev = json.loads(body)
        self.assertEqual(st, 200)
        self.assertLess(ev["kpi"]["on_target_pct"], 100)
        self.assertEqual(ev["specialisation"]["kpi_after"]["on_target_pct"], 100.0)
        # cambiando ugello migliora
        ev2 = json.loads(c.post_json("/api/evaluate", {"task": 0, "config": {**FULL, "nozzles": ["AFC11005"]}, "reference": FULL})[2])
        self.assertGreater(ev2["kpi"]["on_target_pct"], ev["kpi"]["on_target_pct"])
        self.assertIn("b", ev2["reference"]["cmp"])
        # esportazione: senza conferma rifiuta
        st, _, body = c.post_json("/api/export", {"config": FULL})
        self.assertEqual(st, 400)
        self.assertIn("conferma", json.loads(body)["error"])
        st, h, data = c.post_json("/api/export", {"config": FULL, "approve": True})
        self.assertEqual(st, 200)
        self.assertIn("NORDSON.zip", h["Content-Disposition"])
        back = isoxml.analyse(isoxml.read_package(data, "out.zip"))
        self.assertLessEqual(max(k.rate for k in back.tasks[0].classes), 263)
        orig = isoxml.analyse(isoxml.read_package(read_example("01_zone_poligonali_pomodoro.zip"), "o.zip"))
        self.assertEqual([len(p["rings"]) for p in back.tasks[0].polygons],
                         [len(p["rings"]) for p in orig.tasks[0].polygons])      # la geometria è intatta
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn("TASKDATA.XML", z.namelist())

    def test_export_without_changes_needs_no_approval(self):
        c = self.client()
        self.upload(c, "04_rateo_uniforme.zip")
        cfg = {**FULL, "nozzles": ["AFC11005"]}
        st, _, data = c.post_json("/api/export", {"config": cfg})
        self.assertEqual(st, 200)

    def test_export_refuses_incompatible_hardware(self):
        c = self.client()
        self.upload(c, "04_rateo_uniforme.zip")
        st, _, body = c.post_json("/api/export", {"config": {**FULL, "nozzles": []}})
        self.assertEqual(st, 400)

    def test_report_is_html(self):
        c = self.client()
        self.upload(c, "02_griglia_tipo1_frumento.zip")
        st, h, body = c.post_json("/api/report", {"task": 0, "config": FULL})
        self.assertEqual(st, 200)
        self.assertIn("text/html", h["Content-Type"])
        self.assertIn(b"Piano di lavoro", body)

    def test_evaluate_before_upload_is_a_clear_error(self):
        st, _, body = self.client().post_json("/api/evaluate", {"task": 0, "config": FULL})
        self.assertEqual(st, 400)
        self.assertIn("Carica", json.loads(body)["error"])

    def test_garbage_upload_is_a_clear_error(self):
        c = self.client()
        st, _, body = c.req("POST", "/api/import", b"non sono un file", {"X-Filename": "x.zip"})
        self.assertEqual(st, 400)
        self.assertFalse(json.loads(body)["ok"])

    def test_multipart_upload(self):
        c = self.client()
        raw = read_example("04_rateo_uniforme.zip")
        b = b"----umtest"
        body = (b"--" + b + b'\r\nContent-Disposition: form-data; name="file"; filename="campo.zip"\r\nContent-Type: application/zip\r\n\r\n'
                + raw + b"\r\n--" + b + b"--\r\n")
        st, _, out = c.req("POST", "/api/import", body, {"Content-Type": "multipart/form-data; boundary=----umtest"})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(out)["summary"]["filename"], "campo.zip")

    def test_bad_json_and_unknown_route(self):
        c = self.client()
        self.assertEqual(c.req("POST", "/api/evaluate", b"{rotto", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(c.req("GET", "/api/nonesiste")[0], 404)

    def test_many_parallel_visitors(self):
        results = []

        def go(i):
            cl = self.client()
            name = ["01_zone_poligonali_pomodoro.zip", "02_griglia_tipo1_frumento.zip", "04_rateo_uniforme.zip"][i % 3]
            self.upload(cl, name)
            ev = json.loads(cl.post_json("/api/evaluate", {"task": 0, "config": FULL})[2])
            sess = json.loads(cl.req("GET", "/api/session")[2])
            results.append((name, sess["filename"], ev["ok"]))

        ts = [threading.Thread(target=go, args=(i,)) for i in range(18)]
        [t.start() for t in ts]
        [t.join(30) for t in ts]
        self.assertEqual(len(results), 18)
        self.assertTrue(all(a == b and ok for a, b, ok in results))


if __name__ == "__main__":
    unittest.main()
