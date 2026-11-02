"""
AegisPlus - Comprehensive Dota 2 Hero Builds Database
Contains authentic, distinct, hero-specific builds for Dota 2 heroes,
plus dynamic signature item generator for all heroes.
"""

from typing import Any, Dict, List

ITEM_CATALOG: Dict[str, tuple[str, int]] = {
    "item_tango": ("Tango", 90),
    "item_quelling_blade": ("Quelling Blade", 100),
    "item_branches": ("Iron Branch", 50),
    "item_circlet": ("Circlet", 155),
    "item_slippers": ("Slippers of Agility", 140),
    "item_gauntlets": ("Gauntlets of Strength", 140),
    "item_mantle": ("Mantle of Intelligence", 140),
    "item_faerie_fire": ("Faerie Fire", 65),
    "item_magic_wand": ("Magic Wand", 450),
    "item_power_treads": ("Power Treads", 1400),
    "item_phase_boots": ("Phase Boots", 1500),
    "item_arcane_boots": ("Arcane Boots", 1300),
    "item_tranquil_boots": ("Tranquil Boots", 925),
    "item_boots": ("Boots of Speed", 500),
    "item_travel_boots": ("Boots of Travel", 2000),
    "item_wraith_band": ("Wraith Band", 505),
    "item_bracer": ("Bracer", 505),
    "item_null_talisman": ("Null Talisman", 505),
    "item_bottle": ("Bottle", 675),
    "item_soul_ring": ("Soul Ring", 805),
    "item_corrosion": ("Orb of Corrosion", 925),
    "item_bfury": ("Battle Fury", 4100),
    "item_manta": ("Manta Style", 4600),
    "item_black_king_bar": ("Black King Bar", 4050),
    "item_basher": ("Skull Basher", 2875),
    "item_abyssal_blade": ("Abyssal Blade", 6250),
    "item_butterfly": ("Butterfly", 4975),
    "item_satanic": ("Satanic", 5050),
    "item_skadi": ("Eye of Skadi", 5300),
    "item_swift_blink": ("Swift Blink", 6800),
    "item_overwhelming_blink": ("Overwhelming Blink", 6800),
    "item_arcane_blink": ("Arcane Blink", 6800),
    "item_blink": ("Blink Dagger", 2250),
    "item_blade_mail": ("Blade Mail", 2100),
    "item_aghanims_shard": ("Aghanim's Shard", 1400),
    "item_ultimate_scepter": ("Aghanim's Scepter", 4200),
    "item_heart": ("Heart of Tarrasque", 5100),
    "item_shivas_guard": ("Shiva's Guard", 5175),
    "item_diffusal_blade": ("Diffusal Blade", 2500),
    "item_disperser": ("Disperser", 5700),
    "item_desolator": ("Desolator", 3500),
    "item_nullifier": ("Nullifier", 4375),
    "item_pipe": ("Pipe of Insight", 3725),
    "item_octarine_core": ("Octarine Core", 4800),
    "item_refresher": ("Refresher Orb", 5000),
    "item_sheepstick": ("Scythe of Vyse", 5575),
    "item_glimmer_cape": ("Glimmer Cape", 2150),
    "item_force_staff": ("Force Staff", 2200),
    "item_wind_waker": ("Wind Waker", 6825),
    "item_aeon_disk": ("Aeon Disk", 3000),
    "item_dragon_lance": ("Dragon Lance", 1900),
    "item_hurricane_pike": ("Hurricane Pike", 4450),
    "item_maelstrom": ("Maelstrom", 2700),
    "item_mjollnir": ("Mjollnir", 5500),
    "item_daedalus": ("Daedalus", 5100),
    "item_monkey_king_bar": ("Monkey King Bar", 4900),
    "item_witch_blade": ("Witch Blade", 2600),
    "item_kaya_and_sange": ("Kaya and Sange", 4100),
    "item_sange_and_yasha": ("Sange and Yasha", 4100),
    "item_yasha": ("Yasha", 2050),
    "item_orchid": ("Orchid Malevolence", 3475),
    "item_bloodthorn": ("Bloodthorn", 6800),
    "item_vanguard": ("Vanguard", 1700),
    "item_crimson_guard": ("Crimson Guard", 3725),
    "item_assault": ("Assault Cuirass", 5125),
    "item_lotus_orb": ("Lotus Orb", 3850),
    "item_spirit_vessel": ("Spirit Vessel", 2780),
    "item_urn_of_shadows": ("Urn of Shadows", 880),
    "item_aether_lens": ("Aether Lens", 2275),
    "item_bloodstone": ("Bloodstone", 4400),
    "item_heavens_halberd": ("Heaven's Halberd", 3550),
    "item_silver_edge": ("Silver Edge", 5450),
    "item_shadow_blade": ("Shadow Blade", 3000),
    "item_sphere": ("Linken's Sphere", 4600),
    "item_hand_of_midas": ("Hand of Midas", 2200),
    "item_blood_grenade": ("Blood Grenade", 50),
    "item_clarity": ("Clarity", 50),
    "item_ward_observer": ("Observer Ward", 0),
    "item_ward_sentry": ("Sentry Ward", 50),
    "item_wind_lace": ("Wind Lace", 250),
    "item_rapier": ("Divine Rapier", 5950),
    "item_armlet": ("Armlet of Mordiggian", 2500),
    "item_echo_sabre": ("Echo Sabre", 2700),
    "item_harpoon": ("Harpoon", 4700),
    "item_mage_slayer": ("Mage Slayer", 2625),
    "item_gleipnir": ("Gleipnir", 5650),
    "item_radiance": ("Radiance", 4700),
    "item_mask_of_madness": ("Mask of Madness", 1775),
    "item_morbid_mask": ("Morbid Mask", 900),
    "item_vladmir": ("Vladmir's Offering", 2200),
    "item_ethereal_blade": ("Ethereal Blade", 4650),
    "item_dagon_5": ("Dagon Level 5", 7700),
    "item_parasma": ("Parasma", 5575),
    "item_phylactery": ("Phylactery", 2400),
    "item_khanda": ("Khanda", 5000),
    "item_pavise": ("Pavise", 1400),
    "item_solar_crest": ("Solar Crest", 2700)
}

# Major item components breakdown for intuitive step-by-step guidance
ITEM_COMPONENTS: Dict[str, List[tuple[str, int]]] = {
    "item_bfury": [("Cornucopia", 1200), ("Broadsword", 1000), ("Claymore", 1350), ("Quelling Blade", 100)],
    "item_black_king_bar": [("Ogre Axe", 1000), ("Mithril Hammer", 1600), ("Recipe", 1450)],
    "item_manta": [("Yasha", 2050), ("Diadem", 1000), ("Recipe", 1550)],
    "item_blink": [("Blink Dagger", 2250)],
    "item_blade_mail": [("Broadsword", 1000), ("Chainmail", 550), ("Recipe", 550)],
    "item_diffusal_blade": [("Blade of Alacrity", 1000), ("Robe of the Magi", 450), ("Recipe", 1050)],
    "item_disperser": [("Diffusal Blade", 2500), ("Eagle Song", 2800), ("Recipe", 400)],
    "item_desolator": [("Mithril Hammer", 1600), ("Mithril Hammer", 1600), ("Blight Stone", 300)],
    "item_power_treads": [("Boots of Speed", 500), ("Belt of Strength", 450), ("Gloves of Haste", 450)],
    "item_phase_boots": [("Boots of Speed", 500), ("Chainmail", 550), ("Blades of Attack", 450)],
    "item_arcane_boots": [("Boots of Speed", 500), ("Energy Booster", 800)],
    "item_tranquil_boots": [("Boots of Speed", 500), ("Ring of Regen", 175), ("Wind Lace", 250)],
    "item_travel_boots": [("Boots of Speed", 500), ("Recipe", 1500)],
    "item_magic_wand": [("Magic Stick", 200), ("Iron Branch", 50), ("Iron Branch", 50), ("Recipe", 150)],
    "item_wraith_band": [("Circlet", 155), ("Slippers of Agility", 140), ("Recipe", 210)],
    "item_bracer": [("Circlet", 155), ("Gauntlets of Strength", 140), ("Recipe", 210)],
    "item_null_talisman": [("Circlet", 155), ("Mantle of Intelligence", 140), ("Recipe", 210)],
    "item_corrosion": [("Blight Stone", 300), ("Fluffy Hat", 250), ("Wind Lace", 250), ("Recipe", 125)],
    "item_soul_ring": [("Ring of Regen", 175), ("Gauntlets of Strength", 140), ("Recipe", 490)],
    "item_bottle": [("Bottle", 675)],
    "item_vanguard": [("Ring of Health", 700), ("Vitality Booster", 1000)],
    "item_crimson_guard": [("Vanguard", 1700), ("Helm of Iron Will", 975), ("Recipe", 1050)],
    "item_pipe": [("Cloak", 800), ("Headdress", 425), ("Ring of Health", 700), ("Recipe", 1800)],
    "item_shivas_guard": [("Platemail", 1400), ("Mystic Staff", 2700), ("Recipe", 1075)],
    "item_assault": [("Platemail", 1400), ("Hyperstone", 2000), ("Chainmail", 550), ("Recipe", 1175)],
    "item_heart": [("Reaver", 2800), ("Vitality Booster", 1000), ("Recipe", 1300)],
    "item_lotus_orb": [("Perseverance", 1400), ("Platemail", 1400), ("Energy Booster", 800), ("Recipe", 250)],
    "item_heavens_halberd": [("Sange", 2050), ("Talisman of Evasion", 1300), ("Recipe", 200)],
    "item_maelstrom": [("Mithril Hammer", 1600), ("Javelin", 900), ("Recipe", 200)],
    "item_mjollnir": [("Maelstrom", 2700), ("Hyperstone", 2000), ("Recipe", 800)],
    "item_gleipnir": [("Maelstrom", 2700), ("Rod of Atos", 2250), ("Recipe", 700)],
    "item_dragon_lance": [("Ogre Axe", 1000), ("Band of Elvenskin", 450), ("Band of Elvenskin", 450)],
    "item_hurricane_pike": [("Dragon Lance", 1900), ("Force Staff", 2200), ("Recipe", 350)],
    "item_daedalus": [("Crystalys", 1950), ("Demon Edge", 2200), ("Recipe", 950)],
    "item_silver_edge": [("Shadow Blade", 3000), ("Oblivion Staff", 1625), ("Recipe", 825)],
    "item_shadow_blade": [("Shadow Amulet", 1000), ("Broadsword", 1000), ("Blitz Knuckles", 1000)],
    "item_monkey_king_bar": [("Demon Edge", 2200), ("Javelin", 900), ("Blitz Knuckles", 1000), ("Recipe", 800)],
    "item_butterfly": [("Eaglesong", 2800), ("Talisman of Evasion", 1300), ("Quarterstaff", 875)],
    "item_satanic": [("Morbid Mask", 900), ("Reaver", 2800), ("Claymore", 1350)],
    "item_skadi": [("Point Booster", 1200), ("Ultimate Orb", 2050), ("Ultimate Orb", 2050)],
    "item_basher": [("Mithril Hammer", 1600), ("Belt of Strength", 450), ("Recipe", 825)],
    "item_abyssal_blade": [("Skull Basher", 2875), ("Vanguard", 1700), ("Recipe", 1675)],
    "item_orchid": [("Oblivion Staff", 1625), ("Oblivion Staff", 1625), ("Recipe", 225)],
    "item_bloodthorn": [("Orchid Malevolence", 3475), ("Mage Slayer", 2625), ("Recipe", 700)],
    "item_witch_blade": [("Oblivion Staff", 1625), ("Chainmail", 550), ("Recipe", 425)],
    "item_parasma": [("Witch Blade", 2600), ("Mystic Staff", 2700), ("Recipe", 275)],
    "item_octarine_core": [("Aether Lens", 2275), ("Soul Booster", 3000)],
    "item_refresher": [("Perseverance", 1400), ("Perseverance", 1400), ("Recipe", 2200)],
    "item_sheepstick": [("Mystic Staff", 2700), ("Ultimate Orb", 2050), ("Void Stone", 700), ("Recipe", 125)],
    "item_sphere": [("Perseverance", 1400), ("Ultimate Orb", 2050), ("Recipe", 1150)],
    "item_glimmer_cape": [("Shadow Amulet", 1000), ("Cloak", 800), ("Recipe", 350)],
    "item_force_staff": [("Staff of Wizardry", 1000), ("Fluffy Hat", 250), ("Recipe", 950)],
    "item_aether_lens": [("Energy Booster", 800), ("Void Stone", 700), ("Recipe", 775)],
    "item_aeon_disk": [("Vitality Booster", 1000), ("Energy Booster", 800), ("Recipe", 1200)],
    "item_wind_waker": [("Eul's Scepter", 2625), ("Mystic Staff", 2700), ("Recipe", 1500)],
    "item_spirit_vessel": [("Urn of Shadows", 880), ("Vitality Booster", 1000), ("Crown", 450), ("Recipe", 450)],
    "item_urn_of_shadows": [("Sage's Mask", 175), ("Ring of Protection", 175), ("Infused Raindrops", 225), ("Recipe", 305)],
    "item_armlet": [("Helm of Iron Will", 975), ("Gloves of Haste", 450), ("Blades of Attack", 450), ("Recipe", 625)],
    "item_echo_sabre": [("Ogre Axe", 1000), ("Oblivion Staff", 1625), ("Recipe", 75)],
    "item_harpoon": [("Echo Sabre", 2700), ("Diadem", 1000), ("Recipe", 1000)],
    "item_radiance": [("Sacred Relic", 3400), ("Talisman of Evasion", 1300)],
    "item_nullifier": [("Sacred Relic", 3400), ("Helm of Iron Will", 975)],
    "item_aghanims_shard": [("Aghanim's Shard", 1400)],
    "item_ultimate_scepter": [("Point Booster", 1200), ("Ogre Axe", 1000), ("Blade of Alacrity", 1000), ("Staff of Wizardry", 1000)],
    "item_overwhelming_blink": [("Blink Dagger", 2250), ("Reaver", 2800), ("Recipe", 1750)],
    "item_swift_blink": [("Blink Dagger", 2250), ("Eaglesong", 2800), ("Recipe", 1750)],
    "item_arcane_blink": [("Blink Dagger", 2250), ("Mystic Staff", 2700), ("Recipe", 1850)]
}

# Explicit curated builds for distinct Dota 2 heroes
SPECIFIC_HERO_BUILDS: Dict[str, Dict[str, List[str]]] = {
    # 1. Anti-Mage
    "npc_dota_hero_antimage": {
        "starting": ["item_tango", "item_quelling_blade", "item_branches", "item_branches", "item_circlet", "item_slippers"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_bfury", "item_manta", "item_black_king_bar", "item_basher"],
        "luxury": ["item_abyssal_blade", "item_butterfly", "item_satanic", "item_swift_blink", "item_skadi"]
    },
    # 2. Axe
    "npc_dota_hero_axe": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_vanguard", "item_magic_wand"],
        "core": ["item_blink", "item_blade_mail", "item_black_king_bar", "item_aghanims_shard"],
        "luxury": ["item_overwhelming_blink", "item_heart", "item_shivas_guard", "item_bloodstone"]
    },
    # 3. Juggernaut
    "npc_dota_hero_juggernaut": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_wraith_band", "item_magic_wand"],
        "core": ["item_bfury", "item_manta", "item_diffusal_blade", "item_black_king_bar"],
        "luxury": ["item_butterfly", "item_satanic", "item_disperser", "item_swift_blink", "item_skadi"]
    },
    # 4. Phantom Assassin
    "npc_dota_hero_phantom_assassin": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_corrosion", "item_magic_wand"],
        "core": ["item_bfury", "item_desolator", "item_black_king_bar", "item_basher"],
        "luxury": ["item_abyssal_blade", "item_nullifier", "item_satanic", "item_swift_blink", "item_rapier"]
    },
    # 5. Pudge
    "npc_dota_hero_pudge": {
        "starting": ["item_tango", "item_gauntlets", "item_circlet", "item_branches", "item_branches", "item_blood_grenade"],
        "early_game": ["item_phase_boots", "item_urn_of_shadows", "item_magic_wand"],
        "core": ["item_blink", "item_pipe", "item_aghanims_shard", "item_shivas_guard"],
        "luxury": ["item_heart", "item_overwhelming_blink", "item_octarine_core", "item_lotus_orb"]
    },
    # 6. Invoker
    "npc_dota_hero_invoker": {
        "starting": ["item_tango", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_power_treads", "item_urn_of_shadows", "item_bottle", "item_magic_wand"],
        "core": ["item_spirit_vessel", "item_black_king_bar", "item_octarine_core", "item_aghanims_shard"],
        "luxury": ["item_refresher", "item_sheepstick", "item_arcane_blink", "item_shivas_guard"]
    },
    # 7. Crystal Maiden
    "npc_dota_hero_crystal_maiden": {
        "starting": ["item_tango", "item_ward_observer", "item_ward_sentry", "item_blood_grenade", "item_clarity", "item_branches"],
        "early_game": ["item_tranquil_boots", "item_magic_wand", "item_wind_lace"],
        "core": ["item_glimmer_cape", "item_force_staff", "item_black_king_bar", "item_aghanims_shard"],
        "luxury": ["item_ultimate_scepter", "item_octarine_core", "item_aeon_disk", "item_wind_waker"]
    },
    # 8. Sniper
    "npc_dota_hero_sniper": {
        "starting": ["item_tango", "item_slippers", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_power_treads", "item_dragon_lance", "item_wraith_band", "item_magic_wand"],
        "core": ["item_maelstrom", "item_dragon_lance", "item_black_king_bar", "item_mjollnir"],
        "luxury": ["item_hurricane_pike", "item_daedalus", "item_monkey_king_bar", "item_satanic", "item_butterfly"]
    },
    # 9. Faceless Void
    "npc_dota_hero_faceless_void": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_maelstrom", "item_manta", "item_black_king_bar", "item_mjollnir"],
        "luxury": ["item_skadi", "item_butterfly", "item_refresher", "item_satanic", "item_swift_blink"]
    },
    # 10. Legion Commander
    "npc_dota_hero_legion_commander": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_bracer", "item_soul_ring", "item_magic_wand"],
        "core": ["item_blink", "item_blade_mail", "item_black_king_bar", "item_heavens_halberd"],
        "luxury": ["item_overwhelming_blink", "item_assault", "item_satanic", "item_heart"]
    },
    # 11. Drow Ranger
    "npc_dota_hero_drow_ranger": {
        "starting": ["item_tango", "item_slippers", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_dragon_lance", "item_yasha", "item_manta", "item_black_king_bar"],
        "luxury": ["item_hurricane_pike", "item_butterfly", "item_daedalus", "item_satanic", "item_swift_blink"]
    },
    # 12. Slark
    "npc_dota_hero_slark": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_corrosion", "item_magic_wand"],
        "core": ["item_diffusal_blade", "item_echo_sabre", "item_black_king_bar", "item_harpoon"],
        "luxury": ["item_disperser", "item_ultimate_scepter", "item_skadi", "item_abyssal_blade", "item_butterfly"]
    },
    # 13. Shadow Fiend
    "npc_dota_hero_nevermore": {
        "starting": ["item_tango", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_power_treads", "item_dragon_lance", "item_bottle", "item_magic_wand"],
        "core": ["item_shadow_blade", "item_black_king_bar", "item_dragon_lance", "item_desolator"],
        "luxury": ["item_silver_edge", "item_hurricane_pike", "item_butterfly", "item_satanic", "item_swift_blink"]
    },
    # 14. Morphling
    "npc_dota_hero_morphling": {
        "starting": ["item_tango", "item_slippers", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_manta", "item_black_king_bar", "item_sphere", "item_skadi"],
        "luxury": ["item_butterfly", "item_satanic", "item_swift_blink", "item_ethereal_blade"]
    },
    # 15. Sven
    "npc_dota_hero_sven": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_bracer", "item_echo_sabre", "item_magic_wand"],
        "core": ["item_blink", "item_black_king_bar", "item_harpoon", "item_daedalus"],
        "luxury": ["item_overwhelming_blink", "item_satanic", "item_assault", "item_bloodthorn"]
    },
    # 16. Wraith King
    "npc_dota_hero_skeleton_king": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_armlet", "item_magic_wand"],
        "core": ["item_blink", "item_desolator", "item_black_king_bar", "item_basher"],
        "luxury": ["item_assault", "item_abyssal_blade", "item_heart", "item_overwhelming_blink"]
    },
    # 17. Bristleback
    "npc_dota_hero_bristleback": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_vanguard", "item_magic_wand", "item_soul_ring"],
        "core": ["item_bloodstone", "item_aghanims_shard", "item_black_king_bar", "item_lotus_orb"],
        "luxury": ["item_heart", "item_assault", "item_shivas_guard", "item_overwhelming_blink"]
    },
    # 18. Viper
    "npc_dota_hero_viper": {
        "starting": ["item_tango", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_power_treads", "item_dragon_lance", "item_magic_wand"],
        "core": ["item_mage_slayer", "item_dragon_lance", "item_black_king_bar", "item_aghanims_shard"],
        "luxury": ["item_hurricane_pike", "item_butterfly", "item_shivas_guard", "item_heart"]
    },
    # 19. Windranger
    "npc_dota_hero_windrunner": {
        "starting": ["item_tango", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_phase_boots", "item_bottle", "item_magic_wand"],
        "core": ["item_maelstrom", "item_black_king_bar", "item_ultimate_scepter", "item_monkey_king_bar"],
        "luxury": ["item_gleipnir", "item_daedalus", "item_satanic", "item_swift_blink", "item_sphere"]
    },
    # 20. Storm Spirit
    "npc_dota_hero_storm_spirit": {
        "starting": ["item_tango", "item_null_talisman", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_bottle", "item_power_treads", "item_magic_wand", "item_null_talisman"],
        "core": ["item_witch_blade", "item_kaya_and_sange", "item_black_king_bar", "item_orchid"],
        "luxury": ["item_bloodthorn", "item_shivas_guard", "item_sheepstick", "item_arcane_blink"]
    },
    # 21. Tinker
    "npc_dota_hero_tinker": {
        "starting": ["item_tango", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_bottle", "item_soul_ring", "item_magic_wand"],
        "core": ["item_blink", "item_black_king_bar", "item_shivas_guard", "item_sheepstick"],
        "luxury": ["item_arcane_blink", "item_dagon_5", "item_octarine_core", "item_wind_waker"]
    },
    # 22. Lion
    "npc_dota_hero_lion": {
        "starting": ["item_tango", "item_ward_observer", "item_ward_sentry", "item_blood_grenade", "item_clarity", "item_branches"],
        "early_game": ["item_tranquil_boots", "item_magic_wand", "item_wind_lace"],
        "core": ["item_blink", "item_glimmer_cape", "item_force_staff", "item_aghanims_shard"],
        "luxury": ["item_ultimate_scepter", "item_aeon_disk", "item_sheepstick", "item_octarine_core"]
    },
    # 23. Rubick
    "npc_dota_hero_rubick": {
        "starting": ["item_tango", "item_ward_observer", "item_ward_sentry", "item_blood_grenade", "item_clarity", "item_branches"],
        "early_game": ["item_arcane_boots", "item_magic_wand", "item_wind_lace"],
        "core": ["item_blink", "item_aether_lens", "item_glimmer_cape", "item_force_staff"],
        "luxury": ["item_ultimate_scepter", "item_aeon_disk", "item_wind_waker", "item_octarine_core"]
    },
    # 24. Earthshaker
    "npc_dota_hero_earthshaker": {
        "starting": ["item_tango", "item_gauntlets", "item_circlet", "item_branches", "item_branches", "item_clarity"],
        "early_game": ["item_tranquil_boots", "item_soul_ring", "item_magic_wand"],
        "core": ["item_blink", "item_aghanims_shard", "item_force_staff", "item_black_king_bar"],
        "luxury": ["item_octarine_core", "item_overwhelming_blink", "item_refresher", "item_shivas_guard"]
    },
    # 25. Witch Doctor
    "npc_dota_hero_witch_doctor": {
        "starting": ["item_tango", "item_ward_observer", "item_ward_sentry", "item_blood_grenade", "item_clarity", "item_branches"],
        "early_game": ["item_arcane_boots", "item_magic_wand", "item_urn_of_shadows"],
        "core": ["item_glimmer_cape", "item_aghanims_shard", "item_ultimate_scepter", "item_black_king_bar"],
        "luxury": ["item_aeon_disk", "item_aether_lens", "item_wind_waker", "item_lotus_orb"]
    },
    # 26. Ogre Magi
    "npc_dota_hero_ogre_magi": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_blood_grenade", "item_branches"],
        "early_game": ["item_arcane_boots", "item_hand_of_midas", "item_magic_wand"],
        "core": ["item_bloodstone", "item_black_king_bar", "item_aghanims_shard", "item_heart"],
        "luxury": ["item_shivas_guard", "item_octarine_core", "item_assault", "item_sheepstick"]
    },
    # 27. Tidehunter
    "npc_dota_hero_tidehunter": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_vanguard", "item_soul_ring", "item_magic_wand"],
        "core": ["item_blink", "item_pipe", "item_shivas_guard", "item_refresher"],
        "luxury": ["item_overwhelming_blink", "item_heart", "item_assault", "item_lotus_orb"]
    },
    # 28. Magnus
    "npc_dota_hero_magnataur": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_soul_ring", "item_magic_wand"],
        "core": ["item_blink", "item_harpoon", "item_black_king_bar", "item_refresher"],
        "luxury": ["item_overwhelming_blink", "item_octarine_core", "item_shivas_guard", "item_assault"]
    },
    # 29. Ursa
    "npc_dota_hero_ursa": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_morbid_mask", "item_magic_wand"],
        "core": ["item_diffusal_blade", "item_blink", "item_black_king_bar", "item_basher"],
        "luxury": ["item_abyssal_blade", "item_satanic", "item_disperser", "item_swift_blink"]
    },
    # 30. Bloodseeker
    "npc_dota_hero_bloodseeker": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_corrosion", "item_magic_wand"],
        "core": ["item_maelstrom", "item_black_king_bar", "item_sange_and_yasha", "item_basher"],
        "luxury": ["item_gleipnir", "item_butterfly", "item_abyssal_blade", "item_satanic"]
    },
    # 31. Medusa
    "npc_dota_hero_medusa": {
        "starting": ["item_tango", "item_slippers", "item_circlet", "item_branches", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_manta", "item_dragon_lance", "item_skadi", "item_butterfly"],
        "luxury": ["item_hurricane_pike", "item_daedalus", "item_satanic", "item_swift_blink"]
    },
    # 32. Terrorblade
    "npc_dota_hero_terrorblade": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_dragon_lance", "item_manta", "item_skadi", "item_black_king_bar"],
        "luxury": ["item_butterfly", "item_satanic", "item_swift_blink", "item_hurricane_pike"]
    },
    # 33. Luna
    "npc_dota_hero_luna": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_power_treads", "item_wraith_band", "item_magic_wand"],
        "core": ["item_mask_of_madness", "item_manta", "item_dragon_lance", "item_black_king_bar"],
        "luxury": ["item_butterfly", "item_satanic", "item_daedalus", "item_hurricane_pike"]
    },
    # 34. Zeus
    "npc_dota_hero_zuus": {
        "starting": ["item_tango", "item_clarity", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"],
        "early_game": ["item_bottle", "item_arcane_boots", "item_magic_wand"],
        "core": ["item_kaya_and_sange", "item_aghanims_shard", "item_black_king_bar", "item_octarine_core"],
        "luxury": ["item_refresher", "item_ultimate_scepter", "item_shivas_guard", "item_wind_waker"]
    },
    # 35. Marci
    "npc_dota_hero_marci": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_armlet", "item_magic_wand"],
        "core": ["item_black_king_bar", "item_basher", "item_harpoon", "item_daedalus"],
        "luxury": ["item_abyssal_blade", "item_satanic", "item_assault", "item_overwhelming_blink"]
    },
    # 36. Primal Beast
    "npc_dota_hero_primal_beast": {
        "starting": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_bracer", "item_soul_ring", "item_magic_wand"],
        "core": ["item_blade_mail", "item_black_king_bar", "item_heart", "item_aghanims_shard"],
        "luxury": ["item_overwhelming_blink", "item_shivas_guard", "item_assault", "item_octarine_core"]
    },
    # 37. Kez
    "npc_dota_hero_kez": {
        "starting": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet", "item_branches", "item_branches"],
        "early_game": ["item_phase_boots", "item_echo_sabre", "item_magic_wand"],
        "core": ["item_desolator", "item_black_king_bar", "item_harpoon", "item_basher"],
        "luxury": ["item_abyssal_blade", "item_daedalus", "item_satanic", "item_swift_blink"]
    },
    # 38. Ringmaster
    "npc_dota_hero_ringmaster": {
        "starting": ["item_tango", "item_ward_observer", "item_ward_sentry", "item_blood_grenade", "item_clarity", "item_branches"],
        "early_game": ["item_tranquil_boots", "item_magic_wand", "item_wind_lace"],
        "core": ["item_aether_lens", "item_glimmer_cape", "item_force_staff", "item_aeon_disk"],
        "luxury": ["item_octarine_core", "item_wind_waker", "item_lotus_orb", "item_sheepstick"]
    }
}


def get_hero_build_raw(hero_name: str, hero_obj: Dict[str, Any], role: str) -> Dict[str, List[str]]:
    """
    Returns authentic hero-specific build dictionary with starting, early, core, and luxury items.
    If hero is in curated table, returns curated build.
    Otherwise generates an authentic signature build tailored to that specific hero's kit and tags.
    """
    h_clean = hero_name.lower().strip()
    if h_clean in SPECIFIC_HERO_BUILDS:
        return SPECIFIC_HERO_BUILDS[h_clean]

    # Check without prefix
    for k, v in SPECIFIC_HERO_BUILDS.items():
        if k.replace("npc_dota_hero_", "") == h_clean.replace("npc_dota_hero_", ""):
            return v

    # Dynamic distinct hero build generator
    attr = hero_obj.get("attr", "agi") if hero_obj else "agi"
    tags = set(hero_obj.get("tags", [])) if hero_obj else set()
    r_lower = role.lower()

    is_support = "support" in r_lower or "pos 4" in r_lower or "pos 5" in r_lower or "support" in tags
    is_mid = "mid" in r_lower or "pos 2" in r_lower
    is_offlane = "offlane" in r_lower or "pos 3" in r_lower or "initiator" in tags

    # 1. Starting items
    if is_support:
        starting = ["item_tango", "item_ward_observer", "item_ward_sentry", "item_blood_grenade", "item_clarity", "item_branches"]
        early = ["item_arcane_boots" if "mana_burn" in tags or attr == "int" else "item_tranquil_boots", "item_magic_wand", "item_wind_lace"]
        core = ["item_glimmer_cape", "item_force_staff", "item_aether_lens", "item_aghanims_shard"]
        luxury = ["item_aeon_disk", "item_lotus_orb", "item_wind_waker", "item_octarine_core"]
    elif is_offlane:
        starting = ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet", "item_branches", "item_branches"]
        early = ["item_phase_boots", "item_bracer", "item_vanguard" if "tank" in tags else "item_soul_ring", "item_magic_wand"]
        core = ["item_blink", "item_blade_mail", "item_black_king_bar", "item_crimson_guard" if "tank" in tags else "item_pipe"]
        luxury = ["item_overwhelming_blink", "item_heart", "item_shivas_guard", "item_assault"]
    elif is_mid:
        starting = ["item_tango", "item_circlet", "item_branches", "item_branches", "item_faerie_fire"]
        early = ["item_bottle", "item_power_treads", "item_null_talisman" if attr == "int" else "item_wraith_band", "item_magic_wand"]
        core = [
            "item_witch_blade" if attr == "int" else "item_dragon_lance",
            "item_black_king_bar",
            "item_kaya_and_sange" if attr == "int" else "item_desolator",
            "item_orchid"
        ]
        luxury = ["item_bloodthorn", "item_sheepstick", "item_arcane_blink" if attr == "int" else "item_swift_blink", "item_shivas_guard"]
    else:
        # Carry (distinct based on tags)
        starting = ["item_tango", "item_quelling_blade", "item_slippers" if attr == "agi" else "item_gauntlets", "item_circlet", "item_branches", "item_branches"]
        early = ["item_power_treads", "item_wraith_band" if attr == "agi" else "item_bracer", "item_magic_wand"]
        
        if "illusion" in tags:
            core = ["item_diffusal_blade", "item_manta", "item_skadi", "item_black_king_bar"]
            luxury = ["item_butterfly", "item_heart", "item_disperser", "item_satanic"]
        elif "magic_burst" in tags or attr == "int":
            core = ["item_witch_blade", "item_black_king_bar", "item_kaya_and_sange", "item_octarine_core"]
            luxury = ["item_parasma", "item_sheepstick", "item_refresher", "item_shivas_guard"]
        elif "ranged_physical" in tags or "long_range" in tags:
            core = ["item_dragon_lance", "item_maelstrom", "item_black_king_bar", "item_manta"]
            luxury = ["item_hurricane_pike", "item_daedalus", "item_butterfly", "item_satanic"]
        else:
            core = ["item_bfury", "item_manta", "item_black_king_bar", "item_basher"]
            luxury = ["item_abyssal_blade", "item_butterfly", "item_satanic", "item_swift_blink"]

    return {
        "starting": starting,
        "early_game": early,
        "core": core,
        "luxury": luxury
    }
