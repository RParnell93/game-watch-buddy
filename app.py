"""Game Watch Buddy - Live MLB game companion with matchup and umpire data."""

import streamlit as st
import time
from live_feed import get_todays_games, get_live_feed, parse_current_matchup, parse_game_state, get_all_at_bats
import plotly.graph_objects as go
from matchups import batter_profile, pitcher_profile, head_to_head, batter_vs_pitch_type
from umpire import league_avg_zone_stats

st.set_page_config(
    page_title="Game Watch Buddy",
    page_icon="&#9918;",
    layout="wide",
)

# ── Custom CSS ──
st.markdown("""
<style>
    .matchup-header {
        font-size: clamp(1.3rem, 3vw, 2rem);
        font-weight: 700;
        text-align: center;
        margin: 0.5rem 0;
    }
    .stat-card {
        background: #1A1D23;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 4px 0;
        overflow-wrap: break-word;
    }
    .stat-label {
        color: #888;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stat-value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #FAFAFA;
    }
    .count-display {
        font-size: 2rem;
        font-weight: 700;
        text-align: center;
        font-family: monospace;
    }
    .score-display {
        font-size: 1.8rem;
        font-weight: 700;
        text-align: center;
    }
    .vs-text {
        color: #E63946;
        font-size: 0.9rem;
        text-align: center;
    }
    .arsenal-row {
        display: flex;
        justify-content: space-between;
        padding: 4px 0;
        border-bottom: 1px solid #2A2D33;
    }
    .h2h-banner {
        background: linear-gradient(135deg, #1A1D23, #2A2D33);
        border-left: 3px solid #E63946;
        border-radius: 4px;
        padding: 10px 14px;
        margin: 8px 0;
    }
    .inning-info {
        text-align: center;
        color: #888;
        font-size: 0.85rem;
    }
    .umpire-badge {
        background: #2A2D33;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.8rem;
        display: inline-block;
    }
    @media (max-width: 768px) {
        .stat-value { font-size: 1.1rem; }
        .count-display { font-size: 1.5rem; }
    }
</style>
""", unsafe_allow_html=True)


def render_stat_card(label: str, value, color: str = "#FAFAFA"):
    return f"""
    <div class="stat-card">
        <div class="stat-label">{label}</div>
        <div class="stat-value" style="color: {color};">{value}</div>
    </div>
    """


def render_scoreboard(state: dict):
    """Render the game scoreboard."""
    half = state["half_inning"]
    arrow = "\u25B2" if half.lower() == "top" else "\u25BC"

    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 1rem;">
        <div class="inning-info">{arrow} {state['inning']} - {state['status']}</div>
        <div class="score-display">
            {state['away_abbr']} <span style="color: #E63946;">{state['away_score']}</span>
            &nbsp;-&nbsp;
            <span style="color: #E63946;">{state['home_score']}</span> {state['home_abbr']}
        </div>
        {f'<div class="umpire-badge">HP: {state["hp_umpire"]}</div>' if state.get("hp_umpire") else ""}
    </div>
    """, unsafe_allow_html=True)


def render_count(matchup: dict):
    """Render balls-strikes-outs display."""
    b = matchup["balls"]
    s = matchup["strikes"]
    o = matchup["outs"]
    runners = matchup.get("runners_on", [])
    bases = ""
    if "1B" in runners:
        bases += " 1B"
    if "2B" in runners:
        bases += " 2B"
    if "3B" in runners:
        bases += " 3B"
    if not bases:
        bases = " Bases empty"

    st.markdown(f"""
    <div class="count-display">
        <span style="color: #4CAF50;">{b}</span> -
        <span style="color: #E63946;">{s}</span>
    </div>
    <div style="text-align: center; color: #888; font-size: 0.85rem;">
        {o} out {"&bull;" + bases if bases else ""}
    </div>
    """, unsafe_allow_html=True)


def render_batter_card(batter_id: int, name: str, bat_side: str):
    """Render batter stats card."""
    st.markdown(f'<div class="matchup-header">{name}</div>', unsafe_allow_html=True)
    st.caption(f"Bats: {'Left' if bat_side == 'L' else 'Right' if bat_side == 'R' else 'Switch'}")

    # Try 2025 first, fall back to 2024
    stats = batter_profile(batter_id, 2025)
    year_label = "2025"
    if stats is None:
        stats = batter_profile(batter_id, 2024)
        year_label = "2024"
    if stats is None:
        st.info("No Statcast data available")
        return

    st.caption(f"{year_label} Statcast ({stats['pa']} PA)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(render_stat_card("AVG", f".{str(stats['avg'])[2:]}"), unsafe_allow_html=True)
    with col2:
        st.markdown(render_stat_card("OBP", f".{str(stats['obp'])[2:]}"), unsafe_allow_html=True)
    with col3:
        st.markdown(render_stat_card("HR", stats["hr"]), unsafe_allow_html=True)

    col4, col5, col6 = st.columns(3)
    with col4:
        ev = stats["avg_exit_velo"] or "-"
        st.markdown(render_stat_card("Avg EV", f"{ev} mph"), unsafe_allow_html=True)
    with col5:
        la = stats["avg_launch_angle"] or "-"
        st.markdown(render_stat_card("Avg LA", f"{la}\u00B0"), unsafe_allow_html=True)
    with col6:
        whiff = stats["whiff_rate"] or "-"
        st.markdown(render_stat_card("Whiff%", f"{whiff}%"), unsafe_allow_html=True)


def render_batter_vs_pitches(batter_id: int, year: int = 2025):
    """Render batter performance by pitch type as a table + bar chart."""
    df = batter_vs_pitch_type(batter_id, year)
    if df is None or df.empty:
        df = batter_vs_pitch_type(batter_id, 2024)
    if df is None or df.empty:
        return

    st.markdown("**vs Pitch Types**")

    # Add batting avg column
    df["avg"] = df.apply(lambda r: round(r["hits"] / r["abs"], 3) if r["abs"] > 0 else 0, axis=1)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["pitch_name"],
        y=df["whiff_pct"],
        name="Whiff%",
        marker_color="#E63946",
        text=df["whiff_pct"].apply(lambda v: f"{v}%"),
        textposition="outside",
        textfont=dict(size=11),
    ))
    fig.add_trace(go.Bar(
        x=df["pitch_name"],
        y=df["avg_ev"],
        name="Avg EV",
        marker_color="#42A5F5",
        text=df["avg_ev"].apply(lambda v: f"{v}" if v and v > 0 else "-"),
        textposition="outside",
        textfont=dict(size=11),
        visible="legendonly",
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=250,
        margin=dict(l=0, r=0, t=30, b=0),
        showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=1.15, x=0.5, xanchor="center"),
        yaxis=dict(visible=False),
        xaxis=dict(tickfont=dict(size=11)),
        barmode="group",
        bargap=0.3,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

    # Compact table
    display_df = df[["pitch_name", "pitches", "whiff_pct", "avg_ev", "avg", "woba", "xwoba"]].copy()
    display_df.columns = ["Pitch", "N", "Whiff%", "Avg EV", "AVG", "wOBA", "xwOBA"]
    display_df["AVG"] = display_df["AVG"].apply(lambda v: f".{str(v)[2:]}" if v > 0 else "-")
    display_df["Avg EV"] = display_df["Avg EV"].apply(lambda v: f"{v}" if v and v > 0 else "-")
    fmt_woba = lambda v: f".{str(round(v, 3))[2:]}" if v and v > 0 else "-"
    display_df["wOBA"] = display_df["wOBA"].apply(fmt_woba)
    display_df["xwOBA"] = display_df["xwOBA"].apply(fmt_woba)
    st.dataframe(display_df, hide_index=True, use_container_width=True)


def render_pitcher_card(pitcher_id: int, name: str, pitch_hand: str):
    """Render pitcher stats and arsenal card."""
    st.markdown(f'<div class="matchup-header">{name}</div>', unsafe_allow_html=True)
    st.caption(f"Throws: {'Left' if pitch_hand == 'L' else 'Right'}")

    stats = pitcher_profile(pitcher_id, 2025)
    year_label = "2025"
    if stats is None:
        stats = pitcher_profile(pitcher_id, 2024)
        year_label = "2024"
    if stats is None:
        st.info("No Statcast data available")
        return

    st.caption(f"{year_label} Statcast ({stats['batters_faced']} BF)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(render_stat_card("K%", f"{stats['k_rate']}%"), unsafe_allow_html=True)
    with col2:
        st.markdown(render_stat_card("BB%", f"{stats['bb_rate']}%"), unsafe_allow_html=True)
    with col3:
        velo = stats["avg_velo"] or "-"
        st.markdown(render_stat_card("Velo", f"{velo} mph"), unsafe_allow_html=True)

    # Arsenal breakdown
    if stats["arsenal"]:
        st.markdown("**Arsenal**")
        for pitch in stats["arsenal"][:6]:
            st.markdown(f"""
            <div class="arsenal-row">
                <span>{pitch['pitch']}</span>
                <span style="color: #888;">{pitch['usage']}% | {pitch['velo']} mph | {pitch['whiff_pct']}% whiff</span>
            </div>
            """, unsafe_allow_html=True)


def render_h2h(batter_id: int, pitcher_id: int, batter_name: str, pitcher_name: str):
    """Render head-to-head matchup history."""
    h2h = head_to_head(batter_id, pitcher_id)
    if h2h is None:
        st.markdown(f"""
        <div class="h2h-banner">
            <span style="color: #888;">No previous matchup data</span>
        </div>
        """, unsafe_allow_html=True)
        return

    avg_display = f".{str(h2h['avg'])[2:]}" if h2h["avg"] > 0 else ".000"
    st.markdown(f"""
    <div class="h2h-banner">
        <div style="font-weight: 700; margin-bottom: 4px;">Head-to-Head ({h2h['years']})</div>
        <div>{h2h['pa']} PA: {avg_display} AVG, {h2h['hits']} H, {h2h['hr']} HR, {h2h['so']} K, {h2h['bb']} BB</div>
    </div>
    """, unsafe_allow_html=True)


def render_umpire_panel(umpire_name: str | None):
    """Render umpire zone tendencies."""
    if not umpire_name:
        st.caption("Umpire data unavailable")
        return

    st.markdown(f"**HP Umpire: {umpire_name}**")

    # Show league baseline stats
    baseline = league_avg_zone_stats(2025)
    if baseline:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(render_stat_card("Accuracy", f"{baseline['accuracy']}%"), unsafe_allow_html=True)
        with col2:
            st.markdown(render_stat_card("Expand%", f"{baseline['expanded_zone_pct']}%", "#FFA726"), unsafe_allow_html=True)
        with col3:
            st.markdown(render_stat_card("Squeeze%", f"{baseline['squeezed_zone_pct']}%", "#42A5F5"), unsafe_allow_html=True)
        st.caption("League avg zone stats (umpire-specific coming soon)")


def render_game_log(feed: dict, current_matchup: dict | None):
    """Render recent at-bat results."""
    at_bats = get_all_at_bats(feed)
    if not at_bats:
        return

    recent = at_bats[-8:]
    recent.reverse()

    st.markdown("**Recent At-Bats**")
    for ab in recent:
        result = ab["result"] or "In Progress"
        color = "#4CAF50" if result in ("Single", "Double", "Triple", "Home Run") else "#888"
        rbi_text = f" ({ab['rbi']} RBI)" if ab["rbi"] else ""
        st.markdown(
            f'<div style="padding: 2px 0; border-bottom: 1px solid #1A1D23;">'
            f'<span style="color: {color}; font-weight: 600;">{result}{rbi_text}</span> '
            f'<span style="color: #666; font-size: 0.8rem;">{ab["batter_name"]} vs {ab["pitcher_name"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Main App ──
st.title("Game Watch Buddy")

# Game selector
games = get_todays_games()

if not games:
    st.warning("No games scheduled today.")
    st.stop()

game_options = {}
for g in games:
    time_str = f" - {g['game_time']}" if g["game_time"] and g["status"] in ("Scheduled", "Pre-Game") else ""
    label = f"{g['away']} @ {g['home']} ({g['status']}{time_str})"
    game_options[label] = g["game_id"]

selected_label = st.selectbox("Select a game", options=list(game_options.keys()))
game_id = game_options[selected_label]

# Auto-refresh toggle
auto_refresh = st.toggle("Auto-refresh (20s)", value=False)

# Fetch live data
feed = get_live_feed(game_id)
state = parse_game_state(feed)
matchup = parse_current_matchup(feed)

# Scoreboard
render_scoreboard(state)

st.divider()

if state["status"] in ("Pre-Game", "Scheduled", "Warmup"):
    st.info("Game hasn't started yet. Matchups will appear once the first pitch is thrown.")
    if auto_refresh:
        time.sleep(20)
        st.rerun()
    st.stop()

if matchup and matchup["batter_id"] and matchup["pitcher_id"]:
    # Count display
    render_count(matchup)

    st.divider()

    # Head-to-head banner
    render_h2h(matchup["batter_id"], matchup["pitcher_id"], matchup["batter_name"], matchup["pitcher_name"])

    # Batter vs Pitcher side by side
    col_batter, col_pitcher = st.columns(2)

    with col_batter:
        render_batter_card(matchup["batter_id"], matchup["batter_name"], matchup["bat_side"])
        render_batter_vs_pitches(matchup["batter_id"])

    with col_pitcher:
        render_pitcher_card(matchup["pitcher_id"], matchup["pitcher_name"], matchup["pitch_hand"])

    st.divider()

    # Umpire panel
    render_umpire_panel(state.get("hp_umpire"))

    st.divider()

    # Pitch-by-pitch this AB
    pitches_ab = matchup.get("pitches_this_ab", [])
    if pitches_ab:
        st.markdown("**This At-Bat**")
        for p in pitches_ab:
            details = p.get("pitchData", {})
            desc = p.get("details", {})
            velo = details.get("startSpeed", "")
            pitch_type = desc.get("type", {}).get("description", "")
            call = desc.get("description", "")
            velo_str = f" ({velo} mph)" if velo else ""
            st.markdown(f"- {pitch_type}{velo_str} - {call}")

elif state["status"] in ("Final", "Game Over"):
    st.markdown("### Final")
    render_game_log(feed, matchup)
else:
    st.info("Waiting for next at-bat...")

# Game log
if matchup:
    st.divider()
    render_game_log(feed, matchup)

# Auto-refresh
if auto_refresh and state["status"] not in ("Final", "Game Over"):
    time.sleep(20)
    st.rerun()
