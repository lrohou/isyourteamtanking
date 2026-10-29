"""Collecte et calcul des données NBA live."""

import json
import logging
import time
from pathlib import Path

from nba_data import (
    CURRENT_SEASON,
    get_all_teams,
    get_team_game_logs,
    get_team_player_stats,
    get_team_roster,
    get_team_stats_by_period,
)
from tanking_engine import calculate_tanking_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
RESULTS_FILE = Path(__file__).parent / "data" / "results.json"
RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def update_all_teams(season: str = CURRENT_SEASON) -> list[dict]:
    """Calcule les scores pour toutes les équipes exposées par l'API NBA."""
    logger.info("Starting live data update for season %s", season)
    full_game_stats = get_team_stats_by_period(season=season, period=0)
    time.sleep(1)
    q4_stats = get_team_stats_by_period(season=season, period=4)
    teams = get_all_teams()
    if not full_game_stats or not q4_stats or not teams:
        logger.error("Required live NBA data is unavailable; aborting update.")
        return []

    results = []
    for index, team in enumerate(teams, 1):
        logger.info("[%s/%s] Processing %s", index, len(teams), team["full_name"])
        try:
            team_id = team["id"]
            roster = get_team_roster(team_id, season)
            player_stats = get_team_player_stats(team_id, season)
            game_logs = get_team_game_logs(team_id, season)
            wins = sum(1 for game in game_logs if game.get("WL") == "W")
            losses = sum(1 for game in game_logs if game.get("WL") == "L")
            total_games = wins + losses
            record = {"wins": wins, "losses": losses, "pct": round(wins / total_games, 3) if total_games else 0}
            results.append(calculate_tanking_score(
                team_id=team_id,
                team_name=team["full_name"],
                team_abbreviation=team["abbreviation"],
                roster=roster,
                player_stats=player_stats,
                full_game_stats=full_game_stats,
                q4_stats=q4_stats,
                team_record=record,
                season=season,
            ))
        except Exception:
            logger.exception("Failed to process %s", team["full_name"])
        time.sleep(0.5)

    results.sort(key=lambda item: -item["tanking_score"])
    try:
        with RESULTS_FILE.open("w", encoding="utf-8") as file:
            json.dump(results, file, ensure_ascii=False, indent=2, default=str)
    except OSError:
        logger.exception("Failed to save live results")
    return results


def main():
    results = update_all_teams()
    logger.info("Live update completed with %s teams.", len(results))


if __name__ == "__main__":
    main()
