/**
 * Static data for all 30 NBA teams.
 * Colors sourced from official NBA brand guidelines.
 * Team IDs match stats.nba.com identifiers.
 */
const NBA_TEAMS = [
  {
    id: 1610612737, abbreviation: "ATL", name: "Hawks", city: "Atlanta", fullName: "Atlanta Hawks",
    conference: "East", division: "Southeast",
    colors: { primary: "#E03A3E", secondary: "#C1D32F", bg: "#1a0a0a" },
    logo: "https://cdn.nba.com/logos/nba/1610612737/primary/L/logo.svg"
  },
  {
    id: 1610612738, abbreviation: "BOS", name: "Celtics", city: "Boston", fullName: "Boston Celtics",
    conference: "East", division: "Atlantic",
    colors: { primary: "#007A33", secondary: "#BA9653", bg: "#0a1a0f" },
    logo: "https://cdn.nba.com/logos/nba/1610612738/primary/L/logo.svg"
  },
  {
    id: 1610612751, abbreviation: "BKN", name: "Nets", city: "Brooklyn", fullName: "Brooklyn Nets",
    conference: "East", division: "Atlantic",
    colors: { primary: "#000000", secondary: "#FFFFFF", bg: "#0a0a0a" },
    logo: "https://cdn.nba.com/logos/nba/1610612751/primary/L/logo.svg"
  },
  {
    id: 1610612766, abbreviation: "CHA", name: "Hornets", city: "Charlotte", fullName: "Charlotte Hornets",
    conference: "East", division: "Southeast",
    colors: { primary: "#1D1160", secondary: "#00788C", bg: "#0a0a1a" },
    logo: "https://cdn.nba.com/logos/nba/1610612766/primary/L/logo.svg"
  },
  {
    id: 1610612741, abbreviation: "CHI", name: "Bulls", city: "Chicago", fullName: "Chicago Bulls",
    conference: "East", division: "Central",
    colors: { primary: "#CE1141", secondary: "#000000", bg: "#1a0a0e" },
    logo: "https://cdn.nba.com/logos/nba/1610612741/primary/L/logo.svg"
  },
  {
    id: 1610612739, abbreviation: "CLE", name: "Cavaliers", city: "Cleveland", fullName: "Cleveland Cavaliers",
    conference: "East", division: "Central",
    colors: { primary: "#6F263D", secondary: "#FFB81C", bg: "#140a10" },
    logo: "https://cdn.nba.com/logos/nba/1610612739/primary/L/logo.svg"
  },
  {
    id: 1610612742, abbreviation: "DAL", name: "Mavericks", city: "Dallas", fullName: "Dallas Mavericks",
    conference: "West", division: "Southwest",
    colors: { primary: "#00538C", secondary: "#002B5E", bg: "#0a0f1a" },
    logo: "https://cdn.nba.com/logos/nba/1610612742/primary/L/logo.svg"
  },
  {
    id: 1610612743, abbreviation: "DEN", name: "Nuggets", city: "Denver", fullName: "Denver Nuggets",
    conference: "West", division: "Northwest",
    colors: { primary: "#0E2240", secondary: "#FEC524", bg: "#0a0e1a" },
    logo: "https://cdn.nba.com/logos/nba/1610612743/primary/L/logo.svg"
  },
  {
    id: 1610612765, abbreviation: "DET", name: "Pistons", city: "Detroit", fullName: "Detroit Pistons",
    conference: "East", division: "Central",
    colors: { primary: "#C8102E", secondary: "#1D42BA", bg: "#1a0a0e" },
    logo: "https://cdn.nba.com/logos/nba/1610612765/primary/L/logo.svg"
  },
  {
    id: 1610612744, abbreviation: "GSW", name: "Warriors", city: "Golden State", fullName: "Golden State Warriors",
    conference: "West", division: "Pacific",
    colors: { primary: "#1D428A", secondary: "#FFC72C", bg: "#0a0e1a" },
    logo: "https://cdn.nba.com/logos/nba/1610612744/primary/L/logo.svg"
  },
  {
    id: 1610612745, abbreviation: "HOU", name: "Rockets", city: "Houston", fullName: "Houston Rockets",
    conference: "West", division: "Southwest",
    colors: { primary: "#CE1141", secondary: "#000000", bg: "#1a0a0e" },
    logo: "https://cdn.nba.com/logos/nba/1610612745/primary/L/logo.svg"
  },
  {
    id: 1610612754, abbreviation: "IND", name: "Pacers", city: "Indiana", fullName: "Indiana Pacers",
    conference: "East", division: "Central",
    colors: { primary: "#002D62", secondary: "#FDBB30", bg: "#0a0e1a" },
    logo: "https://cdn.nba.com/logos/nba/1610612754/primary/L/logo.svg"
  },
  {
    id: 1610612746, abbreviation: "LAC", name: "Clippers", city: "LA", fullName: "LA Clippers",
    conference: "West", division: "Pacific",
    colors: { primary: "#C8102E", secondary: "#1D428A", bg: "#1a0a0e" },
    logo: "https://cdn.nba.com/logos/nba/1610612746/primary/L/logo.svg"
  },
  {
    id: 1610612747, abbreviation: "LAL", name: "Lakers", city: "Los Angeles", fullName: "Los Angeles Lakers",
    conference: "West", division: "Pacific",
    colors: { primary: "#552583", secondary: "#FDB927", bg: "#120a1a" },
    logo: "https://cdn.nba.com/logos/nba/1610612747/primary/L/logo.svg"
  },
  {
    id: 1610612763, abbreviation: "MEM", name: "Grizzlies", city: "Memphis", fullName: "Memphis Grizzlies",
    conference: "West", division: "Southwest",
    colors: { primary: "#5D76A9", secondary: "#12173F", bg: "#0e101a" },
    logo: "https://cdn.nba.com/logos/nba/1610612763/primary/L/logo.svg"
  },
  {
    id: 1610612748, abbreviation: "MIA", name: "Heat", city: "Miami", fullName: "Miami Heat",
    conference: "East", division: "Southeast",
    colors: { primary: "#98002E", secondary: "#F9A01B", bg: "#1a0a10" },
    logo: "https://cdn.nba.com/logos/nba/1610612748/primary/L/logo.svg"
  },
  {
    id: 1610612749, abbreviation: "MIL", name: "Bucks", city: "Milwaukee", fullName: "Milwaukee Bucks",
    conference: "East", division: "Central",
    colors: { primary: "#00471B", secondary: "#EEE1C6", bg: "#0a140e" },
    logo: "https://cdn.nba.com/logos/nba/1610612749/primary/L/logo.svg"
  },
  {
    id: 1610612750, abbreviation: "MIN", name: "Timberwolves", city: "Minnesota", fullName: "Minnesota Timberwolves",
    conference: "West", division: "Northwest",
    colors: { primary: "#0C2340", secondary: "#236192", bg: "#0a0e14" },
    logo: "https://cdn.nba.com/logos/nba/1610612750/primary/L/logo.svg"
  },
  {
    id: 1610612740, abbreviation: "NOP", name: "Pelicans", city: "New Orleans", fullName: "New Orleans Pelicans",
    conference: "West", division: "Southwest",
    colors: { primary: "#0C2340", secondary: "#C8102E", bg: "#0a0e14" },
    logo: "https://cdn.nba.com/logos/nba/1610612740/primary/L/logo.svg"
  },
  {
    id: 1610612752, abbreviation: "NYK", name: "Knicks", city: "New York", fullName: "New York Knicks",
    conference: "East", division: "Atlantic",
    colors: { primary: "#006BB6", secondary: "#F58426", bg: "#0a101a" },
    logo: "https://cdn.nba.com/logos/nba/1610612752/primary/L/logo.svg"
  },
  {
    id: 1610612760, abbreviation: "OKC", name: "Thunder", city: "Oklahoma City", fullName: "Oklahoma City Thunder",
    conference: "West", division: "Northwest",
    colors: { primary: "#007AC1", secondary: "#EF6020", bg: "#0a101a" },
    logo: "https://cdn.nba.com/logos/nba/1610612760/primary/L/logo.svg"
  },
  {
    id: 1610612753, abbreviation: "ORL", name: "Magic", city: "Orlando", fullName: "Orlando Magic",
    conference: "East", division: "Southeast",
    colors: { primary: "#0077C0", secondary: "#C4CED4", bg: "#0a101a" },
    logo: "https://cdn.nba.com/logos/nba/1610612753/primary/L/logo.svg"
  },
  {
    id: 1610612755, abbreviation: "PHI", name: "76ers", city: "Philadelphia", fullName: "Philadelphia 76ers",
    conference: "East", division: "Atlantic",
    colors: { primary: "#006BB6", secondary: "#ED174C", bg: "#0a101a" },
    logo: "https://cdn.nba.com/logos/nba/1610612755/primary/L/logo.svg"
  },
  {
    id: 1610612756, abbreviation: "PHX", name: "Suns", city: "Phoenix", fullName: "Phoenix Suns",
    conference: "West", division: "Pacific",
    colors: { primary: "#1D1160", secondary: "#E56020", bg: "#0a0a14" },
    logo: "https://cdn.nba.com/logos/nba/1610612756/primary/L/logo.svg"
  },
  {
    id: 1610612757, abbreviation: "POR", name: "Trail Blazers", city: "Portland", fullName: "Portland Trail Blazers",
    conference: "West", division: "Northwest",
    colors: { primary: "#E03A3E", secondary: "#000000", bg: "#1a0a0a" },
    logo: "https://cdn.nba.com/logos/nba/1610612757/primary/L/logo.svg"
  },
  {
    id: 1610612758, abbreviation: "SAC", name: "Kings", city: "Sacramento", fullName: "Sacramento Kings",
    conference: "West", division: "Pacific",
    colors: { primary: "#5A2D81", secondary: "#63727A", bg: "#120a18" },
    logo: "https://cdn.nba.com/logos/nba/1610612758/primary/L/logo.svg"
  },
  {
    id: 1610612759, abbreviation: "SAS", name: "Spurs", city: "San Antonio", fullName: "San Antonio Spurs",
    conference: "West", division: "Southwest",
    colors: { primary: "#C4CED4", secondary: "#000000", bg: "#101214" },
    logo: "https://cdn.nba.com/logos/nba/1610612759/primary/L/logo.svg"
  },
  {
    id: 1610612761, abbreviation: "TOR", name: "Raptors", city: "Toronto", fullName: "Toronto Raptors",
    conference: "East", division: "Atlantic",
    colors: { primary: "#CE1141", secondary: "#000000", bg: "#1a0a0e" },
    logo: "https://cdn.nba.com/logos/nba/1610612761/primary/L/logo.svg"
  },
  {
    id: 1610612762, abbreviation: "UTA", name: "Jazz", city: "Utah", fullName: "Utah Jazz",
    conference: "West", division: "Northwest",
    colors: { primary: "#002B5C", secondary: "#00471B", bg: "#0a0e14" },
    logo: "https://cdn.nba.com/logos/nba/1610612762/primary/L/logo.svg"
  },
  {
    id: 1610612764, abbreviation: "WAS", name: "Wizards", city: "Washington", fullName: "Washington Wizards",
    conference: "East", division: "Southeast",
    colors: { primary: "#002B5C", secondary: "#E31837", bg: "#0a0e14" },
    logo: "https://cdn.nba.com/logos/nba/1610612764/primary/L/logo.svg"
  }
];

/**
 * Utility: find a team by ID, abbreviation, or partial name match.
 */
function findTeam(query) {
  if (!query) return null;
  const q = query.toString().toLowerCase().trim();
  
  // 1. Exact match on ID or abbreviation
  let team = NBA_TEAMS.find(
    (t) => t.id.toString() === q || t.abbreviation.toLowerCase() === q
  );
  if (team) return team;

  // 2. Exact match on full name, city, or team name
  team = NBA_TEAMS.find(
    (t) =>
      t.fullName.toLowerCase() === q ||
      t.city.toLowerCase() === q ||
      t.name.toLowerCase() === q
  );
  if (team) return team;

  // 3. Partial match on full name, city, or team name
  return NBA_TEAMS.find(
    (t) =>
      t.fullName.toLowerCase().includes(q) ||
      t.city.toLowerCase().includes(q) ||
      t.name.toLowerCase().includes(q)
  );
}

/**
 * Returns teams matching a partial search string (for autocomplete).
 */
function searchTeams(query) {
  if (!query || query.length < 1) return [...NBA_TEAMS];
  const q = query.toLowerCase().trim();

  // If query matches an abbreviation exactly, prioritize that team at top of list
  const exactAbbr = NBA_TEAMS.find((t) => t.abbreviation.toLowerCase() === q);
  const matches = NBA_TEAMS.filter(
    (t) =>
      t.fullName.toLowerCase().includes(q) ||
      t.city.toLowerCase().includes(q) ||
      t.name.toLowerCase().includes(q) ||
      t.abbreviation.toLowerCase().includes(q)
  );

  if (exactAbbr && matches.includes(exactAbbr)) {
    return [exactAbbr, ...matches.filter((t) => t !== exactAbbr)];
  }
  return matches;
}
