# 🏀 IsYourTeamTanking

> **Is your NBA team secretly tanking?** Find out with statistical evidence.

Real-time NBA tanking detection powered by a composite **Tanking Score** (0-100%) built from 4 statistical pillars:

| Pillar | Weight | What it measures |
|--------|--------|------------------|
| ⏱️ Veteran Minutes Drop | 30% | Are experienced players being benched? |
| 🏥 DNP / Injury Suspects | 20% | Are key players mysteriously "resting"? |
| 👶 Young Lineup Usage | 25% | Is the team fielding abnormally young lineups? |
| 📉 Clutch Collapse (Q4) | 25% | Does the team collapse in 4th quarters? |

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Install & Run

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Generate demo data (uses simulated 2024-25 season data)
python update_data.py --demo

# 3. Start the server
uvicorn main:app --reload

# 4. Open http://localhost:8000 in your browser
```

### Update with real NBA data

```bash
# Fetch live data from stats.nba.com (takes ~5 min for all 30 teams)
cd backend
python update_data.py
```

> ⚠️ **Rate limiting**: The NBA API may throttle requests. The script includes automatic delays between calls. Run this at most 1-2x per day.

## Architecture

```
isyourteamtanking/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── tanking_engine.py     # Tanking Score algorithm
│   ├── nba_data.py           # NBA API wrapper with caching
│   ├── update_data.py        # Data refresh script
│   ├── requirements.txt      # Python dependencies
│   └── data/                 # Cached results (auto-generated)
│       └── results.json
├── frontend/
│   ├── index.html            # Main page
│   ├── style.css             # Premium dark mode design
│   ├── app.js                # SPA logic
│   └── teams.js              # NBA teams static data
├── Dockerfile                # Container deployment
├── render.yaml               # Render.com config
└── README.md
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/teams` | All teams with summary scores |
| `GET /api/tanking/all` | Full rankings with details |
| `GET /api/tanking/{team_id}` | Detailed report for one team |
| `GET /api/reload` | Reload data from disk |

## Deployment (Render)

1. Push to GitHub
2. Connect repo to [Render](https://render.com)
3. Deploy as **Web Service** (free tier)
4. The app auto-generates demo data on first startup

## Tech Stack

- **Backend**: Python, FastAPI, nba_api, pandas
- **Frontend**: Vanilla JS, CSS (dark mode, glassmorphism)
- **Data**: JSON file cache (no database needed)

## License

MIT - Built for educational and entertainment purposes.

---

*This tool is for entertainment purposes only. "Tanking" is inferred from publicly available statistical patterns and does not reflect any official NBA designation.*