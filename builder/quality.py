"""The catalog's exam: fixed mood requests run through the app's own search, written up for a person to judge.

Run:    uv run python -m builder.quality            (after builder.pack; uses the catalog the backend would load)
Output: data/build/catalog/quality-<version>.md
Re-run after every catalog build (e.g. each weekly 27B upgrade) and compare the reports.
"""
import statistics
from collections import Counter


from backend.catalog import Catalog
from backend.understand import query_for
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
]
NICHE_SAMPLE = 6  # the first few prompts are also run as a niche user, to show the drift in action
RECENT = 2  # "recent" = released in the last N years


def run(catalog, prompt, niche):
    query, effects = query_for(prompt)  # the same LLM rewrite the app uses (cached, so the niche re-runs are free)
    hits = catalog.search(query, k=5, effects=effects, niche=niche)
    rows = catalog.table.take([catalog.index[i] for i, _ in hits]).to_pylist()
    return effects, [(r, score) for r, (_, score) in zip(rows, hits)]


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
        effects, picks = run(catalog, prompt, niche=0.25)
        all_picks += [r for r, _ in picks]
        if effects:
            asked += len(picks)
            matched += sum(r["effect"] in effects for r, _ in picks)
        lines += [f"### {prompt}", f"Effect asked for: {', '.join(effects) or '(none detected)'}", "", *table(effects, picks), ""]

    lines += ["## The same requests for a niche user (niche = 0.8)", ""]
    for prompt in PROMPTS[:NICHE_SAMPLE]:
        effects, picks = run(catalog, prompt, niche=0.8)
        lines += [f"### {prompt}", "", *table(effects, picks), ""]

    counts = Counter(r["tmdb_id"] for r in all_picks)
    repeats = [f"{r['title']} ({counts[r['tmdb_id']]}×)" for r in {r["tmdb_id"]: r for r in all_picks}.values()
               if counts[r["tmdb_id"]] >= 3]
    votes = [r["imdb_votes"] for r in all_picks]
    models = Counter("27B" if "27B" in (r["profile_model"] or "") else "4B" for r in all_picks)
    summary = [
        f"# Catalog quality report: {catalog.version}",
        "",
        f"{len(catalog.ids):,} films. {len(PROMPTS)} requests × 5 picks for a Normal user (niche 0.25), using the "
        "same search as the app. Read each table and ask: would I be happy with these picks?",
        "",
        "| Check | Result | Good looks like |",
        "|---|---|---|",
        f"| Picks with the effect asked for | {matched}/{asked} ({100 * matched / max(asked, 1):.0f}%) | most of them |",
        f"| Median IMDb votes of picks | {statistics.median(votes):,.0f} | thousands+ for a Normal user |",
        f"| Picks from the last {RECENT} years | {sum((r['year'] or 0) > this_year - RECENT for r in all_picks)}"
        f"/{len(all_picks)} | some, not most |",
        f"| Picks with a 27B profile | {models['27B']}/{len(all_picks)} | grows with each upgrade |",
        f"| Films picked for 3+ different requests | {', '.join(repeats) or 'none'} | none (a film that fits "
        "everything is an outlier) |",
        "",
    ]
    path = BUILD / "catalog" / f"quality-{catalog.version}.md"
    path.write_text("\n".join(summary + lines))
    print("\n".join(summary))
    print(f"Full report: {path}")


if __name__ == "__main__":
    main()
