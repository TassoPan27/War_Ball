// WARBall Classic Mode draft UI. Every draft pool and all season math come
// from the local server (python -m warball.server); this file only renders.

// Measured in the browser: 9px mono is 5.4 units per character and the
// ring's inner chord at the name line is ~35.7, so 6 fit and a 7th spills.
const TOKEN_NAME_MAX_CHARS = 6;
const TICK_MS = 70;
const TEAM_STOP_TICK = 14;
const ERA_STOP_TICK = 20;
const ERA_STOP_AFTER_TEAM = 6;
const SEASON_ANIMATION_MS = 3200;

// A re-spin is a spin taken without drafting from the current team & era.
const ROSTER_RESPINS = 3; // shared by the lineup and pitching-staff steps
const COACH_RESPINS = 3;

// Same order as the engine's ALL_SLOTS, so card ids can be sent positionally.
const LINEUP_SLOTS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"];
const ROTATION_SLOTS = ["SP1", "SP2", "SP3", "SP4", "SP5"];
const BULLPEN_SLOTS = ["RP1", "RP2", "RP3"];
const ALL_SLOTS = [...LINEUP_SLOTS, ...ROTATION_SLOTS, ...BULLPEN_SLOTS];

// The draft runs in steps, each on its own screen: hitters -> pitchers -> coach -> season.
const PHASES = ["hitters", "pitchers", "coach"];
const PHASE_SLOTS = { hitters: LINEUP_SLOTS, pitchers: [...ROTATION_SLOTS, ...BULLPEN_SLOTS] };

const state = {
  phase: "hitters", // see PHASES, then "season"
  wheel: { teams: [], eras: [] },
  pool: [], // cards from the current spin
  selectedId: null,
  pickThisSpin: null, // one pick per spin; only this pick can be undone
  hasSpun: false,
  spinning: false,
  respins: ROSTER_RESPINS,
  coachRespins: COACH_RESPINS,
  error: null,
  roster: {}, // slot -> card
  order: Array(LINEUP_SLOTS.length).fill(null),
  coach: null,
};

const $ = id => document.getElementById(id);
const pickFrom = list => (list.length ? list[Math.floor(Math.random() * list.length)] : "— — —");
const escapeHtml = s =>
  String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const signed = (v, digits = 1) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(digits);
const plusMinus = v => `${v >= 0 ? "+" : "−"} ${Math.abs(v).toFixed(0)}`;

// The engine has three interchangeable OF slots; the diamond just labels them LF/CF/RF.
function engineLabel(slot) {
  if (["LF", "CF", "RF"].includes(slot)) return "OF";
  if (slot.startsWith("SP")) return "SP";
  if (slot.startsWith("RP")) return "RP";
  return slot;
}

function tokenName(last) {
  return last.length > TOKEN_NAME_MAX_CHARS ? last.slice(0, TOKEN_NAME_MAX_CHARS - 1) + "." : last;
}

const openSlots = () => (PHASE_SLOTS[state.phase] || []).filter(slot => !state.roster[slot]);
const phaseFull = () => openSlots().length === 0;
const draftedPlayerIds = () => Object.values(state.roster).map(card => card.playerID);
const onRoster = card => Object.values(state.roster).includes(card);
const selectedCard = () => state.pool.find(card => card.id === state.selectedId) || null;
const canPlace = (card, slot) => !state.roster[slot] && card.slots.includes(engineLabel(slot));

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

// ---------- Draft actions ----------

// Spinning again before drafting anyone from the current spin uses up a re-spin.
function isRespin() {
  return state.hasSpun && (state.phase === "coach" ? !state.coach : state.pickThisSpin === null);
}

const respinsLeft = () => (state.phase === "coach" ? state.coachRespins : state.respins);

function canSpin() {
  if (state.spinning) return false;
  if (state.phase === "coach" && state.coach) return false;
  if (state.phase !== "coach" && (!PHASE_SLOTS[state.phase] || phaseFull())) return false;
  return !isRespin() || respinsLeft() > 0;
}

async function spin() {
  if (!canSpin()) return;
  const respin = isRespin();
  let request;
  if (state.phase === "coach") {
    request = api("/api/coach-spin");
  } else {
    const open = [...new Set(openSlots().map(engineLabel))].join(",");
    const exclude = draftedPlayerIds().join(",");
    request = api(`/api/spin?open=${encodeURIComponent(open)}&exclude=${encodeURIComponent(exclude)}`);
  }

  state.error = null;
  try {
    const result = await spinReels(request);
    state.pool = result.cards;
    if (respin && state.phase === "coach") state.coachRespins--;
    else if (respin) state.respins--;
    state.hasSpun = true;
    state.selectedId = null;
    state.pickThisSpin = null;
  } catch (err) {
    state.error = `Spin failed: ${err.message}. Is the server running (python -m warball.server)?`;
  }
  render();
}

function clickCard(card) {
  if (state.phase === "coach") {
    if (state.coach) return;
    state.coach = card;
    state.pickThisSpin = card;
  } else if (!state.pickThisSpin && !state.spinning) {
    state.selectedId = state.selectedId === card.id ? null : card.id;
  }
  render();
}

function clickSlot(slot) {
  if (!PHASE_SLOTS[state.phase]?.includes(slot) || state.spinning) return;
  const current = state.roster[slot];
  if (current) {
    if (current !== state.pickThisSpin) return; // earlier picks are locked in
    delete state.roster[slot];
    removeFromOrder(current);
    state.pickThisSpin = null;
  } else {
    const card = selectedCard();
    if (!card || state.pickThisSpin || !canPlace(card, slot)) return;
    state.roster[slot] = card;
    state.pickThisSpin = card;
    state.selectedId = null;
  }
  render();
}

function undoCoach() {
  if (state.phase !== "coach" || !state.coach) return;
  state.coach = null;
  state.pickThisSpin = null;
  render();
}

function removeFromOrder(card) {
  const i = state.order.indexOf(card);
  if (i > -1) state.order[i] = null;
}

function fillBattingOrder() {
  const unordered = LINEUP_SLOTS.map(slot => state.roster[slot]).filter(card => !state.order.includes(card));
  state.order = state.order.map(card => card || unordered.shift());
}

function goToPhase(phase) {
  fillBattingOrder();
  Object.assign(state, { phase, pool: [], hasSpun: false, pickThisSpin: null, selectedId: null, error: null });
  window.scrollTo(0, 0);
  render();
}

async function simulateSeason() {
  fillBattingOrder();
  const ids = slots => slots.map(slot => state.roster[slot].id);
  const body = {
    lineup: ids(LINEUP_SLOTS),
    rotation: ids(ROTATION_SLOTS),
    bullpen: ids(BULLPEN_SLOTS),
    coach: state.coach.id,
  };
  try {
    const season = await api("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    state.phase = "season";
    showSeason(season);
  } catch (err) {
    state.error = `Simulation failed: ${err.message}`;
    render();
  }
}

// ---------- Reels ----------

function spinReels(request) {
  state.spinning = true;
  $("spin-btn").disabled = true;
  const teamReel = $("reel-team");
  const eraReel = $("reel-era");
  teamReel.classList.add("spinning");
  eraReel.classList.add("spinning");

  let result = null;
  let failure = null;
  request.then(r => (result = r), e => (failure = e));

  return new Promise((resolve, reject) => {
    let ticks = 0;
    let teamStoppedAt = null;
    const finish = () => {
      clearInterval(timer);
      teamReel.classList.remove("spinning");
      eraReel.classList.remove("spinning");
      state.spinning = false;
      failure ? reject(failure) : resolve(result);
    };
    const timer = setInterval(() => {
      ticks++;
      if (failure) return finish();
      // Keep spinning past the stop tick until the server has answered.
      if (teamStoppedAt === null) {
        if (ticks >= TEAM_STOP_TICK && result) {
          $("reel-team-value").textContent = result.team;
          teamReel.classList.remove("spinning");
          teamStoppedAt = ticks;
        } else {
          $("reel-team-value").textContent = pickFrom(state.wheel.teams);
        }
      }
      if (teamStoppedAt !== null && ticks >= Math.max(ERA_STOP_TICK, teamStoppedAt + ERA_STOP_AFTER_TEAM)) {
        $("reel-era-value").textContent = result.era;
        return finish();
      }
      $("reel-era-value").textContent = pickFrom(state.wheel.eras);
    }, TICK_MS);
  });
}

// ---------- Draft rendering ----------

function respinHint() {
  const left = respinsLeft();
  if (!left) return " No re-spins left.";
  return ` Don't like this team? Re-spin (${left} left${state.phase === "coach" ? "" : " for your roster"}).`;
}

function poolHint() {
  if (state.phase === "coach") {
    if (!state.hasSpun)
      return `Roster set. Spin for your coach: a real manager of that team in that era. You get ${COACH_RESPINS} re-spins.`;
    if (state.coach) return `${state.coach.name} is your coach. Click the coach slot to undo.`;
    return "W vs PYTH = wins above what his teams' runs scored and allowed predicted, per 162 games. It's added to your record." + respinHint();
  }
  const hitters = state.phase === "hitters";
  if (phaseFull())
    return hitters
      ? "Lineup complete. Set your batting order, then move on to your pitching staff."
      : "Pitching staff complete. Time to draft your coach.";
  if (!state.hasSpun) {
    const what = hitters ? "nine hitters" : "five starters and three relievers";
    return `Draft your ${what}. Spin the reels to reveal a team & era.` +
      (hitters ? ` You get ${ROSTER_RESPINS} re-spins for your whole roster.` : ` ${state.respins} re-spins left.`);
  }
  if (state.pickThisSpin) return `Drafted ${state.pickThisSpin.name}. Spin for your next team.`;
  if (selectedCard()) return "Click a highlighted slot to place them.";
  return (hitters ? "Pick one hitter, then click an open position he can play." : "Pick one pitcher, then click an open rotation or bullpen slot.") + respinHint();
}

function poolAction() {
  if (state.phase === "hitters" && phaseFull()) return ["NEXT: PITCHING STAFF →", () => goToPhase("pitchers")];
  if (state.phase === "pitchers" && phaseFull()) return ["NEXT: DRAFT YOUR COACH →", () => goToPhase("coach")];
  if (state.phase === "coach" && state.coach) return ["SIMULATE SEASON →", simulateSeason];
  return null;
}

// Earned badges as chips (hover: the real stat and its percentile). Badges a
// season's data can't support (stats not recorded) are simply not shown.
function badgeRow(card) {
  const earned = (card.badges || []).map(
    b => `<span class="badge-chip" title="${escapeHtml(`${b.name}: ${b.detail}`)}">${escapeHtml(b.name.toUpperCase())}</span>`
  );
  return earned.length ? `<div class="badge-row">${earned.join("")}</div>` : "";
}

const badgeCount = card => (card.badges || []).length;

function cardElement(card, locked) {
  const el = document.createElement("div");
  el.className =
    "pool-card" +
    (card.tier ? ` tier-${card.tier}` : "") +
    (card.id === state.selectedId ? " selected" : "") +
    (locked ? " locked" : "");
  const meta = card.kind === "coach" ? `${card.years} · ${card.record}` : card.year;
  const value =
    card.kind === "coach" ? signed(card.stat.value) : card.stat.value.toFixed(card.kind === "pitcher" ? 2 : 1);
  el.innerHTML = `
    <div class="pinfo">
      <div class="badges">${card.positions.map(p => `<span class="pos-badge">${escapeHtml(p)}</span>`).join("")}</div>
      <div>
        <div class="pname">${escapeHtml(card.name)}</div>
        <div class="pmeta">${escapeHtml(meta)}${card.tier ? ` <span class="tier-tag">${card.tier === "diamond" ? "◆ " : ""}${card.tier.toUpperCase()}</span>` : ""}</div>
        ${badgeRow(card)}
      </div>
    </div>
    <div class="pstat">
      <span class="pstat-label">${escapeHtml(card.stat.label)}</span>
      <span class="pstat-value">${value}</span>
    </div>`;
  el.addEventListener("click", () => clickCard(card));
  return el;
}

function renderPool() {
  const panel = $("pool-panel");
  panel.innerHTML = "";
  $("pool-title").textContent = { hitters: "DRAFT POOL — HITTERS", pitchers: "DRAFT POOL — PITCHERS", coach: "COACH POOL" }[state.phase];

  const hint = document.createElement("p");
  hint.className = "pool-hint" + (state.error ? " error" : "");
  hint.textContent = state.error || poolHint();
  panel.appendChild(hint);

  const action = poolAction();
  if (action) {
    const button = document.createElement("button");
    button.className = "action-btn pool-action";
    button.textContent = action[0];
    button.addEventListener("click", action[1]);
    panel.appendChild(button);
  }

  const visible = state.pool.filter(card => card !== state.coach && !onRoster(card));
  const locked = state.pickThisSpin !== null;
  const groups = [[{ hitters: "HITTERS", pitchers: "PITCHERS", coach: "MANAGERS" }[state.phase], visible]];
  for (const [title, cards] of groups) {
    if (!cards.length) continue;
    const heading = document.createElement("div");
    heading.className = "pool-group";
    heading.textContent = title;
    panel.appendChild(heading);
    cards.forEach(card => panel.appendChild(cardElement(card, locked)));
  }
}

function renderWideSlot(el, text, filled, eligible) {
  el.classList.toggle("filled", filled);
  el.classList.toggle("eligible", eligible);
  el.querySelector(".slot-name").textContent = text;
}

function renderDiamond() {
  const selected = selectedCard();
  document.querySelectorAll(".pos-slot").forEach(el => {
    const slot = el.dataset.slot;
    const card = state.roster[slot];
    el.classList.toggle("filled", !!card);
    el.classList.toggle("eligible", !!selected && canPlace(selected, slot));
    el.querySelector(".pos-name").textContent = card ? tokenName(card.last) : "";
  });
  const dh = state.roster.DH;
  renderWideSlot($("dh-slot"), dh ? dh.name : "empty", !!dh, !!selected && canPlace(selected, "DH"));
}

function renderStaff() {
  const selected = selectedCard();
  for (const [containerId, slots] of [["rotation-slots", ROTATION_SLOTS], ["bullpen-slots", BULLPEN_SLOTS]]) {
    const container = $(containerId);
    container.innerHTML = "";
    slots.forEach(slot => {
      const card = state.roster[slot];
      const el = document.createElement("div");
      el.className =
        "staff-slot" + (card ? " filled" : "") + (selected && canPlace(selected, slot) ? " eligible" : "");
      el.innerHTML = `<span class="slot-role">${slot.slice(0, 2)} ${slot.slice(2)}</span>${card ? escapeHtml(card.name) : "empty"}`;
      el.addEventListener("click", () => clickSlot(slot));
      container.appendChild(el);
    });
  }
}

function renderCoachSlot() {
  const coach = state.coach;
  const text = coach ? `${coach.name} (${signed(coach.stat.value)} W vs PYTH)` : "spin for your coach";
  renderWideSlot($("coach-slot"), text, !!coach, false);
}

function renderSteps() {
  const current = PHASES.indexOf(state.phase);
  document.querySelectorAll("#stepper li").forEach(el => {
    const i = PHASES.indexOf(el.dataset.phase);
    el.classList.toggle("active", i === current);
    el.classList.toggle("done", i < current);
  });
  $("hitters-board").hidden = state.phase !== "hitters";
  $("pitchers-board").hidden = state.phase !== "pitchers";
  $("coach-board").hidden = state.phase !== "coach";

  const left = respinsLeft();
  const total = state.phase === "coach" ? COACH_RESPINS : ROSTER_RESPINS;
  $("spin-btn").textContent = isRespin() ? (left ? "RE-SPIN" : "NO RE-SPINS") : "SPIN";
  $("respin-count").textContent = `RE-SPINS ${left} / ${total}`;
}

function renderOrder() {
  const slotsEl = $("order-slots");
  slotsEl.innerHTML = "";
  state.order.forEach((card, i) => {
    const el = document.createElement("div");
    el.className = "order-slot" + (card ? "" : " empty");
    el.innerHTML = `<span class="order-num">${i + 1}</span>${card ? escapeHtml(card.name) : "empty"}`;
    el.addEventListener("click", () => {
      state.order[i] = null;
      render();
    });
    slotsEl.appendChild(el);
  });

  const tray = $("order-tray");
  tray.innerHTML = "";
  LINEUP_SLOTS.map(slot => state.roster[slot])
    .filter(card => card && !state.order.includes(card))
    .forEach(card => {
      const chip = document.createElement("div");
      chip.className = "order-chip";
      chip.textContent = card.name;
      chip.addEventListener("click", () => {
        const i = state.order.indexOf(null);
        if (i > -1) state.order[i] = card;
        render();
      });
      tray.appendChild(chip);
    });
}

function render() {
  renderPool();
  renderDiamond();
  renderOrder();
  renderStaff();
  renderCoachSlot();
  renderSteps();
  $("spin-btn").disabled = !canSpin();
}

// ---------- Season screen ----------

function showSeason(season) {
  $("draft-view").hidden = true;
  $("sim-view").hidden = false;
  window.scrollTo(0, 0);
  const { result, coach } = season;
  $("sb-label").textContent = `SEASON SIMULATION · COACH ${coach.name.toUpperCase()}`;
  playSeason(result.wins, season.constants.seasonGames, () => {
    $("sb-banner").hidden = result.losses !== 0;
    renderMath(season);
    $("sim-math").hidden = false;
    $("again-btn").hidden = false;
  });
}

// Ticks through every game so the record builds up, landing exactly on the projected record.
function playSeason(totalWins, games, onDone) {
  let game = 0;
  const timer = setInterval(() => {
    game++;
    const wins = Math.round((game * totalWins) / games);
    $("sb-wins").textContent = wins;
    $("sb-losses").textContent = game - wins;
    $("sb-game").textContent = `Game ${game} of ${games}`;
    $("sb-bar-fill").style.width = `${(game / games) * 100}%`;
    if (game === games) {
      clearInterval(timer);
      onDone();
    }
  }, SEASON_ANIMATION_MS / games);
}

function mathLine(label, value, total = false) {
  return `<div class="math-line${total ? " total" : ""}"><span>${label}</span><span class="num">${value}</span></div>`;
}

function renderMath({ result, coach, constants }) {
  const base = constants.leagueAvgRuns.toFixed(0);
  const exp = constants.pythagExponent;
  const rs = result.projected_runs_scored.toFixed(0);
  const ra = result.projected_runs_allowed.toFixed(0);

  const hitterRuns = new Map(LINEUP_SLOTS.map((slot, i) => [state.roster[slot], [slot, result.hitter_runs[i]]]));
  $("offense-table").innerHTML =
    `<tr><th>#</th><th>Hitter</th><th class="num">WAR</th><th class="num">Runs vs avg</th><th class="num">Badges</th></tr>` +
    state.order
      .map((card, i) => {
        const [slot, runs] = hitterRuns.get(card);
        return `<tr><td>${i + 1}</td><td>${escapeHtml(card.name)} <span class="muted">${card.year} · ${slot}</span></td>
          <td class="num">${card.stat.value.toFixed(1)}</td><td class="num">${signed(runs)}</td>
          <td class="num" title="${escapeHtml((card.badges || []).map(b => b.name).join(", "))}">${badgeCount(card) ? signed(badgeCount(card) * constants.badgeRuns) : "—"}</td></tr>`;
      })
      .join("");
  $("offense-lines").innerHTML =
    mathLine(`Lineup runs above average (every starter at ${constants.batterSeasonPA} PA)`, signed(result.lineup_wraa_full_season)) +
    mathLine(
      `Badges (${result.lineup_badge_runs / constants.badgeRuns} × ${constants.badgeRuns} runs)`,
      signed(result.lineup_badge_runs)
    ) +
    mathLine(
      `Runs scored = ${base} league-average ${plusMinus(result.lineup_wraa_full_season)} ${plusMinus(result.lineup_badge_runs)} badges`,
      rs,
      true
    );

  const staffSlots = [...ROTATION_SLOTS, ...BULLPEN_SLOTS];
  $("pitching-table").innerHTML =
    `<tr><th>Role</th><th>Pitcher</th><th class="num">FIP</th><th class="num">Sim IP</th><th class="num">Runs saved</th><th class="num">Badges</th></tr>` +
    staffSlots
      .map((slot, i) => {
        const card = state.roster[slot];
        return `<tr><td>${slot}</td><td>${escapeHtml(card.name)} <span class="muted">${card.year}</span></td>
          <td class="num">${card.stat.value.toFixed(2)}</td><td class="num">${result.pitcher_ip[i].toFixed(0)}</td>
          <td class="num">${signed(result.pitcher_runs[i])}</td>
          <td class="num" title="${escapeHtml((card.badges || []).map(b => b.name).join(", "))}">${badgeCount(card) ? signed(badgeCount(card) * constants.badgeRuns) : "—"}</td></tr>`;
      })
      .join("");
  $("pitching-lines").innerHTML =
    mathLine("Staff runs saved vs. league average", signed(result.staff_runs_saved_full_season)) +
    mathLine(
      `Badges (${result.staff_badge_runs / constants.badgeRuns} × ${constants.badgeRuns} runs saved)`,
      signed(result.staff_badge_runs)
    ) +
    mathLine(
      `Runs allowed = ${base} league-average ${plusMinus(-result.staff_runs_saved_full_season)} ${plusMinus(-result.staff_badge_runs)} badges`,
      ra,
      true
    );

  $("record-lines").innerHTML =
    mathLine(`Pythagorean win% = ${rs}<sup>${exp}</sup> / (${rs}<sup>${exp}</sup> + ${ra}<sup>${exp}</sup>)`, result.win_pct.toFixed(3)) +
    mathLine(`× ${constants.seasonGames} games`, `${result.pythag_wins.toFixed(1)} wins`) +
    mathLine(
      `Coach ${escapeHtml(coach.name)} (${escapeHtml(coach.record)}, expected ${coach.expectedWins} W)`,
      `${signed(result.coach_wins)} wins`
    ) +
    mathLine(`Final record (rounded, capped at ${constants.seasonGames} wins)`, `${result.wins}-${result.losses}`, true);
}

// ---------- Init ----------

async function init() {
  document.querySelectorAll(".pos-slot").forEach(el => el.addEventListener("click", () => clickSlot(el.dataset.slot)));
  $("dh-slot").addEventListener("click", () => clickSlot("DH"));
  $("coach-slot").addEventListener("click", undoCoach);
  $("spin-btn").addEventListener("click", spin);
  $("again-btn").addEventListener("click", () => location.reload());

  try {
    state.wheel = await api("/api/wheel");
  } catch (err) {
    state.error = "Couldn't reach the draft server. Start it with: python -m warball.server";
  }
  render();
}

init();
