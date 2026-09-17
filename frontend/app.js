/**
 * app.js - IsYourTeamTanking SPA Logic
 *
 * Fetches tanking data from the API, renders the gauge, pillars and rankings.
 */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const API_BASE = window.location.origin; // Same-origin when served by FastAPI
const GAUGE_RADIUS = 90;
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let allTeamResults = [];
let selectedTeam = null;
let autocompleteIndex = -1;
let rankingView = "conferences";
let rankingFilter = "all";
let rankingSort = "score";

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  await loadData();
  setupSearch();
  renderRankings();
  setupScrollToTop();
  setupHomeButton();
  setupLeagueControls();
  window.addEventListener("popstate", handleHistoryNavigation);
  openTeamFromUrl();
});

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function loadData() {
  showLoading(true);
  try {
    const res = await fetch(`${API_BASE}/api/tanking/all`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allTeamResults = await res.json();
  } catch (err) {
    console.error("Failed to fetch data:", err);
    showError("Could not load tanking data. Is the server running?");
  }
  showLoading(false);
}

function openTeamFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const queryAbbr = params.get("team");
  const hashValue = window.location.hash.replace(/^#/, "");
  const token = queryAbbr || (hashValue && !hashValue.startsWith("team-") ? hashValue : "");
  if (!token) return;

  const result = allTeamResults.find((team) =>
    team.team_abbreviation?.toLowerCase() === token.toLowerCase()
  );
  if (result) selectTeam(result.team_id, { updateHistory: false });
}

function showLoading(on) {
  const el = $("#loading");
  if (el) el.style.display = on ? "flex" : "none";
}

function showError(msg) {
  const el = $("#error");
  if (el) {
    el.textContent = msg;
    el.style.display = "block";
  }
}

// ---------------------------------------------------------------------------
// Search / Autocomplete
// ---------------------------------------------------------------------------
function setupSearch() {
  const input = $("#search-input");
  const list = $("#autocomplete-list");
  if (!input || !list) return;

  input.addEventListener("input", () => {
    const q = input.value.trim();
    autocompleteIndex = -1;
    if (q.length === 0) {
      renderAutocomplete(allTeamResults);
    } else {
      const matches = searchTeams(q).map((t) =>
        allTeamResults.find((r) => r.team_id === t.id)
      ).filter(Boolean);
      renderAutocomplete(matches);
    }
  });

  input.addEventListener("focus", () => {
    const q = input.value.trim();
    if (q.length === 0) {
      renderAutocomplete(allTeamResults);
    }
  });

  input.addEventListener("keydown", (e) => {
    const items = $$("#autocomplete-list .autocomplete-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      autocompleteIndex = Math.min(autocompleteIndex + 1, items.length - 1);
      updateAutocompleteActive(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      autocompleteIndex = Math.max(autocompleteIndex - 1, 0);
      updateAutocompleteActive(items);
    } else if (e.key === "Enter" && autocompleteIndex >= 0) {
      e.preventDefault();
      items[autocompleteIndex]?.click();
    } else if (e.key === "Escape") {
      hideAutocomplete();
    }
  });

  // Close autocomplete when clicking outside
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrapper")) {
      hideAutocomplete();
    }
  });
}

function renderAutocomplete(results) {
  const list = $("#autocomplete-list");
  if (!list) return;

  if (!results || results.length === 0) {
    list.innerHTML = `<div class="autocomplete-item" style="justify-content:center;color:var(--text-muted);">No teams found</div>`;
    list.classList.add("visible");
    return;
  }

  list.innerHTML = results
    .map((r) => {
      const team = findTeam(r.team_abbreviation);
      const logoUrl = team?.logo || "";
      const scoreClass = getScoreColorClass(r.tanking_score);
      const record = r.record ? `${r.record.wins}-${r.record.losses}` : "";
      return `
        <div class="autocomplete-item" data-team-id="${r.team_id}">
          <img class="autocomplete-item__logo" src="${logoUrl}" alt="${r.team_name}" loading="lazy" onerror="this.style.display='none'">
          <span class="autocomplete-item__name">${r.team_name}</span>
          <span class="autocomplete-item__record">${record}</span>
          <span class="autocomplete-item__score-badge badge-${scoreClass}">${r.tanking_score}%</span>
        </div>
      `;
    })
    .join("");

  list.classList.add("visible");

  // Attach click handlers
  list.querySelectorAll(".autocomplete-item[data-team-id]").forEach((item) => {
    item.addEventListener("click", () => {
      const teamId = parseInt(item.dataset.teamId, 10);
      selectTeam(teamId);
      hideAutocomplete();
    });
  });
}

function updateAutocompleteActive(items) {
  items.forEach((it, i) => {
    it.classList.toggle("active", i === autocompleteIndex);
  });
}

function hideAutocomplete() {
  const list = $("#autocomplete-list");
  if (list) list.classList.remove("visible");
  autocompleteIndex = -1;
}

// ---------------------------------------------------------------------------
// Team selection
// ---------------------------------------------------------------------------
function selectTeam(teamId, options = {}) {
  const result = allTeamResults.find((r) => r.team_id === teamId);
  if (!result) return;

  if (options.updateHistory !== false) {
    history.pushState({ teamId }, "", `?team=${encodeURIComponent(result.team_abbreviation)}`);
  }

  const input = $("#search-input");
  if (input) input.value = result.team_name;

  // UI state for selection
  const homeBtn = $("#home-btn");
  if (homeBtn) homeBtn.style.display = "inline-flex";

  const rankings = $(".rankings-section");
  if (rankings) rankings.style.display = "none";

  selectedTeam = result;
  renderResult(result);

  // Scroll to result
  const section = $(".result-section");
  if (section) {
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function handleHistoryNavigation() {
  const teamId = history.state?.teamId;
  if (teamId) {
    selectTeam(teamId, { updateHistory: false });
    return;
  }
  resetHomeView(false);
}

// ---------------------------------------------------------------------------
// Render Result Card
// ---------------------------------------------------------------------------
function renderResult(data) {
  const section = $(".result-section");
  if (!section) return;

  const team = findTeam(data.team_abbreviation);
  const logoUrl = team?.logo || "";
  const scoreColor = getScoreColor(data.tanking_score);
  const scoreClass = getScoreColorClass(data.tanking_score);
  const record = data.record
    ? `${data.record.wins}-${data.record.losses} (.${Math.round(data.record.pct * 1000)
      .toString()
      .padStart(3, "0")})`
    : "";

  // Standings info
  const standingsRank = data.standings_rank || "—";
  const standingsTotal = data.standings_total || 15;
  const conference = data.conference || "—";
  const badges = data.badges || [];
  const suspectTracker = data.suspect_tracker || { overall_suspicion: 0, players: [] };

  // Recent games HTML
  const recentGamesHtml = (data.recent_games || [])
    .map((g) => {
      const isWin = g.result === "W";
      const resultClass = isWin ? "game-win" : "game-loss";
      const oppTeam = findTeam(g.opponent);
      const oppLogo = oppTeam?.logo || "";
      const oppName = oppTeam?.fullName || g.opponent;
      const locationIcon = g.home ? "🏠" : "✈️";
      const link = g.game_id ? `href="https://www.nba.com/game/${g.game_id}" target="_blank"` : `href="https://www.nba.com/games" target="_blank"`;
      return `
        <a ${link} class="game-card ${resultClass}" style="text-decoration: none; color: inherit;">
          <div class="game-card__date">${g.date}</div>
          <div class="game-card__matchup">
            <img class="game-card__opp-logo" src="${oppLogo}" alt="${oppName}" onerror="this.style.display='none'" loading="lazy">
            <span class="game-card__opp-name">${g.opponent}</span>
            <span class="game-card__location" title="${g.home ? 'Home' : 'Away'}">${locationIcon}</span>
          </div>
          <div class="game-card__score">
            <span class="game-card__result-badge result-${g.result}">${g.result}</span>
            <span class="game-card__score-text">${g.team_score} - ${g.opponent_score}</span>
          </div>
        </a>
      `;
    })
    .join("");

  // Upcoming games HTML
  const upcomingGamesHtml = (data.upcoming_games || [])
    .map((g) => {
      const oppTeam = findTeam(g.opponent);
      const oppLogo = oppTeam?.logo || "";
      const oppName = oppTeam?.fullName || g.opponent;
      const locationIcon = g.home ? "🏠" : "✈️";
      const teamSlug = team?.name ? team.name.toLowerCase() : "games";
      const link = `href="https://www.nba.com/${teamSlug}/schedule" target="_blank"`;
      return `
        <a ${link} class="game-card game-upcoming" style="text-decoration: none; color: inherit;">
          <div class="game-card__date">${g.date}</div>
          <div class="game-card__matchup">
            <img class="game-card__opp-logo" src="${oppLogo}" alt="${oppName}" onerror="this.style.display='none'" loading="lazy">
            <span class="game-card__opp-name">${g.opponent}</span>
            <span class="game-card__location" title="${g.home ? 'Home' : 'Away'}">${locationIcon}</span>
          </div>
          <div class="game-card__vs">${g.home ? "vs" : "@"}</div>
        </a>
      `;
    })
    .join("");

  section.innerHTML = `
    <div class="result-card">
      <div class="result-card__header">
        <img class="result-card__logo" src="${logoUrl}" alt="${data.team_name}" onerror="this.style.display='none'">
        <div class="result-card__team-info">
          <h2 class="result-card__team-name">${data.team_name}</h2>
          <p class="result-card__record">${record} · ${data.season}</p>
        </div>
        <span class="result-card__status-badge status-${data.status}">${data.status_label}</span>
      </div>
      <div class="sharing-actions" aria-label="Share team result">
        <button class="share-button share-button--primary" id="share-card-btn" type="button">📲 Share my team</button>
        <button class="share-button" id="share-x-btn" type="button">𝕏 Share on X</button>
        <button class="share-button" id="share-reddit-btn" type="button">Reddit</button>
      </div>

      <div class="gauge-section">
        <div class="gauge-container">
          <svg class="gauge-svg" viewBox="0 0 200 200">
            <circle class="gauge-bg" cx="100" cy="100" r="${GAUGE_RADIUS}" />
            <circle
              class="gauge-fill"
              cx="100" cy="100" r="${GAUGE_RADIUS}"
              stroke="${scoreColor}"
              stroke-dasharray="${GAUGE_CIRCUMFERENCE}"
              stroke-dashoffset="${GAUGE_CIRCUMFERENCE}"
              id="gauge-circle"
              style="--gauge-color: ${scoreColor};"
            />
          </svg>
          <div class="gauge-center">
            <span class="gauge-value score-${scoreClass}" id="gauge-value">0</span>
            <span class="gauge-label">Tanking Score</span>
          </div>
        </div>
      </div>

      <div class="team-overview">
        <div class="standings-card">
          <div class="standings-card__icon">🏆</div>
          <div class="standings-card__info">
            <span class="standings-card__rank">#${standingsRank}</span>
            <span class="standings-card__conf">${conference}ern Conference</span>
            <span class="standings-card__of">out of ${standingsTotal} teams</span>
          </div>
        </div>

        <div class="schedule-block">
          <h3 class="schedule-block__title">📋 Last 3 Games</h3>
          <div class="games-list">
            ${recentGamesHtml || '<p class="no-data">No recent games data</p>'}
          </div>
        </div>

        <div class="schedule-block">
          <h3 class="schedule-block__title">📅 Next 3 Games</h3>
          <div class="games-list">
            ${upcomingGamesHtml || '<p class="no-data">No upcoming games data</p>'}
          </div>
        </div>
      </div>

      <section class="gamification-section" aria-label="Suspect tracker and team badges">
        <div class="section-heading-row">
          <div>
            <h3 class="gamification-title">Trophées de la honte</h3>
          </div>
          <span class="suspicion-meter">${suspectTracker.overall_suspicion || 0}% suspect</span>
        </div>
        <div class="badges-grid count-${Math.min(badges.length, 4)}">
          ${badges.map((badge) => `
            <article class="humor-badge badge-type-${badge.type || "shame"}">
              <span class="humor-badge__icon" aria-hidden="true">${badge.icon}</span>
              <div>
                <h4>${badge.name}</h4>
                <p class="humor-badge__explanation">${getBadgeExplanation(badge)}</p>
                <span class="humor-badge__metric">${badge.highlight}</span>
              </div>
            </article>
          `).join("")}
        </div>
      </section>

      <section class="gamification-section" aria-label="Suspect tracker and team badges">
          <div>
            <h3 class="gamification-title">Unavailable players</h3>
          </div>
        <div class="suspect-list count-${Math.min((suspectTracker.players || []).length, 4)}">
          ${(suspectTracker.players || []).map((player) => `
            <article class="suspect-player">
              <div class="suspect-player__topline">
                <div>
                  <h4 title="${player.name}">${player.name}</h4>
                  <p>${player.position || "Rotation"}</p>
                </div>
                <span class="player-status status-${player.status_code || "out"}">${player.status}</span>
              </div>
              <p class="suspect-player__reason">${player.reason}</p>
              <span class="suspect-player__missed">${player.games_missed} · ${player.suspicion_level}% suspicion</span>
            </article>
          `).join("")}
        </div>
      </section>

      <div class="chart-section">
        <h3 class="chart-section__title">📈 Tanking Score Evolution</h3>
        <p class="chart-section__subtitle">Score trajectory throughout the ${data.season} season</p>
        <div class="chart-container">
          <canvas id="tanking-chart"></canvas>
        </div>
      </div>

      <br>
      
      <h3 class="pillars-title">🔍 Why this score?</h3>
      <div class="pillars-grid">
        ${data.pillars.map((p) => renderPillarCard(p)).join("")}
      </div>
    </div>
  `;

  section.classList.add("visible");
  setupSharingActions(data);

  // Animate gauge after render
  requestAnimationFrame(() => {
    setTimeout(() => animateGauge(data.tanking_score, scoreColor), 100);
    animatePillarBars(data.pillars);
    if (data.tanking_history && data.tanking_history.length) {
      renderTankingChart(data.tanking_history, scoreColor);
    }
  });
}

function setupSharingActions(data) {
  $("#share-card-btn")?.addEventListener("click", () => downloadTankingCard(data));
  $("#share-x-btn")?.addEventListener("click", () => openSocialShare("x", data));
  $("#share-reddit-btn")?.addEventListener("click", () => openSocialShare("reddit", data));
}

function getShareText(data) {
  return `Mon équipe a un Tanking Score de ${data.tanking_score}%... Dégoûté mais vivement la lottery ! 🏀 #Tanking`;
}

function openSocialShare(network, data) {
  const text = encodeURIComponent(getShareText(data));
  const url = encodeURIComponent(window.location.href);
  const target = network === "reddit"
    ? `https://www.reddit.com/submit?title=${encodeURIComponent(`${data.team_name} Tanking Score: ${data.tanking_score}%`)}&text=${text}&url=${url}`
    : `https://twitter.com/intent/tweet?text=${text}&url=${url}`;
  window.open(target, "_blank", "noopener,noreferrer,width=680,height=620");
}

function downloadTankingCard(data) {
  const canvas = document.createElement("canvas");
  canvas.width = 1080;
  canvas.height = 1920;
  const ctx = canvas.getContext("2d");
  const scoreColor = getScoreColor(data.tanking_score);
  const badge = (data.badges || [])[0];
  const pillars = data.pillars || [];
  const suspicion = data.suspect_tracker?.overall_suspicion || 0;
  const record = `${data.record?.wins || 0}-${data.record?.losses || 0}`;

  ctx.fillStyle = "#252422";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#403d39";
  ctx.beginPath();
  ctx.roundRect(42, 42, 996, 1836, 32);
  ctx.fill();
  ctx.fillStyle = "#eb5e28";
  ctx.fillRect(42, 42, 10, 1836);
  ctx.fillStyle = "#ccc5b9";
  ctx.font = "700 28px Arial";
  ctx.fillText("IS YOUR TEAM TANKING?", 92, 125);
  ctx.fillStyle = "#fffcf2";
  ctx.font = "800 62px Arial";
  ctx.fillText(data.team_name, 92, 225);
  ctx.fillStyle = "#ccc5b9";
  ctx.font = "500 28px Arial";
  ctx.fillText(`${record}  ·  ${data.status_label}`, 96, 275);
  ctx.strokeStyle = "#5b5751";
  ctx.lineWidth = 24;
  ctx.beginPath();
  ctx.arc(540, 560, 190, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = scoreColor;
  ctx.beginPath();
  ctx.arc(540, 560, 190, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * data.tanking_score / 100));
  ctx.stroke();
  ctx.fillStyle = scoreColor;
  ctx.font = "800 78px Arial";
  ctx.textAlign = "center";
  ctx.fillText(`${data.tanking_score}%`, 540, 575);
  ctx.fillStyle = "#fffcf2";
  ctx.font = "700 26px Arial";
  ctx.fillText("TANKING SCORE", 540, 625);
  ctx.textAlign = "left";
  ctx.fillStyle = "#252422";
  ctx.beginPath();
  ctx.roundRect(92, 820, 896, 170, 20);
  ctx.fill();
  ctx.fillStyle = "#eb5e28";
  ctx.font = "700 28px Arial";
  ctx.fillText(`${badge?.icon || "🏀"} ${badge?.name || "League watch"}`, 125, 875);
  ctx.fillStyle = "#ccc5b9";
  ctx.font = "500 22px Arial";
  ctx.fillText("Primary signal detected", 125, 925);
  ctx.fillStyle = "#fffcf2";
  ctx.font = "800 30px Arial";
  ctx.fillText("KEY INDICATORS", 92, 1085);
  pillars.forEach((pillar, index) => {
    const y = 1145 + index * 125;
    ctx.fillStyle = "#5b5751";
    ctx.beginPath();
    ctx.roundRect(92, y, 896, 86, 16);
    ctx.fill();
    ctx.fillStyle = "#fffcf2";
    ctx.font = "600 24px Arial";
    ctx.fillText(pillar.name, 120, y + 37);
    ctx.fillStyle = getScoreColor(pillar.score);
    ctx.font = "800 28px Arial";
    ctx.textAlign = "right";
    ctx.fillText(`${pillar.score}%`, 955, y + 37);
    ctx.textAlign = "left";
  });
  ctx.fillStyle = "#252422";
  ctx.beginPath();
  ctx.roundRect(92, 1690, 896, 110, 16);
  ctx.fill();
  ctx.fillStyle = "#fffcf2";
  ctx.font = "600 25px Arial";
  ctx.fillText(`Suspect Tracker: ${suspicion}%`, 125, 1758);
  ctx.fillStyle = "#ccc5b9";
  ctx.font = "500 20px Arial";
  ctx.fillText("Statistical detector · isyourteamtanking.com", 92, 1840);
  const link = document.createElement("a");
  link.download = `${data.team_abbreviation.toLowerCase()}-tanking-story.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function getBadgeExplanation(badge) {
  const explanations = {
    trust_the_process: "Score global supérieur à 85 %." ,
    phantom_injury: "Absences suspectes des joueurs clés.",
    brick_city: "Effondrements répétés dans le money time.",
    daycare_lineup: "Lineup très jeune, sous le seuil de référence.",
    anti_tank: "Aucun signal majeur de tanking détecté.",
    limbo_alert: "Signaux partagés : la situation reste indécise.",
  };
  return explanations[badge.id] || "Signal notable dans les données de l'équipe.";
}

function renderPillarCard(pillar) {
  const scoreClass = getScoreColorClass(pillar.score);
  const weightPct = Math.round(pillar.weight * 100);
  return `
    <div class="pillar-card">
      <div class="pillar-card__header">
        <img src="/static/icons/${pillar.id}.svg" class="pillar-card__icon" alt="" />
        <div class="pillar-card__name-wrapper">
          <span class="pillar-card__name">${pillar.name}</span>
          <span class="pillar-card__weight">${weightPct}% weight</span>
        </div>
        <span class="pillar-card__score score-${scoreClass}">${pillar.score}</span>
      </div>
      <div class="pillar-card__bar-track">
        <div class="pillar-card__bar-fill bar-${scoreClass}" data-width="${pillar.score}"></div>
      </div>
      <p class="pillar-card__description">${pillar.description}</p>
      <p class="pillar-card__details">${pillar.details}</p>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Gauge Animation
// ---------------------------------------------------------------------------
function animateGauge(targetValue, color) {
  const circle = document.getElementById("gauge-circle");
  const valueEl = document.getElementById("gauge-value");
  if (!circle || !valueEl) return;

  const offset = GAUGE_CIRCUMFERENCE - (targetValue / 100) * GAUGE_CIRCUMFERENCE;
  circle.style.strokeDashoffset = offset;

  // Counter animation
  animateCounter(valueEl, 0, targetValue, 1200);
}

function animateCounter(el, start, end, duration) {
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease-out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(start + (end - start) * eased);
    el.textContent = current + "%";
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }
  requestAnimationFrame(update);
}

function animatePillarBars(pillars) {
  const bars = $$(".pillar-card__bar-fill");
  bars.forEach((bar) => {
    const w = bar.dataset.width || 0;
    setTimeout(() => {
      bar.style.width = w + "%";
    }, 300);
  });
}

// ---------------------------------------------------------------------------
// Tanking Score Evolution Chart
// ---------------------------------------------------------------------------
let tankingChartInstance = null;

function renderTankingChart(history, scoreColor) {
  const canvas = document.getElementById("tanking-chart");
  if (!canvas || typeof Chart === "undefined") return;

  // Destroy previous chart instance
  if (tankingChartInstance) {
    tankingChartInstance.destroy();
    tankingChartInstance = null;
  }

  const ctx = canvas.getContext("2d");
  const labels = history.map((h) => h.month);
  const scores = history.map((h) => h.score);

  // Create gradient fill
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.parentElement.clientHeight || 300);
  gradient.addColorStop(0, scoreColor + "66"); // 40% opacity at top
  gradient.addColorStop(0.5, scoreColor + "22"); // 13% opacity at middle
  gradient.addColorStop(1, "transparent");

  // Glow color for point
  const glowColor = scoreColor + "88";

  tankingChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Tanking Score",
          data: scores,
          fill: true,
          backgroundColor: gradient,
          borderColor: scoreColor,
          borderWidth: 3,
          pointBackgroundColor: scoreColor,
          pointBorderColor: "#1a1a2e",
          pointBorderWidth: 2,
          pointRadius: 5,
          pointHoverRadius: 8,
          pointHoverBackgroundColor: "#fff",
          pointHoverBorderColor: scoreColor,
          pointHoverBorderWidth: 3,
          tension: 0.4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 1500,
        easing: "easeOutQuart",
      },
      interaction: {
        intersect: false,
        mode: "index",
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15, 15, 35, 0.95)",
          titleColor: "#fff",
          bodyColor: "#fff",
          borderColor: scoreColor + "55",
          borderWidth: 1,
          cornerRadius: 12,
          padding: 14,
          displayColors: false,
          titleFont: { family: "'Outfit', sans-serif", size: 14, weight: "600" },
          bodyFont: { family: "'Inter', sans-serif", size: 13 },
          callbacks: {
            title: (items) => items[0].label + " 2025",
            label: (item) => `Tanking Score: ${item.raw}%`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.04)", drawBorder: false },
          ticks: {
            color: "rgba(255,255,255,0.5)",
            font: { family: "'Inter', sans-serif", size: 12 },
          },
          border: { display: false },
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: "rgba(255,255,255,0.04)", drawBorder: false },
          ticks: {
            color: "rgba(255,255,255,0.5)",
            font: { family: "'Inter', sans-serif", size: 12 },
            stepSize: 25,
            callback: (v) => v + "%",
          },
          border: { display: false },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Rankings
// ---------------------------------------------------------------------------
function renderRankings() {
  const containerEast = $("#rankings-list-east");
  const containerWest = $("#rankings-list-west");
  if (!containerEast || !containerWest || !allTeamResults.length) return;

  const teams = getFilteredTeams();
  const eastTeams = teams.filter(r => r.conference === "East").sort((a, b) => a.standings_rank - b.standings_rank);
  const westTeams = teams.filter(r => r.conference === "West").sort((a, b) => a.standings_rank - b.standings_rank);

  const generateHtml = (teams) => teams
    .map((r) => {
      const team = findTeam(r.team_abbreviation);
      const logoUrl = team?.logo || "";
      const scoreClass = getScoreColorClass(r.tanking_score);
      const record = r.record ? `${r.record.wins}-${r.record.losses}` : "";
      const featuredBadge = (r.badges || []).find((badge) => badge.type === "shame") || (r.badges || [])[0];
      return `
        <div class="ranking-item glass-effect" data-team-id="${r.team_id}">
          <span class="ranking-item__rank">${r.standings_rank}</span>
          <img class="ranking-item__logo" src="${logoUrl}" alt="${r.team_name}" loading="lazy" onerror="this.style.display='none'">
          <div class="ranking-item__identity">
            <span class="ranking-item__name">${r.team_name}</span>
            <span class="ranking-item__badge">${featuredBadge ? `${featuredBadge.icon} ${featuredBadge.name}` : "No badge"}</span>
          </div>
          <span class="ranking-item__record">${record}</span>
          <div class="ranking-item__bar-wrapper">
            <div class="ranking-item__bar-track">
              <div class="ranking-item__bar-fill bar-${scoreClass}" style="width:${r.tanking_score}%"></div>
            </div>
          </div>
          <span class="ranking-item__score score-${scoreClass}">${r.tanking_score}%</span>
        </div>
      `;
    })
    .join("");

  containerEast.innerHTML = generateHtml(eastTeams);
  containerWest.innerHTML = generateHtml(westTeams);
  renderLeagueTable(teams);

  // Click to select team
  document.querySelectorAll(".ranking-item").forEach((item) => {
    item.addEventListener("click", () => {
      const teamId = parseInt(item.dataset.teamId, 10);
      selectTeam(teamId);
      // Scroll to top
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function setupLeagueControls() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      rankingView = button.dataset.view;
      document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("is-active", item === button));
      $("#conference-view").hidden = rankingView !== "conferences";
      $("#league-table-view").hidden = rankingView !== "table";
    });
  });
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      rankingFilter = button.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      renderRankings();
    });
  });
  $("#league-sort")?.addEventListener("change", (event) => {
    rankingSort = event.target.value;
    renderRankings();
  });
  $("#reset-league-btn")?.addEventListener("click", resetLeagueControls);
  document.querySelectorAll("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      rankingSort = button.dataset.sort;
      $("#league-sort").value = rankingSort;
      renderRankings();
    });
  });
}

function resetLeagueControls() {
  rankingView = "conferences";
  rankingFilter = "all";
  rankingSort = "score";
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("is-active", item.dataset.view === "conferences"));
  document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-active", item.dataset.filter === "all"));
  const sort = $("#league-sort");
  if (sort) sort.value = "score";
  $("#conference-view").hidden = false;
  $("#league-table-view").hidden = true;
  renderRankings();
}

function getPillarScore(result, id) {
  return result.pillars?.find((pillar) => pillar.id === id)?.score || 0;
}

function getFilteredTeams() {
  return allTeamResults.filter((result) => {
    if (rankingFilter === "tank") return result.tanking_score >= 66;
    if (rankingFilter === "borderline") return result.tanking_score >= 31 && result.tanking_score < 66;
    if (rankingFilter === "contender") return result.tanking_score < 31;
    return true;
  });
}

function getSortedTeams(teams) {
  return [...teams].sort((a, b) => {
    if (rankingSort === "record") {
      return ((b.record?.pct || 0) - (a.record?.pct || 0)) || (b.tanking_score - a.tanking_score);
    }
    if (["vet_minutes", "dnp_suspects", "young_lineups", "clutch_collapse"].includes(rankingSort)) {
      return getPillarScore(b, rankingSort) - getPillarScore(a, rankingSort);
    }
    return b.tanking_score - a.tanking_score;
  });
}

function renderLeagueTable(teams) {
  const body = $("#league-table-body");
  if (!body) return;
  body.innerHTML = getSortedTeams(teams).map((result, index) => `
    <button class="league-table__row" data-team-id="${result.team_id}" type="button">
      <span>${index + 1}</span>
      <strong>${result.team_name}</strong>
      <span>${result.record?.wins || 0}-${result.record?.losses || 0}</span>
      <span class="score-${getScoreColorClass(result.tanking_score)}">${result.tanking_score}%</span>
      <span>${getPillarScore(result, "vet_minutes")}</span>
      <span>${getPillarScore(result, "dnp_suspects")}</span>
      <span>${getPillarScore(result, "young_lineups")}</span>
      <span>${getPillarScore(result, "clutch_collapse")}</span>
    </button>
  `).join("");
  body.querySelectorAll("[data-team-id]").forEach((row) => row.addEventListener("click", () => selectTeam(Number(row.dataset.teamId))));
}

// ---------------------------------------------------------------------------
// Scroll to top button
// ---------------------------------------------------------------------------
function setupScrollToTop() {
  const btn = $("#scroll-top-btn");
  if (!btn) return;
  window.addEventListener("scroll", () => {
    btn.classList.toggle("visible", window.scrollY > 400);
  });
  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getScoreColor(score) {
  if (score >= 66) return "#ef4444";
  if (score >= 31) return "#eab308";
  return "#22c55e";
}

function getScoreColorClass(score) {
  if (score >= 66) return "red";
  if (score >= 31) return "yellow";
  return "green";
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function setupHomeButton() {
  const homeBtn = $("#home-btn");
  if (!homeBtn) return;
  homeBtn.addEventListener("click", () => {
    history.replaceState(null, "", window.location.pathname);
    resetHomeView(true);
  });
}

function resetHomeView(shouldScroll = true) {
  const section = $(".result-section");
  if (section) {
    section.classList.remove("visible");
    section.innerHTML = "";
  }

  const rankings = $(".rankings-section");
  if (rankings) rankings.style.display = "block";

  const homeBtn = $("#home-btn");
  if (homeBtn) homeBtn.style.display = "none";

  const input = $("#search-input");
  if (input) input.value = "";

  selectedTeam = null;

  if (shouldScroll) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}
