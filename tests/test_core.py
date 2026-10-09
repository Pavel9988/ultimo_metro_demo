import io
import unittest
import zipfile
from pathlib import Path

import app

ROOT = Path(__file__).resolve().parents[1]


class IsoXmlDemoTests(unittest.TestCase):
    def setUp(self):
        app.CURRENT_PACKAGE = None
        app.api_demo_file()

    def test_demo_summary(self):
        summary = app.CURRENT_PACKAGE["summary"]
        self.assertEqual(summary["version"], "4.3")
        self.assertEqual(summary["counts"]["tasks"], 1)
        self.assertEqual(summary["counts"]["zones"], 2)
        self.assertAlmostEqual(summary["total_area_ha"], 18.6)
        self.assertAlmostEqual(summary["target_rate_l_ha"], 250.0)
        self.assertEqual(summary["devices"][0]["name"], "Irroratrice demo")
        self.assertIn("non prova", summary["devices"][0]["source_note"])

    def test_export_adds_hardware_weather_notes_and_preserves_target_values(self):
        package, filename, count = app.api_export_package({
            "tank_l": 1200,
            "speed_min": 5,
            "speed_max": 10,
            "weather_status": "GIALLA",
            "controller": "Bravo 400S",
            "rate_control_code": "4679013",
            "flowmeter_code": "46211P40000",
            "valve_code": "853T04A55",
            "actuator_code": "4063T95A0",
            "pump_code": "97055201",
            "nozzle_code": "AFC11002",
            "filter_code": "42433135",
            "nozzle_holder_code": "002750B",
            "wind_kmh": 11,
            "temperature_c": 29,
            "rain_hours": 3,
        })
        self.assertEqual(count, 1)
        self.assertTrue(filename.endswith("_ultimometro.zip"))
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            root = app.safe_parse_xml(archive.read("TASKDATA.XML"))
            comments = [node.attrib.get("C", "") for node in app.descendants(root, "CAN")]
            self.assertIn("UM HW T1200L V5-10 B400", comments)
            self.assertIn("UM ARAG TB400 R4679013", comments)
            self.assertIn("UM FLOW F46211P40000 V853T04A55", comments)
            self.assertIn("UM ACT A4063T95A0 P97055201", comments)
            self.assertIn("UM NOZ NAFC11002 F42433135", comments)
            self.assertIn("UM HOLD 002750B", comments)
            self.assertIn("UM WX GIALLA W11 T29 R3", comments)
            values = [app.attr(node, "B") for node in app.descendants(root, "PDV")]
            self.assertEqual(values, ["2500000", "1800000"])

    def test_repeated_export_updates_notes_without_duplicates(self):
        package, _, _ = app.api_export_package({"weather_status": "VERDE", "tank_l": 1200, "controller": "Bravo 400S"})
        # Load the prior export and submit it again: UM-prefixed comments should be updated in place.
        app.api_import_file(package, "first-export.zip")
        second, _, _ = app.api_export_package({"weather_status": "ROSSA", "tank_l": 1500, "controller": "Bravo 180S"})
        with zipfile.ZipFile(io.BytesIO(second)) as archive:
            root = app.safe_parse_xml(archive.read("TASKDATA.XML"))
            comments = [node.attrib.get("C", "") for node in app.descendants(root, "CAN")]
        self.assertEqual(len(comments), 8)
        self.assertIn("UM HW T1500L V5-10 B180", comments)
        self.assertTrue(any(note.startswith("UM WX ROSSA") for note in comments))
        self.assertIn("UM ARAG TB180 RND", comments)

    def test_reset_clears_current_package(self):
        result = app.api_reset()
        self.assertTrue(result["cleared"])
        self.assertIsNone(app.CURRENT_PACKAGE)

    def test_preserves_other_zip_payloads(self):
        current = app.CURRENT_PACKAGE
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in current["files"].items():
                archive.writestr(name, payload)
            archive.writestr("GRD00001.bin", b"demo-binary-grid-payload")
        app.api_import_file(data.getvalue(), "package-with-grid.zip")
        exported, _, _ = app.api_export_package({"weather_status": "VERDE"})
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            self.assertEqual(archive.read("GRD00001.bin"), b"demo-binary-grid-payload")

    def test_plain_xml_can_be_wrapped_as_iso_xml_zip(self):
        xml_bytes = (ROOT / "examples" / "TASKDATA_demo.xml").read_bytes()
        app.CURRENT_PACKAGE = app.load_package(xml_bytes, "TASKDATA_demo.xml")
        exported, _, _ = app.api_export_package({"weather_status": "VERDE"})
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            self.assertEqual(archive.namelist(), ["TASKDATA.XML"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
