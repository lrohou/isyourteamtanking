"""
tanking_engine.py - Moteur de calcul du Tanking Score.

Score composite de 0 Ã  100 basÃ© sur 4 piliers :
  1. Vet Minutes Drop (30%)   - Chute du temps de jeu des vÃ©tÃ©rans
  2. DNP / Injury Suspects (20%) - Absences suspectes des joueurs clÃ©s
  3. Young Lineup Usage (25%)  - Rajeunissement des lineups
  4. Clutch Collapse Q4 (25%) - Effondrement au 4e quart-temps
"""

import logging
import random
from datetime import datetime, timedelta

from nba_data import fetch_live_standings, fetch_team_schedule, get_team_game_logs, fetch_all_schedules

logger = logging.getLogger(__name__)

# Poids de chaque pilier dans le score final
WEIGHTS = {
    "vet_minutes": 0.30,
    "dnp_suspects": 0.20,
    "young_lineups": 0.25,
    "clutch_collapse": 0.25,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _get_player_age(player: dict) -> float | None:
    """Extrait l'Ã¢ge d'un joueur depuis les donnÃ©es du roster."""
    if "AGE" in player and player["AGE"]:
        try:
            return float(player["AGE"])
        except (ValueError, TypeError):
            pass
    if "BIRTH_DATE" in player and player["BIRTH_DATE"]:
        try:
            bd = player["BIRTH_DATE"]
            if isinstance(bd, str):
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%b %d, %Y", "%Y-%m-%d"):
                    try:
                        born = datetime.strptime(bd, fmt)
                        return (datetime.now() - born).days / 365.25
                    except ValueError:
                        continue
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Pilier 1 : Vet Minutes Drop
# ---------------------------------------------------------------------------

def calc_vet_minutes_drop(roster: list[dict], player_stats: list[dict]) -> dict:
    """
    Compare les minutes des vÃ©tÃ©rans (â‰¥28 ans) avec l'ensemble de l'Ã©quipe.
    Regarde si les vÃ©tÃ©rans jouent anormalement peu par rapport Ã  leur potentiel.
    
    Signal fort : les meilleurs joueurs de l'Ã©quipe jouent peu de minutes.
    """
    vet_ids = set()
    for p in roster:
        age = _get_player_age(p)
        if age and age >= 28:
            pid = p.get("PLAYER_ID") or p.get("player_id")
            if pid:
                vet_ids.add(int(pid))

    if not player_stats or not vet_ids:
        return {
            "score": 0,
            "description": "Insufficient data to evaluate veteran minutes.",
            "details": "Not enough roster or stats data available.",
            "data": {},
        }

    # Trouver les vÃ©tÃ©rans dans les stats de l'Ã©quipe
    vet_stats = []
    all_minutes = []

    for ps in player_stats:
        pid = ps.get("PLAYER_ID") or ps.get("player_id")
        mins = ps.get("MIN", 0)
        gp = ps.get("GP", 0)
        if not pid or not gp:
            continue

        try:
            mins = float(mins)
            gp = int(gp)
        except (ValueError, TypeError):
            continue

        if gp < 5:
            continue

        all_minutes.append(mins)
        if int(pid) in vet_ids:
            vet_stats.append({
                "player_id": int(pid),
                "name": ps.get("PLAYER_NAME", "Unknown"),
                "minutes": mins,
                "games_played": gp,
            })

    if not vet_stats or not all_minutes:
        return {
            "score": 0,
            "description": "No veteran data available.",
            "details": "No veterans found with sufficient playing time.",
            "data": {},
        }

    # Moyenne des minutes de tous les joueurs actifs
    team_avg_min = sum(all_minutes) / len(all_minutes) if all_minutes else 25.0

    # Moyenne des minutes des vÃ©tÃ©rans
    vet_avg_min = sum(v["minutes"] for v in vet_stats) / len(vet_stats)

    # Le ratio vet_minutes / team_avg est un indicateur
    # Si les vÃ©tÃ©rans jouent moins que la moyenne â†’ signal de tanking
    ratio = vet_avg_min / team_avg_min if team_avg_min > 0 else 1.0

    # Normalement, les vÃ©tÃ©rans jouent PLUS que la moyenne (ratio > 1.0).
    # Un ratio < 0.8 est suspect, < 0.6 est un signal fort
    if ratio >= 1.1:
        score = 0
    elif ratio >= 0.9:
        score = 15
    elif ratio >= 0.75:
        score = 40
    elif ratio >= 0.6:
        score = 65
    else:
        score = 90

    # Bonus : si un vÃ©tÃ©ran de qualitÃ© joue < 20 min
    low_min_vets = [v for v in vet_stats if v["minutes"] < 20]
    if len(low_min_vets) >= 3:
        score = min(100, score + 15)
    elif len(low_min_vets) >= 2:
        score = min(100, score + 8)

    score = _clamp(score)

    if score >= 70:
        desc = "Significant drop in veteran playing time detected."
    elif score >= 40:
        desc = "Veterans are playing fewer minutes than expected."
    else:
        desc = "Veteran minutes are within normal range."

    top_vets_str = ", ".join(
        f"{v['name']} ({v['minutes']:.1f} min)" for v in sorted(vet_stats, key=lambda x: -x["minutes"])[:3]
    )

    return {
        "score": round(score),
        "description": desc,
        "details": (
            f"Veterans (28+) average {vet_avg_min:.1f} min/game vs team average "
            f"{team_avg_min:.1f} min (ratio: {ratio:.2f}). "
            f"Top vets: {top_vets_str}."
        ),
        "data": {
            "vet_avg_minutes": round(vet_avg_min, 1),
            "team_avg_minutes": round(team_avg_min, 1),
            "ratio": round(ratio, 2),
            "low_minute_vets": len(low_min_vets),
            "total_vets": len(vet_stats),
        },
    }


# ---------------------------------------------------------------------------
# Pilier 2 : DNP / Injury Suspects
# ---------------------------------------------------------------------------

def calc_dnp_suspects(roster: list[dict], player_stats: list[dict], team_games: int = 82) -> dict:
    """
    DÃ©tecte les absences suspectes des joueurs clÃ©s.
    Si les meilleurs joueurs manquent beaucoup de matchs en fin de saison,
    c'est un signal de tanking (repos, blessures mineures, etc.).
    """
    if not player_stats:
        return {
            "score": 0,
            "description": "Insufficient data for DNP analysis.",
            "details": "No player stats available.",
            "data": {},
        }

    # Identifier les top joueurs par points (top 5)
    sorted_players = sorted(
        [p for p in player_stats if p.get("GP", 0) and p.get("GP", 0) > 0],
        key=lambda x: float(x.get("PTS", 0)),
        reverse=True,
    )
    top_players = sorted_players[:5]

    if not top_players:
        return {
            "score": 0,
            "description": "No key players identified.",
            "details": "Could not identify top scorers.",
            "data": {},
        }

    # Calculer le ratio de matchs manquÃ©s par les top joueurs
    total_missed = 0
    player_details = []

    for p in top_players:
        gp = int(p.get("GP", 0))
        name = p.get("PLAYER_NAME", "Unknown")
        pts = float(p.get("PTS", 0))
        missed = team_games - gp

        # Ratio de matchs manquÃ©s (0 = a tout jouÃ©, 1 = n'a rien jouÃ©)
        miss_ratio = missed / team_games if team_games > 0 else 0

        player_details.append({
            "name": name,
            "games_played": gp,
            "games_missed": missed,
            "miss_ratio": round(miss_ratio, 2),
            "ppg": round(pts, 1),
        })
        total_missed += missed

    avg_miss_ratio = total_missed / (len(top_players) * team_games) if top_players else 0

    # BarÃ¨me :
    # < 10% absent : normal (blessures courantes)
    # 10-25% : zone grise
    # 25-40% : suspect
    # > 40% : signal fort
    if avg_miss_ratio < 0.10:
        score = 5
    elif avg_miss_ratio < 0.20:
        score = 25
    elif avg_miss_ratio < 0.35:
        score = 55
    elif avg_miss_ratio < 0.50:
        score = 78
    else:
        score = 95

    score = _clamp(score)

    if score >= 70:
        desc = "Key players are missing a suspicious number of games."
    elif score >= 40:
        desc = "Some key players have elevated absence rates."
    else:
        desc = "Key player availability is within normal range."

    details_str = "; ".join(
        f"{p['name']} missed {p['games_missed']} games ({p['miss_ratio']*100:.0f}%)"
        for p in player_details[:3]
    )

    return {
        "score": round(score),
        "description": desc,
        "details": f"Top scorers availability: {details_str}.",
        "data": {
            "avg_miss_ratio": round(avg_miss_ratio, 2),
            "top_players": player_details,
        },
    }


# ---------------------------------------------------------------------------
# Pilier 3 : Young Lineup Usage
# ---------------------------------------------------------------------------

def calc_young_lineup_usage(roster: list[dict], player_stats: list[dict]) -> dict:
    """
    Mesure l'Ã¢ge moyen pondÃ©rÃ© par les minutes jouÃ©es.
    Si l'Ã©quipe est anormalement jeune pondÃ©rÃ©e par minutes, c'est un signe
    de dÃ©veloppement de jeunes / tanking.
    """
    if not roster or not player_stats:
        return {
            "score": 0,
            "description": "Insufficient data for lineup age analysis.",
            "details": "No roster or stats data available.",
            "data": {},
        }

    # Construire un mapping player_id â†’ age
    age_map = {}
    for p in roster:
        pid = p.get("PLAYER_ID") or p.get("player_id")
        age = _get_player_age(p)
        if pid and age:
            age_map[int(pid)] = age

    # Calculer l'Ã¢ge moyen pondÃ©rÃ© par les minutes
    weighted_age_sum = 0.0
    total_weight = 0.0
    player_details = []

    for ps in player_stats:
        pid = ps.get("PLAYER_ID") or ps.get("player_id")
        mins = float(ps.get("MIN", 0))
        gp = int(ps.get("GP", 0))
        if not pid or mins <= 0 or gp < 5:
            continue

        pid = int(pid)
        if pid not in age_map:
            continue

        age = age_map[pid]
        total_mins = mins * gp  # minutes totales de la saison
        weighted_age_sum += age * total_mins
        total_weight += total_mins

        player_details.append({
            "name": ps.get("PLAYER_NAME", "Unknown"),
            "age": round(age, 1),
            "minutes_per_game": round(mins, 1),
        })

    if total_weight == 0:
        return {
            "score": 0,
            "description": "Could not calculate weighted team age.",
            "details": "No valid age/minutes data.",
            "data": {},
        }

    weighted_avg_age = weighted_age_sum / total_weight

    # L'Ã¢ge moyen pondÃ©rÃ© de la NBA est environ 26-27 ans.
    # < 24 : trÃ¨s jeune (dÃ©veloppement / tanking)
    # 24-25 : jeune
    # 25-27 : normal
    # > 27 : expÃ©rimentÃ©
    if weighted_avg_age >= 27.5:
        score = 0
    elif weighted_avg_age >= 26.5:
        score = 10
    elif weighted_avg_age >= 25.5:
        score = 25
    elif weighted_avg_age >= 24.5:
        score = 50
    elif weighted_avg_age >= 23.5:
        score = 72
    else:
        score = 92

    # Bonus si beaucoup de rookies/sophomores jouent > 25 min
    young_starters = [p for p in player_details if p["age"] < 23 and p["minutes_per_game"] > 25]
    if len(young_starters) >= 3:
        score = min(100, score + 12)
    elif len(young_starters) >= 2:
        score = min(100, score + 6)

    score = _clamp(score)

    if score >= 70:
        desc = "Lineup is very young - heavy youth development focus."
    elif score >= 40:
        desc = "Team is trending younger than the league average."
    else:
        desc = "Team age profile is within normal NBA range."

    youngest = sorted(player_details, key=lambda x: x["age"])[:3]
    youngest_str = ", ".join(f"{p['name']} ({p['age']}y, {p['minutes_per_game']}min)" for p in youngest)

    return {
        "score": round(score),
        "description": desc,
        "details": (
            f"Minutes-weighted average age: {weighted_avg_age:.1f} years. "
            f"Youngest rotation players: {youngest_str}."
        ),
        "data": {
            "weighted_avg_age": round(weighted_avg_age, 1),
            "young_starters": len(young_starters),
            "youngest_players": youngest,
        },
    }


# ---------------------------------------------------------------------------
# Pilier 4 : Clutch Collapse Q4
# ---------------------------------------------------------------------------

def calc_clutch_collapse(
    team_id: int,
    full_game_stats: list[dict],
    q4_stats: list[dict],
) -> dict:
    """
    Compare le Net Rating global vs le Net Rating du Q4.
    Les Ã©quipes qui tankent ont tendance Ã  perdre les matchs serrÃ©s en
    fin de rencontre (effondrement volontaire ou non).
    """
    if not full_game_stats or not q4_stats:
        return {
            "score": 0,
            "description": "Insufficient data for clutch analysis.",
            "details": "No quarter-by-quarter stats available.",
            "data": {},
        }

    # Trouver les stats de notre Ã©quipe
    team_full = None
    team_q4 = None

    for t in full_game_stats:
        tid = t.get("TEAM_ID") or t.get("team_id")
        if tid and int(tid) == team_id:
            team_full = t
            break

    for t in q4_stats:
        tid = t.get("TEAM_ID") or t.get("team_id")
        if tid and int(tid) == team_id:
            team_q4 = t
            break

    if not team_full or not team_q4:
        return {
            "score": 0,
            "description": "Team not found in league stats.",
            "details": f"Could not locate team {team_id} in league-wide data.",
            "data": {},
        }

    full_net = float(team_full.get("NET_RATING", 0))
    q4_net = float(team_q4.get("NET_RATING", 0))

    # Le diffÃ©rentiel : si Q4 est bien pire que le reste â†’ tanking
    differential = q4_net - full_net

    # BarÃ¨me :
    # diff > 0 : Q4 meilleur que le reste (clutch!) â†’ pas de tanking
    # diff 0 Ã  -3 : normal
    # diff -3 Ã  -6 : suspect
    # diff -6 Ã  -10 : signal fort
    # diff < -10 : trÃ¨s fort
    if differential >= 0:
        score = 0
    elif differential >= -2:
        score = 10
    elif differential >= -4:
        score = 30
    elif differential >= -6:
        score = 55
    elif differential >= -9:
        score = 78
    else:
        score = 95

    # Bonus si le Net Rating Q4 est trÃ¨s nÃ©gatif en absolu
    if q4_net < -10:
        score = min(100, score + 10)
    elif q4_net < -7:
        score = min(100, score + 5)

    score = _clamp(score)

    if score >= 70:
        desc = "Significant 4th quarter collapse detected."
    elif score >= 40:
        desc = "Team performance dips noticeably in 4th quarters."
    else:
        desc = "4th quarter performance is consistent with overall play."

    return {
        "score": round(score),
        "description": desc,
        "details": (
            f"Overall Net Rating: {full_net:+.1f} | Q4 Net Rating: {q4_net:+.1f} | "
            f"Differential: {differential:+.1f}."
        ),
        "data": {
            "full_game_net_rating": round(full_net, 1),
            "q4_net_rating": round(q4_net, 1),
            "differential": round(differential, 1),
        },
    }


# ---------------------------------------------------------------------------
# Score composite final
# ---------------------------------------------------------------------------

def get_tanking_status(score: float) -> tuple[str, str]:
    """Retourne (status_key, status_label) selon le score."""
    if score >= 66:
        return "hard_tanking", "Hard Tanking Detected!"
    elif score >= 31:
        return "soft_tanking", "Soft Tanking / Gray Zone"
    else:
        return "competing", "Actively Competing"


def calculate_tanking_score(
    team_id: int,
    team_name: str,
    team_abbreviation: str,
    roster: list[dict],
    player_stats: list[dict],
    full_game_stats: list[dict],
    q4_stats: list[dict],
    team_record: dict | None = None,
    season: str = "2024-25",
) -> dict:
    """
    Calcule le Tanking Score composite pour une Ã©quipe.
    Retourne un dictionnaire complet avec le score, le statut et les dÃ©tails
    de chaque pilier.
    """
    # Estimer le nombre de matchs jouÃ©s par l'Ã©quipe
    team_games = 82
    if team_record:
        team_games = team_record.get("wins", 0) + team_record.get("losses", 0)
        if team_games == 0:
            team_games = 82

    # Calculer chaque pilier
    p1 = calc_vet_minutes_drop(roster, player_stats)
    p2 = calc_dnp_suspects(roster, player_stats, team_games)
    p3 = calc_young_lineup_usage(roster, player_stats)
    p4 = calc_clutch_collapse(team_id, full_game_stats, q4_stats)

    # Score composite pondÃ©rÃ©
    composite = (
        p1["score"] * WEIGHTS["vet_minutes"]
        + p2["score"] * WEIGHTS["dnp_suspects"]
        + p3["score"] * WEIGHTS["young_lineups"]
        + p4["score"] * WEIGHTS["clutch_collapse"]
    )
    composite = round(_clamp(composite))

    status_key, status_label = get_tanking_status(composite)

    pillars = [
        {
            "id": "vet_minutes",
            "name": "Veteran Minutes Drop",
            "icon": "â±ï¸",
            "weight": WEIGHTS["vet_minutes"],
            "score": p1["score"],
            "weighted_score": round(p1["score"] * WEIGHTS["vet_minutes"], 1),
            **p1,
        },
        {
            "id": "dnp_suspects",
            "name": "DNP / Injury Suspects",
            "icon": "ðŸ¥",
            "weight": WEIGHTS["dnp_suspects"],
            "score": p2["score"],
            "weighted_score": round(p2["score"] * WEIGHTS["dnp_suspects"], 1),
            **p2,
        },
        {
            "id": "young_lineups",
            "name": "Young Lineup Usage",
            "icon": "ðŸ‘¶",
            "weight": WEIGHTS["young_lineups"],
            "score": p3["score"],
            "weighted_score": round(p3["score"] * WEIGHTS["young_lineups"], 1),
            **p3,
        },
        {
            "id": "clutch_collapse",
            "name": "Clutch Collapse (Q4)",
            "icon": "ðŸ“‰",
            "weight": WEIGHTS["clutch_collapse"],
            "score": p4["score"],
            "weighted_score": round(p4["score"] * WEIGHTS["clutch_collapse"], 1),
            **p4,
        },
    ]

    return {
        "team_id": team_id,
        "team_name": team_name,
        "team_abbreviation": team_abbreviation,
        "tanking_score": composite,
        "status": status_key,
        "status_label": status_label,
        "season": season,
        "last_updated": datetime.now().isoformat(),
        "pillars": pillars,
        "record": team_record or {"wins": 0, "losses": 0, "pct": 0.0},
    }


# ---------------------------------------------------------------------------
# DonnÃ©es de dÃ©mo (simulÃ©es pour la saison 2024-25)
# ---------------------------------------------------------------------------

def _generate_demo_schedule(
    team_abbr: str,
    wins: int,
    losses: int,
    all_teams_abbrs: list[str],
) -> dict:
    """
    GÃ©nÃ¨re des donnÃ©es de calendrier de dÃ©mo pour une Ã©quipe :
    - 3 derniers matchs jouÃ©s (avec rÃ©sultat, score, adversaire)
    - 3 prochains matchs (avec date, adversaire, lieu)
    """
    if team_abbr == "WAS":
        return {
            "recent_games": [
                {
                    "date": "09/04/26",
                    "opponent": "CHI",
                    "home": True,
                    "result": "L",
                    "team_score": 108,
                    "opponent_score": 119,
                },
                {
                    "date": "10/04/26",
                    "opponent": "MIA",
                    "home": True,
                    "result": "L",
                    "team_score": 117,
                    "opponent_score": 140,
                },
                {
                    "date": "12/04/26",
                    "opponent": "CLE",
                    "home": False,
                    "result": "L",
                    "team_score": 117,
                    "opponent_score": 130,
                },
            ],
            "upcoming_games": [
                {
                    "date": "21/10/26",
                    "opponent": "MIL",
                    "home": True,
                },
                {
                    "date": "23/10/26",
                    "opponent": "TOR",
                    "home": True,
                },
                {
                    "date": "24/10/26",
                    "opponent": "CHI",
                    "home": False,
                },
            ],
        }

    random.seed(hash(team_abbr))  # Reproductible par Ã©quipe

    # Calculer la probabilitÃ© de victoire Ã  partir du bilan
    total = wins + losses
    win_pct = wins / total if total > 0 else 0.5

    # Adversaires possibles (exclure l'Ã©quipe elle-mÃªme)
    opponents = [a for a in all_teams_abbrs if a != team_abbr]

    # --- 3 derniers matchs ---
    recent_games = []
    base_date = datetime(2026, 4, 15)  # Fin de saison
    for i in range(3):
        game_date = base_date - timedelta(days=(3 - i) * 2)
        opp = random.choice(opponents)
        is_home = random.random() > 0.5
        is_win = random.random() < win_pct

        # GÃ©nÃ©rer des scores rÃ©alistes NBA (90-130)
        team_score = random.randint(95, 125)
        opp_score = team_score + random.randint(-15, -1) if is_win else team_score + random.randint(1, 15)

        recent_games.append({
            "date": game_date.strftime("%d/%m/%y"),
            "opponent": opp,
            "home": is_home,
            "result": "W" if is_win else "L",
            "team_score": team_score,
            "opponent_score": opp_score,
        })

    # --- 3 prochains matchs ---
    upcoming_games = []
    next_date = datetime(2026, 10, 20)
    for i in range(3):
        game_date = next_date + timedelta(days=i * 2)
        opp = random.choice(opponents)
        is_home = random.random() > 0.5
        upcoming_games.append({
            "date": game_date.strftime("%d/%m/%y"),
            "opponent": opp,
            "home": is_home,
        })

    return {
        "recent_games": recent_games,
        "upcoming_games": upcoming_games,
    }


def generate_demo_data() -> list[dict]:
    """
    GÃ©nÃ¨re les donnÃ©es pour l'intersaison.
    - Classement rÃ©el figÃ© de la saison 2025-26
    - Past calendar : derniers matchs de la saison (via CDN)
    - Future calendar : premiers matchs de la prochaine saison (via CDN)
    Utilise seulement 2 appels API (standings + CDN schedule) => ultra rapide.
    """
    # --- 1. Fetch real standings (1 API call) ---
    logger.info("Fetching live standings for 2025-26...")
    live_standings = []
    try:
        live_standings = fetch_live_standings(season="2025-26")
        logger.info(f"Got {len(live_standings)} teams from live standings")
    except Exception as e:
        logger.error(f"Error fetching live standings: {e}")

    # --- 2. Fetch all schedules in bulk (1 API call) ---
    logger.info("Fetching bulk schedule from CDN...")
    all_schedules = {}
    try:
        all_schedules = fetch_all_schedules()
        logger.info(f"Got schedules for {len(all_schedules)} teams")
    except Exception as e:
        logger.error(f"Error fetching bulk schedules: {e}")

    demo_teams = [
        # (team_id, abbr, full_name, default_wins, default_losses, score, p1, p2, p3, p4)
        # Eastern Conference
        (1610612765, "DET", "Detroit Pistons", 60, 22, 8, 5, 5, 12, 10),
        (1610612738, "BOS", "Boston Celtics", 56, 26, 4, 3, 5, 5, 3),
        (1610612752, "NYK", "New York Knicks", 53, 29, 6, 5, 8, 5, 8),
        (1610612739, "CLE", "Cleveland Cavaliers", 52, 30, 12, 10, 15, 20, 5),
        (1610612761, "TOR", "Toronto Raptors", 46, 36, 32, 30, 35, 35, 25),
        (1610612737, "ATL", "Atlanta Hawks", 46, 36, 34, 35, 38, 35, 28),
        (1610612755, "PHI", "Philadelphia 76ers", 45, 37, 38, 42, 45, 28, 35),
        (1610612753, "ORL", "Orlando Magic", 45, 37, 24, 22, 18, 30, 25),
        (1610612766, "CHA", "Charlotte Hornets", 44, 38, 40, 40, 42, 45, 35),
        (1610612748, "MIA", "Miami Heat", 43, 39, 28, 30, 35, 15, 32),
        (1610612749, "MIL", "Milwaukee Bucks", 32, 50, 62, 60, 65, 55, 68),
        (1610612741, "CHI", "Chicago Bulls", 31, 51, 65, 65, 62, 60, 72),
        (1610612751, "BKN", "Brooklyn Nets", 20, 62, 78, 75, 80, 75, 82),
        (1610612754, "IND", "Indiana Pacers", 19, 63, 85, 82, 85, 88, 85),
        (1610612764, "WAS", "Washington Wizards", 17, 65, 92, 92, 85, 88, 90),

        # Western Conference
        (1610612760, "OKC", "Oklahoma City Thunder", 57, 25, 3, 2, 2, 8, 2),
        (1610612746, "LAC", "LA Clippers", 51, 31, 38, 42, 45, 28, 35),
        (1610612742, "DAL", "Dallas Mavericks", 50, 32, 14, 15, 18, 5, 18),
        (1610612740, "NOP", "New Orleans Pelicans", 49, 33, 18, 15, 18, 12, 28),
        (1610612756, "PHX", "Phoenix Suns", 49, 33, 15, 12, 10, 18, 20),
        (1610612743, "DEN", "Denver Nuggets", 48, 34, 8, 5, 10, 8, 10),
        (1610612747, "LAL", "Los Angeles Lakers", 47, 35, 25, 28, 22, 18, 30),
        (1610612750, "MIN", "Minnesota Timberwolves", 47, 35, 9, 8, 8, 10, 10),
        (1610612758, "SAC", "Sacramento Kings", 46, 36, 30, 32, 25, 38, 25),
        (1610612744, "GSW", "Golden State Warriors", 46, 36, 22, 18, 15, 55, 5),
        (1610612745, "HOU", "Houston Rockets", 41, 41, 35, 25, 28, 68, 20),
        (1610612762, "UTA", "Utah Jazz", 31, 51, 52, 40, 68, 55, 48),
        (1610612763, "MEM", "Memphis Grizzlies", 27, 55, 60, 48, 78, 72, 42),
        (1610612759, "SAS", "San Antonio Spurs", 22, 60, 68, 65, 72, 78, 58),
        (1610612757, "POR", "Portland Trail Blazers", 21, 61, 74, 70, 62, 90, 72),
    ]

    all_abbrs = [t[1] for t in demo_teams]

    # ConfÃ©rence de chaque Ã©quipe pour le classement
    east_teams = {"WAS", "BKN", "TOR", "CHA", "DET", "CHI", "PHI", "ATL",
                  "MIA", "IND", "ORL", "MIL", "NYK", "BOS", "CLE"}

    results = []
    for (tid, abbr, name, default_wins, default_losses, score, s1, s2, s3, s4) in demo_teams:
        # --- Override record with live standings ---
        wins = default_wins
        losses = default_losses
        conference = "East" if abbr in east_teams else "West"

        if live_standings:
            my_stand = next((s for s in live_standings if s.get("TeamID") == tid), None)
            if my_stand:
                wins = my_stand.get("WINS", wins)
                losses = my_stand.get("LOSSES", losses)
                conference = my_stand.get("Conference", conference)

        pct = wins / (wins + losses) if (wins + losses) > 0 else 0
        status_key, status_label = get_tanking_status(score)

        # --- Schedule from CDN bulk data ---
        team_sched = all_schedules.get(str(tid), {})
        recent_games = team_sched.get("recent_games", [])
        upcoming_games = team_sched.get("upcoming_games", [])

        # Fallback to demo schedule if CDN returned nothing
        if not recent_games or not upcoming_games:
            demo_sched = _generate_demo_schedule(abbr, wins, losses, all_abbrs)
            if not recent_games:
                recent_games = demo_sched["recent_games"]
            if not upcoming_games:
                upcoming_games = demo_sched["upcoming_games"]

        results.append({
            "team_id": tid,
            "team_name": name,
            "team_abbreviation": abbr,
            "tanking_score": score,
            "status": status_key,
            "status_label": status_label,
            "season": "2025-26",
            "last_updated": datetime.now().isoformat(),
            "conference": conference,
            "pillars": [
                {
                    "id": "vet_minutes",
                    "name": "Veteran Minutes Drop",
                    "icon": "â±ï¸",
                    "weight": 0.30,
                    "score": s1,
                    "weighted_score": round(s1 * 0.30, 1),
                    "description": (
                        "Significant drop in veteran playing time detected."
                        if s1 >= 70 else
                        "Veterans are playing fewer minutes than expected."
                        if s1 >= 40 else
                        "Veteran minutes are within normal range."
                    ),
                    "details": f"Veteran minutes score: {s1}/100.",
                    "data": {"score_raw": s1},
                },
                {
                    "id": "dnp_suspects",
                    "name": "DNP / Injury Suspects",
                    "icon": "ðŸ¥",
                    "weight": 0.20,
                    "score": s2,
                    "weighted_score": round(s2 * 0.20, 1),
                    "description": (
                        "Key players are missing a suspicious number of games."
                        if s2 >= 70 else
                        "Some key players have elevated absence rates."
                        if s2 >= 40 else
                        "Key player availability is within normal range."
                    ),
                    "details": f"DNP suspect score: {s2}/100.",
                    "data": {"score_raw": s2},
                },
                {
                    "id": "young_lineups",
                    "name": "Young Lineup Usage",
                    "icon": "ðŸ‘¶",
                    "weight": 0.25,
                    "score": s3,
                    "weighted_score": round(s3 * 0.25, 1),
                    "description": (
                        "Lineup is very young - heavy youth development focus."
                        if s3 >= 70 else
                        "Team is trending younger than the league average."
                        if s3 >= 40 else
                        "Team age profile is within normal NBA range."
                    ),
                    "details": f"Youth lineup score: {s3}/100.",
                    "data": {"score_raw": s3},
                },
                {
                    "id": "clutch_collapse",
                    "name": "Clutch Collapse (Q4)",
                    "icon": "ðŸ“‰",
                    "weight": 0.25,
                    "score": s4,
                    "weighted_score": round(s4 * 0.25, 1),
                    "description": (
                        "Significant 4th quarter collapse detected."
                        if s4 >= 70 else
                        "Team performance dips noticeably in 4th quarters."
                        if s4 >= 40 else
                        "4th quarter performance is consistent with overall play."
                    ),
                    "details": f"Clutch collapse score: {s4}/100.",
                    "data": {"score_raw": s4},
                },
            ],
            "record": {
                "wins": wins,
                "losses": losses,
                "pct": round(pct, 3),
            },
            "recent_games": recent_games,
            "upcoming_games": upcoming_games,
        })

    # Trier par tanking score dÃ©croissant
    results.sort(key=lambda x: -x["tanking_score"])

    # Calculer le classement par confÃ©rence (basÃ© sur le win %)
    east_sorted = sorted(
        [r for r in results if r["conference"] == "East"],
        key=lambda x: -x["record"]["pct"]
    )
    west_sorted = sorted(
        [r for r in results if r["conference"] == "West"],
        key=lambda x: -x["record"]["pct"]
    )

    for i, r in enumerate(east_sorted):
        r["standings_rank"] = i + 1
        r["standings_total"] = len(east_sorted)

    for i, r in enumerate(west_sorted):
        r["standings_rank"] = i + 1
        r["standings_total"] = len(west_sorted)

    return results
