import asyncio
import json
import mimetypes
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

# Ensure project root is in sys.path regardless of execution directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from gi.repository import GLib

from backend.analytics_engine import AnalyticsEngine
from backend.config_manager import ConfigManager
from backend.qr_generator import SimpleQRCode

def get_local_ips() -> List[str]:
    ips = set()
    # 1. Subprocess hostname -I
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True, timeout=1).strip().split()
        for ip in out:
            if not ip.startswith("127.") and not ip.startswith("172.17.") and ":" not in ip:
                ips.add(ip)
    except Exception:
        pass

    # 2. UDP routing probe
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        cand = s.getsockname()[0]
        s.close()
        if not cand.startswith("127."):
            ips.add(cand)
    except Exception:
        pass

    # 3. ip route
    try:
        out = subprocess.check_output(["ip", "route", "get", "1.1.1.1"], text=True, timeout=1)
        for part in out.split():
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", part) and not part.startswith("127."):
                ips.add(part)
    except Exception:
        pass

    return list(ips) or ["127.0.0.1"]

def get_local_ip() -> str:
    return get_local_ips()[0]



FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

overlay_app = None

def set_overlay_app(app):
    global overlay_app
    overlay_app = app


class AppState:
    def __init__(self):
        self.engine = AnalyticsEngine()
        self.selected_rank = "Archon"
        self.selected_role = "Carry"
        self.audio_enabled = True
        self.clickthrough = False
        self.overlay_open = True
        self.should_quit = False
        self.manual_enemy_heroes: List[str] = []
        
        # Live state from GSI
        self.raw_gsi: Dict[str, Any] = {}
        self.last_update_ts = 0.0
        self.is_connected = False
        self._first_packet_logged = False
        
        # Simulation
        self.simulation_running = False
        self.simulation_time = 0
        
        # Roshan tracking
        self.roshan_death_time: Optional[int] = None
        self.last_roshan_state = "alive"

        # Net worth timeline history for Dota Plus progress graph
        self.timeline_history: List[Dict[str, Any]] = []
        self.last_recorded_minute: int = -1
        
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
            "recommended_items": [],
            "damage_breakdown": self.engine.calculate_damage_breakdown(self.manual_enemy_heroes),
            "item_build": self.engine.get_item_progression("npc_dota_hero_juggernaut", self.selected_role),
            "ability_build": self.engine.get_ability_build("npc_dota_hero_juggernaut", hero_level=1),
            "next_item": self.engine.get_next_recommended_item(
                "npc_dota_hero_juggernaut",
                self.selected_role,
                current_gold=600,
                current_inventory=[],
                clock_time=0,
                enemy_heroes=self.manual_enemy_heroes,
                current_gpm=0
            ),
            "dynamic_phase": self.engine.get_game_phase(0),
            "tracked_ultimates": self.engine.get_tracked_ultimates(self.manual_enemy_heroes, 0),
            "stack_alerts_midgame_enabled": self.engine.stack_alerts_enabled_midgame,
            "nw_history": []
        }

    def process_gsi_payload(self, data: Dict[str, Any]):
        if not isinstance(data, dict):
            return

        self.raw_gsi = data
        self.last_update_ts = time.time()
        self.is_connected = True

        map_data = data.get("map") or {}
        player_data = data.get("player") or {}
        hero_data = data.get("hero") or {}
        draft_data = data.get("draft") or {}
        items_data = data.get("items") or {}

        game_state_str = str(map_data.get("game_state", ""))
        try:
            clock_time = int(map_data.get("clock_time", 0) or 0)
        except (ValueError, TypeError):
            clock_time = 0

        # Check Roshan State changes from GSI
        roshan_state = str(map_data.get("roshan_state", "alive") or "alive")
        if roshan_state != "alive" and self.last_roshan_state == "alive" and clock_time > 0:
            self.engine.record_roshan_killed(clock_time)
        elif roshan_state == "alive" and self.last_roshan_state != "alive":
            self.engine.roshan_death_time = None
        self.last_roshan_state = roshan_state

        # Determine Game Phase (handle matchmaking, lobby and bot matches)
        if "HERO_SELECTION" in game_state_str or "STRATEGY_TIME" in game_state_str:
            phase = "DRAFT"
        elif "IN_PROGRESS" in game_state_str or "PRE_GAME" in game_state_str:
            phase = "IN_GAME"
        elif "POST_GAME" in game_state_str:
            phase = "POST_GAME"
        else:
            phase = "IDLE" if not game_state_str else "PRE_GAME"

        # Extract draft heroes from GSI
        radiant_heroes: List[Any] = []
        dire_heroes: List[Any] = []
        if isinstance(draft_data, dict):
            t2 = draft_data.get("team2") or {}
            t3 = draft_data.get("team3") or {}
            if isinstance(t2, dict):
                for k, v in t2.items():
                    if "pick" in k and isinstance(v, dict) and "hero_id" in v:
                        radiant_heroes.append(v["hero_id"])
            if isinstance(t3, dict):
                for k, v in t3.items():
                    if "pick" in k and isinstance(v, dict) and "hero_id" in v:
                        dire_heroes.append(v["hero_id"])

        raw_team = str(player_data.get("team_name", "radiant") or "radiant").lower()
        if "dire" in raw_team or "team3" in raw_team:
            user_team = "dire"
        else:
            user_team = "radiant"

        # Enemy heroes: use manual overrides if set by user, otherwise use GSI draft
        if self.manual_enemy_heroes:
            effective_enemy_heroes = list(self.manual_enemy_heroes)
        else:
            effective_enemy_heroes = dire_heroes if user_team == "radiant" else radiant_heroes

        # Extract current player items and check for Aegis in slot0..slot5
        player_item_list: List[str] = []
        has_aegis = False
        if isinstance(items_data, dict):
            for slot in ["slot0", "slot1", "slot2", "slot3", "slot4", "slot5"]:
                item_info = items_data.get(slot)
                if isinstance(item_info, dict):
                    iname = item_info.get("name")
                    if iname and iname not in ["empty", "none"]:
                        player_item_list.append(str(iname))
                        if iname == "item_aegis":
                            has_aegis = True

        # Update hybrid Aegis tracker in engine
        self.engine.update_aegis_inventory(has_aegis, clock_time)

        # Compute draft analysis safely
        draft_rad = radiant_heroes if user_team == "radiant" else effective_enemy_heroes
        draft_dire = effective_enemy_heroes if user_team == "radiant" else dire_heroes
        draft_analysis = self.engine.analyze_draft(
            radiant_heroes=draft_rad,
            dire_heroes=draft_dire,
            user_team=user_team,
            target_role=self.selected_role
        )

        def safe_int(val: Any, default: int = 0) -> int:
            try:
                return int(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        current_cs = safe_int(player_data.get("last_hits"), 0)
        current_denies = safe_int(player_data.get("denies"), 0)
        current_gold = safe_int(player_data.get("gold"), 0)
        gold_unreliable = safe_int(player_data.get("gold_unreliable"), 0)
        current_gpm = safe_int(player_data.get("gpm"), 0)
        current_xpm = safe_int(player_data.get("xpm"), 0)
        hero_alive = bool(hero_data.get("alive", True))
        current_kills = safe_int(player_data.get("kills"), 0)
        current_deaths = safe_int(player_data.get("deaths"), 0)
        current_assists = safe_int(player_data.get("assists"), 0)

        bb_cost_raw = hero_data.get("buyback_cost")
        bb_cost = safe_int(bb_cost_raw, None) if bb_cost_raw is not None else None
        bb_cd = safe_int(hero_data.get("buyback_cooldown"), 0)

        # Reconstruct net worth if missing in GSI:
        net_worth = safe_int(player_data.get("net_worth"), 0)
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
            buyback_cooldown=bb_cd,
            current_kills=current_kills,
            current_deaths=current_deaths,
            current_assists=current_assists
        )

        daytime = bool(map_data.get("daytime", True))
        radar_analysis = self.engine.get_macro_timers(
            clock_time=clock_time,
            daytime=daytime,
            role=self.selected_role
        )

        # Inventory inspection (neutral0, teleport0, backpack active items)
        if isinstance(items_data, dict):
            inventory_alerts = self.engine.inspect_inventory(items_data, clock_time)
            radar_analysis["active_alerts"].extend(inventory_alerts)

        # Enemy power spikes (Ursa/Huskar @ 9:30, Blink @ 10:30, Orchid @ 14:30)
        power_spike_alerts = self.engine.check_power_spikes(clock_time, effective_enemy_heroes)
        radar_analysis["active_alerts"].extend(power_spike_alerts)

        item_advice = self.engine.recommend_items(
            enemy_heroes=effective_enemy_heroes,
            current_player_items=player_item_list
        )

        # Full Dota Plus analytics suite:
        hero_raw_name = str(hero_data.get("name", "") or "")
        hero_level = safe_int(hero_data.get("level"), 1)
        damage_breakdown = self.engine.calculate_damage_breakdown(effective_enemy_heroes)
        item_build = self.engine.get_item_progression(hero_raw_name or "npc_dota_hero_juggernaut", self.selected_role)
        ability_build = self.engine.get_ability_build(hero_raw_name or "npc_dota_hero_juggernaut", hero_level=hero_level)
        next_item = self.engine.get_next_recommended_item(
            hero_identifier=hero_raw_name or "npc_dota_hero_juggernaut",
            role=self.selected_role,
            current_gold=current_gold,
            current_inventory=player_item_list,
            clock_time=clock_time,
            enemy_heroes=effective_enemy_heroes,
            current_gpm=current_gpm
        )
        game_phase_meta = self.engine.get_game_phase(clock_time)
        tracked_ultimates = self.engine.get_tracked_ultimates(effective_enemy_heroes, clock_time)

        # Record timeline history (Net Worth progression graph)
        if clock_time >= 0:
            curr_min = clock_time // 60
            if curr_min != self.last_recorded_minute:
                self.last_recorded_minute = curr_min
                self.timeline_history.append({
                    "minute": curr_min,
                    "clock_formatted": self.engine.format_clock(clock_time),
                    "player_nw": net_worth,
                    "benchmark_nw": performance_analysis["benchmarks"]["target_nw"],
                    "player_gpm": current_gpm,
                    "benchmark_gpm": performance_analysis["benchmarks"]["target_gpm"]
                })
                if len(self.timeline_history) > 90:
                    self.timeline_history.pop(0)

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
                "match_id": str(map_data.get("matchid", "")),
                "clock_time": clock_time,
                "clock_formatted": self.engine.format_clock(clock_time),
                "daytime": daytime,
                "radiant_score": safe_int(map_data.get("radiant_score"), 0),
                "dire_score": safe_int(map_data.get("dire_score"), 0),
                "user_team": user_team
            },
            "player": {
                "hero_name": str(hero_data.get("name", "")),
                "hero_level": safe_int(hero_data.get("level"), 1),
                "alive": hero_alive,
                "respawn_seconds": safe_int(hero_data.get("respawn_seconds"), 0),
                "health": safe_int(hero_data.get("health"), 0),
                "max_health": safe_int(hero_data.get("max_health"), 1),
                "mana": safe_int(hero_data.get("mana"), 0),
                "max_mana": safe_int(hero_data.get("max_mana"), 1),
                "kills": safe_int(player_data.get("kills"), 0),
                "deaths": safe_int(player_data.get("deaths"), 0),
                "assists": safe_int(player_data.get("assists"), 0),
                "gold": current_gold,
                "gold_unreliable": gold_unreliable,
                "net_worth": net_worth,
                "items": player_item_list
            },
            "draft": draft_analysis,
            "performance": performance_analysis,
            "radar": radar_analysis,
            "recommended_items": item_advice,
            "damage_breakdown": damage_breakdown,
            "item_build": item_build,
            "ability_build": ability_build,
            "next_item": next_item,
            "dynamic_phase": game_phase_meta,
            "tracked_ultimates": tracked_ultimates,
            "stack_alerts_midgame_enabled": self.engine.stack_alerts_enabled_midgame,
            "nw_history": list(self.timeline_history)
        }

        self.notify_subscribers()

    def notify_subscribers(self):
        payload = json.dumps(self.cached_analysis)
        with self.subscribers_lock:
            for q in list(self.subscribers):
                try:
                    q.put_nowait(payload)
                except Exception:
                    pass


state = AppState()


class GSIHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def log_message(self, format, *args):
        # Suppress routine SSE polling for cleaner stdout
        if len(args) >= 1 and isinstance(args[0], str) and "GET /api/events" in args[0]:
            return
        super().log_message(format, *args)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # 1. API: Close Menu (Esc or ✕ button) -> Switch to HUD mode
        if parsed.path == "/api/close_menu":
            if overlay_app:
                GLib.idle_add(overlay_app.set_interactive_mode, False)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"menu_closed"}')
            return

        # 2. API: Toggle Menu (Super + O)
        elif parsed.path == "/api/toggle_menu":
            if overlay_app:
                GLib.idle_add(overlay_app.toggle_interactive_mode)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        # 3. API: Shutdown Application (Quit button)
        elif parsed.path in ["/api/shutdown", "/api/quit"]:
            if overlay_app:
                GLib.idle_add(overlay_app.quit_application)
            threading.Timer(0.5, lambda: os._exit(0)).start()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"quitting"}')
            return

        # 3. API: Settings update
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
                    state.cached_analysis["recommended_items"] = state.engine.recommend_items(state.manual_enemy_heroes)
                    state.cached_analysis["damage_breakdown"] = state.engine.calculate_damage_breakdown(state.manual_enemy_heroes)
                    state.cached_analysis["item_build"] = state.engine.get_item_progression("npc_dota_hero_juggernaut", state.selected_role)
                    state.cached_analysis["next_item"] = state.engine.get_next_recommended_item(
                        "npc_dota_hero_juggernaut",
                        state.selected_role,
                        600,
                        [],
                        0,
                        state.manual_enemy_heroes,
                        0
                    )
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

        # 4. API: Roshan manual kill mark
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

        # 5. API: Glyph used mark
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

        # 5.1. API: Big Ultimate Used Tracker
        elif parsed.path == "/api/ultimate_used":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
                data = json.loads(body) if body else {}
                hero = data.get("hero")
                clock_time = int(state.raw_gsi.get("map", {}).get("clock_time", 0)) if state.raw_gsi else 0
                res = state.engine.record_ultimate_used(hero, clock_time)
                if state.raw_gsi:
                    state.process_gsi_payload(state.raw_gsi)
                else:
                    state.cached_analysis["tracked_ultimates"] = state.engine.get_tracked_ultimates(state.manual_enemy_heroes, clock_time)
                    state.notify_subscribers()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ultimate_recorded", "result": res}).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        # 5.2. API: Toggle midgame stack alerts
        elif parsed.path == "/api/toggle_midgame_stacks":
            try:
                state.engine.stack_alerts_enabled_midgame = not state.engine.stack_alerts_enabled_midgame
                clock_time = int(state.raw_gsi.get("map", {}).get("clock_time", 0)) if state.raw_gsi else 0
                if state.raw_gsi:
                    state.process_gsi_payload(state.raw_gsi)
                else:
                    state.cached_analysis["stack_alerts_midgame_enabled"] = state.engine.stack_alerts_enabled_midgame
                    state.notify_subscribers()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "toggled", "enabled": state.engine.stack_alerts_enabled_midgame}).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        # 6. API: Simulate match
        elif parsed.path == "/api/simulate":
            threading.Thread(target=run_simulation, daemon=True).start()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"simulation_started"}')
            return

        # 7. API: Roshan Manual Controls (Mobile & Companion)
        elif parsed.path == "/api/roshan/manual_kill":
            try:
                clock = int(state.raw_gsi.get("map", {}).get("clock_time", 0) or 0)
            except (ValueError, TypeError):
                clock = 0
            if not clock and getattr(state, "simulation_time", 0):
                clock = state.simulation_time
            state.engine.record_roshan_killed(clock)
            state.roshan_death_time = clock
            state.last_roshan_state = "dead"
            if state.raw_gsi:
                state.process_gsi_payload(state.raw_gsi)
            else:
                state.notify_subscribers()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "roshan_death_time": clock}).encode("utf-8"))
            return

        elif parsed.path == "/api/roshan/reset":
            state.engine.roshan_death_time = None
            state.roshan_death_time = None
            state.last_roshan_state = "alive"
            if state.raw_gsi:
                state.process_gsi_payload(state.raw_gsi)
            else:
                state.notify_subscribers()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "roshan_state": "alive"}).encode("utf-8"))
            return

        # 8. API: Overlay legacy toggles
        elif parsed.path == "/api/overlay/toggle":
            state.overlay_open = not getattr(state, "overlay_open", True)
            if overlay_app:
                GLib.idle_add(overlay_app.set_interactive_mode, state.overlay_open)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "overlay_open": state.overlay_open}).encode("utf-8"))
            return

        elif parsed.path == "/api/overlay/open":
            state.overlay_open = True
            if overlay_app:
                GLib.idle_add(overlay_app.set_interactive_mode, True)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "overlay_open": True}).encode("utf-8"))
            return

        elif parsed.path == "/api/overlay/close":
            state.overlay_open = False
            if overlay_app:
                GLib.idle_add(overlay_app.set_interactive_mode, False)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "overlay_open": False}).encode("utf-8"))
            return

        # 8. All other POST requests: treat as Dota 2 GSI payload regardless of path
        try:
            data = json.loads(body.decode("utf-8"))
            if not state._first_packet_logged:
                state._first_packet_logged = True
                game_state = data.get("map", {}).get("game_state", "unknown")
                print(f"[GSI] Packet received: map.game_state = {game_state}")
            state.process_gsi_payload(data)
        except Exception as e:
            pass

        # Always immediately return 200 OK to keep Dota 2 GSI sender alive and healthy
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def end_headers(self):
        # Prevent caching of frontend assets (HTML, CSS, JS) so HUD updates immediately
        req_path = getattr(self, "path", "") or ""
        if any(req_path.endswith(ext) or ext in req_path for ext in [".html", ".css", ".js", "/"]):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/status":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            is_interactive = overlay_app.interactive if overlay_app else True
            status_data = {
                "status": "running",
                "interactive": is_interactive,
                "gsi_connected": state.is_connected
            }
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
            return

        elif parsed.path == "/api/state":
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

        # SSE stream endpoint supported on /api/events, /events, /stream
        elif parsed.path in ["/api/events", "/events", "/stream"]:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

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

        if parsed.path in ["/", ""]:
            self.path = "/index.html"

        super().do_GET()


def run_simulation():
    """Simulates a realistic Dota 2 match progression with inventory checks."""
    if state.simulation_running:
        return
    state.simulation_running = True

    try:
        # 1. Draft Phase simulation
        state.process_gsi_payload({
            "map": { "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION", "clock_time": -30, "radiant_score": 0, "dire_score": 0 },
            "player": { "team_name": "radiant", "last_hits": 0, "denies": 0, "gold": 600, "gold_unreliable": 500, "gpm": 0, "xpm": 0 },
            "draft": {
                "team2": { "pick0": { "hero_id": 8 }, "pick1": { "hero_id": 5 } },
                "team3": { "pick0": { "hero_id": 99 }, "pick1": { "hero_id": 44 }, "pick2": { "hero_id": 10 } }
            }
        })
        time.sleep(1.5)

        # 2. In-Game Phase progression
        simulated_stages = [
            { "clock": 165, "cs": 18, "nw": 1350, "gpm": 420, "xpm": 390, "kills": 1, "deaths": 0, "assists": 0 },
            { "clock": 405, "cs": 52, "nw": 3100, "gpm": 460, "xpm": 480, "kills": 2, "deaths": 0, "assists": 2 },
            { "clock": 595, "cs": 86, "nw": 5400, "gpm": 510, "xpm": 520, "kills": 4, "deaths": 1, "assists": 4 },
            { "clock": 1035, "cs": 142, "nw": 9200, "gpm": 540, "xpm": 560, "kills": 7, "deaths": 1, "assists": 8 }
        ]

        for stage in simulated_stages:
            state.process_gsi_payload({
                "map": {
                    "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                    "clock_time": stage["clock"],
                    "daytime": ((stage["clock"] // 300) % 2 == 0),
                    "radiant_score": 12,
                    "dire_score": 9
                },
                "player": {
                    "team_name": "radiant",
                    "last_hits": stage["cs"],
                    "denies": 12,
                    "gold": 1200,
                    "gold_unreliable": 400,
                    "gpm": stage["gpm"],
                    "xpm": stage["xpm"],
                    "net_worth": stage["nw"],
                    "kills": stage["kills"],
                    "deaths": stage["deaths"],
                    "assists": stage["assists"]
                },
                "hero": {
                    "name": "npc_dota_hero_juggernaut",
                    "level": 14,
                    "alive": True,
                    "buyback_cost": 480,
                    "buyback_cooldown": 0
                },
                "items": {
                    "slot0": { "name": "item_phase_boots" },
                    "slot1": { "name": "item_bfury" },
                    "slot2": { "name": "item_yasha" },
                    "slot3": { "name": "item_magic_wand" },
                    "slot4": { "name": "item_aegis" if stage["clock"] > 900 else "empty" }
                }
            })
            time.sleep(1.5)
    finally:
        state.simulation_running = False


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
        super().server_bind()


def start_server(port: int = 3000):
    public_url = os.environ.get("AEGIS_PUBLIC_URL", "").strip()
    all_ips = get_local_ips()
    primary_ip = all_ips[0]
    local_url = f"http://{primary_ip}:{port}"
    localhost_url = f"http://127.0.0.1:{port}"
    active_target_url = public_url if public_url else local_url
    qr_ascii = SimpleQRCode.to_terminal_string(active_target_url)

    print("\n" + "=" * 65)
    print("🛡️   AegisPlus Pro: Dota 2 Mobile Companion & Game Server")
    print("=" * 65)
    print(f"👉 Локально на ПК:      {localhost_url}")
    print(f"👉 Steam In-Game HUD:   {localhost_url}/?mode=hud")
    for idx, ip in enumerate(all_ips):
        print(f"👉 По Wi-Fi сети #{idx+1}:   http://{ip}:{port}")
    if public_url:
        print(f"🌐 ОТКРЫТЫЙ ИНТЕРНЕТ:   {public_url}")
    print("-" * 65)
    print(f"📱 Отсканируйте QR-код камерой телефона ({'Интернет' if public_url else 'Wi-Fi'}):")
    print(qr_ascii)
    print("=" * 65 + "\n")


    try:
        server = ReusableThreadingHTTPServer(("0.0.0.0", port), GSIHTTPRequestHandler)
        server.serve_forever()
    except OSError as e:
        if e.errno == 98:
            print(f"[AegisPlus GSI] Порт {port} уже занят (сервер уже работает)")
        else:
            raise



if __name__ == "__main__":
    start_server(3000)
