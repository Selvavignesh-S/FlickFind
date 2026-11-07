import datetime

from builder.curate import FLOORS, drop_reason

TODAY = datetime.date(2026, 11, 7)
GOOD = {"release_date": "2001-07-20", "overview": " ".join(["word"] * 20)}


def days_ago(n):
    return {**GOOD, "release_date": (TODAY - datetime.timedelta(days=n)).isoformat()}


def test_keeps_a_film_that_passes_every_rule():
    assert drop_reason(GOOD, "japanese", False, FLOORS["japanese"], TODAY) is None


def test_rules_in_order():
    assert drop_reason({}, "english", False, 10**6, TODAY) == "not on TMDB"
    assert drop_reason({**GOOD, "softcore": True}, "english", False, 10**6, TODAY) == "adult"
    assert drop_reason({**GOOD, "video": True}, "english", False, 10**6, TODAY) == "video release"
    assert drop_reason({**GOOD, "release_date": "2027-01-01"}, "english", False, 10**6, TODAY) == "not released"
    assert drop_reason({**GOOD, "overview": "too short"}, "english", False, 10**6, TODAY) == "synopsis too short"
    assert drop_reason(GOOD, None, False, 10**6, TODAY) == "language out of scope"


def test_vote_floor_per_group_and_documentaries_have_their_own():
    assert drop_reason(GOOD, "indian", False, FLOORS["indian"] - 1, TODAY) == "below vote floor"
    assert drop_reason(GOOD, "indian", True, 60, TODAY) is None  # documentary floor is 50


def test_new_films_floor_grows_with_age():
    # 1 month old: English needs only the 20-vote minimum; Indian needs 5000 × 30/365 ≈ 411
    assert drop_reason(days_ago(30), "english", False, 20, TODAY) is None
    assert drop_reason(days_ago(30), "indian", False, 420, TODAY) is None
    assert drop_reason(days_ago(30), "indian", False, 400, TODAY) == "below vote floor"
    # 6 months old: English needs ≈ 100
    assert drop_reason(days_ago(182), "english", False, 100, TODAY) is None
    assert drop_reason(days_ago(182), "english", False, 90, TODAY) == "below vote floor"


def test_films_over_a_year_old_need_the_full_floor():
    assert drop_reason(days_ago(400), "english", False, FLOORS["english"] - 1, TODAY) == "below vote floor"


def test_every_language_has_a_group_except_missing():
    from builder.curate import group_of
    assert group_of("ja") == "japanese" and group_of("ta") == "indian"
    assert group_of("ko") == "world" and group_of("xx") == "world"  # xx = silent / no spoken language
    assert group_of(None) is None and group_of("") is None


def test_tmdb_refresh_picks_the_oldest(tmp_path):
    import sqlite3
    import time

    from builder.tmdb import stale
    con = sqlite3.connect(tmp_path / "t.sqlite")
    con.execute("CREATE TABLE details (tmdb_id INTEGER PRIMARY KEY, body TEXT, fetched_at INTEGER)")
    now, day = int(time.time()), 86400
    con.executemany("INSERT INTO details VALUES (?, '{}', ?)", [(1, now - 40 * day), (2, now - 90 * day),
                                                              (3, now - 5 * day), (4, now - 31 * day)])
    assert stale(con, 30, 10) == [2, 1, 4]  # older than 30 days, oldest first
    assert stale(con, 30, 2) == [2, 1]
