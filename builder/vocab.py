"""The fixed mood vocabulary every film profile is written in.

Changing a word here means re-profiling the catalog, so keep it stable.
"""

# What the film does to the viewer. Chat quick replies map onto these.
EFFECTS = {
    "lift": "leaves you lighter: funny, joyful or hopeful",
    "catharsis": "lets you have a good cry and come out lighter",
    "comfort": "warm, safe and familiar; a cup of tea in film form",
    "wonder": "awe at something vast, beautiful or strange",
    "tension": "keeps you on edge: suspense, dread or thrills",
    "escape": "pulls you fully into another world and away from your own",
    "provoke": "leaves you thinking, arguing or unsettled",
    "numb": "lets you sit in a flat or empty feeling without forcing a lift",
}

TAGS = {
    "feel": [
        "melancholic", "bittersweet", "uplifting", "heartwarming", "cozy", "hopeful", "joyful",
        "funny", "absurd", "dark-humoured", "romantic", "tender", "nostalgic", "lonely", "bleak",
        "tragic", "eerie", "unsettling", "terrifying", "tense", "suspenseful", "angry", "defiant",
        "dreamlike", "whimsical", "awe-inspiring", "mysterious", "contemplative", "cathartic", "euphoric",
        "satirical", "inspiring", "mind-bending",
    ],
    "style": [
        "slow-burn", "meditative", "brisk", "frantic", "dialogue-driven", "visually-lush",
        "minimalist", "epic", "intimate", "ensemble", "atmospheric",
    ],
    "theme": [
        "grief", "love", "family", "friendship", "coming-of-age", "identity", "isolation", "survival",
        "revenge", "justice", "class", "ambition", "memory", "faith", "war", "crime", "freedom",
        "nature", "technology", "madness", "redemption", "growing-old", "dystopia",
    ],
}
# Definitions the profile prompt gives for tags a small model tends to confuse.
TAG_NOTES = {
    "uplifting": "leaves you in a better mood",
    "inspiring": "makes you want to act or change something",
}
ALL_TAGS = [t for group in TAGS.values() for t in group]
PACES = ["slow", "medium", "fast"]

# JSON schema the AI must answer in (Ollama `format` and Gemini `response_schema` both accept it).
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "mood_tags": {"type": "array", "items": {"type": "string", "enum": ALL_TAGS},
                      "minItems": 3, "maxItems": 6},
        "effect": {"type": "string", "enum": list(EFFECTS)},
        "pace": {"type": "string", "enum": PACES},
        "intensity": {"type": "integer", "minimum": 1, "maximum": 5},
        "watch_when": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "low"]},
    },
    "required": ["mood_tags", "effect", "pace", "intensity", "watch_when", "confidence"],
}

assert len(ALL_TAGS) == len(set(ALL_TAGS)), "duplicate tag"
