# Silca Tire-Pressure Playground

Interactive explorer for the [Silca Pro Tire Pressure Calculator](https://silca.cc/pages/pro-tire-pressure-calculator).

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## 1 – Scrape (one-time)

```bash
# Reconnaissance – dumps selectors and network log
python -m scrape.inspect

# Full parameter sweep (saves data/silca_sweep.csv)
python -m scrape.sweep
```

A committed snapshot of `data/silca_sweep.csv` is included so you can skip the
sweep and go straight to the playground.

## 2 – Playground

```bash
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 and move the sliders.

## Parameters swept

| Parameter     | Range              | Notes                       |
|---------------|--------------------|-----------------------------|
| Rider weight  | 60–90 kg, step 5   |                             |
| Bike weight   | 10–25 kg, step 5   | Includes e-bikes            |
| Luggage       | 0–10 kg, step 2    | Pannier / rack load         |
| Tire width    | 23–50 mm           | 12 values                   |
| Surface       | all dropdown values | ~5 Silca surface categories |

Fixed defaults: 700C wheel, Road bike, Tubeless, 30 km/h.
