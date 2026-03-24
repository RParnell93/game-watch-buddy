# Game Watch Buddy

## Overview
Live MLB game companion app. Shows real-time matchup data, pitcher arsenals, batter profiles, head-to-head history, and umpire zone tendencies during live games.

## Tech Stack
- Python 3.12, Streamlit, DuckDB (v1.4.4), plotly, MLB-StatsAPI
- Data: MotherDuck cloud DuckDB (baseball database, read-only)
- Live feed: MLB Stats API (free, no auth)

## Running
- `streamlit run app.py`

## Architecture
- app.py: Streamlit UI, game selector, auto-refresh loop
- live_feed.py: MLB Stats API polling, parse matchups/game state
- matchups.py: MotherDuck queries for batter/pitcher profiles, H2H, pitch type splits
- umpire.py: Zone accuracy analysis from Statcast called pitch data

## Data Source
- Reads from MotherDuck "baseball" database (shared with baseball-analytics project)
- MOTHERDUCK_TOKEN in .env
- Tables used: statcast_pitches (1.5M+ rows, 2024-2026)
- Live data: statsapi.mlb.com (free, updates every ~15 seconds during games)

## Secrets
- .env: MOTHERDUCK_TOKEN
- .streamlit/secrets.toml: for Streamlit Cloud deployment
