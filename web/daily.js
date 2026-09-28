// WARBall Daily Mode: draft three elite starters, each facing today's Legends
// once through. The score is expected runs allowed vs. par. Today's pool and
// every number come from the local server (python -m warball.server).

const HR_EDGE_RATIO = 0.75; // highlight adjusted HR% at least 25% below today's league average
const SAMPLE_PA_MS = 110;

const state = { challenge: null, staff: [], locked: false };

const $ = id => document.getElementById(id);
const escapeHtml = s =>
  String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = v => `${(v * 100).toFixed(1)}%`;
const signed = (v, digits = 2) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(digits);

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

// ---------- Draft ----------

function toggle(card) {
  if (state.locked) return;
  const i = state.staff.findIndex(c => c.id === card.id);
  if (i > -1) state.staff.splice(i, 1);
  else if (state.staff.length < state.challenge.staffSize) state.staff.push(card);
  render();
}

function cardElement(card) {
  const picked = state.staff.some(c => c.id === card.id);
  const full = state.staff.length >= state.challenge.staffSize;
  const lowHr = card.adjusted.HR <= HR_EDGE_RATIO * state.challenge.reference.HR;
  const el = document.createElement("div");
  el.className = "player-card" + (picked ? " selected" : "") + (!picked && full ? " unavailable" : "");
  el.innerHTML = `
    <div class="player-head"><span class="role-badge">SP</span><span class="player-name">${escapeHtml(card.name)}</span></div>
    <div class="player-era">${card.years} · ${card.IP.toLocaleString()} IP · FIP- ${card.FIPminus}</div>
    <div class="player-stats">
      <div class="stat-block"><div class="stat-value">${card.FIP.toFixed(2)}</div><div class="stat-label">FIP</div></div>
      <div class="stat-block"><div class="stat-value${lowHr ? " edge" : ""}">${pct(card.adjusted.HR)}</div><div class="stat-label">HR%</div></div>
      <div class="stat-block"><div class="stat-value">${pct(card.adjusted.K)}</div><div class="stat-label">K%</div></div>
      <div class="stat-block"><div class="stat-value">${pct(card.adjusted.BB)}</div><div class="stat-label">BB%</div></div>
    </div>`;
  el.addEventListener("click", () => toggle(card));
  return el;
}

function render() {
  const c = state.challenge;
  $("pool").replaceChildren(...c.pool.map(cardElement));
  $("staff-slots").replaceChildren(
    ...Array.from({ length: c.staffSize }, (_, i) => {
      const card = state.staff[i];
      const row = document.createElement("div");
      row.className = "staff-row " + (card ? "filled" : "empty");
      row.innerHTML = `<span class="slot-role">ARM ${i + 1} · ${c.paPerArm} PA</span>${card ? escapeHtml(card.name) : "empty"}`;
      if (card) row.addEventListener("click", () => toggle(card));
      return row;
    })
  );
  $("progress-count").textContent = state.staff.length;
  $("lock-btn").disabled = state.staff.length < c.staffSize || state.locked;
}

function renderChallenge() {
  const c = state.challenge;
  $("header-date").textContent = c.date;
  $("theme-tag").textContent = `TODAY'S THEME — ${c.theme}`;
  $("hero-sub").textContent =
    `Every Legend's career is adjusted to today's game (2015–2024). Draft ${c.staffSize} starters; each faces the ` +
    `lineup once through, ${c.staffSize * c.paPerArm} plate appearances in all. Your score is the runs they're ` +
    `expected to allow, so keep the ball in the park and beat par.`;
  $("hero-par").textContent = c.par.toFixed(2);
  $("pool-note").innerHTML =
    `Career rates adjusted to today's game. <span class="edge-key">HR% in orange</span> is at least 25% below ` +
    `today's league average (${pct(c.reference.HR)}).`;
  $("staff-size").textContent = c.staffSize;
  $("target-par").textContent = c.par.toFixed(2);
  $("target-average").textContent = c.averageStaff.toFixed(2);

  $("legends-table").innerHTML =
    `<tr><th>Hitter</th><th class="num">Career HR</th><th class="num">HR%</th><th class="num">K%</th><th class="num">BB%</th></tr>` +
    c.legends
      .map(
        b => `<tr><td>${escapeHtml(b.name)} <span class="muted">${b.years}</span></td><td class="num">${b.HR}</td>
          <td class="num">${pct(b.adjusted.HR)}</td><td class="num">${pct(b.adjusted.K)}</td><td class="num">${pct(b.adjusted.BB)}</td></tr>`
      )
      .join("") +
    `<tr><td class="muted">Rates adjusted to today's game</td><td></td><td class="num muted">lg ${pct(c.reference.HR)}</td>
      <td class="num muted">lg ${pct(c.reference.K)}</td><td class="num muted">lg ${pct(c.reference.BB)}</td></tr>`;
}

async function lockIn() {
  state.locked = true;
  render();
  try {
    const result = await api("/api/daily/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: state.challenge.date, staff: state.staff.map(c => c.id) }),
    });
    showResult(result);
  } catch (err) {
    state.locked = false;
    render();
    $("error").textContent = `Scoring failed: ${err.message}`;
    $("error").hidden = false;
  }
}

// ---------- Result ----------

function mathLine(label, value, cls = "") {
  return `<div class="math-line ${cls}"><span>${label}</span><span class="num">${value}</span></div>`;
}

function showResult(r) {
  $("hero").hidden = true;
  $("draft-view").hidden = true;
  $("result-view").hidden = false;
  $("result-date").textContent = r.date;
  window.scrollTo(0, 0);

  $("score").textContent = r.score.toFixed(2);
  $("score-sub").textContent =
    `expected runs allowed · par ${r.par.toFixed(2)} · better than ${r.betterThanPct.toFixed(0)}% of random elite staffs`;
  const banner = $("par-banner");
  const under = r.vsPar < 0;
  banner.textContent = `${Math.abs(r.vsPar).toFixed(2)} ${under ? "UNDER" : "OVER"} PAR`;
  banner.classList.toggle("over", !under);

  $("math-lines").innerHTML =
    mathLine("A league-average staff vs. today's Legends", r.averageStaff.toFixed(2)) +
    mathLine(
      `− raw quality: runs your staff saves vs. a league-average lineup (${r.averageLineupVsAverageStaff.toFixed(2)} → ${r.averageLineupVsYou.toFixed(2)})`,
      signed(-r.rawQuality)
    ) +
    mathLine("− matchup edge: extra runs saved against these sluggers", signed(-r.matchupEdge)) +
    mathLine("&nbsp;&nbsp;&nbsp;of which home-run suppression (approximate)", signed(-r.hrEdge), "sub") +
    mathLine("= your expected runs allowed", r.score.toFixed(2), "total") +
    mathLine("Par", r.par.toFixed(2)) +
    mathLine("Your score vs. par", signed(r.vsPar), "total");

  $("staff-table").innerHTML =
    `<tr><th>Pitcher</th><th class="num">Runs allowed</th><th class="num">vs. avg lineup</th><th class="num">Exp. HR</th></tr>` +
    r.staff
      .map(
        (p, i) => `<tr><td>${escapeHtml(p.name)} <span class="muted">arm ${i + 1}</span></td>
          <td class="num">${p.runsAllowed.toFixed(2)}</td><td class="num">${p.runsVsAverageLineup.toFixed(2)}</td>
          <td class="num">${p.homeRuns.toFixed(2)}</td></tr>`
      )
      .join("");

  $("legends-result-table").innerHTML =
    `<tr><th>Hitter</th><th class="num">Exp. HR vs. you</th><th class="num">vs. avg staff</th><th class="num">Runs in</th></tr>` +
    r.legends
      .map(
        b => `<tr><td>${escapeHtml(b.name)}</td><td class="num">${b.homeRuns.toFixed(2)}</td>
          <td class="num">${b.homeRunsVsAverage.toFixed(2)}</td><td class="num">${b.runs.toFixed(2)}</td></tr>`
      )
      .join("");

  playSample(r);
}

// Reveals the seeded sample game one plate appearance at a time, one row per arm.
function playSample(r) {
  const container = $("sample-game");
  const rows = r.staff.map((p, i) => {
    const row = document.createElement("div");
    row.className = "sample-row";
    row.innerHTML = `<div class="sample-arm">${escapeHtml(p.name)}</div><div class="sample-chips"></div>`;
    container.appendChild(row);
    return row.querySelector(".sample-chips");
  });

  let i = 0;
  let total = 0;
  const timer = setInterval(() => {
    const e = r.sampleGame[i];
    total += e.runs;
    const chip = document.createElement("span");
    chip.className = `chip chip-${e.outcome}`;
    chip.title = `${state.challenge.legends[e.batter].name}, inning ${e.inning}`;
    chip.innerHTML = e.outcome + (e.runs ? `<sup>+${e.runs}</sup>` : "");
    rows[e.pitcher].appendChild(chip);
    $("sample-total").textContent = `Runs in this sampled game: ${total}`;
    if (++i === r.sampleGame.length) clearInterval(timer);
  }, SAMPLE_PA_MS);
}

// ---------- Init ----------

async function init() {
  $("lock-btn").addEventListener("click", lockIn);
  try {
    state.challenge = await api("/api/daily");
  } catch (err) {
    $("hero-sub").textContent = `Couldn't load today's challenge (${err.message}). Is python -m warball.server running?`;
    return;
  }
  renderChallenge();
  render();
}

init();
