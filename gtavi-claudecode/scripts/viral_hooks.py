"""Viral Hooks integration based on rediumvex/viral-hooks-skill database.
Loads battle-tested short-form hook formulas across 10 psychology triggers.
"""
from pathlib import Path
import random
import re

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "viral-hooks"
DB_PATH = SKILL_DIR / "hooks-database.md"

FALLBACK_VIRAL_HOOKS = [
    "NOBODY NOTICED THIS IN GTA 6 💀",
    "THIS CANNOT BE REAL 🤯🔥",
    "BRO COMPLETELY LOST HIS MIND 😭",
    "I DID NOT EXPECT THIS TO HAPPEN 💀",
    "THIS JUST BROKE GTA 6 😭💀",
    "DO NOT TRY THIS IN GTA 6 💀🔥",
    "HE HAD ZERO IDEA WHAT WAS COMING 🤯",
    "EVERYONE MISSED THIS DETAIL 💀",
    "THIS IS WHY NOBODY DOES THIS IN GTA 6 💀",
    "HE REGRETTED THIS IMMEDIATELY 😭💀"
]

FALLBACK_VIRAL_TITLES = [
    "NOBODY EXPECTED THIS IN GTA 6! 💀🔥",
    "BRO WENT ABSOLUTELY CRAZY! 😭💀",
    "HE FINALLY FOUND THE SECRET! 🤯🔥",
    "SPEED LOST HIS MIND IN GTA 6! 💀😭",
    "THIS MOMENT BROKE THE INTERNET! 💀🔥",
    "THE CRAZIEST THING JUST HAPPENED! 🤯🔥"
]


def load_database_formulas():
    if not DB_PATH.exists():
        return []
    formulas = []
    try:
        text = DB_PATH.read_text(encoding="utf-8")
        # Match markdown table rows containing formulas: | 001 | "..." | "..." | ...
        matches = re.findall(r'\|\s*\d+\s*\|\s*"([^"]+)"', text)
        for m in matches:
            if m.strip():
                formulas.append(m.strip())
    except Exception:
        pass
    return formulas


def get_random_viral_hook(streamer="", topic="GTA 6"):
    formulas = load_database_formulas()
    if not formulas:
        return random.choice(FALLBACK_VIRAL_HOOKS)
    
    cand = random.choice(formulas)
    # Fill common placeholders
    cand = cand.replace("[niche]", topic).replace("[topic]", topic).replace("[game]", topic)
    cand = cand.replace("[action/situation]", "this happened").replace("[unexpected thing]", "this secret")
    cand = cand.replace("[authority/creator/brand]", streamer or "Speed")
    if "[" in cand or "]" in cand:
        return random.choice(FALLBACK_VIRAL_HOOKS)
    return f"{cand.upper()} 💀"
