"""
main.py - Serveur FastAPI pour IsYourTeamTanking.

Sert l'API JSON et le frontend statique.
Au démarrage, charge les résultats pré-calculés (ou génère les données de démo).
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from tanking_engine import compute_badges_and_suspects
from nba_data import CURRENT_SEASON, fetch_draft_prospects, fetch_live_standings, fetch_team_schedule

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = DATA_DIR / "results.json"

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------

def load_results() -> list[dict]:
    """Charge les calculs persistés avant de les synchroniser avec l'API NBA."""
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for result in data:
                    if "badges" not in result or "suspect_tracker" not in result:
                        result.update(compute_badges_and_suspects(
                            result.get("tanking_score", 0),
                            result.get("pillars", []),
                            result.get("team_abbreviation", ""),
                            result.get("team_name", "Team"),
                        ))
            logger.info(f"Loaded {len(data)} computed team results from {RESULTS_FILE}")
            return sync_live_standings(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error loading results: {e}")

    logger.error("No computed results file available; refusing to serve demo data.")
    return []


def sync_live_standings(results: list[dict]) -> list[dict]:
    """Synchronise les champs de classement depuis l'API NBA officielle."""
    standings = fetch_live_standings(season=CURRENT_SEASON)
    if not standings:
        logger.warning("NBA standings API unavailable; serving last computed cache.")
        return results

    by_team_id = {row.get("TeamID"): row for row in standings}
    synced = []
    for result in results:
        live = by_team_id.get(result.get("team_id"))
        if not live:
            continue
        wins = int(live.get("WINS", result.get("record", {}).get("wins", 0)))
        losses = int(live.get("LOSSES", result.get("record", {}).get("losses", 0)))
        games = wins + losses
        result["team_name"] = f"{live.get('TeamCity', '')} {live.get('TeamName', '')}".strip()
        result["record"] = {"wins": wins, "losses": losses, "pct": round(wins / games, 3) if games else 0}
        result["conference"] = live.get("Conference", result.get("conference"))
        result["season"] = CURRENT_SEASON
        result["last_updated"] = datetime.now().isoformat()
        result["data_source"] = "NBA Stats API"
        synced.append(result)

    for conference in ("East", "West"):
        teams = sorted(
            [r for r in synced if r.get("conference") == conference],
            key=lambda item: -item["record"]["pct"],
        )
        for rank, result in enumerate(teams, 1):
            result["standings_rank"] = rank
    return synced


# Données en mémoire (rechargées au démarrage)
_results: list[dict] = []

# ---------------------------------------------------------------------------
# Application FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IsYourTeamTanking API",
    description="NBA Tanking Detection API - Détecte automatiquement le tanking en NBA.",
    version="1.0.0",
)

# CORS pour le développement local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    global _results
    _results = load_results()
    logger.info(f"Server started with {len(_results)} teams loaded for {CURRENT_SEASON}.")


# ---------------------------------------------------------------------------
# Endpoints API
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "teams_loaded": len(_results),
        "season": CURRENT_SEASON,
        "data_source": "NBA Stats API + computed metrics",
        "data_status": "live standings synchronized; tanking metrics computed from NBA stats",
        "last_updated": max((r.get("last_updated", "") for r in _results), default=None),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/teams")
async def get_teams():
    """Liste des 30 équipes NBA avec leur score de tanking résumé."""
    return [
        {
            "team_id": r["team_id"],
            "team_name": r["team_name"],
            "team_abbreviation": r["team_abbreviation"],
            "tanking_score": r["tanking_score"],
            "status": r["status"],
            "status_label": r["status_label"],
            "record": r.get("record", {}),
            "data_source": r.get("data_source", "NBA Stats API + computed metrics"),
            "last_updated": r.get("last_updated"),
        }
        for r in _results
    ]


@app.get("/api/tanking/all")
async def get_all_tanking():
    """Classement complet de toutes les équipes par tanking score."""
    if not _results:
        raise HTTPException(status_code=503, detail="NBA data is currently unavailable.")
    return sorted(_results, key=lambda x: -x["tanking_score"])


@app.get("/api/tanking/{team_id}")
async def get_tanking(team_id: int):
    """Score de tanking détaillé pour une équipe spécifique."""
    for r in _results:
        if r["team_id"] == team_id:
            return r
    raise HTTPException(status_code=404, detail=f"Team {team_id} not found.")


@app.get("/api/reload")
async def reload_data():
    """Recharge les données depuis le fichier JSON (utile après un update_data)."""
    global _results
    _results = load_results()
    return {"status": "reloaded", "teams": len(_results)}


@app.get("/api/standings")
async def get_live_standings():
    """Récupère le classement en direct via l'API NBA."""
    return fetch_live_standings()


@app.get("/api/draft/prospects")
async def get_draft_prospects():
    """Retourne les prospects actuels du Big Board Tankathon."""
    prospects = fetch_draft_prospects(limit=10)
    if not prospects:
        raise HTTPException(status_code=503, detail="Draft prospect data is currently unavailable.")
    return {"season": CURRENT_SEASON, "source": "Tankathon Big Board", "prospects": prospects}


@app.get("/api/schedule/{team_id}")
async def get_team_schedule(team_id: int, team_abbr: str):
    """Récupère le calendrier en direct (3 derniers, 3 prochains) pour une équipe."""
    return fetch_team_schedule(team_id, team_abbr)


# ---------------------------------------------------------------------------
# Servir le frontend
# ---------------------------------------------------------------------------

# Monter les fichiers statiques du frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse({"error": "Frontend not found"}, status_code=404)

    # Catch-all pour servir les fichiers frontend
    @app.get("/{path:path}")
    async def serve_static(path: str):
        # Ne pas intercepter les routes API
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = FRONTEND_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Fallback vers index.html (SPA behavior)
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404)
