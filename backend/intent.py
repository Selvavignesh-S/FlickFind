"""What effect a message asks for ("a good cry" -> catharsis), from keyword rules.

shortcut: keywords only (no negation: "not scary" still reads as tension); the P3 chat turn replaces this with the
LLM, which also asks a clarifying question when the message is vague.
"""
import re

RULES = {  # effect -> phrases that ask for it (the effects come from builder/vocab.py)
    "catharsis": ["cry", "tear", "sob", "weep", "heartbreak", "let it out", "emotional"],
    "lift": ["laugh", "funny", "comedy", "cheer me up", "cheer up", "hilarious", "happy", "feel good", "feel-good",
             "uplift", "joy"],
    "comfort": ["cosy", "cozy", "comfort", "warm", "rainy", "gentle", "wholesome", "soothing", "calm"],
    "tension": ["tense", "thrill", "suspense", "edge of my seat", "scary", "scare", "horror", "nail-biting", "gripping"],
    "wonder": ["mind-bending", "mind bending", "awe", "wonder", "beautiful", "epic", "magical", "trippy"],
    "escape": ["escape", "adventure", "forget", "another world", "fantasy", "swept away", "switch off", "zone out",
               "turn my brain off", "mindless", "easy watch", "nothing heavy"],
    "provoke": ["make me think", "thought-provoking", "challenge", "disturb", "unsettl", "provoke", "make me question"],
    "numb": ["numb", "empty", "don't want to be cheered up", "not be cheered up", "sit with"],
}
_PATTERNS = {e: re.compile("|".join(r"\b" + re.escape(p) for p in ps), re.I) for e, ps in RULES.items()}


def effects_for(message):
    """The effects a message asks for, in the order they appear in it."""
    found = {e: m.start() for e, p in _PATTERNS.items() if (m := p.search(message))}
    return sorted(found, key=found.get)
