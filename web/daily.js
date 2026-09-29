// WARBall Daily Mode. Two kinds of puzzle share this page:
//   staff  (Power Hitters): draft 3 elite starters vs. nine Legends; score = expected runs allowed
//   lineup (Great Pitchers): draft 9 modern hitters vs. one ace; score = expected runs scored
// Today's theme, pool, and every number come from the local server (python -m warball.server).
// ?theme=power|aces and ?date=YYYY-MM-DD preview another theme or day.

const LEVER_EDGE_RATIO = 0.75; // staff: highlight a lever rate at least 25% below today's league average
const SIG_EDGE_WOBA = 0.01; // lineup: highlight hitters this much better vs. the signature pitch than their skill predicts
const SAMPLE_PA_MS = 110;

const KINDS = {
  staff: {
    poolTitle: "DRAFT POOL — ELITE STARTERS",
    pickLabel: "YOUR STAFF",
    slot: (i, c) => `ARM ${i + 1} · ${c.paPerPick} PA`,
    averageLabel: "League-average staff",
    targetNote: "Expected runs allowed. Lower is better.",
    lock: "LOCK IN STAFF",
    parLabel: "PAR<br>EXPECTED RUNS ALLOWED",
    scoreLabel: "expected runs allowed",
    entries: "random elite staffs",
    lowerIsBetter: true,
  },
  lineup: {
    poolTitle: "DRAFT POOL — MODERN HITTERS",
    pickLabel: "YOUR LINEUP",
    slot: (i, c) => `#${i + 1} · ${c.paPerPick} PA`,
    averageLabel: "League-average lineup",
    targetNote: "Expected runs scored. Higher is better. Your lineup bats in the order you draft it.",
    lock: "LOCK IN LINEUP",
    parLabel: "PAR<br>EXPECTED RUNS SCORED",
    scoreLabel: "expected runs scored",
    entries: "random lineups",
    lowerIsBetter: false,
  },
};

const state = { challenge: null, picks: [], locked: false };
const params = new URLSearchParams(location.search);

const $ = id => document.getElementById(id);
const escapeHtml = s =>
  String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = v => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const rate3 = v => v.toFixed(3).replace(/^0/, "");
const signed = (v, digits = 2) => {
  const shown = Math.abs(v).toFixed(digits);
  return (v >= 0 || Number(shown) === 0 ? "+" : "−") + shown; // never "−0.00"
};
const kind = () => KINDS[state.challenge.kind];
const leverStat = lever => `${lever}%`;

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

// ---------- Draft ----------

function toggle(card) {
  if (state.locked) return;
  const i = state.picks.findIndex(c => c.id === card.id);
  if (i > -1) state.picks.splice(i, 1);
  else if (state.picks.length < state.challenge.pickCount) state.picks.push(card);
  render();
}

function statBlock(value, label, edge = false) {
  return `<div class="stat-block"><div class="stat-value${edge ? " edge" : ""}">${value}</div><div class="stat-label">${label}</div></div>`;
}

function pitcherCardHtml(card) {
  const c = state.challenge;
  const edge = card.adjusted[c.lever] <= LEVER_EDGE_RATIO * c.reference[c.lever];
  return `
    <div class="player-head"><span class="role-badge">SP</span><span class="player-name">${escapeHtml(card.name)}</span></div>
    <div class="player-era">${card.years} · ${card.IP.toLocaleString()} IP · FIP- ${card.FIPminus}</div>
    <div class="player-stats">
      ${statBlock(card.FIP.toFixed(2), "FIP")}
      ${["HR", "K", "BB"].map(b => statBlock(pct(card.adjusted[b]), leverStat(b), b === c.lever && edge)).join("")}
    </div>`;
}

function hitterCardHtml(card) {
  const sig = state.challenge.lever;
  const edge = card.sigWoba - card.sigExpected >= SIG_EDGE_WOBA;
  return `
    <div class="player-head"><span class="role-badge">BAT</span><span class="player-name">${escapeHtml(card.name)}</span></div>
    <div class="player-era">${card.years} · ${card.PA.toLocaleString()} PA · K ${pct(card.K)}</div>
    <div class="player-stats">
      ${statBlock(rate3(card.woba), "wOBA")}
      ${statBlock(rate3(card.sigWoba), `vs ${sig} wOBA`, edge)}
      ${statBlock(pct(card.sigWhiffRate), `${sig} whiff`)}
      ${statBlock(card.sigPA, `${sig} PA`)}
    </div>`;
}

function cardElement(card) {
  const picked = state.picks.some(c => c.id === card.id);
  const full = state.picks.length >= state.challenge.pickCount;
  const el = document.createElement("div");
  el.className = "player-card" + (picked ? " selected" : "") + (!picked && full ? " unavailable" : "");
  el.innerHTML = state.challenge.kind === "staff" ? pitcherCardHtml(card) : hitterCardHtml(card);
  el.addEventListener("click", () => toggle(card));
  return el;
}

function render() {
  const c = state.challenge;
  $("pool").replaceChildren(...c.pool.map(cardElement));
  $("pick-slots").replaceChildren(
    ...Array.from({ length: c.pickCount }, (_, i) => {
      const card = state.picks[i];
      const row = document.createElement("div");
      row.className = "staff-row " + (card ? "filled" : "empty");
      row.innerHTML = `<span class="slot-role">${kind().slot(i, c)}</span>${card ? escapeHtml(card.name) : "empty"}`;
      if (card) row.addEventListener("click", () => toggle(card));
      return row;
    })
  );
  $("progress-count").textContent = state.picks.length;
  $("lock-btn").disabled = state.picks.length < c.pickCount || state.locked;
}

function arsenalTable(ace) {
  return (
    `<tr><th>Pitch</th><th class="num">Share of PA</th><th class="num">Whiff%</th><th class="num">wOBA</th><th class="num">League</th></tr>` +
    ace.arsenal
      .map(
        p => `<tr class="${p.group === ace.signature ? "signature" : ""}"><td>${p.name}${p.group === ace.signature ? " ★" : ""}</td>
          <td class="num">${pct(p.usage)}</td><td class="num">${pct(p.whiffRate)}</td>
          <td class="num">${rate3(p.woba)}</td><td class="num muted">${rate3(p.leagueWoba)}</td></tr>`
      )
      .join("")
  );
}

function renderStaffChallenge(c) {
  $("hero-sub").textContent =
    `Every Legend's career is adjusted to today's game (2015–2024). Draft ${c.pickCount} starters; each faces the ` +
    `lineup once through, ${c.pickCount * c.paPerPick} plate appearances in all. Your score is the runs they're ` +
    `expected to allow, ${c.blurb}`;
  $("pool-note").innerHTML =
    `Career rates adjusted to today's game. <span class="edge-key">${leverStat(c.lever)} in orange</span> is at least ` +
    `25% below today's league average (${pct(c.reference[c.lever])}).`;

  $("legends-title").textContent = "TODAY'S LEGENDS";
  $("legends-table").innerHTML =
    `<tr><th>Hitter</th><th class="num">Career HR</th><th class="num">HR%</th><th class="num">K%</th><th class="num">BB%</th></tr>` +
    c.legends
      .map(
        b => `<tr><td>${escapeHtml(b.name)} <span class="muted">${b.years}</span></td>
          <td class="num">${b.HR}</td><td class="num">${pct(b.adjusted.HR)}</td>
          <td class="num">${pct(b.adjusted.K)}</td><td class="num">${pct(b.adjusted.BB)}</td></tr>`
      )
      .join("") +
    `<tr><td class="muted">Rates adjusted to today's game</td><td></td><td class="num muted">lg ${pct(c.reference.HR)}</td>
      <td class="num muted">lg ${pct(c.reference.K)}</td><td class="num muted">lg ${pct(c.reference.BB)}</td></tr>`;
}

function renderLineupChallenge(c) {
  const ace = c.ace;
  const sig = ace.arsenal.find(p => p.group === ace.signature);
  $("hero-sub").textContent =
    `${ace.name} (${ace.years}), three times through your order. His ${ace.signatureName} ends ${pct(sig.usage)} of ` +
    `his plate appearances and holds hitters to a ${rate3(sig.woba)} wOBA (league ${rate3(sig.leagueWoba)}). Draft ` +
    `${c.pickCount} hitters; your score is the runs they're expected to score, so find the bats that handle his ` +
    `${ace.signatureName} and beat par.`;
  $("pool-note").innerHTML =
    `2015–2024 Statcast rates, shrunk toward each hitter's overall skill. <span class="edge-key">vs ${c.lever} wOBA in ` +
    `orange</span> is at least ${rate3(SIG_EDGE_WOBA)} better than his overall skill predicts against ${ace.signatureName}s ` +
    `(league: ${rate3(c.leagueSigWoba)}).`;
  $("legends-title").textContent = `TODAY'S ACE — ${ace.name.toUpperCase()}`;
  $("legends-note").hidden = false;
  $("legends-note").textContent =
    `${ace.years} · ${ace.BF.toLocaleString()} batters faced · wOBA allowed ${rate3(ace.wobaAllowed)} ` +
    `(league ${rate3(ace.leagueWoba)}). ★ = signature pitch.`;
  $("legends-table").innerHTML = arsenalTable(ace);
}

function renderChallenge() {
  const c = state.challenge;
  const k = kind();
  $("header-date").textContent = c.date;
  $("theme-tag").textContent = `TODAY'S THEME — ${c.theme}`;
  $("hero-headline").textContent = c.headline;
  $("hero-par").textContent = c.par.toFixed(2);
  $("hero-par-label").innerHTML = k.parLabel;
  $("pool-title").textContent = k.poolTitle;
  $("pick-label").textContent = k.pickLabel;
  $("pick-count").textContent = c.pickCount;
  $("target-par").textContent = c.par.toFixed(2);
  $("target-average-label").textContent = k.averageLabel;
  $("target-average").textContent = c.average.toFixed(2);
  $("target-note").textContent = k.targetNote;
  $("lock-btn").textContent = k.lock;
  if (c.kind === "staff") renderStaffChallenge(c);
  else renderLineupChallenge(c);
}

async function lockIn() {
  state.locked = true;
  render();
  try {
    const result = await api("/api/daily/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date: state.challenge.date,
        theme: state.challenge.themeKey,
        picks: state.picks.map(c => c.id),
      }),
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

function staffResult(r) {
  const lever = r.lever;
  $("math-lines").innerHTML =
    mathLine("A league-average staff vs. today's Legends", r.average.toFixed(2)) +
    mathLine(
      `− raw quality: runs your staff saves vs. a league-average lineup (${r.averageVsAverage.toFixed(2)} → ${r.averageVsYou.toFixed(2)})`,
      signed(-r.rawQuality)
    ) +
    mathLine("− matchup edge: extra runs saved against these Legends", signed(-r.matchupEdge)) +
    mathLine(`&nbsp;&nbsp;&nbsp;of which ${r.leverName} (approximate)`, signed(-r.leverEdge), "sub") +
    mathLine("= your expected runs allowed", r.score.toFixed(2), "total") +
    mathLine("Par", r.par.toFixed(2)) +
    mathLine("Your score vs. par", signed(r.vsPar), "total");

  $("picks-result-title").textContent = "YOUR STAFF";
  $("picks-table").innerHTML =
    `<tr><th>Pitcher</th><th class="num">Runs allowed</th><th class="num">vs. avg lineup</th><th class="num">Exp. ${lever}</th></tr>` +
    r.staff
      .map(
        (p, i) => `<tr><td>${escapeHtml(p.name)} <span class="muted">arm ${i + 1}</span></td>
          <td class="num">${p.runsAllowed.toFixed(2)}</td><td class="num">${p.runsVsAverageLineup.toFixed(2)}</td>
          <td class="num">${p.lever.toFixed(2)}</td></tr>`
      )
      .join("");

  $("opponent-result-title").textContent = "THE LEGENDS AT THE PLATE";
  $("opponent-table").innerHTML =
    `<tr><th>Hitter</th><th class="num">Exp. ${lever} vs. you</th><th class="num">vs. avg staff</th><th class="num">Runs in</th></tr>` +
    r.legends
      .map(
        b => `<tr><td>${escapeHtml(b.name)}</td><td class="num">${b.lever.toFixed(2)}</td>
          <td class="num">${b.leverVsAverage.toFixed(2)}</td><td class="num">${b.runs.toFixed(2)}</td></tr>`
      )
      .join("");
}

function lineupResult(r) {
  $("math-lines").innerHTML =
    mathLine(`A league-average lineup vs. ${escapeHtml(r.ace.name)}`, r.average.toFixed(2)) +
    mathLine(
      `+ raw quality: runs your lineup adds vs. a league-average pitcher (${r.averageVsAverage.toFixed(2)} → ${r.youVsAverage.toFixed(2)})`,
      signed(r.rawQuality)
    ) +
    mathLine("+ matchup edge: extra runs against this ace", signed(r.matchupEdge)) +
    mathLine(`&nbsp;&nbsp;&nbsp;of which ${r.leverName} (approximate)`, signed(r.leverEdge), "sub") +
    mathLine("= your expected runs scored", r.score.toFixed(2), "total") +
    mathLine("Par", r.par.toFixed(2)) +
    mathLine("Your score vs. par", signed(r.vsPar), "total");

  $("picks-result-title").textContent = "YOUR LINEUP";
  $("picks-table").innerHTML =
    `<tr><th>Hitter</th><th class="num">Runs</th><th class="num">vs. avg pitcher</th><th class="num">wOBA vs. ace</th></tr>` +
    r.hitters
      .map(
        (h, i) => `<tr><td><span class="muted">${i + 1}.</span> ${escapeHtml(h.name)}</td>
          <td class="num">${h.runs.toFixed(2)}</td><td class="num">${h.runsVsAverage.toFixed(2)}</td>
          <td class="num">${rate3(h.wobaVsAce)}</td></tr>`
      )
      .join("");

  $("opponent-result-title").textContent = `THE ACE — ${r.ace.name.toUpperCase()}`;
  $("opponent-table").innerHTML = arsenalTable(r.ace);
}

function showResult(r) {
  const k = kind();
  $("hero").hidden = true;
  $("draft-view").hidden = true;
  $("result-view").hidden = false;
  $("result-theme").textContent = `BEAT THE LEGENDS — ${state.challenge.theme}`;
  $("result-date").textContent = r.date;
  window.scrollTo(0, 0);

  $("score").textContent = r.score.toFixed(2);
  $("score-sub").textContent =
    `${k.scoreLabel} · par ${r.par.toFixed(2)} · better than ${r.betterThanPct.toFixed(0)}% of ${k.entries}`;
  const banner = $("par-banner");
  const onPar = Math.abs(r.vsPar) < 0.005;
  const beatPar = k.lowerIsBetter ? r.vsPar < 0 : r.vsPar > 0;
  banner.textContent = onPar ? "ON PAR" : `${Math.abs(r.vsPar).toFixed(2)} ${r.vsPar < 0 ? "UNDER" : "OVER"} PAR`;
  banner.classList.toggle("miss", !beatPar && !onPar);

  if (r.kind === "staff") staffResult(r);
  else lineupResult(r);
  playSample(r);
}

// Reveals the seeded sample game one plate appearance at a time: one row per arm, or per time through the order.
function playSample(r) {
  const container = $("sample-game");
  const rows = r.sampleRows.map(label => {
    const row = document.createElement("div");
    row.className = "sample-row";
    row.innerHTML = `<div class="sample-arm">${escapeHtml(label)}</div><div class="sample-chips"></div>`;
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
    chip.title = `${r.sampleBatters[e.batter]}, inning ${e.inning}`;
    chip.innerHTML = e.outcome + (e.runs ? `<sup>+${e.runs}</sup>` : "");
    rows[e.pitcher].appendChild(chip);
    $("sample-total").textContent = `Runs in this sampled game: ${total}`;
    if (++i === r.sampleGame.length) clearInterval(timer);
  }, SAMPLE_PA_MS);
}

// ---------- Init ----------

async function init() {
  $("lock-btn").addEventListener("click", lockIn);
  const query = new URLSearchParams();
  for (const key of ["date", "theme"]) if (params.get(key)) query.set(key, params.get(key));
  try {
    state.challenge = await api(`/api/daily${query.size ? `?${query}` : ""}`);
  } catch (err) {
    $("hero-sub").textContent = `Couldn't load today's challenge (${err.message}). Is python -m warball.server running?`;
    return;
  }
  renderChallenge();
  render();
}

init();
