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

from tanking_engine import generate_demo_data

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
    """Charge les résultats depuis le fichier JSON, ou génère les données démo."""
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data)} team results from {RESULTS_FILE}")
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error loading results: {e}")

    # Générer les données de démo
    logger.info("No results file found. Generating demo data...")
    demo = generate_demo_data()
    try:
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(demo, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Demo data saved to {RESULTS_FILE}")
    except OSError as e:
        logger.warning(f"Could not save demo data: {e}")
    return demo


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
    logger.info(f"Server started with {len(_results)} teams loaded.")


# ---------------------------------------------------------------------------
# Endpoints API
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "teams_loaded": len(_results),
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
        }
        for r in _results
    ]


@app.get("/api/tanking/all")
async def get_all_tanking():
    """Classement complet de toutes les équipes par tanking score."""
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
