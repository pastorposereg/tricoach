/**
 * Main Application Controller for Triathlon Performance & Health.
 * Manages dual-page navigation, weekly workout calendar, zone summary,
 * workout efficiency & decoupling modal, PMC chart, and AI Coach chatbot.
 */

const state = {
  currentTab: 'calendar', // 'calendar' | 'form'
  weekOffset: 0,
  weekData: null,
  pmcDays: 90,
  pmcData: null,
  activeZoneSport: 'all',
  chatHistory: [],
  athleteStatus: null,
  isSyncing: false,
  activityDetailCache: {},
};

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initPWA();
  initApp();
  setupEventListeners();
});

function initPWA() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  }
}

async function initApp() {
  await loadStatus();
  await loadWeek(0);
}

function setupEventListeners() {
  // Navigation Tabs
  document.querySelectorAll('[data-tab-target]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const target = btn.getAttribute('data-tab-target');
      switchTab(target);
    });
  });

  // Week Controls
  document.getElementById('btn-prev-week')?.addEventListener('click', () => loadWeek(state.weekOffset - 1));
  document.getElementById('btn-next-week')?.addEventListener('click', () => loadWeek(state.weekOffset + 1));
  document.getElementById('btn-current-week')?.addEventListener('click', () => loadWeek(0));

  // Sync Button
  document.getElementById('btn-sync')?.addEventListener('click', () => syncAllData());

  // Settings Modal
  document.getElementById('btn-open-settings')?.addEventListener('click', () => openSettingsModal());
  document.getElementById('btn-close-settings')?.addEventListener('click', () => closeSettingsModal());
  document.getElementById('btn-save-settings')?.addEventListener('click', () => saveSettings());
  document.getElementById('btn-test-garmin')?.addEventListener('click', () => testGarmin());
  document.getElementById('btn-test-intervals')?.addEventListener('click', () => testIntervals());
  document.getElementById('btn-sync-thresholds')?.addEventListener('click', () => syncThresholds());

  // Activity & Planned Modal Close
  document.getElementById('btn-close-activity-modal')?.addEventListener('click', () => closeActivityModal());
  document.getElementById('btn-close-planned-modal')?.addEventListener('click', () => closePlannedModal());

  // PMC Range Pills
  document.querySelectorAll('[data-pmc-days]').forEach(pill => {
    pill.addEventListener('click', (e) => {
      const days = parseInt(pill.getAttribute('data-pmc-days'), 10);
      document.querySelectorAll('[data-pmc-days]').forEach(p => {
        p.classList.remove('bg-sky-500', 'text-white');
        p.classList.add('bg-slate-800', 'text-slate-400');
      });
      pill.classList.remove('bg-slate-800', 'text-slate-400');
      pill.classList.add('bg-sky-500', 'text-white');
      loadPMC(days);
    });
  });

  // Chatbot
  document.getElementById('form-chat')?.addEventListener('submit', (e) => {
    e.preventDefault();
    submitChatMessage();
  });

  // Quick Prompt Pills
  document.querySelectorAll('[data-quick-prompt]').forEach(chip => {
    chip.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      if (input) {
        input.value = chip.getAttribute('data-quick-prompt');
        submitChatMessage();
      }
    });
  });
}

function switchTab(tabId) {
  state.currentTab = tabId;
  const page1 = document.getElementById('page-calendar');
  const page2 = document.getElementById('page-form');

  // Desktop tab buttons
  document.querySelectorAll('[data-tab-target]').forEach(btn => {
    const isTarget = btn.getAttribute('data-tab-target') === tabId;
    if (isTarget) {
      btn.classList.add('text-sky-400', 'border-b-2', 'border-sky-400', 'bg-sky-950/20');
      btn.classList.remove('text-slate-400', 'border-transparent');
    } else {
      btn.classList.remove('text-sky-400', 'border-b-2', 'border-sky-400', 'bg-sky-950/20');
      btn.classList.add('text-slate-400', 'border-transparent');
    }
  });

  if (tabId === 'calendar') {
    page1?.classList.remove('hidden');
    page2?.classList.add('hidden');
  } else {
    page1?.classList.add('hidden');
    page2?.classList.remove('hidden');
    // Load PMC if not loaded yet
    if (!state.pmcData) {
      loadPMC(state.pmcDays);
    }
  }
}

async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    state.athleteStatus = data;

    // Update athlete greeting
    const nameEl = document.getElementById('athlete-name-display');
    if (nameEl) nameEl.textContent = data.athlete_name || 'Pastor';

    const phaseEl = document.getElementById('athlete-phase-display');
    if (phaseEl) phaseEl.textContent = data.athlete_phase || 'Periodo de Base Aeróbica';

    // Status Badges
    const garminBadge = document.getElementById('garmin-status-pill');
    if (garminBadge) {
      if (data.garmin.connected) {
        garminBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
        garminBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Garmin Conectado`;
      } else {
        garminBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 cursor-pointer';
        garminBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> Conectar Garmin`;
        garminBadge.onclick = openSettingsModal;
      }
    }

    const intervalsBadge = document.getElementById('intervals-status-pill');
    if (intervalsBadge) {
      if (data.intervals.connected) {
        intervalsBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-orange-500/10 text-orange-400 border border-orange-500/20';
        intervalsBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse"></span> Intervals.icu Conectado`;
      } else {
        intervalsBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700 cursor-pointer';
        intervalsBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-slate-500"></span> Intervals.icu`;
        intervalsBadge.onclick = openSettingsModal;
      }
    }

    // Mobile Remote URL & QR Code
    const publicUrl = data.public_url || 'http://192.168.1.135:8000';
    const mobileLinkEl = document.getElementById('mobile-public-url');
    if (mobileLinkEl) {
      mobileLinkEl.textContent = publicUrl;
      mobileLinkEl.href = publicUrl;
    }
    const qrImg = document.getElementById('mobile-qr-img');
    if (qrImg) {
      qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(publicUrl)}`;
    }
    const btnCopy = document.getElementById('btn-copy-public-url');
    if (btnCopy) {
      btnCopy.onclick = () => {
        navigator.clipboard.writeText(publicUrl).then(() => {
          btnCopy.textContent = '¡Copiado!';
          setTimeout(() => { btnCopy.textContent = 'Copiar'; }, 2000);
        }).catch(() => {
          prompt('Copia este enlace para abrir en tu móvil:', publicUrl);
        });
      };
    }
  } catch (err) {
    console.error('Error loading status:', err);
  }
}

async function loadWeek(offset) {
  state.weekOffset = offset;
  const container = document.getElementById('week-days-container');
  if (container) {
    container.innerHTML = `
      <div class="col-span-full py-16 flex flex-col items-center justify-center text-slate-400">
        <svg class="animate-spin h-8 w-8 text-sky-400 mb-3" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span class="text-sm">Cargando semana y actividades...</span>
      </div>`;
  }

  try {
    const res = await fetch(`/api/week?offset=${offset}`);
    const data = await res.json();
    state.weekData = data;

    // Header updates
    const titleEl = document.getElementById('week-title-display');
    if (titleEl) {
      const isCurrent = offset === 0 ? ' (Esta semana)' : '';
      titleEl.textContent = `${data.week_label}${isCurrent}`;
    }

    const dateRangeEl = document.getElementById('week-dates-display');
    if (dateRangeEl) {
      dateRangeEl.textContent = data.date_range;
    }

    // Render Calendar
    renderCalendarGrid(data.days);

    // Render Weekly Zone Summary Box
    renderWeeklyZoneSummary(data.zone_summary, data.totals);
  } catch (err) {
    console.error('Error loading week:', err);
    if (container) {
      container.innerHTML = `<div class="col-span-full py-8 text-center text-rose-400">Error al cargar la semana. Por favor recarga.</div>`;
    }
  }
}

function renderCalendarGrid(days) {
  const container = document.getElementById('week-days-container');
  if (!container) return;

  container.innerHTML = '';

  days.forEach(day => {
    const isToday = day.is_today;
    const dayCard = document.createElement('div');
    dayCard.className = `flex flex-col rounded-xl overflow-hidden glass-panel border transition-all ${
      isToday ? 'border-sky-500/50 shadow-lg shadow-sky-500/10 ring-1 ring-sky-500/30' : 'border-slate-800'
    }`;

    // Day Header
    const formattedDate = day.date.substring(5).replace('-', '/');
    const w = day.wellness || {};
    const rhrBadge = w.resting_hr ? `<span title="FC Reposo">${w.resting_hr} bpm</span>` : '';
    const hrvBadge = w.hrv_ms ? `<span title="VFC">${w.hrv_ms} ms</span>` : (w.hrv_status ? `<span title="VFC">${w.hrv_status}</span>` : '');

    dayCard.innerHTML = `
      <div class="px-3 py-2 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div class="flex items-center gap-1.5">
          <span class="text-xs uppercase tracking-wider font-semibold ${isToday ? 'text-sky-400' : 'text-slate-300'}">${day.day_name}</span>
          <span class="text-xs font-mono text-slate-500">${formattedDate}</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
            ${rhrBadge}
            ${hrvBadge ? `• ${hrvBadge}` : ''}
          </div>
          <button type="button" onclick="openAddNoteModal('${day.date}', '${day.day_name}')"
                  title="Añadir nota en Intervals.icu para el ${day.day_name}"
                  class="px-1.5 py-0.5 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 text-[10px] font-medium flex items-center gap-0.5 transition-colors">
            <span>+</span><span>Nota</span>
          </button>
        </div>
      </div>
      <div class="p-2.5 flex-1 flex flex-col gap-2.5 bg-slate-950/40">
        <!-- Planned Section -->
        <div>
          <div class="text-[10px] uppercase font-bold text-slate-500 mb-1 flex items-center justify-between">
            <span>Planificado</span>
            <span class="text-slate-600">${day.planned.length}</span>
          </div>
          <div class="flex flex-col gap-1.5" id="planned-${day.date}">
            ${renderPlannedItems(day.planned)}
          </div>
        </div>

        <!-- Completed Section -->
        <div class="pt-2 border-t border-slate-800/80 flex-1">
          <div class="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
            <span class="flex items-center gap-1 text-emerald-400 font-semibold">
              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
              Realizado
            </span>
            <span class="text-slate-500">${day.completed.length}</span>
          </div>
          <div class="flex flex-col gap-1.5" id="completed-${day.date}">
            ${renderCompletedItems(day.completed)}
          </div>
        </div>
      </div>
    `;

    container.appendChild(dayCard);
  });
}

function renderPlannedItems(items) {
  if (!items || items.length === 0) {
    return `<div class="text-xs text-slate-600 italic py-1 text-center">Descanso o libre</div>`;
  }

  return items.map(it => {
    // NOTE items (entrenador or athlete notes)
    if (it.is_note) {
      const descPreview = (it.description || '').substring(0, 80);
      return `
        <div class="p-2 rounded-lg bg-amber-950/25 hover:bg-amber-900/35 border border-amber-500/30 text-xs transition-all group shadow-sm flex items-start justify-between gap-1.5">
          <div onclick="openPlannedModal('${it.id}')" class="flex-1 cursor-pointer min-w-0">
            <div class="flex items-center justify-between gap-1 mb-0.5">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-amber-400 text-[10px]">📝</span>
                <span class="font-medium text-amber-200 text-[11px] truncate">${it.name}</span>
              </div>
              <span class="text-[9px] text-amber-400/70 group-hover:text-amber-300 transition-colors shrink-0">Ver ↗</span>
            </div>
            ${descPreview ? `<div class="text-[10px] text-slate-400 leading-snug line-clamp-2">${descPreview}</div>` : ''}
          </div>
          <button type="button" onclick="event.stopPropagation(); deleteNoteEvent('${it.id}')"
                  title="Eliminar nota de Intervals.icu"
                  class="text-slate-500 hover:text-rose-400 p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      `;
    }

    const sportIcon = getSportIcon(it.sport_type);
    const durMins = Math.round((it.planned_duration_seconds || 0) / 60);
    const distKm = it.planned_distance_meters > 0 
      ? (it.planned_distance_meters / (it.sport_type === 'swimming' ? 1 : 1000)).toFixed(it.sport_type === 'swimming' ? 0 : 1) + (it.sport_type === 'swimming' ? 'm' : 'km') 
      : '';

    return `
      <div onclick="openPlannedModal('${it.id}')"
           class="p-2 rounded-lg bg-slate-900/90 hover:bg-slate-800/90 border border-slate-800/80 hover:border-amber-500/60 text-xs cursor-pointer transition-all group shadow-sm">
        <div class="flex items-start justify-between gap-1 mb-1">
          <div class="font-medium text-slate-200 group-hover:text-amber-300 transition-colors line-clamp-1">${it.name}</div>
          <span class="text-xs shrink-0">${sportIcon}</span>
        </div>
        <div class="flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <span>${durMins ? durMins + ' min' : ''}${distKm ? ` • ${distKm}` : ''}</span>
          <div class="flex items-center gap-1">
            ${it.planned_load ? `<span class="text-amber-400/90">${it.planned_load} TSS</span>` : ''}
            <span class="text-[9px] text-slate-500 group-hover:text-amber-400 opacity-60 group-hover:opacity-100 transition-opacity">↗</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderCompletedItems(items) {
  if (!items || items.length === 0) {
    return `<div class="text-xs text-slate-600 italic py-1 text-center">Sin actividades registradas</div>`;
  }

  return items.map(act => {
    const sportIcon = getSportIcon(act.sport_type);
    const durMins = Math.round((act.duration_seconds || 0) / 60);
    const dist = act.distance_meters > 0 
      ? (act.distance_meters / (act.sport_type === 'swimming' ? 1 : 1000)).toFixed(act.sport_type === 'swimming' ? 0 : 1) + (act.sport_type === 'swimming' ? 'm' : 'km')
      : '';
    const hr = act.avg_heart_rate ? `${Math.round(act.avg_heart_rate)} bpm` : '';

    // Efficiency badge
    let effBadge = '';
    const eff = act.efficiency || {};
    if (act.sport_type === 'cycling' && eff.fec) {
      effBadge = `<span class="text-sky-400 font-mono font-medium">FEc: ${eff.fec}</span>`;
    } else if (act.sport_type === 'running' && eff.fecp) {
      effBadge = `<span class="text-emerald-400 font-mono font-medium">FEcp: ${eff.fecp}</span>`;
    } else if (act.sport_type === 'swimming' && eff.pace_str) {
      effBadge = `<span class="text-cyan-400 font-mono font-medium">${eff.pace_str}</span>`;
    }

    return `
      <div onclick="openActivityModal('${act.activity_id}')" 
           class="p-2.5 rounded-lg glass-panel-interactive cursor-pointer border border-slate-700/60 hover:border-sky-400/60 shadow-sm transition-all group">
        <div class="flex items-center justify-between gap-1 mb-1">
          <div class="font-semibold text-slate-100 group-hover:text-sky-300 text-xs line-clamp-1 transition-colors">
            ${act.name}
          </div>
          <span class="text-sm">${sportIcon}</span>
        </div>
        <div class="flex items-center justify-between text-[11px] text-slate-300 font-mono mb-1">
          <span>${durMins} min ${dist ? `• ${dist}` : ''}</span>
          ${hr ? `<span class="text-rose-400">${hr}</span>` : ''}
        </div>
        <div class="flex items-center justify-between text-[10px] pt-1 border-t border-slate-800/80">
          ${effBadge}
          <span class="text-sky-400 flex items-center gap-0.5 group-hover:underline">
            Análisis Experto
            <svg class="w-3 h-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
          </span>
        </div>
      </div>
    `;
  }).join('');
}

function renderWeeklyZoneSummary(zoneSummary, totals) {
  const container = document.getElementById('weekly-zones-container');
  if (!container) return;

  const sports = [
    { key: 'swimming', label: 'Natación', icon: '🏊', color: 'from-cyan-500 to-blue-600' },
    { key: 'cycling', label: 'Ciclismo', icon: '🚴', color: 'from-amber-500 to-orange-600' },
    { key: 'running', label: 'Carrera a Pie', icon: '🏃', color: 'from-emerald-500 to-green-600' },
    { key: 'strength', label: 'Fuerza & Core', icon: '🏋️', color: 'from-purple-500 to-indigo-600' }
  ];

  let html = `
    <!-- Totals Header -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
      <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400 mb-1">Tiempo Planificado</span>
        <span class="text-lg font-bold font-mono text-slate-100">${totals.planned_hours} h</span>
      </div>
      <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400 mb-1">Tiempo Realizado</span>
        <span class="text-lg font-bold font-mono text-emerald-400">${totals.completed_hours} h</span>
      </div>
      <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400 mb-1">Carga Planificada</span>
        <span class="text-lg font-bold font-mono text-amber-400">${totals.planned_load} TSS</span>
      </div>
      <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400 mb-1">Carga Realizada</span>
        <span class="text-lg font-bold font-mono text-sky-400">${totals.completed_load} TSS</span>
      </div>
    </div>

    <!-- Summary Table: Totales Semanales por Disciplina (Tiempo & Km) -->
    <div class="mb-6 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/80 p-3 sm:p-4 shadow-lg">
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <span class="text-base text-amber-400">📊</span>
          <h4 class="text-xs font-bold text-slate-200 uppercase tracking-wider">Totales de la Semana por Disciplina</h4>
        </div>
        <span class="text-[11px] font-mono text-slate-400">Tiempo & Kilómetros (Plan vs Real)</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="text-[10px] uppercase font-mono text-slate-500 border-b border-slate-800/80">
              <th class="pb-2 font-semibold">Disciplina</th>
              <th class="pb-2 font-semibold text-right">Tiempo Plan</th>
              <th class="pb-2 font-semibold text-right">Tiempo Real</th>
              <th class="pb-2 font-semibold text-right">Distancia Plan</th>
              <th class="pb-2 font-semibold text-right">Distancia Real</th>
              <th class="pb-2 font-semibold text-right">Carga (TSS)</th>
              <th class="pb-2 font-semibold text-right">Cumplimiento</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60 font-mono text-[11px]">
            ${renderDisciplineTotalRows(zoneSummary, totals)}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Sports Discipline Zone Rows -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
  `;

  sports.forEach(sp => {
    const data = zoneSummary[sp.key] || { planned_hours: 0, completed_hours: 0, compliance_percent: 0, zones: {} };
    const pct = data.compliance_percent;
    const progressWidth = Math.min(pct, 100);
    const pDist = data.planned_distance_formatted || (sp.key === 'strength' ? '-' : '0 km');
    const cDist = data.completed_distance_formatted || (sp.key === 'strength' ? '-' : '0 km');

    html += `
      <div class="p-4 rounded-xl glass-panel border border-slate-800 flex flex-col justify-between">
        <div>
          <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div class="flex items-center gap-2">
              <span class="text-lg">${sp.icon}</span>
              <div>
                <span class="font-bold text-slate-100 text-sm block">${sp.label}</span>
                <span class="text-[10px] text-slate-400 font-mono">
                  ${data.planned_sessions || 0} planif. • ${data.completed_sessions || 0} hechas
                </span>
              </div>
            </div>

            <!-- TIEMPO Y KM (PLAN VS REAL) -->
            <div class="flex flex-wrap items-center gap-1.5 text-xs font-mono">
              <div class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[11px]" title="Tiempo Planificado vs Real">
                <span class="text-slate-400">⏱️ ${data.planned_hours}h</span>
                <span class="text-slate-600">/</span>
                <span class="text-emerald-400 font-bold">${data.completed_hours}h</span>
              </div>

              ${sp.key !== 'strength' ? `
                <div class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[11px]" title="Distancia Planificada vs Real">
                  <span class="text-slate-400">📍 ${pDist}</span>
                  <span class="text-slate-600">/</span>
                  <span class="text-sky-400 font-bold">${cDist}</span>
                </div>
              ` : ''}

              <span class="text-xs px-2 py-0.5 rounded-full font-bold ${pct >= 90 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}">
                ${pct}%
              </span>
            </div>
          </div>

          <!-- Overall Discipline Progress Bar -->
          <div class="w-full bg-slate-800 rounded-full h-2 mb-4 overflow-hidden">
            <div class="h-2 rounded-full bg-gradient-to-r ${sp.color}" style="width: ${progressWidth}%"></div>
          </div>

          <!-- Zone Breakdown Table -->
          <div class="space-y-1.5">
            <div class="grid grid-cols-6 text-[10px] font-semibold uppercase text-slate-500 px-1">
              <span class="col-span-2">Zona</span>
              <span class="text-right">Plan</span>
              <span class="text-right">Real</span>
              <span class="col-span-2 text-right">Comparativa</span>
            </div>
            ${renderZoneRows(data.zones)}
          </div>
        </div>
      </div>
    `;
  });

  html += `</div>`;
  container.innerHTML = html;
}

function renderZoneRows(zones) {
  const zoneLabels = {
    'Z1': 'Z1 Recuperación',
    'Z2': 'Z2 Base Aeróbica',
    'Z3': 'Z3 Tempo',
    'Z4': 'Z4 Umbral',
    'Z5': 'Z5 VO2 Máx'
  };

  const zoneColors = {
    'Z1': 'bg-slate-500',
    'Z2': 'bg-sky-500',
    'Z3': 'bg-emerald-500',
    'Z4': 'bg-amber-500',
    'Z5': 'bg-rose-500'
  };

  let rows = '';
  for (const [zKey, label] of Object.entries(zoneLabels)) {
    const zData = (zones && zones[zKey]) || { planned_mins: 0, completed_mins: 0 };
    const pMin = zData.planned_mins || 0;
    const cMin = zData.completed_mins || 0;
    const maxMin = Math.max(pMin, cMin, 60);
    const pWidth = Math.min((pMin / maxMin) * 100, 100);
    const cWidth = Math.min((cMin / maxMin) * 100, 100);

    rows += `
      <div class="grid grid-cols-6 items-center text-xs py-1 px-1 rounded hover:bg-slate-800/40 font-mono">
        <div class="col-span-2 flex items-center gap-1.5 text-slate-300">
          <span class="w-2 h-2 rounded-full ${zoneColors[zKey]}"></span>
          <span class="truncate">${zKey}</span>
        </div>
        <div class="text-right text-slate-400">${pMin}m</div>
        <div class="text-right ${cMin >= pMin && pMin > 0 ? 'text-emerald-400 font-bold' : 'text-slate-200'}">${cMin}m</div>
        <div class="col-span-2 pl-3 flex flex-col gap-0.5">
          <!-- Planned Bar (gray) -->
          <div class="w-full bg-slate-800/60 rounded h-1">
            <div class="bg-slate-600 h-1 rounded" style="width: ${pWidth}%"></div>
          </div>
          <!-- Completed Bar (colored) -->
          <div class="w-full bg-slate-800/60 rounded h-1">
            <div class="${zoneColors[zKey]} h-1 rounded" style="width: ${cWidth}%"></div>
          </div>
        </div>
      </div>
    `;
  }
  return rows;
}

function renderDisciplineTotalRows(zoneSummary, totals) {
  const sports = [
    { key: 'swimming', label: 'Natación', icon: '🏊', isSwim: true },
    { key: 'cycling', label: 'Ciclismo', icon: '🚴' },
    { key: 'running', label: 'Carrera a Pie', icon: '🏃' },
    { key: 'strength', label: 'Fuerza & Core', icon: '🏋️', isStrength: true }
  ];

  let rows = '';
  sports.forEach(sp => {
    const d = zoneSummary[sp.key] || {};
    const pHours = d.planned_hours || 0;
    const cHours = d.completed_hours || 0;
    const pDist = d.planned_distance_formatted || (sp.isStrength ? '-' : '0 km');
    const cDist = d.completed_distance_formatted || (sp.isStrength ? '-' : '0 km');
    const pLoad = d.planned_load || 0;
    const cLoad = d.completed_load || 0;
    const pct = d.compliance_percent || 0;

    rows += `
      <tr class="hover:bg-slate-900/60 transition-colors">
        <td class="py-2.5 flex items-center gap-2">
          <span class="text-base">${sp.icon}</span>
          <span class="font-bold text-slate-200">${sp.label}</span>
        </td>
        <td class="py-2.5 text-right text-slate-400 font-mono">${pHours.toFixed(1)} h</td>
        <td class="py-2.5 text-right font-mono font-bold ${cHours >= pHours && pHours > 0 ? 'text-emerald-400' : 'text-slate-100'}">${cHours.toFixed(1)} h</td>
        <td class="py-2.5 text-right text-slate-400 font-mono">${pDist}</td>
        <td class="py-2.5 text-right font-mono font-bold ${!sp.isStrength ? 'text-sky-400' : 'text-slate-500'}">${cDist}</td>
        <td class="py-2.5 text-right text-slate-400 font-mono">${pLoad} / <span class="text-amber-400">${cLoad}</span></td>
        <td class="py-2.5 text-right">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono ${pct >= 90 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'}">
            ${pct}%
          </span>
        </td>
      </tr>
    `;
  });

  // Total summary row
  const totPHours = totals.planned_hours || 0;
  const totCHours = totals.completed_hours || 0;
  const totPKm = totals.planned_km || 0;
  const totCKm = totals.completed_km || 0;
  const totPLoad = totals.planned_load || 0;
  const totCLoad = totals.completed_load || 0;
  const totPct = totPHours > 0 ? Math.round((totCHours / totPHours) * 100) : 100;

  rows += `
    <tr class="bg-slate-900/80 font-bold border-t-2 border-slate-700/80 text-slate-100">
      <td class="py-2.5 flex items-center gap-2 text-slate-100">
        <span class="text-base">🏆</span>
        <span>TOTAL SEMANAL</span>
      </td>
      <td class="py-2.5 text-right text-slate-300 font-mono">${totPHours.toFixed(1)} h</td>
      <td class="py-2.5 text-right text-emerald-400 font-mono">${totCHours.toFixed(1)} h</td>
      <td class="py-2.5 text-right text-slate-300 font-mono">${totPKm} km</td>
      <td class="py-2.5 text-right text-sky-400 font-mono">${totCKm} km</td>
      <td class="py-2.5 text-right text-amber-400 font-mono">${totPLoad} / ${totCLoad} TSS</td>
      <td class="py-2.5 text-right">
        <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-500/10 text-sky-400 border border-sky-500/20">
          ${totPct}%
        </span>
      </td>
    </tr>
  `;

  return rows;
}

// Calendar Note Modal (Intervals.icu)
function openAddNoteModal(dateStr, dayName) {
  const modal = document.getElementById('note-modal');
  if (!modal) return;
  const dateInput = document.getElementById('input-note-date');
  if (dateInput) dateInput.value = dateStr;
  const titleInput = document.getElementById('input-note-title');
  if (titleInput) titleInput.value = '';
  const descInput = document.getElementById('input-note-desc');
  if (descInput) descInput.value = '';
  const sub = document.getElementById('note-modal-subtitle');
  if (sub) sub.textContent = `Se guardará automáticamente en Intervals.icu para el ${dayName} (${dateStr})`;
  modal.classList.remove('hidden');
  setTimeout(() => document.getElementById('input-note-title')?.focus(), 100);
}

function closeNoteModal() {
  const modal = document.getElementById('note-modal');
  if (modal) modal.classList.add('hidden');
}

async function submitCalendarNote() {
  const dateVal = document.getElementById('input-note-date')?.value;
  const titleVal = document.getElementById('input-note-title')?.value.trim();
  const descVal = document.getElementById('input-note-desc')?.value.trim();
  const btn = document.getElementById('btn-submit-note');

  if (!titleVal || !dateVal) return;

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Guardando en Intervals...</span>`;
  }

  try {
    const res = await fetch('/api/calendar/note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: dateVal,
        name: titleVal,
        description: descVal
      })
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      closeNoteModal();
      await loadWeek(state.weekOffset);
    } else {
      alert(data.detail || 'No se pudo guardar la nota en Intervals.icu.');
    }
  } catch (err) {
    console.error('Error saving calendar note:', err);
    alert('Error al conectar con Intervals.icu.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>Guardar en Intervals.icu</span> <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
    }
  }
}

async function deleteNoteEvent(eventId) {
  if (!confirm('¿Deseas eliminar esta nota de tu calendario de Intervals.icu?')) return;
  try {
    const res = await fetch(`/api/calendar/event/${eventId}`, { method: 'DELETE' });
    if (res.ok) {
      await loadWeek(state.weekOffset);
    } else {
      alert('No se pudo eliminar la nota.');
    }
  } catch (err) {
    console.error('Error deleting calendar event:', err);
    alert('Error al eliminar la nota de Intervals.icu.');
  }
}

// Activity Modal
async function openActivityModal(activityId) {
  const modal = document.getElementById('activity-modal');
  const content = document.getElementById('activity-modal-content');
  if (!modal || !content) return;

  modal.classList.remove('hidden');

  // 1. Instant Cache hit (< 1ms)
  if (!state.activityDetailCache) state.activityDetailCache = {};
  if (state.activityDetailCache[activityId]) {
    renderActivityModalContent(state.activityDetailCache[activityId]);
    return;
  }

  // 2. Progressive loading: Check if activity summary exists in state.weekData for 0ms preview
  let foundAct = null;
  if (state.weekData && Array.isArray(state.weekData.days)) {
    for (const day of state.weekData.days) {
      if (Array.isArray(day.completed_activities)) {
        const match = day.completed_activities.find(a => String(a.activity_id) === String(activityId));
        if (match) {
          foundAct = match;
          break;
        }
      }
    }
  }

  if (foundAct) {
    const durMins = Math.round((foundAct.duration_seconds || 0) / 60);
    const speedMps = foundAct.avg_speed_mps || 0;
    const paceStr = speedMps > 0 
      ? (foundAct.sport_type === 'swimming'
          ? `${Math.floor(100 / speedMps / 60)}:${Math.round((100 / speedMps) % 60).toString().padStart(2, '0')}/100m`
          : `${Math.floor(1000 / speedMps / 60)}:${Math.round((1000 / speedMps) % 60).toString().padStart(2, '0')}/km`)
      : null;

    const previewData = {
      activity: {
        ...foundAct,
        splits: foundAct.splits || []
      },
      efficiency: {
        fec: foundAct.normalized_power && foundAct.avg_heart_rate ? (foundAct.normalized_power / foundAct.avg_heart_rate).toFixed(2) : null,
        iv: foundAct.normalized_power && foundAct.avg_power ? (foundAct.normalized_power / foundAct.avg_power).toFixed(2) : null,
        fecp: speedMps && foundAct.avg_heart_rate ? ((speedMps * 3.6) / foundAct.avg_heart_rate).toFixed(2) : null,
        pace_str: paceStr,
        avg_swolf: foundAct.avg_swim_swolf || null,
        dps_meters: foundAct.distance_meters && foundAct.avg_swim_strokes ? (foundAct.distance_meters / foundAct.avg_swim_strokes).toFixed(2) : null
      },
      decoupling: {
        has_decoupling: false,
        diagnosis: "Sincronizando telemetría completa y cálculo de desacople aeróbico...",
        metric_name: foundAct.sport_type === 'cycling' ? 'Pw:HR' : 'Pa:HR'
      },
      coach_analysis: {
        content: `### 1. Calidad del Estímulo (Carga Rápida)\nSesión **${foundAct.name}** (${durMins} min) detectada. Mostrando vista previa inmediata mientras se completan las métricas avanzadas en segundo plano...`
      },
      _isLoading: true
    };
    renderActivityModalContent(previewData);
  } else {
    content.innerHTML = `
      <div class="py-20 flex flex-col items-center justify-center text-slate-400">
        <svg class="animate-spin h-9 w-9 text-sky-400 mb-3" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span class="text-sm font-medium">Analizando entrenamiento y telemetría...</span>
      </div>
    `;
  }

  // 3. Fast background fetch
  try {
    const res = await fetch(`/api/activity/${activityId}`);
    if (res.ok) {
      const data = await res.json();
      state.activityDetailCache[activityId] = data;
      if (!modal.classList.contains('hidden')) {
        renderActivityModalContent(data);
      }
    }
  } catch (err) {
    console.error('Error fetching activity details:', err);
    if (!foundAct) {
      content.innerHTML = `<div class="p-8 text-center text-rose-400">Error al cargar el análisis del entrenamiento.</div>`;
    }
  }
}

// ==========================================
// Device Laps & Timeline Visualization Helpers
// ==========================================
function formatLapDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}h ${remM}m`;
  }
  if (m > 0) {
    return `${m}:${s.toString().padStart(2, '0')}`;
  }
  return `${s}s`;
}

function formatPace(speedMps) {
  if (!speedMps || speedMps <= 0) return '--:--';
  const paceSec = 1000 / speedMps;
  const m = Math.floor(paceSec / 60);
  const s = Math.round(paceSec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatSwimPace(speedMps) {
  if (!speedMps || speedMps <= 0) return '--:--';
  const paceSec = 100 / speedMps;
  const m = Math.floor(paceSec / 60);
  const s = Math.round(paceSec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatLapDistance(meters, sportType) {
  if (!meters || meters <= 0) return '0 m';
  if (sportType === 'swimming') {
    return `${Math.round(meters)} m`;
  }
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toFixed(2)} km`;
}

function toggleLapsTable() {
  const el = document.getElementById('laps-table-wrapper');
  const btn = document.getElementById('btn-toggle-laps-table');
  if (!el) return;
  if (el.classList.contains('hidden')) {
    el.classList.remove('hidden');
    if (btn) btn.textContent = 'Ocultar Tabla ▴';
  } else {
    el.classList.add('hidden');
    if (btn) btn.textContent = 'Ver Tabla ▾';
  }
}
window.toggleLapsTable = toggleLapsTable;

function renderProportionalLapsSection(act) {
  if (!act.splits || act.splits.length === 0) return '';
  const splits = act.splits;
  const isCycling = act.sport_type === 'cycling';
  const isRunning = act.sport_type === 'running';
  const isSwim = act.sport_type === 'swimming';

  const totalDuration = splits.reduce((acc, s) => acc + (s.duration_seconds || 0), 0) || act.duration_seconds || 1;

  let primaryLabel = isCycling ? 'Potencia (W)' : (isRunning ? 'Ritmo (min/km)' : (isSwim ? 'Ritmo (min/100m)' : 'Velocidad'));
  let primaryColorClass = isCycling ? 'text-amber-400' : (isRunning ? 'text-emerald-400' : (isSwim ? 'text-cyan-400' : 'text-sky-400'));
  let badgeColorClass = isCycling ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : (isRunning ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300');

  // Build the proportional ribbon blocks
  const ribbonBlocksHtml = splits.map((s, idx) => {
    const durSec = s.duration_seconds || 0;
    const durPct = Math.max(1, ((durSec / totalDuration) * 100)).toFixed(1);
    const lapNum = s.lap_index || (idx + 1);
    const durFormatted = formatLapDuration(durSec);
    const distFormatted = formatLapDistance(s.distance_meters, act.sport_type);
    const hrVal = s.avg_heart_rate ? `${Math.round(s.avg_heart_rate)} bpm` : '--';

    let primaryVal = '--';
    if (isCycling) {
      primaryVal = s.avg_power ? `${Math.round(s.avg_power)} W` : '-- W';
    } else if (isRunning) {
      primaryVal = s.avg_speed_mps ? `${formatPace(s.avg_speed_mps)}/km` : '--:--';
    } else if (isSwim) {
      primaryVal = s.avg_speed_mps ? `${formatSwimPace(s.avg_speed_mps)}/100m` : '--:--';
    } else {
      primaryVal = s.avg_speed_mps ? `${(s.avg_speed_mps * 3.6).toFixed(1)} km/h` : '--';
    }

    return `
      <div class="group relative flex flex-col justify-between p-2.5 rounded-lg border border-slate-700/60 bg-slate-800/80 hover:bg-slate-750 hover:border-slate-500 transition-all cursor-pointer shrink-0"
           style="flex: ${Math.max(15, durSec)} 1 0; min-width: 96px;"
           title="Lap ${lapNum}: ${durFormatted} • ${distFormatted} • ${primaryVal} • ${hrVal}">
        <div class="flex items-center justify-between gap-1 mb-1 pb-1 border-b border-slate-700/50">
          <span class="text-[10px] font-mono font-bold text-slate-300">L${lapNum}</span>
          <span class="text-[10px] font-mono text-slate-400">${durFormatted}</span>
        </div>
        <div class="space-y-1 my-1">
          <div class="flex items-baseline justify-between gap-1">
            <span class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">${isCycling ? 'Pot' : 'Ritmo'}</span>
            <span class="text-xs font-mono font-bold ${primaryColorClass}">${primaryVal}</span>
          </div>
          <div class="flex items-baseline justify-between gap-1">
            <span class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">FC</span>
            <span class="text-[11px] font-mono font-semibold text-rose-400 flex items-center gap-0.5">
              <span class="text-[9px] text-rose-500">❤️</span>${hrVal}
            </span>
          </div>
        </div>
        <div class="mt-1 pt-1 border-t border-slate-700/30 flex justify-between text-[9px] font-mono text-slate-400">
          <span>${distFormatted}</span>
          <span>${durPct}%</span>
        </div>
      </div>
    `;
  }).join('');

  // Table rows for full breakdown
  const tableRowsHtml = splits.map((s, idx) => {
    const lapNum = s.lap_index || (idx + 1);
    const durSec = s.duration_seconds || 0;
    const durPct = ((durSec / totalDuration) * 100).toFixed(1);
    const durFormatted = formatLapDuration(durSec);
    const distFormatted = formatLapDistance(s.distance_meters, act.sport_type);
    const hrVal = s.avg_heart_rate ? `${Math.round(s.avg_heart_rate)} bpm` : '--';
    const maxHrVal = s.max_heart_rate ? `${Math.round(s.max_heart_rate)} bpm` : '--';

    let primaryVal = '--';
    if (isCycling) {
      primaryVal = s.avg_power ? `${Math.round(s.avg_power)} W` : '--';
    } else if (isRunning) {
      primaryVal = s.avg_speed_mps ? `${formatPace(s.avg_speed_mps)} /km` : '--';
    } else if (isSwim) {
      primaryVal = s.avg_speed_mps ? `${formatSwimPace(s.avg_speed_mps)} /100m` : '--';
    } else {
      primaryVal = s.avg_speed_mps ? `${(s.avg_speed_mps * 3.6).toFixed(1)} km/h` : '--';
    }

    return `
      <tr class="border-b border-slate-800/60 hover:bg-slate-800/40 text-xs font-mono">
        <td class="py-2 px-2.5 font-bold text-slate-200">L${lapNum}</td>
        <td class="py-2 px-2.5 text-slate-300">${durFormatted} <span class="text-[10px] text-slate-500">(${durPct}%)</span></td>
        <td class="py-2 px-2.5 text-slate-300">${distFormatted}</td>
        <td class="py-2 px-2.5 font-bold ${primaryColorClass}">${primaryVal}</td>
        <td class="py-2 px-2.5 text-rose-400 font-semibold">${hrVal}</td>
        <td class="py-2 px-2.5 text-rose-500">${maxHrVal}</td>
      </tr>
    `;
  }).join('');

  return `
    <div class="mb-6 p-4 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl">
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-800 flex-wrap gap-2">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg ${badgeColorClass} flex items-center justify-center font-bold text-sm">
            ⏱️
          </div>
          <div>
            <h3 class="text-xs font-bold text-slate-100 uppercase tracking-wider">Laps Grabados en Dispositivo (${splits.length} laps)</h3>
            <p class="text-[10px] text-slate-400">Ancho proporcional a la duración real • Métricas: ${isCycling ? 'Vatios (W) y Frecuencia Cardíaca (FC)' : (isRunning ? 'Ritmo (min/km) y FC' : 'Ritmo (min/100m) y FC')}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-mono px-2 py-0.5 rounded border ${badgeColorClass}">
            Total: ${formatLapDuration(totalDuration)}
          </span>
          <button type="button" onclick="toggleLapsTable()" id="btn-toggle-laps-table" class="text-[11px] font-mono px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 transition-colors">
            Ver Tabla ▾
          </button>
        </div>
      </div>

      <!-- Proportional Ribbon Timeline Container (Horizontally Scrollable) -->
      <div class="mb-4">
        <div class="flex items-center justify-between text-[10px] font-mono text-slate-500 mb-1 px-1">
          <span>00:00 (Inicio)</span>
          <span class="text-slate-400">Bloques con ancho proporcional al tiempo de cada lap</span>
          <span>${formatLapDuration(totalDuration)} (Fin)</span>
        </div>
        <div class="flex items-stretch gap-1.5 overflow-x-auto pb-2 p-1.5 rounded-xl bg-slate-950/80 border border-slate-800 scrollbar-thin">
          ${ribbonBlocksHtml}
        </div>
      </div>

      <!-- Dual-Axis Telemetry Chart -->
      <div>
        <div class="h-48 w-full bg-slate-950/60 rounded-xl p-2 border border-slate-800/80">
          <canvas id="splitsChart"></canvas>
        </div>
      </div>

      <!-- Collapsible Detailed Table -->
      <div id="laps-table-wrapper" class="hidden overflow-x-auto mt-4 pt-3 border-t border-slate-800/80">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="text-[10px] font-mono uppercase tracking-wider text-slate-400 border-b border-slate-800 bg-slate-950/40">
              <th class="py-1.5 px-2.5">Lap</th>
              <th class="py-1.5 px-2.5">Duración (% total)</th>
              <th class="py-1.5 px-2.5">Distancia</th>
              <th class="py-1.5 px-2.5">${primaryLabel}</th>
              <th class="py-1.5 px-2.5">FC Media</th>
              <th class="py-1.5 px-2.5">FC Máx</th>
            </tr>
          </thead>
          <tbody>
            ${tableRowsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderActivityModalContent(data) {
  const content = document.getElementById('activity-modal-content');
  if (!content) return;

  const act = data.activity || {};
  const eff = data.efficiency || {};
  const dec = data.decoupling || {};
  const coach = data.coach_analysis || { content: '' };
  const durMins = Math.round((act.duration_seconds || 0) / 60);
  const distKm = ((act.distance_meters || 0) / (act.sport_type === 'swimming' ? 1 : 1000)).toFixed(act.sport_type === 'swimming' ? 0 : 2);

  let effMetricHtml = '';
  if (act.sport_type === 'cycling') {
    effMetricHtml = `
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">Factor de Eficiencia (FEc = NP/FC)</span>
        <span class="text-xl font-bold font-mono text-sky-400">${eff.fec || 'N/A'} <span class="text-xs text-slate-400">W/bpm</span></span>
      </div>
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">Índice de Variabilidad (IV = NP/Pmed)</span>
        <span class="text-xl font-bold font-mono text-amber-400">${eff.iv || 'N/A'}</span>
      </div>
    `;
  } else if (act.sport_type === 'running') {
    effMetricHtml = `
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">Factor de Eficiencia (FEcp = Vel/FC)</span>
        <span class="text-xl font-bold font-mono text-emerald-400">${eff.fecp || 'N/A'}</span>
      </div>
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">Ritmo Medio</span>
        <span class="text-xl font-bold font-mono text-slate-100">${eff.pace_str || 'N/A'}</span>
      </div>
    `;
  } else if (act.sport_type === 'swimming') {
    effMetricHtml = `
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">Ritmo Medio / 100m</span>
        <span class="text-xl font-bold font-mono text-cyan-400">${eff.pace_str || 'N/A'}</span>
      </div>
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">Distancia por Brazada (DPS)</span>
        <span class="text-xl font-bold font-mono text-sky-300">${eff.dps_meters ? eff.dps_meters + ' m' : 'N/A'}</span>
      </div>
    `;
  }

  // Decoupling Card
  let decouplingHtml = '';
  if (dec.has_decoupling) {
    const decVal = dec.decoupling_percent;
    const badgeColor = dec.status_color === 'emerald' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : (dec.status_color === 'blue' ? 'text-sky-400 border-sky-500/30 bg-sky-500/10' : 'text-amber-400 border-amber-500/30 bg-amber-500/10');

    decouplingHtml = `
      <div class="p-4 rounded-xl bg-slate-900/90 border border-slate-800 mb-6">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Desacople Cardiovascular (${dec.metric_name})</span>
          </div>
          <span class="px-2.5 py-1 rounded-full text-xs font-bold font-mono ${badgeColor}">
            ${decVal}%
          </span>
        </div>
        <p class="text-xs text-slate-300 mb-3">${dec.diagnosis}</p>
        <div class="grid grid-cols-2 gap-3 text-xs font-mono bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
          <div>
            <span class="text-slate-500 block text-[10px] uppercase">1ª Mitad</span>
            <span class="text-slate-200">${dec.half_1 ? dec.half_1.label : ''}</span>
          </div>
          <div>
            <span class="text-slate-500 block text-[10px] uppercase">2ª Mitad</span>
            <span class="text-slate-200">${dec.half_2 ? dec.half_2.label : ''}</span>
          </div>
        </div>
      </div>
    `;
  }

  content.innerHTML = `
    <!-- Header -->
    <div class="flex items-start justify-between pb-4 mb-4 border-b border-slate-800">
      <div>
        <div class="flex items-center gap-2 mb-1 flex-wrap">
          <span class="text-xl">${getSportIcon(act.sport_type)}</span>
          <h2 class="text-lg font-bold text-slate-100">${act.name}</h2>
          ${data._isLoading ? `
            <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-sky-500/10 text-sky-400 border border-sky-500/20 flex items-center gap-1">
              <svg class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
              Sincronizando telemetría...
            </span>
          ` : ''}
        </div>
        <span class="text-xs text-slate-400 font-mono">${act.start_time || ''}</span>
      </div>
      <div class="text-right">
        <span class="text-lg font-mono font-bold text-slate-100">${durMins} min</span>
        <span class="text-xs text-slate-400 block font-mono">${distKm} ${act.sport_type === 'swimming' ? 'm' : 'km'}</span>
      </div>
    </div>

    <!-- Core Metrics Grid -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">FC Media</span>
        <span class="text-xl font-bold font-mono text-rose-400">${act.avg_heart_rate ? Math.round(act.avg_heart_rate) + ' bpm' : 'N/A'}</span>
      </div>
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
        <span class="text-xs text-slate-400">FC Máxima</span>
        <span class="text-xl font-bold font-mono text-rose-500">${act.max_heart_rate ? Math.round(act.max_heart_rate) + ' bpm' : 'N/A'}</span>
      </div>
      ${effMetricHtml}
    </div>

    <!-- Decoupling Section -->
    ${decouplingHtml}

    <!-- Device Laps Proportional Ribbon & Chart -->
    ${renderProportionalLapsSection(act)}

    <!-- Expert Coach AI Evaluation Report -->
    <div class="p-5 rounded-xl bg-gradient-to-b from-slate-900 to-slate-950 border border-purple-500/20 shadow-xl mb-6">
      <div class="flex items-center gap-2 mb-3">
        <div class="w-7 h-7 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold text-sm">
          ⚡
        </div>
        <div>
          <h3 class="text-sm font-bold text-slate-100">Análisis del Entrenador Experto en Triatlón</h3>
          <span class="text-[11px] text-purple-400">Fase de Base Aeróbica • Tolerancia Biológica y Deriva Cardíaca</span>
        </div>
      </div>
      <div class="prose prose-invert prose-sm max-w-none text-slate-300 text-xs leading-relaxed space-y-3">
        ${formatCoachReport(coach.content)}
      </div>
    </div>

    <!-- Interactive Activity Chatbot with Coach -->
    <div class="p-4 sm:p-5 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl">
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center font-bold text-sm">
            💬
          </div>
          <div>
            <h4 class="text-xs font-bold text-slate-100">Consulta con tu Entrenador sobre esta sesión</h4>
            <p class="text-[10px] text-slate-400">Pregúntale detalles sobre el desacople, métricas por km o recomendaciones para tus próximas sesiones.</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-mono px-2 py-0.5 rounded ${state.athleteStatus?.ai?.has_key ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' : 'bg-slate-800 text-slate-400 border border-slate-700'}">
            ${state.athleteStatus?.ai?.has_key ? '● Gemini 2.0 Flash' : '⚡ Motor Experto Fisiología'}
          </span>
          <span class="hidden sm:inline-block text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-sky-400 border border-slate-700">
            Sesión: ${act.name}
          </span>
        </div>
      </div>

      <!-- Quick prompts for this activity -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cómo valoras mi desacople cardiovascular en esta sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 transition-colors">
          ¿Cómo estuvo mi desacople?
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cuál fue mi split más eficiente y cómo progresó el ritmo?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 transition-colors">
          Analizar splits por km
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cómo fue mi cadencia y biomecánica en esta sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 transition-colors">
          Cadencia y biomecánica
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cuántas calorías quemé y qué pauta de carbohidratos me recomiendas?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 transition-colors">
          Calorías y nutrición
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Debería haber apretado más o estuvo bien no subir de pulso?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 transition-colors">
          ¿Debería haber forzado más?
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cómo debería ajustar el entrenamiento de mañana según esta carga?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 transition-colors">
          ¿Cómo ajustar mañana?
        </button>
      </div>

      <!-- Messages container -->
      <div id="activity-chat-messages" class="space-y-3 max-h-64 overflow-y-auto mb-3 p-3 rounded-xl bg-slate-950/70 border border-slate-800/80">
        <!-- Rendered dynamically -->
      </div>

      <!-- Input Form -->
      <form id="form-activity-chat" onsubmit="event.preventDefault(); submitActivityChatMessage('${act.activity_id}');" class="flex gap-2">
        <input type="text" id="input-activity-chat" placeholder="Pregunta al entrenador sobre esta sesión..."
          class="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500 transition-colors">
        <button type="submit" id="btn-activity-chat-send"
          class="px-4 py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-sky-500/20 transition-all shrink-0">
          <span>Enviar</span>
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
        </button>
      </form>
    </div>
  `;

  // Initialize and render activity chat messages
  renderActivityChatMessages(act.activity_id, act);

  // Render splits chart if splits exist
  if (act.splits && act.splits.length > 1) {
    setTimeout(() => {
      renderWorkoutSplitsChart('splitsChart', act.splits, act.sport_type);
    }, 50);
  }
}

function setActivityPrompt(activityId, text) {
  const input = document.getElementById('input-activity-chat');
  if (input) {
    input.value = text;
    submitActivityChatMessage(activityId);
  }
}

function renderActivityChatMessages(activityId, act) {
  if (!state.activityChatHistory) state.activityChatHistory = {};
  if (!state.activityChatHistory[activityId]) {
    const durMins = Math.round((act.duration_seconds || 0) / 60);
    const distStr = act.distance_meters > 0 
      ? `${(act.distance_meters / (act.sport_type === 'swimming' ? 1 : 1000)).toFixed(1)} ${act.sport_type === 'swimming' ? 'm' : 'km'}` 
      : '';
    state.activityChatHistory[activityId] = [{
      role: 'assistant',
      content: `Hola Pastor. He examinado toda la telemetría y splits de **${act.name}** (${durMins} min${distStr ? `, ${distStr}` : ''}). ¿Tienes alguna duda sobre tu deriva cardiovascular, el ritmo por parcial o cómo asimilar este estímulo en tus próximos días?`
    }];
  }

  const container = document.getElementById('activity-chat-messages');
  if (!container) return;

  container.innerHTML = state.activityChatHistory[activityId].map(msg => {
    const isUser = msg.role === 'user';
    return `
      <div class="flex gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}">
        ${!isUser ? `
          <div class="w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400 shrink-0 font-bold text-[10px]">
            Coach
          </div>
        ` : ''}
        <div class="max-w-[85%] rounded-2xl p-2.5 text-xs leading-relaxed ${
          isUser 
            ? 'bg-sky-600 text-white rounded-tr-none' 
            : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none prose prose-invert'
        }">
          ${formatCoachReport(msg.content)}
        </div>
      </div>
    `;
  }).join('');

  container.scrollTop = container.scrollHeight;
}

async function submitActivityChatMessage(activityId) {
  const input = document.getElementById('input-activity-chat');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  if (!state.activityChatHistory) state.activityChatHistory = {};
  if (!state.activityChatHistory[activityId]) state.activityChatHistory[activityId] = [];

  // Append user message
  state.activityChatHistory[activityId].push({ role: 'user', content: text });
  
  // Re-render
  const container = document.getElementById('activity-chat-messages');
  if (container) {
    const userMsgEl = document.createElement('div');
    userMsgEl.className = 'flex gap-2.5 justify-end';
    userMsgEl.innerHTML = `
      <div class="max-w-[85%] rounded-2xl p-2.5 text-xs leading-relaxed bg-sky-600 text-white rounded-tr-none">
        ${formatCoachReport(text)}
      </div>
    `;
    container.appendChild(userMsgEl);

    // Loader
    const loaderEl = document.createElement('div');
    loaderEl.id = 'activity-chat-loader';
    loaderEl.className = 'flex gap-2.5 justify-start';
    loaderEl.innerHTML = `
      <div class="w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400 shrink-0 font-bold text-[10px]">
        Coach
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-none p-2.5 flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce" style="animation-delay: 0.15s"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce" style="animation-delay: 0.3s"></span>
      </div>
    `;
    container.appendChild(loaderEl);
    container.scrollTop = container.scrollHeight;
  }

  try {
    const res = await fetch(`/api/activity/${activityId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: state.activityChatHistory[activityId]
      })
    });
    const data = await res.json();
    document.getElementById('activity-chat-loader')?.remove();

    const reply = data.reply || 'No se pudo generar respuesta en este momento.';
    state.activityChatHistory[activityId].push({ role: 'assistant', content: reply });

    if (container) {
      const botMsgEl = document.createElement('div');
      botMsgEl.className = 'flex gap-2.5 justify-start';
      botMsgEl.innerHTML = `
        <div class="w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400 shrink-0 font-bold text-[10px]">
          Coach
        </div>
        <div class="max-w-[85%] rounded-2xl p-2.5 text-xs leading-relaxed bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none prose prose-invert">
          ${formatCoachReport(reply)}
        </div>
      `;
      container.appendChild(botMsgEl);
      container.scrollTop = container.scrollHeight;
    }
  } catch (err) {
    document.getElementById('activity-chat-loader')?.remove();
    console.error('Error in activity chat:', err);
  }
}

function closeActivityModal() {
  const modal = document.getElementById('activity-modal');
  if (modal) modal.classList.add('hidden');
}

// Planned Workout Modal (Intervals.icu)
async function openPlannedModal(eventId) {
  const modal = document.getElementById('planned-modal');
  const content = document.getElementById('planned-modal-content');
  if (!modal || !content) return;

  modal.classList.remove('hidden');

  // Find in local week data first for instant rendering
  let eventItem = null;
  if (state.weekData && state.weekData.days) {
    for (const d of state.weekData.days) {
      const match = (d.planned || []).find(p => String(p.id) === String(eventId));
      if (match) {
        eventItem = match;
        break;
      }
    }
  }

  if (eventItem) {
    renderPlannedModalContent(eventItem);
  } else {
    content.innerHTML = `
      <div class="py-16 flex flex-col items-center justify-center text-slate-400">
        <svg class="animate-spin h-8 w-8 text-amber-400 mb-3" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span class="text-xs">Cargando sesión de Intervals.icu...</span>
      </div>
    `;
  }

  // Fetch complete details from backend /api/planned/{id}
  try {
    const res = await fetch(`/api/planned/${eventId}`);
    if (res.ok) {
      const freshData = await res.json();
      renderPlannedModalContent(freshData);
    }
  } catch (err) {
    console.warn('Error fetching fresh planned details:', err);
  }
}

function renderPlannedModalContent(ev) {
  const content = document.getElementById('planned-modal-content');
  if (!content) return;

  const sportIcon = getSportIcon(ev.sport_type);
  const durMins = Math.round((ev.planned_duration_seconds || 0) / 60);
  const durHours = durMins >= 60 ? `${(durMins / 60).toFixed(1)} h` : `${durMins} min`;
  const distKm = ev.planned_distance_meters > 0 
    ? `${(ev.planned_distance_meters / (ev.sport_type === 'swimming' ? 1 : 1000)).toFixed(ev.sport_type === 'swimming' ? 0 : 2)} ${ev.sport_type === 'swimming' ? 'm' : 'km'}` 
    : '';

  const isNote = ev.is_note || ev.category === 'NOTE';
  const badgeText = isNote ? 'Nota del Entrenador' : 'Intervals.icu • Planificado';
  const badgeColor = isNote ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20';

  // Format description text cleanly
  let rawDesc = (ev.description || '').trim();
  let descHtml = '';
  if (rawDesc) {
    descHtml = rawDesc
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n\n/g, '<div class="my-2 border-t border-slate-800/60"></div>')
      .replace(/\n/g, '<br/>');
  } else {
    descHtml = '<span class="text-slate-500 italic">No hay descripción adicional de texto en Intervals.icu para esta sesión.</span>';
  }

  // Target Zones preview if present
  let zonesHtml = '';
  if (ev.target_zones && Object.keys(ev.target_zones).length > 0) {
    const tz = ev.target_zones;
    const zList = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5'];
    const hasZones = zList.some(z => (tz[z] || 0) > 0);
    if (hasZones) {
      const zPills = zList.map(z => {
        const secs = tz[z] || 0;
        const mins = Math.round(secs / 60);
        return `
          <div class="p-2 rounded-lg bg-slate-900 border border-slate-800/80 text-center font-mono">
            <span class="text-[10px] text-slate-400 block">${z}</span>
            <span class="text-xs font-bold text-slate-200">${mins}m</span>
          </div>
        `;
      }).join('');

      zonesHtml = `
        <div class="mt-4 pt-4 border-t border-slate-800/80">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-2">Distribución Estimada por Zonas</span>
          <div class="grid grid-cols-5 gap-2">
            ${zPills}
          </div>
        </div>
      `;
    }
  }

  content.innerHTML = `
    <!-- Header -->
    <div class="flex items-start justify-between pb-4 mb-4 border-b border-slate-800">
      <div>
        <div class="flex items-center gap-2 mb-1.5 flex-wrap">
          <span class="text-2xl">${sportIcon}</span>
          <h2 class="text-lg font-bold text-slate-100">${ev.name}</h2>
          <span class="px-2.5 py-0.5 rounded-full text-[10px] font-medium border ${badgeColor}">
            ${badgeText}
          </span>
        </div>
        <div class="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <span>📅 ${ev.date || 'Esta semana'}</span>
          ${ev.start_time ? `<span>• ${ev.start_time.substring(11, 16) || ''}</span>` : ''}
        </div>
      </div>
    </div>

    <!-- Quick Metrics Grid -->
    ${!isNote ? `
      <div class="grid grid-cols-3 gap-3 mb-5">
        <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
          <span class="text-xs text-slate-400 mb-0.5">Tiempo Estimado</span>
          <span class="text-base font-bold font-mono text-slate-100">${durMins > 0 ? durHours : 'Libre'}</span>
        </div>
        <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
          <span class="text-xs text-slate-400 mb-0.5">Distancia</span>
          <span class="text-base font-bold font-mono text-sky-400">${distKm || 'N/A'}</span>
        </div>
        <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
          <span class="text-xs text-slate-400 mb-0.5">Carga Prevista</span>
          <span class="text-base font-bold font-mono text-amber-400">${ev.planned_load ? ev.planned_load + ' TSS' : 'N/A'}</span>
        </div>
      </div>
    ` : ''}

    <!-- Description & Intervals.icu Workout Instructions -->
    <div class="p-4 sm:p-5 rounded-xl bg-slate-900/90 border border-slate-800">
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-800/80">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
          <span>📝</span> Descripción del Entrenamiento (Intervals.icu)
        </h3>
        <span class="text-[10px] text-slate-500 font-mono">ID: ${ev.id}</span>
      </div>

      <div class="text-xs font-mono leading-relaxed text-slate-200 bg-slate-950/80 p-3.5 rounded-lg border border-slate-800/90 max-h-80 overflow-y-auto whitespace-pre-wrap selection:bg-amber-500 selection:text-black">
${descHtml}
      </div>

      ${zonesHtml}
    </div>

    <!-- Interactive Planned Workout Chatbot -->
    <div class="p-4 sm:p-5 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl mt-5">
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-sm">
            💬
          </div>
          <div>
            <h4 class="text-xs font-bold text-slate-100">Consulta con tu Entrenador sobre esta sesión planificada</h4>
            <p class="text-[10px] text-slate-400">Pregúntale cómo calentar, a qué vatios/ritmo hacer las series o qué estrategia de hidratación y nutrición seguir.</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-mono px-2 py-0.5 rounded ${state.athleteStatus?.ai?.has_key ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' : 'bg-slate-800 text-slate-400 border border-slate-700'}">
            ${state.athleteStatus?.ai?.has_key ? '🤖 Gemini Coach IA' : '🧠 Motor Experto Triatlón'}
          </span>
        </div>
      </div>

      <!-- Quick prompts for planned workout -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        <button type="button" onclick="setPlannedPrompt('${ev.id}', '¿Cómo estructuro el calentamiento óptimo para esta sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700 transition-colors">
          Calentamiento óptimo
        </button>
        <button type="button" onclick="setPlannedPrompt('${ev.id}', '¿A qué vatios o ritmo exacto debo hacer las partes principales?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700 transition-colors">
          Vatios / Ritmos de series
        </button>
        <button type="button" onclick="setPlannedPrompt('${ev.id}', '¿Qué pauta de hidratación y nutrición debo llevar durante la sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700 transition-colors">
          Nutrición e Hidratación
        </button>
        <button type="button" onclick="setPlannedPrompt('${ev.id}', 'Si noto fatiga acumulada en las piernas, ¿cómo adapto o recorto el volumen?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700 transition-colors">
          Adaptar por fatiga
        </button>
      </div>

      <!-- Chat history messages container -->
      <div id="planned-chat-messages" class="space-y-3 max-h-64 overflow-y-auto mb-3 p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
        <!-- Rendered by renderPlannedChatMessages -->
      </div>

      <!-- Chat input form -->
      <form id="form-planned-chat" onsubmit="event.preventDefault(); submitPlannedChatMessage('${ev.id}');" class="flex gap-2">
        <input 
          type="text" 
          id="input-planned-chat"
          placeholder="Haz cualquier pregunta al entrenador sobre esta sesión..." 
          class="flex-1 bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition-colors"
        />
        <button 
          type="submit" 
          id="btn-planned-chat-submit"
          class="px-4 py-2 bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-slate-950 font-semibold rounded-xl text-xs transition-all shadow-lg shadow-amber-900/20 flex items-center gap-1.5"
        >
          <span>Preguntar</span>
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
        </button>
      </form>
    </div>

    <!-- Footer Actions -->
    <div class="mt-5 pt-3 border-t border-slate-800 flex items-center justify-between flex-wrap gap-2 text-xs">
      <a href="https://intervals.icu/events/${ev.id}" target="_blank" rel="noopener"
         class="text-amber-400 hover:text-amber-300 flex items-center gap-1 hover:underline">
        <span>Abrir en Intervals.icu</span>
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
      </a>

      <button type="button" onclick="closePlannedModal(); switchTab('form');"
        class="px-3.5 py-1.5 rounded-lg bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 border border-purple-500/30 font-medium transition-colors flex items-center gap-1.5">
        <span>💬</span>
        <span>Ir al Chat General del Coach</span>
      </button>
    </div>
  `;

  // Initialize and render planned chat messages
  renderPlannedChatMessages(ev.id, ev);
}

function renderPlannedChatMessages(eventId, ev) {
  if (!state.plannedChatHistory) state.plannedChatHistory = {};
  if (!state.plannedChatHistory[eventId]) {
    const durMins = Math.round((ev.planned_duration_seconds || 0) / 60);
    const distStr = ev.planned_distance_meters > 0 
      ? `${(ev.planned_distance_meters / (ev.sport_type === 'swimming' ? 1 : 1000)).toFixed(1)} ${ev.sport_type === 'swimming' ? 'm' : 'km'}` 
      : '';
    state.plannedChatHistory[eventId] = [{
      role: 'assistant',
      content: `Hola Pastor. He examinado los detalles de tu sesión planificada: **${ev.name || 'Sesión'}** (${durMins > 0 ? durMins + ' min' : 'Libre'}${distStr ? `, ${distStr}` : ''}).\n\n¿Tienes alguna duda sobre los vatios o ritmos objetivo, el calentamiento, nutrición o cómo modular los intervalos según tu estado de fatiga actual?`
    }];
  }

  const container = document.getElementById('planned-chat-messages');
  if (!container) return;
  container.innerHTML = '';

  state.plannedChatHistory[eventId].forEach(msg => {
    const isUser = msg.role === 'user';
    const msgEl = document.createElement('div');
    msgEl.className = `flex gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`;
    msgEl.innerHTML = `
      ${!isUser ? `
        <div class="w-6 h-6 rounded-md bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0 font-bold text-[10px]">
          Coach
        </div>
      ` : ''}
      <div class="max-w-[85%] rounded-xl p-2.5 text-xs leading-relaxed ${
        isUser 
          ? 'bg-amber-600 text-white rounded-tr-none' 
          : 'bg-slate-800/90 border border-slate-700/60 text-slate-200 rounded-tl-none prose prose-invert'
      }">
        ${formatCoachReport(msg.content)}
      </div>
    `;
    container.appendChild(msgEl);
  });
  container.scrollTop = container.scrollHeight;
}

function setPlannedPrompt(eventId, text) {
  const input = document.getElementById('input-planned-chat');
  if (input) {
    input.value = text;
    submitPlannedChatMessage(eventId);
  }
}
window.setPlannedPrompt = setPlannedPrompt;

async function submitPlannedChatMessage(eventId) {
  const input = document.getElementById('input-planned-chat');
  const btn = document.getElementById('btn-planned-chat-submit');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  if (!state.plannedChatHistory) state.plannedChatHistory = {};
  if (!state.plannedChatHistory[eventId]) state.plannedChatHistory[eventId] = [];

  state.plannedChatHistory[eventId].push({ role: 'user', content: text });
  renderPlannedChatMessages(eventId, {});

  // Append temporary loader
  const container = document.getElementById('planned-chat-messages');
  const loaderId = 'loader-planned-' + Date.now();
  if (container) {
    const loaderEl = document.createElement('div');
    loaderEl.id = loaderId;
    loaderEl.className = 'flex gap-2.5 justify-start';
    loaderEl.innerHTML = `
      <div class="w-6 h-6 rounded-md bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0 font-bold text-[10px]">
        Coach
      </div>
      <div class="bg-slate-800 border border-slate-700 rounded-xl rounded-tl-none p-2.5 flex items-center gap-1.5">
        <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce" style="animation-delay: 0.15s"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce" style="animation-delay: 0.3s"></span>
      </div>
    `;
    container.appendChild(loaderEl);
    container.scrollTop = container.scrollHeight;
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/planned/${eventId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: state.plannedChatHistory[eventId].slice(0, -1)
      })
    });
    const data = await res.json();
    const l = document.getElementById(loaderId);
    if (l) l.remove();
    state.plannedChatHistory[eventId].push({ role: 'assistant', content: data.reply });
    renderPlannedChatMessages(eventId, {});
  } catch (err) {
    const l = document.getElementById(loaderId);
    if (l) l.remove();
    state.plannedChatHistory[eventId].push({
      role: 'assistant',
      content: 'Disculpa Pastor, ocurrió un problema al conectar con el entrenador para esta sesión planificada.'
    });
    renderPlannedChatMessages(eventId, {});
  } finally {
    if (btn) btn.disabled = false;
  }
}
window.submitPlannedChatMessage = submitPlannedChatMessage;

function closePlannedModal() {
  const modal = document.getElementById('planned-modal');
  if (modal) modal.classList.add('hidden');
}

// Page 2: PMC and Chatbot
async function loadPMC(days) {
  state.pmcDays = days;
  try {
    const res = await fetch(`/api/pmc?days=${days}`);
    const data = await res.json();
    state.pmcData = data;

    // Update Form Status Cards
    document.getElementById('pmc-ctl-val').textContent = data.current_ctl;
    document.getElementById('pmc-atl-val').textContent = data.current_atl;
    const tsbEl = document.getElementById('pmc-tsb-val');
    if (tsbEl) {
      tsbEl.textContent = data.current_tsb;
      tsbEl.className = data.current_tsb >= 0 ? 'text-2xl font-bold font-mono text-emerald-400' : 'text-2xl font-bold font-mono text-amber-400';
    }
    document.getElementById('pmc-acwr-val').textContent = data.acwr;

    // Render Canvas
    renderPMCChart('pmcChart', data.series);
  } catch (err) {
    console.error('Error loading PMC:', err);
  }
}

async function submitChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  appendChatMessage('user', text);

  // Loading bubble
  const loaderId = appendChatLoader();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: state.chatHistory })
    });
    const data = await res.json();
    removeChatLoader(loaderId);
    appendChatMessage('assistant', data.reply);
  } catch (err) {
    removeChatLoader(loaderId);
    appendChatMessage('assistant', 'Lo siento, ocurrió un error al consultar con el entrenador.');
  }
}

function appendChatMessage(role, content) {
  state.chatHistory.push({ role, content });
  const container = document.getElementById('chat-messages-container');
  if (!container) return;

  const isUser = role === 'user';
  const msgEl = document.createElement('div');
  msgEl.className = `flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`;

  const formattedContent = formatCoachReport(content);

  msgEl.innerHTML = `
    ${!isUser ? `
      <div class="w-8 h-8 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400 shrink-0 font-bold text-xs">
        Coach
      </div>
    ` : ''}
    <div class="max-w-[85%] rounded-2xl p-3.5 text-xs leading-relaxed ${
      isUser 
        ? 'bg-sky-600 text-white rounded-tr-none' 
        : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none prose prose-invert'
    }">
      ${formattedContent}
    </div>
  `;

  container.appendChild(msgEl);
  container.scrollTop = container.scrollHeight;
}

function appendChatLoader() {
  const container = document.getElementById('chat-messages-container');
  const id = 'loader-' + Date.now();
  const el = document.createElement('div');
  el.id = id;
  el.className = 'flex gap-3 justify-start';
  el.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400 shrink-0 font-bold text-xs">
      Coach
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-none p-3.5 flex items-center gap-1.5">
      <span class="w-2 h-2 rounded-full bg-purple-400 animate-bounce"></span>
      <span class="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style="animation-delay: 0.15s"></span>
      <span class="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style="animation-delay: 0.3s"></span>
    </div>
  `;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeChatLoader(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// Settings Modal
async function openSettingsModal() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  modal.classList.remove('hidden');

  if (state.athleteStatus) {
    const s = state.athleteStatus;
    const garminEmail = document.getElementById('input-garmin-email');
    if (garminEmail && s.garmin) garminEmail.value = s.garmin.has_credentials ? '••••••••' : '';
    const intervalsKey = document.getElementById('input-intervals-key');
    if (intervalsKey && s.intervals) intervalsKey.value = s.intervals.has_api_key ? '••••••••' : '';
    const intervalsId = document.getElementById('input-intervals-id');
    if (intervalsId && s.intervals) intervalsId.value = s.intervals.athlete_id || '';

    // Populate Gemini status
    const geminiInput = document.getElementById('input-gemini-key');
    const geminiBadge = document.getElementById('gemini-status-badge');
    if (geminiInput && s.ai) {
      geminiInput.value = s.ai.has_key ? '••••••••' : '';
    }
    if (geminiBadge && s.ai) {
      if (s.ai.has_key) {
        geminiBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-purple-500/10 text-purple-400 border border-purple-500/30 flex items-center gap-1';
        geminiBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse"></span> <span>Gemini IA Activo</span>';
      } else {
        geminiBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700';
        geminiBadge.innerHTML = '<span>Modo Experto Local</span>';
      }
    }
    
    // Populate thresholds
    if (s.thresholds) {
      populateThresholdsUI(s.thresholds);
    }
  }

  // If Intervals.icu is connected, fetch live thresholds to ensure always up-to-date
  if (state.athleteStatus?.intervals?.connected) {
    syncThresholds(true); // silent background sync
  }
}

function populateThresholdsUI(t) {
  if (!t) return;

  const ftpInput = document.getElementById('input-ftp');
  if (ftpInput && t.ftp) ftpInput.value = t.ftp;

  const runInput = document.getElementById('input-run-thresh');
  if (runInput && t.run_threshold_pace) runInput.value = t.run_threshold_pace;

  const cssInput = document.getElementById('input-css');
  if (cssInput && t.css_pace) cssInput.value = t.css_pace;

  const lthrInput = document.getElementById('input-lthr');
  if (lthrInput && t.lthr) lthrInput.value = t.lthr;

  const maxHrInput = document.getElementById('input-max-hr');
  if (maxHrInput && t.max_hr) maxHrInput.value = t.max_hr;

  const restHrInput = document.getElementById('input-rest-hr');
  if (restHrInput && t.rest_hr) restHrInput.value = t.rest_hr;

  // Detail breakdown container
  const detailContainer = document.getElementById('thresholds-disciplines-detail');
  if (detailContainer) {
    let syncInfo = '';
    if (t.last_sync) {
      syncInfo = `<div class="text-[10px] text-emerald-400 font-mono flex items-center justify-between mb-2">
        <span>Última sincronización: ${t.last_sync}</span>
        ${t.weight ? `<span class="text-slate-400">Peso: <strong class="text-slate-200">${t.weight} kg</strong></span>` : ''}
      </div>`;
    }

    let pzHtml = '';
    const bike = t.disciplines?.cycling;
    if (bike?.power_zones?.length) {
      const zPills = bike.power_zones.map(z => 
        `<div class="flex items-center justify-between py-0.5 px-1 rounded bg-slate-950/70 border border-slate-800/80 font-mono text-[10px]">
          <span class="text-slate-400">${z.name}</span>
          <span class="text-sky-300 font-bold">${z.min_watts}-${z.max_watts > 800 ? '+' : z.max_watts}W</span>
        </div>`
      ).join('');
      pzHtml = `
        <div class="mt-2">
          <span class="text-[10px] font-semibold text-slate-300 uppercase tracking-wider block mb-1">Zonas de Potencia Ciclismo (Intervals)</span>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-1">${zPills}</div>
        </div>
      `;
    }

    let hrHtml = '';
    const run = t.disciplines?.running;
    if (run?.hr_zones?.length) {
      const zList = run.hr_zones.map((val, idx) => `Z${idx+1}: <${val}bpm`).join(' • ');
      hrHtml = `
        <div class="mt-2 text-[10px] font-mono text-slate-400">
          <span class="text-slate-300 font-semibold uppercase">Zonas FC Carrera:</span> ${zList}
        </div>
      `;
    }

    detailContainer.innerHTML = syncInfo + pzHtml + hrHtml;
  }
}

async function syncThresholds(silent = false) {
  const btn = document.getElementById('btn-sync-thresholds');
  const badge = document.getElementById('thresholds-sync-badge');
  if (!silent && btn) {
    btn.disabled = true;
    btn.innerHTML = `<svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Sincronizando...</span>`;
  }

  try {
    const res = await fetch('/api/thresholds/sync', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'success' && data.thresholds) {
      populateThresholdsUI(data.thresholds);
      if (state.athleteStatus) {
        state.athleteStatus.thresholds = data.thresholds;
      }
      if (badge) {
        badge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1';
        badge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> <span>Sincronizado</span>`;
      }
    }
  } catch (err) {
    console.warn('Error syncing thresholds:', err);
  } finally {
    if (!silent && btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg> <span>Sincronizar</span>`;
    }
  }
}

function closeSettingsModal() {
  const modal = document.getElementById('settings-modal');
  if (modal) modal.classList.add('hidden');
}

async function saveSettings() {
  const emailVal = document.getElementById('input-garmin-email')?.value.trim();
  const passVal = document.getElementById('input-garmin-password')?.value;
  const intIdVal = document.getElementById('input-intervals-id')?.value.trim();
  const intKeyVal = document.getElementById('input-intervals-key')?.value.trim();
  const geminiVal = document.getElementById('input-gemini-key')?.value.trim();

  // Thresholds
  const ftpVal = parseInt(document.getElementById('input-ftp')?.value, 10);
  const runThreshVal = document.getElementById('input-run-thresh')?.value.trim();
  const cssVal = document.getElementById('input-css')?.value.trim();
  const lthrVal = parseInt(document.getElementById('input-lthr')?.value, 10);
  const maxHrVal = parseInt(document.getElementById('input-max-hr')?.value, 10);
  const restHrVal = parseInt(document.getElementById('input-rest-hr')?.value, 10);

  const payload = {};
  if (emailVal && emailVal !== '••••••••') payload.garmin_email = emailVal;
  if (passVal && passVal !== '••••••••') payload.garmin_password = passVal;
  if (intIdVal) payload.intervals_athlete_id = intIdVal;
  if (intKeyVal && intKeyVal !== '••••••••') payload.intervals_api_key = intKeyVal;
  if (geminiVal && geminiVal !== '••••••••') payload.gemini_api_key = geminiVal;

  if (!isNaN(ftpVal)) payload.ftp = ftpVal;
  if (runThreshVal) payload.run_threshold_pace = runThreshVal;
  if (cssVal) payload.css_pace = cssVal;
  if (!isNaN(lthrVal)) payload.lthr = lthrVal;
  if (!isNaN(maxHrVal)) payload.max_hr = maxHrVal;
  if (!isNaN(restHrVal)) payload.rest_hr_baseline = restHrVal;

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    alert('Ajustes guardados con éxito.');
    closeSettingsModal();
    await loadStatus();
    await loadWeek(state.weekOffset);
  } catch (err) {
    alert('Error al guardar ajustes.');
  }
}

async function testGarmin() {
  const statusEl = document.getElementById('garmin-test-result');
  const email = document.getElementById('input-garmin-email')?.value.trim();
  const password = document.getElementById('input-garmin-password')?.value;

  if (statusEl) statusEl.textContent = 'Verificando sesión...';
  try {
    const bodyPayload = (email && password) ? { email, password } : {};
    const res = await fetch('/api/garmin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyPayload)
    });
    const data = await res.json();
    if (data.status === 'success') {
      if (statusEl) statusEl.innerHTML = `<span class="text-emerald-400 font-bold">✓ Conectado como ${data.athlete_name}</span>`;
      await loadStatus();
      await loadWeek(state.weekOffset);
    } else {
      if (statusEl) statusEl.innerHTML = `<span class="text-rose-400 font-semibold">✗ ${data.message}</span>`;
    }
  } catch (err) {
    if (statusEl) statusEl.innerHTML = `<span class="text-rose-400 font-semibold">✗ Error de conexión</span>`;
  }
}

async function testIntervals() {
  const statusEl = document.getElementById('intervals-test-result');
  const athleteId = document.getElementById('input-intervals-id')?.value.trim() || '0';
  const apiKey = document.getElementById('input-intervals-key')?.value.trim();

  if (!apiKey) {
    if (statusEl) statusEl.innerHTML = '<span class="text-amber-400 font-semibold">Introduce tu API Key de Intervals.icu</span>';
    return;
  }

  if (statusEl) statusEl.textContent = 'Verificando con Intervals.icu...';
  try {
    const res = await fetch('/api/intervals/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ athlete_id: athleteId, api_key: apiKey })
    });
    const data = await res.json();
    if (data.status === 'success') {
      if (statusEl) statusEl.innerHTML = `<span class="text-emerald-400 font-bold">✓ Conectado: ${data.athlete_name} (FTP: ${data.ftp}W, Umbral: ${data.run_threshold_pace}/km)</span>`;
      if (data.thresholds) populateThresholdsUI(data.thresholds);
      await loadStatus();
      await loadWeek(state.weekOffset);
    } else {
      if (statusEl) statusEl.innerHTML = `<span class="text-rose-400 font-semibold">✗ ${data.message}</span>`;
    }
  } catch (err) {
    if (statusEl) statusEl.innerHTML = `<span class="text-rose-400 font-semibold">✗ Error de conexión</span>`;
  }
}

async function syncAllData() {
  const btn = document.getElementById('btn-sync');
  if (btn) btn.classList.add('animate-spin');
  await loadStatus();
  await loadWeek(state.weekOffset);
  if (state.currentTab === 'form') {
    await loadPMC(state.pmcDays);
  }
  if (btn) btn.classList.remove('animate-spin');
}

// Helpers
function getSportIcon(type) {
  const t = (type || '').toLowerCase();
  if (t === 'swimming') return '🏊';
  if (t === 'cycling') return '🚴';
  if (t === 'running') return '🏃';
  if (t === 'strength') return '🏋️';
  if (t === 'other') return '📋';
  return '⚡';
}

function formatCoachReport(text) {
  if (!text) return '';
  // Basic markdown conversion for bold and lists
  let formatted = text
    .replace(/^### (.*$)/gim, '<h4 class="font-bold text-slate-100 text-xs mt-3 mb-1">$1</h4>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');
  return formatted;
}
