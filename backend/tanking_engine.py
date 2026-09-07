"""
tanking_engine.py - Moteur de calcul du Tanking Score.

Score composite de 0 à 100 basé sur 4 piliers :
  1. Vet Minutes Drop (30%)   - Chute du temps de jeu des vétérans
  2. DNP / Injury Suspects (20%) - Absences suspectes des joueurs clés
  3. Young Lineup Usage (25%)  - Rajeunissement des lineups
  4. Clutch Collapse Q4 (25%) - Effondrement au 4e quart-temps
"""

import logging
from datetime import datetime

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
    """Extrait l'âge d'un joueur depuis les données du roster."""
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
    Compare les minutes des vétérans (≥28 ans) avec l'ensemble de l'équipe.
    Regarde si les vétérans jouent anormalement peu par rapport à leur potentiel.
    
    Signal fort : les meilleurs joueurs de l'équipe jouent peu de minutes.
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

    # Trouver les vétérans dans les stats de l'équipe
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

    # Moyenne des minutes des vétérans
    vet_avg_min = sum(v["minutes"] for v in vet_stats) / len(vet_stats)

    # Le ratio vet_minutes / team_avg est un indicateur
    # Si les vétérans jouent moins que la moyenne → signal de tanking
    ratio = vet_avg_min / team_avg_min if team_avg_min > 0 else 1.0

    # Normalement, les vétérans jouent PLUS que la moyenne (ratio > 1.0).
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

    # Bonus : si un vétéran de qualité joue < 20 min
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
    Détecte les absences suspectes des joueurs clés.
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

    # Calculer le ratio de matchs manqués par les top joueurs
    total_missed = 0
    player_details = []

    for p in top_players:
        gp = int(p.get("GP", 0))
        name = p.get("PLAYER_NAME", "Unknown")
        pts = float(p.get("PTS", 0))
        missed = team_games - gp

        # Ratio de matchs manqués (0 = a tout joué, 1 = n'a rien joué)
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

    # Barème :
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
    Mesure l'âge moyen pondéré par les minutes jouées.
    Si l'équipe est anormalement jeune pondérée par minutes, c'est un signe
    de développement de jeunes / tanking.
    """
    if not roster or not player_stats:
        return {
            "score": 0,
            "description": "Insufficient data for lineup age analysis.",
            "details": "No roster or stats data available.",
            "data": {},
        }

    # Construire un mapping player_id → age
    age_map = {}
    for p in roster:
        pid = p.get("PLAYER_ID") or p.get("player_id")
        age = _get_player_age(p)
        if pid and age:
            age_map[int(pid)] = age

    # Calculer l'âge moyen pondéré par les minutes
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

    # L'âge moyen pondéré de la NBA est environ 26-27 ans.
    # < 24 : très jeune (développement / tanking)
    # 24-25 : jeune
    # 25-27 : normal
    # > 27 : expérimenté
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
    Les équipes qui tankent ont tendance à perdre les matchs serrés en
    fin de rencontre (effondrement volontaire ou non).
    """
    if not full_game_stats or not q4_stats:
        return {
            "score": 0,
            "description": "Insufficient data for clutch analysis.",
            "details": "No quarter-by-quarter stats available.",
            "data": {},
        }

    # Trouver les stats de notre équipe
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

    # Le différentiel : si Q4 est bien pire que le reste → tanking
    differential = q4_net - full_net

    # Barème :
    # diff > 0 : Q4 meilleur que le reste (clutch!) → pas de tanking
    # diff 0 à -3 : normal
    # diff -3 à -6 : suspect
    # diff -6 à -10 : signal fort
    # diff < -10 : très fort
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

    # Bonus si le Net Rating Q4 est très négatif en absolu
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
    Calcule le Tanking Score composite pour une équipe.
    Retourne un dictionnaire complet avec le score, le statut et les détails
    de chaque pilier.
    """
    # Estimer le nombre de matchs joués par l'équipe
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

    # Score composite pondéré
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
            "icon": "⏱️",
            "weight": WEIGHTS["vet_minutes"],
            "score": p1["score"],
            "weighted_score": round(p1["score"] * WEIGHTS["vet_minutes"], 1),
            **p1,
        },
        {
            "id": "dnp_suspects",
            "name": "DNP / Injury Suspects",
            "icon": "🏥",
            "weight": WEIGHTS["dnp_suspects"],
            "score": p2["score"],
            "weighted_score": round(p2["score"] * WEIGHTS["dnp_suspects"], 1),
            **p2,
        },
        {
            "id": "young_lineups",
            "name": "Young Lineup Usage",
            "icon": "👶",
            "weight": WEIGHTS["young_lineups"],
            "score": p3["score"],
            "weighted_score": round(p3["score"] * WEIGHTS["young_lineups"], 1),
            **p3,
        },
        {
            "id": "clutch_collapse",
            "name": "Clutch Collapse (Q4)",
            "icon": "📉",
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
# Données de démo (simulées pour la saison 2024-25)
# ---------------------------------------------------------------------------

def generate_demo_data() -> list[dict]:
    """
    Génère des données de démo réalistes basées sur la saison 2024-25.
    Utilisé quand l'API nba_api n'est pas disponible (hors saison, etc.).
    """
    demo_teams = [
        # (team_id, abbr, full_name, wins, losses, score, p1, p2, p3, p4)
        (1610612764, "WAS", "Washington Wizards", 19, 63, 89, 92, 85, 88, 90),
        (1610612751, "BKN", "Brooklyn Nets", 22, 60, 80, 82, 78, 85, 74),
        (1610612757, "POR", "Portland Trail Blazers", 24, 58, 74, 70, 62, 90, 72),
        (1610612761, "TOR", "Toronto Raptors", 25, 57, 68, 65, 72, 78, 58),
        (1610612762, "UTA", "Utah Jazz", 27, 55, 64, 58, 55, 82, 60),
        (1610612766, "CHA", "Charlotte Hornets", 26, 56, 60, 48, 78, 72, 42),
        (1610612740, "NOP", "New Orleans Pelicans", 29, 53, 52, 40, 68, 55, 48),
        (1610612765, "DET", "Detroit Pistons", 30, 52, 48, 38, 42, 75, 38),
        (1610612741, "CHI", "Chicago Bulls", 31, 51, 42, 45, 38, 45, 40),
        (1610612755, "PHI", "Philadelphia 76ers", 28, 54, 45, 35, 72, 30, 42),
        (1610612759, "SAS", "San Antonio Spurs", 34, 48, 35, 25, 28, 68, 20),
        (1610612737, "ATL", "Atlanta Hawks", 36, 46, 30, 32, 25, 38, 25),
        (1610612745, "HOU", "Houston Rockets", 41, 41, 22, 18, 15, 55, 5),
        (1610612747, "LAL", "Los Angeles Lakers", 38, 44, 28, 30, 35, 15, 32),
        (1610612746, "LAC", "LA Clippers", 33, 49, 38, 42, 45, 28, 35),
        (1610612744, "GSW", "Golden State Warriors", 39, 43, 25, 28, 22, 18, 30),
        (1610612758, "SAC", "Sacramento Kings", 37, 45, 24, 22, 18, 30, 25),
        (1610612763, "MEM", "Memphis Grizzlies", 40, 42, 20, 15, 28, 22, 15),
        (1610612748, "MIA", "Miami Heat", 40, 42, 18, 15, 18, 12, 28),
        (1610612754, "IND", "Indiana Pacers", 43, 39, 15, 12, 10, 18, 20),
        (1610612756, "PHX", "Phoenix Suns", 42, 40, 16, 18, 15, 10, 22),
        (1610612753, "ORL", "Orlando Magic", 44, 38, 12, 10, 15, 20, 5),
        (1610612749, "MIL", "Milwaukee Bucks", 44, 38, 14, 15, 18, 5, 18),
        (1610612742, "DAL", "Dallas Mavericks", 46, 36, 10, 8, 12, 8, 12),
        (1610612743, "DEN", "Denver Nuggets", 48, 34, 8, 5, 10, 8, 10),
        (1610612750, "MIN", "Minnesota Timberwolves", 47, 35, 9, 8, 8, 10, 10),
        (1610612752, "NYK", "New York Knicks", 50, 32, 6, 5, 8, 5, 8),
        (1610612738, "BOS", "Boston Celtics", 52, 30, 4, 3, 5, 5, 3),
        (1610612760, "OKC", "Oklahoma City Thunder", 57, 25, 3, 2, 2, 8, 2),
        (1610612739, "CLE", "Cleveland Cavaliers", 55, 27, 5, 3, 5, 5, 5),
    ]

    results = []
    for (tid, abbr, name, wins, losses, score, s1, s2, s3, s4) in demo_teams:
        pct = wins / (wins + losses) if (wins + losses) > 0 else 0
        status_key, status_label = get_tanking_status(score)

        results.append({
            "team_id": tid,
            "team_name": name,
            "team_abbreviation": abbr,
            "tanking_score": score,
            "status": status_key,
            "status_label": status_label,
            "season": "2024-25",
            "last_updated": datetime.now().isoformat(),
            "pillars": [
                {
                    "id": "vet_minutes",
                    "name": "Veteran Minutes Drop",
                    "icon": "⏱️",
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
                    "icon": "🏥",
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
                    "icon": "👶",
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
                    "icon": "📉",
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
        })

    return sorted(results, key=lambda x: -x["tanking_score"])
