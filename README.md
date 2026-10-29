# IsYourTeamTanking

NBA tanking detection based on live NBA statistics and four weighted signals:

- Veteran minutes drop: 30%
- DNP and availability signal: 20%
- Young lineup usage: 25%
- Fourth-quarter collapse: 25%

## Run locally

Requirements: Python 3.10+.

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

The server loads the current-season standings and game schedules from ESPN's live NBA API at startup and refreshes them every five minutes. It only publishes a refresh after receiving and validating schedules for all 30 teams; it never substitutes the old `results.json` snapshot. If ESPN is unavailable, the last successful live update is marked stale, or the API returns `503` until the first live update succeeds.

The four-pillar tanking score requires current player-level statistics. Since the NBA Stats API is timing out in some environments, the app does not reuse an old score or infer tanking from wins alone; scores and player availability are explicitly shown as unavailable until those statistics can be fetched reliably.

To force a refresh:

```bash
curl http://localhost:8000/api/reload
```

Standings, records, recent results, and upcoming games are fetched from ESPN. Draft prospects are fetched separately from Tankathon.

## API endpoints

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | Service and live-data status |
| `GET /api/teams` | Team summaries |
| `GET /api/tanking/all` | Full live rankings |
| `GET /api/tanking/{team_id}` | Live team report |
| `GET /api/standings` | NBA standings |
| `GET /api/schedule/{team_id}?team_abbr=...` | Team schedule |
| `GET /api/draft/prospects` | Current draft board |
| `GET /api/reload` | Force a live recalculation |

## Deployment

The Render service installs `backend/requirements.txt` and starts FastAPI with Uvicorn. Configure the deployment with outbound network access to ESPN and Tankathon APIs.

Tanking scores are statistical indicators for entertainment and do not represent an official NBA designation.
