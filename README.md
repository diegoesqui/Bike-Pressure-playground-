# Silca Tire-Pressure Playground

Interactive explorer for the [Silca Pro Tire Pressure Calculator](https://silca.cc/pages/pro-tire-pressure-calculator).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

The app auto-generates a synthetic dataset on first run (no CSV needed).

## Deploy to Streamlit Cloud

1. Fork / push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Select repo, branch `main`, file `app/streamlit_app.py`
4. Deploy

## Scrape real Silca data (optional)

```bash
pip install playwright
playwright install chromium
python -m scrape.inspect   # reconnaissance
python -m scrape.sweep     # full grid sweep
```

Replace `data/silca_sweep.csv` with the real output to upgrade from the synthetic approximation.

## Parameters

| Parameter     | Range           | Notes                  |
|---------------|-----------------|------------------------|
| Rider weight  | 60–90 kg, step 5 |                        |
| Bike weight   | 10–25 kg, step 1 | Includes e-bikes       |
| Luggage       | 0–10 kg, step 1  | Pannier / rack load    |
| Tire width    | 23–50 mm        | 12 values              |
| Surface       | 5 types          | Smooth → Gravel/Dirt  |
