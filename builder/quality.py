"""The catalog's exam: fixed mood requests run through the app's own search, written up for a person to judge.

Run:    uv run python -m builder.quality            (after builder.pack; uses the catalog the backend would load)
Output: data/build/catalog/quality-<version>.md
Re-run after every catalog build (e.g. each weekly 27B upgrade) and compare the reports.
"""
import statistics
from collections import Counter

import pyarrow as pa


from backend.catalog import NEUTRAL, Catalog
from backend.understand import prepare
from builder.common import BUILD

PROMPTS = [
    "I'm sad and want to laugh",
    "I want a good cry",
    "Something tense that keeps me on the edge of my seat",
    "A cosy film for a rainy evening",
    "Mind-bending but not slow",
    "I've had a long week, I want to switch off",
    "Cheer me up, I'm feeling low",
    "Something beautiful and quiet",
    "A thought-provoking film that stays with me",
    "An epic adventure to get lost in",
    "A heartwarming family film for the weekend",
    "Something scary for a night in",
    "I feel numb and don't want to be cheered up",
    "A romantic film that isn't cheesy",
    "A feel-good documentary",
    "Something dark and funny",
    "A slow, atmospheric mystery",
    "A film about friendship that will make me smile",
    "I'm anxious, I need something gentle",
    "An inspiring true story",
    "Something weird and surreal",
    "A gripping crime story",
    "Nostalgic, like being a kid again",
    "A bittersweet film about growing up",
    "I want to be amazed by the visuals",
    "A Japanese film that is calm and moving",
    "An angry film about injustice",
    "Light and fun, nothing heavy",
    "A war film that shows the human cost",
    "Something hopeful after a breakup",
    # the user's own requests from the first app test (2026-11-07), kept so every catalog is checked against them
    "I wanna cry a lot and drain my sadness away",
    "I want to forget my sadness, wanna laugh a lot",
    "I want to watch a good techno thriller",
    "I want to feel existential dread once I watch a film you recommend",
    "I want to feel very little among the grand scheme of life",
]
# Requests with hard rules, each with an independent check every pick must pass (not the search code's own matching).
RULES = {
    "Movies directed by Tarantino": lambda r: "Quentin Tarantino" in r["director"],
    "Indian thriller movies": lambda r: ("IN" in r["countries"] or r["group"] == "indian") and "Thriller" in r["genres"],
    "A feel-good Malayalam film from the 2010s": lambda r: r["language"] == "ml" and 2010 <= (r["year"] or 0) <= 2019,
    "Christopher Nolan films that will blow my mind": lambda r: "Christopher Nolan" in r["director"],
    "A comedy under 90 minutes": lambda r: "Comedy" in r["genres"] and 0 < (r["runtime"] or 0) <= 90,
    "A documentary about space": lambda r: r["documentary"],
    "Films starring Shah Rukh Khan": lambda r: "Shah Rukh Khan" in r["cast"],
    "French films from the 1960s": lambda r: ("FR" in r["countries"] or r["language"] == "fr")
                                             and 1960 <= (r["year"] or 0) <= 1969,
    "A Korean revenge thriller": lambda r: "KR" in r["countries"] or r["language"] == "ko",
    "An animated film that isn't for kids": lambda r: r["animation"],
    "A24 horror films": lambda r: "A24" in (r.get("companies") or []),
    "Studio Ghibli films for a slow Sunday": lambda r: "Studio Ghibli" in (r.get("companies") or []),
}
# Requests naming a reference film: the reference itself must never be one of the picks.
LIKE = {"Films like Inception": "Inception", "Something like Spirited Away but for adults": "Spirited Away",
        "Movies similar to Drishyam": "Drishyam"}
NICHE_SAMPLE = 6  # the first few prompts are also run as a niche user, to show the drift in action
RECENT = 2  # "recent" = released in the last N years


def run(catalog, prompt, niche):
    plan = prepare(catalog, prompt)  # the same reading the app uses (cached, so the niche re-runs are free)
    effects = plan["effects"]
    hits = catalog.search(plan["query_vec"], k=5, effects=effects, niche=niche, allowed=plan["allowed"],
                          exclude=plan["exclude"])
    rows = catalog.table.take(pa.array([catalog.index[i] for i, _ in hits], pa.int64())).to_pylist()
    return effects, [(r, score) for r, (_, score) in zip(rows, hits)], plan


def table(effects, picks):
    out = ["| # | Film | Effect | Mood tags | IMDb (votes) | Profile |", "|---|---|---|---|---|---|"]
    for n, (r, _) in enumerate(picks, 1):
        effect = f"**{r['effect']}**" if r["effect"] in effects else r["effect"]
        model = "27B" if "27B" in (r["profile_model"] or "") else "4B"
        out.append(f"| {n} | {r['title']} ({r['year']}) | {effect} | {', '.join(r['mood_tags'])} | "
                   f"{r['imdb_rating']} ({r['imdb_votes']:,}) | {model} |")
    return out


def main():
    catalog = Catalog.load()
    this_year = max(y for y in catalog.table["year"].to_pylist() if y)
    lines, all_picks, matched, asked = [], [], 0, 0
    for prompt in PROMPTS:
        effects, picks, _ = run(catalog, prompt, niche=NEUTRAL)
        all_picks += [r for r, _ in picks]
        if effects:
            asked += len(picks)
            matched += sum(r["effect"] in effects for r, _ in picks)
        lines += [f"### {prompt}", f"Effect asked for: {', '.join(effects) or '(none detected)'}", "", *table(effects, picks), ""]

    lines += ["## The same requests for a niche user (niche = 0.8)", ""]
    for prompt in PROMPTS[:NICHE_SAMPLE]:
        effects, picks, _ = run(catalog, prompt, niche=0.8)
        lines += [f"### {prompt}", "", *table(effects, picks), ""]

    lines += ["## Requests with rules or a reference film", ""]
    broken, checked, self_refs = [], 0, []
    for prompt in [*RULES, *LIKE]:
        effects, picks, plan = run(catalog, prompt, niche=NEUTRAL)
        for r, _ in picks:
            if prompt in RULES:
                checked += 1
                if not RULES[prompt](r):
                    broken.append(f"{r['title']} for \"{prompt}\"")
            elif r["title"] == LIKE[prompt]:
                self_refs.append(prompt)
        lines += [f"### {prompt}", f"Understood: {'; '.join(plan['understood']) or '(no rules)'}",
                  *[f"Note: {n}" for n in plan["notes"]], "", *table(effects, picks), ""]

    counts = Counter(r["tmdb_id"] for r in all_picks)
    repeats = [f"{r['title']} ({counts[r['tmdb_id']]}×)" for r in {r["tmdb_id"]: r for r in all_picks}.values()
               if counts[r["tmdb_id"]] >= 3]
    votes = [r["imdb_votes"] for r in all_picks]
    in_catalog = Counter(catalog.table["group"].to_pylist())
    in_picks = Counter(r["group"] for r in all_picks)
    mix = ", ".join(f"{g} {100 * in_picks[g] / len(all_picks):.0f}% vs {100 * n / len(catalog.ids):.0f}%"
                    for g, n in in_catalog.most_common())
    models = Counter("27B" if "27B" in (r["profile_model"] or "") else "4B" for r in all_picks)
    summary = [
        f"# Catalog quality report: {catalog.version}",
        "",
        f"{len(catalog.ids):,} films. {len(PROMPTS)} requests × 5 picks for a new user (no lean), using the "
        "same search as the app. Read each table and ask: would I be happy with these picks?",
        "",
        "| Check | Result | Good looks like |",
        "|---|---|---|",
        f"| Picks with the effect asked for | {matched}/{asked} ({100 * matched / max(asked, 1):.0f}%) | most of them |",
        f"| Median IMDb votes of picks | {statistics.median(votes):,.0f} | not tiny (picks people have seen) |",
        f"| Language mix of picks vs catalog | {mix} | close to the catalog (no group favoured) |",
        f"| Picks from the last {RECENT} years | {sum((r['year'] or 0) > this_year - RECENT for r in all_picks)}"
        f"/{len(all_picks)} | some, not most |",
        f"| Picks with a 27B profile | {models['27B']}/{len(all_picks)} | grows with each upgrade |",
        f"| Films picked for 3+ different requests | {', '.join(repeats) or 'none'} | none (a film that fits "
        "everything is an outlier) |",
        f"| Picks that break the request's rules | {len(broken)}/{checked}{': ' + ', '.join(broken) if broken else ''}"
        " | 0, always |",
        f"| Reference films recommended back | {len(self_refs)} | 0, always |",
        "",
    ]
    path = BUILD / "catalog" / f"quality-{catalog.version}.md"
    path.write_text("\n".join(summary + lines))
    print("\n".join(summary))
    print(f"Full report: {path}")


if __name__ == "__main__":
    main()
