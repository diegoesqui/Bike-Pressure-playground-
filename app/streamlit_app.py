"""Silca Tire-Pressure Playground."""
from __future__ import annotations
import csv, itertools, pathlib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.interpolate import LinearNDInterpolator

DATA_PATH = pathlib.Path(__file__).parent.parent / "data" / "silca_sweep.csv"
PSI_TO_BAR = 0.0689476

st.set_page_config(page_title="Calculadora de Presión Silca", page_icon="🚲", layout="wide")

_C = 49.0
_FRONT_SPLIT = 0.42
_REAR_SPLIT  = 0.58
_SURFACES: dict[str, float] = {
    "Asfalto nuevo":                  1.00,
    "Asfalto desgastado / fisuras":   0.93,
    "Asfalto deteriorado / gravilla": 0.86,
    "Grava cat. 1 (ligera)":          0.79,
    "Adoquín":                        0.72,
    "Grava cat. 2":                   0.65,
    "Grava cat. 3":                   0.58,
    "Grava cat. 4 (gruesa)":          0.50,
}
_TIRE_TYPE_FACTOR = 0.90
_SPEED_FACTOR     = 0.99
_TOTAL_KG       = list(range(70, 130, 5))
_TIRE_WIDTHS_MM = [30, 32, 35, 38, 40, 42, 45, 50]

def _compute_psi(total_kg, split, width_mm, sfactor):
    raw = _C * (total_kg * split) / width_mm * sfactor * _TIRE_TYPE_FACTOR * _SPEED_FACTOR
    return round(max(12.0, min(130.0, raw)), 1)

def _generate_synthetic_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rider_kg","bike_kg","luggage_kg","total_kg","tire_width_mm","surface",
                  "wheel","bike_type","tire_type","speed_kmh","front_psi","rear_psi",
                  "front_bar","rear_bar","data_source"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for total, width, (surf, sfac) in itertools.product(_TOTAL_KG, _TIRE_WIDTHS_MM, _SURFACES.items()):
            fp = _compute_psi(total, _FRONT_SPLIT, width, sfac)
            rp = _compute_psi(total, _REAR_SPLIT,  width, sfac)
            w.writerow({"rider_kg":total,"bike_kg":0,"luggage_kg":0,"total_kg":total,
                        "tire_width_mm":width,"surface":surf,"wheel":"700c",
                        "bike_type":"Road","tire_type":"mid-range-butyl","speed_kmh":14,
                        "front_psi":fp,"rear_psi":rp,
                        "front_bar":round(fp*PSI_TO_BAR,2),"rear_bar":round(rp*PSI_TO_BAR,2),
                        "data_source":"synthetic"})

@st.cache_data
def load_data(path):
    if not path.exists():
        _generate_synthetic_csv(path)
    df = pd.read_csv(path)
    df = df.dropna(subset=["front_psi","rear_psi"])
    if "total_kg" not in df.columns:
        df["total_kg"] = df["rider_kg"] + df["bike_kg"] + df["luggage_kg"]
    if "front_bar" not in df.columns or df["front_bar"].isna().all():
        df["front_bar"] = (df["front_psi"] * PSI_TO_BAR).round(2)
    if "rear_bar" not in df.columns or df["rear_bar"].isna().all():
        df["rear_bar"] = (df["rear_psi"] * PSI_TO_BAR).round(2)
    return df

def interpolate_pressure(df_surface, total_kg, tire_mm, col="front_bar"):
    pts  = df_surface[["total_kg","tire_width_mm"]].values
    vals = df_surface[col].values
    if len(pts) < 4:
        return None
    try:
        r = LinearNDInterpolator(pts, vals)([[total_kg, tire_mm]])[0]
        return round(float(r), 2) if not np.isnan(r) else None
    except Exception:
        return None

def main():
    st.title("🚲 Calculadora de Presión de Neumáticos")
    st.caption("Basado en el [Silca Pro Tire Pressure Calculator](https://silca.cc/pages/pro-tire-pressure-calculator) · 700C · Recreativo · Butilo · Distribución Carretera 48/52")

    df = load_data(DATA_PATH)
    if df.empty:
        st.error("Sin datos."); return

    if "data_source" in df.columns and (df["data_source"] == "synthetic").any():
        st.warning("**Datos sintéticos** — aproximación de la fórmula Silca. Ejecuta `python -m scrape.sweep` para datos reales.", icon="⚠️")

    surfaces = sorted(df["surface"].unique().tolist())
    widths   = sorted(df["tire_width_mm"].unique().tolist())
    palette  = px.colors.qualitative.Set2

    with st.sidebar:
        st.header("Parámetros")
        rider_kg   = st.slider("Peso ciclista (kg)",    60, 90, 75, step=5)
        bike_kg    = st.slider("Peso bicicleta (kg)",   10, 25, 12, step=1)
        luggage_kg = st.slider("Equipaje (kg)",          0, 10,  0, step=1)
        total_kg   = rider_kg + bike_kg + luggage_kg
        st.metric("Peso total", f"{total_kg} kg")
        st.divider()
        tire_mm = st.select_slider("Ancho del neumático (mm)", options=widths,
                                   value=35 if 35 in widths else widths[len(widths)//2])
        surface = st.radio("Superficie", options=surfaces, index=0)

    df_surf   = df[df["surface"] == surface]
    cur_front = interpolate_pressure(df_surf, total_kg, tire_mm, "front_bar")
    cur_rear  = interpolate_pressure(df_surf, total_kg, tire_mm, "rear_bar")

    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Presión delantera", f"{cur_front} bar" if cur_front else "—")
    m2.metric("Presión trasera",   f"{cur_rear} bar"  if cur_rear  else "—")
    m3.metric("Superficie", surface)
    m4.metric("Ancho", f"{tire_mm} mm")
    st.divider()

    tab1,tab2,tab3,tab4 = st.tabs(["📈 Presión vs Peso","📏 Presión vs Ancho","🌍 Comparativa superficies","🔥 Mapa de calor"])

    with tab1:
        st.subheader("Presión en función del peso total")
        st.caption(f"Ancho fijo: {tire_mm} mm")
        df_w = df[df["tire_width_mm"]==tire_mm].copy()
        fig = go.Figure()
        for i,surf in enumerate(surfaces):
            sub = df_w[df_w["surface"]==surf].sort_values("total_kg")
            if sub.empty: continue
            c = palette[i%len(palette)]
            fig.add_trace(go.Scatter(x=sub["total_kg"],y=sub["front_bar"],mode="lines+markers",
                name=f"{surf} — Del.",line={"color":c,"dash":"solid"},legendgroup=surf))
            fig.add_trace(go.Scatter(x=sub["total_kg"],y=sub["rear_bar"],mode="lines+markers",
                name=f"{surf} — Tras.",line={"color":c,"dash":"dot"},legendgroup=surf))
        if cur_front:
            fig.add_vline(x=total_kg,line_dash="dash",line_color="red",
                          annotation_text=f"{total_kg} kg",annotation_position="top right")
            fig.add_trace(go.Scatter(x=[total_kg],y=[cur_front],mode="markers",name="Tu punto (Del.)",
                marker={"size":14,"color":"red","symbol":"star"}))
        if cur_rear:
            fig.add_trace(go.Scatter(x=[total_kg],y=[cur_rear],mode="markers",name="Tu punto (Tras.)",
                marker={"size":14,"color":"darkred","symbol":"star-open"}))
        fig.update_layout(xaxis_title="Peso total (kg)",yaxis_title="Presión (bar)",
                          legend_title="Superficie — Eje",height=480)
        st.plotly_chart(fig,use_container_width=True)

    with tab2:
        st.subheader("Presión en función del ancho")
        st.caption(f"Peso total: {total_kg} kg")
        avail = sorted(df["total_kg"].unique())
        nearest = min(avail, key=lambda x: abs(x-total_kg))
        df_tw = df[df["total_kg"]==nearest].copy()
        if nearest != total_kg:
            st.caption(f"ℹ Peso de grid más cercano: {nearest} kg")
        fig2 = go.Figure()
        for i,surf in enumerate(surfaces):
            sub = df_tw[df_tw["surface"]==surf].sort_values("tire_width_mm")
            if sub.empty: continue
            c = palette[i%len(palette)]
            fig2.add_trace(go.Scatter(x=sub["tire_width_mm"],y=sub["front_bar"],mode="lines+markers",
                name=f"{surf} — Del.",line={"color":c,"dash":"solid"},legendgroup=surf))
            fig2.add_trace(go.Scatter(x=sub["tire_width_mm"],y=sub["rear_bar"],mode="lines+markers",
                name=f"{surf} — Tras.",line={"color":c,"dash":"dot"},legendgroup=surf))
        fig2.add_vline(x=tire_mm,line_dash="dash",line_color="red",
                       annotation_text=f"{tire_mm} mm",annotation_position="top right")
        if cur_front:
            fig2.add_trace(go.Scatter(x=[tire_mm],y=[cur_front],mode="markers",name="Tu punto (Del.)",
                marker={"size":14,"color":"red","symbol":"star"}))
        if cur_rear:
            fig2.add_trace(go.Scatter(x=[tire_mm],y=[cur_rear],mode="markers",name="Tu punto (Tras.)",
                marker={"size":14,"color":"darkred","symbol":"star-open"}))
        fig2.update_layout(xaxis_title="Ancho (mm)",yaxis_title="Presión (bar)",
                           legend_title="Superficie — Eje",height=480)
        st.plotly_chart(fig2,use_container_width=True)

    with tab3:
        st.subheader("Comparativa de superficies")
        st.caption(f"Total: {total_kg} kg, ancho: {tire_mm} mm")
        rows = []
        for surf in surfaces:
            fp = interpolate_pressure(df[df["surface"]==surf],total_kg,tire_mm,"front_bar")
            rp = interpolate_pressure(df[df["surface"]==surf],total_kg,tire_mm,"rear_bar")
            if fp: rows.append({"Superficie":surf,"Eje":"Delantera","Presión (bar)":fp})
            if rp: rows.append({"Superficie":surf,"Eje":"Trasera",  "Presión (bar)":rp})
        if rows:
            df_bar = pd.DataFrame(rows)
            fig3 = px.bar(df_bar,x="Superficie",y="Presión (bar)",color="Eje",barmode="group",
                          color_discrete_map={"Delantera":"#1f77b4","Trasera":"#ff7f0e"},height=400)
            idx = surfaces.index(surface)
            fig3.update_layout(shapes=[dict(type="rect",xref="x",yref="paper",
                x0=idx-0.45,x1=idx+0.45,y0=0,y1=1,fillcolor="yellow",opacity=0.15,line_width=0)])
            st.plotly_chart(fig3,use_container_width=True)
        else:
            st.info("Sin datos interpolados.")

    with tab4:
        st.subheader(f"Mapa de calor — {surface}")
        axle = st.radio("Eje", ["Delantera","Trasera"], horizontal=True, key="hm")
        col  = "front_bar" if axle=="Delantera" else "rear_bar"
        df_h = df[df["surface"]==surface].copy()
        piv  = df_h.groupby(["total_kg","tire_width_mm"])[col].mean().reset_index()
        pw   = piv.pivot(index="total_kg",columns="tire_width_mm",values=col)
        fig4 = go.Figure(go.Heatmap(z=pw.values,x=[str(c) for c in pw.columns],
            y=[str(r) for r in pw.index],colorscale="RdYlGn_r",
            colorbar={"title":"bar"},hoverongaps=False))
        nw  = min(pw.index,   key=lambda x: abs(x-total_kg))
        nmm = min(pw.columns, key=lambda x: abs(x-tire_mm))
        fig4.add_trace(go.Scatter(x=[str(nmm)],y=[str(nw)],mode="markers",
            marker={"size":18,"color":"white","symbol":"cross","line":{"width":3,"color":"black"}},
            name="Tu config",showlegend=True))
        fig4.update_layout(xaxis_title="Ancho (mm)",yaxis_title="Peso total (kg)",height=500)
        st.plotly_chart(fig4,use_container_width=True)

if __name__ == "__main__":
    main()
