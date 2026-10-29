"""FastAPI server for IsYourTeamTanking using live ESPN NBA data."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nba_data import CURRENT_SEASON, fetch_draft_prospects, fetch_live_league_results

import json
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
RESULTS_FILE = Path(__file__).parent / "data" / "results.json"
_results: list[dict] = []
if RESULTS_FILE.exists():
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            _results = json.load(f)
            logger.info("Preloaded %s teams from results.json at startup.", len(_results))
    except Exception as e:
        logger.warning("Could not preload results.json: %s", e)

_last_refresh_error: str | None = None
_refresh_lock = asyncio.Lock()


async def refresh_results() -> bool:
    """Actualise classements, calendriers et scores de tanking depuis ESPN."""
    global _results, _last_refresh_error
    async with _refresh_lock:
        results = await asyncio.to_thread(fetch_live_league_results, CURRENT_SEASON)
        if len(results) == 30:
            _results = results
            _last_refresh_error = None
            try:
                with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            except Exception as e:
                logger.warning("Could not cache to results.json: %s", e)
            has_scores = sum(1 for r in results if r.get("tanking_score") is not None)
            logger.info("Loaded ESPN data for all 30 teams (%s with tanking scores).", has_scores)
            return True

        _last_refresh_error = "ESPN did not return valid current-season data for all 30 teams."
        if _results:
            for result in _results:
                result["data_status"] = "stale"
        logger.error(_last_refresh_error)
        return False


async def refresh_loop():
    """Actualise les données live toutes les cinq minutes."""
    while True:
        await refresh_results()
        await asyncio.sleep(300)


app = FastAPI(
    title="IsYourTeamTanking API",
    description="NBA standings, schedules and tanking scores from live ESPN data.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    asyncio.create_task(refresh_loop())
    logger.info("Server started; live ESPN refresh scheduled.")


@app.get("/api/health")
async def health():
    data_status = _results[0].get("data_status") if _results else None
    has_scores = any(r.get("tanking_score") is not None for r in _results)
    status = "warming_up" if not _results else "stale" if _last_refresh_error else "ok"
    return {
        "status": status,
        "teams_loaded": len(_results),
        "season": CURRENT_SEASON,
        "data_status": data_status,
        "data_source": "ESPN NBA API",
        "score_status": "available" if has_scores else "unavailable",
        "last_refresh_error": _last_refresh_error,
        "last_updated": _results[0].get("last_updated") if _results else None,
        "timestamp": datetime.now().astimezone().isoformat(),
    }


@app.get("/api/teams")
async def get_teams():
    return _results


@app.get("/api/tanking/all")
async def get_all_tanking():
    if not _results:
        raise HTTPException(status_code=503, detail=_last_refresh_error or "Live NBA data is loading.")
    return sorted(_results, key=lambda item: (item["conference"], item["standings_rank"]))


@app.get("/api/tanking/{team_id}")
async def get_tanking(team_id: int):
    for result in _results:
        if result["team_id"] == team_id:
            return result
    raise HTTPException(status_code=404, detail=f"Team {team_id} not found.")


@app.get("/api/reload")
async def reload_data():
    if not await refresh_results():
        raise HTTPException(status_code=503, detail=_last_refresh_error)
    return {"status": "reloaded", "teams": len(_results), "last_updated": _results[0]["last_updated"]}


@app.get("/api/standings")
async def get_live_standings():
    if not _results:
        raise HTTPException(status_code=503, detail=_last_refresh_error or "Live NBA standings are loading.")
    return _results


@app.get("/api/draft/prospects")
async def get_draft_prospects():
    prospects = fetch_draft_prospects(limit=10)
    if not prospects:
        raise HTTPException(status_code=503, detail="Draft prospect data is currently unavailable.")
    return {"season": CURRENT_SEASON, "source": "Tankathon Big Board", "prospects": prospects}


@app.get("/api/schedule/{team_id}")
async def get_team_schedule(team_id: int, team_abbr: str):
    schedule = next((team for team in _results if team["team_id"] == team_id), None)
    if not schedule:
        raise HTTPException(status_code=503, detail="Live NBA schedule is currently unavailable.")
    return {
        "recent_games": schedule["recent_games"],
        "upcoming_games": schedule["upcoming_games"],
        "season": schedule["season"],
        "data_source": schedule["data_source"],
        "last_updated": schedule["last_updated"],
    }


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse({"error": "Frontend not found"}, status_code=404)

    @app.get("/{path:path}")
    async def serve_static(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = FRONTEND_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404)
