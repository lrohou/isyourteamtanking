"""
nba_data.py - Couche d'accès aux données NBA via nba_api.

Gère le rate limiting, le cache JSON et les fallbacks.
Toutes les fonctions retournent des dict/list Python prêts à être sérialisés.
"""

import json
import html
import os
import re
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Répertoire de cache
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Délai entre les requêtes nba_api pour éviter le rate limiting
REQUEST_DELAY = 0.8  # secondes

def get_current_season(reference: datetime | None = None) -> str:
    """Retourne la saison NBA correspondant à la date courante.

    L'intersaison appartient encore à la saison terminée : en septembre 2026,
    les données de classement disponibles sont donc celles de 2025-26.
    """
    current = reference or datetime.now()
    season_start = current.year if current.month >= 10 else current.year - 1
    return f"{season_start}-{str(season_start + 1)[-2:]}"


CURRENT_SEASON = get_current_season()


def is_offseason(reference: datetime | None = None) -> bool:
    """Indique si la date est dans l'intersaison NBA (mai à septembre)."""
    current = reference or datetime.now()
    return 5 <= current.month <= 9


def _get_cache_path(key: str) -> Path:
    """Retourne le chemin du fichier cache pour une clé donnée."""
    safe_key = key.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe_key}.json"


def _read_cache(key: str, max_age_hours: int = 12, allow_stale: bool = False) -> dict | list | None:
    """Lit le cache si le fichier existe et n'a pas expiré."""
    path = _get_cache_path(key)
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if not allow_stale and datetime.now() - mtime > timedelta(hours=max_age_hours):
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


def fetch_live_league_results(season: str = CURRENT_SEASON) -> list[dict]:
    """Construit le classement et les calendriers à partir des horaires ESPN live."""
    try:
        teams_response = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams",
            params={"limit": 1000},
            headers={"User-Agent": "IsYourTeamTanking/1.0"},
            timeout=20,
        )
        teams_response.raise_for_status()
        league = teams_response.json()["sports"][0]["leagues"][0]
        espn_teams = [entry["team"] for entry in league["teams"]]
        nba_teams = get_all_teams()
        if len(espn_teams) != 30 or len(nba_teams) != 30:
            raise ValueError(f"Expected 30 NBA teams, got ESPN={len(espn_teams)}, NBA={len(nba_teams)}")

        def normalize_name(name: str) -> str:
            return re.sub(r"[^a-z0-9]", "", name.lower().replace("los angeles", "la"))

        nba_by_name = {normalize_name(team["full_name"]): team for team in nba_teams}
        espn_by_nba_id = {}
        nba_abbr_by_espn_abbr = {}
        for espn_team in espn_teams:
            nba_team = nba_by_name.get(normalize_name(espn_team["displayName"]))
            if not nba_team:
                raise ValueError(f"Unable to match ESPN team {espn_team['displayName']} to an NBA team")
            espn_by_nba_id[nba_team["id"]] = espn_team
            nba_abbr_by_espn_abbr[espn_team["abbreviation"]] = nba_team["abbreviation"]

        season_year = int(season[:4]) + 1

        def fetch_team(nba_team: dict) -> dict:
            espn_team = espn_by_nba_id[nba_team["id"]]
            response = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_team['abbreviation'].lower()}/schedule",
                params={"season": season_year},
                headers={"User-Agent": "IsYourTeamTanking/1.0"},
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()
            live_team = payload.get("team", {})
            if int(payload.get("season", {}).get("year", 0)) != season_year:
                raise ValueError(f"ESPN returned the wrong season for {nba_team['full_name']}")

            completed = []
            upcoming = []
            for event in payload.get("events", []):
                if int(event.get("seasonType", {}).get("type", 0)) != 2:
                    continue
                competition = (event.get("competitions") or [{}])[0]
                competitors = competition.get("competitors", [])
                current = next((item for item in competitors if item["team"]["id"] == live_team.get("id")), None)
                opponent = next((item for item in competitors if item is not current), None)
                if not current or not opponent:
                    continue

                try:
                    game_time = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
                    game_date = game_time.astimezone(ZoneInfo("America/New_York")).strftime("%d/%m/%y")
                except (KeyError, ValueError):
                    logger.warning("Skipping ESPN game with invalid date for %s.", nba_team["full_name"])
                    continue

                game = {
                    "game_id": event.get("id"),
                    "game_url": f"https://www.espn.com/nba/game/_/gameId/{event.get('id')}",
                    "date": game_date,
                    "opponent": nba_abbr_by_espn_abbr.get(opponent["team"]["abbreviation"], opponent["team"]["abbreviation"]),
                    "home": current.get("homeAway") == "home",
                }
                if competition.get("status", {}).get("type", {}).get("completed"):
                    game["team_score"] = int(float(current["score"]["value"]))
                    game["opponent_score"] = int(float(opponent["score"]["value"]))
                    game["result"] = "W" if current.get("winner") else "L"
                    completed.append(game)
                else:
                    upcoming.append(game)

            wins = sum(game["result"] == "W" for game in completed)
            losses = len(completed) - wins
            reported_record = re.fullmatch(r"(\d+)-(\d+)", live_team.get("recordSummary", ""))
            if reported_record and (wins, losses) != tuple(map(int, reported_record.groups())):
                raise ValueError(f"Schedule and ESPN record disagree for {nba_team['full_name']}")
            point_difference = sum(game["team_score"] - game["opponent_score"] for game in completed)
            conference_id = str(live_team.get("groups", {}).get("parent", {}).get("id", ""))
            conference = {"5": "East", "6": "West"}.get(conference_id)
            if not conference:
                raise ValueError(f"Unknown ESPN conference for {nba_team['full_name']}: {conference_id}")
            return {
                "team_id": nba_team["id"],
                "team_name": nba_team["full_name"],
                "team_abbreviation": nba_team["abbreviation"],
                "season": season,
                "conference": conference,
                "record": {"wins": wins, "losses": losses, "pct": round(wins / (wins + losses), 3) if wins + losses else 0},
                "recent_games": list(reversed(completed[-3:])),
                "upcoming_games": upcoming[:3],
                "_point_difference": point_difference,
            }

        results = []
        failures = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_team, team): team for team in nba_teams}
            for future in as_completed(futures):
                team = futures[future]
                try:
                    results.append(future.result())
                except (KeyError, TypeError, ValueError, requests.RequestException) as error:
                    failures.append(team["full_name"])
                    logger.error("Failed to load current ESPN data for %s: %s", team["full_name"], error)

        if failures or len(results) != 30:
            logger.error("Discarding incomplete live NBA refresh; loaded %s of 30 teams.", len(results))
            return []

        for conference in ("East", "West"):
            conference_teams = sorted(
                (team for team in results if team["conference"] == conference),
                key=lambda team: (-team["record"]["pct"], -team["record"]["wins"], -team["_point_difference"], team["team_name"]),
            )
            if len(conference_teams) != 15:
                logger.error("Expected 15 teams in %s, got %s.", conference, len(conference_teams))
                return []
            for rank, team in enumerate(conference_teams, 1):
                team["standings_rank"] = rank
                team["standings_total"] = 15

        updated_at = datetime.now().astimezone().isoformat()
        for result in results:
            result.pop("_point_difference")
            result.update({
                "tanking_score": None,
                "status": "unavailable",
                "status_label": "Tanking score unavailable",
                "pillars": [],
                "badges": [],
                "suspect_tracker": {"overall_suspicion": None, "players": []},
                "tanking_history": [],
                "data_status": "live",
                "data_source": "ESPN NBA API",
                "last_updated": updated_at,
                "score_status": "unavailable",
            })
        return results
    except (KeyError, TypeError, ValueError, requests.RequestException) as error:
        logger.error("Failed to load live ESPN NBA data: %s", error)
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
    cache = _read_cache(cache_key, max_age_hours=1)
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
    stale_cache = _read_cache(cache_key, allow_stale=True)
    if stale_cache:
        logger.warning("Using the last available standings snapshot for %s.", season)
        return stale_cache
    return []


def fetch_draft_prospects(limit: int = 10) -> list[dict]:
    """Récupère le Big Board de la prochaine draft depuis Tankathon."""
    cache_key = f"draft_prospects_{get_current_season()}"
    cache = _read_cache(cache_key, max_age_hours=6)
    if cache:
        return cache[:limit]

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
    try:
        response = requests.get("https://www.tankathon.com/big_board", headers=headers, timeout=20)
        response.raise_for_status()
        matches = re.findall(
            r'/players/[^"\']+"><div class="mock-row-name">([^<]+)</div>'
            r'<div class="mock-row-school-position">([^<]+)</div>',
            response.text,
        )
        prospects = []
        seen = set()
        for raw_name, raw_position_school in matches:
            name = html.unescape(re.sub(r"\s+", " ", raw_name)).strip()
            position_school = html.unescape(re.sub(r"\s+", " ", raw_position_school)).strip()
            if " | " not in position_school or name in seen:
                continue
            position, school = position_school.split(" | ", 1)
            seen.add(name)
            prospects.append({"name": name, "school": school, "position": position, "note": "Current Tankathon Big Board"})
            if len(prospects) == limit:
                break
        if prospects:
            _write_cache(cache_key, prospects)
        return prospects
    except Exception as e:
        logger.error(f"Failed to fetch draft prospects: {e}")
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
