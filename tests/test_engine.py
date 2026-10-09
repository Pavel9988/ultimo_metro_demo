import unittest

from tests.helpers import BARE, FULL, VALVE_ONLY
from um.engine import ClassIn, evaluate, kpis, plan_rate, q_required, specialise, suggest
from um.hardware import HwConfig, load_catalog, resolve_chain

CAT = load_catalog()


def setup(d, **kw):
    cfg = HwConfig.from_dict({**d, **kw})
    return cfg, resolve_chain(cfg, CAT)


class Hydraulics(unittest.TestCase):
    def test_required_flow_formula(self):
        # 200 L/ha a 8 km/h con 0,5 m: 200*8*0,5/600 = 1,3333 L/min per ugello
        self.assertAlmostEqual(q_required(200, 8, 0.5), 1.3333, places=3)

    def test_reachable_rate_is_ok_at_nominal_speed(self):
        cfg, ch = setup(FULL)
        p = plan_rate(150, cfg, ch, CAT)
        self.assertEqual(p.status, "ok")
        self.assertAlmostEqual(p.delivered, 150, delta=150 * 0.05)
        self.assertEqual(p.speed, 8)

    def test_too_high_rate_is_underdosed_with_exact_ceiling(self):
        cfg, ch = setup(FULL)
        p = plan_rate(340, cfg, ch, CAT)
        self.assertEqual(p.status, "under")
        # al massimo: portata max dell'ugello alla velocità minima
        n = ch.nozzles[0]
        qmax = n.flow(ch.window(n)[1])
        self.assertAlmostEqual(p.delivered, qmax * 600 / (cfg.speed_min * cfg.spacing), delta=1.0)
        self.assertLess(p.delivered, 340)

    def test_speed_adaptation_can_be_disabled(self):
        cfg, ch = setup(FULL, allow_speed_adapt=False)
        p = plan_rate(220, cfg, ch, CAT)           # oltre 196 L/ha a 8 km/h
        self.assertEqual(p.status, "under")
        cfg2, ch2 = setup(FULL, allow_speed_adapt=True)
        self.assertEqual(plan_rate(220, cfg2, ch2, CAT).status, "adapt")

    def test_second_nozzle_via_seletron_reaches_high_rate(self):
        cfg, ch = setup(FULL, nozzles=["AFC11002", "AFC11006"])
        p = plan_rate(340, cfg, ch, CAT)
        self.assertIn(p.status, ("ok", "adapt"))
        self.assertEqual(p.nozzle, "AFC11006")
        self.assertIn("switch", p.flags)

    def test_low_rate_below_range_is_overdosed_without_pwm(self):
        cfg, ch = setup(VALVE_ONLY, nozzles=["WRC110025"])
        self.assertFalse(ch.pwm)
        p = plan_rate(20, cfg, ch, CAT)
        self.assertEqual(p.status, "over")
        self.assertGreater(p.delivered, 20)

    def test_pwm_reaches_lower_rate_than_pressure_only(self):
        full_cfg, full_ch = setup(FULL, nozzles=["WRC110025"])
        v_cfg, v_ch = setup(VALVE_ONLY)
        low = 40
        self.assertEqual(plan_rate(low, full_cfg, full_ch, CAT).status in ("ok", "adapt"), True)
        self.assertEqual(plan_rate(low, v_cfg, v_ch, CAT).status in ("over",), True)

    def test_zero_rate_is_off(self):
        cfg, ch = setup(FULL)
        self.assertEqual(plan_rate(0, cfg, ch, CAT).status, "off")


class Chains(unittest.TestCase):
    def test_full_chain_is_vra_pwm(self):
        _, ch = setup(FULL)
        self.assertTrue(ch.vra and ch.pwm and not ch.blockers)

    def test_terminal_without_task_controller_blocks(self):
        _, ch = setup(FULL, terminal="4674L0701")
        self.assertTrue(any("Task Controller" in b for b in ch.blockers))

    def test_ibx_terminal_needs_ibx_unit(self):
        _, ch = setup({**BARE, "terminal": "4675204"})
        self.assertTrue(any("IBX" in b for b in ch.blockers))

    def test_no_nozzle_blocks(self):
        _, ch = setup(FULL, nozzles=[])
        self.assertTrue(any("ugello" in b.lower() for b in ch.blockers))

    def test_bare_terminal_cannot_do_variable_rate(self):
        cfg, ch = setup(BARE)
        self.assertFalse(ch.vra)
        cin = [ClassIn(0, 100, 5.0), ClassIn(1, 200, 5.0)]
        plans = evaluate(cin, cfg, ch, CAT, variable_file=True)
        self.assertTrue(all(p.status == "novra" for p in plans))
        spec = specialise(cin, plans, cfg, ch, CAT)
        self.assertEqual(spec.strategy, "uniform")
        self.assertAlmostEqual(spec.uniform_rate, 150, delta=2)      # media pesata per area

    def test_more_nozzles_than_ways_warns(self):
        _, ch = setup({**FULL, "actuator": "4063T1400"}, nozzles=["AFC11002", "AFC11004", "AFC11006"])
        self.assertTrue(any("vie" in w for w in ch.warnings))
        self.assertEqual(len(ch.nozzles), 2)


class Specialisation(unittest.TestCase):
    def test_only_unreachable_classes_are_rewritten(self):
        cfg, ch = setup(FULL)
        cin = [ClassIn(0, 150, 3.0), ClassIn(1, 220, 3.0), ClassIn(2, 340, 1.0)]
        plans = evaluate(cin, cfg, ch, CAT, variable_file=True)
        spec = specialise(cin, plans, cfg, ch, CAT)
        self.assertEqual(spec.strategy, "variable")
        self.assertEqual(spec.changed, [2])
        self.assertLess(spec.new_rate[2], 340)
        # dopo la specializzazione tutto è eseguibile
        self.assertEqual(spec.kpi_after["on_target_pct"], 100.0)
        self.assertLess(kpis(cin, plans)["on_target_pct"], 100.0)

    def test_nothing_to_rewrite_when_all_reachable(self):
        cfg, ch = setup(FULL, nozzles=["AFC11005"])
        cin = [ClassIn(0, 150, 3.0), ClassIn(1, 300, 3.0)]
        plans = evaluate(cin, cfg, ch, CAT, variable_file=True)
        self.assertEqual(specialise(cin, plans, cfg, ch, CAT).changed, [])

    def test_forced_uniform_preserves_volume(self):
        cfg, ch = setup(FULL, strategy="uniform")
        cin = [ClassIn(0, 150, 3.0), ClassIn(1, 250, 1.0)]
        plans = evaluate(cin, cfg, ch, CAT, variable_file=True)
        spec = specialise(cin, plans, cfg, ch, CAT)
        self.assertEqual(spec.strategy, "uniform")
        self.assertAlmostEqual(spec.uniform_rate, (150 * 3 + 250 * 1) / 4, delta=1)

    def test_suggestions_improve_coverage(self):
        cfg, ch = setup(FULL)
        cin = [ClassIn(0, 150, 3.0), ClassIn(1, 340, 3.0)]
        s = suggest(cin, cfg, ch, CAT)
        self.assertGreater(s["singles"][0]["on_target_pct"], s["current"]["on_target_pct"])


if __name__ == "__main__":
    unittest.main()
