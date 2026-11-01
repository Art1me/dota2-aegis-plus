import json
import unittest
from backend.analytics_engine import AnalyticsEngine
from backend.gsi_server import AppState

class TestPhase2Features(unittest.TestCase):
    def setUp(self):
        self.engine = AnalyticsEngine()

    def test_roshan_manual_record(self):
        # Roshan killed at 15:00 (900s)
        clock_time = 900
        res = self.engine.record_roshan_killed(clock_time)
        
        self.assertEqual(res["roshan_death_time"], 900)
        self.assertEqual(res["aegis_end"], 1200) # 20:00
        self.assertEqual(res["rosh_min"], 1380) # 23:00
        self.assertEqual(res["rosh_max"], 1560) # 26:00
        self.assertEqual(res["chat_string"], "20:00 Aegis | 23:00 - 26:00 Roshan")

        # Test daytime pit location (Day -> Radiant/Bottom)
        timers_day = self.engine.get_macro_timers(clock_time=950, daytime=True, role="Carry")
        rosh_day = timers_day["roshan"]
        self.assertEqual(rosh_day["status"], "respawning")
        self.assertEqual(rosh_day["aegis_left"], 250)
        self.assertFalse(rosh_day["aegis_expired"])
        self.assertIn("Нижнее логово (Radiant)", rosh_day["pit_location"])

        # Test nighttime pit location (Night -> Dire/Top)
        timers_night = self.engine.get_macro_timers(clock_time=1000, daytime=False, role="Carry")
        self.assertIn("Верхнее логово (Dire)", timers_night["roshan"]["pit_location"])

        # Test Aegis 30s alert (clock_time = 1175 -> 25s left)
        timers_warn = self.engine.get_macro_timers(clock_time=1175, daytime=False, role="Carry")
        alert_ids = [a["id"] for a in timers_warn["active_alerts"]]
        self.assertIn("aegis_warn_30", alert_ids)

        # Test Aegis 10s alert (clock_time = 1195 -> 5s left)
        timers_crit = self.engine.get_macro_timers(clock_time=1195, daytime=False, role="Carry")
        alert_ids_crit = [a["id"] for a in timers_crit["active_alerts"]]
        self.assertIn("aegis_warn_10", alert_ids_crit)

        # Test Roshan in respawn window (480s to 660s: clock_time = 1400 -> elapsed = 500)
        timers_window = self.engine.get_macro_timers(clock_time=1400, daytime=False, role="Carry")
        rosh_win = timers_window["roshan"]
        self.assertEqual(rosh_win["status"], "in_window")
        self.assertEqual(rosh_win["aegis_left"], 0)
        win_alert_ids = [a["id"] for a in timers_window["active_alerts"]]
        self.assertIn("roshan_window_alert", win_alert_ids)

        # Test Roshan respawn passed (> 660s: clock_time = 1600 -> elapsed = 700)
        timers_alive = self.engine.get_macro_timers(clock_time=1600, daytime=False, role="Carry")
        self.assertEqual(timers_alive["roshan"]["status"], "alive")
        self.assertEqual(timers_alive["roshan"]["window"], "Жив")

    def test_aegis_auto_detection_and_early_expiry(self):
        # 1. Hero picks up Aegis at 12:00 (720s)
        self.engine.update_aegis_inventory(has_aegis=True, clock_time=720)
        self.assertEqual(self.engine.roshan_death_time, 720)
        self.assertEqual(self.engine.aegis_start_time, 720)
        self.assertFalse(self.engine.aegis_expired)

        # 2. Hero loses Aegis (died / popped) at 14:00 (840s, 120s later)
        self.engine.update_aegis_inventory(has_aegis=False, clock_time=840)
        self.assertTrue(self.engine.aegis_expired)

        # 3. get_macro_timers should show aegis_left = 0
        timers = self.engine.get_macro_timers(clock_time=845, daytime=True)
        self.assertEqual(timers["roshan"]["aegis_left"], 0)
        self.assertTrue(timers["roshan"]["aegis_expired"])

    def test_glyph_cooldown(self):
        # Enemy used glyph at 10:00 (600s)
        self.engine.record_glyph_used(clock_time=600)

        # Check at 12:00 (720s, 120s elapsed -> 180s left)
        timers = self.engine.get_macro_timers(clock_time=720, daytime=True)
        glyph = timers["glyph"]
        self.assertTrue(glyph["is_on_cooldown"])
        self.assertEqual(glyph["seconds_left"], 180)
        self.assertEqual(glyph["status"], "03:00")

        # Check at 15:05 (905s, 305s elapsed -> ready)
        timers_ready = self.engine.get_macro_timers(clock_time=905, daytime=True)
        glyph_ready = timers_ready["glyph"]
        self.assertFalse(glyph_ready["is_on_cooldown"])
        self.assertEqual(glyph_ready["seconds_left"], 0)
        self.assertEqual(glyph_ready["status"], "Готов")

    def test_power_spikes(self):
        # Test Ursa / Early Roshan spike at 09:30 (570s)
        spikes_rosh = self.engine.check_power_spikes(clock_time=570, enemy_heroes=["Ursa", "Crystal Maiden"])
        self.assertTrue(any(s["id"] == "spike_early_rosh" for s in spikes_rosh))

        # Test Axe / Blink Dagger spike at 10:30 (630s)
        spikes_blink = self.engine.check_power_spikes(clock_time=630, enemy_heroes=["Axe", "Lion"])
        self.assertTrue(any(s["id"] == "spike_blink_dagger" for s in spikes_blink))

        # Test Storm Spirit / Orchid spike at 14:30 (870s)
        spikes_orchid = self.engine.check_power_spikes(clock_time=870, enemy_heroes=["Storm Spirit", "Snapfire"])
        self.assertTrue(any(s["id"] == "spike_orchid_gank" for s in spikes_orchid))

        # Irrelevant heroes should not trigger
        no_spikes = self.engine.check_power_spikes(clock_time=570, enemy_heroes=["Sniper", "Dazzle"])
        self.assertEqual(len(no_spikes), 0)

    def test_rolling_gpm_and_tempo(self):
        # Simulate net worth progression
        # Target for Archon Carry at 10 min is ~4500 nw, target gpm ~450
        # At 7 min (420s): nw = 2800
        self.engine.evaluate_performance(
            clock_time=420, rank="Archon", role="Carry",
            current_cs=40, current_denies=5, current_networth=2800,
            current_gpm=400, current_xpm=420, current_gold=500,
            gold_unreliable=300, hero_alive=True
        )

        # At 10 min (600s): nw = 5200 (gained 2400 NW in 180s = 800 GPM!)
        res = self.engine.evaluate_performance(
            clock_time=600, rank="Archon", role="Carry",
            current_cs=75, current_denies=10, current_networth=5200,
            current_gpm=520, current_xpm=550, current_gold=1200,
            gold_unreliable=400, hero_alive=True
        )

        benchmarks = res["benchmarks"]
        self.assertEqual(benchmarks["rolling_gpm"], 800) # (5200 - 2800) / 3 = 800
        self.assertTrue(benchmarks["is_high_tempo"]) # 800 > target_gpm (~460)

    def test_app_state_integration(self):
        app = AppState()
        # Feed GSI data with Aegis in slot0
        gsi_data = {
            "map": {
                "matchid": "99999",
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "clock_time": 900,
                "daytime": True
            },
            "player": {
                "team_name": "radiant",
                "gold": 2500,
                "gold_unreliable": 800,
                "last_hits": 90,
                "denies": 8,
                "gpm": 550,
                "xpm": 580,
                "net_worth": 6500
            },
            "hero": {
                "name": "npc_dota_hero_juggernaut",
                "alive": True,
                "buyback_cost": 700,
                "buyback_cooldown": 0
            },
            "items": {
                "slot0": { "name": "item_aegis" },
                "slot1": { "name": "item_manta" },
                "slot2": { "name": "item_phase_boots" },
                "slot3": { "name": "empty" },
                "slot4": { "name": "empty" },
                "slot5": { "name": "empty" },
                "neutral0": { "name": "item_broom_handle" },
                "teleport0": { "name": "item_tpscroll", "charges": 1 }
            }
        }
        app.process_gsi_payload(gsi_data)

        # Check radar state
        radar = app.cached_analysis["radar"]
        self.assertIsNotNone(radar["roshan"])
        self.assertEqual(radar["roshan"]["status"], "respawning")
        self.assertEqual(radar["roshan"]["aegis_left"], 300)
        self.assertIn("20:00 Aegis", radar["roshan"]["chat_string"])

    def test_http_api_endpoints(self):
        import http.client
        import threading
        from backend.gsi_server import GSIHTTPRequestHandler, ThreadingHTTPServer

        # Start temporary server on dynamic port
        server = ThreadingHTTPServer(("127.0.0.1", 0), GSIHTTPRequestHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            
            # 1. POST /api/roshan_killed
            conn.request("POST", "/api/roshan_killed", body=b"{}")
            res = conn.getresponse()
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode())
            self.assertEqual(data["status"], "roshan_recorded")
            self.assertIn("chat_string", data)

            # 2. POST /api/glyph_used
            conn.request("POST", "/api/glyph_used", body=b"{}")
            res_glyph = conn.getresponse()
            self.assertEqual(res_glyph.status, 200)
            data_glyph = json.loads(res_glyph.read().decode())
            self.assertEqual(data_glyph["status"], "glyph_recorded")
            self.assertEqual(data_glyph["seconds_left"], 300)

            # 3. GET /api/state
            conn.request("GET", "/api/state")
            res_state = conn.getresponse()
            self.assertEqual(res_state.status, 200)
            state_data = json.loads(res_state.read().decode())
            self.assertIn("radar", state_data)
            self.assertIn("roshan", state_data["radar"])
            self.assertIn("glyph", state_data["radar"])
            self.assertTrue(state_data["radar"]["glyph"]["is_on_cooldown"])

            conn.close()
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main()
