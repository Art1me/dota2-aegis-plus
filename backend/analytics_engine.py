import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).parent.parent / "data"

class AnalyticsEngine:
    def __init__(self):
        self.heroes_data: Dict[str, Any] = {}
        self.benchmarks_data: Dict[str, Any] = {}
        self.items_data: List[Dict[str, Any]] = []
        self._load_datasets()
        
        # Mapping by hero name and hero id
        self.hero_by_id: Dict[str, Dict[str, Any]] = {}
        self.hero_by_name: Dict[str, Dict[str, Any]] = {}
        self._build_hero_indexes()

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
    # 1. DRAFT ANALYTICS & COUNTER RECOMMENDER
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
    # 2. LIVE GAME PERFORMANCE & BENCHMARKING
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
        buyback_cooldown: int = 0
    ) -> Dict[str, Any]:
        """
        Compares player's in-game stats against rank benchmarks and calculates buyback
        with unreliable gold loss upon death accounted for.
        """
        minute = max(1, math.floor(clock_time / 60)) if clock_time > 0 else 0
        rank_data = self.benchmarks_data.get("benchmarks", {}).get(rank, {}).get(role, {})

        if not rank_data:
            rank_data = self.benchmarks_data.get("benchmarks", {}).get(rank, {}).get("Carry", {})

        target_cs, target_nw, target_gpm, target_xpm = self._interpolate_benchmark(rank_data, minute)

        delta_cs = current_cs - target_cs
        delta_nw = current_networth - target_nw
        delta_gpm = current_gpm - target_gpm
        delta_xpm = current_xpm - target_xpm

        score_pct = 100.0
        if target_nw > 0:
            score_pct = (current_networth / target_nw) * 100.0

        if score_pct >= 115:
            grade = "S"
            grade_label = "Доминирование"
            grade_color = "#10B981" # Green
        elif score_pct >= 95:
            grade = "A"
            grade_label = "В графике ранга"
            grade_color = "#3B82F6" # Blue
        elif score_pct >= 80:
            grade = "B"
            grade_label = "Отставание"
            grade_color = "#F59E0B" # Yellow
        else:
            grade = "C"
            grade_label = "Критически позади"
            grade_color = "#EF4444" # Red

        # Buyback calculation
        bb_cost = hero_buyback_cost if hero_buyback_cost else int(200 + (current_networth / 13))
        
        # Loss of unreliable gold upon death
        death_penalty = min(gold_unreliable, current_networth // 40) if hero_alive else 0
        gold_after_death = max(0, current_gold - death_penalty)
        surplus = current_gold - bb_cost
        surplus_after_death = gold_after_death - bb_cost

        # 4 Explicit Statuses: COOLDOWN, READY, AT_RISK, DEFICIT
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

        return {
            "minute": minute,
            "clock_formatted": self.format_clock(clock_time),
            "rank": rank,
            "role": role,
            "grade": grade,
            "grade_label": grade_label,
            "grade_color": grade_color,
            "score_pct": round(score_pct, 1),
            "benchmarks": {
                "target_cs": target_cs,
                "current_cs": current_cs,
                "delta_cs": delta_cs,
                "target_nw": target_nw,
                "current_nw": current_networth,
                "delta_nw": delta_nw,
                "target_gpm": target_gpm,
                "current_gpm": current_gpm,
                "delta_gpm": delta_gpm,
                "target_xpm": target_xpm,
                "current_xpm": current_xpm,
                "delta_xpm": delta_xpm
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
                "surplus_after_death": surplus_after_death
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
    # 3. INVENTORY INSPECTION
    # ==========================================
    def inspect_inventory(self, items_data: Dict[str, Any], clock_time: int) -> List[Dict[str, Any]]:
        """
        Inspects items block in GSI:
        - Neutral slot neutral0 (empty or outdated tier after 7, 17, 27, 37, 60m)
        - Teleport slot teleport0 (missing after 4:00)
        - Active item without CD in backpack (slot6..slot8) with empty/branch slots in main (slot0..slot5)
        """
        alerts = []
        if clock_time <= 0 or not items_data:
            return alerts

        # 1. Neutral Item Check
        expected_tier = 0
        if clock_time >= 3600: # 60 min
            expected_tier = 5
        elif clock_time >= 2220: # 37 min
            expected_tier = 4
        elif clock_time >= 1620: # 27 min
            expected_tier = 3
        elif clock_time >= 1020: # 17 min
            expected_tier = 2
        elif clock_time >= 420: # 7 min
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

        # 2. Teleport Scroll Check (after 4:00 = 240s)
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

        # 3. Backpack Active Items vs Main Inventory Free/Branch Slots
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
    # 4. MACRO RADAR & TIMERS ENGINE
    # ==========================================
    def get_macro_timers(
        self,
        clock_time: int,
        roshan_death_time: Optional[int] = None,
        role: str = "Carry"
    ) -> Dict[str, Any]:
        """
        Calculates upcoming map objectives with role-based filtering:
        - Water Runes (2:00, 4:00) for Mid
        - Lotus Pools (every 3m = 180s)
        - Wisdom Runes (every 7m = 420s)
        - Power Runes (every 2m starting from 6:00 = 360s)
        - Bounty Runes (every 3m = 180s)
        - Tormentor (at 20:00 = 1200s)
        - Camp Stacking alert (:48 - :54 of every minute)
        - Day/Night (every 5m = 300s, with proper Russian declension)
        """
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
                }]
            }

        timers = []
        alerts = []
        r_lower = role.lower()
        is_mid = "mid" in r_lower or "pos 2" in r_lower
        is_support = "support" in r_lower or "pos 4" in r_lower or "pos 5" in r_lower

        # 1. Water Runes (Руны Воды: 2:00 = 120s, 4:00 = 240s)
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
                "sound": "wisdom_soon"
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
                    "sound": "tormentor_soon"
                })

        # 6. Stacking Alert (:48 to :55 of each minute)
        sec_in_min = clock_time % 60
        if 48 <= sec_in_min <= 54:
            alerts.append({
                "id": "stack_camps",
                "title": "ТАЙМИНГ СТАКА",
                "text": f"Секунда {sec_in_min}s! Ударьте лесной кемп и уводите крипов для стака!",
                "severity": "warning" if is_support else "info",
                "sound": "stack_alert"
            })

        # 7. Day / Night Cycle (fixed Russian declension: "до ночи", "до дня")
        is_day = ((clock_time // 300) % 2) == 0
        sec_to_cycle = 300 - (clock_time % 300)
        day_night_name = "День" if is_day else "Ночь"
        next_cycle_genitive = "ночи" if is_day else "дня"
        day_night_title = f"{day_night_name} (до {next_cycle_genitive} {sec_to_cycle}с)"

        # 8. Roshan Tracker
        roshan_info = {"status": "alive", "window": "Рошан жив"}
        if roshan_death_time is not None:
            time_since_death = clock_time - roshan_death_time
            if time_since_death < 300: # 5 min Aegis
                roshan_info = {
                    "status": "aegis_active",
                    "window": f"Аегис истекает через {self.format_clock(300 - time_since_death)}"
                }
            elif time_since_death < 480: # 5-8 min Aegis expired, wait for min spawn
                roshan_info = {
                    "status": "respawning",
                    "window": f"Мин. спавн через {self.format_clock(480 - time_since_death)}"
                }
            elif time_since_death <= 660: # 8-11 min random spawn window
                roshan_info = {
                    "status": "in_window",
                    "window": f"Окно респавна! (до {self.format_clock(660 - time_since_death)})"
                }
                alerts.append({
                    "id": "roshan_window",
                    "title": "РОШАН В ОКНЕ РЕСПАВНА",
                    "text": "Рошан может появиться в любую секунду! Проверьте логово",
                    "severity": "warning"
                })

        # Filter and prioritize timers based on role
        sorted_timers = sorted(timers, key=lambda x: x["seconds_left"])

        return {
            "clock_formatted": self.format_clock(clock_time),
            "clock_seconds": clock_time,
            "daytime": is_day,
            "day_night_title": day_night_title,
            "timers": sorted_timers,
            "active_alerts": alerts,
            "roshan": roshan_info
        }

    # ==========================================
    # 5. DYNAMIC SITUATIONAL ITEM ADVISOR
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

    @staticmethod
    def format_clock(seconds: int) -> str:
        sign = "-" if seconds < 0 else ""
        sec = abs(seconds)
        m = sec // 60
        s = sec % 60
        return f"{sign}{m:02d}:{s:02d}"
