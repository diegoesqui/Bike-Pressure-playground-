"""
Silca Tire-Pressure Playground – Streamlit app.

Auto-generates a synthetic dataset on first run if data/silca_sweep.csv is missing.
All pressures in bar. Weights in kg.

Run:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import csv
import itertools
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
PSI_TO_BAR = 0.0689476

st.set_page_config(
    page_title="Silca Tire-Pressure Playground",
    page_icon="🚲",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Synthetic data generation (runs only if CSV is missing)
# ---------------------------------------------------------------------------
_C = 49.0
_FRONT_SPLIT = 0.42
_REAR_SPLIT = 0.58
_SURFACES: dict[str, float] = {
    "Asfalto liso": 1.00,
    "Asfalto mixto": 0.90,
    "Gravilla compacta": 0.81,
    "Grava ligera": 0.72,
    "Grava / tierra": 0.63,
}
_TIRE_TYPE_FACTOR = 0.90
_SPEED_FACTOR = 0.99
_RIDER_KG = list(range(60, 95, 5))
_BIKE_KG = [10, 15, 20, 25]
_LUGGAGE_KG = [0, 2, 4, 6, 8, 10]
_TIRE_WIDTHS_MM = [23, 25, 28, 30, 32, 35, 38, 40, 42, 45, 47, 50]


def _compute_psi(total_kg: float, split: float, width_mm: int, sfactor: float) -> float:
    raw = _C * (total_kg * split) / width_mm * sfactor * _TIRE_TYPE_FACTOR * _SPEED_FACTOR
    return round(max(12.0, min(130.0, raw)), 1)


def _generate_synthetic_csv(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rider_kg", "bike_kg", "luggage_kg", "total_kg",
        "tire_width_mm", "surface", "wheel", "bike_type", "tire_type", "speed_kmh",
        "front_psi", "rear_psi", "data_source",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rider, bike, luggage, width, (surf, sfac) in itertools.product(
            _RIDER_KG, _BIKE_KG, _LUGGAGE_KG, _TIRE_WIDTHS_MM, _SURFACES.items()
        ):
            total = rider + bike + luggage
            w.writerow({
                "rider_kg": rider, "bike_kg": bike, "luggage_kg": luggage,
                "total_kg": total, "tire_width_mm": width, "surface": surf,
                "wheel": "700c", "bike_type": "Road", "tire_type": "Tubeless",
                "speed_kmh": 30.0,
                "front_psi": _compute_psi(total, _FRONT_SPLIT, width, sfac),
                "rear_psi": _compute_psi(total, _REAR_SPLIT, width, sfac),
                "data_source": "synthetic",
            })


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_data(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        _generate_synthetic_csv(path)
    df = pd.read_csv(path)
    df = df.dropna(subset=["front_psi", "rear_psi"])
    df["total_kg"] = df["rider_kg"] + df["bike_kg"] + df["luggage_kg"]
    df["front_bar"] = (df["front_psi"] * PSI_TO_BAR).round(2)
    df["rear_bar"] = (df["rear_psi"] * PSI_TO_BAR).round(2)
    return df


def check_data() -> pd.DataFrame | None:
    df = load_data(DATA_PATH)
    if df.empty:
        st.error("CSV vacío o sin lecturas válidas.")
        return None
    return df


# ---------------------------------------------------------------------------
# Interpolation helper
# ---------------------------------------------------------------------------

def interpolate_pressure(
    df_surface: pd.DataFrame,
    total_kg: float,
    tire_mm: float,
    col: str = "front_bar",
) -> float | None:
    pts = df_surface[["total_kg", "tire_width_mm"]].values
    vals = df_surface[col].values
    if len(pts) < 4:
        return None
    try:
        interp = LinearNDInterpolator(pts, vals)
        result = interp([[total_kg, tire_mm]])[0]
        return round(float(result), 2) if not np.isnan(result) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("🚲 Calculadora de presión de neumáticos")
    st.caption(
        "Explorador interactivo basado en el "
        "[Silca Pro Tire Pressure Calculator](https://silca.cc/pages/pro-tire-pressure-calculator)"
    )

    df = check_data()
    if df is None:
        return

    if "data_source" in df.columns and (df["data_source"] == "synthetic").any():
        st.warning(
            "**Datos sintéticos** (aproximación física de la fórmula Silca). "
            "Ejecuta `python3.9 -m scrape.sweep` desde tu máquina para obtener datos reales.",
            icon="⚠️",
        )

    surfaces = sorted(df["surface"].unique().tolist())
    widths = sorted(df["tire_width_mm"].unique().tolist())
    palette = px.colors.qualitative.Set2

    # -------------------------------------------------------------------
    # Sidebar
    # -------------------------------------------------------------------
    with st.sidebar:
        st.header("Parámetros")

        rider_kg = st.slider("Peso ciclista (kg)", 60, 90, 75, step=5)
        bike_kg = st.slider("Peso bicicleta (kg)", 10, 25, 12, step=1)
        luggage_kg = st.slider("Equipaje (kg)", 0, 10, 0, step=1)
        total_kg = rider_kg + bike_kg + luggage_kg
        st.metric("Peso total del sistema", f"{total_kg} kg")

        st.divider()

        tire_mm = st.select_slider(
            "Anchura del neumático (mm)",
            options=widths,
            value=widths[widths.index(35)] if 35 in widths else widths[len(widths) // 2],
        )
        surface = st.radio("Superficie", options=surfaces, index=0)

    # Current-point pressures
    df_surf = df[df["surface"] == surface]
    cur_front = interpolate_pressure(df_surf, total_kg, tire_mm, "front_bar")
    cur_rear = interpolate_pressure(df_surf, total_kg, tire_mm, "rear_bar")

    # Top metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Presión delantera", f"{cur_front} bar" if cur_front else "—")
    m2.metric("Presión trasera", f"{cur_rear} bar" if cur_rear else "—")
    m3.metric("Superficie", surface)
    m4.metric("Ancho neumático", f"{tire_mm} mm")

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Presión vs Peso",
        "📏 Presión vs Ancho",
        "🌍 Comparativa superficies",
        "🔥 Mapa de calor",
    ])

    # Tab 1
    with tab1:
        st.subheader("Presión en función del peso total del sistema")
        st.caption(f"Ancho de neumático fijo en {tire_mm} mm — una curva por superficie")
        df_w = df[df["tire_width_mm"] == tire_mm].copy()
        if df_w.empty:
            st.info("Sin datos para este ancho.")
        else:
            fig = go.Figure()
            for i, surf in enumerate(surfaces):
                sub = df_w[df_w["surface"] == surf].sort_values("total_kg")
                if sub.empty:
                    continue
                color = palette[i % len(palette)]
                fig.add_trace(go.Scatter(
                    x=sub["total_kg"], y=sub["front_bar"],
                    mode="lines+markers", name=f"{surf} — Delantera",
                    line={"color": color, "dash": "solid"}, legendgroup=surf,
                ))
                fig.add_trace(go.Scatter(
                    x=sub["total_kg"], y=sub["rear_bar"],
                    mode="lines+markers", name=f"{surf} — Trasera",
                    line={"color": color, "dash": "dot"}, legendgroup=surf,
                ))
            if cur_front is not None:
                fig.add_vline(x=total_kg, line_dash="dash", line_color="red",
                              annotation_text=f"{total_kg} kg", annotation_position="top right")
                fig.add_trace(go.Scatter(
                    x=[total_kg], y=[cur_front], mode="markers",
                    name="Tu punto (Del.)",
                    marker={"size": 14, "color": "red", "symbol": "star"},
                ))
            if cur_rear is not None:
                fig.add_trace(go.Scatter(
                    x=[total_kg], y=[cur_rear], mode="markers",
                    name="Tu punto (Tras.)",
                    marker={"size": 14, "color": "darkred", "symbol": "star-open"},
                ))
            fig.update_layout(
                xaxis_title="Peso total del sistema (kg)",
                yaxis_title="Presión (bar)",
                legend_title="Superficie — Eje",
                height=480,
            )
            st.plotly_chart(fig, use_container_width=True)

    # Tab 2
    with tab2:
        st.subheader("Presión en función del ancho del neumático")
        st.caption(f"Peso total fijo en {total_kg} kg — una curva por superficie")
        available_totals = sorted(df["total_kg"].unique())
        nearest_total = min(available_totals, key=lambda x: abs(x - total_kg))
        df_tw = df[df["total_kg"] == nearest_total].copy()
        if df_tw.empty:
            st.info("Sin datos para este peso total.")
        else:
            if nearest_total != total_kg:
                st.caption(f"ℹ Peso de grid más cercano: {nearest_total} kg (seleccionado: {total_kg} kg)")
            fig2 = go.Figure()
            for i, surf in enumerate(surfaces):
                sub = df_tw[df_tw["surface"] == surf].sort_values("tire_width_mm")
                if sub.empty:
                    continue
                color = palette[i % len(palette)]
                fig2.add_trace(go.Scatter(
                    x=sub["tire_width_mm"], y=sub["front_bar"],
                    mode="lines+markers", name=f"{surf} — Delantera",
                    line={"color": color, "dash": "solid"}, legendgroup=surf,
                ))
                fig2.add_trace(go.Scatter(
                    x=sub["tire_width_mm"], y=sub["rear_bar"],
                    mode="lines+markers", name=f"{surf} — Trasera",
                    line={"color": color, "dash": "dot"}, legendgroup=surf,
                ))
            fig2.add_vline(x=tire_mm, line_dash="dash", line_color="red",
                           annotation_text=f"{tire_mm} mm", annotation_position="top right")
            if cur_front is not None:
                fig2.add_trace(go.Scatter(
                    x=[tire_mm], y=[cur_front], mode="markers",
                    name="Tu punto (Del.)",
                    marker={"size": 14, "color": "red", "symbol": "star"},
                ))
            if cur_rear is not None:
                fig2.add_trace(go.Scatter(
                    x=[tire_mm], y=[cur_rear], mode="markers",
                    name="Tu punto (Tras.)",
                    marker={"size": 14, "color": "darkred", "symbol": "star-open"},
                ))
            fig2.update_layout(
                xaxis_title="Ancho del neumático (mm)",
                yaxis_title="Presión (bar)",
                legend_title="Superficie — Eje",
                height=480,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Tab 3
    with tab3:
        st.subheader("Comparativa de superficies en tu configuración actual")
        st.caption(f"Total: {total_kg} kg, neumático: {tire_mm} mm")
        rows = []
        for surf in surfaces:
            df_s = df[df["surface"] == surf]
            fp = interpolate_pressure(df_s, total_kg, tire_mm, "front_bar")
            rp = interpolate_pressure(df_s, total_kg, tire_mm, "rear_bar")
            if fp is not None:
                rows.append({"Superficie": surf, "Eje": "Delantera", "Presión (bar)": fp})
            if rp is not None:
                rows.append({"Superficie": surf, "Eje": "Trasera", "Presión (bar)": rp})
        if rows:
            df_bar = pd.DataFrame(rows)
            fig3 = px.bar(
                df_bar, x="Superficie", y="Presión (bar)", color="Eje",
                barmode="group",
                color_discrete_map={"Delantera": "#1f77b4", "Trasera": "#ff7f0e"},
                height=400,
            )
            shapes = [dict(
                type="rect", xref="x", yref="paper",
                x0=surfaces.index(surface) - 0.45, x1=surfaces.index(surface) + 0.45,
                y0=0, y1=1, fillcolor="yellow", opacity=0.15, line_width=0,
            )]
            fig3.update_layout(shapes=shapes)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sin datos interpolados para la configuración actual.")

    # Tab 4
    with tab4:
        st.subheader(f"Mapa de calor — superficie: {surface}")
        st.caption("Ejes: peso total del sistema (filas) × ancho del neumático (columnas)")
        axle_choice = st.radio("Eje", ["Delantera", "Trasera"], horizontal=True, key="heatmap_axle")
        bar_col = "front_bar" if axle_choice == "Delantera" else "rear_bar"
        df_h = df[df["surface"] == surface].copy()
        if df_h.empty:
            st.info("Sin datos para esta superficie.")
        else:
            piv = df_h.groupby(["total_kg", "tire_width_mm"])[bar_col].mean().reset_index()
            piv_wide = piv.pivot(index="total_kg", columns="tire_width_mm", values=bar_col)
            fig4 = go.Figure(go.Heatmap(
                z=piv_wide.values,
                x=[str(c) for c in piv_wide.columns],
                y=[str(r) for r in piv_wide.index],
                colorscale="RdYlGn_r",
                colorbar={"title": "Presión (bar)"},
                hoverongaps=False,
            ))
            nearest_w = min(piv_wide.index, key=lambda x: abs(x - total_kg))
            nearest_mm = min(piv_wide.columns, key=lambda x: abs(x - tire_mm))
            fig4.add_trace(go.Scatter(
                x=[str(nearest_mm)], y=[str(nearest_w)],
                mode="markers",
                marker={"size": 18, "color": "white", "symbol": "cross",
                        "line": {"width": 3, "color": "black"}},
                name="Tu configuración", showlegend=True,
            ))
            fig4.update_layout(
                xaxis_title="Ancho del neumático (mm)",
                yaxis_title="Peso total del sistema (kg)",
                height=500,
            )
            st.plotly_chart(fig4, use_container_width=True)


if __name__ == "__main__":
    main()
