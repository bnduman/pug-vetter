"""Which equipment slots a raid-ready character is expected to have enchanted.

Warcraft Logs returns each gear item with an explicit `slot` number (0 = Head,
2 = Shoulder, 4 = Chest, 6 = Legs, 8 = Wrist, 9 = Hands, 14 = Back, 15 = Main
Hand, etc.), so we match on that rather than array position.

Tuned for The Burning Crusade (current Anniversary content), where head and
shoulder enchants are standard raid enchants (Aldor/Scryer inscriptions, etc.).
`required=True` slots count toward the "missing enchants" warning.
"""

ENCHANT_SLOTS = [
    {"slot": 0, "label": "Head", "required": True},
    {"slot": 2, "label": "Shoulder", "required": True},
    {"slot": 14, "label": "Back", "required": True},
    {"slot": 4, "label": "Chest", "required": True},
    {"slot": 8, "label": "Wrist", "required": True},
    {"slot": 9, "label": "Hands", "required": True},
    {"slot": 6, "label": "Legs", "required": True},
    {"slot": 7, "label": "Feet", "required": True},
    {"slot": 15, "label": "Weapon", "required": True},
]

# Slots to ignore when averaging item level (cosmetic / no real ilvl).
NON_ILVL_SLOTS = {3, 18}  # Shirt, Tabard
