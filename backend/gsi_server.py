import asyncio
import json
import mimetypes
import os
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import parse_qs, urlparse

from backend.analytics_engine import AnalyticsEngine
from backend.config_manager import ConfigManager

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

class AppState:
    def __init__(self):
        self.engine = AnalyticsEngine()
        self.selected_rank = "Archon"
        self.selected_role = "Carry"
        self.audio_enabled = True
        self.clickthrough = False
        self.manual_enemy_heroes: List[str] = []
        
        # Live state from GSI
        self.raw_gsi: Dict[str, Any] = {}
        self.last_update_ts = 0.0
        self.is_connected = False
        
        # Simulation
        self.simulation_running = False
        self.simulation_time = 0
        
        # Roshan tracking
        self.roshan_death_time: int | None = None
        self.last_roshan_state = "alive"
        
        # Cached analysis payload
        self.cached_analysis: Dict[str, Any] = self._generate_initial_state()
        self.subscribers: Set[Any] = set()
        self.subscribers_lock = threading.Lock()

    def _generate_initial_state(self) -> Dict[str, Any]:
        return {
            "connected": False,
            "status": "Ожидание запуска Dota 2...",
            "settings": {
                "rank": self.selected_rank,
                "role": self.selected_role,
                "audio": self.audio_enabled,
                "clickthrough": self.clickthrough,
                "manual_enemy_heroes": self.manual_enemy_heroes
            },
            "game_phase": "IDLE",
            "draft": self.engine.analyze_draft([], [], "radiant", self.selected_role),
            "performance": self.engine.evaluate_performance(
                clock_time=0,
                rank=self.selected_rank,
                role=self.selected_role,
                current_cs=0,
                current_denies=0,
                current_networth=600,
                current_gpm=0,
                current_xpm=0,
                current_gold=600,
                gold_unreliable=0,
                hero_alive=True
            ),
            "radar": self.engine.get_macro_timers(0, role=self.selected_role),
            "recommended_items": []
        }

    def process_gsi_payload(self, data: Dict[str, Any]):
        self.raw_gsi = data
        self.last_update_ts = time.time()
        self.is_connected = True

        map_data = data.get("map", {})
        player_data = data.get("player", {})
        hero_data = data.get("hero", {})
        draft_data = data.get("draft", {})
        items_data = data.get("items", {})

        game_state_str = map_data.get("game_state", "")
        clock_time = int(map_data.get("clock_time", 0))

        # Check Roshan State changes from GSI
        roshan_state = map_data.get("roshan_state", "alive")
        if roshan_state != "alive" and self.last_roshan_state == "alive" and clock_time > 0:
            self.engine.record_roshan_killed(clock_time)
        elif roshan_state == "alive" and self.last_roshan_state != "alive":
            self.engine.roshan_death_time = None
        self.last_roshan_state = roshan_state

        # Determine Game Phase
        if "HERO_SELECTION" in game_state_str or "STRATEGY_TIME" in game_state_str:
            phase = "DRAFT"
        elif "IN_PROGRESS" in game_state_str or "PRE_GAME" in game_state_str:
            phase = "IN_GAME"
        elif "POST_GAME" in game_state_str:
            phase = "POST_GAME"
        else:
            phase = "IDLE" if not game_state_str else "PRE_GAME"

        # Extract draft heroes from GSI
        radiant_heroes = []
        dire_heroes = []
        if draft_data:
            t2 = draft_data.get("team2", {})
            t3 = draft_data.get("team3", {})
            for k, v in t2.items():
                if "pick" in k and isinstance(v, dict) and "hero_id" in v:
                    radiant_heroes.append(v["hero_id"])
            for k, v in t3.items():
                if "pick" in k and isinstance(v, dict) and "hero_id" in v:
                    dire_heroes.append(v["hero_id"])

        user_team = player_data.get("team_name", "radiant").lower()

        # Enemy heroes: use manual overrides if set by user, otherwise use GSI draft
        if self.manual_enemy_heroes:
            effective_enemy_heroes = list(self.manual_enemy_heroes)
        else:
            effective_enemy_heroes = dire_heroes if user_team == "radiant" else radiant_heroes

        # Extract current player items and check for Aegis in slot0..slot5
        player_item_list = []
        has_aegis = False
        for slot in ["slot0", "slot1", "slot2", "slot3", "slot4", "slot5"]:
            item_info = items_data.get(slot)
            if item_info and isinstance(item_info, dict):
                iname = item_info.get("name")
                if iname and iname not in ["empty", "none"]:
                    player_item_list.append(iname)
                    if iname == "item_aegis":
                        has_aegis = True

        # Update hybrid Aegis tracker in engine
        self.engine.update_aegis_inventory(has_aegis, clock_time)

        # Compute draft analysis
        draft_rad = radiant_heroes if user_team == "radiant" else effective_enemy_heroes
        draft_dire = effective_enemy_heroes if user_team == "radiant" else dire_heroes
        draft_analysis = self.engine.analyze_draft(
            radiant_heroes=draft_rad,
            dire_heroes=draft_dire,
            user_team=user_team,
            target_role=self.selected_role
        )

        current_cs = int(player_data.get("last_hits", 0))
        current_denies = int(player_data.get("denies", 0))
        current_gold = int(player_data.get("gold", 0))
        gold_unreliable = int(player_data.get("gold_unreliable", 0))
        current_gpm = int(player_data.get("gpm", 0))
        current_xpm = int(player_data.get("xpm", 0))
        hero_alive = bool(hero_data.get("alive", True))

        bb_cost_raw = hero_data.get("buyback_cost")
        bb_cost = int(bb_cost_raw) if bb_cost_raw is not None else None
        bb_cd = int(hero_data.get("buyback_cooldown", 0))

        # Reconstruct net worth if missing in GSI:
        # formula: (hero.buyback_cost - 200) * 13
        net_worth = int(player_data.get("net_worth", 0))
        if net_worth == 0:
            if bb_cost is not None and bb_cost > 200:
                net_worth = max(0, int((bb_cost - 200) * 13))
            else:
                net_worth = current_gold + (current_cs * 45) + (current_gpm * (max(0, clock_time) // 60))

        performance_analysis = self.engine.evaluate_performance(
            clock_time=clock_time,
            rank=self.selected_rank,
            role=self.selected_role,
            current_cs=current_cs,
            current_denies=current_denies,
            current_networth=net_worth,
            current_gpm=current_gpm,
            current_xpm=current_xpm,
            current_gold=current_gold,
            gold_unreliable=gold_unreliable,
            hero_alive=hero_alive,
            hero_buyback_cost=bb_cost,
            buyback_cooldown=bb_cd
        )

        daytime = bool(map_data.get("daytime", True))
        radar_analysis = self.engine.get_macro_timers(
            clock_time=clock_time,
            daytime=daytime,
            role=self.selected_role
        )

        # Inventory inspection (neutral0, teleport0, backpack active items)
        inventory_alerts = self.engine.inspect_inventory(items_data, clock_time)
        radar_analysis["active_alerts"].extend(inventory_alerts)

        # Enemy power spikes (Ursa/Huskar @ 9:30, Blink @ 10:30, Orchid @ 14:30)
        power_spike_alerts = self.engine.check_power_spikes(clock_time, effective_enemy_heroes)
        radar_analysis["active_alerts"].extend(power_spike_alerts)

        item_advice = self.engine.recommend_items(
            enemy_heroes=effective_enemy_heroes,
            current_player_items=player_item_list
        )

        self.cached_analysis = {
            "connected": True,
            "status": "В игре" if phase == "IN_GAME" else ("Стадия драфта" if phase == "DRAFT" else "В лобби"),
            "settings": {
                "rank": self.selected_rank,
                "role": self.selected_role,
                "audio": self.audio_enabled,
                "clickthrough": self.clickthrough,
                "manual_enemy_heroes": self.manual_enemy_heroes
            },
            "game_phase": phase,
            "match_info": {
                "match_id": map_data.get("matchid", ""),
                "clock_time": clock_time,
                "clock_formatted": self.engine.format_clock(clock_time),
                "daytime": map_data.get("daytime", True),
                "radiant_score": map_data.get("radiant_score", 0),
                "dire_score": map_data.get("dire_score", 0),
                "user_team": user_team
            },
            "player": {
                "hero_name": hero_data.get("name", ""),
                "hero_level": hero_data.get("level", 1),
                "alive": hero_alive,
                "respawn_seconds": hero_data.get("respawn_seconds", 0),
                "health": hero_data.get("health", 0),
                "max_health": hero_data.get("max_health", 1),
                "mana": hero_data.get("mana", 0),
                "max_mana": hero_data.get("max_mana", 1),
                "kills": player_data.get("kills", 0),
                "deaths": player_data.get("deaths", 0),
                "assists": player_data.get("assists", 0),
                "gold": current_gold,
                "gold_unreliable": gold_unreliable,
                "net_worth": net_worth,
                "items": player_item_list
            },
            "draft": draft_analysis,
            "performance": performance_analysis,
            "radar": radar_analysis,
            "recommended_items": item_advice
        }

        self.notify_subscribers()

    def notify_subscribers(self):
        with self.subscribers_lock:
            dead_queues = []
            payload_str = json.dumps(self.cached_analysis)
            for q in self.subscribers:
                try:
                    q.put_nowait(payload_str)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                self.subscribers.remove(dq)

state = AppState()

class GSIHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if parsed.path == "/gsi":
            try:
                data = json.loads(body.decode("utf-8"))
                state.process_gsi_payload(data)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except Exception as e:
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        elif parsed.path == "/api/settings":
            try:
                data = json.loads(body.decode("utf-8"))
                if "rank" in data:
                    state.selected_rank = data["rank"]
                if "role" in data:
                    state.selected_role = data["role"]
                if "audio" in data:
                    state.audio_enabled = bool(data["audio"])
                if "clickthrough" in data:
                    state.clickthrough = bool(data["clickthrough"])
                if "manual_enemy_heroes" in data:
                    state.manual_enemy_heroes = [str(h) for h in data["manual_enemy_heroes"] if h]

                # Trigger refresh
                if state.raw_gsi:
                    state.process_gsi_payload(state.raw_gsi)
                else:
                    state.cached_analysis["settings"] = {
                        "rank": state.selected_rank,
                        "role": state.selected_role,
                        "audio": state.audio_enabled,
                        "clickthrough": state.clickthrough,
                        "manual_enemy_heroes": state.manual_enemy_heroes
                    }
                    # Also refresh item recommendations if idle
                    state.cached_analysis["recommended_items"] = state.engine.recommend_items(state.manual_enemy_heroes)
                    state.notify_subscribers()

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"updated"}')
            except Exception as e:
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        elif parsed.path == "/api/roshan_killed":
            try:
                clock_time = int(state.raw_gsi.get("map", {}).get("clock_time", 0)) if state.raw_gsi else 0
                res = state.engine.record_roshan_killed(clock_time)
                if state.raw_gsi:
                    state.process_gsi_payload(state.raw_gsi)
                else:
                    state.cached_analysis["radar"] = state.engine.get_macro_timers(clock_time, daytime=True, role=state.selected_role)
                    state.notify_subscribers()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "roshan_recorded", **res}).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        elif parsed.path == "/api/glyph_used":
            try:
                clock_time = int(state.raw_gsi.get("map", {}).get("clock_time", 0)) if state.raw_gsi else 0
                left = state.engine.record_glyph_used(clock_time)
                if state.raw_gsi:
                    state.process_gsi_payload(state.raw_gsi)
                else:
                    state.cached_analysis["radar"] = state.engine.get_macro_timers(clock_time, daytime=True, role=state.selected_role)
                    state.notify_subscribers()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "glyph_recorded", "seconds_left": left}).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        elif parsed.path == "/api/simulate":
            threading.Thread(target=run_simulation, daemon=True).start()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"simulation_started"}')
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/state":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(state.cached_analysis).encode("utf-8"))
            return

        elif parsed.path == "/api/heroes":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            heroes_list = [
                {
                    "id": h["id"],
                    "name": h["name"],
                    "display_name": h["display_name"],
                    "attr": h.get("attr", "str"),
                    "role": h.get("role", "Carry"),
                    "aliases": h.get("aliases", [])
                }
                for h in sorted(state.engine.heroes_data.values(), key=lambda x: x.get("display_name", ""))
            ]
            self.wfile.write(json.dumps(heroes_list, ensure_ascii=False).encode("utf-8"))
            return

        elif parsed.path == "/api/events":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            import queue
            q = queue.Queue(maxsize=30)
            with state.subscribers_lock:
                state.subscribers.add(q)

            initial_payload = json.dumps(state.cached_analysis)
            try:
                self.wfile.write(f"data: {initial_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                with state.subscribers_lock:
                    state.subscribers.discard(q)
                return

            try:
                while True:
                    try:
                        msg = q.get(timeout=15.0)
                        self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with state.subscribers_lock:
                    state.subscribers.discard(q)
            return

        if parsed.path == "/" or parsed.path == "":
            self.path = "/index.html"

        super().do_GET()


def run_simulation():
    """Simulates a realistic Dota 2 match progression with inventory checks."""
    if state.simulation_running:
        return
    state.simulation_running = True

    # 1. Draft Phase simulation
    state.process_gsi_payload({
        "map": { "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION", "clock_time": -30, "radiant_score": 0, "dire_score": 0 },
        "player": { "team_name": "radiant", "last_hits": 0, "denies": 0, "gold": 600, "gold_unreliable": 500, "gpm": 0, "xpm": 0 },
        "draft": {
            "team2": { "pick0": { "hero_id": 8 }, "pick1": { "hero_id": 5 } },
            "team3": { "pick0": { "hero_id": 99 }, "pick1": { "hero_id": 44 }, "pick2": { "hero_id": 10 } }
        }
    })
    time.sleep(2)

    # 2. In-Game Phase: 2:45, 6:45, 9:55, 17:15
    simulated_seconds = [165, 405, 595, 1035]
    
    for s in simulated_seconds:
        m = s // 60
        cs = int(m * 7.5 + 4)
        nw = int(600 + (m * 460))
        gold = 1350 + (m * 60)
        gold_unreliable = int(gold * 0.7)
        
        state.process_gsi_payload({
            "map": {
                "matchid": "7812984510",
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "clock_time": s,
                "daytime": ((s // 300) % 2) == 0,
                "radiant_score": 5 + (m // 2),
                "dire_score": 3 + (m // 3),
                "roshan_state": "alive"
            },
            "player": {
                "team_name": "radiant",
                "kills": 2 + (m // 5),
                "deaths": 1,
                "assists": 3 + (m // 3),
                "last_hits": cs,
                "denies": 6 + (m // 2),
                "gold": gold,
                "gold_unreliable": gold_unreliable,
                "net_worth": nw,
                "gpm": 510,
                "xpm": 540
            },
            "hero": {
                "name": "npc_dota_hero_antimage",
                "level": max(1, m + 1),
                "alive": True,
                "respawn_seconds": 0,
                "health": 1150,
                "max_health": 1250,
                "mana": 480,
                "max_mana": 600,
                "buyback_cost": int(200 + (nw / 13)),
                "buyback_cooldown": 0
            },
            "items": {
                "slot0": { "name": "item_power_treads" },
                "slot1": { "name": "item_bfury" },
                "slot2": { "name": "item_branches" }, # free/cheap slot
                "slot3": { "name": "empty" },
                "slot4": { "name": "empty" },
                "slot5": { "name": "empty" },
                "slot6": { "name": "item_manta", "cooldown": 0 }, # active item in backpack!
                "teleport0": { "name": "empty", "charges": 0 }, # missing TP after 4:00
                "neutral0": { "name": "empty" } # missing neutral item after 7:00
            },
            "draft": {
                "team2": { "pick0": { "hero_id": 1 }, "pick1": { "hero_id": 5 } },
                "team3": { "pick0": { "hero_id": 99 }, "pick1": { "hero_id": 44 } }
            }
        })
        time.sleep(2.5)

    state.simulation_running = False

def start_server(port: int = 3000):
    server = ThreadingHTTPServer(("0.0.0.0", port), GSIHTTPRequestHandler)
    print(f"[AegisPlus] Сервер запущен на http://127.0.0.1:{port}")
    server.serve_forever()

if __name__ == "__main__":
    start_server(3000)
