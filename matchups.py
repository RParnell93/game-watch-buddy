"""Pull hitter vs pitcher matchup data from MotherDuck Statcast tables."""

import os
import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

_conn = None


def _get_token():
    try:
        import streamlit as st
        return st.secrets["MOTHERDUCK_TOKEN"]
    except Exception:
        return os.environ.get("MOTHERDUCK_TOKEN")


def _get_conn():
    global _conn
    if _conn is None:
        token = _get_token()
        if token:
            _conn = duckdb.connect(f"md:baseball?motherduck_token={token}")
        else:
            raise RuntimeError("MOTHERDUCK_TOKEN not set")
    return _conn


def batter_profile(batter_id: int, year: int = 2025) -> dict | None:
    """Get a batter's season stats from Statcast data."""
    con = _get_conn()
    df = con.execute("""
        SELECT
            COUNT(*) as pitches_seen,
            COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) as plate_appearances,
            COUNT(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 END) as hits,
            COUNT(CASE WHEN events = 'home_run' THEN 1 END) as hr,
            COUNT(CASE WHEN events IN ('walk','hit_by_pitch') THEN 1 END) as bb_hbp,
            COUNT(CASE WHEN events = 'strikeout' THEN 1 END) as so,
            AVG(CASE WHEN launch_speed IS NOT NULL THEN launch_speed END) as avg_exit_velo,
            AVG(CASE WHEN launch_angle IS NOT NULL THEN launch_angle END) as avg_launch_angle,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY launch_speed) as max_exit_velo_p90,
            AVG(CASE WHEN description = 'swinging_strike' THEN 1.0 ELSE 0.0 END) as whiff_rate,
            AVG(CASE WHEN description IN ('called_strike','swinging_strike','foul','foul_tip') THEN 1.0
                 WHEN description IN ('ball','blocked_ball','hit_by_pitch') THEN 0.0
                 ELSE NULL END) as zone_contact_proxy
        FROM statcast_pitches
        WHERE batter = ? AND YEAR(game_date) = ?
    """, [batter_id, year]).fetchdf()

    if df.empty or df.iloc[0]["pitches_seen"] == 0:
        return None

    row = df.iloc[0]
    pa = row["plate_appearances"]
    if pa == 0:
        return None

    return {
        "pitches_seen": int(row["pitches_seen"]),
        "pa": int(pa),
        "hits": int(row["hits"]),
        "hr": int(row["hr"]),
        "bb_hbp": int(row["bb_hbp"]),
        "so": int(row["so"]),
        "avg": round(row["hits"] / max(pa - row["bb_hbp"], 1), 3),
        "obp": round((row["hits"] + row["bb_hbp"]) / pa, 3),
        "avg_exit_velo": round(row["avg_exit_velo"], 1) if pd.notna(row["avg_exit_velo"]) else None,
        "avg_launch_angle": round(row["avg_launch_angle"], 1) if pd.notna(row["avg_launch_angle"]) else None,
        "max_ev_p90": round(row["max_exit_velo_p90"], 1) if pd.notna(row["max_exit_velo_p90"]) else None,
        "whiff_rate": round(row["whiff_rate"] * 100, 1) if pd.notna(row["whiff_rate"]) else None,
    }


def pitcher_profile(pitcher_id: int, year: int = 2025) -> dict | None:
    """Get a pitcher's season stats and arsenal from Statcast data."""
    con = _get_conn()

    # Overall stats
    df = con.execute("""
        SELECT
            COUNT(*) as pitches,
            COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) as batters_faced,
            COUNT(CASE WHEN events = 'strikeout' THEN 1 END) as so,
            COUNT(CASE WHEN events IN ('walk','hit_by_pitch') THEN 1 END) as bb_hbp,
            COUNT(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 END) as hits_allowed,
            COUNT(CASE WHEN events = 'home_run' THEN 1 END) as hr_allowed,
            AVG(release_speed) as avg_velo,
            AVG(CASE WHEN description = 'swinging_strike' THEN 1.0 ELSE 0.0 END) as whiff_rate,
            AVG(CASE WHEN description = 'called_strike' THEN 1.0 ELSE 0.0 END) as called_strike_rate
        FROM statcast_pitches
        WHERE pitcher = ? AND YEAR(game_date) = ?
    """, [pitcher_id, year]).fetchdf()

    if df.empty or df.iloc[0]["pitches"] == 0:
        return None

    row = df.iloc[0]
    bf = row["batters_faced"]
    if bf == 0:
        return None

    # Arsenal breakdown
    arsenal_df = con.execute("""
        SELECT
            pitch_name,
            COUNT(*) as count,
            ROUND(AVG(release_speed), 1) as avg_velo,
            ROUND(AVG(CASE WHEN description = 'swinging_strike' THEN 1.0 ELSE 0.0 END) * 100, 1) as whiff_pct
        FROM statcast_pitches
        WHERE pitcher = ? AND YEAR(game_date) = ?
            AND pitch_name IS NOT NULL AND pitch_name != ''
        GROUP BY pitch_name
        ORDER BY count DESC
    """, [pitcher_id, year]).fetchdf()

    total_pitches = arsenal_df["count"].sum()
    arsenal = []
    for _, r in arsenal_df.iterrows():
        arsenal.append({
            "pitch": r["pitch_name"],
            "usage": round(r["count"] / total_pitches * 100, 1),
            "velo": r["avg_velo"],
            "whiff_pct": r["whiff_pct"],
        })

    return {
        "pitches": int(row["pitches"]),
        "batters_faced": int(bf),
        "so": int(row["so"]),
        "bb_hbp": int(row["bb_hbp"]),
        "hits_allowed": int(row["hits_allowed"]),
        "hr_allowed": int(row["hr_allowed"]),
        "k_rate": round(row["so"] / bf * 100, 1),
        "bb_rate": round(row["bb_hbp"] / bf * 100, 1),
        "avg_velo": round(row["avg_velo"], 1) if pd.notna(row["avg_velo"]) else None,
        "whiff_rate": round(row["whiff_rate"] * 100, 1) if pd.notna(row["whiff_rate"]) else None,
        "arsenal": arsenal,
    }


def head_to_head(batter_id: int, pitcher_id: int) -> dict | None:
    """Get historical batter vs pitcher matchup stats across all available years."""
    con = _get_conn()
    df = con.execute("""
        SELECT
            COUNT(*) as pitches,
            COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) as pa,
            COUNT(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 END) as hits,
            COUNT(CASE WHEN events = 'home_run' THEN 1 END) as hr,
            COUNT(CASE WHEN events = 'strikeout' THEN 1 END) as so,
            COUNT(CASE WHEN events IN ('walk','hit_by_pitch') THEN 1 END) as bb,
            STRING_AGG(DISTINCT CAST(YEAR(game_date) AS VARCHAR), ', ' ORDER BY CAST(YEAR(game_date) AS VARCHAR)) as years
        FROM statcast_pitches
        WHERE batter = ? AND pitcher = ?
    """, [batter_id, pitcher_id]).fetchdf()

    if df.empty or df.iloc[0]["pa"] == 0:
        return None

    row = df.iloc[0]
    pa = row["pa"]
    return {
        "pa": int(pa),
        "pitches": int(row["pitches"]),
        "hits": int(row["hits"]),
        "hr": int(row["hr"]),
        "so": int(row["so"]),
        "bb": int(row["bb"]),
        "avg": round(row["hits"] / max(pa - row["bb"], 1), 3),
        "years": row["years"],
    }


def batter_vs_pitch_type(batter_id: int, year: int = 2025) -> pd.DataFrame:
    """Get batter performance broken down by pitch type."""
    con = _get_conn()
    return con.execute("""
        SELECT
            pitch_name,
            COUNT(*) as pitches,
            ROUND(AVG(CASE WHEN description = 'swinging_strike' THEN 1.0 ELSE 0.0 END) * 100, 1) as whiff_pct,
            ROUND(AVG(CASE WHEN launch_speed IS NOT NULL THEN launch_speed END), 1) as avg_ev,
            COUNT(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 END) as hits,
            COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) as abs,
            ROUND(AVG(CASE WHEN woba_value IS NOT NULL THEN woba_value END), 3) as woba,
            ROUND(AVG(CASE WHEN estimated_woba_using_speedangle IS NOT NULL THEN estimated_woba_using_speedangle END), 3) as xwoba
        FROM statcast_pitches
        WHERE batter = ? AND YEAR(game_date) = ?
            AND pitch_name IS NOT NULL AND pitch_name != ''
        GROUP BY pitch_name
        HAVING COUNT(*) >= 5
        ORDER BY pitches DESC
    """, [batter_id, year]).fetchdf()
