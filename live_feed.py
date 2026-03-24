"""Poll MLB Stats API for live game data."""

import statsapi
from datetime import datetime


def get_todays_games() -> list[dict]:
    """Get all games scheduled for today with status."""
    today = datetime.now().strftime("%m/%d/%Y")
    schedule = statsapi.schedule(date=today)
    games = []
    for g in schedule:
        games.append({
            "game_id": g["game_id"],
            "away": g["away_name"],
            "home": g["home_name"],
            "away_short": g["away_abbreviation"] if "away_abbreviation" in g else g["away_name"][:3].upper(),
            "home_short": g["home_abbreviation"] if "home_abbreviation" in g else g["home_name"][:3].upper(),
            "status": g["status"],
            "away_score": g.get("away_score", 0),
            "home_score": g.get("home_score", 0),
            "game_time": g.get("game_datetime", ""),
            "summary": g.get("summary", ""),
        })
    return games


def get_live_feed(game_id: int) -> dict:
    """Get the full live feed for a game."""
    return statsapi.get("game", {"gamePk": game_id})


def parse_current_matchup(feed: dict) -> dict | None:
    """Extract the current batter/pitcher matchup from a live feed."""
    live = feed.get("liveData", {})
    plays = live.get("plays", {})
    current = plays.get("currentPlay", {})

    if not current:
        return None

    matchup = current.get("matchup", {})
    batter = matchup.get("batter", {})
    pitcher = matchup.get("pitcher", {})
    count = current.get("count", {})
    runners = current.get("runners", [])

    # Get batter handedness and pitcher handedness
    bat_side = matchup.get("batSide", {}).get("code", "")
    pitch_hand = matchup.get("pitchHand", {}).get("code", "")

    # Current pitches in this at-bat
    play_events = current.get("playEvents", [])
    pitches = [e for e in play_events if e.get("isPitch", False)]

    return {
        "batter_id": batter.get("id"),
        "batter_name": batter.get("fullName", "Unknown"),
        "pitcher_id": pitcher.get("id"),
        "pitcher_name": pitcher.get("fullName", "Unknown"),
        "bat_side": bat_side,
        "pitch_hand": pitch_hand,
        "balls": count.get("balls", 0),
        "strikes": count.get("strikes", 0),
        "outs": count.get("outs", 0),
        "runners_on": [r.get("movement", {}).get("originBase") for r in runners if r.get("movement", {}).get("originBase")],
        "pitches_this_ab": pitches,
        "inning": current.get("about", {}).get("inning", 0),
        "half_inning": current.get("about", {}).get("halfInning", "top"),
    }


def parse_game_state(feed: dict) -> dict:
    """Extract overall game state from live feed."""
    game_data = feed.get("gameData", {})
    live = feed.get("liveData", {})
    linescore = live.get("linescore", {})

    teams = game_data.get("teams", {})
    away = teams.get("away", {})
    home = teams.get("home", {})

    # Get umpire info - check live feed first, fall back to boxscore
    officials = game_data.get("officials", [])
    if not officials:
        try:
            box = statsapi.get("game_boxscore", {"gamePk": game_data.get("game", {}).get("pk", 0)})
            officials = box.get("officials", [])
        except Exception:
            officials = []
    hp_umpire = None
    for off in officials:
        if off.get("officialType") == "Home Plate":
            hp_umpire = off.get("official", {}).get("fullName")
            break

    status = game_data.get("status", {})

    return {
        "away_name": away.get("name", "Away"),
        "home_name": home.get("name", "Home"),
        "away_abbr": away.get("abbreviation", "AWY"),
        "home_abbr": home.get("abbreviation", "HME"),
        "away_score": linescore.get("teams", {}).get("away", {}).get("runs", 0),
        "home_score": linescore.get("teams", {}).get("home", {}).get("runs", 0),
        "inning": linescore.get("currentInning", 0),
        "half_inning": linescore.get("inningHalf", "Top"),
        "status": status.get("detailedState", "Unknown"),
        "hp_umpire": hp_umpire,
    }


def get_all_at_bats(feed: dict) -> list[dict]:
    """Get all completed at-bats from the game so far."""
    live = feed.get("liveData", {})
    plays = live.get("plays", {})
    all_plays = plays.get("allPlays", [])

    at_bats = []
    for play in all_plays:
        matchup = play.get("matchup", {})
        result = play.get("result", {})
        at_bats.append({
            "batter_id": matchup.get("batter", {}).get("id"),
            "batter_name": matchup.get("batter", {}).get("fullName"),
            "pitcher_id": matchup.get("pitcher", {}).get("id"),
            "pitcher_name": matchup.get("pitcher", {}).get("fullName"),
            "result": result.get("event", ""),
            "description": result.get("description", ""),
            "rbi": result.get("rbi", 0),
            "inning": play.get("about", {}).get("inning"),
            "half_inning": play.get("about", {}).get("halfInning"),
        })
    return at_bats
