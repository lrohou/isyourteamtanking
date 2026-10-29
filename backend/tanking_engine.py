"""Calcul du Tanking Score à partir de statistiques NBA live."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)
WEIGHTS = {"vet_minutes": 0.30, "dnp_suspects": 0.20, "young_lineups": 0.25, "clutch_collapse": 0.25}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_player_age(player: dict) -> float | None:
    if player.get("AGE"):
        return _number(player["AGE"], None)
    birth_date = player.get("BIRTH_DATE")
    if not birth_date:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return (datetime.now() - datetime.strptime(str(birth_date), fmt)).days / 365.25
        except ValueError:
            continue
    return None


def calc_vet_minutes_drop(roster, player_stats):
    veteran_ids = {int(p.get("PLAYER_ID") or p.get("player_id")) for p in roster if _get_player_age(p) and _get_player_age(p) >= 28 and (p.get("PLAYER_ID") or p.get("player_id"))}
    valid = [p for p in player_stats if _number(p.get("GP")) >= 5]
    veterans = [p for p in valid if _number(p.get("PLAYER_ID") or p.get("player_id")) in veteran_ids]
    if not valid or not veterans:
        return {"score": 0, "description": "Insufficient data to evaluate veteran minutes.", "details": "No live veteran minutes data available.", "data": {}}
    team_average = sum(_number(p.get("MIN")) for p in valid) / len(valid)
    veteran_average = sum(_number(p.get("MIN")) for p in veterans) / len(veterans)
    ratio = veteran_average / team_average if team_average else 1
    score = 0 if ratio >= 1.1 else 15 if ratio >= .9 else 40 if ratio >= .75 else 65 if ratio >= .6 else 90
    low_minutes = sum(1 for p in veterans if _number(p.get("MIN")) < 20)
    score = _clamp(score + (15 if low_minutes >= 3 else 8 if low_minutes >= 2 else 0))
    return {"score": round(score), "description": "Veterans are playing fewer minutes than expected." if score >= 40 else "Veteran minutes are within normal range.", "details": f"Veterans average {veteran_average:.1f} min/game vs team average {team_average:.1f} min/game.", "data": {"vet_avg_minutes": round(veteran_average, 1), "team_avg_minutes": round(team_average, 1), "ratio": round(ratio, 2), "low_minute_vets": low_minutes}}


def calc_dnp_suspects(roster, player_stats, team_games=82):
    players = sorted([p for p in player_stats if _number(p.get("GP")) > 0], key=lambda p: _number(p.get("PTS")), reverse=True)[:5]
    if not players or not team_games:
        return {"score": 0, "description": "Insufficient data for DNP analysis.", "details": "No live player availability data available.", "data": {}}
    details = []
    for player in players:
        games_played = int(_number(player.get("GP")))
        missed = max(0, team_games - games_played)
        details.append({"name": player.get("PLAYER_NAME", "Unknown"), "games_played": games_played, "games_missed": missed, "miss_ratio": round(missed / team_games, 2), "ppg": round(_number(player.get("PTS")), 1)})
    average = sum(p["miss_ratio"] for p in details) / len(details)
    score = 5 if average < .10 else 25 if average < .20 else 55 if average < .35 else 78 if average < .50 else 95
    return {"score": score, "description": "Key players are missing a suspicious number of games." if score >= 70 else "Some key players have elevated absence rates." if score >= 40 else "Key player availability is within normal range.", "details": "; ".join(f"{p['name']} missed {p['games_missed']} games" for p in details[:3]), "data": {"avg_miss_ratio": round(average, 2), "top_players": details}}


def calc_young_lineup_usage(roster, player_stats, win_pct=0.0):
    ages = {int(p.get("PLAYER_ID") or p.get("player_id")): _get_player_age(p) for p in roster if (p.get("PLAYER_ID") or p.get("player_id")) and _get_player_age(p) is not None}
    weighted = [(ages.get(int(p.get("PLAYER_ID") or p.get("player_id"))), _number(p.get("MIN")) * _number(p.get("GP")), p) for p in player_stats if (p.get("PLAYER_ID") or p.get("player_id")) and _number(p.get("GP")) >= 5 and _number(p.get("MIN")) > 0 and int(p.get("PLAYER_ID") or p.get("player_id")) in ages]
    if not weighted:
        return {"score": 0, "description": "Insufficient data for lineup age analysis.", "details": "No live roster age data available.", "data": {}}
    average = sum(age * minutes for age, minutes, _ in weighted) / sum(minutes for _, minutes, _ in weighted)
    score = 0 if average >= 27.5 else 10 if average >= 26.5 else 25 if average >= 25.5 else 50 if average >= 24.5 else 72 if average >= 23.5 else 92
    young = sum(1 for age, _, player in weighted if age < 23 and _number(player.get("MIN")) > 25)
    score = min(100, score + (12 if young >= 3 else 6 if young >= 2 else 0))
    if win_pct >= .40:
        score *= 1 - min(1, (win_pct - .40) / .20)
    return {"score": round(_clamp(score)), "description": "Team age profile is within normal NBA range." if score < 40 else "Team is trending younger than the league average.", "details": f"Minutes-weighted average age: {average:.1f} years.", "data": {"weighted_avg_age": round(average, 1), "young_starters": young}}


def calc_clutch_collapse(team_id, full_game_stats, q4_stats):
    full = next((row for row in full_game_stats if int(row.get("TEAM_ID") or row.get("team_id")) == team_id), None)
    q4 = next((row for row in q4_stats if int(row.get("TEAM_ID") or row.get("team_id")) == team_id), None)
    if not full or not q4:
        return {"score": 0, "description": "Insufficient data for clutch analysis.", "details": "No live quarter statistics available.", "data": {}}
    full_net, q4_net = _number(full.get("NET_RATING")), _number(q4.get("NET_RATING"))
    difference = q4_net - full_net
    score = 0 if difference >= 0 else 10 if difference >= -2 else 30 if difference >= -4 else 55 if difference >= -6 else 78 if difference >= -9 else 95
    score = min(100, score + (10 if q4_net < -10 else 5 if q4_net < -7 else 0))
    return {"score": round(_clamp(score)), "description": "Significant 4th quarter collapse detected." if score >= 70 else "Team performance dips noticeably in 4th quarters." if score >= 40 else "4th quarter performance is consistent with overall play.", "details": f"Overall Net Rating: {full_net:+.1f} | Q4 Net Rating: {q4_net:+.1f} | Differential: {difference:+.1f}.", "data": {"full_game_net_rating": round(full_net, 1), "q4_net_rating": round(q4_net, 1), "differential": round(difference, 1)}}


def get_tanking_status(score):
    return ("hard_tanking", "Hard Tanking Detected!") if score >= 66 else ("soft_tanking", "Soft Tanking / Gray Zone") if score >= 31 else ("competing", "Actively Competing")


def compute_badges_and_suspects(tanking_score, pillars, team_abbr, team_name):
    pillar_map = {pillar.get("id"): pillar.get("score", 0) for pillar in pillars}
    badges = []
    if tanking_score >= 85:
        badges.append({"id": "trust_the_process", "name": "Trust The Process Award", "type": "shame", "highlight": f"Score global {tanking_score}%"})
    if pillar_map.get("dnp_suspects", 0) >= 80:
        badges.append({"id": "phantom_injury", "name": "Phantom Injury Ward", "type": "shame", "highlight": f"DNP Suspects : {pillar_map['dnp_suspects']}%"})
    if pillar_map.get("clutch_collapse", 0) >= 70:
        badges.append({"id": "brick_city", "name": "Brick City / Q4 Melt", "type": "shame", "highlight": f"Sabotage Q4 : {pillar_map['clutch_collapse']}%"})
    if pillar_map.get("young_lineups", 0) >= 70:
        badges.append({"id": "daycare_lineup", "name": "Daycare Lineup", "type": "shame", "highlight": f"Score Jeunesse : {pillar_map['young_lineups']}%"})
    if not badges:
        badges.append({"id": "anti_tank" if tanking_score <= 25 else "limbo_alert", "name": "Anti-Tank Division" if tanking_score <= 25 else "Limbo Alert", "type": "honor" if tanking_score <= 25 else "neutral", "highlight": f"Tanking score {tanking_score}%"})
    players = pillars[1].get("data", {}).get("top_players", []) if len(pillars) > 1 else []
    suspects = [{"name": p.get("name", "Unknown"), "status": "AVAILABILITY_SIGNAL" if p.get("games_missed") else "ACTIVE", "status_code": "availability_signal" if p.get("games_missed") else "active", "reason": "Games missed in current season", "games_missed": p.get("games_missed", 0), "suspicion_level": round(p.get("miss_ratio", 0) * 100)} for p in players]
    suspicion = round(sum(p["suspicion_level"] for p in suspects) / len(suspects)) if suspects else 0
    return {"badges": badges, "suspect_tracker": {"team_abbreviation": team_abbr, "team_name": team_name, "overall_suspicion": suspicion, "players": suspects}}


def calculate_tanking_score(team_id, team_name, team_abbreviation, roster, player_stats, full_game_stats, q4_stats, team_record=None, season=""):
    record = team_record or {"wins": 0, "losses": 0, "pct": 0}
    games = record.get("wins", 0) + record.get("losses", 0) or 82
    calculated = [
        ("vet_minutes", "Veteran Minutes Drop", calc_vet_minutes_drop(roster, player_stats)),
        ("dnp_suspects", "DNP / Injury Suspects", calc_dnp_suspects(roster, player_stats, games)),
        ("young_lineups", "Young Lineup Usage", calc_young_lineup_usage(roster, player_stats, record.get("pct", 0))),
        ("clutch_collapse", "Clutch Collapse (Q4)", calc_clutch_collapse(team_id, full_game_stats, q4_stats)),
    ]
    pillars = [{"id": key, "name": name, "weight": WEIGHTS[key], **value, "weighted_score": round(value["score"] * WEIGHTS[key], 1)} for key, name, value in calculated]
    score = round(_clamp(sum(p["score"] * WEIGHTS[p["id"]] for p in pillars)))
    status, label = get_tanking_status(score)
    return {"team_id": team_id, "team_name": team_name, "team_abbreviation": team_abbreviation, "tanking_score": score, "status": status, "status_label": label, "season": season, "last_updated": datetime.now().isoformat(), "pillars": pillars, **compute_badges_and_suspects(score, pillars, team_abbreviation, team_name), "record": record}
