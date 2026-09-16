"""
nba_data.py - Couche d'accès aux données NBA via nba_api.

Gère le rate limiting, le cache JSON et les fallbacks.
Toutes les fonctions retournent des dict/list Python prêts à être sérialisés.
"""

import json
import os
import time
import logging
import requests
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


def fetch_live_standings(season: str = CURRENT_SEASON) -> list[dict]:
    """
    Récupère le classement en temps réel depuis stats.nba.com.
    """
    cache_key = f"live_standings_{season}"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
        'Origin': 'https://www.nba.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
    }
    url = f"https://stats.nba.com/stats/leaguestandingsv3?LeagueID=00&Season={season}&SeasonType=Regular+Season"
    
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            rs = data.get('resultSets', [])
            if rs:
                headers_list = rs[0].get('headers', [])
                rows = rs[0].get('rowSet', [])
                result = [dict(zip(headers_list, row)) for row in rows]
                _write_cache(cache_key, result)
                return result
    except Exception as e:
        logger.error(f"Failed to fetch live standings: {e}")
    return []


def fetch_team_schedule(team_id: int, team_abbr: str, season: str = CURRENT_SEASON) -> dict:
    """
    Récupère le calendrier de l'équipe (3 derniers, 3 prochains) via cdn.nba.com.
    """
    cache_key = f"team_schedule_{team_id}_{season}"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
        'Origin': 'https://www.nba.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
    }
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            dates = data.get('leagueSchedule', {}).get('gameDates', [])
            
            team_games = []
            for gd in dates:
                for g in gd.get('games', []):
                    ht = g.get('homeTeam', {})
                    at = g.get('awayTeam', {})
                    if ht.get('teamId') == team_id or at.get('teamId') == team_id or ht.get('teamTricode') == team_abbr or at.get('teamTricode') == team_abbr:
                        is_home = ht.get('teamId') == team_id or ht.get('teamTricode') == team_abbr
                        team_games.append({
                            'game_id': g.get('gameId'),
                            'date': gd.get('gameDate'), # MM/DD/YYYY 00:00:00
                            'opponent': at.get('teamTricode') if is_home else ht.get('teamTricode'),
                            'home': is_home,
                            'team_score': ht.get('score', 0) if is_home else at.get('score', 0),
                            'opponent_score': at.get('score', 0) if is_home else ht.get('score', 0),
                            'status': g.get('gameStatus'), # 1=Scheduled, 2=Live, 3=Final
                        })
            
            completed = [g for g in team_games if g['status'] == 3]
            upcoming = [g for g in team_games if g['status'] in (1, 2)]
            
            # Format dates to DD/MM/YY
            for g in team_games:
                try:
                    dt = datetime.strptime(g['date'].split(' ')[0], '%m/%d/%Y')
                    g['date_fmt'] = dt.strftime('%d/%m/%y')
                except:
                    g['date_fmt'] = g['date']
                    
            recent_games = []
            for g in completed[-3:]:
                is_win = g['team_score'] > g['opponent_score']
                recent_games.append({
                    'game_id': g['game_id'],
                    'date': g['date_fmt'],
                    'opponent': g['opponent'],
                    'home': g['home'],
                    'result': 'W' if is_win else 'L',
                    'team_score': g['team_score'],
                    'opponent_score': g['opponent_score']
                })
                
            upcoming_games = []
            for g in upcoming[:3]:
                upcoming_games.append({
                    'game_id': g['game_id'],
                    'date': g['date_fmt'],
                    'opponent': g['opponent'],
                    'home': g['home']
                })
                
            result = {
                'recent_games': recent_games,
                'upcoming_games': upcoming_games
            }
            _write_cache(cache_key, result)
            return result
    except Exception as e:
        logger.error(f"Failed to fetch schedule for team {team_id}: {e}")
    return {}


def fetch_all_schedules() -> dict:
    """
    Récupère le calendrier complet de la ligue en un seul appel CDN,
    puis retourne un dict {team_id: {"recent_games": [...], "upcoming_games": [...]}}
    pour les 30 équipes. Ultra rapide (~1 requête HTTP).
    """
    cache_key = "all_schedules_bulk"
    cache = _read_cache(cache_key, max_age_hours=12)
    if cache:
        return cache

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
        'Origin': 'https://www.nba.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
    }
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            logger.error(f"CDN schedule returned {r.status_code}")
            return {}

        data = r.json()
        dates = data.get('leagueSchedule', {}).get('gameDates', [])

        # Build per-team game lists
        team_games: dict[int, list] = {}
        for gd in dates:
            for g in gd.get('games', []):
                ht = g.get('homeTeam', {})
                at = g.get('awayTeam', {})
                home_id = ht.get('teamId')
                away_id = at.get('teamId')

                # Format date
                raw_date = gd.get('gameDate', '')
                try:
                    dt = datetime.strptime(raw_date.split(' ')[0], '%m/%d/%Y')
                    date_fmt = dt.strftime('%d/%m/%y')
                except Exception:
                    date_fmt = raw_date

                game_status = g.get('gameStatus')  # 1=Scheduled 2=Live 3=Final
                game_id = g.get('gameId')

                # Home team entry
                if home_id:
                    team_games.setdefault(home_id, []).append({
                        'game_id': game_id,
                        'date': date_fmt,
                        'opponent': at.get('teamTricode', ''),
                        'home': True,
                        'team_score': ht.get('score', 0),
                        'opponent_score': at.get('score', 0),
                        'status': game_status,
                    })
                # Away team entry
                if away_id:
                    team_games.setdefault(away_id, []).append({
                        'game_id': game_id,
                        'date': date_fmt,
                        'opponent': ht.get('teamTricode', ''),
                        'home': False,
                        'team_score': at.get('score', 0),
                        'opponent_score': ht.get('score', 0),
                        'status': game_status,
                    })

        # Extract recent (last 3 completed) and upcoming (first 3 scheduled) per team
        result = {}
        for tid, games in team_games.items():
            completed = [g for g in games if g['status'] == 3]
            upcoming = [g for g in games if g['status'] in (1, 2)]

            recent_games = []
            for g in completed[-3:]:
                is_win = (g['team_score'] or 0) > (g['opponent_score'] or 0)
                recent_games.append({
                    'game_id': g['game_id'],
                    'date': g['date'],
                    'opponent': g['opponent'],
                    'home': g['home'],
                    'result': 'W' if is_win else 'L',
                    'team_score': g['team_score'],
                    'opponent_score': g['opponent_score'],
                })

            upcoming_games = []
            for g in upcoming[:3]:
                upcoming_games.append({
                    'game_id': g['game_id'],
                    'date': g['date'],
                    'opponent': g['opponent'],
                    'home': g['home'],
                })

            result[str(tid)] = {
                'recent_games': recent_games,
                'upcoming_games': upcoming_games,
            }

        _write_cache(cache_key, result)
        logger.info(f"Fetched bulk schedule for {len(result)} teams")
        return result

    except Exception as e:
        logger.error(f"Failed to fetch bulk schedule: {e}")
        return {}


