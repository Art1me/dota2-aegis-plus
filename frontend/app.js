// AegisPlus Client Logic
let audioEnabled = true;
let activeDraftRole = "Carry";
let isLockedClickthrough = false;
let latestData = null;
let lastAlertIds = new Set();
let allHeroesList = [];
let manualEnemyHeroes = [];
let activeToasts = new Map(); // id -> { elem, expireAt, baseText, secondsLeft }

// Web Audio synthesizer for crisp in-game audio cues
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

function playSoundCue(type) {
  if (!audioEnabled || audioCtx.state === 'suspended') {
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    if (!audioEnabled) return;
  }

  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.connect(gain);
  gain.connect(audioCtx.destination);

  const now = audioCtx.currentTime;

  if (type === 'critical' || type === 'wisdom_soon') {
    osc.frequency.setValueAtTime(880, now);
    osc.frequency.setValueAtTime(1174.66, now + 0.15);
    gain.gain.setValueAtTime(0.2, now);
    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
    osc.start(now);
    osc.stop(now + 0.4);
  } else if (type === 'warning' || type === 'lotus_soon') {
    osc.frequency.setValueAtTime(587.33, now);
    osc.frequency.setValueAtTime(880, now + 0.12);
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
    osc.start(now);
    osc.stop(now + 0.35);
  } else {
    osc.frequency.setValueAtTime(523.25, now);
    gain.gain.setValueAtTime(0.1, now);
    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
    osc.start(now);
    osc.stop(now + 0.2);
  }
}

function speakAlert(text) {
  if (!audioEnabled || !('speechSynthesis' in window)) return;
  try {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ru-RU';
    utterance.rate = 1.1;
    utterance.volume = 0.8;
    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn("Speech synthesis error", e);
  }
}

// Fetch all heroes for manual picker
function fetchHeroesList() {
  fetch("/api/heroes")
    .then(r => r.json())
    .then(list => {
      allHeroesList = list;
    })
    .catch(e => console.warn("Failed to load heroes list:", e));
}

// SSE Connection
function initEventSource() {
  const evtSource = new EventSource("/api/events");

  evtSource.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);
      latestData = data;
      renderUI(data);
    } catch (err) {
      console.error("Error parsing GSI stream:", err);
    }
  };

  evtSource.onerror = function() {
    document.getElementById("statusDot").classList.remove("connected");
    document.getElementById("statusText").innerText = "Переподключение...";
  };
}

// Main UI Render Function
function renderUI(data) {
  const isConnected = data.connected;
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");

  if (isConnected) {
    statusDot.classList.add("connected");
    statusText.innerText = data.status || "В игре";
  } else {
    statusDot.classList.remove("connected");
    statusText.innerText = data.status || "Ожидание Dota 2";
  }

  // Update sync settings if received
  if (data.settings) {
    if (data.settings.manual_enemy_heroes && manualEnemyHeroes.length === 0) {
      manualEnemyHeroes = data.settings.manual_enemy_heroes;
      renderManualEnemySlots();
    }
  }

  // 1. Clock & Day/Night (Proper Russian Declension)
  if (data.radar) {
    document.getElementById("clockDisplay").innerText = data.radar.clock_formatted || "00:00";
    document.getElementById("dayNightSub").innerText = data.radar.day_night_title || "День";

    renderTimerChips(data.radar.timers || [], data.radar.roshan);
    renderAlerts(data.radar.active_alerts || []);
  }

  // 2. Performance & 4 Buyback Statuses
  if (data.performance) {
    const perf = data.performance;
    const gradeBadge = document.getElementById("gradeBadge");
    const gradeLetter = document.getElementById("gradeLetter");
    const gradeLabel = document.getElementById("gradeLabel");

    gradeLetter.innerText = perf.grade;
    gradeLabel.innerText = perf.grade_label;
    gradeBadge.style.background = perf.grade_color + "22";
    gradeBadge.style.color = perf.grade_color;

    const b = perf.benchmarks;
    document.getElementById("metricCS").innerText = `${b.current_cs} / ${b.target_cs} target`;
    
    const deltaCSEl = document.getElementById("deltaCS");
    deltaCSEl.innerText = (b.delta_cs >= 0 ? "+" : "") + b.delta_cs;
    deltaCSEl.className = "metric-delta " + (b.delta_cs >= 0 ? "positive" : "negative");

    document.getElementById("metricNW").innerText = `${b.current_nw.toLocaleString()} 💰`;
    const deltaNWEl = document.getElementById("deltaNW");
    deltaNWEl.innerText = (b.delta_nw >= 0 ? "+" : "") + b.delta_nw.toLocaleString() + "g";
    deltaNWEl.className = "metric-delta " + (b.delta_nw >= 0 ? "positive" : "negative");

    document.getElementById("metricGPM").innerText = `${b.current_gpm} / ${b.current_xpm}`;

    // Buyback (4 Statuses: READY, AT_RISK, DEFICIT, COOLDOWN)
    if (perf.buyback) {
      const bb = perf.buyback;
      const bbStatusBox = document.getElementById("bbStatusBox");
      const bbStatusText = document.getElementById("bbStatusText");
      const bbCost = document.getElementById("bbCost");
      const bbSurplusLabel = document.getElementById("bbSurplusLabel");
      const bbRiskNote = document.getElementById("bbRiskNote");

      bbCost.innerText = `${bb.cost} 💰`;

      if (bb.status === "READY") {
        bbStatusBox.style.borderColor = "var(--color-green)";
        bbStatusText.style.color = "var(--color-green)";
        bbStatusText.innerText = "Выкуп готов";
        bbSurplusLabel.innerText = `+${bb.surplus}g резерв`;
        bbSurplusLabel.style.color = "var(--color-green)";
        bbRiskNote.innerText = bb.death_penalty > 0 ? `Потеря при смерти: -${bb.death_penalty}g` : "";
      } else if (bb.status === "AT_RISK") {
        bbStatusBox.style.borderColor = "var(--color-yellow)";
        bbStatusText.style.color = "var(--color-yellow)";
        bbStatusText.innerText = "Риск потери выкупа";
        bbSurplusLabel.innerText = `-${Math.abs(bb.surplus_after_death)}g при смерти`;
        bbSurplusLabel.style.color = "var(--color-yellow)";
        bbRiskNote.innerText = `Хватает сейчас, но смерть отнимет ${bb.death_penalty}g!`;
      } else if (bb.status === "COOLDOWN") {
        bbStatusBox.style.borderColor = "var(--color-purple)";
        bbStatusText.style.color = "var(--color-purple)";
        bbStatusText.innerText = `КД выкупа (${bb.cooldown}с)`;
        bbSurplusLabel.innerText = `КД: ${bb.cooldown}с`;
        bbSurplusLabel.style.color = "var(--color-purple)";
        bbRiskNote.innerText = "";
      } else {
        // DEFICIT
        bbStatusBox.style.borderColor = "var(--color-red)";
        bbStatusText.style.color = "var(--color-red)";
        bbStatusText.innerText = "Не хватает золота";
        bbSurplusLabel.innerText = `${bb.surplus}g дефицит`;
        bbSurplusLabel.style.color = "var(--color-red)";
        bbRiskNote.innerText = "";
      }
    }
  }

  // 3. Situational Items (Fixed icons & Steam CDN)
  if (data.recommended_items) {
    renderItems(data.recommended_items);
  }

  // 4. Draft Assistant
  if (data.draft) {
    renderDraft(data.draft);
    if (data.game_phase === "DRAFT") {
      document.getElementById("draftOverlay").classList.remove("hidden");
    }
  }
}

function renderTimerChips(timers, roshan) {
  const container = document.getElementById("timerChips");
  container.innerHTML = "";

  timers.forEach(t => {
    const chip = document.createElement("div");
    chip.className = "timer-chip";
    if (t.seconds_left <= 20) {
      chip.classList.add("urgent");
    } else if (t.seconds_left <= 45) {
      chip.classList.add("warning");
    }

    const min = Math.floor(t.seconds_left / 60);
    const sec = t.seconds_left % 60;
    const timeStr = `${min}:${sec < 10 ? '0' : ''}${sec}`;

    let icon = "⏱️";
    if (t.id === "water_rune") icon = "💧";
    if (t.id === "lotus") icon = "🌸";
    if (t.id === "wisdom") icon = "🌟";
    if (t.id === "power_rune") icon = "⚡";
    if (t.id === "tormentor") icon = "🛡️";

    chip.innerHTML = `<span>${icon} ${t.name}:</span><span class="chip-time">${timeStr}</span>`;
    container.appendChild(chip);
  });

  if (roshan) {
    const roshChip = document.createElement("div");
    roshChip.className = "timer-chip";
    roshChip.innerHTML = `<span>⚔️ Рошан:</span><span class="chip-time">${roshan.window || 'Жив'}</span>`;
    container.appendChild(roshChip);
  }
}

// Compact Toast Alerts with Live Decrementing Seconds and 6s Auto-Fade
function renderAlerts(alerts) {
  const banner = document.getElementById("alertsBanner");

  alerts.forEach(a => {
    if (!activeToasts.has(a.id)) {
      const toast = document.createElement("div");
      toast.className = `alert-toast ${a.severity || 'info'}`;
      toast.id = `toast_${a.id}`;

      // Extract seconds if any in text
      let secMatch = a.text.match(/(\d+)\s*с/);
      let secLeft = secMatch ? parseInt(secMatch[1], 10) : null;

      toast.innerHTML = `
        <span style="font-size: 14px;">⚠️</span>
        <div style="flex: 1;">
          <div style="font-weight: 700; color: #fff;">${a.title}</div>
          <div class="toast-body" style="font-size: 11px; margin-top: 2px;">${a.text}</div>
        </div>
      `;

      banner.appendChild(toast);

      // Audio notification on spawn
      if (!lastAlertIds.has(a.id)) {
        playSoundCue(a.sound || a.severity);
        if (a.severity === 'critical') {
          speakAlert(a.title);
        }
      }

      // Schedule auto-hide after 6 seconds
      const fadeTimer = setTimeout(() => {
        toast.classList.add("fade-out");
      }, 5400);

      const removeTimer = setTimeout(() => {
        toast.remove();
        activeToasts.delete(a.id);
      }, 6000);

      activeToasts.set(a.id, {
        elem: toast,
        secLeft: secLeft,
        baseText: a.text,
        fadeTimer: fadeTimer,
        removeTimer: removeTimer
      });
    }
  });

  lastAlertIds = new Set(alerts.map(a => a.id));
}

// Tick down seconds in active toasts every 1s
setInterval(() => {
  activeToasts.forEach((item, id) => {
    if (item.secLeft !== null && item.secLeft > 0) {
      item.secLeft -= 1;
      const bodyEl = item.elem.querySelector(".toast-body");
      if (bodyEl) {
        bodyEl.innerText = item.baseText.replace(/\d+\s*с/, `${item.secLeft}с`);
      }
    }
  });
}, 1000);

// Situational Items with Fixed Container and Steam CDN
function renderItems(items) {
  const container = document.getElementById("itemsContainer");
  if (!items || items.length === 0) {
    container.innerHTML = `<span style="color: var(--text-muted); font-size: 11px;">Оптимальные предметы вычисляются по пику...</span>`;
    return;
  }

  container.innerHTML = "";
  items.forEach(it => {
    const cleanName = it.id.replace("item_", "");
    const imgUrl = it.image_url || `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/${cleanName}.png`;

    const entry = document.createElement("div");
    entry.className = "item-entry";
    entry.innerHTML = `
      <div class="item-icon-box">
        <img src="${imgUrl}" alt="${it.name}" class="item-img" onerror="this.src='https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/branches.png'">
      </div>
      <div class="item-info">
        <div class="item-name">${it.name}</div>
        <div class="item-advice">${it.advice}</div>
        <div class="item-reasons">${it.reasons.length > 0 ? '• ' + it.reasons.join(', ') : ''}</div>
      </div>
    `;
    container.appendChild(entry);
  });
}

// Draft Assistant & Manual Enemy Heroes
function renderDraft(draft) {
  const radAdv = draft.win_advantage_pct || 50;
  const direAdv = Math.round((100 - radAdv) * 10) / 10;

  document.getElementById("radAdvantage").innerText = radAdv + "%";
  document.getElementById("direAdvantage").innerText = direAdv + "%";
  document.getElementById("advantageFill").style.width = radAdv + "%";

  const recGrid = document.getElementById("draftRecGrid");
  recGrid.innerHTML = "";

  const roleList = draft.recommendations ? (draft.recommendations[activeDraftRole] || []) : [];
  if (roleList.length === 0) {
    recGrid.innerHTML = `<span style="color: var(--text-muted); font-size: 12px;">Герои для выбора...</span>`;
  } else {
    roleList.forEach(hero => {
      const card = document.createElement("div");
      card.className = "hero-rec-card";
      card.innerHTML = `
        <div>
          <div class="hero-name">${hero.display_name}</div>
          <div class="hero-reasons">${hero.reasons.length > 0 ? hero.reasons.join(", ") : "Сильный пик меты"}</div>
        </div>
        <div class="hero-score-badge">+${hero.score}</div>
      `;
      recGrid.appendChild(card);
    });
  }

  const banList = document.getElementById("banList");
  if (draft.bans && draft.bans.length > 0) {
    banList.innerHTML = draft.bans.map(b => `• <strong>${b.display_name}</strong>: ${b.reason}`).join("<br>");
  } else {
    banList.innerText = "Определяется на основе пиков врагов";
  }

  const gapsList = document.getElementById("gapsList");
  if (draft.missing_composition && draft.missing_composition.length > 0) {
    gapsList.innerHTML = draft.missing_composition.map(g => `• ${g}`).join("<br>");
  } else {
    gapsList.innerText = "Баланс сетапа в норме";
  }
}

// Manual Enemy Hero Slots Render
function renderManualEnemySlots() {
  const grid = document.getElementById("enemySlotsGrid");
  grid.innerHTML = "";

  document.getElementById("manualEnemiesCount").innerText = `${manualEnemyHeroes.length}/5 выбрано`;

  for (let i = 0; i < 5; i++) {
    const slot = document.createElement("div");
    const heroName = manualEnemyHeroes[i];

    if (heroName) {
      slot.className = "enemy-slot filled";
      const hObj = allHeroesList.find(h => h.name === heroName || h.id === heroName || h.display_name.toLowerCase() === heroName.toLowerCase());
      const dName = hObj ? hObj.display_name : heroName;

      slot.innerHTML = `
        <span class="enemy-slot-name">${dName}</span>
        <span class="enemy-slot-remove" data-index="${i}" title="Удалить">✕</span>
      `;
    } else {
      slot.className = "enemy-slot";
      slot.innerHTML = `<span style="color: var(--text-muted);">+ Слот ${i + 1}</span>`;
      slot.style.cursor = "pointer";
      slot.onclick = () => {
        document.getElementById("heroSearchInput").focus();
      };
    }

    grid.appendChild(slot);
  }

  // Remove buttons
  grid.querySelectorAll(".enemy-slot-remove").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.getAttribute("data-index"), 10);
      manualEnemyHeroes.splice(idx, 1);
      syncManualEnemies();
    };
  });
}

function syncManualEnemies() {
  renderManualEnemySlots();
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manual_enemy_heroes: manualEnemyHeroes })
  });
}

// Filter Hero Search Dropdown
function setupHeroSearch() {
  const input = document.getElementById("heroSearchInput");
  const dropdown = document.getElementById("heroDropdown");

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      dropdown.classList.add("hidden");
      return;
    }

    const matches = allHeroesList.filter(h => {
      if (h.display_name.toLowerCase().includes(q)) return true;
      if (h.name.toLowerCase().includes(q)) return true;
      if (h.aliases && h.aliases.some(a => a.toLowerCase().includes(q))) return true;
      return false;
    }).slice(0, 10);

    if (matches.length === 0) {
      dropdown.innerHTML = `<div style="padding: 8px 12px; color: var(--text-muted); font-size: 11px;">Герой не найден</div>`;
      dropdown.classList.remove("hidden");
      return;
    }

    dropdown.innerHTML = "";
    matches.forEach(m => {
      const item = document.createElement("div");
      item.className = "hero-dropdown-item";
      item.innerHTML = `
        <span style="font-weight: 700;">${m.display_name}</span>
        <span style="font-size: 10px; color: var(--text-muted);">${m.role}</span>
      `;
      item.onclick = () => {
        if (manualEnemyHeroes.length < 5 && !manualEnemyHeroes.includes(m.name)) {
          manualEnemyHeroes.push(m.name);
          syncManualEnemies();
        }
        input.value = "";
        dropdown.classList.add("hidden");
      };
      dropdown.appendChild(item);
    });

    dropdown.classList.remove("hidden");
  });

  document.addEventListener("click", (e) => {
    if (!document.getElementById("heroSearchWrapper").contains(e.target)) {
      dropdown.classList.add("hidden");
    }
  });
}

// Global Lock / Click-Through State Controller
window.setLockState = function(locked) {
  isLockedClickthrough = locked;
  const container = document.getElementById("hudContainer");
  const btn = document.getElementById("btnClickthrough");
  const lockIcon = document.getElementById("lockIcon");
  const interactives = document.querySelectorAll(".hud-card, .controls-cluster, .macro-radar");

  if (isLockedClickthrough) {
    if (container) container.classList.add("locked-hud");
    btn.classList.add("active");
    lockIcon.innerText = "🔒 Разблок";
    interactives.forEach(el => el.classList.remove("interactive"));
    btn.classList.add("interactive");
  } else {
    if (container) container.classList.remove("locked-hud");
    btn.classList.remove("active");
    lockIcon.innerText = "🔓 Меню";
    interactives.forEach(el => el.classList.add("interactive"));
  }

  // Notify WebKitGTK host if running in native overlay
  if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.overlay) {
    window.webkit.messageHandlers.overlay.postMessage({ action: "set_lock", locked: isLockedClickthrough });
  }

  // Sync with backend
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clickthrough: isLockedClickthrough })
  });
};

window.toggleClickthrough = function() {
  window.setLockState(!isLockedClickthrough);
};

// Event Listeners on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  fetchHeroesList();
  initEventSource();
  setupHeroSearch();
  renderManualEnemySlots();

  document.getElementById("rankSelector").addEventListener("change", (e) => {
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rank: e.target.value })
    });
  });

  document.getElementById("roleSelector").addEventListener("change", (e) => {
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: e.target.value })
    });
  });

  document.getElementById("btnAudioToggle").addEventListener("click", () => {
    audioEnabled = !audioEnabled;
    const btn = document.getElementById("btnAudioToggle");
    const icon = document.getElementById("audioIcon");
    if (audioEnabled) {
      btn.classList.add("active");
      icon.innerText = "🔊 Звук";
    } else {
      btn.classList.remove("active");
      icon.innerText = "🔇 Выкл";
    }
  });

  document.getElementById("btnDraftToggle").addEventListener("click", () => {
    document.getElementById("draftOverlay").classList.toggle("hidden");
  });

  document.getElementById("btnCloseDraft").addEventListener("click", () => {
    document.getElementById("draftOverlay").classList.add("hidden");
  });

  document.querySelectorAll(".draft-tab").forEach(tab => {
    tab.addEventListener("click", (e) => {
      document.querySelectorAll(".draft-tab").forEach(t => t.classList.remove("active"));
      e.target.classList.add("active");
      activeDraftRole = e.target.getAttribute("data-role");
      if (latestData && latestData.draft) {
        renderDraft(latestData.draft);
      }
    });
  });

  document.getElementById("btnSimulate").addEventListener("click", () => {
    fetch("/api/simulate", { method: "POST" });
  });

  document.getElementById("btnClickthrough").addEventListener("click", () => {
    window.toggleClickthrough();
  });
});
