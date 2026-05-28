"""
Rowing power analysis — Streamlit app.

Run locally:
    streamlit run notebooks/power_analysis.py

Deploy (Streamlit Community Cloud):
    Push repo to GitHub → share.streamlit.io → set requirements file to notebooks/requirements.txt
"""

import json
from urllib.request import urlopen
from urllib.error import URLError

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Erg Power Analysis", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Erg Power Analysis")
    host_raw = st.text_input("Erg host", value="192.168.0.224:8501")
    host = ("http://" + host_raw.rstrip("/")) if "://" not in host_raw else host_raw.rstrip("/")

    if st.button("Load Sessions", use_container_width=True):
        try:
            with urlopen(f"{host}/api/history", timeout=8) as r:
                st.session_state.sessions = json.loads(r.read())
                st.session_state.host = host
        except URLError as e:
            st.error(f"Cannot reach {host}: {e}")

    sessions = st.session_state.get("sessions", [])
    if not sessions:
        st.info("Click **Load Sessions** to begin.")
        st.stop()

    opts = {s["label"]: s["id"] for s in sessions}
    chosen_label = st.selectbox("Session", list(opts.keys()))
    session_id = opts[chosen_label]

    if st.button("Fetch Session", type="primary", use_container_width=True):
        try:
            with urlopen(f"{host}/api/summary/{session_id}", timeout=10) as r:
                st.session_state.meta = json.loads(r.read())
            with urlopen(f"{host}/api/summary/{session_id}/strokes", timeout=10) as r:
                st.session_state.strokes = json.loads(r.read())
        except URLError as e:
            st.error(f"Fetch failed: {e}")

# ── Guard ─────────────────────────────────────────────────────────────────────

if "strokes" not in st.session_state:
    st.info("Select a session in the sidebar and click **Fetch Session**.")
    st.stop()

meta = st.session_state.meta
strokes = st.session_state.strokes
if not strokes:
    st.warning("No stroke data for this session.")
    st.stop()

df = pd.DataFrame(strokes)
df["stroke_n"] = range(1, len(df) + 1)
df["elapsed_min"] = df["elapsed"] / 60
df["watts_roll5"] = df["watts"].rolling(5, min_periods=1).mean()

# ── Summary metrics ───────────────────────────────────────────────────────────

stats = meta.get("stats", {})
avg_hr_val = stats.get("avg_hr", "--")
avg_pace_val = stats.get("avg_pace", "--")
strive_val = meta.get("strive", {}).get("score")

metric_data = [
    ("Distance",  stats.get("distance", "--")),
    ("Time",      stats.get("time", "--")),
    ("Avg Pace",  f"{avg_pace_val}/500" if avg_pace_val != "--" else "--"),
    ("Avg Watts", stats.get("avg_watts", "--")),
    ("Avg HR",    f"{avg_hr_val} bpm" if avg_hr_val != "--" else "--"),
    ("Strive",    str(strive_val) if strive_val is not None else "--"),
]
for col, (label, val) in zip(st.columns(6), metric_data):
    col.metric(label, val)

st.divider()

# ── Power chart ───────────────────────────────────────────────────────────────

st.subheader("Power")
avg_w = df["watts"].dropna().mean()
fig = go.Figure([
    go.Scatter(
        x=df["elapsed_min"], y=df["watts"],
        mode="markers",
        marker=dict(size=4, color="rgba(99,110,250,0.25)"),
        name="Watts",
        customdata=df["stroke_n"],
        hovertemplate="Stroke %{customdata}<br>%{x:.1f} min — %{y:.0f} W<extra></extra>",
    ),
    go.Scatter(
        x=df["elapsed_min"], y=df["watts_roll5"],
        mode="lines",
        line=dict(color="rgba(99,110,250,1)", width=2),
        name="5-stroke avg",
        hoverinfo="skip",
    ),
])
if avg_w:
    fig.add_hline(y=avg_w, line_dash="dash", line_color="orange",
                  annotation_text=f"Avg {avg_w:.0f} W", annotation_position="top left")
fig.update_layout(xaxis_title="Elapsed (min)", yaxis_title="Watts",
                  height=350, margin=dict(t=20, b=40), showlegend=True)
st.plotly_chart(fig, use_container_width=True)

# ── Force chart ───────────────────────────────────────────────────────────────

if df[["peak_force_n", "avg_force_n"]].notna().any().any():
    st.subheader("Force")
    fig2 = go.Figure([
        go.Scatter(x=df["elapsed_min"], y=df["peak_force_n"], mode="lines",
                   name="Peak", line=dict(color="crimson"),
                   hovertemplate="%{y:.0f} N<extra>Peak</extra>"),
        go.Scatter(x=df["elapsed_min"], y=df["avg_force_n"], mode="lines",
                   name="Avg", line=dict(color="steelblue"),
                   hovertemplate="%{y:.0f} N<extra>Avg</extra>"),
    ])
    fig2.update_layout(xaxis_title="Elapsed (min)", yaxis_title="Force (N)",
                       height=300, margin=dict(t=20, b=40))
    st.plotly_chart(fig2, use_container_width=True)

# ── Pace chart ────────────────────────────────────────────────────────────────

if df["pace_sec"].notna().any():
    st.subheader("Pace")
    pace_labels = [
        f"{int(p)//60}:{int(p)%60:02d}/500m" if pd.notna(p) else "--"
        for p in df["pace_sec"]
    ]
    fig3 = go.Figure([
        go.Scatter(
            x=df["elapsed_min"], y=df["pace_sec"],
            mode="lines+markers", marker=dict(size=3),
            line=dict(color="mediumseagreen"),
            name="Pace",
            customdata=pace_labels,
            hovertemplate="%{customdata}<extra></extra>",
        ),
    ])
    fig3.update_yaxes(autorange="reversed", title="Pace (sec/500m)")
    fig3.update_layout(xaxis_title="Elapsed (min)", height=300, margin=dict(t=20, b=40))
    st.plotly_chart(fig3, use_container_width=True)

# ── HR chart ──────────────────────────────────────────────────────────────────

if "hr_bpm" in df.columns and df["hr_bpm"].notna().any():
    st.subheader("Heart Rate")
    fig4 = go.Figure([
        go.Scatter(x=df["elapsed_min"], y=df["hr_bpm"], mode="lines",
                   line=dict(color="tomato"), name="HR",
                   hovertemplate="%{y:.0f} bpm<extra></extra>"),
    ])
    fig4.update_layout(xaxis_title="Elapsed (min)", yaxis_title="HR (bpm)",
                       height=280, margin=dict(t=20, b=40))
    st.plotly_chart(fig4, use_container_width=True)
else:
    st.info("No heart-rate data for this session.")

# ── Drive / recovery ──────────────────────────────────────────────────────────

if df[["drive_time", "recovery"]].notna().all(axis=None):
    st.subheader("Drive / Recovery")
    fig5 = go.Figure([
        go.Bar(x=df["elapsed_min"], y=df["drive_time"],
               name="Drive", marker_color="steelblue",
               hovertemplate="%{y:.2f} s<extra>Drive</extra>"),
        go.Bar(x=df["elapsed_min"], y=df["recovery"],
               name="Recovery", marker_color="lightsteelblue",
               hovertemplate="%{y:.2f} s<extra>Recovery</extra>"),
    ])
    fig5.update_layout(barmode="stack", xaxis_title="Elapsed (min)",
                       yaxis_title="Seconds", height=280, margin=dict(t=20, b=40))
    st.plotly_chart(fig5, use_container_width=True)

# ── Force curve player ────────────────────────────────────────────────────────

st.divider()
st.subheader("Force Curve Player")

curves_df = df[df["force_curve"].notna()].reset_index(drop=True) if "force_curve" in df.columns else pd.DataFrame()

if curves_df.empty:
    st.info("No force curve data in this session. Sessions recorded after the CE06003D upgrade will include full curves.")
else:
    n_curves = len(curves_df)
    stroke_idx = st.slider("Stroke", min_value=1, max_value=n_curves, value=n_curves,
                           format="Stroke %d") - 1
    row = curves_df.iloc[stroke_idx]
    pts = row["force_curve"]  # list of floats in Newtons

    # Ratio-based colour: green ≤1.75, orange ≤2.10, red >2.10 (matches web UI)
    ratio = row.get("peak_avg_ratio")
    if pd.notna(ratio):
        if ratio <= 1.75:
            curve_color = "#2ECC71"
        elif ratio <= 2.10:
            curve_color = "#F39C12"
        else:
            curve_color = "#E74C3C"
    else:
        curve_color = "#636EFA"

    def _xs_for(r):
        dl = (r["drive_length"] / 100.0) if pd.notna(r.get("drive_length")) else None
        n  = len(r["force_curve"])
        if dl and dl > 0:
            return [dl * i / max(n - 1, 1) for i in range(n)], "Drive position (m)"
        return list(range(n)), "Sample index"

    xs, x_label = _xs_for(row)
    all_y = list(pts)

    # Ghost traces: up to 5 strokes before the selected one (faded)
    ghost_traces = []
    for g_offset in range(5, 0, -1):
        g_idx = stroke_idx - g_offset
        if g_idx < 0:
            continue
        g_row = curves_df.iloc[g_idx]
        g_xs, _ = _xs_for(g_row)
        opacity = 0.08 + g_offset * 0.06  # 0.14 → 0.38 from oldest to newest
        ghost_traces.append(go.Scatter(
            x=g_xs, y=g_row["force_curve"],
            mode="lines",
            line=dict(color=f"rgba(150,150,150,{opacity:.2f})", width=1),
            showlegend=False, hoverinfo="skip",
        ))
        all_y.extend(g_row["force_curve"])

    max_n = max(all_y) if all_y else 1
    avg_n = row.get("avg_force_n")
    peak_n = row.get("peak_force_n")

    fig6 = go.Figure(ghost_traces + [
        go.Scatter(
            x=xs, y=pts,
            mode="lines",
            fill="tozeroy",
            fillcolor=curve_color.replace("#", "rgba(").rstrip(")") + ",0.15)" if curve_color.startswith("#") else curve_color,
            line=dict(color=curve_color, width=2.5),
            name="Force",
            hovertemplate=f"{x_label.split()[0]} %{{x:.2f}} — %{{y:.0f}} N<extra></extra>",
        ),
    ])

    # fix fill colour: plotly needs rgba string
    fill_hex = curve_color.lstrip("#")
    r_int, g_int, b_int = int(fill_hex[0:2],16), int(fill_hex[2:4],16), int(fill_hex[4:6],16)
    fig6.data[-1].fillcolor = f"rgba({r_int},{g_int},{b_int},0.15)"

    if pd.notna(avg_n):
        fig6.add_hline(y=avg_n, line_dash="dash", line_color="steelblue",
                       annotation_text=f"Avg {avg_n:.0f} N", annotation_position="top left")
    if pd.notna(peak_n):
        fig6.add_hline(y=peak_n, line_dash="dot", line_color="crimson",
                       annotation_text=f"Peak {peak_n:.0f} N", annotation_position="top right")
    fig6.update_layout(
        xaxis_title=x_label,
        yaxis_title="Force (N)",
        yaxis=dict(range=[0, max_n * 1.15]),
        height=380, margin=dict(t=20, b=40),
        showlegend=False,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font_color="#c8c8d8",
        xaxis=dict(gridcolor="#1e2030"), yaxis_gridcolor="#1e2030",
    )
    st.plotly_chart(fig6, use_container_width=True)

    # Stroke metadata
    elapsed_str = f"{int(row['elapsed'])//60}:{int(row['elapsed'])%60:02d}" if pd.notna(row.get("elapsed")) else "--"
    drive_str   = f"{row['drive_time']:.2f} s" if pd.notna(row.get("drive_time")) else "--"
    rec_str     = f"{row['recovery']:.2f} s" if pd.notna(row.get("recovery")) else "--"
    dl_m        = (row["drive_length"] / 100.0) if pd.notna(row.get("drive_length")) else None
    dl_str      = f"{dl_m:.2f} m" if dl_m else "--"
    ratio_str   = f"{ratio:.2f}" if pd.notna(ratio) else "--"
    mcols = st.columns(6)
    for col, (label, val) in zip(mcols, [
        ("Stroke #", f"{stroke_idx + 1} / {n_curves}"),
        ("Elapsed",  elapsed_str),
        ("Drive",    drive_str),
        ("Recovery", rec_str),
        ("Length",   dl_str),
        ("Peak/Avg", ratio_str),
    ]):
        col.metric(label, val)
