"""
nba_data.py - Couche d'accès aux données NBA via nba_api.

Gère le rate limiting, le cache JSON et les fallbacks.
Toutes les fonctions retournent des dict/list Python prêts à être sérialisés.
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Répertoire de cache
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Délai entre les requêtes nba_api pour éviter le rate limiting
REQUEST_DELAY = 0.8  # secondes

# Saison courante (à mettre à jour chaque année)
CURRENT_SEASON = "2024-25"


def _get_cache_path(key: str) -> Path:
    """Retourne le chemin du fichier cache pour une clé donnée."""
    safe_key = key.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe_key}.json"


def _read_cache(key: str, max_age_hours: int = 12) -> dict | list | None:
    """Lit le cache si le fichier existe et n'a pas expiré."""
    path = _get_cache_path(key)
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > timedelta(hours=max_age_hours):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Cache read error for {key}: {e}")
        return None


def _write_cache(key: str, data: dict | list):
    """Écrit les données dans le cache."""
    path = _get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
    except OSError as e:
        logger.warning(f"Cache write error for {key}: {e}")


def _throttle():
    """Pause entre les requêtes pour ne pas se faire bloquer."""
    time.sleep(REQUEST_DELAY)


# ---------------------------------------------------------------------------
# Fonctions de récupération de données NBA
# ---------------------------------------------------------------------------

def get_all_teams() -> list[dict]:
    """Retourne la liste des 30 équipes NBA avec leur ID."""
    cache = _read_cache("all_teams", max_age_hours=168)  # 1 semaine
    if cache:
        return cache

    try:
        from nba_api.stats.static import teams
        nba_teams = teams.get_teams()
        result = [
            {
                "id": t["id"],
                "full_name": t["full_name"],
                "abbreviation": t["abbreviation"],
                "nickname": t["nickname"],
                "city": t["city"],
                "state": t["state"],
            }
            for t in nba_teams
        ]
        _write_cache("all_teams", result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch teams: {e}")
        return []


def get_team_roster(team_id: int, season: str = CURRENT_SEASON) -> list[dict]:
    """
    Récupère le roster d'une équipe avec l'âge et la date de naissance.
    Utilise CommonTeamRoster.
    """
    cache_key = f"roster_{team_id}_{season}"
    cache = _read_cache(cache_key, max_age_hours=24)
    if cache:
        return cache

    try:
        from nba_api.stats.endpoints import commonteamroster
        _throttle()
        roster = commonteamroster.CommonTeamRoster(
            team_id=team_id,
            season=season
        )
        df = roster.get_data_frames()[0]
        result = df.to_dict(orient="records")
        _write_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch roster for team {team_id}: {e}")
        return []


def get_team_player_stats(team_id: int, season: str = CURRENT_SEASON) -> list[dict]:
    """
    Récupère les statistiques par joueur d'une équipe (minutes, points, etc.).
    Utilise TeamPlayerDashboard.
    """
    cache_key = f"player_stats_{team_id}_{season}"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    try:
        from nba_api.stats.endpoints import teamplayerdashboard
        _throttle()
        dashboard = teamplayerdashboard.TeamPlayerDashboard(
            team_id=team_id,
            season=season
        )
        frames = dashboard.get_data_frames()
        # Index 1 contient les stats individuelles des joueurs
        df = frames[1] if len(frames) > 1 else frames[0]
        result = df.to_dict(orient="records")
        _write_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch player stats for team {team_id}: {e}")
        return []


def get_player_game_logs(player_id: int, season: str = CURRENT_SEASON) -> list[dict]:
    """
    Récupère les game logs d'un joueur pour détecter les matchs manqués.
    """
    cache_key = f"player_logs_{player_id}_{season}"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    try:
        from nba_api.stats.endpoints import playergamelog
        _throttle()
        logs = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season
        )
        df = logs.get_data_frames()[0]
        result = df.to_dict(orient="records")
        _write_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch game logs for player {player_id}: {e}")
        return []


def get_team_stats_by_period(
    season: str = CURRENT_SEASON,
    period: int = 0,
) -> list[dict]:
    """
    Récupère les stats d'équipe (Net Rating, OFF/DEF Rating) pour une période.
    period=0: jeu complet, period=4: Q4 uniquement.
    """
    cache_key = f"team_stats_period_{period}_{season}"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        _throttle()
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            period=period,
            per_mode_detailed="PerGame",
            measure_type_detailed_defense="Advanced",
            league_id_nullable="00",
        )
        df = stats.get_data_frames()[0]
        result = df.to_dict(orient="records")
        _write_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch team stats period={period}: {e}")
        return []


def get_player_monthly_splits(
    player_id: int,
    season: str = CURRENT_SEASON,
) -> list[dict]:
    """
    Récupère les splits mensuels d'un joueur (minutes par mois).
    """
    cache_key = f"player_monthly_{player_id}_{season}"
    cache = _read_cache(cache_key, max_age_hours=24)
    if cache:
        return cache

    try:
        from nba_api.stats.endpoints import playerdashboardbygamesplits
        _throttle()
        splits = playerdashboardbygamesplits.PlayerDashboardByGameSplits(
            player_id=player_id,
            season=season,
            per_mode_detailed="PerGame",
        )
        frames = splits.get_data_frames()
        # Le DataFrame des splits par mois est généralement à l'index 3
        for i, df in enumerate(frames):
            if "GROUP_VALUE" in df.columns:
                records = df.to_dict(orient="records")
                _write_cache(cache_key, records)
                return records
        # Fallback: retourner le premier frame
        result = frames[0].to_dict(orient="records") if frames else []
        _write_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch monthly splits for player {player_id}: {e}")
        return []


def get_team_game_logs(team_id: int, season: str = CURRENT_SEASON) -> list[dict]:
    """Récupère les game logs d'une équipe (W/L, score, etc.)."""
    cache_key = f"team_game_logs_{team_id}_{season}"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    try:
        from nba_api.stats.endpoints import teamgamelog
        _throttle()
        logs = teamgamelog.TeamGameLog(
            team_id=team_id,
            season=season
        )
        df = logs.get_data_frames()[0]
        result = df.to_dict(orient="records")
        _write_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch game logs for team {team_id}: {e}")
        return []
