import pytest

from builder.mood import clean, film_text, fingerprint

GOOD = {"mood_tags": ["melancholic", "tender", "nonsense-tag", "melancholic", "family"], "effect": "catharsis",
        "pace": "slow", "intensity": 9, "watch_when": " you want to sit with sadness ", "confidence": "high"}


def test_clean_drops_unknown_and_duplicate_tags_and_clamps():
    p = clean(GOOD)
    assert p["mood_tags"] == ["melancholic", "tender", "family"]
    assert p["intensity"] == 5 and p["watch_when"] == "you want to sit with sadness"
    assert clean({**GOOD, "watch_when": "Watch this when you need a cry."})["watch_when"] == "you need a cry."


def test_clean_rejects_unusable_answers():
    with pytest.raises(ValueError):
        clean({**GOOD, "effect": "happy"})
    with pytest.raises(ValueError):
        clean({**GOOD, "mood_tags": ["made-up", "tender"]})


def test_film_text_and_fingerprint():
    d = {"title": "Tokyo Story", "release_date": "1953-11-03", "original_language": "ja",
         "genres": [{"name": "Drama"}], "runtime": 136, "overview": "An elderly couple visits their children.",
         "keywords": {"keywords": [{"name": "aging parents"}]},
         "reviews": {"results": [{"content": "Quietly\ndevastating."}]}}
    text = film_text(d)
    assert "Title: Tokyo Story (1953)" in text and "Keywords: aging parents" in text
    assert "Review excerpt: Quietly devastating." in text
    assert fingerprint(text) == fingerprint(text) != fingerprint(text + " ")
