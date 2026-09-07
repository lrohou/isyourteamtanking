"""
update_data.py - Script de mise à jour des données de tanking.

Récupère les données de l'API NBA pour les 30 équipes,
calcule le Tanking Score de chaque équipe, et sauvegarde les résultats
dans data/results.json.

Usage :
    python update_data.py              # Mise à jour avec données réelles
    python update_data.py --demo       # Générer/réinitialiser les données de démo
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

from nba_data import (
    get_all_teams,
    get_team_roster,
    get_team_player_stats,
    get_team_stats_by_period,
    get_team_game_logs,
    CURRENT_SEASON,
)
from tanking_engine import calculate_tanking_score, generate_demo_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = DATA_DIR / "results.json"


def update_all_teams(season: str = CURRENT_SEASON) -> list[dict]:
    """
    Met à jour les scores de tanking pour toutes les équipes.
    Retourne la liste des résultats triés par score décroissant.
    """
    logger.info(f"Starting data update for season {season}...")

    # 1. Récupérer les stats globales (une seule requête pour toute la ligue)
    logger.info("Fetching league-wide stats (full game + Q4)...")
    full_game_stats = get_team_stats_by_period(season=season, period=0)
    time.sleep(1)
    q4_stats = get_team_stats_by_period(season=season, period=4)

    if not full_game_stats:
        logger.error("Could not fetch league stats. Aborting update.")
        return []

    # 2. Récupérer la liste des équipes
    teams = get_all_teams()
    if not teams:
        logger.error("Could not fetch teams list.")
        return []

    logger.info(f"Processing {len(teams)} teams...")
    results = []

    for i, team in enumerate(teams):
        team_id = team["id"]
        team_name = team["full_name"]
        team_abbr = team["abbreviation"]

        logger.info(f"[{i+1}/{len(teams)}] Processing {team_name}...")

        try:
            # Récupérer le roster et les stats joueurs
            roster = get_team_roster(team_id, season)
            player_stats = get_team_player_stats(team_id, season)
            game_logs = get_team_game_logs(team_id, season)

            # Calculer le bilan W/L
            if game_logs:
                wins = sum(1 for g in game_logs if g.get("WL") == "W")
                losses = sum(1 for g in game_logs if g.get("WL") == "L")
            else:
                wins, losses = 0, 0

            total = wins + losses
            pct = wins / total if total > 0 else 0

            team_record = {
                "wins": wins,
                "losses": losses,
                "pct": round(pct, 3),
            }

            # Calculer le tanking score
            result = calculate_tanking_score(
                team_id=team_id,
                team_name=team_name,
                team_abbreviation=team_abbr,
                roster=roster,
                player_stats=player_stats,
                full_game_stats=full_game_stats,
                q4_stats=q4_stats,
                team_record=team_record,
                season=season,
            )
            results.append(result)
            logger.info(
                f"  → {team_name}: Tanking Score = {result['tanking_score']}% "
                f"({result['status_label']})"
            )

        except Exception as e:
            logger.error(f"  ✗ Error processing {team_name}: {e}")
            continue

        # Pause entre les équipes
        time.sleep(0.5)

    # Trier par score décroissant
    results.sort(key=lambda x: -x["tanking_score"])

    # Sauvegarder
    try:
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Results saved to {RESULTS_FILE} ({len(results)} teams)")
    except OSError as e:
        logger.error(f"Failed to save results: {e}")

    return results


def main():
    if "--demo" in sys.argv:
        logger.info("Generating demo data...")
        demo = generate_demo_data()
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(demo, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Demo data saved to {RESULTS_FILE} ({len(demo)} teams)")
        return

    start = time.time()
    results = update_all_teams()
    elapsed = time.time() - start

    if results:
        logger.info(f"Update complete in {elapsed:.1f}s. Top 5 tanking teams:")
        for r in results[:5]:
            logger.info(
                f"  {r['tanking_score']:3d}% - {r['team_name']} "
                f"({r['record']['wins']}-{r['record']['losses']})"
            )
    else:
        logger.warning("Update produced no results. Check API connectivity.")


if __name__ == "__main__":
    main()
