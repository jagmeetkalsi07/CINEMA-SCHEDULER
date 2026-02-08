"""
Cinema Showtime Scheduler — Human-Like Algorithm
==================================================
Flask backend that generates cinema schedules following 13 professional
scheduling rules used by real cinema programmers.

Rules implemented:
  HARD RULES (Must Do):
    1.  End-of-Day Cutoff       – No show starts after 11:30 PM
    2.  Global Staggering       – Max 2 shows at same start time; 5-min grid
    3.  Same-Movie Staggering   – Same movie min 30-45 min apart on diff screens
    4.  Regional Restrictions   – Regional movies only 12:00 PM – 9:30 PM
    5.  Sequential Timing       – Show waits for prev movie + TAT on same screen
    6.  Greedy Scheduling       – Target 5 shows/audi (4 if movie+TAT > 180 min)
    7.  Movie of the Week       – Highest allocation → biggest capacity audi
    8.  Audi Allocation         – 4/5+ shows dedicated audi; 2-3 shows time-spread
    10. Bengali Movies          – Strictly 3 PM – 9 PM (prefer 4–7 PM single show)
    11. Format Matching         – 3D→3D, IMAX→IMAX, 4DX→4DX, Atmos→Atmos
    13. Even Spread             – Shows spread across day, not clustered

  SOFT RULES (High Priority):
    9.  Compactness             – No gap between consecutive shows on same audi
    12. 1st Show W/A            – 25-min TAT on first show when 5+ shows on screen
"""

import uuid
import math
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# ========================= CONFIGURATION =========================
EARLIEST_START = 540          # 09:00 AM in minutes
DAY_END = 1410                # 11:30 PM — hard cutoff (Rule 1)
ABSOLUTE_DAY_END = 1440       # midnight — show must finish before this
GRID = 5                      # 5-min rounding grid (Rule 2)
MAX_GLOBAL_STARTS = 2         # max shows starting at same time (Rule 2)
MIN_STAGGER_GAP_SMALL = 45    # same-movie gap for <4 screens (Rule 3)
MIN_STAGGER_GAP_LARGE = 30    # same-movie gap for 5+ screens (Rule 3)
IDEAL_STAGGER_GAP = 60        # ideal same-movie gap (Rule 3)
REGIONAL_START = 720           # 12:00 PM (Rule 4)
REGIONAL_END = 1290            # 9:30 PM (Rule 4)
BENGALI_START = 900            # 3:00 PM (Rule 10)
BENGALI_END = 1260             # 9:00 PM (Rule 10)
BENGALI_PREF_START = 960       # 4:00 PM preferred (Rule 10)
BENGALI_PREF_END = 1140        # 7:00 PM preferred (Rule 10)
PRIME_START = 1080             # 6:00 PM
PRIME_END = 1260               # 9:00 PM
TARGET_SHOWS_PER_SCREEN = 5   # greedy target (Rule 6)
LONG_SHOW_THRESHOLD = 180     # minutes — if movie+TAT > this, 4 shows ok (Rule 6)
WA_TAT = 25                   # without-ads TAT (Rule 12)
MORNING_END = 720             # 12:00 PM
AFTERNOON_START = 720         # 12:00 PM
EVENING_START = 1020          # 5:00 PM
NIGHT_START = 1200            # 8:00 PM
# =================================================================


def align(t):
    """Round up to nearest GRID-minute boundary."""
    return math.ceil(t / GRID) * GRID


def is_bengali(movie):
    """Check if a movie is Bengali based on title or format keywords."""
    title = str(movie.get("title", "")).lower()
    fmt = str(movie.get("format", "")).lower()
    return "bengali" in title or "bengali" in fmt


def is_regional(movie):
    """Check if a movie is marked as regional."""
    return movie.get("isRegional", False)


def is_format_ok(movie, screen):
    """
    Rule 11 — Format Matching.
    3D movies only go to 3D-capable screens, IMAX to IMAX, 4DX to 4DX,
    Atmos to Atmos. Plain 2D movies can go anywhere.
    """
    mf = str(movie.get("format", "")).upper().strip()
    sf = str(screen.get("format", "")).upper().strip()

    # 2D / blank / non-3D movies can go on any screen
    if mf in ("", "2D", "NON-3D"):
        return True

    # For specialty formats, screen must contain the format keyword
    # e.g. movie "IMAX 3D" needs a screen with "IMAX" in its format
    format_keywords = ["IMAX", "4DX", "4D", "ATMOS", "3D", "DOLBY"]
    for kw in format_keywords:
        if kw in mf:
            if kw not in sf:
                return False
    return True


def get_movie_time_window(movie, start_time):
    """
    Get the allowed scheduling window for a movie based on its type.
    Rules 4, 10.
    """
    window_start = start_time
    window_end = DAY_END

    if is_bengali(movie):
        # Rule 10: Bengali strictly 3 PM – 9 PM
        window_start = max(start_time, BENGALI_START)
        window_end = min(DAY_END, BENGALI_END)
    elif is_regional(movie):
        # Rule 4: Regional 12 PM – 9:30 PM
        window_start = max(start_time, REGIONAL_START)
        window_end = min(DAY_END, REGIONAL_END)

    return window_start, window_end


def get_same_movie_min_gap(num_screens):
    """
    Rule 3 — Same-Movie Staggering.
    For <4 screens: min 45 min gap.
    For 5+ screens: min 30 min gap.
    """
    if num_screens < 5:
        return MIN_STAGGER_GAP_SMALL
    return MIN_STAGGER_GAP_LARGE


def check_global_stagger(start, shows):
    """
    Rule 2 — Global Staggering.
    No more than MAX_GLOBAL_STARTS shows can start at the exact same time.
    """
    count = sum(1 for s in shows if s["startTime"] == start)
    return count < MAX_GLOBAL_STARTS


def check_same_movie_stagger(movie_id, screen_id, start, shows, num_screens):
    """
    Rule 3 — Same-Movie Staggering.
    The same movie cannot start within min_gap of itself on a DIFFERENT screen.
    """
    min_gap = get_same_movie_min_gap(num_screens)
    for s in shows:
        if s["movieId"] == movie_id and s["screenId"] != screen_id:
            if abs(s["startTime"] - start) < min_gap:
                return False
    return True


def check_even_spread(movie_id, start, shows, total_allocated):
    """
    Rule 13 — Even Spread.
    Penalize clustering of same movie shows in a narrow time window.
    Returns True if placement is acceptable.
    """
    if total_allocated <= 1:
        return True

    same_movie_times = sorted([s["startTime"] for s in shows if s["movieId"] == movie_id])

    if len(same_movie_times) == 0:
        return True

    # Check for clustering: no more than 2 shows within any 90-min window
    candidate_times = sorted(same_movie_times + [start])
    for i in range(len(candidate_times)):
        window_count = sum(1 for t in candidate_times if abs(t - candidate_times[i]) <= 90)
        if window_count > 2:
            return False

    return True


def can_place(movie, screen, start, shows, num_screens, total_allocated):
    """
    Master validation — checks ALL hard constraints before placing a show.
    """
    dur = movie["duration"]
    tat = movie.get("tat", 15)

    # Rule 1: End of Day
    if start > DAY_END:
        return False

    # Show must finish before absolute day end
    if start + dur > ABSOLUTE_DAY_END:
        return False

    # Rule 5: Sequential Timing (handled externally by screen_time tracking)
    # But double-check no overlap on this screen
    screen_shows = [s for s in shows if s["screenId"] == screen["id"]]
    for s in screen_shows:
        s_end = s["startTime"] + s["duration"] + s.get("tat", 15)
        if start < s_end and start + dur + tat > s["startTime"]:
            # Overlap detected
            if start != s["startTime"]:  # not the same show
                return False

    # Time window checks (Rules 4, 10)
    if is_bengali(movie):
        if start < BENGALI_START or start > BENGALI_END:
            return False
    elif is_regional(movie):
        if start < REGIONAL_START or start > REGIONAL_END:
            return False

    # Rule 2: Global Staggering
    if not check_global_stagger(start, shows):
        return False

    # Rule 3: Same-Movie Staggering
    if not check_same_movie_stagger(movie["id"], screen["id"], start, shows, num_screens):
        return False

    # Rule 13: Even Spread
    if not check_even_spread(movie["id"], start, shows, total_allocated):
        return False

    return True


def find_best_start(movie, screen, earliest, shows, num_screens, total_allocated,
                    prefer_window=None):
    """
    Find the earliest valid start time for a movie on a screen,
    optionally preferring a specific time window.
    """
    window_start, window_end = get_movie_time_window(movie, earliest)
    search_start = align(max(earliest, window_start))

    if prefer_window:
        pw_start, pw_end = prefer_window
        search_start = align(max(search_start, pw_start))
        window_end = min(window_end, pw_end)

    t = search_start
    while t <= window_end:
        if can_place(movie, screen, t, shows, num_screens, total_allocated):
            return t
        t += GRID

    # If preferred window failed, try full window
    if prefer_window:
        t = align(max(earliest, get_movie_time_window(movie, earliest)[0]))
        full_end = get_movie_time_window(movie, earliest)[1]
        while t <= full_end:
            if can_place(movie, screen, t, shows, num_screens, total_allocated):
                return t
            t += GRID

    return None


def make_show(cinema_id, screen_id, movie, start_time):
    """Create a show dict."""
    return {
        "id": str(uuid.uuid4()),
        "cinemaId": cinema_id,
        "screenId": screen_id,
        "movieId": movie["id"],
        "title": movie["title"],
        "format": movie.get("format", "2D"),
        "duration": movie["duration"],
        "tat": movie.get("tat", 15),
        "startTime": start_time,
    }


def get_time_slot_windows(alloc_count, movie, start_time):
    """
    Rule 8 — Audi Allocation time windows.
    Returns list of preferred time windows based on allocation count.
    - 5+ shows: full day spread
    - 3 shows: morning, afternoon/evening, night
    - 2 shows: afternoon, evening/night
    - 1 show: prime time
    """
    window_start, window_end = get_movie_time_window(movie, start_time)

    if is_bengali(movie) and alloc_count == 1:
        # Single Bengali show: prefer 4-7 PM
        return [(BENGALI_PREF_START, BENGALI_PREF_END)]

    if alloc_count >= 5:
        # Spread across full window — evenly divided
        span = window_end - window_start
        slot_size = span // alloc_count
        windows = []
        for i in range(alloc_count):
            w_start = window_start + i * slot_size
            w_end = w_start + slot_size
            windows.append((w_start, min(w_end, window_end)))
        return windows

    if alloc_count == 4:
        # Morning, early afternoon, evening, night
        return [
            (window_start, MORNING_END),
            (AFTERNOON_START, EVENING_START),
            (EVENING_START, NIGHT_START),
            (NIGHT_START, window_end),
        ]

    if alloc_count == 3:
        # Morning, afternoon/evening, night
        return [
            (window_start, AFTERNOON_START),
            (AFTERNOON_START, NIGHT_START),
            (NIGHT_START, window_end),
        ]

    if alloc_count == 2:
        # Afternoon, evening/night
        return [
            (AFTERNOON_START, EVENING_START),
            (EVENING_START, window_end),
        ]

    # 1 show — prime time preferred
    return [(PRIME_START, PRIME_END)]


# =========================================================
# MAIN SCHEDULER ENDPOINT
# =========================================================
@app.route("/schedule", methods=["POST"])
def schedule():
    data = request.json

    cinema = data["cinema"]
    all_movies = {m["id"]: m for m in data["movies"]}
    allocations = {k: int(v) for k, v in data["allocations"].items() if int(v) > 0}
    start_time = data.get("startTime", EARLIEST_START)

    screens = sorted(
        cinema["screens"],
        key=lambda s: int(s.get("capacity", 0)),
        reverse=True,
    )
    num_screens = len(screens)

    # Original allocation counts (for reference)
    original_allocs = dict(allocations)

    # Remaining allocations to place
    remaining = dict(allocations)

    # Ranked movies by allocation count descending (Rule 7)
    ranked_movies = sorted(allocations.keys(), key=lambda m: allocations[m], reverse=True)

    log.info(f"Scheduling for {cinema['name']} — {num_screens} screens, "
             f"{len(ranked_movies)} movies, start={start_time}")

    # ============== PHASE 1: SCREEN COMMITMENT (Rules 7, 8, 11) ==============
    # Assign movies to specific screens based on allocation count and capacity.
    # Highest allocation movie gets the biggest screen.

    screen_primary = {}      # screen_id → primary movie_id
    movie_screens = {}       # movie_id → [screen_ids]
    assigned_screens = set()

    for mid in ranked_movies:
        movie = all_movies[mid]
        count = allocations[mid]
        movie_screens[mid] = []

        # Rule 8: 4/5+ shows = dedicated audi (or 2 if very high)
        if count >= 8:
            needed_screens = 2
        elif count >= 4:
            needed_screens = 1
        else:
            needed_screens = 0  # shared screen

        for s in screens:
            if s["id"] in assigned_screens:
                continue
            if not is_format_ok(movie, s):
                continue

            screen_primary[s["id"]] = mid
            movie_screens[mid].append(s["id"])
            assigned_screens.add(s["id"])

            if len(movie_screens[mid]) >= max(needed_screens, 1):
                break

    # Assign remaining unassigned screens to movies that still need them
    for s in screens:
        if s["id"] not in assigned_screens:
            # Assign to the movie with highest remaining allocation that fits
            for mid in ranked_movies:
                movie = all_movies[mid]
                if is_format_ok(movie, s):
                    if s["id"] not in [sid for sids in movie_screens.values() for sid in sids]:
                        screen_primary[s["id"]] = mid
                        movie_screens[mid].append(s["id"])
                        assigned_screens.add(s["id"])
                        break

    log.info(f"Screen commitments: {screen_primary}")

    # ============== PHASE 2: PRIMARY PLACEMENT (Rules 1-5, 8, 9, 10, 13) ==============
    # Place allocated shows respecting all constraints.
    # Strategy: For each movie, use time-slot windows for even spread.

    shows = []
    screen_time = {s["id"]: align(start_time) for s in screens}

    # Sort movies: Bengali first (they have tightest windows), then by allocation desc
    placement_order = sorted(
        ranked_movies,
        key=lambda mid: (
            0 if is_bengali(all_movies[mid]) else 1,
            -allocations[mid],
        ),
    )

    for mid in placement_order:
        movie = all_movies[mid]
        count = remaining[mid]
        if count <= 0:
            continue

        # Get preferred time windows for this movie (Rule 8)
        time_windows = get_time_slot_windows(count, movie, start_time)

        # Get screens this movie can use
        available_screens = movie_screens.get(mid, [])
        # Also consider other screens where format matches
        for s in screens:
            if s["id"] not in available_screens and is_format_ok(movie, s):
                available_screens.append(s["id"])

        shows_placed_for_movie = 0

        # Try to place one show per time window
        for window_idx, window in enumerate(time_windows):
            if remaining[mid] <= 0:
                break

            placed = False

            # Prefer dedicated screens first, then others
            screen_order = []
            for sid in available_screens:
                if screen_primary.get(sid) == mid:
                    screen_order.insert(0, sid)
                else:
                    screen_order.append(sid)

            for sid in screen_order:
                screen = next(s for s in screens if s["id"] == sid)
                earliest = align(screen_time[sid])

                best_start = find_best_start(
                    movie, screen, earliest, shows, num_screens,
                    original_allocs.get(mid, 0),
                    prefer_window=window,
                )

                if best_start is not None:
                    show = make_show(cinema["id"], sid, movie, best_start)
                    shows.append(show)
                    screen_time[sid] = best_start + movie["duration"] + movie.get("tat", 15)
                    remaining[mid] -= 1
                    shows_placed_for_movie += 1
                    placed = True
                    break

            if not placed:
                # Window missed — try to place anywhere valid
                for sid in screen_order:
                    screen = next(s for s in screens if s["id"] == sid)
                    earliest = align(screen_time[sid])

                    best_start = find_best_start(
                        movie, screen, earliest, shows, num_screens,
                        original_allocs.get(mid, 0),
                    )
                    if best_start is not None:
                        show = make_show(cinema["id"], sid, movie, best_start)
                        shows.append(show)
                        screen_time[sid] = best_start + movie["duration"] + movie.get("tat", 15)
                        remaining[mid] -= 1
                        shows_placed_for_movie += 1
                        break

        # If still remaining, force-place on any screen
        attempts = 0
        while remaining[mid] > 0 and attempts < 50:
            attempts += 1
            placed = False
            for sid in available_screens:
                screen = next(s for s in screens if s["id"] == sid)
                earliest = align(screen_time[sid])

                best_start = find_best_start(
                    movie, screen, earliest, shows, num_screens,
                    original_allocs.get(mid, 0),
                )
                if best_start is not None:
                    show = make_show(cinema["id"], sid, movie, best_start)
                    shows.append(show)
                    screen_time[sid] = best_start + movie["duration"] + movie.get("tat", 15)
                    remaining[mid] -= 1
                    placed = True
                    break

            if not placed:
                log.warning(f"Could not place all shows for {movie['title']}. "
                            f"Remaining: {remaining[mid]}")
                break

    log.info(f"After primary placement: {len(shows)} shows, "
             f"remaining unplaced: {sum(v for v in remaining.values() if v > 0)}")

    # ============== PHASE 3: GREEDY FILL (Rule 6) ==============
    # Target minimum 5 shows per screen (4 if long movies).
    # Fill remaining gaps on each screen with available movies.

    for screen in screens:
        sid = screen["id"]
        screen_shows = [s for s in shows if s["screenId"] == sid]
        screen_show_count = len(screen_shows)

        # Determine target (Rule 6)
        primary_mid = screen_primary.get(sid)
        if primary_mid:
            primary_movie = all_movies[primary_mid]
            effective_duration = primary_movie["duration"] + primary_movie.get("tat", 15)
            target = 4 if effective_duration > LONG_SHOW_THRESHOLD else TARGET_SHOWS_PER_SCREEN
        else:
            target = TARGET_SHOWS_PER_SCREEN

        if screen_show_count >= target:
            continue

        # How many more shows do we need?
        need = target - screen_show_count
        idle_steps = 0

        for _ in range(need):
            t = align(screen_time[sid])
            if t > DAY_END:
                break

            placed = False

            # Candidate movies: prefer the screen's primary movie, then others
            candidates = []
            if primary_mid and remaining.get(primary_mid, 0) > 0:
                candidates.append(primary_mid)

            # Add other movies that still have remaining allocation
            candidates += [
                mid for mid in ranked_movies
                if mid not in candidates and remaining.get(mid, 0) > 0
            ]

            # Also add movies with 0 remaining (for greedy fill beyond allocation)
            candidates += [
                mid for mid in ranked_movies
                if mid not in candidates
            ]

            for mid in candidates:
                movie = all_movies[mid]
                if not is_format_ok(movie, screen):
                    continue

                best_start = find_best_start(
                    movie, screen, t, shows, num_screens,
                    original_allocs.get(mid, 0),
                )
                if best_start is not None:
                    show = make_show(cinema["id"], sid, movie, best_start)
                    shows.append(show)
                    screen_time[sid] = best_start + movie["duration"] + movie.get("tat", 15)
                    if remaining.get(mid, 0) > 0:
                        remaining[mid] -= 1
                    placed = True
                    break

            if not placed:
                # Advance time and try again
                screen_time[sid] += GRID
                idle_steps += 1
                if idle_steps > 18:  # 90 min of no placement → stop
                    break

    log.info(f"After greedy fill: {len(shows)} shows")

    # ============== PHASE 4: POST-PROCESSING ==============

    # Rule 12: W/A (Without Ads) — 25 min TAT on first show when 5+ on screen
    for screen in screens:
        sid = screen["id"]
        screen_shows = sorted(
            [s for s in shows if s["screenId"] == sid],
            key=lambda s: s["startTime"],
        )

        if len(screen_shows) >= 5:
            first_show = screen_shows[0]
            original_tat = first_show["tat"]
            if original_tat > WA_TAT:
                saved_time = original_tat - WA_TAT
                first_show["tat"] = WA_TAT
                log.info(f"Applied W/A to first show on {screen.get('name', sid)}, "
                         f"saved {saved_time} min")

                # Repack subsequent shows to close the gap (Rule 9: Compactness)
                for i in range(1, len(screen_shows)):
                    prev = screen_shows[i - 1]
                    prev_end = prev["startTime"] + prev["duration"] + prev["tat"]
                    curr = screen_shows[i]
                    new_start = align(prev_end)

                    # Only move earlier, never later (preserve constraint validity)
                    if new_start < curr["startTime"]:
                        # Verify the move is still valid
                        screen_obj = screen
                        other_shows = [s for s in shows if s["id"] != curr["id"]]
                        movie = all_movies.get(curr["movieId"])
                        if movie and can_place(movie, screen_obj, new_start, other_shows,
                                               num_screens, original_allocs.get(curr["movieId"], 0)):
                            curr["startTime"] = new_start

    # Final sort
    shows.sort(key=lambda x: (x["screenId"], x["startTime"]))

    # Log summary
    for screen in screens:
        sid = screen["id"]
        screen_shows = [s for s in shows if s["screenId"] == sid]
        log.info(f"  {screen.get('name', sid)}: {len(screen_shows)} shows")

    log.info(f"Total: {len(shows)} shows generated")

    return jsonify(shows)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
