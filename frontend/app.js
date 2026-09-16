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
function selectTeam(teamId) {
  const result = allTeamResults.find((r) => r.team_id === teamId);
  if (!result) return;

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

  // Animate gauge after render
  requestAnimationFrame(() => {
    setTimeout(() => animateGauge(data.tanking_score, scoreColor), 100);
    animatePillarBars(data.pillars);
    if (data.tanking_history && data.tanking_history.length) {
      renderTankingChart(data.tanking_history, scoreColor);
    }
  });
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

  const eastTeams = allTeamResults.filter(r => r.conference === "East").sort((a, b) => a.standings_rank - b.standings_rank);
  const westTeams = allTeamResults.filter(r => r.conference === "West").sort((a, b) => a.standings_rank - b.standings_rank);

  const generateHtml = (teams) => teams
    .map((r) => {
      const team = findTeam(r.team_abbreviation);
      const logoUrl = team?.logo || "";
      const scoreClass = getScoreColorClass(r.tanking_score);
      const record = r.record ? `${r.record.wins}-${r.record.losses}` : "";
      return `
        <div class="ranking-item glass-effect" data-team-id="${r.team_id}">
          <span class="ranking-item__rank">${r.standings_rank}</span>
          <img class="ranking-item__logo" src="${logoUrl}" alt="${r.team_name}" loading="lazy" onerror="this.style.display='none'">
          <span class="ranking-item__name">${r.team_name}</span>
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
    // Reset view
    const section = $(".result-section");
    if (section) {
      section.classList.remove("visible");
      section.innerHTML = "";
    }

    const rankings = $(".rankings-section");
    if (rankings) rankings.style.display = "block";

    homeBtn.style.display = "none";

    const input = $("#search-input");
    if (input) input.value = "";

    selectedTeam = null;

    // Scroll to top
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}
