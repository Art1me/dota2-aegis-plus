// AegisPlus Client Logic
let audioEnabled = true;
let mobileHapticEnabled = true;
let activeDraftRole = "Carry";
let isLockedClickthrough = false;
let latestData = null;
let lastAlertIds = new Set();
let alertedTimerIds = new Set();
let allHeroesList = [];
let manualEnemyHeroes = [];
let activeToasts = new Map(); // id -> { elem, expireAt, baseText, secondsLeft }

let currentMobileItemStage = "starting";
let currentDesktopItemStage = "core";
let currentDesktopBuildView = "items";
let lastStackAlertPlayedMin = -1;

function triggerHaptic(pattern = 50) {
  if (mobileHapticEnabled && navigator.vibrate) {
    try {
      navigator.vibrate(pattern);
    } catch (e) {
      // Ignore vibration error on unsupported desktop browsers
    }
  }
}

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

function copyToClipboard(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(err => {
      console.warn("Clipboard write failed:", err);
    });
  }
}

function showSingleToast(title, text, severity = "info") {
  renderAlerts([{
    id: "toast_" + Date.now(),
    title: title,
    text: text,
    severity: severity,
    sound: severity === "critical" ? "wisdom_soon" : "power_soon"
  }]);
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

  // Update Mobile Companion UI
  renderMobileUI(data);

  // Update sync settings if received

  if (data.settings) {
    if (data.settings.rank) {
      const rankVal = data.settings.rank;
      const rankElem = document.getElementById("rankSelectValue");
      if (rankElem) rankElem.innerText = rankVal;
      const nativeRank = document.getElementById("rankSelector");
      if (nativeRank) nativeRank.value = rankVal;
      document.querySelectorAll("#rankSelectOptions .custom-select-option").forEach(opt => {
        opt.classList.toggle("selected", opt.getAttribute("data-value") === rankVal);
      });
    }
    if (data.settings.role) {
      const roleVal = data.settings.role;
      const roleLabels = { "Carry": "Pos 1 (Carry)", "Mid": "Pos 2 (Mid)", "Offlane": "Pos 3 (Offlane)", "Support": "Pos 4/5 (Support)" };
      const roleElem = document.getElementById("roleSelectValue");
      if (roleElem) roleElem.innerText = roleLabels[roleVal] || roleVal;
      const nativeRole = document.getElementById("roleSelector");
      if (nativeRole) nativeRole.value = roleVal;
      document.querySelectorAll("#roleSelectOptions .custom-select-option").forEach(opt => {
        opt.classList.toggle("selected", opt.getAttribute("data-value") === roleVal);
      });
    }
    if (data.settings.manual_enemy_heroes && manualEnemyHeroes.length === 0) {
      manualEnemyHeroes = data.settings.manual_enemy_heroes;
      renderManualEnemySlots();
    }
  }

  // 1. Clock & Day/Night (Proper Russian Declension)
  if (data.radar) {
    document.getElementById("clockDisplay").innerText = data.radar.clock_formatted || "00:00";
    document.getElementById("dayNightSub").innerText = data.radar.day_night_title || "День";

    renderTimerChips(data.radar.timers || [], data.radar.roshan, data.radar.glyph);
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
    document.getElementById("metricCS").innerText = `${b.current_cs} / ${b.target_cs}`;
    updateDeltaBadge("deltaCSBadge", b.cs_arrow || "▲", (b.delta_cs >= 0 ? "+" : "") + b.delta_cs, b.cs_status === "ahead");

    document.getElementById("metricNW").innerText = `${b.current_nw.toLocaleString()} 💰`;
    updateDeltaBadge("deltaNWBadge", b.nw_arrow || "▲", (b.delta_nw >= 0 ? "+" : "") + b.delta_nw.toLocaleString() + "g", b.nw_status === "ahead");

    document.getElementById("metricGPM").innerText = `${b.current_gpm} / ${b.current_xpm}`;
    updateDeltaBadge("deltaGPMBadge", b.gpm_arrow || "▲", (b.delta_gpm >= 0 ? "+" : "") + b.delta_gpm, b.gpm_status === "ahead");

    // Render Desktop KDA Plan vs Actual Grid & Plan Verdict
    renderKDABenchmarks(b, "desktop");

    const rollingGPMEl = document.getElementById("metricRollingGPM");
    if (rollingGPMEl) {
      rollingGPMEl.innerText = `3м: ${b.rolling_gpm !== undefined ? b.rolling_gpm : b.current_gpm} GPM`;
    }
    const highTempoEl = document.getElementById("highTempoBadge");
    if (highTempoEl) {
      if (b.is_high_tempo) {
        highTempoEl.classList.remove("hidden");
      } else {
        highTempoEl.classList.add("hidden");
      }
    }

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

  // 3. Situational Items & Full Item Stages & Next Recommended Item
  if (data.next_item) {
    renderNextItem(data.next_item);
  }
  renderItemProgression(data.item_build, data.recommended_items);

  // 4. Dota Plus Damage Breakdown
  if (data.damage_breakdown) {
    renderDamageBreakdown(data.damage_breakdown);
  }

  // 5. Dota Plus Net Worth Graph
  renderNetWorthGraph(data.nw_history || [], data.performance ? data.performance.benchmarks : null, "desktopNWSvgContent", 320, 100);
  renderNetWorthGraph(data.nw_history || [], data.performance ? data.performance.benchmarks : null, "mobileNWSvgContent", 320, 120);

  // 6. Dota Plus Ability & Talent Progression
  if (data.ability_build) {
    const lvl = (data.player && data.player.hero_level) || 1;
    renderAbilityBuild(data.ability_build, lvl);
  }

  // 7. Draft Assistant
  if (data.draft) {
    renderDraft(data.draft);
    if (data.game_phase === "DRAFT") {
      document.getElementById("draftOverlay").classList.remove("hidden");
    }
  }
}

function renderTimerChips(timers, roshan, glyph) {
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
    roshChip.className = "timer-chip clickable";

    if (roshan.chat_string) {
      roshChip.title = `Кликните, чтобы скопировать тайминг в буфер:\n${roshan.chat_string}\nТекущее логово: ${roshan.pit_location}`;
      roshChip.onclick = () => {
        copyToClipboard(roshan.chat_string);
        showSingleToast("⚔️ Тайминг Рошана", `Скопировано: ${roshan.chat_string}`, "info");
      };
    } else {
      roshChip.title = `Текущее логово: ${roshan.pit_location}`;
    }

    if (roshan.aegis_left > 0) {
      const aMin = Math.floor(roshan.aegis_left / 60);
      const aSec = roshan.aegis_left % 60;
      const aStr = `${aMin}:${aSec < 10 ? '0' : ''}${aSec}`;
      if (roshan.aegis_left <= 30) {
        roshChip.classList.add("urgent");
      } else {
        roshChip.classList.add("warning");
      }
      roshChip.innerHTML = `<span>🛡️ Аегис:</span><span class="chip-time">${aStr}</span>`;
    } else if (roshan.status === "in_window") {
      roshChip.classList.add("urgent");
      roshChip.innerHTML = `<span>⚔️ Рошан:</span><span class="chip-time">${roshan.window}</span>`;
    } else if (roshan.status === "respawning") {
      roshChip.classList.add("warning");
      roshChip.innerHTML = `<span>⚔️ Рошан:</span><span class="chip-time">${roshan.window}</span>`;
    } else {
      roshChip.innerHTML = `<span>⚔️ Рошан:</span><span class="chip-time">Жив</span>`;
    }
    container.appendChild(roshChip);
  }

  if (glyph && glyph.is_on_cooldown) {
    const glyphChip = document.createElement("div");
    glyphChip.className = "timer-chip warning";
    glyphChip.title = "Перезарядка вражеского укрепления строений (300с)";
    glyphChip.innerHTML = `<span>🛡️ Глиф:</span><span class="chip-time">${glyph.status}</span>`;
    container.appendChild(glyphChip);
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

// Custom Wayland Layer-Shell Dropdown Selectors
function setupCustomSelects() {
  const configs = [
    { containerId: "customRankSelect", triggerId: "rankSelectTrigger", valueId: "rankSelectValue", optionsId: "rankSelectOptions", selectId: "rankSelector", settingKey: "rank" },
    { containerId: "customRoleSelect", triggerId: "roleSelectTrigger", valueId: "roleSelectValue", optionsId: "roleSelectOptions", selectId: "roleSelector", settingKey: "role" }
  ];

  configs.forEach(cfg => {
    const container = document.getElementById(cfg.containerId);
    const trigger = document.getElementById(cfg.triggerId);
    const valueSpan = document.getElementById(cfg.valueId);
    const optionsPanel = document.getElementById(cfg.optionsId);
    const nativeSelect = document.getElementById(cfg.selectId);

    if (!container || !trigger || !optionsPanel || !nativeSelect) return;

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = container.classList.contains("open");
      // Close other dropdowns
      document.querySelectorAll(".custom-select").forEach(cs => {
        cs.classList.remove("open");
        const panel = cs.querySelector(".custom-select-options");
        if (panel) panel.classList.add("hidden");
      });

      if (!isOpen) {
        container.classList.add("open");
        optionsPanel.classList.remove("hidden");
      }
    });

    optionsPanel.querySelectorAll(".custom-select-option").forEach(opt => {
      opt.addEventListener("click", (e) => {
        e.stopPropagation();
        const val = opt.getAttribute("data-value");
        const text = opt.innerText;

        valueSpan.innerText = text;
        nativeSelect.value = val;

        optionsPanel.querySelectorAll(".custom-select-option").forEach(o => o.classList.remove("selected"));
        opt.classList.add("selected");

        container.classList.remove("open");
        optionsPanel.classList.add("hidden");

        fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [cfg.settingKey]: val })
        });
      });
    });
  });

  // Global click outside listener to close dropdowns
  document.addEventListener("click", () => {
    document.querySelectorAll(".custom-select").forEach(cs => {
      cs.classList.remove("open");
      const panel = cs.querySelector(".custom-select-options");
      if (panel) panel.classList.add("hidden");
    });
  });
}

function renderMobileUI(data) {
  const container = document.getElementById("mobileCompanion");
  if (!container) return;

  // Status & Connection
  const mobStatus = document.getElementById("mobileStatusText");
  if (mobStatus) {
    mobStatus.innerText = data.connected ? (data.status || "В игре") : "Ожидание Dota 2";
    mobStatus.style.color = data.connected ? "#10b981" : "#94a3b8";
  }

  // Clock & Scores
  if (data.radar) {
    const clockEl = document.getElementById("mobileMatchClock");
    if (clockEl) clockEl.innerText = data.radar.clock_formatted || "00:00";
    
    // Scores
    const radScore = document.getElementById("mobileScoreRad");
    const direScore = document.getElementById("mobileScoreDire");
    const m = data.match_info || (data.raw && data.raw.map) || {};
    const rScoreVal = m.radiant_score !== undefined ? m.radiant_score : 0;
    const dScoreVal = m.dire_score !== undefined ? m.dire_score : 0;
    if (radScore) radScore.innerText = rScoreVal;
    if (direScore) direScore.innerText = dScoreVal;

    // Dota Plus Live Win Probability Bar calculation
    const diff = rScoreVal - dScoreVal;
    let radWinChance = 50 + diff * 2.5;
    radWinChance = Math.max(15, Math.min(85, Math.round(radWinChance)));
    const direWinChance = 100 - radWinChance;

    const fillRad = document.getElementById("winMeterFillRad");
    const fillDire = document.getElementById("winMeterFillDire");
    const divMeter = document.getElementById("winMeterDivider");
    const labelRad = document.getElementById("winLabelRad");
    const labelDire = document.getElementById("winLabelDire");
    const leadText = document.getElementById("winMeterLead");

    if (fillRad) fillRad.style.width = `${radWinChance}%`;
    if (fillDire) fillDire.style.width = `${direWinChance}%`;
    if (divMeter) divMeter.style.left = `${radWinChance}%`;
    if (labelRad) labelRad.innerText = `Radiant ${radWinChance}%`;
    if (labelDire) labelDire.innerText = `Dire ${direWinChance}%`;

    if (leadText) {
      if (Math.abs(diff) <= 1) {
        leadText.innerText = "Равные шансы";
        leadText.style.color = "#e5c158";
      } else if (diff > 1) {
        leadText.innerText = `Преимущество Radiant (+${diff})`;
        leadText.style.color = "#10b981";
      } else {
        leadText.innerText = `Преимущество Dire (+${Math.abs(diff)})`;
        leadText.style.color = "#ef4444";
      }
    }


    // Hero stats
    const p = data.player || (data.raw && data.raw.player) || {};
    const heroRaw = p.hero_name || (data.raw && data.raw.hero && data.raw.hero.name) || "";
    const hName = document.getElementById("mobileHeroName");
    if (hName) {
      const cleanHero = heroRaw.replace("npc_dota_hero_", "").replace(/_/g, " ").toUpperCase();
      hName.innerText = cleanHero || "Герой не выбран";
    }
    const hLvl = document.getElementById("mobileHeroLvl");
    if (hLvl) hLvl.innerText = `Ур. ${p.hero_level || (data.raw && data.raw.hero && data.raw.hero.level) || 1}`;

    const kda = document.getElementById("mobileKDA");
    if (kda) {
      const b = (data.performance && data.performance.benchmarks) || {};
      const arrowIcon = b.kda_arrow || "▲";
      const arrowColor = b.kda_status === "ahead" ? "#10b981" : "#ef4444";
      kda.innerHTML = `${p.kills || 0} / ${p.deaths || 0} / ${p.assists || 0} <span style="color: ${arrowColor}; font-weight: 800; font-size: 10px;">${arrowIcon} ${b.current_kda !== undefined ? b.current_kda.toFixed(1) : '0.0'}</span> <span style="font-size: 9px; color: #94a3b8;">(пл: ${b.target_kills || 0}/${b.target_deaths || 0})</span>`;
    }
    const nw = document.getElementById("mobileNW");
    if (nw) nw.innerText = `${(p.gold || 0).toLocaleString()} 💰`;
    const gpm = document.getElementById("mobileGPM");
    if (gpm) gpm.innerText = `${p.gpm || 0} GPM`;

    // Roshan on mobile
    const rosh = data.radar.roshan;
    if (rosh) {
      const pill = document.getElementById("mobileRoshStatusBadge");
      const primaryTime = document.getElementById("mobileRoshPrimaryTime");
      const phase = document.getElementById("mobileRoshPhase");
      const fill = document.getElementById("mobileRoshFill");
      const btnKill = document.getElementById("btnMobileRoshanKill");

      if (rosh.state === "alive") {
        if (pill) { pill.className = "mobile-rosh-status-pill alive"; pill.innerText = "ЖИВ"; }
        if (primaryTime) primaryTime.innerText = "ЖИВ";
        if (phase) phase.innerText = "Готов к битве";
        if (fill) fill.style.width = "0%";
        if (btnKill) {
          btnKill.style.background = "linear-gradient(135deg, #059669, #10b981)";
          btnKill.innerHTML = `<span>⚔️ РОШАН УБИТ</span><small>Нажмите при смерти Рошана</small>`;
        }
      } else {
        const d = rosh.details || {};
        const deathTime = rosh.death_time || 0;
        const clock = data.radar.clock_time || 0;
        const elapsed = clock - deathTime;

        if (document.getElementById("mobileRoshAegisVal"))
          document.getElementById("mobileRoshAegisVal").innerText = d.aegis_expires || "--:--";
        if (document.getElementById("mobileRoshMinVal"))
          document.getElementById("mobileRoshMinVal").innerText = d.min_respawn || "--:--";
        if (document.getElementById("mobileRoshMaxVal"))
          document.getElementById("mobileRoshMaxVal").innerText = d.max_respawn || "--:--";

        if (elapsed < 300) {
          const left = 300 - elapsed;
          const m = Math.floor(left / 60);
          const s = left % 60;
          const timeStr = `${m}:${s < 10 ? '0' : ''}${s}`;
          if (pill) { pill.className = "mobile-rosh-status-pill aegis"; pill.innerText = "ЭГИДА"; }
          if (primaryTime) primaryTime.innerText = timeStr;
          if (phase) phase.innerText = `Эгида активна до ${d.aegis_expires}`;
          if (fill) fill.style.width = `${Math.min(100, (elapsed / 300) * 100)}%`;
          if (btnKill) {
            btnKill.style.background = "linear-gradient(135deg, #b45309, #f59e0b)";
            btnKill.innerHTML = `<span>🛡️ ЭГИДА АКТИВНА: ${timeStr}</span><small>Истекает в ${d.aegis_expires}</small>`;
          }
        } else if (elapsed < 480) {
          const left = 480 - elapsed;
          const m = Math.floor(left / 60);
          const s = left % 60;
          const timeStr = `${m}:${s < 10 ? '0' : ''}${s}`;
          if (pill) { pill.className = "mobile-rosh-status-pill respawn"; pill.innerText = "ОЖИДАНИЕ"; }
          if (primaryTime) primaryTime.innerText = timeStr;
          if (phase) phase.innerText = `Мин. спавн в ${d.min_respawn}`;
          if (fill) fill.style.width = `${Math.min(100, (elapsed / 480) * 100)}%`;
          if (btnKill) {
            btnKill.style.background = "linear-gradient(135deg, #6d28d9, #8b5cf6)";
            btnKill.innerHTML = `<span>⏳ ОЖИДАНИЕ СПАВНА: ${timeStr}</span><small>Окно: ${d.min_respawn} - ${d.max_respawn}</small>`;
          }
        } else {
          const left = Math.max(0, 660 - elapsed);
          const m = Math.floor(left / 60);
          const s = left % 60;
          const timeStr = `${m}:${s < 10 ? '0' : ''}${s}`;
          if (pill) { pill.className = "mobile-rosh-status-pill respawn"; pill.innerText = "СПАВН!"; }
          if (primaryTime) primaryTime.innerText = timeStr;
          if (phase) phase.innerText = `Может появиться сейчас! Макс: ${d.max_respawn}`;
          if (fill) fill.style.width = "100%";
          if (btnKill) {
            btnKill.style.background = "linear-gradient(135deg, #b91c1c, #ef4444)";
            btnKill.innerHTML = `<span>⚡ РОШАН МОЖЕТ БЫТЬ ЖИВ</span><small>Макс. время: ${d.max_respawn}</small>`;
          }
        }
      }
    }

    // Camp Stacking Alert (:48 to :55 sec of each minute with mobile vibration)
    const clock = (data.match_info && data.match_info.clock_time !== undefined) ? data.match_info.clock_time : (data.radar ? data.radar.clock_seconds : 0);
    if (clock > 0) {
      const secInMin = clock % 60;
      const stackBanner = document.getElementById("mobileCampStackBanner");
      const stackSec = document.getElementById("mobileCampStackSec");
      if (secInMin >= 48 && secInMin <= 55) {
        if (stackBanner) stackBanner.classList.remove("hidden");
        if (stackSec) stackSec.innerText = `${secInMin}s`;
        const curMin = Math.floor(clock / 60);
        if (secInMin === 52 && lastStackAlertPlayedMin !== curMin) {
          lastStackAlertPlayedMin = curMin;
          triggerHaptic([200, 100, 200]);
          playSoundCue("warning");
        }
      } else {
        if (stackBanner) stackBanner.classList.add("hidden");
      }
    }

    // Runes, Tormentor & Lotus countdowns
    (data.radar.timers || []).forEach(t => {
      const min = Math.floor(t.seconds_left / 60);
      const sec = t.seconds_left % 60;
      const timeStr = `${min}:${sec < 10 ? '0' : ''}${sec}`;

      let cardId = null;
      let timeId = null;
      let dotId = null;

      if (t.id === "wisdom") { cardId = "cardRuneWisdom"; timeId = "mobileTimeWisdom"; dotId = "dotWisdom"; }
      else if (t.id === "bounty" || t.id === "water_rune") { cardId = "cardRuneBounty"; timeId = "mobileTimeBounty"; dotId = "dotBounty"; }
      else if (t.id === "lotus") { cardId = "cardRuneLotus"; timeId = "mobileTimeLotus"; dotId = "dotLotus"; }
      else if (t.id === "power_rune") { cardId = "cardRunePower"; timeId = "mobileTimePower"; dotId = "dotPower"; }
      else if (t.id === "tormentor") { cardId = "cardRuneTormentor"; timeId = "mobileTimeTormentor"; dotId = "dotTormentor"; }

      if (timeId && document.getElementById(timeId)) {
        document.getElementById(timeId).innerText = timeStr;
      }
      if (cardId && document.getElementById(cardId)) {
        const card = document.getElementById(cardId);
        const dot = dotId ? document.getElementById(dotId) : null;
        if (t.seconds_left <= 15) {
          card.classList.add("soon-alert");
          if (dot) dot.classList.remove("hidden");
          const alertKey = `${t.id}_${Math.floor(data.radar.clock_time / 60)}`;
          if (!alertedTimerIds.has(alertKey)) {
            alertedTimerIds.add(alertKey);
            triggerHaptic([200, 100, 200]);
            playSoundCue(t.id === "wisdom" ? "critical" : "warning");
          }
        } else {
          card.classList.remove("soon-alert");
          if (dot) dot.classList.add("hidden");
        }
      }
    });
  }

  // Performance & Benchmarks on mobile
  if (data.performance) {
    const p = data.performance;
    const grade = document.getElementById("mobileBenchmarkGrade");
    if (grade) {
      grade.innerText = p.grade || "A";
      grade.style.color = p.grade_color || "#10b981";
    }
    const b = p.benchmarks || {};
    renderKDABenchmarks(b, "mobile");

    const cs = document.getElementById("mobileCS");
    if (cs) cs.innerText = `${b.current_cs || 0} / ${b.current_denies || 0}`;
    const targetCS = document.getElementById("mobileTargetCS");
    if (targetCS) targetCS.innerText = `${b.target_cs || 0}`;
    updateDeltaBadge("mobileDeltaCSBadge", b.cs_arrow || "▲", (b.delta_cs >= 0 ? "+" : "") + (b.delta_cs || 0), b.cs_status === "ahead");

    const nw = document.getElementById("mobileNWVal");
    if (nw) nw.innerText = `${(b.current_nw || 0).toLocaleString()} 💰`;
    const targetNW = document.getElementById("mobileTargetNW");
    if (targetNW) targetNW.innerText = `${(b.target_nw || 0).toLocaleString()}`;
    updateDeltaBadge("mobileDeltaNWBadge", b.nw_arrow || "▲", (b.delta_nw >= 0 ? "+" : "") + ((b.delta_nw || 0).toLocaleString()) + "g", b.nw_status === "ahead");

    const gpm = document.getElementById("mobileGPMVal");
    if (gpm) gpm.innerText = `${b.current_gpm || 0} / ${b.current_xpm || 0}`;
    const targetGPM = document.getElementById("mobileTargetGPM");
    if (targetGPM) targetGPM.innerText = `${b.target_gpm || 0} / ${b.target_xpm || 0}`;
    updateDeltaBadge("mobileDeltaGPMBadge", b.gpm_arrow || "▲", (b.delta_gpm >= 0 ? "+" : "") + (b.delta_gpm || 0), b.gpm_status === "ahead");

    // Buyback on mobile
    if (p.buyback) {
      const bb = p.buyback;
      const bbCost = document.getElementById("mobileBBCost");
      if (bbCost) bbCost.innerText = `${bb.cost} 💰`;
      const bbStatus = document.getElementById("mobileBBStatus");
      const bbSurplus = document.getElementById("mobileBBSurplus");
      const bbNote = document.getElementById("mobileBBNote");

      if (bb.status === "READY") {
        if (bbStatus) { bbStatus.innerText = "Выкуп готов"; bbStatus.style.color = "#10b981"; }
        if (bbSurplus) { bbSurplus.innerText = `+${bb.surplus}g резерв`; bbSurplus.className = "mobile-badge positive"; }
        if (bbNote) bbNote.innerText = bb.death_penalty > 0 ? `Потеря при смерти: -${bb.death_penalty}g` : "Безопасно";
      } else if (bb.status === "AT_RISK") {
        if (bbStatus) { bbStatus.innerText = "Риск потери выкупа"; bbStatus.style.color = "#fbbf24"; }
        if (bbSurplus) { bbSurplus.innerText = `-${Math.abs(bb.surplus_after_death)}g при смерти`; bbSurplus.className = "mobile-badge"; }
        if (bbNote) bbNote.innerText = `Хватит сейчас, но смерть снимет ${bb.death_penalty}g!`;
      } else if (bb.status === "COOLDOWN") {
        if (bbStatus) { bbStatus.innerText = `Кулдаун (${bb.cooldown}с)`; bbStatus.style.color = "#c084fc"; }
        if (bbSurplus) { bbSurplus.innerText = `КД: ${bb.cooldown}с`; bbSurplus.className = "mobile-badge"; }
        if (bbNote) bbNote.innerText = "Выкуп на перезарядке";
      } else {
        if (bbStatus) { bbStatus.innerText = "Не хватает золота"; bbStatus.style.color = "#f87171"; }
        if (bbSurplus) { bbSurplus.innerText = `Дефицит ${bb.deficit || 0}g`; bbSurplus.className = "mobile-badge"; }
        if (bbNote) bbNote.innerText = "Нужно больше фарма";
      }
    }
  }

  // Next Item on Mobile & Desktop
  if (data.next_item) {
    renderNextItem(data.next_item);
  }

  // Items on Mobile
  renderItemProgression(data.item_build, data.recommended_items);

}


// ==========================================
// DOTA PLUS SUITE: DAMAGE BREAKDOWN, NET WORTH GRAPH, ITEM PROGRESSION, ABILITIES
// ==========================================

function updateDeltaBadge(elemId, arrow, deltaStr, isAhead) {
  const el = document.getElementById(elemId);
  if (!el) return;
  el.className = `delta-arrow-badge ${isAhead ? 'ahead' : 'behind'}`;
  el.innerHTML = `<span class="metric-delta-arrow">${arrow}</span> ${deltaStr}`;
}

function renderKDABenchmarks(b, prefix = "mobile") {
  if (!b) return;

  // Plan verdict
  const verdictPill = document.getElementById(`${prefix}PlanVerdict`);
  const verdictText = document.getElementById(`${prefix}PlanVerdictText`);
  const verdictArrow = document.getElementById(`${prefix}PlanVerdictArrow`);
  if (verdictPill && verdictText && verdictArrow) {
    const isAhead = b.plan_status === "ahead";
    verdictPill.className = `plan-verdict-pill ${isAhead ? 'ahead' : 'behind'}`;
    verdictText.innerText = `${b.plan_verdict || 'В плане'} (${b.ahead_count !== undefined ? b.ahead_count : 4}/${b.total_metrics || 5})`;
    verdictArrow.innerText = isAhead ? "▲ В плюсе" : "▼ Отставание";
  }

  // KDA Ratio
  const kdaVal = document.getElementById(`${prefix}KdaVal`);
  const kdaPlan = document.getElementById(`${prefix}KdaPlan`);
  if (kdaVal) kdaVal.innerText = b.current_kda !== undefined ? b.current_kda.toFixed(1) : "0.0";
  if (kdaPlan) kdaPlan.innerText = prefix === "mobile" ? (b.target_kda !== undefined ? b.target_kda.toFixed(1) : "3.5") : `план ${b.target_kda !== undefined ? b.target_kda.toFixed(1) : "3.5"}`;
  updateDeltaBadge(
    `${prefix}KdaDeltaBadge`,
    b.kda_arrow || "▲",
    (b.delta_kda >= 0 ? "+" : "") + (b.delta_kda !== undefined ? b.delta_kda.toFixed(1) : "0.0"),
    b.kda_status === "ahead"
  );

  // Kills
  const kVal = document.getElementById(`${prefix}KillsVal`);
  const kPlan = document.getElementById(`${prefix}KillsPlan`);
  if (kVal) kVal.innerText = b.current_kills || 0;
  if (kPlan) kPlan.innerText = prefix === "mobile" ? (b.target_kills || 0) : `план ${b.target_kills || 0}`;
  updateDeltaBadge(
    `${prefix}KillsDeltaBadge`,
    b.kills_arrow || "▲",
    (b.delta_kills >= 0 ? "+" : "") + (b.delta_kills !== undefined ? b.delta_kills : 0),
    b.kills_status === "ahead"
  );

  // Deaths (fewer deaths than target = ahead!)
  const dVal = document.getElementById(`${prefix}DeathsVal`);
  const dPlan = document.getElementById(`${prefix}DeathsPlan`);
  if (dVal) dVal.innerText = b.current_deaths || 0;
  if (dPlan) dPlan.innerText = prefix === "mobile" ? (b.target_deaths || 0) : `план ${b.target_deaths || 0}`;
  const dStr = (b.delta_deaths > 0 ? "+" : "") + (b.delta_deaths !== undefined ? b.delta_deaths : 0);
  updateDeltaBadge(
    `${prefix}DeathsDeltaBadge`,
    b.deaths_arrow || "▲",
    dStr,
    b.deaths_status === "ahead"
  );

  // Assists
  const aVal = document.getElementById(`${prefix}AssistsVal`);
  const aPlan = document.getElementById(`${prefix}AssistsPlan`);
  if (aVal) aVal.innerText = b.current_assists || 0;
  if (aPlan) aPlan.innerText = prefix === "mobile" ? (b.target_assists || 0) : `план ${b.target_assists || 0}`;
  updateDeltaBadge(
    `${prefix}AssistsDeltaBadge`,
    b.assists_arrow || "▲",
    (b.delta_assists >= 0 ? "+" : "") + (b.delta_assists !== undefined ? b.delta_assists : 0),
    b.assists_status === "ahead"
  );
}

function renderDamageBreakdown(dmg) {
  if (!dmg) return;
  const pPct = dmg.physical_pct !== undefined ? dmg.physical_pct : 50;
  const mPct = dmg.magical_pct !== undefined ? dmg.magical_pct : 42;
  const uPct = dmg.pure_pct !== undefined ? dmg.pure_pct : 8;
  const adv = dmg.advice || "Анализ сетапа...";

  // Mobile elements
  const mPBar = document.getElementById("mobileDmgPhysBar");
  const mMBar = document.getElementById("mobileDmgMagicBar");
  const mUBar = document.getElementById("mobileDmgPureBar");
  if (mPBar) mPBar.style.width = `${pPct}%`;
  if (mMBar) mMBar.style.width = `${mPct}%`;
  if (mUBar) mUBar.style.width = `${uPct}%`;

  const mPPct = document.getElementById("mobileDmgPhysPct");
  const mMPct = document.getElementById("mobileDmgMagicPct");
  const mUPct = document.getElementById("mobileDmgPurePct");
  if (mPPct) mPPct.innerText = `${pPct}%`;
  if (mMPct) mMPct.innerText = `${mPct}%`;
  if (mUPct) mUPct.innerText = `${uPct}%`;

  const mAdv = document.getElementById("mobileDamageAdvice");
  if (mAdv) mAdv.innerText = adv;

  // Desktop elements
  const dPBar = document.getElementById("desktopDmgPhysBar");
  const dMBar = document.getElementById("desktopDmgMagicBar");
  const dUBar = document.getElementById("desktopDmgPureBar");
  if (dPBar) dPBar.style.width = `${pPct}%`;
  if (dMBar) dMBar.style.width = `${mPct}%`;
  if (dUBar) dUBar.style.width = `${uPct}%`;

  const dPPct = document.getElementById("desktopDmgPhysPct");
  const dMPct = document.getElementById("desktopDmgMagicPct");
  const dUPct = document.getElementById("desktopDmgPurePct");
  if (dPPct) dPPct.innerText = `${pPct}%`;
  if (dMPct) dMPct.innerText = `${mPct}%`;
  if (dUPct) dUPct.innerText = `${uPct}%`;

  const dAdv = document.getElementById("desktopDamageAdvice");
  if (dAdv) dAdv.innerText = adv;
}

function renderNetWorthGraph(history, benchmarks, targetElemId, svgW, svgH) {
  const elem = document.getElementById(targetElemId);
  if (!elem) return;

  const padLeft = 24;
  const padRight = 8;
  const padTop = 8;
  const padBottom = 16;
  const plotW = svgW - padLeft - padRight;
  const plotH = svgH - padTop - padBottom;

  let points = [];
  if (history && history.length > 0) {
    points = history.slice();
  } else {
    const curNW = benchmarks ? (benchmarks.current_nw || 600) : 600;
    const tgtNW = benchmarks ? (benchmarks.target_nw || 600) : 600;
    points = [
      { minute: 0, player_nw: 600, benchmark_nw: 600 },
      { minute: 1, player_nw: curNW, benchmark_nw: tgtNW }
    ];
  }

  let maxMin = 15;
  let maxNW = 5000;
  points.forEach(p => {
    if (p.minute > maxMin) maxMin = p.minute;
    if (p.player_nw > maxNW) maxNW = p.player_nw;
    if (p.benchmark_nw > maxNW) maxNW = p.benchmark_nw;
  });
  maxMin = Math.max(10, Math.ceil(maxMin / 5) * 5);
  maxNW = Math.max(3000, Math.ceil(maxNW / 2000) * 2000);

  function getX(m) {
    return padLeft + (m / maxMin) * plotW;
  }
  function getY(nw) {
    return padTop + plotH - (Math.max(0, nw) / maxNW) * plotH;
  }

  let gridSvg = "";
  const stepsNW = [0.25, 0.5, 0.75, 1.0];
  stepsNW.forEach(factor => {
    const nwVal = Math.round(maxNW * factor);
    const y = getY(nwVal);
    gridSvg += `<line x1="${padLeft}" y1="${y}" x2="${svgW - padRight}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-width="1" />`;
    gridSvg += `<text x="${padLeft - 3}" y="${y + 3}" fill="#64748b" font-size="7.5" text-anchor="end">${Math.round(nwVal / 1000)}k</text>`;
  });

  for (let m = 5; m <= maxMin; m += 5) {
    const x = getX(m);
    gridSvg += `<line x1="${x}" y1="${padTop}" x2="${x}" y2="${padTop + plotH}" stroke="rgba(255,255,255,0.06)" stroke-width="1" />`;
    gridSvg += `<text x="${x}" y="${padTop + plotH + 11}" fill="#64748b" font-size="7.5" text-anchor="middle">${m}m</text>`;
  }

  const benchPointsStr = points.map(p => `${getX(p.minute)},${getY(p.benchmark_nw)}`).join(" ");
  const benchLine = `<polyline points="${benchPointsStr}" fill="none" stroke="#38bdf8" stroke-width="1.8" stroke-dasharray="3,3" opacity="0.85" />`;

  const playerPointsStr = points.map(p => `${getX(p.minute)},${getY(p.player_nw)}`).join(" ");
  const firstX = getX(points[0].minute);
  const lastX = getX(points[points.length - 1].minute);
  const bottomY = getY(0);
  const areaPointsStr = `${firstX},${bottomY} ${playerPointsStr} ${lastX},${bottomY}`;
  const gradId = targetElemId.includes("mobile") ? "mobileNwGrad" : "desktopNwGrad";
  const playerArea = `<polygon points="${areaPointsStr}" fill="url(#${gradId})" />`;
  const playerLine = `<polyline points="${playerPointsStr}" fill="none" stroke="#e5c158" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`;

  const lastP = points[points.length - 1];
  const lastDot = `
    <circle cx="${getX(lastP.minute)}" cy="${getY(lastP.player_nw)}" r="3.5" fill="#e5c158" stroke="#ffffff" stroke-width="1.5" />
    <circle cx="${getX(lastP.minute)}" cy="${getY(lastP.player_nw)}" r="6.5" fill="none" stroke="#e5c158" stroke-width="1" opacity="0.6" />
  `;

  elem.innerHTML = gridSvg + playerArea + benchLine + playerLine + lastDot;
}

function renderItemProgression(itemBuild, situationalItems) {
  // 1. Mobile Item Stage Rendering
  const mContainer = document.getElementById("mobileItemsContainer");
  if (mContainer) {
    let list = [];
    if (currentMobileItemStage === "situational") {
      list = situationalItems || [];
    } else if (itemBuild && itemBuild[currentMobileItemStage]) {
      list = itemBuild[currentMobileItemStage];
    }

    if (!list || list.length === 0) {
      mContainer.innerHTML = `<span style="color: #94a3b8; font-size: 11px; padding: 12px; grid-column: 1/-1; text-align: center;">Оптимальные предметы определяются...</span>`;
    } else {
      mContainer.innerHTML = "";
      list.forEach(it => {
        const cleanName = (it.id || "").replace("item_", "");
        const imgUrl = it.image_url || `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/${cleanName}.png`;
        const card = document.createElement("div");
        card.className = "item-stage-card";
        card.innerHTML = `
          <div class="item-stage-img-wrap">
            <img src="${imgUrl}" alt="${it.name}" onerror="this.src='https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/branches.png'">
          </div>
          <div class="item-stage-info">
            <span class="item-stage-name">${it.name || it.id}</span>
            <span class="item-stage-cost">${it.cost ? it.cost + ' 💰' : (it.advice || '')}</span>
          </div>
        `;
        mContainer.appendChild(card);
      });
    }
  }

  // 2. Desktop Item Stage Rendering
  const dContainer = document.getElementById("itemsContainer");
  if (dContainer) {
    let dList = [];
    if (currentDesktopItemStage === "situational") {
      dList = situationalItems || [];
    } else if (itemBuild && itemBuild[currentDesktopItemStage]) {
      dList = itemBuild[currentDesktopItemStage];
    }

    if (!dList || dList.length === 0) {
      dContainer.innerHTML = `<span style="color: #94a3b8; font-size: 11px; padding: 10px; grid-column: 1/-1; text-align: center;">Оптимальные предметы определяются...</span>`;
    } else {
      dContainer.innerHTML = "";
      dList.forEach(it => {
        const cleanName = (it.id || "").replace("item_", "");
        const imgUrl = it.image_url || `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/${cleanName}.png`;
        const card = document.createElement("div");
        card.className = "item-stage-card";
        card.innerHTML = `
          <div class="item-stage-img-wrap">
            <img src="${imgUrl}" alt="${it.name}" onerror="this.src='https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/branches.png'">
          </div>
          <div class="item-stage-info">
            <span class="item-stage-name">${it.name || it.id}</span>
            <span class="item-stage-cost">${it.cost ? it.cost + ' 💰' : (it.advice || '')}</span>
          </div>
        `;
        dContainer.appendChild(card);
      });
    }
  }
}

function renderNextItem(nextItem) {
  if (!nextItem) return;

  // 1. Mobile Next Item Card
  const mName = document.getElementById("mobileNextItemName");
  if (mName) mName.innerText = nextItem.name || nextItem.id || "Предмет";

  const mCost = document.getElementById("mobileNextItemCost");
  if (mCost) mCost.innerText = `${(nextItem.cost || 0).toLocaleString()} 💰`;

  const mGoldStatus = document.getElementById("mobileNextItemGoldStatus");
  if (mGoldStatus) {
    mGoldStatus.innerText = `${(nextItem.current_gold || 0).toLocaleString()} / ${(nextItem.cost || 0).toLocaleString()} 💰`;
  }

  const mETA = document.getElementById("mobileNextItemETA");
  if (mETA) {
    if (nextItem.can_buy_now) {
      mETA.innerText = "Хватает золота!";
      mETA.style.color = "#10b981";
    } else {
      const etaStr = nextItem.eta_seconds ? ` (~${Math.ceil(nextItem.eta_seconds / 60)} мин)` : "";
      mETA.innerText = `Осталось: ${(nextItem.gold_needed || 0).toLocaleString()}g${etaStr}`;
      mETA.style.color = "var(--text-muted)";
    }
  }

  const mProgressFill = document.getElementById("mobileNextItemProgressFill");
  if (mProgressFill) {
    mProgressFill.style.width = `${Math.min(100, Math.max(0, nextItem.progress_pct || 0))}%`;
  }

  const mProgressPct = document.getElementById("mobileNextItemProgressPct");
  if (mProgressPct) {
    mProgressPct.innerText = `${nextItem.progress_pct || 0}%`;
  }

  const mImg = document.getElementById("mobileNextItemImg");
  const mImgWrap = document.getElementById("mobileNextItemImgWrap");
  if (mImg) {
    mImg.src = nextItem.image_url || `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/${(nextItem.id || "").replace("item_", "")}.png`;
  }
  if (mImgWrap) {
    if (nextItem.can_buy_now) {
      mImgWrap.classList.add("affordable");
    } else {
      mImgWrap.classList.remove("affordable");
    }
  }

  const mUrgency = document.getElementById("mobileNextItemUrgency");
  if (mUrgency) {
    mUrgency.innerText = nextItem.stage_label || (nextItem.urgency === "urgent" ? "Срочный контрпик" : "Ядро");
    if (nextItem.urgency === "urgent") {
      mUrgency.className = "mobile-badge next-item-urgency-badge urgent";
    } else {
      mUrgency.className = "mobile-badge next-item-urgency-badge";
    }
  }

  const mCompBar = document.getElementById("mobileNextItemComponentBar");
  const mCompText = document.getElementById("mobileNextItemComponentText");
  if (mCompText) {
    mCompText.innerText = nextItem.next_component || "Копите золото";
  }
  if (mCompBar) {
    if (nextItem.comp_affordable || nextItem.can_buy_now) {
      mCompBar.className = "next-item-component-bar can-buy";
    } else {
      mCompBar.className = "next-item-component-bar";
    }
  }

  const mReason = document.getElementById("mobileNextItemReason");
  if (mReason) {
    mReason.innerText = nextItem.reason || "Рекомендуемый предмет";
  }

  // 2. Desktop Next Item Bar
  const dName = document.getElementById("desktopNextItemName");
  if (dName) dName.innerText = nextItem.name || nextItem.id || "Предмет";

  const dCost = document.getElementById("desktopNextItemCost");
  if (dCost) dCost.innerText = `${(nextItem.cost || 0).toLocaleString()} 💰`;

  const dProgressFill = document.getElementById("desktopNextItemProgressFill");
  if (dProgressFill) {
    dProgressFill.style.width = `${Math.min(100, Math.max(0, nextItem.progress_pct || 0))}%`;
  }

  const dImg = document.getElementById("desktopNextItemImg");
  if (dImg) {
    dImg.src = nextItem.image_url || `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/${(nextItem.id || "").replace("item_", "")}.png`;
  }

  const dCompText = document.getElementById("desktopNextItemComponentText");
  if (dCompText) {
    dCompText.innerText = nextItem.next_component || "Копите золото";
  }

  const dETA = document.getElementById("desktopNextItemETA");
  if (dETA) {
    if (nextItem.can_buy_now) {
      dETA.innerText = "Готов к покупке!";
      dETA.style.color = "#10b981";
    } else {
      dETA.innerText = `Осталось: ${(nextItem.gold_needed || 0).toLocaleString()}g`;
      dETA.style.color = "var(--text-muted)";
    }
  }
}

function renderAbilityBuild(abilityBuild, heroLevel) {
  if (!abilityBuild) return;
  const seq = abilityBuild.sequence || [];
  const talents = abilityBuild.talents || {};

  const nextStep = seq.find(s => s.lvl === (heroLevel + 1)) || seq[seq.length - 1];
  const nextBadge = document.getElementById("mobileNextSkillBadge");
  if (nextBadge && nextStep) {
    nextBadge.innerText = `След.: ${nextStep.key} (${nextStep.lvl} ур.)`;
  }

  function renderSeqTo(elemId) {
    const elem = document.getElementById(elemId);
    if (!elem) return;
    elem.innerHTML = "";
    seq.forEach(s => {
      const isNext = s.lvl === (heroLevel + 1);
      const isLearned = s.lvl <= heroLevel;
      const stepDiv = document.createElement("div");
      stepDiv.className = "ability-step";
      stepDiv.innerHTML = `
        <span class="ability-step-lvl">${s.lvl}</span>
        <div class="ability-step-pill ${s.type} ${isNext ? 'next-active' : ''}" style="${isLearned ? 'opacity: 0.5;' : ''}">${s.key}</div>
      `;
      elem.appendChild(stepDiv);
    });
  }

  function renderTalentsTo(elemId) {
    const elem = document.getElementById(elemId);
    if (!elem) return;
    elem.innerHTML = "";
    [25, 20, 15, 10].forEach(lvl => {
      const t = talents[lvl];
      if (!t) return;
      const isLeftRec = t.recommended === "left";
      const isRightRec = t.recommended === "right";
      const row = document.createElement("div");
      row.className = "talent-tier-row";
      row.innerHTML = `
        <div class="talent-tier-choice ${isLeftRec ? 'recommended' : ''}">
          <span>${t.left}</span>
          ${isLeftRec ? '<span style="color: #e5c158; font-size: 10px;">★ ' + (t.winrate || 54) + '% WR</span>' : ''}
        </div>
        <div class="talent-tier-circle">${lvl}</div>
        <div class="talent-tier-choice ${isRightRec ? 'recommended' : ''}">
          ${isRightRec ? '<span style="color: #e5c158; font-size: 10px;">★ ' + (t.winrate || 54) + '% WR</span>' : ''}
          <span>${t.right}</span>
        </div>
      `;
      elem.appendChild(row);
    });
  }

  renderSeqTo("mobileAbilitySequence");
  renderTalentsTo("mobileTalentsTree");

  renderSeqTo("desktopAbilitySequence");
  renderTalentsTo("desktopTalentsTree");
}

// State Pulling Fallback for Tab Switching & Window Focus
function fetchLatestState() {
  fetch("/api/state")
    .then(r => r.json())
    .then(data => {
      latestData = data;
      renderUI(data);
    })
    .catch(err => console.warn("Fetch state error:", err));
}

// Event Listeners on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  // Check Steam HUD Mode
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("mode") === "hud") {
    document.body.classList.add("mode-hud-only");
    document.body.classList.remove("mode-menu");
  }

  // Auto-refresh when window or tab regains focus
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      fetchLatestState();
    }
  });

  window.addEventListener("focus", () => {
    fetchLatestState();
  });

  // Continuous background sync (1.5s interval)
  setInterval(() => {
    fetchLatestState();
  }, 1500);

  // Mobile Tabs
  document.querySelectorAll(".nav-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".mobile-page").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-target");
      const page = document.getElementById(targetId);
      if (page) page.classList.add("active");
      if (latestData) {
        renderMobileUI(latestData);
      }
      triggerHaptic(40);
    });
  });

  // Mobile Item Stage Tabs
  document.querySelectorAll("#mobileItemTabs .item-stage-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#mobileItemTabs .item-stage-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentMobileItemStage = tab.getAttribute("data-stage");
      const badge = document.getElementById("mobileItemStageBadge");
      if (badge) badge.innerText = tab.innerText;
      if (latestData) {
        renderItemProgression(latestData.item_build, latestData.recommended_items);
      }
      triggerHaptic(30);
    });
  });

  // Mobile Collapsible Net Worth Graph Toggle
  const btnToggleNWGraph = document.getElementById("btnToggleNWGraph");
  const mobileNWGraphCollapsible = document.getElementById("mobileNWGraphCollapsible");
  const nwGraphToggleArrow = document.getElementById("nwGraphToggleArrow");
  if (btnToggleNWGraph && mobileNWGraphCollapsible) {
    btnToggleNWGraph.addEventListener("click", () => {
      const isHidden = mobileNWGraphCollapsible.classList.contains("hidden");
      if (isHidden) {
        mobileNWGraphCollapsible.classList.remove("hidden");
        if (nwGraphToggleArrow) nwGraphToggleArrow.innerText = "▴";
      } else {
        mobileNWGraphCollapsible.classList.add("hidden");
        if (nwGraphToggleArrow) nwGraphToggleArrow.innerText = "▾";
      }
      triggerHaptic(25);
    });
  }

  // Desktop Item Stage Tabs
  document.querySelectorAll("#desktopItemStages .item-stage-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#desktopItemStages .item-stage-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentDesktopItemStage = tab.getAttribute("data-dstage");
      if (latestData) {
        renderItemProgression(latestData.item_build, latestData.recommended_items);
      }
    });
  });

  // Desktop Left HUD View Switcher (Items vs Skills/Talents)
  document.querySelectorAll("#desktopBuildTabs .item-stage-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#desktopBuildTabs .item-stage-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const targetView = tab.getAttribute("data-targetview");
      const itemsView = document.getElementById("desktopItemsView");
      const skillsView = document.getElementById("desktopSkillsView");
      if (targetView === "skills") {
        if (itemsView) itemsView.classList.add("hidden");
        if (skillsView) skillsView.classList.remove("hidden");
        if (latestData && latestData.ability_build) {
          const lvl = (latestData.player && latestData.player.hero_level) || 1;
          renderAbilityBuild(latestData.ability_build, lvl);
        }
      } else {
        if (skillsView) skillsView.classList.add("hidden");
        if (itemsView) itemsView.classList.remove("hidden");
        if (latestData) {
          renderItemProgression(latestData.item_build, latestData.recommended_items);
        }
      }
    });
  });


  // Mobile Haptic Toggle
  const btnHaptic = document.getElementById("btnMobileHaptic");
  if (btnHaptic) {
    btnHaptic.addEventListener("click", () => {
      mobileHapticEnabled = !mobileHapticEnabled;
      const icon = document.getElementById("mobileHapticIcon");
      if (icon) icon.innerText = mobileHapticEnabled ? "🔔 Вкл" : "🔕 Выкл";
      btnHaptic.style.color = mobileHapticEnabled ? "#00ff88" : "#94a3b8";
      if (mobileHapticEnabled) triggerHaptic([100, 50, 100]);
    });
  }

  // Mobile Roshan Controls
  const btnMobRoshKill = document.getElementById("btnMobileRoshanKill");
  if (btnMobRoshKill) {
    btnMobRoshKill.addEventListener("click", () => {
      triggerHaptic([300, 100, 300]);
      playSoundCue("critical");
      fetch("/api/roshan/manual_kill", { method: "POST" })
        .then(r => r.json())
        .then(() => {
          showSingleToast("⚔️ Рошан убит!", "Таймер отсчета респавна запущен", "warning");
        })
        .catch(e => console.error("Roshan kill trigger error:", e));
    });
  }

  const btnMobRoshReset = document.getElementById("btnMobileRoshanReset");
  if (btnMobRoshReset) {
    btnMobRoshReset.addEventListener("click", () => {
      triggerHaptic(80);
      fetch("/api/roshan/reset", { method: "POST" })
        .then(r => r.json())
        .then(() => {
          showSingleToast("🛡️ Рошан", "Таймер сброшен (Рошан жив)", "info");
        })
        .catch(e => console.error("Roshan reset error:", e));
    });
  }

  // Mobile Simulate
  const btnMobSim = document.getElementById("btnMobileSimulate");
  if (btnMobSim) {
    btnMobSim.addEventListener("click", () => {
      triggerHaptic(100);
      fetch("/api/simulate", { method: "POST" }).catch(e => console.error(e));
    });
  }

  // Mobile Glyph
  const btnMobGlyph = document.getElementById("btnMobileGlyphTrigger");
  if (btnMobGlyph) {
    btnMobGlyph.addEventListener("click", () => {
      triggerHaptic(100);
      fetch("/api/glyph_used", { method: "POST" })
        .then(r => r.json())
        .then(() => {
          showSingleToast("🛡️ Глиф врага использован!", "Таймер 300с запущен", "warning");
        })
        .catch(e => console.error(e));
    });
  }

  fetchHeroesList();
  initEventSource();
  setupHeroSearch();

  renderManualEnemySlots();
  setupCustomSelects();

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
    const draftModal = document.getElementById("draftOverlay");
    draftModal.classList.toggle("hidden");
    if (!draftModal.classList.contains("hidden")) {
      const searchInp = document.getElementById("heroSearchInput");
      if (searchInp) searchInp.focus();
    }
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

  const btnSim = document.getElementById("btnSimulate");
  if (btnSim) {
    btnSim.addEventListener("click", () => {
      const origHtml = btnSim.innerHTML;
      btnSim.innerHTML = "<span>⏳ Тест...</span>";
      fetch("/api/simulate", { method: "POST" })
        .then(() => {
          setTimeout(() => { btnSim.innerHTML = origHtml; }, 1000);
        })
        .catch(() => {
          btnSim.innerHTML = origHtml;
        });
    });
  }

  const btnRosh = document.getElementById("btnRoshKilled");
  if (btnRosh) {
    btnRosh.addEventListener("click", () => {
      btnRosh.innerText = "✓ Скопировано!";
      setTimeout(() => { btnRosh.innerText = "⚔️ Рошан"; }, 1500);
      fetch("/api/roshan_killed", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          if (data.chat_string) {
            copyToClipboard(data.chat_string);
            showSingleToast("⚔️ Рошан зафиксирован!", `Тайминг скопирован в буфер: ${data.chat_string}`, "info");
          }
        })
        .catch(e => console.error("Roshan killed err:", e));
    });
  }

  const btnGlyph = document.getElementById("btnGlyphUsed");
  if (btnGlyph) {
    btnGlyph.addEventListener("click", () => {
      btnGlyph.innerText = "✓ Запущен";
      setTimeout(() => { btnGlyph.innerText = "🛡️ Глиф"; }, 1500);
      fetch("/api/glyph_used", { method: "POST" })
        .then(r => r.json())
        .then(() => {
          showSingleToast("🛡️ Глиф врага использован!", "Таймер перезарядки (300с) запущен", "warning");
        })
        .catch(e => console.error("Glyph used err:", e));
    });
  }

  const btnClose = document.getElementById("btnCloseOverlay");
  if (btnClose) {
    btnClose.addEventListener("click", () => {
      window.closeMenu();
    });
  }

  const btnQuit = document.getElementById("btnQuitOverlay");
  if (btnQuit) {
    btnQuit.addEventListener("click", () => {
      window.shutdownApp();
    });
  }

  // Center Command Center Handlers
  const btnCenterClose = document.getElementById("btnCenterClose");
  if (btnCenterClose) {
    btnCenterClose.addEventListener("click", () => {
      window.closeMenu();
    });
  }

  const btnCenterDraft = document.getElementById("btnCenterDraft");
  if (btnCenterDraft) {
    btnCenterDraft.addEventListener("click", () => {
      const draftModal = document.getElementById("draftOverlay");
      if (draftModal) {
        draftModal.classList.remove("hidden");
        const searchInp = document.getElementById("heroSearchInput");
        if (searchInp) searchInp.focus();
      }
    });
  }

  const btnCenterSim = document.getElementById("btnCenterSimulate");
  if (btnCenterSim) {
    btnCenterSim.addEventListener("click", () => {
      const origHtml = btnCenterSim.innerHTML;
      btnCenterSim.innerHTML = "<span>⏳ Симуляция...</span>";
      fetch("/api/simulate", { method: "POST" })
        .then(() => {
          setTimeout(() => { btnCenterSim.innerHTML = origHtml; }, 1000);
        })
        .catch(() => {
          btnCenterSim.innerHTML = origHtml;
        });
    });
  }

  const btnCenterRosh = document.getElementById("btnCenterRosh");
  if (btnCenterRosh) {
    btnCenterRosh.addEventListener("click", () => {
      btnCenterRosh.innerText = "✓ Скопировано!";
      setTimeout(() => { btnCenterRosh.innerText = "⚔️ Рошан убит"; }, 1500);
      fetch("/api/roshan_killed", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          if (data.chat_string) {
            copyToClipboard(data.chat_string);
            showSingleToast("⚔️ Рошан зафиксирован!", `Тайминг скопирован в буфер: ${data.chat_string}`, "info");
          }
        })
        .catch(e => console.error("Roshan killed err:", e));
    });
  }

  const btnCenterGlyph = document.getElementById("btnCenterGlyph");
  if (btnCenterGlyph) {
    btnCenterGlyph.addEventListener("click", () => {
      btnCenterGlyph.innerText = "✓ Запущен";
      setTimeout(() => { btnCenterGlyph.innerText = "🛡️ Глиф врага"; }, 1500);
      fetch("/api/glyph_used", { method: "POST" })
        .then(r => r.json())
        .then(() => {
          showSingleToast("🛡️ Глиф врага использован!", "Таймер перезарядки (300с) запущен", "warning");
        })
        .catch(e => console.error("Glyph used err:", e));
    });
  }

  const btnCenterQuit = document.getElementById("btnCenterQuit");
  if (btnCenterQuit) {
    btnCenterQuit.addEventListener("click", () => {
      window.shutdownApp();
    });
  }

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const draftModal = document.getElementById("draftOverlay");
      if (draftModal && !draftModal.classList.contains("hidden")) {
        draftModal.classList.add("hidden");
        return;
      }
      window.closeMenu();
    }
  });

  const btnClick = document.getElementById("btnClickthrough");
  if (btnClick) {
    btnClick.addEventListener("click", () => {
      window.closeMenu();
    });
  }
});

// UI Mode & Steam Overlay Controller
window.setUiMode = function(isInteractive) {
  const body = document.body;
  const lockIcon = document.getElementById("lockIcon");
  if (isInteractive) {
    body.classList.remove("mode-hud");
    body.classList.add("mode-menu");
    if (lockIcon) lockIcon.innerText = "🔓 Меню";
  } else {
    body.classList.remove("mode-menu");
    body.classList.add("mode-hud");
    if (lockIcon) lockIcon.innerText = "🔒 В игре";
    const draftModal = document.getElementById("draftOverlay");
    if (draftModal) draftModal.classList.add("hidden");
  }
};

window.closeMenu = function() {
  window.setUiMode(false);
  fetch("/api/close_menu", { method: "POST" }).catch(() => {});
  if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.overlay) {
    window.webkit.messageHandlers.overlay.postMessage({ action: "close_menu" });
  }
};

window.shutdownApp = function() {
  fetch("/api/shutdown", { method: "POST" }).catch(() => {});
  if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.overlay) {
    window.webkit.messageHandlers.overlay.postMessage({ action: "quit_app" });
  }
};

// Aliases for backwards compatibility
window.closeOverlay = window.closeMenu;
window.quitApp = window.shutdownApp;
