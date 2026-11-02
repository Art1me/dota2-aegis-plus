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

    def test_distinct_hero_builds(self):
        # 2 completely different heroes must have distinct builds
        am = self.engine.get_item_progression("antimage", "Carry")
        axe = self.engine.get_item_progression("axe", "Offlane")
        cm = self.engine.get_item_progression("crystal_maiden", "Support")

        am_core_ids = [it["id"] for it in am["core"]]
        axe_core_ids = [it["id"] for it in axe["core"]]
        cm_core_ids = [it["id"] for it in cm["core"]]

        self.assertIn("item_bfury", am_core_ids)
        self.assertNotIn("item_bfury", axe_core_ids)
        self.assertIn("item_blink", axe_core_ids)
        self.assertIn("item_glimmer_cape", cm_core_ids)
        self.assertNotEqual(am_core_ids, axe_core_ids)
        self.assertNotEqual(axe_core_ids, cm_core_ids)

    def test_dynamic_next_recommended_item(self):
        # 1. Early game AM with 1200 gold should recommend Power Treads slot
        res1 = self.engine.get_next_recommended_item(
            hero_identifier="antimage",
            role="Carry",
            current_gold=1200,
            current_inventory=[],
            clock_time=200,
            enemy_heroes=[],
            current_gpm=500
        )
        self.assertEqual(res1["id"], "item_power_treads")
        self.assertEqual(res1["stage_label"], "Ранняя игра")
        self.assertEqual(res1["gold_needed"], 200)
        self.assertIn("скорость атаки", res1["reason"])

        # 2. Mid game AM with completed early items should recommend Battle Fury slot
        res2 = self.engine.get_next_recommended_item(
            hero_identifier="antimage",
            role="Carry",
            current_gold=1350,
            current_inventory=["item_power_treads", "item_wraith_band", "item_magic_wand"],
            clock_time=480,
            enemy_heroes=[],
            current_gpm=600
        )
        self.assertEqual(res2["id"], "item_bfury")
        self.assertEqual(res2["stage_label"], "Ядро")
        self.assertGreater(res2["gold_needed"], 0)
        self.assertIn("ускорение фарма", res2["reason"])

        # 3. Urgent BKB against heavy magic burst enemies
        res3 = self.engine.get_next_recommended_item(
            hero_identifier="antimage",
            role="Carry",
            current_gold=1100,
            current_inventory=["item_power_treads", "item_bfury"],
            clock_time=900,
            enemy_heroes=["npc_dota_hero_lina", "npc_dota_hero_lion", "npc_dota_hero_zeus"],
            current_gpm=650
        )
        self.assertEqual(res3["id"], "item_black_king_bar")
        self.assertEqual(res3["urgency"], "urgent")
        self.assertIn("маг. урона", res3["reason"])

    def test_dynamic_game_phases(self):
        # 3 min (180s) -> Water runes active
        p_water = self.engine.get_game_phase(180)
        self.assertEqual(p_water["phase"], "laning")
        self.assertTrue(p_water["show_cs"])
        self.assertTrue(p_water["show_water_runes"])
        self.assertTrue(p_water["allow_camp_stacks"])

        # 6 min (360s) -> Water runes expired, still laning
        p_laning = self.engine.get_game_phase(360)
        self.assertEqual(p_laning["phase"], "laning")
        self.assertTrue(p_laning["show_cs"])
        self.assertFalse(p_laning["show_water_runes"])
        self.assertTrue(p_laning["allow_camp_stacks"])

        # 15 min (900s) -> Midgame
        p_mid = self.engine.get_game_phase(900)
        self.assertEqual(p_mid["phase"], "midgame")
        self.assertFalse(p_mid["show_cs"])
        self.assertFalse(p_mid["show_water_runes"])
        self.assertTrue(p_mid["allow_camp_stacks"])

        # 25 min (1500s) -> Late game
        p_late = self.engine.get_game_phase(1500)
        self.assertEqual(p_late["phase"], "late")
        self.assertFalse(p_late["show_cs"])
        self.assertFalse(p_late["show_water_runes"])
        self.assertFalse(p_late["allow_camp_stacks"])

    def test_big_ultimates_tracker(self):
        enemies = ["npc_dota_hero_enigma", "npc_dota_hero_tidehunter", "npc_dota_hero_sniper"]
        tracked = self.engine.get_tracked_ultimates(enemies, 600)
        self.assertEqual(len(tracked), 2)
        hero_names = [t["hero"] for t in tracked]
        self.assertIn("Enigma", hero_names)
        self.assertIn("Tidehunter", hero_names)

        # Record Tidehunter Ravage used at 600s (cd 150s)
        res = self.engine.record_ultimate_used("npc_dota_hero_tidehunter", 600)
        self.assertIsNotNone(res)
        self.assertEqual(res["cooldown"], 150)
        self.assertEqual(res["ready_time"], 750)

        # Check status at 650s (should be on cooldown, 100s remaining)
        tracked_650 = self.engine.get_tracked_ultimates(enemies, 650)
        tide_meta = next(t for t in tracked_650 if t["hero"] == "Tidehunter")
        self.assertTrue(tide_meta["on_cooldown"])
        self.assertEqual(tide_meta["remaining_seconds"], 100)

        # Check status at 760s (should be ready)
        tracked_760 = self.engine.get_tracked_ultimates(enemies, 760)
        tide_ready = next(t for t in tracked_760 if t["hero"] == "Tidehunter")
        self.assertFalse(tide_ready["on_cooldown"])

    def test_late_game_buyback_danger_banner(self):
        # Late game (clock_time = 1800s, 30 min) with buyback deficit
        perf = self.engine.evaluate_performance(
            clock_time=1800,
            rank="Archon",
            role="Carry",
            current_cs=250,
            current_denies=15,
            current_networth=16000,
            current_gpm=600,
            current_xpm=650,
            current_gold=100, # Only 100g, buyback costs 1000+
            current_kills=5,
            current_deaths=2,
            current_assists=7
        )
        bb = perf["buyback"]
        danger = bb["danger_banner"]
        self.assertTrue(danger["is_danger"])
        self.assertIn("ОПАСНОСТЬ", danger["text"])
        self.assertIn("байбек", danger["tts"])

    def test_ability_priority_and_talent_popover(self):
        # Level 10 should show talent popover
        build_lvl10 = self.engine.get_ability_build("npc_dota_hero_juggernaut", hero_level=10)
        self.assertIn("skill_priority", build_lvl10)
        self.assertTrue(build_lvl10["show_talent"])
        self.assertEqual(build_lvl10["active_tier"], 10)
        self.assertIsNotNone(build_lvl10["active_talent"])

        # Level 5 should NOT show talent popover
        build_lvl5 = self.engine.get_ability_build("npc_dota_hero_juggernaut", hero_level=5)
        self.assertFalse(build_lvl5["show_talent"])
        self.assertIsNone(build_lvl5["active_talent"])

if __name__ == "__main__":
    unittest.main()
