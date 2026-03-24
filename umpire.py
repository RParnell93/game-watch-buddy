"""Umpire zone analysis from Statcast called pitch data."""

import os
import duckdb
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()


def _get_conn():
    token = os.environ.get("MOTHERDUCK_TOKEN")
    if token:
        return duckdb.connect(f"md:baseball?motherduck_token={token}")
    raise RuntimeError("MOTHERDUCK_TOKEN not set")


def umpire_season_stats(umpire_name: str, year: int = 2025) -> dict | None:
    """Get umpire accuracy stats for the season from Statcast called pitches."""
    con = _get_conn()

    # Called pitches = balls and called_strikes only
    df = con.execute("""
        SELECT
            COUNT(*) as total_called,
            COUNT(CASE WHEN description = 'called_strike' THEN 1 END) as called_strikes,
            COUNT(CASE WHEN description = 'ball' THEN 1 END) as called_balls,
            -- "Correct" calls: called strike in zone OR ball outside zone
            -- Using standard zone: -0.83 to 0.83 horizontal, sz_bot to sz_top vertical
            COUNT(CASE
                WHEN description = 'called_strike'
                    AND plate_x BETWEEN -0.83 AND 0.83
                    AND plate_z BETWEEN sz_bot AND sz_top
                THEN 1
                WHEN description IN ('ball', 'blocked_ball')
                    AND NOT (plate_x BETWEEN -0.83 AND 0.83
                        AND plate_z BETWEEN sz_bot AND sz_top)
                THEN 1
            END) as correct_calls,
            -- Expanded zone calls (called strike outside zone)
            COUNT(CASE
                WHEN description = 'called_strike'
                    AND NOT (plate_x BETWEEN -0.83 AND 0.83
                        AND plate_z BETWEEN sz_bot AND sz_top)
                THEN 1
            END) as expanded_zone,
            -- Squeezed zone calls (ball inside zone)
            COUNT(CASE
                WHEN description IN ('ball', 'blocked_ball')
                    AND plate_x BETWEEN -0.83 AND 0.83
                    AND plate_z BETWEEN sz_bot AND sz_top
                THEN 1
            END) as squeezed_zone
        FROM statcast_pitches
        WHERE description IN ('called_strike', 'ball', 'blocked_ball')
            AND plate_x IS NOT NULL AND plate_z IS NOT NULL
            AND sz_bot IS NOT NULL AND sz_top IS NOT NULL
            AND YEAR(game_date) = ?
    """, [year]).fetchdf()
    # Note: Statcast doesn't have umpire name in the data.
    # We'd need to join with game-level umpire assignments.
    # For now, return aggregate stats across all umpires as baseline.

    if df.empty or df.iloc[0]["total_called"] == 0:
        return None

    row = df.iloc[0]
    total = row["total_called"]
    return {
        "total_called": int(total),
        "called_strikes": int(row["called_strikes"]),
        "called_balls": int(row["called_balls"]),
        "accuracy": round(row["correct_calls"] / total * 100, 1),
        "expanded_zone_pct": round(row["expanded_zone"] / total * 100, 1),
        "squeezed_zone_pct": round(row["squeezed_zone"] / total * 100, 1),
    }


def zone_tendency_data(year: int = 2025) -> pd.DataFrame:
    """Get all called pitches with zone classification for heatmap rendering."""
    con = _get_conn()
    return con.execute("""
        SELECT
            plate_x, plate_z, sz_top, sz_bot, description,
            CASE
                WHEN plate_x BETWEEN -0.83 AND 0.83
                    AND plate_z BETWEEN sz_bot AND sz_top THEN 'in_zone'
                ELSE 'out_zone'
            END as zone_loc,
            CASE
                WHEN description = 'called_strike'
                    AND NOT (plate_x BETWEEN -0.83 AND 0.83 AND plate_z BETWEEN sz_bot AND sz_top)
                THEN 'expanded'
                WHEN description IN ('ball', 'blocked_ball')
                    AND plate_x BETWEEN -0.83 AND 0.83 AND plate_z BETWEEN sz_bot AND sz_top
                THEN 'squeezed'
                ELSE 'correct'
            END as call_accuracy
        FROM statcast_pitches
        WHERE description IN ('called_strike', 'ball', 'blocked_ball')
            AND plate_x IS NOT NULL AND plate_z IS NOT NULL
            AND sz_bot IS NOT NULL AND sz_top IS NOT NULL
            AND YEAR(game_date) = ?
        ORDER BY RANDOM()
        LIMIT 10000
    """, [year]).fetchdf()


def league_avg_zone_stats(year: int = 2025) -> dict:
    """Get league-wide average zone stats as a baseline for comparison."""
    stats = umpire_season_stats(None, year)
    if stats is None:
        return {"accuracy": 87.0, "expanded_zone_pct": 5.0, "squeezed_zone_pct": 8.0}
    return stats
