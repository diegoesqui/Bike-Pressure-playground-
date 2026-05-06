"""
Silca Tire-Pressure Playground – Streamlit app.

Loads data/silca_sweep.csv and lets you explore how pressure varies with
rider weight, bike weight, luggage, tire width, and surface type.

Run:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.interpolate import LinearNDInterpolator

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_PATH = pathlib.Path(__file__).parent.parent / "data" / "silca_sweep.csv"

st.set_page_config(
    page_title="Silca Tire-Pressure Playground",
    page_icon="🚲",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_data(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.dropna(subset=["front_psi", "rear_psi"])
    df["total_kg"] = df["rider_kg"] + df["bike_kg"] + df["luggage_kg"]
    return df


def check_data() -> pd.DataFrame | None:
    if not DATA_PATH.exists():
        st.error(
            f"**Data file not found:** `{DATA_PATH}`\n\n"
            "Run the sweep first:\n```\npython -m scrape.sweep\n```"
        )
        return None
    df = load_data(DATA_PATH)
    if df.empty:
        st.error("CSV is empty or has no valid pressure readings. Re-run the sweep.")
        return None
    return df


# ---------------------------------------------------------------------------
# Interpolation helper
# ---------------------------------------------------------------------------

def interpolate_pressure(
    df_surface: pd.DataFrame,
    total_kg: float,
    tire_mm: float,
    axis: str = "front_psi",
) -> float | None:
    pts = df_surface[["total_kg", "tire_width_mm"]].values
    vals = df_surface[axis].values
    if len(pts) < 4:
        return None
    try:
        interp = LinearNDInterpolator(pts, vals)
        result = interp([[total_kg, tire_mm]])[0]
        return float(result) if not np.isnan(result) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def to_display(psi: float | None, use_bar: bool) -> float | None:
    if psi is None:
        return None
    return round(psi * 0.0689476, 2) if use_bar else round(psi, 1)


def unit_label(use_bar: bool) -> str:
    return "bar" if use_bar else "psi"


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("🚲 Silca Tire-Pressure Playground")
    st.caption(
        "Interactive explorer based on the "
        "[Silca Pro Tire Pressure Calculator](https://silca.cc/pages/pro-tire-pressure-calculator)"
    )

    df = check_data()
    if df is None:
        return

    if "data_source" in df.columns and (df["data_source"] == "synthetic").any():
        st.warning(
            "**Using synthetic data** (physics-based approximation of the Silca formula). "
            "Run `python -m scrape.sweep` from your machine to replace with real Silca outputs.",
            icon="⚠️",
        )

    surfaces = sorted(df["surface"].unique().tolist())
    widths = sorted(df["tire_width_mm"].unique().tolist())

    # -------------------------------------------------------------------
    # Sidebar – controls
    # -------------------------------------------------------------------
    with st.sidebar:
        st.header("Parameters")

        rider_kg = st.slider("Rider weight (kg)", 60, 90, 75, step=5)
        bike_kg = st.slider("Bike weight (kg)", 10, 25, 12, step=1)
        luggage_kg = st.slider("Luggage (kg)", 0, 10, 0, step=1)
        total_kg = rider_kg + bike_kg + luggage_kg
        st.metric("Total system weight", f"{total_kg} kg")

        st.divider()

        tire_mm = st.select_slider(
            "Tire width (mm)",
            options=widths,
            value=widths[widths.index(35)] if 35 in widths else widths[len(widths) // 2],
        )
        surface = st.radio("Surface", options=surfaces, index=0)

        st.divider()
        use_bar = st.toggle("Show in bar (instead of PSI)", value=False)

    ul = unit_label(use_bar)

    # Current-point pressures (interpolated)
    df_surf = df[df["surface"] == surface]
    cur_front = to_display(
        interpolate_pressure(df_surf, total_kg, tire_mm, "front_psi"), use_bar
    )
    cur_rear = to_display(
        interpolate_pressure(df_surf, total_kg, tire_mm, "rear_psi"), use_bar
    )

    # Quick-look metrics at the top
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Front pressure", f"{cur_front} {ul}" if cur_front else "—")
    m2.metric("Rear pressure", f"{cur_rear} {ul}" if cur_rear else "—")
    m3.metric("Surface", surface)
    m4.metric("Tire width", f"{tire_mm} mm")

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Pressure vs Weight",
        "📏 Pressure vs Tire Width",
        "🌍 Surface comparison",
        "🔥 Heatmap",
    ])

    # -------------------------------------------------------------------
    # Tab 1: Pressure vs total system weight
    # -------------------------------------------------------------------
    with tab1:
        st.subheader("Pressure as a function of total system weight")
        st.caption(f"Tire width fixed at {tire_mm} mm — one curve per surface")

        df_w = df[df["tire_width_mm"] == tire_mm].copy()
        if df_w.empty:
            st.info("No data for this tire width. Adjust the slider.")
        else:
            if use_bar:
                df_w["front_disp"] = df_w["front_psi"] * 0.0689476
                df_w["rear_disp"] = df_w["rear_psi"] * 0.0689476
            else:
                df_w["front_disp"] = df_w["front_psi"]
                df_w["rear_disp"] = df_w["rear_psi"]

            fig = go.Figure()
            palette = px.colors.qualitative.Set2
            for i, surf in enumerate(surfaces):
                sub = df_w[df_w["surface"] == surf].sort_values("total_kg")
                if sub.empty:
                    continue
                color = palette[i % len(palette)]
                fig.add_trace(go.Scatter(
                    x=sub["total_kg"], y=sub["front_disp"],
                    mode="lines+markers", name=f"{surf} — Front",
                    line={"color": color, "dash": "solid"},
                    legendgroup=surf,
                ))
                fig.add_trace(go.Scatter(
                    x=sub["total_kg"], y=sub["rear_disp"],
                    mode="lines+markers", name=f"{surf} — Rear",
                    line={"color": color, "dash": "dot"},
                    legendgroup=surf,
                ))

            # Current-point markers
            if cur_front is not None:
                fig.add_vline(x=total_kg, line_dash="dash", line_color="red",
                              annotation_text=f"{total_kg} kg", annotation_position="top right")
                fig.add_trace(go.Scatter(
                    x=[total_kg], y=[cur_front],
                    mode="markers", name="Your point (Front)",
                    marker={"size": 14, "color": "red", "symbol": "star"},
                    showlegend=True,
                ))
            if cur_rear is not None:
                fig.add_trace(go.Scatter(
                    x=[total_kg], y=[cur_rear],
                    mode="markers", name="Your point (Rear)",
                    marker={"size": 14, "color": "darkred", "symbol": "star-open"},
                    showlegend=True,
                ))

            fig.update_layout(
                xaxis_title="Total system weight (kg)",
                yaxis_title=f"Pressure ({ul})",
                legend_title="Surface — Axle",
                height=480,
            )
            st.plotly_chart(fig, use_container_width=True)

    # -------------------------------------------------------------------
    # Tab 2: Pressure vs tire width
    # -------------------------------------------------------------------
    with tab2:
        st.subheader("Pressure as a function of tire width")
        st.caption(f"Total weight fixed at {total_kg} kg — one curve per surface")

        # Find nearest grid total_kg
        available_totals = sorted(df["total_kg"].unique())
        nearest_total = min(available_totals, key=lambda x: abs(x - total_kg))

        df_tw = df[df["total_kg"] == nearest_total].copy()
        if df_tw.empty:
            st.info("No data at this total weight. Adjust the sliders.")
        else:
            if use_bar:
                df_tw["front_disp"] = df_tw["front_psi"] * 0.0689476
                df_tw["rear_disp"] = df_tw["rear_psi"] * 0.0689476
            else:
                df_tw["front_disp"] = df_tw["front_psi"]
                df_tw["rear_disp"] = df_tw["rear_psi"]

            if nearest_total != total_kg:
                st.caption(f"ℹ Nearest grid weight used: {nearest_total} kg (selected: {total_kg} kg)")

            fig2 = go.Figure()
            for i, surf in enumerate(surfaces):
                sub = df_tw[df_tw["surface"] == surf].sort_values("tire_width_mm")
                if sub.empty:
                    continue
                color = palette[i % len(palette)]
                fig2.add_trace(go.Scatter(
                    x=sub["tire_width_mm"], y=sub["front_disp"],
                    mode="lines+markers", name=f"{surf} — Front",
                    line={"color": color, "dash": "solid"}, legendgroup=surf,
                ))
                fig2.add_trace(go.Scatter(
                    x=sub["tire_width_mm"], y=sub["rear_disp"],
                    mode="lines+markers", name=f"{surf} — Rear",
                    line={"color": color, "dash": "dot"}, legendgroup=surf,
                ))

            fig2.add_vline(x=tire_mm, line_dash="dash", line_color="red",
                           annotation_text=f"{tire_mm} mm", annotation_position="top right")
            if cur_front is not None:
                fig2.add_trace(go.Scatter(
                    x=[tire_mm], y=[cur_front],
                    mode="markers", name="Your point (Front)",
                    marker={"size": 14, "color": "red", "symbol": "star"},
                ))
            if cur_rear is not None:
                fig2.add_trace(go.Scatter(
                    x=[tire_mm], y=[cur_rear],
                    mode="markers", name="Your point (Rear)",
                    marker={"size": 14, "color": "darkred", "symbol": "star-open"},
                ))

            fig2.update_layout(
                xaxis_title="Tire width (mm)",
                yaxis_title=f"Pressure ({ul})",
                legend_title="Surface — Axle",
                height=480,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # -------------------------------------------------------------------
    # Tab 3: Surface comparison (bar chart)
    # -------------------------------------------------------------------
    with tab3:
        st.subheader("Surface comparison at your current settings")
        st.caption(
            f"Total: {total_kg} kg, tire: {tire_mm} mm — front vs rear across all surfaces"
        )

        rows = []
        for surf in surfaces:
            df_s = df[df["surface"] == surf]
            fp = to_display(interpolate_pressure(df_s, total_kg, tire_mm, "front_psi"), use_bar)
            rp = to_display(interpolate_pressure(df_s, total_kg, tire_mm, "rear_psi"), use_bar)
            if fp is not None:
                rows.append({"Surface": surf, "Axle": "Front", f"Pressure ({ul})": fp})
            if rp is not None:
                rows.append({"Surface": surf, "Axle": "Rear", f"Pressure ({ul})": rp})

        if rows:
            df_bar = pd.DataFrame(rows)
            fig3 = px.bar(
                df_bar, x="Surface", y=f"Pressure ({ul})", color="Axle",
                barmode="group", color_discrete_map={"Front": "#1f77b4", "Rear": "#ff7f0e"},
                height=400,
            )
            # Highlight the selected surface
            shapes = [
                dict(
                    type="rect",
                    xref="x", yref="paper",
                    x0=surfaces.index(surface) - 0.45,
                    x1=surfaces.index(surface) + 0.45,
                    y0=0, y1=1,
                    fillcolor="yellow", opacity=0.15, line_width=0,
                )
            ]
            fig3.update_layout(shapes=shapes)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No interpolated data available for current settings.")

    # -------------------------------------------------------------------
    # Tab 4: Heatmap – pressure vs (weight, width)
    # -------------------------------------------------------------------
    with tab4:
        st.subheader(f"Pressure heatmap — surface: {surface}")
        st.caption("Axis: total system weight (rows) × tire width (columns)")

        axle_choice = st.radio("Axle", ["Front", "Rear"], horizontal=True, key="heatmap_axle")
        psi_col = "front_psi" if axle_choice == "Front" else "rear_psi"

        df_h = df[df["surface"] == surface].copy()
        if df_h.empty:
            st.info("No data for this surface.")
        else:
            piv = df_h.groupby(["total_kg", "tire_width_mm"])[psi_col].mean().reset_index()
            piv_wide = piv.pivot(index="total_kg", columns="tire_width_mm", values=psi_col)
            if use_bar:
                piv_wide = piv_wide * 0.0689476

            fig4 = go.Figure(go.Heatmap(
                z=piv_wide.values,
                x=[str(c) for c in piv_wide.columns],
                y=[str(r) for r in piv_wide.index],
                colorscale="RdYlGn_r",
                colorbar={"title": f"Pressure ({ul})"},
                hoverongaps=False,
            ))

            # Cross-hair for current settings
            nearest_w = min(piv_wide.index, key=lambda x: abs(x - total_kg))
            nearest_mm = min(piv_wide.columns, key=lambda x: abs(x - tire_mm))
            fig4.add_trace(go.Scatter(
                x=[str(nearest_mm)], y=[str(nearest_w)],
                mode="markers",
                marker={"size": 18, "color": "white", "symbol": "cross", "line": {"width": 3, "color": "black"}},
                name="Your settings",
                showlegend=True,
            ))

            fig4.update_layout(
                xaxis_title="Tire width (mm)",
                yaxis_title="Total system weight (kg)",
                height=500,
            )
            st.plotly_chart(fig4, use_container_width=True)


if __name__ == "__main__":
    main()
