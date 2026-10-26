# Windgate

A pilot desk for a GB energy supplier’s day-ahead desk. It shows the national operational wind forecast that was actually published before the auction gate, and it scores that same file against the half-hourly wind outturn. The pilot window is delivery in January 2026. The only market data is Elexon: FUELHH wind, and WINDFOR.

The app was built with help from Cursor’s coding agent (Grok 4.7). The gate rule, the join, and the metrics are ordinary Python, covered by tests, and the numbers on screen come from those functions.

## Run it

Docker is the supported way to run the whole app:

```bash
docker compose up --build
```

Then open http://localhost:8000. The first response can take about twenty seconds while the image starts.

Without Docker, from the repository root:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
uvicorn backend.main:app --port 8000
```

For UI work, run the API and the Vite dev server in two terminals. Vite proxies `/api` to port 8000.

```bash
uvicorn backend.main:app --reload --port 8000
cd frontend && npm run dev
```

Tests:

```bash
pytest
```

Refresh the Elexon snapshot (the running app does not call Elexon itself):

```bash
python scripts/fetch_elexon.py
```

API reference is at http://localhost:8000/docs once the server is up.

## Repository

Public: https://github.com/Murli1498/kjhwr

## Hosted app

https://kjhwr-iota.vercel.app

Open that URL in a private window before submitting the form. Redeploy from the repository root with:

```bash
npx vercel --prod
```

## Video

Record one unlisted YouTube video, at most 10 minutes, in two parts. The evaluation starts with this video. A script that matches this build:

**Part 1, for the client, about 5 minutes.** Open the desk. It lands on 31 January 2026 because that day had the largest move between the last two files available before the N2EX gate. Say what the screen is for: the wind term in the day-ahead buy, not a price forecast and not a demand forecast. One megawatt-hour of wind error is one megawatt-hour of residual to buy or to unwind later. Point at the locked file: published 09:30 London on 30 January, 20 minutes before the 09:50 N2EX gate. EPEX hourly had already closed at 09:20, on the 07:30 file, which was 12 GWh higher. Show the revision list, then turn on “With outturn”: the day came in about 45 GWh below the file, so a buyer who trusted it was short. Switch to Accuracy. MAE is 2,123 MW, bias is +1,840 MW (the file ran high), skill against same-hour persistence is 0.46. The file beat “use yesterday”. The flat 90% haircut is deliberately expensive; the row that matters is the one fit on 1–21 January and scored on 22–31 January. Close on the boundary: operationally metered wind only, about four fifths of GB wind, hourly forecast, one month.

**Part 2, for the technical lead, about 5 minutes.** Draw the path: browser, FastAPI, pure functions in `backend/analysis.py`, snapshot JSON. The process does not call BMRS on a page view; `scripts/fetch_elexon.py` is the only client. Show `select_publish` and why a file must cover all 24 hours. Show the join: WINDFOR is hourly, FUELHH is the average of two settlement periods, error is forecast minus actual. Positive means short. Show the tests that lock the January gates: N2EX gets 09:30, EPEX hourly gets 07:30, the half-hour auction gets 15:30, and a one-minute buffer drops that 15:30 file. Mention 15 January, when the late-morning run is 12:25 rather than 11:30, and that the code keeps it as its own slot. Mention the holdout split and that a haircut fit on the same hours it scores is not a policy. Show the Dockerfile: Node builds the UI, Python serves the API and the built files, one port.

## What the product does

- Locks the latest WINDFOR publication at or before the chosen gate, minus a preparation buffer. Gates are N2EX 09:50, EPEX hourly 09:20, and EPEX half-hourly 15:30, all London time.
- Shows how that file moved through the publications on the decision day and the delivery day. Files after the deadline are marked as no longer a day-ahead input.
- Draws an error band from earlier January days, or from the whole month if you ask for the retrospective view. The band is the 10th to 90th percentile of forecast minus actual, by forecast level when the bin is large enough.
- Scores the gate-time file on MAE, RMSE, bias, and a persistence skill. A haircut fit on the first three weeks is scored on the last ten days.

## Files and directories

| Path | What it is |
| --- | --- |
| `backend/analysis.py` | Gates, the hourly join, quantiles, metrics, the error band, the haircut |
| `backend/present.py` | The JSON for the desk, the month score, and the calendar, including the sentences on screen |
| `backend/store.py` | Loads the snapshot |
| `backend/main.py` | FastAPI routes, CSV export, and the built UI |
| `backend/tests/test_analysis.py` | Unit tests and a check that this January snapshot locks the expected files |
| `frontend/` | React and Vite. Desk, Accuracy, and Method |
| `data/elexon_january_2026.json` | FUELHH wind from 30 December 2025 through 31 January 2026, and WINDFOR publications from 30 December through 31 January |
| `scripts/fetch_elexon.py` | Rebuilds that snapshot from the Elexon stream endpoints |
| `Dockerfile`, `docker-compose.yml` | One image: UI build, then the API |
| `api/index.py`, `vercel.json` | Vercel entry: the same FastAPI app, plus the built UI |
| `heroku.yml` | Same image, for the Heroku container stack |
| `requirements.txt`, `requirements-dev.txt` | Runtime and test dependencies |
| `.github/workflows/test.yml` | Pytest, and a frontend production build |

## Data and method

FUELHH `generation` for `fuelType=WIND` is the half-hourly average MW. WINDFOR `generation` is hourly and is treated as the average MW for that clock hour. The hourly outturn is the mean of the two settlement periods, which is also the energy in that hour. Error is forecast minus actual. A positive error means operational wind came in below the file.

Both series are operationally metered wind visible to the system operator. Elexon states that this leaves out embedded wind, and that in 2025 about 82% of wind capacity had operational meters. This is not total GB wind. Demand, prices, and other fuels are out of scope, so the desk never prints a buy quantity. It prints the wind term and the error in it.

January 2026 is GMT, so London and UTC show the same clock. Deadlines are still computed in `Europe/London`. The hour generator steps in UTC, so a spring-forward day has 23 hours and an autumn day has 25. The API refuses delivery dates outside this January.

Quantiles are nearest-rank, `ceil(p × n)`. The in-sample 90% haircut covers at least 90% of the hours it was fit on, by construction. The held-out row does not.

Elexon retains rights in the underlying data. The snapshot is stored so a review does not depend on BMRS being available, and so the January numbers do not move under a reviewer.
