import io
import unittest
import zipfile

from tests.helpers import read_example
from um import isoxml


def analyse(name):
    return isoxml.analyse(isoxml.read_package(read_example(name), name))


class Reading(unittest.TestCase):
    def test_polygon_zones(self):
        rx = analyse("01_zone_poligonali_pomodoro.zip")
        t = rx.tasks[0]
        self.assertEqual(t.kind, "zones_geo")
        self.assertEqual([round(k.rate) for k in t.classes], [150, 220, 300, 340])
        total = sum(k.area_ha for k in t.classes)
        self.assertAlmostEqual(total, rx.fields[0].area_ha, delta=rx.fields[0].area_ha * 0.03)

    def test_grid_type1_orientation_and_mask(self):
        rx = analyse("02_griglia_tipo1_frumento.zip")
        t = rx.tasks[0]
        self.assertEqual(t.kind, "grid1")
        g = t.grid
        self.assertEqual(len(g.cell_class), g.cols * g.rows)
        # tutte le celle trattate cadono dentro al contorno del campo
        rings = rx.fields[0].rings
        for r in range(g.rows):
            iv = isoxml.row_intervals(rings, g.min_lat + (r + 0.5) * g.dlat)
            for c in range(g.cols):
                if g.cell_class[r * g.cols + c] != isoxml.OUTSIDE:
                    x = g.min_lon + (c + 0.5) * g.dlon
                    self.assertTrue(any(a <= x <= b for a, b in iv))

    def test_grid_type2_many_classes(self):
        t = analyse("03_griglia_tipo2_mappa_continua.zip").tasks[0]
        self.assertEqual(t.kind, "grid2")
        self.assertGreater(len(t.classes), 100)
        rates = [k.rate for k in t.classes]
        self.assertEqual(rates, sorted(rates))

    def test_single_rate_without_geometry(self):
        t = analyse("04_rateo_uniforme.zip").tasks[0]
        self.assertEqual(t.kind, "zones_nogeo")
        self.assertEqual(t.classes[0].rate, 200.0)

    def test_two_fields_two_tasks(self):
        rx = analyse("05_due_campi_due_task.zip")
        self.assertEqual(len(rx.fields), 2)
        self.assertEqual([t.kind for t in rx.tasks], ["zones_geo", "grid1"])

    def test_zones_without_geometry_are_declared_not_invented(self):
        t = analyse("06_zone_senza_geometria.zip").tasks[0]
        self.assertEqual(t.kind, "zones_nogeo")
        self.assertTrue(any("geometria" in n for n in t.notes))
        self.assertEqual(t.polygons, [])

    def test_grid_without_coordinates_is_flagged(self):
        t = analyse("07_griglia_senza_coordinate.zip").tasks[0]
        self.assertFalse(t.grid.geo)
        self.assertTrue(any("coordinate" in n for n in t.notes))

    def test_external_file_and_rates_without_vpn(self):
        rx = analyse("08_file_esterno_e_dosi_senza_vpn.zip")
        self.assertEqual([round(k.rate) for k in rx.tasks[0].classes], [90, 175])
        self.assertTrue(rx.fields[0].rings)


class RoundTrip(unittest.TestCase):
    def test_apply_rates_and_verify_every_example(self):
        import glob, os
        from tests.helpers import ROOT
        for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.zip"))):
            name = os.path.basename(path)
            raw = read_example(name)
            rx = isoxml.analyse(isoxml.read_package(raw, name))
            mapping_by_task = {}
            for t in rx.tasks:
                pos = [k for k in t.classes if k.rate and k.rate > 0]
                if not pos:
                    continue
                m = {pos[-1].idx: round(pos[-1].rate * 0.8, 2)}      # riscrivo la classe più alta
                isoxml.apply_rates(rx, t, m)
                mapping_by_task[t.index] = m
            out = isoxml.build_zip(isoxml.serialize(rx))
            back = isoxml.analyse(isoxml.read_package(out, "x.zip"))
            for ti, m in mapping_by_task.items():
                self.assertEqual(isoxml.verify_task(rx.tasks[ti], back.tasks[ti], m), [], name)

    def test_note_is_short(self):
        rx = analyse("01_zone_poligonali_pomodoro.zip")
        isoxml.add_note(rx.tasks[0], "UM NORDSON VRA AFC11002 " + "x" * 40)
        xml = isoxml.serialize(rx)[rx.pkg.main.path].decode("utf-8")
        import re
        notes = re.findall(r'<CAN [^>]*C="([^"]*)"', xml)
        self.assertTrue(notes and all(len(n) <= 32 for n in notes))


class Hostile(unittest.TestCase):
    def _zip(self, files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for k, v in files.items():
                z.writestr(k, v)
        return buf.getvalue()

    def test_dtd_and_entities_rejected(self):
        evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><ISO11783_TaskData VersionMajor="4"/>'
        with self.assertRaises(isoxml.IsoxmlError):
            isoxml.read_package(self._zip({"TASKDATA.XML": evil}), "a.zip")

    def test_not_a_zip_nor_xml(self):
        with self.assertRaises(isoxml.IsoxmlError):
            isoxml.read_package(b"hello", "a.zip")

    def test_zip_without_taskdata(self):
        with self.assertRaises(isoxml.IsoxmlError):
            isoxml.read_package(self._zip({"altro.txt": "x"}), "a.zip")

    def test_zip_slip_paths_are_refused(self):
        ok = b'<?xml version="1.0"?><ISO11783_TaskData VersionMajor="4" VersionMinor="3" ManagementSoftwareManufacturer="m" ManagementSoftwareVersion="1" DataTransferOrigin="1"/>'
        with self.assertRaises(isoxml.IsoxmlError):
            isoxml.read_package(self._zip({"TASKDATA.XML": ok, "../../evil.txt": "x"}), "a.zip")

    def test_zip_bomb_is_refused(self):
        big = b"<a>" + b"x" * (60 * 1024 * 1024) + b"</a>"
        with self.assertRaises(isoxml.IsoxmlError):
            isoxml.read_package(self._zip({"TASKDATA.XML": big}), "a.zip")


if __name__ == "__main__":
    unittest.main()
