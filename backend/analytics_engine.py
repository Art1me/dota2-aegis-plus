import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.hero_builds import ITEM_CATALOG, ITEM_COMPONENTS, SPECIFIC_HERO_BUILDS, get_hero_build_raw
except ImportError:
    from hero_builds import ITEM_CATALOG, ITEM_COMPONENTS, SPECIFIC_HERO_BUILDS, get_hero_build_raw

DATA_DIR = Path(__file__).parent.parent / "data"

# Big Game-Changing Ultimates Database
BIG_ULTIMATES: Dict[str, Dict[str, Any]] = {
    "npc_dota_hero_enigma": {
        "hero": "Enigma",
        "ability": "Black Hole",
        "cooldown": 180,
        "icon": "enigma_black_hole",
        "symbol": "🌀"
    },
    "npc_dota_hero_tidehunter": {
        "hero": "Tidehunter",
        "ability": "Ravage",
        "cooldown": 150,
        "icon": "tidehunter_ravage",
        "symbol": "🌊"
    },
    "npc_dota_hero_faceless_void": {
        "hero": "Faceless Void",
        "ability": "Chronosphere",
        "cooldown": 160,
        "icon": "faceless_void_chronosphere",
        "symbol": "⏱️"
    },
    "npc_dota_hero_magnataur": {
        "hero": "Magnus",
        "ability": "Reverse Polarity",
        "cooldown": 130,
        "icon": "magnataur_reverse_polarity",
        "symbol": "🧲"
    },
    "npc_dota_hero_silencer": {
        "hero": "Silencer",
        "ability": "Global Silence",
        "cooldown": 130,
        "icon": "silencer_global_silence",
        "symbol": "🤫"
    },
    "npc_dota_hero_warlock": {
        "hero": "Warlock",
        "ability": "Chaotic Offering",
        "cooldown": 160,
        "icon": "warlock_rain_of_chaos",
        "symbol": "👹"
    },
    "npc_dota_hero_doom_bringer": {
        "hero": "Doom",
        "ability": "Doom",
        "cooldown": 140,
        "icon": "doom_bringer_doom",
        "symbol": "🔥"
    },
    "npc_dota_hero_mars": {
        "hero": "Mars",
        "ability": "Arena of Blood",
        "cooldown": 95,
        "icon": "mars_arena_of_blood",
        "symbol": "🛡️"
    }
}

class AnalyticsEngine:
    def __init__(self):
        self.heroes_data: Dict[str, Any] = {}
        self.benchmarks_data: Dict[str, Any] = {}
        self.items_data: List[Dict[str, Any]] = []
        self._load_datasets()
        
        self.hero_by_id: Dict[str, Dict[str, Any]] = {}
        self.hero_by_name: Dict[str, Dict[str, Any]] = {}
        self._build_hero_indexes()

        # Hybrid Roshan & Aegis state
        self.roshan_death_time: Optional[int] = None
        self.aegis_start_time: Optional[int] = None
        self.aegis_expired: bool = False
        self.player_had_aegis: bool = False

        # Enemy Glyph state
        self.glyph_cooldown_start: Optional[int] = None

        # Rolling 3-min GPM buffer: [(clock_time, net_worth), ...]
        self.nw_history: List[Tuple[int, int]] = []

        # Big Ultimates cooldown tracker: {hero_key: expiry_clock_time}
        self.ultimate_cooldowns: Dict[str, int] = {}

        # User preference: stack alerts enabled in mid/late game
        self.stack_alerts_enabled_midgame: bool = False

    def _load_datasets(self):
        heroes_path = DATA_DIR / "heroes.json"
        benchmarks_path = DATA_DIR / "benchmarks.json"
        items_path = DATA_DIR / "items.json"

        if heroes_path.exists():
            with open(heroes_path, "r", encoding="utf-8") as f:
                self.heroes_data = json.load(f)
        
        if benchmarks_path.exists():
            with open(benchmarks_path, "r", encoding="utf-8") as f:
                self.benchmarks_data = json.load(f)

        if items_path.exists():
            with open(items_path, "r", encoding="utf-8") as f:
                self.items_data = json.load(f)

    def _build_hero_indexes(self):
        for hid, hdata in self.heroes_data.items():
            hdata["id"] = hid
            self.hero_by_id[str(hid)] = hdata
            name = hdata.get("name", "")
            if name:
                self.hero_by_name[name] = hdata

    def get_hero_by_identifier(self, identifier: Any) -> Optional[Dict[str, Any]]:
        if identifier is None:
            return None
        s_id = str(identifier).strip().lower()
        if s_id in self.hero_by_id:
            return self.hero_by_id[s_id]
        if s_id in self.hero_by_name:
            return self.hero_by_name[s_id]

        for h in self.heroes_data.values():
            h_name = h.get("name", "").lower()
            if h_name == s_id or h_name == f"npc_dota_hero_{s_id}":
                return h
            if h.get("display_name", "").lower() == s_id:
                return h
            aliases = [a.lower() for a in h.get("aliases", [])]
            if s_id in aliases:
                return h
        return None

    # ==========================================
    # 1. HYBRID ROSHAN & GLYPH TRACKER
    # ==========================================
    def record_roshan_killed(self, clock_time: int) -> Dict[str, Any]:
        """
        Manually or automatically marks Roshan killed at clock_time.
        Computes Aegis & respawn window and copies chat string to clipboard.
        """
        self.roshan_death_time = clock_time
        self.aegis_start_time = clock_time
        self.aegis_expired = False

        aegis_end = clock_time + 300
        rosh_min = clock_time + 480
        rosh_max = clock_time + 660

        chat_string = f"{self.format_clock(aegis_end)} Aegis | {self.format_clock(rosh_min)} - {self.format_clock(rosh_max)} Roshan"

        # Copy to clipboard via wl-copy (Wayland) if available
        if shutil.which("wl-copy"):
            try:
                subprocess.Popen(["wl-copy", chat_string], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"[AegisPlus Analytics] Ошибка wl-copy: {e}")

        return {
            "roshan_death_time": clock_time,
            "aegis_end": aegis_end,
            "rosh_min": rosh_min,
            "rosh_max": rosh_max,
            "chat_string": chat_string
        }

    def update_aegis_inventory(self, has_aegis: bool, clock_time: int):
        """
        Auto-detection of Aegis in player inventory:
        - Auto-start if picked up first time.
        - Auto-expire if lost before 300 seconds.
        """
        if has_aegis and not self.player_had_aegis:
            if self.roshan_death_time is None:
                self.record_roshan_killed(clock_time)
            self.aegis_start_time = clock_time
            self.aegis_expired = False
        elif not has_aegis and self.player_had_aegis:
            if self.aegis_start_time is not None and (clock_time - self.aegis_start_time) < 300:
                self.aegis_expired = True

        self.player_had_aegis = has_aegis

    def record_glyph_used(self, clock_time: int) -> int:
        """Starts 300s enemy Glyph cooldown."""
        self.glyph_cooldown_start = clock_time
        return 300

    # ==========================================
    # 1.1 BIG ENEMY ULTIMATES & GAME PHASES
    # ==========================================
    def record_ultimate_used(self, hero_identifier: str, clock_time: int) -> Optional[Dict[str, Any]]:
        """
        Marks an enemy ultimate as used at clock_time and starts its cooldown countdown.
        """
        hero_obj = self.get_hero_by_identifier(hero_identifier)
        hero_name = hero_obj.get("name", "") if hero_obj else str(hero_identifier or "")

        matched_key = None
        for k in BIG_ULTIMATES:
            if k == hero_name or k.replace("npc_dota_hero_", "") == hero_name.replace("npc_dota_hero_", ""):
                matched_key = k
                break

        if not matched_key:
            return None

        meta = BIG_ULTIMATES[matched_key]
        cd = meta["cooldown"]
        ready_time = clock_time + cd
        self.ultimate_cooldowns[matched_key] = ready_time

        return {
            "hero_key": matched_key,
            "hero": meta["hero"],
            "ability": meta["ability"],
            "cooldown": cd,
            "ready_time": ready_time,
            "ready_at": self.format_clock(ready_time)
        }

    def get_tracked_ultimates(self, enemy_heroes: List[Any], clock_time: int) -> List[Dict[str, Any]]:
        """
        Returns list of trackable big enemy ultimates present in the enemy lineup.
        """
        tracked = []
        if not enemy_heroes:
            return tracked

        for eh in enemy_heroes:
            if not eh:
                continue
            e_obj = self.get_hero_by_identifier(eh)
            h_name = e_obj.get("name", "") if e_obj else str(eh)

            for k, meta in BIG_ULTIMATES.items():
                if k == h_name or k.replace("npc_dota_hero_", "") == h_name.replace("npc_dota_hero_", ""):
                    ready_time = self.ultimate_cooldowns.get(k, 0)
                    rem = max(0, ready_time - clock_time)
                    is_on_cd = (rem > 0)
                    tracked.append({
                        "hero_key": k,
                        "hero": meta["hero"],
                        "ability": meta["ability"],
                        "cooldown": meta["cooldown"],
                        "symbol": meta["symbol"],
                        "icon": meta["icon"],
                        "is_on_cooldown": is_on_cd,
                        "on_cooldown": is_on_cd,
                        "remaining_seconds": rem,
                        "ready_at": self.format_clock(ready_time) if is_on_cd else "ГОТОВ"
                    })
                    break
        return tracked

    def get_game_phase(self, clock_time: int) -> Dict[str, Any]:
        """
        Evaluates match clock_time and returns dynamic game phase:
        - Laning (00:00 - 10:00 / 600s)
        - Midgame (10:00 - 22:00 / 1320s)
        - Late Game (22:00+ / 1320s+)
        """
        if clock_time < 600:
            return {
                "phase": "laning",
                "label": "Лайнинг (0-10 мин)",
                "badge": "🌿 Лайнинг",
                "show_cs": True,
                "show_water_runes": clock_time < 270,
                "allow_camp_stacks": True
            }
        elif clock_time < 1320:
            return {
                "phase": "midgame",
                "label": "Мидгейм (10-22 мин)",
                "badge": "⚔️ Мидгейм",
                "show_cs": False,
                "show_water_runes": False,
                "allow_camp_stacks": clock_time < 960 or self.stack_alerts_enabled_midgame
            }
        else:
            return {
                "phase": "late",
                "label": "Лейтгейм (22+ мин)",
                "badge": "🔥 Лейтгейм",
                "show_cs": False,
                "show_water_runes": False,
                "allow_camp_stacks": self.stack_alerts_enabled_midgame
            }

    # ==========================================
    # 2. ENEMY POWER SPIKE WARNINGS
    # ==========================================
    def check_power_spikes(self, clock_time: int, enemy_heroes: List[Any]) -> List[Dict[str, Any]]:
        """
        Checks dangerous clock_time power spikes for selected enemy heroes:
        - 09:30: Ursa, Huskar, Meepo, Troll Warlord -> Early Roshan risk
        - 10:30: Axe, Magnus, Earthshaker, LC, Centaur, Sand King, Tidehunter -> Blink Dagger timing
        - 14:30: Storm Spirit, Clinkz, Queen of Pain, Nyx Assassin -> Orchid / Ganking window
        """
        alerts = []
        if clock_time <= 0 or not enemy_heroes:
            return alerts

        enemy_objs = [self.get_hero_by_identifier(h) for h in enemy_heroes if self.get_hero_by_identifier(h)]
        enemy_names = {e["name"] for e in enemy_objs}

        # Spike 1: 09:30 (570s) Early Roshan Risk
        if 560 <= clock_time <= 585:
            early_rosh_threats = [
                "npc_dota_hero_ursa",
                "npc_dota_hero_huskar",
                "npc_dota_hero_meepo",
                "npc_dota_hero_troll_warlord"
            ]
            matching = [e["display_name"] for e in enemy_objs if e["name"] in early_rosh_threats]
            if matching:
                alerts.append({
                    "id": "spike_early_rosh",
                    "title": "РИСК РАННЕГО РОШАНА!",
                    "text": f"Враг ({', '.join(matching)}) может забирать Рошана на 9-10 мин! Проверьте логово.",
                    "severity": "critical",
                    "sound": "wisdom_soon"
                })

        # Spike 2: 10:30 (630s) Blink Dagger Timing
        if 620 <= clock_time <= 645:
            blink_threats = [
                "npc_dota_hero_axe",
                "npc_dota_hero_magnataur",
                "npc_dota_hero_earthshaker",
                "npc_dota_hero_legion_commander",
                "npc_dota_hero_centaur",
                "npc_dota_hero_sand_king",
                "npc_dota_hero_tidehunter"
            ]
            matching = [e["display_name"] for e in enemy_objs if e["name"] in blink_threats]
            if matching:
                alerts.append({
                    "id": "spike_blink_dagger",
                    "title": "ТАЙМИНГ BLINK DAGGER У ВРАГА!",
                    "text": f"10:30 — средний тайминг Блинка у {', '.join(matching)}! Играйте аккуратнее на линиях.",
                    "severity": "warning",
                    "sound": "power_soon"
                })

        # Spike 3: 14:30 (870s) Orchid / Gank Window
        if 860 <= clock_time <= 885:
            orchid_threats = [
                "npc_dota_hero_storm_spirit",
                "npc_dota_hero_clinkz",
                "npc_dota_hero_queenofpain",
                "npc_dota_hero_nyx_assassin"
            ]
            matching = [e["display_name"] for e in enemy_objs if e["name"] in orchid_threats]
            if matching:
                alerts.append({
                    "id": "spike_orchid_gank",
                    "title": "ОКНО ПОКУПКИ ORCHID / ГАНГА!",
                    "text": f"14:30 — опасный пик силы {', '.join(matching)} с Orchid / прокастом! Носите детекцию и сейв.",
                    "severity": "warning",
                    "sound": "lotus_soon"
                })

        return alerts

    # ==========================================
    # 3. DRAFT ANALYTICS & COUNTER RECOMMENDER
    # ==========================================
    def analyze_draft(
        self,
        radiant_heroes: List[Any],
        dire_heroes: List[Any],
        user_team: str = "radiant",
        target_role: Optional[str] = None
    ) -> Dict[str, Any]:
        rad_objs = [self.get_hero_by_identifier(h) for h in radiant_heroes if self.get_hero_by_identifier(h)]
        dire_objs = [self.get_hero_by_identifier(h) for h in dire_heroes if self.get_hero_by_identifier(h)]

        ally_objs = rad_objs if user_team == "radiant" else dire_objs
        enemy_objs = dire_objs if user_team == "radiant" else rad_objs

        all_picked_names = {h["name"] for h in (rad_objs + dire_objs)}

        counter_scores: Dict[str, float] = {}
        for enemy in enemy_objs:
            for counter_hero_name in enemy.get("countered_by", []):
                counter_scores[counter_hero_name] = counter_scores.get(counter_hero_name, 0.0) + 1.8
            for victim_hero_name in enemy.get("counters", []):
                counter_scores[victim_hero_name] = counter_scores.get(victim_hero_name, 0.0) - 1.2

        role_recommendations: Dict[str, List[Dict[str, Any]]] = {
            "Carry": [],
            "Mid": [],
            "Offlane": [],
            "Support": []
        }

        for hero in self.heroes_data.values():
            if hero["name"] in all_picked_names:
                continue

            score = counter_scores.get(hero["name"], 0.0)
            hero_tags = set(hero.get("tags", []))
            for enemy in enemy_objs:
                e_tags = set(enemy.get("tags", []))
                if "illusion" in e_tags and "anti_illusion" in hero_tags:
                    score += 2.0
                if "high_regen" in e_tags and "anti_regen" in hero_tags:
                    score += 2.5
                if "invis" in e_tags and "anti_invis" in hero_tags:
                    score += 2.0

            role = hero.get("role", "Carry")
            target_bucket = "Support" if "Support" in role else role
            if target_bucket not in role_recommendations:
                target_bucket = "Carry"

            role_recommendations[target_bucket].append({
                "hero_id": hero["id"],
                "name": hero["name"],
                "display_name": hero["display_name"],
                "attr": hero.get("attr", "str"),
                "score": round(score, 1),
                "tags": hero.get("tags", []),
                "reasons": self._generate_counter_reasons(hero, enemy_objs)
            })

        for r_name in role_recommendations:
            role_recommendations[r_name].sort(key=lambda x: x["score"], reverse=True)
            role_recommendations[r_name] = role_recommendations[r_name][:5]

        ban_recommendations: List[Dict[str, Any]] = []
        ban_scores: Dict[str, float] = {}
        for ally in ally_objs:
            for counter_name in ally.get("countered_by", []):
                ban_scores[counter_name] = ban_scores.get(counter_name, 0.0) + 2.0

        for hero in self.heroes_data.values():
            if hero["name"] in all_picked_names:
                continue
            if hero["name"] in ban_scores:
                ban_recommendations.append({
                    "name": hero["name"],
                    "display_name": hero["display_name"],
                    "threat_score": ban_scores[hero["name"]],
                    "reason": f"Критическая угроза для: {', '.join([a['display_name'] for a in ally_objs if hero['name'] in a.get('countered_by', [])])}"
                })
        ban_recommendations.sort(key=lambda x: x["threat_score"], reverse=True)

        ally_counter_power = sum(counter_scores.get(a["name"], 0) for a in ally_objs)
        base_advantage = 50.0 + (ally_counter_power * 4.0)
        win_advantage = max(20.0, min(80.0, base_advantage))

        return {
            "user_team": user_team,
            "win_advantage_pct": round(win_advantage, 1),
            "recommendations": role_recommendations,
            "bans": ban_recommendations[:4],
            "radiant_picks": [h["display_name"] for h in rad_objs],
            "dire_picks": [h["display_name"] for h in dire_objs],
            "missing_composition": self._check_composition_gaps(ally_objs)
        }

    def _generate_counter_reasons(self, hero: Dict[str, Any], enemy_heroes: List[Dict[str, Any]]) -> List[str]:
        reasons = []
        h_name = hero["name"]
        for enemy in enemy_heroes:
            if h_name in enemy.get("countered_by", []):
                reasons.append(f"Контрит {enemy['display_name']}")
        return reasons

    def _check_composition_gaps(self, team: List[Dict[str, Any]]) -> List[str]:
        gaps = []
        if not team:
            return gaps
        
        has_stun = any("stun" in " ".join(h.get("tags", [])) for h in team)
        has_tank = any("tank" in " ".join(h.get("tags", [])) for h in team)
        has_magic = any("magic" in " ".join(h.get("tags", [])) for h in team)

        if not has_stun and len(team) >= 3:
            gaps.append("Мало надежного контроля / станов")
        if not has_tank and len(team) >= 3:
            gaps.append("Нет плотного фронтлейнера / инициатора")
        if not has_magic and len(team) >= 3:
            gaps.append("Слишком много физ. урона (легко контрить броней)")

        return gaps

    # ==========================================
    # 4. LIVE PERFORMANCE & ROLLING 3-MIN GPM
    # ==========================================
    def evaluate_performance(
        self,
        clock_time: int,
        rank: str,
        role: str,
        current_cs: int,
        current_denies: int,
        current_networth: int,
        current_gpm: int,
        current_xpm: int,
        current_gold: int,
        gold_unreliable: int = 0,
        hero_alive: bool = True,
        hero_buyback_cost: Optional[int] = None,
        buyback_cooldown: int = 0,
        current_kills: int = 0,
        current_deaths: int = 0,
        current_assists: int = 0
    ) -> Dict[str, Any]:
        minute = max(1, math.floor(clock_time / 60)) if clock_time > 0 else 0
        rank_data = self.benchmarks_data.get("benchmarks", {}).get(rank, {}).get(role, {})

        if not rank_data:
            rank_data = self.benchmarks_data.get("benchmarks", {}).get(rank, {}).get("Carry", {})

        target_cs, target_nw, target_gpm, target_xpm = self._interpolate_benchmark(rank_data, minute)

        delta_cs = current_cs - target_cs
        delta_nw = current_networth - target_nw
        delta_gpm = current_gpm - target_gpm
        delta_xpm = current_xpm - target_xpm

        # Target KDA benchmarks based on role, rank and game minute
        r_lower = role.lower()
        rank_lower = rank.lower()
        if any(rk in rank_lower for rk in ["divine", "immortal"]):
            k_mult, d_mult = 1.15, 0.85
        elif any(rk in rank_lower for rk in ["herald", "guardian"]):
            k_mult, d_mult = 0.85, 1.25
        else:
            k_mult, d_mult = 1.0, 1.0

        if "support" in r_lower or "pos 4" in r_lower or "pos 5" in r_lower:
            target_kills = round(max(0.0, (0.08 * minute - 0.2) * k_mult), 1)
            target_deaths = round(max(0.0, (0.16 * minute + 0.3) * d_mult), 1)
            target_assists = round(max(0.0, (0.50 * minute - 0.5) * k_mult), 1)
        elif "offlane" in r_lower or "pos 3" in r_lower:
            target_kills = round(max(0.0, (0.18 * minute - 0.4) * k_mult), 1)
            target_deaths = round(max(0.0, (0.14 * minute + 0.2) * d_mult), 1)
            target_assists = round(max(0.0, (0.42 * minute - 0.5) * k_mult), 1)
        elif "mid" in r_lower or "pos 2" in r_lower:
            target_kills = round(max(0.0, (0.28 * minute - 0.4) * k_mult), 1)
            target_deaths = round(max(0.0, (0.12 * minute) * d_mult), 1)
            target_assists = round(max(0.0, (0.32 * minute - 0.5) * k_mult), 1)
        else:  # Carry / Pos 1
            target_kills = round(max(0.0, (0.24 * minute - 0.4) * k_mult), 1)
            target_deaths = round(max(0.0, (0.10 * minute) * d_mult), 1)
            target_assists = round(max(0.0, (0.22 * minute - 0.4) * k_mult), 1)

        target_kda = round((target_kills + target_assists) / max(1.0, target_deaths), 2)
        current_kda = round((current_kills + current_assists) / max(1, current_deaths), 2)
        delta_kda = round(current_kda - target_kda, 2)
        delta_kills = round(current_kills - target_kills, 1)
        delta_deaths = round(current_deaths - target_deaths, 1)
        delta_assists = round(current_assists - target_assists, 1)

        # Ahead / Behind status indicators
        cs_ahead = delta_cs >= 0
        nw_ahead = delta_nw >= 0
        gpm_ahead = delta_gpm >= 0
        xpm_ahead = delta_xpm >= 0
        kda_ahead = delta_kda >= 0
        kills_ahead = delta_kills >= 0
        deaths_ahead = current_deaths <= target_deaths  # Fewer deaths than average = GOOD
        assists_ahead = delta_assists >= 0

        ahead_count = sum([1 for f in [cs_ahead, nw_ahead, gpm_ahead, kda_ahead, deaths_ahead] if f])
        if ahead_count >= 4:
            plan_verdict = "Опережение графика (S-тир)"
            plan_status = "ahead"
        elif ahead_count >= 3:
            plan_verdict = "В графике плана ранга"
            plan_status = "ahead"
        elif ahead_count == 2:
            plan_verdict = "Небольшое отставание"
            plan_status = "behind"
        else:
            plan_verdict = "Критическое отставание"
            plan_status = "behind"

        # Rolling 3-minute GPM calculation (180s circular window)
        if clock_time > 0:
            if not self.nw_history or clock_time > self.nw_history[-1][0]:
                self.nw_history.append((clock_time, current_networth))
            # Keep only items in the last 180s
            cutoff = clock_time - 180
            self.nw_history = [item for item in self.nw_history if item[0] >= cutoff]

        if len(self.nw_history) >= 2:
            t_old, nw_old = self.nw_history[0]
            dt = clock_time - t_old
            dnw = current_networth - nw_old
            if dt >= 20:
                rolling_gpm = max(0, int((dnw / dt) * 60))
            else:
                rolling_gpm = current_gpm
        else:
            rolling_gpm = current_gpm

        is_high_tempo = (rolling_gpm > target_gpm)

        score_pct = 100.0
        if target_nw > 0:
            score_pct = (current_networth / target_nw) * 100.0

        if score_pct >= 115:
            grade = "S"
            grade_label = "Доминирование"
            grade_color = "#10B981"
        elif score_pct >= 95:
            grade = "A"
            grade_label = "В графике ранга"
            grade_color = "#3B82F6"
        elif score_pct >= 80:
            grade = "B"
            grade_label = "Отставание"
            grade_color = "#F59E0B"
        else:
            grade = "C"
            grade_label = "Критически позади"
            grade_color = "#EF4444"

        # Buyback calculation
        bb_cost = hero_buyback_cost if hero_buyback_cost else int(200 + (current_networth / 13))
        death_penalty = min(gold_unreliable, current_networth // 40) if hero_alive else 0
        gold_after_death = max(0, current_gold - death_penalty)
        surplus = current_gold - bb_cost
        surplus_after_death = gold_after_death - bb_cost

        if buyback_cooldown > 0:
            status = "COOLDOWN"
            status_text = f"КД выкупа ({buyback_cooldown}с)"
            can_buyback = False
        elif gold_after_death >= bb_cost:
            status = "READY"
            status_text = "Выкуп готов"
            can_buyback = True
        elif current_gold >= bb_cost:
            status = "AT_RISK"
            status_text = f"Риск при смерти (-{death_penalty}g)"
            can_buyback = False
        else:
            status = "DEFICIT"
            deficit = bb_cost - current_gold
            status_text = f"Дефицит {deficit} 💰"
            can_buyback = False

        # Critical late-game danger banner (20:00+ and not safely buyback-ready)
        is_danger_bb = (clock_time >= 1200) and (status in ["AT_RISK", "DEFICIT"])
        danger_needed = abs(surplus_after_death) if status == "AT_RISK" else (bb_cost - current_gold)
        danger_banner = {
            "is_danger": is_danger_bb,
            "needed_gold": danger_needed,
            "text": f"⚠️ ОПАСНОСТЬ: ДО БАЙБЕКА +{danger_needed}g (НЕ УМИРАЙ!)" if is_danger_bb else "",
            "tts": "Внимание, не хватает на байбек после смерти" if is_danger_bb else ""
        }

        # Ergonomic 3-metric tempo summary for instant 0.5s reading
        tempo_summary = {
            "delta_nw": delta_nw,
            "delta_nw_str": f"{'+' if delta_nw >= 0 else ''}{delta_nw:,}g".replace(",", " "),
            "nw_arrow": "▲" if nw_ahead else "▼",
            "nw_status": "ahead" if nw_ahead else "behind",
            "rolling_gpm": rolling_gpm,
            "target_gpm": target_gpm,
            "delta_gpm": rolling_gpm - target_gpm,
            "gpm_arrow": "▲" if (rolling_gpm >= target_gpm) else "▼",
            "gpm_status": "ahead" if (rolling_gpm >= target_gpm) else "behind",
            "current_cs": current_cs,
            "current_denies": current_denies,
            "target_cs": target_cs,
            "show_cs": (clock_time < 600)  # Laning stage only (0:00 - 10:00)
        }

        return {
            "minute": minute,
            "clock_formatted": self.format_clock(clock_time),
            "rank": rank,
            "role": role,
            "grade": grade,
            "grade_label": grade_label,
            "grade_color": grade_color,
            "score_pct": round(score_pct, 1),
            "tempo_summary": tempo_summary,
            "benchmarks": {
                "target_cs": target_cs,
                "current_cs": current_cs,
                "delta_cs": delta_cs,
                "cs_status": "ahead" if cs_ahead else "behind",
                "cs_arrow": "▲" if cs_ahead else "▼",

                "target_nw": target_nw,
                "current_nw": current_networth,
                "delta_nw": delta_nw,
                "nw_status": "ahead" if nw_ahead else "behind",
                "nw_arrow": "▲" if nw_ahead else "▼",

                "target_gpm": target_gpm,
                "current_gpm": current_gpm,
                "delta_gpm": delta_gpm,
                "gpm_status": "ahead" if gpm_ahead else "behind",
                "gpm_arrow": "▲" if gpm_ahead else "▼",

                "target_xpm": target_xpm,
                "current_xpm": current_xpm,
                "delta_xpm": delta_xpm,
                "xpm_status": "ahead" if xpm_ahead else "behind",
                "xpm_arrow": "▲" if xpm_ahead else "▼",

                "current_kills": current_kills,
                "target_kills": target_kills,
                "delta_kills": delta_kills,
                "kills_status": "ahead" if kills_ahead else "behind",
                "kills_arrow": "▲" if kills_ahead else "▼",

                "current_deaths": current_deaths,
                "target_deaths": target_deaths,
                "delta_deaths": delta_deaths,
                "deaths_status": "ahead" if deaths_ahead else "behind",
                "deaths_arrow": "▲" if deaths_ahead else "▼",

                "current_assists": current_assists,
                "target_assists": target_assists,
                "delta_assists": delta_assists,
                "assists_status": "ahead" if assists_ahead else "behind",
                "assists_arrow": "▲" if assists_ahead else "▼",

                "current_kda": current_kda,
                "target_kda": target_kda,
                "delta_kda": delta_kda,
                "kda_status": "ahead" if kda_ahead else "behind",
                "kda_arrow": "▲" if kda_ahead else "▼",

                "plan_verdict": plan_verdict,
                "plan_status": plan_status,
                "ahead_count": ahead_count,
                "total_metrics": 5,
                "rolling_gpm": rolling_gpm,
                "is_high_tempo": is_high_tempo
            },
            "buyback": {
                "cost": bb_cost,
                "cooldown": buyback_cooldown,
                "gold_unreliable": gold_unreliable,
                "death_penalty": death_penalty,
                "gold_after_death": gold_after_death,
                "status": status,
                "status_text": status_text,
                "can_buyback": can_buyback,
                "surplus": surplus,
                "surplus_after_death": surplus_after_death,
                "danger_banner": danger_banner
            }
        }

    def _interpolate_benchmark(self, rank_data: Dict[str, Any], current_minute: int) -> tuple[int, int, int, int]:
        available_minutes = sorted([int(m) for m in rank_data.keys()])
        if not available_minutes:
            return 0, 0, 0, 0

        if current_minute <= available_minutes[0]:
            first = rank_data[str(available_minutes[0])]
            ratio = max(0.1, current_minute / available_minutes[0])
            return (
                int(first.get("cs", 0) * ratio),
                int(first.get("net_worth", 0) * ratio),
                first.get("gpm", 0),
                first.get("xpm", 0)
            )

        if current_minute >= available_minutes[-1]:
            last = rank_data[str(available_minutes[-1])]
            extra_mins = current_minute - available_minutes[-1]
            return (
                last.get("cs", 0) + (extra_mins * 8),
                last.get("net_worth", 0) + (extra_mins * 600),
                last.get("gpm", 0),
                last.get("xpm", 0)
            )

        m_lower = available_minutes[0]
        m_upper = available_minutes[-1]
        for m in available_minutes:
            if m <= current_minute:
                m_lower = m
            if m >= current_minute:
                m_upper = m
                break

        if m_lower == m_upper:
            target = rank_data[str(m_lower)]
            return target.get("cs", 0), target.get("net_worth", 0), target.get("gpm", 0), target.get("xpm", 0)

        t_factor = (current_minute - m_lower) / (m_upper - m_lower)
        d_lower = rank_data[str(m_lower)]
        d_upper = rank_data[str(m_upper)]

        cs = int(d_lower.get("cs", 0) + t_factor * (d_upper.get("cs", 0) - d_lower.get("cs", 0)))
        nw = int(d_lower.get("net_worth", 0) + t_factor * (d_upper.get("net_worth", 0) - d_lower.get("net_worth", 0)))
        gpm = int(d_lower.get("gpm", 0) + t_factor * (d_upper.get("gpm", 0) - d_lower.get("gpm", 0)))
        xpm = int(d_lower.get("xpm", 0) + t_factor * (d_upper.get("xpm", 0) - d_lower.get("xpm", 0)))

        return cs, nw, gpm, xpm

    # ==========================================
    # 5. INVENTORY INSPECTION
    # ==========================================
    def inspect_inventory(self, items_data: Dict[str, Any], clock_time: int) -> List[Dict[str, Any]]:
        alerts = []
        if clock_time <= 0 or not items_data:
            return alerts

        expected_tier = 0
        if clock_time >= 3600:
            expected_tier = 5
        elif clock_time >= 2220:
            expected_tier = 4
        elif clock_time >= 1620:
            expected_tier = 3
        elif clock_time >= 1020:
            expected_tier = 2
        elif clock_time >= 420:
            expected_tier = 1

        neutral_obj = items_data.get("neutral0", {})
        neutral_name = neutral_obj.get("name", "") if isinstance(neutral_obj, dict) else str(neutral_obj)
        is_neutral_empty = (not neutral_name) or (neutral_name in ["empty", "none", "item_empty"])

        if expected_tier >= 1 and is_neutral_empty:
            alerts.append({
                "id": f"neutral_empty_t{expected_tier}",
                "title": f"НЕЙТРАЛЬНЫЙ СЛОТ ПУСТ (Тир {expected_tier})",
                "text": f"Прошло {clock_time // 60} мин игры! Доступен {expected_tier}-й тир нейтральных предметов, выберите предмет!",
                "severity": "critical" if expected_tier >= 2 else "warning",
                "sound": "lotus_soon"
            })

        if clock_time >= 240:
            tp_obj = items_data.get("teleport0", {})
            tp_name = tp_obj.get("name", "") if isinstance(tp_obj, dict) else str(tp_obj)
            tp_charges = tp_obj.get("charges", 1) if isinstance(tp_obj, dict) else 1
            has_no_tp = (not tp_name) or (tp_name in ["empty", "none", "item_empty"]) or (tp_charges <= 0)

            if has_no_tp:
                alerts.append({
                    "id": "tp_missing",
                    "title": "НЕТ СВИТКА ТП",
                    "text": "Слот телепорта пуст! Купите свиток телепортации (TP) для подключения к драке или спасения",
                    "severity": "critical",
                    "sound": "wisdom_soon"
                })

        main_slots = ["slot0", "slot1", "slot2", "slot3", "slot4", "slot5"]
        backpack_slots = ["slot6", "slot7", "slot8"]

        has_free_main_slot = False
        for s in main_slots:
            slot_obj = items_data.get(s, {})
            s_name = slot_obj.get("name", "") if isinstance(slot_obj, dict) else str(slot_obj)
            if not s_name or s_name in ["empty", "none", "item_empty", "item_branches"]:
                has_free_main_slot = True
                break

        if has_free_main_slot:
            for bs in backpack_slots:
                b_obj = items_data.get(bs, {})
                if not isinstance(b_obj, dict):
                    continue
                b_name = b_obj.get("name", "")
                if not b_name or b_name in ["empty", "none", "item_empty", "item_branches", "item_ward_observer", "item_ward_sentry"]:
                    continue

                b_cd = int(b_obj.get("cooldown", 0))
                if b_cd == 0:
                    clean_item_name = b_name.replace("item_", "").replace("_", " ").title()
                    alerts.append({
                        "id": f"backpack_active_{b_name}",
                        "title": "ПРЕДМЕТ В РАНЦЕ",
                        "text": f"В ранце лежит {clean_item_name} без КД! В основном инвентаре есть свободный слот или ветка.",
                        "severity": "warning",
                        "sound": "power_soon"
                    })
                    break

        return alerts

    # ==========================================
    # 6. MACRO RADAR & TIMERS ENGINE
    # ==========================================
    def get_macro_timers(
        self,
        clock_time: int,
        daytime: bool = True,
        role: str = "Carry"
    ) -> Dict[str, Any]:
        if clock_time < 0:
            return {
                "phase": "pre_game",
                "seconds_to_horn": abs(clock_time),
                "timers": [],
                "active_alerts": [{
                    "id": "horn",
                    "title": "СТАРТ ИГРЫ",
                    "text": f"Выход крипов через {abs(clock_time)}с",
                    "severity": "info"
                }],
                "roshan": {
                    "status": "alive",
                    "window": "Жив",
                    "aegis_left": 0,
                    "aegis_expired": True,
                    "pit_location": "Нижнее логово (Radiant)",
                    "chat_string": ""
                },
                "glyph": {
                    "seconds_left": 0,
                    "status": "Готов",
                    "is_on_cooldown": False
                }
            }

        timers = []
        alerts = []
        r_lower = role.lower()
        is_mid = "mid" in r_lower or "pos 2" in r_lower
        is_support = "support" in r_lower or "pos 4" in r_lower or "pos 5" in r_lower

        # 1. Water Runes (2:00 = 120s, 4:00 = 240s)
        if clock_time < 240:
            if clock_time < 120:
                sec_to_water = 120 - clock_time
                next_water_clock = "02:00"
            else:
                sec_to_water = 240 - clock_time
                next_water_clock = "04:00"

            timers.append({
                "id": "water_rune",
                "name": "Руны Воды",
                "seconds_left": sec_to_water,
                "next_at_clock": next_water_clock,
                "icon": "water_rune"
            })

            if sec_to_water <= 30 and is_mid:
                alerts.append({
                    "id": "water_soon",
                    "title": "РУНЫ ВОДЫ (МИД)",
                    "text": f"Руны воды на реке через {sec_to_water}с! Контролируйте руну для пополнения Bottle",
                    "severity": "warning",
                    "sound": "power_soon"
                })

        # 2. Lotus Pools (every 180s)
        lotus_mod = clock_time % 180
        sec_to_lotus = 180 - lotus_mod
        timers.append({
            "id": "lotus",
            "name": "Пруд Лотосов",
            "seconds_left": sec_to_lotus,
            "next_at_clock": self.format_clock(clock_time + sec_to_lotus),
            "icon": "lotus"
        })
        if sec_to_lotus <= 20:
            alerts.append({
                "id": "lotus_soon",
                "title": "ЛОТОС СКОРО",
                "text": f"Появление Лотоса через {sec_to_lotus}с! Проверьте фонтан на реке",
                "severity": "warning",
                "sound": "lotus_soon"
            })

        # 3. Wisdom Runes (every 420s: 7:00, 14:00, 21:00...)
        wisdom_mod = clock_time % 420
        sec_to_wisdom = 420 - wisdom_mod
        timers.append({
            "id": "wisdom",
            "name": "Руна Мудрости",
            "seconds_left": sec_to_wisdom,
            "next_at_clock": self.format_clock(clock_time + sec_to_wisdom),
            "icon": "wisdom"
        })
        if sec_to_wisdom <= 35:
            alerts.append({
                "id": "wisdom_soon",
                "title": "РУНА МУДРОСТИ (EXP)",
                "text": f"Руна Мудрости через {sec_to_wisdom}с! Займите позицию у края карты",
                "severity": "critical",
                "sound": "wisdom_soon",
                "tts": "Руна мудрости через двадцать секунд" if sec_to_wisdom <= 25 else None
            })

        # 4. Power Runes (every 120s from 6:00 = 360s)
        if clock_time >= 360:
            power_mod = clock_time % 120
            sec_to_power = 120 - power_mod
        else:
            sec_to_power = 360 - clock_time
        
        timers.append({
            "id": "power_rune",
            "name": "Активная Руна",
            "seconds_left": sec_to_power,
            "next_at_clock": self.format_clock(clock_time + sec_to_power),
            "icon": "power_rune"
        })
        if sec_to_power <= 20:
            alerts.append({
                "id": "power_soon",
                "title": "АКТИВНАЯ РУНА",
                "text": f"Руна на реке через {sec_to_power}с! Подготовьте вард или контроль",
                "severity": "info",
                "sound": "power_soon"
            })

        # 5. Tormentor (Терзатель)
        if clock_time < 1200:
            sec_to_tormentor = 1200 - clock_time
            timers.append({
                "id": "tormentor",
                "name": "Терзатель (Шард)",
                "seconds_left": sec_to_tormentor,
                "next_at_clock": "20:00",
                "icon": "tormentor"
            })
            if sec_to_tormentor <= 60:
                alerts.append({
                    "id": "tormentor_soon",
                    "title": "ТЕРЗАТЕЛЬ (20:00)",
                    "text": "Через 1 минуту спавнится Терзатель! Соберитесь командой за Шардом",
                    "severity": "warning",
                    "sound": "tormentor_soon",
                    "tts": "Терзатель через двадцать секунд" if sec_to_tormentor <= 25 else None
                })

        # 6. Stacking Alert (:48 to :55 of each minute, silenced after 16:00 unless toggled)
        sec_in_min = clock_time % 60
        allow_stack = (clock_time < 960) or self.stack_alerts_enabled_midgame
        if allow_stack and 48 <= sec_in_min <= 54:
            alerts.append({
                "id": "stack_camps",
                "title": "ТАЙМИНГ СТАКА",
                "text": f"Секунда {sec_in_min}s! Ударьте лесной кемп и уводите крипов для стака!",
                "severity": "warning" if is_support else "info",
                "sound": "stack_alert",
                "tts": "Стакни лес"
            })

        # 7. Day / Night Cycle (Day -> Bottom/Radiant pit, Night -> Top/Dire pit)
        is_day = daytime if daytime is not None else (((clock_time // 300) % 2) == 0)
        sec_to_cycle = 300 - (clock_time % 300)
        day_night_name = "День" if is_day else "Ночь"
        next_cycle_genitive = "ночи" if is_day else "дня"
        day_night_title = f"{day_night_name} (до {next_cycle_genitive} {sec_to_cycle}с)"

        # 8. Hybrid Roshan Tracker with future pit location calculation
        aegis_left = 0
        chat_string = ""

        if self.roshan_death_time is not None:
            elapsed = clock_time - self.roshan_death_time
            aegis_end = self.roshan_death_time + 300
            rosh_min = self.roshan_death_time + 480
            rosh_max = self.roshan_death_time + 660
            chat_string = f"{self.format_clock(aegis_end)} Aegis | {self.format_clock(rosh_min)} - {self.format_clock(rosh_max)} Roshan"

            # Future respawn pit based on 5-minute cycle parity at rosh_min (clock_time + 480)
            respawn_time = rosh_min
            is_day_at_respawn = ((respawn_time // 300) % 2 == 0)
            pit_location = "Нижнее логово (Radiant)" if is_day_at_respawn else "Верхнее логово (Dire)"

            # Aegis (300s)
            if not self.aegis_expired and elapsed < 300:
                aegis_left = 300 - elapsed
                if 10 < aegis_left <= 30:
                    alerts.append({
                        "id": "aegis_warn_30",
                        "title": "АЕГИС СКОРО ИСТЕКАЕТ",
                        "text": f"Аегис исчезнет через {aegis_left}с! Готовьтесь к аккуратной позиции",
                        "severity": "warning",
                        "sound": "lotus_soon",
                        "tts": "Аегис закончится через тридцать секунд"
                    })
                elif aegis_left <= 10:
                    alerts.append({
                        "id": "aegis_warn_10",
                        "title": "АЕГИС: ПОСЛЕДНИЕ СЕКУНДЫ!",
                        "text": f"Аегис пропадёт через {aegis_left}с!",
                        "severity": "critical",
                        "sound": "wisdom_soon",
                        "tts": "Аегис закончится через десять секунд"
                    })
            else:
                self.aegis_expired = True
                aegis_left = 0

            # Respawn window (480s - 660s)
            if elapsed < 480:
                rosh_status = "respawning"
                min_sec = 480 - elapsed
                rosh_window_str = f"Мин. спавн: {self.format_clock(min_sec)}"
            elif elapsed <= 660:
                rosh_status = "in_window"
                max_sec = 660 - elapsed
                rosh_window_str = f"Окно респавна! (до {self.format_clock(max_sec)})"
                alerts.append({
                    "id": "roshan_window_alert",
                    "title": "РОШАН В ОКНЕ РЕСПАВНА!",
                    "text": f"Рошан может появиться в любую секунду! Проверьте {pit_location}",
                    "severity": "warning"
                })
            else:
                rosh_status = "alive"
                rosh_window_str = "Жив"
                self.roshan_death_time = None
        else:
            # If alive, pit location is based on current clock time parity
            current_is_day = ((clock_time // 300) % 2 == 0) if clock_time >= 0 else True
            pit_location = "Нижнее логово (Radiant)" if current_is_day else "Верхнее логово (Dire)"
            rosh_status = "alive"
            rosh_window_str = "Жив"

        # 9. Enemy Glyph Cooldown (300s)
        glyph_left = 0
        if self.glyph_cooldown_start is not None:
            g_elapsed = clock_time - self.glyph_cooldown_start
            if g_elapsed < 300:
                glyph_left = 300 - g_elapsed
                glyph_status = f"{self.format_clock(glyph_left)}"
            else:
                self.glyph_cooldown_start = None
                glyph_status = "Готов"
        else:
            glyph_status = "Готов"

        roshan_info = {
            "status": rosh_status,
            "window": rosh_window_str,
            "aegis_left": aegis_left,
            "aegis_expired": self.aegis_expired,
            "pit_location": pit_location,
            "chat_string": chat_string
        }

        glyph_info = {
            "seconds_left": glyph_left,
            "status": glyph_status,
            "is_on_cooldown": (glyph_left > 0)
        }

        sorted_timers = sorted(timers, key=lambda x: x["seconds_left"])

        return {
            "clock_formatted": self.format_clock(clock_time),
            "clock_seconds": clock_time,
            "daytime": is_day,
            "day_night_title": day_night_title,
            "timers": sorted_timers,
            "active_alerts": alerts,
            "roshan": roshan_info,
            "glyph": glyph_info
        }

    # ==========================================
    # 7. DYNAMIC SITUATIONAL ITEM ADVISOR
    # ==========================================
    def recommend_items(self, enemy_heroes: List[Any], current_player_items: List[str] = []) -> List[Dict[str, Any]]:
        enemy_objs = [self.get_hero_by_identifier(h) for h in enemy_heroes if self.get_hero_by_identifier(h)]
        enemy_names = {e["name"] for e in enemy_objs}
        enemy_tags = set()
        for e in enemy_objs:
            enemy_tags.update(e.get("tags", []))

        bought_items = set(current_player_items)
        recommendations = []

        for item in self.items_data:
            item_id = item["id"]
            if item_id in bought_items:
                continue

            matches = False
            reasons = []

            trig_heroes = item.get("trigger_heroes", [])
            for th in trig_heroes:
                if th in enemy_names:
                    matches = True
                    hero_obj = self.get_hero_by_identifier(th)
                    d_name = hero_obj["display_name"] if hero_obj else th
                    reasons.append(f"Против {d_name}")

            trig_tags = item.get("trigger_tags", [])
            for tt in trig_tags:
                if tt in enemy_tags:
                    matches = True
                    if tt == "evasion":
                        reasons.append("У врагов есть уклонение")
                    elif tt == "high_regen":
                        reasons.append("Высокая регенерация у врагов")
                    elif tt == "magic_burst":
                        reasons.append("Опасный маг. прокаст")
                    elif tt == "invis":
                        reasons.append("У врагов невидимость")
                    elif tt == "illusion":
                        reasons.append("У врагов иллюзии")

            if matches:
                clean_name = item["id"].replace("item_", "")
                steam_cdn_url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{clean_name}.png"
                recommendations.append({
                    "id": item["id"],
                    "name": item["name"],
                    "icon": item.get("icon", ""),
                    "image_url": steam_cdn_url,
                    "priority": item.get("priority", 5),
                    "advice": item.get("advice_ru", ""),
                    "reasons": reasons[:2]
                })

        recommendations.sort(key=lambda x: x["priority"], reverse=True)
        return recommendations[:5]

    # ==========================================
    # 8. DAMAGE BREAKDOWN (THEORETICAL ENEMY DRAFT)
    # ==========================================
    def calculate_damage_breakdown(self, enemy_heroes: List[Any]) -> Dict[str, Any]:
        """
        Calculates theoretical damage type breakdown (Physical, Magical, Pure)
        based on the composition of the enemy draft, and returns counter-item defensive advice.
        """
        if not enemy_heroes:
            return {
                "physical_pct": 50,
                "magical_pct": 42,
                "pure_pct": 8,
                "primary_threat": "physical",
                "advice": "Сбалансированный урон врагов. Держите базовую броню и готовьте Black King Bar к мидгейму."
            }

        enemy_objs = [self.get_hero_by_identifier(h) for h in enemy_heroes if self.get_hero_by_identifier(h)]
        if not enemy_objs:
            return {
                "physical_pct": 50,
                "magical_pct": 42,
                "pure_pct": 8,
                "primary_threat": "physical",
                "advice": "Сбалансированный урон врагов. Держите базовую броню и готовьте Black King Bar к мидгейму."
            }

        phys_score = 0.0
        magic_score = 0.0
        pure_score = 0.0

        pure_tags = {
            "pure_damage", "chakram_pure", "pure_arcane_orb", "pure_glaives",
            "purification_pure", "sonic_wave_pure", "midnight_pulse_pure",
            "infernal_blade", "sun_ray_percent_heal", "percentage_damage"
        }
        magic_tags = {
            "magic_burst", "aoe_magic", "aoe_magic_burst", "finger_of_death",
            "macropyre", "mystic_flare_burst", "pulse_nova", "global_magic",
            "call_down_nuke", "eclipse_magic", "magic_rightclick", "cataclysm",
            "rearm_burst", "chain_frost", "sanity_eclipse"
        }
        phys_tags = {
            "high_physical", "physical_burst", "ranged_physical", "cleave",
            "massive_crits", "swashbuckle_slash", "fury_swipes", "tidebringer",
            "jingu_mastery", "walrus_punch_crit", "quill_spray", "focus_fire",
            "split_shot", "fast_attack_speed", "minus_armor", "backstab"
        }

        for hero in enemy_objs:
            attr = hero.get("attr", "str")
            tags = set(hero.get("tags", []))

            if attr == "agi":
                h_phys = 7.0
                h_magic = 2.0
                h_pure = 0.5
            elif attr == "int":
                h_phys = 1.5
                h_magic = 8.0
                h_pure = 1.0
            else:  # str / universal
                h_phys = 5.0
                h_magic = 4.5
                h_pure = 1.0

            for tag in tags:
                if tag in pure_tags:
                    h_pure += 5.5
                if tag in magic_tags:
                    h_magic += 4.5
                if tag in phys_tags:
                    h_phys += 4.5

            phys_score += h_phys
            magic_score += h_magic
            pure_score += h_pure

        total = phys_score + magic_score + pure_score
        if total <= 0:
            total = 1.0

        p_pct = int(round((phys_score / total) * 100))
        m_pct = int(round((magic_score / total) * 100))
        u_pct = 100 - (p_pct + m_pct)
        if u_pct < 0:
            p_pct += u_pct
            u_pct = 0

        if u_pct >= 18:
            primary = "pure"
            advice = f"Опасный чистый урон ({u_pct}%)! Броня и маг. резист не спасают от чистого урона. Собирайте максимум HP (Heart of Tarrasque, Eye of Skadi, Sange & Yasha)."
        elif m_pct >= 52:
            primary = "magical"
            advice = f"Высокий маг. урон врагов ({m_pct}%)! Приоритет: Black King Bar, Pipe of Insight, Mage Slayer, Glimmer Cape."
        elif p_pct >= 55:
            primary = "physical"
            advice = f"Преобладает физ. урон ({p_pct}%)! Приоритет: Shiva's Guard, Assault Cuirass, Crimson Guard, Ghost Scepter, Butterfly."
        else:
            primary = "balanced"
            advice = f"Сбалансированный урон ({p_pct}% физ / {m_pct}% маг). Сбалансируйте защиту: BKB против заклинаний и базовую броню против кликов."

        return {
            "physical_pct": p_pct,
            "magical_pct": m_pct,
            "pure_pct": u_pct,
            "primary_threat": primary,
            "advice": advice
        }

    # ==========================================
    # 9. FULL DOTA PLUS ITEM BUILD PROGRESSION
    # ==========================================
    def get_item_progression(self, hero_identifier: Any, role: str = "Carry") -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns authentic Dota Plus item build stages for each distinct hero:
        Starting Items, Early Game, Core Items, and Luxury / Late Game.
        Uses comprehensive hero build database with distinct items for every hero.
        """
        hero_obj = self.get_hero_by_identifier(hero_identifier)
        hero_name = hero_obj.get("name", "") if hero_obj else str(hero_identifier or "")

        build_raw = get_hero_build_raw(hero_name, hero_obj or {}, role)

        result: Dict[str, List[Dict[str, Any]]] = {}
        for stage, items in build_raw.items():
            stage_items = []
            for item_id in items:
                title, cost = ITEM_CATALOG.get(item_id, (item_id.replace("item_", "").replace("_", " ").title(), 0))
                clean_name = item_id.replace("item_", "")
                img_url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{clean_name}.png"
                stage_items.append({
                    "id": item_id,
                    "name": title,
                    "cost": cost,
                    "image_url": img_url
                })
            result[stage] = stage_items

        return result

    def get_next_recommended_item(
        self,
        hero_identifier: Any,
        role: str = "Carry",
        current_gold: int = 0,
        current_inventory: Optional[List[str]] = None,
        clock_time: int = 0,
        enemy_heroes: Optional[List[Any]] = None,
        current_gpm: int = 0
    ) -> Dict[str, Any]:
        """
        Dynamically analyzes the match context and recommends the single best item to buy RIGHT NOW.
        Continuously adapts based on:
        - Player's owned items (excludes already purchased items and previous components)
        - Current gold and remaining gold needed
        - Percentage progress bar (0% - 100%)
        - Counter-item urgency (e.g., enemy magic burst >= 40% -> urgent BKB; evasion -> MKB; passives -> Silver Edge)
        - Step-by-step next component suggestion (e.g. Ogre Axe, Broadsword, Cornucopia)
        """
        if current_inventory is None:
            current_inventory = []
        if enemy_heroes is None:
            enemy_heroes = []

        hero_obj = self.get_hero_by_identifier(hero_identifier)
        hero_raw_name = hero_obj.get("name", "") if hero_obj else str(hero_identifier or "")

        # 1. Normalize owned items into clean IDs
        owned = set()
        for item in current_inventory:
            if not item:
                continue
            item_str = str(item).lower().strip()
            if not item_str.startswith("item_"):
                item_str = f"item_{item_str}"
            owned.add(item_str)

        # Handle upgrade chains (if player owns higher-tier item, lower tier counts as owned)
        UPGRADE_MAP = {
            "item_abyssal_blade": ["item_basher", "item_vanguard"],
            "item_hurricane_pike": ["item_dragon_lance", "item_force_staff"],
            "item_mjollnir": ["item_maelstrom"],
            "item_disperser": ["item_diffusal_blade"],
            "item_silver_edge": ["item_shadow_blade"],
            "item_bloodthorn": ["item_orchid", "item_mage_slayer"],
            "item_harpoon": ["item_echo_sabre"],
            "item_octarine_core": ["item_aether_lens"],
            "item_spirit_vessel": ["item_urn_of_shadows"],
            "item_crimson_guard": ["item_vanguard"],
            "item_wind_waker": ["item_cyclone"],
            "item_parasma": ["item_witch_blade"],
            "item_overwhelming_blink": ["item_blink"],
            "item_swift_blink": ["item_blink"],
            "item_arcane_blink": ["item_blink"],
            "item_power_treads": ["item_boots"],
            "item_phase_boots": ["item_boots"],
            "item_arcane_boots": ["item_boots"],
            "item_tranquil_boots": ["item_boots"],
            "item_travel_boots": ["item_boots"],
        }
        for higher, lowers in UPGRADE_MAP.items():
            if higher in owned:
                for low in lowers:
                    owned.add(low)

        # 2. Check urgent counter-item priorities based on enemies
        urgent_target: Optional[tuple[str, str]] = None
        dmg_profile = self.calculate_damage_breakdown(enemy_heroes)
        magic_pct = dmg_profile.get("magical_pct", dmg_profile.get("magic_pct", 0))

        # A) Urgent BKB against magic burst / heavy crowd control (when enemies are detected/specified)
        if enemy_heroes and magic_pct >= 42 and clock_time >= 480 and "item_black_king_bar" not in owned:
            urgent_target = (
                "item_black_king_bar",
                f"У врагов {magic_pct}% маг. урона! Срочный BKB для выживания в драках."
            )

        # B) Urgent MKB against evasion
        if not urgent_target and clock_time >= 900 and "item_monkey_king_bar" not in owned:
            has_evasion = False
            for eh in enemy_heroes:
                e_obj = self.get_hero_by_identifier(eh)
                if e_obj:
                    e_name = e_obj.get("name", "").lower()
                    if any(ev in e_name for ev in ["phantom_assassin", "windrunner", "brewmaster"]):
                        has_evasion = True
                        break
            if has_evasion:
                urgent_target = (
                    "item_monkey_king_bar",
                    "Контрпик: пробитие уклонения (True Strike) против вражеских промахов!"
                )

        # C) Urgent Silver Edge against passives
        if not urgent_target and clock_time >= 720 and "item_silver_edge" not in owned:
            has_passives = False
            for eh in enemy_heroes:
                e_obj = self.get_hero_by_identifier(eh)
                if e_obj:
                    e_name = e_obj.get("name", "").lower()
                    if any(pv in e_name for pv in ["bristleback", "spectre", "huskar", "shredder"]):
                        has_passives = True
                        break
            if has_passives and role.lower() in ["carry", "pos 1", "mid", "pos 2", "offlane", "pos 3"]:
                urgent_target = (
                    "item_silver_edge",
                    "Контрпик: отключение пассивок (Break) против Bristleback / Spectre!"
                )

        # 3. Retrieve hero progression build
        build_raw = get_hero_build_raw(hero_raw_name, hero_obj or {}, role)

        chosen_id: Optional[str] = None
        chosen_reason = "Рекомендуемый предмет по таймингу игры"
        urgency = "normal"
        stage_label = "Ядро"

        CORE_REASONS = {
            "item_bfury": "⚔️ Battle Fury — ускорение фарма и зачистка лесных стаков",
            "item_manta": "⚡ Manta Style — сброс дебаффов и сплитпуш иллюзиями",
            "item_blink": "🌪️ Blink Dagger — ключевая инициация и позиционка в драке",
            "item_blade_mail": "🛡️ Blade Mail — возврат урона и выживаемость при фокусе",
            "item_desolator": "💀 Desolator — срез брони и быстрый снос строений",
            "item_diffusal_blade": "⚡ Diffusal Blade — выжигание маны и контроль мобильности",
            "item_basher": "🔨 Skull Basher — пробитие неуязвимости к магии станом",
            "item_abyssal_blade": "🔨 Abyssal Blade — гарантированный контроль сквозь BKB",
            "item_butterfly": "🦋 Butterfly — уклонение и колоссальный физ. урон",
            "item_satanic": "🩸 Satanic — выживаемость и мгновенный отжор в драке",
            "item_skadi": "❄️ Eye of Skadi — срез лечения врага и замедление",
            "item_shivas_guard": "❄️ Shiva's Guard — аура замедления и защита от физ. урона",
            "item_heart": "❤️ Heart of Tarrasque — максимальная плотность и реген здоровья",
            "item_glimmer_cape": "✨ Glimmer Cape — невидимость и маг. барьер для спасения",
            "item_force_staff": "💨 Force Staff — разрыв дистанции и спасение союзников",
            "item_aether_lens": "🔮 Aether Lens — дальность применения способностей",
            "item_octarine_core": "⏱️ Octarine Core — срез перезарядки всех скиллов и предметов",
            "item_pipe": "🛡️ Pipe of Insight — командный барьер от магического прокаста",
            "item_crimson_guard": "🛡️ Crimson Guard — командный блок физического урона",
            "item_lotus_orb": "🌸 Lotus Orb — сброс дебаффов и отражение таргетных заклинаний",
            "item_heavens_halberd": "🗡️ Heaven's Halberd — обезоруживание вражеского керри",
            "item_witch_blade": "🧙 Witch Blade — замедление и периодический урон от интеллекта",
            "item_spirit_vessel": "🏺 Spirit Vessel — срез вампиризма и процентный урон",
            "item_urn_of_shadows": "🏺 Urn of Shadows — ранний урон и лечение после киллов",
            "item_phase_boots": "👢 Phase Boots — урон и скорость бега сквозь крипов",
            "item_power_treads": "👢 Power Treads — переключение статов и скорость атаки",
            "item_arcane_boots": "👢 Arcane Boots — манапул для себя и команды"
        }

        if urgent_target:
            chosen_id, chosen_reason = urgent_target
            urgency = "urgent"
            stage_label = "Срочный контрпик"
        else:
            # Check stages in chronological priority
            early_candidates = [it for it in build_raw.get("early_game", []) if it not in owned]
            core_candidates = [it for it in build_raw.get("core", []) if it not in owned]
            luxury_candidates = [it for it in build_raw.get("luxury", []) if it not in owned]

            if clock_time < 360 and early_candidates:
                chosen_id = early_candidates[0]
                stage_label = "Ранняя игра"
                chosen_reason = CORE_REASONS.get(chosen_id, "Стартовый разгон: статы и скорость передвижения на линии")
            elif core_candidates:
                chosen_id = core_candidates[0]
                stage_label = "Ядро"
                chosen_reason = CORE_REASONS.get(chosen_id, "Ключевой артефакт билда для боевой эффективности")
            elif luxury_candidates:
                chosen_id = luxury_candidates[0]
                stage_label = "Лейт / Роскошь"
                chosen_reason = CORE_REASONS.get(chosen_id, "Финальное усиление для победы в поздней стадии")
            elif early_candidates:
                chosen_id = early_candidates[0]
                stage_label = "Ранняя игра"
                chosen_reason = CORE_REASONS.get(chosen_id, "Добор ранних статов и расходников")
            else:
                chosen_id = "item_moon_shard" if "item_moon_shard" not in owned else "item_rapier"
                stage_label = "Ультра-лейт"
                chosen_reason = "Финальный слот"

        # 4. Construct response item metadata
        clean_name = chosen_id.replace("item_", "")
        title, cost = ITEM_CATALOG.get(chosen_id, (clean_name.replace("_", " ").title(), 2000))
        gold_needed = max(0, cost - current_gold)
        progress_pct = min(100, int((current_gold / cost) * 100)) if cost > 0 else 100
        can_buy_now = (current_gold >= cost)

        eta_seconds: Optional[int] = None
        if gold_needed > 0 and current_gpm > 50:
            gps = current_gpm / 60.0
            eta_seconds = int(gold_needed / gps)

        # Slot completion status without micro-component spam
        if can_buy_now:
            slot_status_text = "Готов к покупке целиком!"
        else:
            eta_str = f" (~{max(1, eta_seconds // 60)} мин)" if eta_seconds else ""
            slot_status_text = f"Осталось: {gold_needed:,} 💰{eta_str}".replace(",", " ")

        img_url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{clean_name}.png"

        return {
            "id": chosen_id,
            "name": title,
            "cost": cost,
            "current_gold": current_gold,
            "gold_needed": gold_needed,
            "progress_pct": progress_pct,
            "can_buy_now": can_buy_now,
            "eta_seconds": eta_seconds,
            "next_component": slot_status_text,
            "comp_affordable": can_buy_now,
            "reason": chosen_reason,
            "urgency": urgency,
            "stage_label": stage_label,
            "image_url": img_url
        }

    # ==========================================
    # 10. ABILITY & TALENT BUILD GUIDE
    # ==========================================
    def get_ability_build(self, hero_identifier: Any, hero_level: int = 1) -> Dict[str, Any]:
        """
        Returns authentic Dota Plus ability progression, compact skill priority line,
        and talent recommendations when approaching level 10, 15, 20, 25.
        """
        hero_obj = self.get_hero_by_identifier(hero_identifier)
        hero_name = hero_obj.get("name", "") if hero_obj else "npc_dota_hero_antimage"
        display_name = hero_obj.get("display_name", "Герой") if hero_obj else "Герой"

        # Standard high-winrate ability leveling sequence (1 to 25)
        build_sequence = [
            {"lvl": 1, "key": "Q", "type": "skill"},
            {"lvl": 2, "key": "W", "type": "skill"},
            {"lvl": 3, "key": "Q", "type": "skill"},
            {"lvl": 4, "key": "E", "type": "skill"},
            {"lvl": 5, "key": "Q", "type": "skill"},
            {"lvl": 6, "key": "R", "type": "ult"},
            {"lvl": 7, "key": "Q", "type": "skill"},
            {"lvl": 8, "key": "W", "type": "skill"},
            {"lvl": 9, "key": "W", "type": "skill"},
            {"lvl": 10, "key": "T10", "type": "talent"},
            {"lvl": 11, "key": "W", "type": "skill"},
            {"lvl": 12, "key": "R", "type": "ult"},
            {"lvl": 13, "key": "E", "type": "skill"},
            {"lvl": 14, "key": "E", "type": "skill"},
            {"lvl": 15, "key": "T15", "type": "talent"},
            {"lvl": 16, "key": "E", "type": "skill"},
            {"lvl": 18, "key": "R", "type": "ult"},
            {"lvl": 20, "key": "T20", "type": "talent"},
            {"lvl": 25, "key": "T25", "type": "talent"}
        ]

        # Hero-specific talent trees
        TALENT_TREES: Dict[str, Dict[int, Dict[str, Any]]] = {
            "npc_dota_hero_antimage": {
                10: {"left": "+9 к силе", "right": "+11 к ловкости", "recommended": "right", "winrate": 53.4, "pickrate": 78},
                15: {"left": "-1с перезарядки Blink", "right": "+0.6% урона от сожжения маны", "recommended": "left", "winrate": 54.2, "pickrate": 84},
                20: {"left": "+250 к дальности прыжка Blink", "right": "-40с перезарядки Mana Void", "recommended": "left", "winrate": 56.1, "pickrate": 71},
                25: {"left": "-50с перезарядки Mana Void", "right": "+20% к Counterspell пассивно", "recommended": "right", "winrate": 58.7, "pickrate": 65}
            },
            "npc_dota_hero_axe": {
                10: {"left": "+12% к скорости передвижения", "right": "+20 к урону от Berserker's Call", "recommended": "left", "winrate": 52.8, "pickrate": 82},
                15: {"left": "+30 к урону от Counter Helix", "right": "+10% к замедлению Battle Hunger", "recommended": "left", "winrate": 54.5, "pickrate": 88},
                20: {"left": "+1 к радиусу Berserker's Call", "right": "+150 к порогу Culling Blade", "recommended": "right", "winrate": 55.9, "pickrate": 76},
                25: {"left": "Counter Helix пробивает БКБ", "right": "+100 к броне от Berserker's Call", "recommended": "left", "winrate": 58.2, "pickrate": 81}
            },
            "npc_dota_hero_juggernaut": {
                10: {"left": "+5 к броне", "right": "+150 к радиусу Blade Fury", "recommended": "right", "winrate": 53.1, "pickrate": 74},
                15: {"left": "-20с к КД Healing Ward", "right": "+20 к скорости атаки", "recommended": "right", "winrate": 54.8, "pickrate": 80},
                20: {"left": "+1с к длительности Blade Fury", "right": "+50% урона от Blade Dance критов", "recommended": "right", "winrate": 56.3, "pickrate": 85},
                25: {"left": "+1с к длительности Omnislash", "right": "+475 к здоровью", "recommended": "left", "winrate": 59.1, "pickrate": 89}
            },
            "npc_dota_hero_phantom_assassin": {
                10: {"left": "+0.5с длительности Phantom Strike", "right": "+150 к здоровью", "recommended": "left", "winrate": 52.6, "pickrate": 79},
                15: {"left": "+25% к уклонению Blur", "right": "+20 к урону", "recommended": "left", "winrate": 54.9, "pickrate": 83},
                20: {"left": "+25% к вампиризму", "right": "Тройной кинжал Stifling Dagger", "recommended": "right", "winrate": 57.4, "pickrate": 91},
                25: {"left": "+7% шанса Coup de Grace", "right": "+250 к дальности атаки", "recommended": "left", "winrate": 60.1, "pickrate": 86}
            },
            "npc_dota_hero_pudge": {
                10: {"left": "+4 к броне", "right": "+20 к урону Rot", "recommended": "right", "winrate": 52.4, "pickrate": 76},
                15: {"left": "-10% снижения урона Flesh Heap", "right": "+120 к урону Meat Hook", "recommended": "left", "winrate": 54.1, "pickrate": 81},
                20: {"left": "-4с перезарядки Meat Hook", "right": "+0.8с длительности Dismember", "recommended": "left", "winrate": 55.7, "pickrate": 74},
                25: {"left": "1.5x силы от Flesh Heap", "right": "+1.5x урона Rot", "recommended": "left", "winrate": 58.4, "pickrate": 85}
            }
        }

        talents = TALENT_TREES.get(hero_name)
        if not talents:
            talents = {
                10: {"left": "+200 к здоровью", "right": "+15 к скорости атаки", "recommended": "left", "winrate": 52.5, "pickrate": 68},
                15: {"left": "-3с к перезарядке Q", "right": "+25 к урону", "recommended": "right", "winrate": 54.0, "pickrate": 72},
                20: {"left": "+25% к маг. резисту", "right": "+1.5с к длительности контроля", "recommended": "right", "winrate": 56.2, "pickrate": 78},
                25: {"left": "+25% к вампиризму", "right": "+2 заряда ключевой способности", "recommended": "right", "winrate": 58.9, "pickrate": 83}
            }

        PRIORITIES = {
            "npc_dota_hero_antimage": "Max Q ➔ W ➔ E",
            "npc_dota_hero_axe": "Max E ➔ Q ➔ W",
            "npc_dota_hero_juggernaut": "Max Q ➔ E ➔ W",
            "npc_dota_hero_phantom_assassin": "Max Q ➔ E ➔ W",
            "npc_dota_hero_pudge": "Max W ➔ Q ➔ E",
            "npc_dota_hero_invoker": "Exort ➔ Wex ➔ Quas",
            "npc_dota_hero_crystal_maiden": "Max Q ➔ W ➔ E",
            "npc_dota_hero_sniper": "Max Q ➔ E ➔ W",
            "npc_dota_hero_faceless_void": "Max Q ➔ E ➔ W",
            "npc_dota_hero_legion_commander": "Max Q ➔ W ➔ E",
            "npc_dota_hero_slark": "Max Q ➔ E ➔ W",
            "npc_dota_hero_drow_ranger": "Max E ➔ Q ➔ W",
            "npc_dota_hero_storm_spirit": "Max Q ➔ E ➔ W",
            "npc_dota_hero_earthshaker": "Max Q ➔ E ➔ W",
            "npc_dota_hero_sven": "Max Q ➔ E ➔ W"
        }
        skill_priority = PRIORITIES.get(hero_name, "Max Q ➔ W ➔ E")

        # Talent alert only near level 10, 15, 20, 25 (9-10, 14-15, 19-20, 24-25)
        show_talent = hero_level in [9, 10, 14, 15, 19, 20, 24, 25]
        active_tier = 10 if hero_level in [9, 10] else (15 if hero_level in [14, 15] else (20 if hero_level in [19, 20] else (25 if hero_level in [24, 25] else None)))
        active_talent = talents.get(active_tier) if active_tier else None

        return {
            "hero_name": hero_name,
            "display_name": display_name,
            "skill_priority": skill_priority,
            "show_talent": show_talent,
            "active_tier": active_tier,
            "active_talent": active_talent,
            "sequence": build_sequence,
            "talents": talents
        }

    @staticmethod
    def format_clock(seconds: int) -> str:
        sign = "-" if seconds < 0 else ""
        sec = abs(seconds)
        m = sec // 60
        s = sec % 60
        return f"{sign}{m:02d}:{s:02d}"
