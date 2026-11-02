import unittest
from backend.analytics_engine import AnalyticsEngine

class TestDotaPlusFeatures(unittest.TestCase):
    def setUp(self):
        self.engine = AnalyticsEngine()

    def test_damage_breakdown_physical(self):
        # Enemy draft with heavy physical right-clickers
        enemies = ["npc_dota_hero_phantom_assassin", "npc_dota_hero_slardar", "npc_dota_hero_sven"]
        res = self.engine.calculate_damage_breakdown(enemies)
        self.assertIn("physical_pct", res)
        self.assertIn("magical_pct", res)
        self.assertIn("pure_pct", res)
        self.assertGreaterEqual(res["physical_pct"], 50)
        self.assertEqual(res["primary_threat"], "physical")
        self.assertIn("Shiva's Guard", res["advice"])

    def test_damage_breakdown_pure(self):
        # Enemy with pure damage (Axe)
        enemies = ["npc_dota_hero_axe", "npc_dota_hero_tinker"]
        res = self.engine.calculate_damage_breakdown(enemies)
        self.assertGreaterEqual(res["pure_pct"], 18)
        self.assertEqual(res["primary_threat"], "pure")
        self.assertIn("чистый урон", res["advice"])

    def test_item_progression_structure(self):
        build = self.engine.get_item_progression("npc_dota_hero_antimage", "Carry")
        self.assertIn("starting", build)
        self.assertIn("early_game", build)
        self.assertIn("core", build)
        self.assertIn("luxury", build)
        
        # Check starting items have images and names
        starting = build["starting"]
        self.assertGreater(len(starting), 0)
        for it in starting:
            self.assertIn("id", it)
            self.assertIn("name", it)
            self.assertTrue(it["image_url"].startswith("https://cdn.cloudflare.steamstatic.com"))

    def test_ability_and_talent_build(self):
        build = self.engine.get_ability_build("npc_dota_hero_axe")
        self.assertEqual(build["hero_name"], "npc_dota_hero_axe")
        self.assertGreaterEqual(len(build["sequence"]), 16)
        
        talents = build["talents"]
        for lvl in [10, 15, 20, 25]:
            self.assertIn(lvl, talents)
            t = talents[lvl]
            self.assertIn(t["recommended"], ["left", "right"])
            self.assertIn("winrate", t)

    def test_camp_stack_and_tormentor_timers(self):
        # At 53 seconds, camp stack alert should trigger
        radar_53 = self.engine.get_macro_timers(53)
        alerts_53 = [a["id"] for a in radar_53["active_alerts"]]
        self.assertIn("stack_camps", alerts_53)

        # Before 20:00 (e.g. 600s), tormentor timer should be present
        radar_600 = self.engine.get_macro_timers(600)
        timer_ids = [t["id"] for t in radar_600["timers"]]
        self.assertIn("tormentor", timer_ids)

    def test_kda_benchmarks_and_arrows(self):
        # Minute 15 Carry test: kills=4, deaths=0, assists=3
        perf = self.engine.evaluate_performance(
            clock_time=900,
            rank="Archon",
            role="Carry",
            current_cs=120,
            current_denies=12,
            current_networth=8000,
            current_gpm=550,
            current_xpm=580,
            current_gold=1200,
            current_kills=4,
            current_deaths=0,
            current_assists=3
        )
        b = perf["benchmarks"]
        self.assertIn("current_kda", b)
        self.assertIn("target_kda", b)
        self.assertEqual(b["kda_status"], "ahead")
        self.assertEqual(b["kda_arrow"], "▲")
        self.assertEqual(b["deaths_status"], "ahead")
        self.assertEqual(b["deaths_arrow"], "▲")
        self.assertEqual(b["cs_arrow"], "▲")
        self.assertEqual(b["nw_arrow"], "▲")
        self.assertEqual(b["plan_status"], "ahead")
        self.assertGreaterEqual(b["ahead_count"], 3)

if __name__ == "__main__":
    unittest.main()
