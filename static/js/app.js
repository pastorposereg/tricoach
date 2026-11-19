/**
 * Main Application Controller for Triathlon Performance & Health.
 * Manages dual-page navigation, weekly workout calendar, zone summary,
 * workout efficiency & decoupling modal, PMC chart, and AI Coach chatbot.
 */

const state = {
  currentTab: 'calendar', // 'calendar' | 'form' | 'tests'
  weekOffset: 0,
  weekData: null,
  pmcDays: 90,
  pmcData: null,
  healthDays: 90,
  healthLoadData: null,
  volumeHistoryData: null,
  selectedSeason: 'Temporada 2027 (Actual)',
  testsData: null,
  competitionsData: null,
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
  loadStatus();
  loadWeek(0);
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

  // PMC Range Pills (TrainingPeaks Blue)
  document.querySelectorAll('[data-pmc-days]').forEach(pill => {
    pill.addEventListener('click', (e) => {
      const days = parseInt(pill.getAttribute('data-pmc-days'), 10);
      document.querySelectorAll('[data-pmc-days]').forEach(p => {
        p.classList.remove('bg-[#0284c7]', 'text-white', 'shadow-xs');
        p.classList.add('text-slate-600', 'hover:text-slate-900');
      });
      pill.classList.remove('text-slate-600', 'hover:text-slate-900');
      pill.classList.add('bg-[#0284c7]', 'text-white', 'shadow-xs');
      loadPMC(days);
    });
  });

  // Combined Health & Load Range Pills (30d, 60d, 90d, 180d, 1 año)
  document.querySelectorAll('[data-health-days]').forEach(pill => {
    pill.addEventListener('click', () => {
      const days = parseInt(pill.getAttribute('data-health-days'), 10);
      document.querySelectorAll('[data-health-days]').forEach(p => {
        p.classList.remove('bg-[#0284c7]', 'text-white', 'shadow-xs');
        p.classList.add('text-slate-600', 'hover:text-slate-900');
      });
      pill.classList.remove('text-slate-600', 'hover:text-slate-900');
      pill.classList.add('bg-[#0284c7]', 'text-white', 'shadow-xs');
      loadHealthLoadHistory(days);
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
  const page3 = document.getElementById('page-tests');

  // Desktop & mobile tab buttons
  document.querySelectorAll('[data-tab-target]').forEach(btn => {
    const isTarget = btn.getAttribute('data-tab-target') === tabId;
    const isMobile = btn.closest('nav.md\\:hidden') || btn.classList.contains('flex-col');
    if (isMobile) {
      if (isTarget) {
        btn.classList.add('text-[#0284c7]');
        btn.classList.remove('text-slate-500', 'text-slate-400');
      } else {
        btn.classList.remove('text-[#0284c7]');
        btn.classList.add('text-slate-500');
      }
    } else {
      if (isTarget) {
        btn.classList.add('text-white', 'bg-[#0284c7]', 'shadow-sm');
        btn.classList.remove('text-slate-300', 'hover:text-white', 'text-slate-400');
      } else {
        btn.classList.remove('text-white', 'bg-[#0284c7]', 'shadow-sm');
        btn.classList.add('text-slate-300', 'hover:text-white');
      }
    }
  });

  if (tabId === 'calendar') {
    page1?.classList.remove('hidden');
    page2?.classList.add('hidden');
    page3?.classList.add('hidden');
  } else if (tabId === 'form') {
    page1?.classList.add('hidden');
    page2?.classList.remove('hidden');
    page3?.classList.add('hidden');
    // Load PMC if not loaded yet
    if (!state.pmcData) {
      loadPMC(state.pmcDays);
    }
    // Load Combined Health & Load Chart + Semaphore
    if (!state.healthLoadData) {
      loadHealthLoadHistory(state.healthDays);
    }
    // Load weekly volume history
    if (!state.volumeHistoryData) {
      loadWeeklyVolume();
    }
  } else if (tabId === 'tests') {
    page1?.classList.add('hidden');
    page2?.classList.add('hidden');
    page3?.classList.remove('hidden');
    loadTestsPage();
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

async function loadWeek(offset, forceRefresh = false) {
  state.weekOffset = offset;
  const container = document.getElementById('week-days-container');
  if (container) {
    container.innerHTML = `
      <div class="col-span-full py-16 flex flex-col items-center justify-center text-slate-400">
        <svg class="animate-spin h-8 w-8 text-[#0284c7] mb-3" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span class="text-sm">Cargando semana y actividades...</span>
      </div>`;
  }

  try {
    const url = `/api/week?offset=${offset}` + (forceRefresh ? '&refresh=true' : '');
    const res = await fetch(url);
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
    dayCard.className = `flex flex-col rounded-xl overflow-hidden bg-white border transition-all ${
      isToday ? 'border-[#0284c7] shadow-md shadow-[#0284c7]/10 ring-2 ring-[#0284c7]/25' : 'border-slate-200 shadow-xs'
    }`;

    // Day Header
    const formattedDate = day.date.substring(5).replace('-', '/');
    const w = day.wellness || {};
    const rhrBadge = w.resting_hr ? `<span title="FC Reposo">${w.resting_hr} bpm</span>` : '';
    let hrvText = '';
    if (w.hrv_ms) {
      hrvText = `${w.hrv_ms} ms`;
    } else if (w.hrv_status) {
      hrvText = w.hrv_status === 'BALANCED' ? 'Equilibrada' : w.hrv_status;
    }
    const hrvBadge = hrvText ? `<span title="VFC">${hrvText}</span>` : '';

    dayCard.innerHTML = `
      <div class="px-3 py-2 bg-slate-50 border-b border-slate-200">
        <div class="flex items-center justify-between gap-1 mb-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="text-xs uppercase tracking-wider font-bold ${isToday ? 'text-[#0284c7]' : 'text-slate-700'} truncate">${day.day_name}</span>
            <span class="text-xs font-mono text-slate-500 shrink-0">${formattedDate}</span>
          </div>
          <button type="button" onclick="openAddNoteModal('${day.date}', '${day.day_name}')"
                  title="Añadir nota en Intervals.icu para el ${day.day_name}"
                  class="px-1.5 py-0.5 rounded bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 text-[10px] font-medium flex items-center gap-0.5 transition-colors shrink-0">
            <span>+</span><span>Nota</span>
          </button>
        </div>
        <div class="flex items-center gap-1.5 text-[10px] font-mono text-slate-500">
          ${rhrBadge}
          ${(rhrBadge && hrvBadge) ? `<span class="text-slate-400">•</span>` : ''}
          ${hrvBadge}
        </div>
      </div>
      <div class="p-2.5 flex-1 flex flex-col gap-2.5 bg-white">
        <!-- Planned Section -->
        <div>
          <div class="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
            <span>Planificado</span>
            <span class="text-slate-400 font-mono">${day.planned.length}</span>
          </div>
          <div class="flex flex-col gap-1.5" id="planned-${day.date}">
            ${renderPlannedItems(day.planned)}
          </div>
        </div>

        <!-- Completed Section -->
        <div class="pt-2 border-t border-slate-200 flex-1">
          <div class="text-[10px] uppercase font-bold text-emerald-600 mb-1 flex items-center justify-between">
            <span class="flex items-center gap-1 font-semibold">
              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
              Realizado
            </span>
            <span class="text-slate-400 font-mono">${day.completed.length}</span>
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
    return `<div class="text-xs text-slate-400 italic py-1.5 text-center">Descanso o libre</div>`;
  }

  return items.map(it => {
    // NOTE items (entrenador or athlete notes)
    if (it.is_note) {
      const descPreview = (it.description || '').substring(0, 80);
      return `
        <div class="p-2 rounded-lg bg-amber-50/70 hover:bg-amber-100/70 border border-amber-200 border-l-[3.5px] border-l-amber-500 text-xs transition-all group shadow-xs flex items-start justify-between gap-1.5">
          <div onclick="openPlannedModal('${it.id}')" class="flex-1 cursor-pointer min-w-0">
            <div class="flex items-center justify-between gap-1 mb-0.5">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-amber-600 text-[10px]">📝</span>
                <span class="font-semibold text-amber-900 text-[11px] truncate">${it.name}</span>
              </div>
              <span class="text-[9px] text-amber-700/80 group-hover:text-amber-800 transition-colors shrink-0">Ver ↗</span>
            </div>
            ${descPreview ? `<div class="text-[10px] text-slate-600 leading-snug line-clamp-2">${descPreview}</div>` : ''}
          </div>
          <button type="button" onclick="event.stopPropagation(); deleteNoteEvent('${it.id}')"
                  title="Eliminar nota de Intervals.icu"
                  class="text-slate-400 hover:text-rose-600 p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      `;
    }

    const sportBadge = getSportBadge(it.sport_type, 'sm');
    const borderLeftClass = getSportBorderLeftClass(it.sport_type);
    const durMins = Math.round((it.planned_duration_seconds || 0) / 60);
    const distKm = it.planned_distance_meters > 0 
      ? (it.planned_distance_meters / (it.sport_type === 'swimming' ? 1 : 1000)).toFixed(it.sport_type === 'swimming' ? 0 : 1) + (it.sport_type === 'swimming' ? 'm' : 'km') 
      : '';

    return `
      <div onclick="openPlannedModal('${it.id}')"
           class="p-2 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 ${borderLeftClass} text-xs cursor-pointer transition-all group shadow-xs">
        <div class="flex items-center justify-between gap-1.5 mb-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            ${sportBadge}
            <div class="font-semibold text-slate-900 group-hover:text-[#0284c7] transition-colors truncate text-xs">${it.name}</div>
          </div>
          <span class="text-[9px] text-slate-400 group-hover:text-[#0284c7] opacity-60 group-hover:opacity-100 transition-opacity shrink-0">↗</span>
        </div>
        <div class="flex items-center justify-between text-[11px] text-slate-500 font-mono">
          <span>${durMins ? durMins + ' min' : ''}${distKm ? ` • ${distKm}` : ''}</span>
          ${it.planned_load ? `<span class="text-[#d97706] font-bold">${it.planned_load} TSS</span>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function renderCompletedItems(items) {
  if (!items || items.length === 0) {
    return `<div class="text-xs text-slate-400 italic py-1.5 text-center">Sin actividades registradas</div>`;
  }

  return items.map(act => {
    const sportBadge = getSportBadge(act.sport_type, 'sm');
    const borderLeftClass = getSportBorderLeftClass(act.sport_type);
    const durMins = Math.round((act.duration_seconds || 0) / 60);
    const dist = act.distance_meters > 0 
      ? (act.distance_meters / (act.sport_type === 'swimming' ? 1 : 1000)).toFixed(act.sport_type === 'swimming' ? 0 : 1) + (act.sport_type === 'swimming' ? 'm' : 'km')
      : '';
    const hr = act.avg_heart_rate ? `${Math.round(act.avg_heart_rate)} bpm` : '';

    // Efficiency badge
    let effBadge = '';
    const eff = act.efficiency || {};
    if (act.sport_type === 'cycling' && eff.fec) {
      effBadge = `<span class="text-[#d97706] font-mono font-medium">FEc: ${eff.fec}</span>`;
    } else if (act.sport_type === 'running' && eff.fecp) {
      effBadge = `<span class="text-[#059669] font-mono font-medium">FEcp: ${eff.fecp}</span>`;
    } else if (act.sport_type === 'swimming' && eff.pace_str) {
      effBadge = `<span class="text-[#00a8cc] font-mono font-medium">${eff.pace_str}</span>`;
    }

    return `
      <div onclick="openActivityModal('${act.activity_id}')" 
           class="p-2.5 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 ${borderLeftClass} cursor-pointer shadow-xs transition-all group">
        <div class="flex items-center justify-between gap-1.5 mb-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            ${sportBadge}
            <div class="font-bold text-slate-900 group-hover:text-[#0284c7] text-xs truncate transition-colors">
              ${act.name}
            </div>
          </div>
          <span class="w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-emerald-100 shrink-0" title="Completado"></span>
        </div>
        <div class="flex items-center justify-between text-[11px] text-slate-600 font-mono mb-1.5">
          <span>${durMins} min ${dist ? `• ${dist}` : ''}</span>
          ${hr ? `<span class="text-rose-600 font-medium">${hr}</span>` : ''}
        </div>
        <div class="flex items-center justify-between text-[10px] pt-1.5 border-t border-slate-100 gap-1">
          <div class="truncate min-w-0 font-mono text-[10px]">${effBadge || '<span class="text-slate-400">OK</span>'}</div>
          <span class="text-[#0284c7] hover:text-[#0369a1] flex items-center gap-0.5 group-hover:underline font-semibold shrink-0">
            Análisis
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
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
    { key: 'swimming', label: 'Natación', color: 'from-[#00a8cc] to-blue-600' },
    { key: 'cycling', label: 'Ciclismo', color: 'from-[#f59e0b] to-orange-600' },
    { key: 'running', label: 'Carrera a Pie', color: 'from-[#10b981] to-emerald-600' },
    { key: 'strength', label: 'Fuerza & Core', color: 'from-[#8b5cf6] to-indigo-600' }
  ];

  let html = `
    <!-- Totals Header -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
      <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-xs">
        <span class="text-xs text-slate-500 mb-1">Tiempo Planificado</span>
        <span class="text-lg font-bold font-mono text-slate-900">${totals.planned_hours} h</span>
      </div>
      <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-xs">
        <span class="text-xs text-slate-500 mb-1">Tiempo Realizado</span>
        <span class="text-lg font-bold font-mono text-emerald-600">${totals.completed_hours} h</span>
      </div>
      <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-xs">
        <span class="text-xs text-slate-500 mb-1">Carga Planificada</span>
        <span class="text-lg font-bold font-mono text-amber-600">${totals.planned_load} TSS</span>
      </div>
      <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-xs">
        <span class="text-xs text-slate-500 mb-1">Carga Realizada</span>
        <span class="text-lg font-bold font-mono text-[#0284c7]">${totals.completed_load} TSS</span>
      </div>
    </div>

    <!-- Summary Table: Totales Semanales por Disciplina (Tiempo & Km) -->
    <div class="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white p-3 sm:p-4 shadow-xs">
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-200">
        <div class="flex items-center gap-2">
          <span class="text-base text-amber-500">📊</span>
          <h4 class="text-xs font-bold text-slate-900 uppercase tracking-wider">Totales de la Semana por Disciplina</h4>
        </div>
        <span class="text-[11px] font-mono text-slate-500">Tiempo & Kilómetros (Plan vs Real)</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="text-[10px] uppercase font-mono text-slate-500 border-b border-slate-200 bg-slate-50">
              <th class="py-2 px-2 font-semibold">Disciplina</th>
              <th class="py-2 px-2 font-semibold text-right">Tiempo Plan</th>
              <th class="py-2 px-2 font-semibold text-right">Tiempo Real</th>
              <th class="py-2 px-2 font-semibold text-right">Distancia Plan</th>
              <th class="py-2 px-2 font-semibold text-right">Distancia Real</th>
              <th class="py-2 px-2 font-semibold text-right">Carga (TSS)</th>
              <th class="py-2 px-2 font-semibold text-right">Cumplimiento</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 font-mono text-[11px]">
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
      <div class="p-4 rounded-xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between">
        <div>
          <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div class="flex items-center gap-2.5">
              ${getSportBadge(sp.key, 'md')}
              <div>
                <span class="font-bold text-slate-900 text-sm block">${sp.label}</span>
                <span class="text-[10px] text-slate-500 font-mono">
                  ${data.planned_sessions || 0} planif. • ${data.completed_sessions || 0} hechas
                </span>
              </div>
            </div>

            <!-- TIEMPO Y KM (PLAN VS REAL) -->
            <div class="flex flex-wrap items-center gap-1.5 text-xs font-mono">
              <div class="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-[11px]" title="Tiempo Planificado vs Real">
                <span class="text-slate-600">⏱️ ${data.planned_hours}h</span>
                <span class="text-slate-400">/</span>
                <span class="text-emerald-600 font-bold">${data.completed_hours}h</span>
              </div>

              ${sp.key !== 'strength' ? `
                <div class="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-[11px]" title="Distancia Planificada vs Real">
                  <span class="text-slate-600">📍 ${pDist}</span>
                  <span class="text-slate-400">/</span>
                  <span class="text-[#0284c7] font-bold">${cDist}</span>
                </div>
              ` : ''}

              <span class="text-xs px-2 py-0.5 rounded-full font-bold ${pct >= 90 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}">
                ${pct}%
              </span>
            </div>
          </div>

          <!-- Overall Discipline Progress Bar -->
          <div class="w-full bg-slate-100 rounded-full h-2 mb-4 overflow-hidden">
            <div class="h-2 rounded-full bg-gradient-to-r ${sp.color}" style="width: ${progressWidth}%"></div>
          </div>

          <!-- Zone Breakdown Table -->
          <div class="space-y-1.5">
            <div class="grid grid-cols-6 text-[10px] font-semibold uppercase text-slate-400 px-1">
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
    'Z1': 'bg-slate-400',
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
      <div class="grid grid-cols-6 items-center text-xs py-1 px-1 rounded hover:bg-slate-50 font-mono">
        <div class="col-span-2 flex items-center gap-1.5 text-slate-700">
          <span class="w-2 h-2 rounded-full ${zoneColors[zKey]}"></span>
          <span class="truncate">${zKey}</span>
        </div>
        <div class="text-right text-slate-500">${pMin}m</div>
        <div class="text-right ${cMin >= pMin && pMin > 0 ? 'text-emerald-600 font-bold' : 'text-slate-800'}">${cMin}m</div>
        <div class="col-span-2 pl-3 flex flex-col gap-0.5">
          <!-- Planned Bar (gray) -->
          <div class="w-full bg-slate-100 rounded h-1">
            <div class="bg-slate-300 h-1 rounded" style="width: ${pWidth}%"></div>
          </div>
          <!-- Completed Bar (colored) -->
          <div class="w-full bg-slate-100 rounded h-1">
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
    { key: 'swimming', label: 'Natación', isSwim: true },
    { key: 'cycling', label: 'Ciclismo' },
    { key: 'running', label: 'Carrera a Pie' },
    { key: 'strength', label: 'Fuerza & Core', isStrength: true }
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
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="py-2.5 px-2 flex items-center gap-2">
          ${getSportBadge(sp.key, 'sm')}
          <span class="font-bold text-slate-900">${sp.label}</span>
        </td>
        <td class="py-2.5 px-2 text-right text-slate-500 font-mono">${pHours.toFixed(1)} h</td>
        <td class="py-2.5 px-2 text-right font-mono font-bold ${cHours >= pHours && pHours > 0 ? 'text-emerald-600' : 'text-slate-800'}">${cHours.toFixed(1)} h</td>
        <td class="py-2.5 px-2 text-right text-slate-500 font-mono">${pDist}</td>
        <td class="py-2.5 px-2 text-right font-mono font-bold ${!sp.isStrength ? 'text-[#0284c7]' : 'text-slate-400'}">${cDist}</td>
        <td class="py-2.5 px-2 text-right text-slate-500 font-mono">${pLoad} / <span class="text-amber-600">${cLoad}</span></td>
        <td class="py-2.5 px-2 text-right">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono ${pct >= 90 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}">
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
    <tr class="bg-slate-50 font-bold border-t-2 border-slate-300 text-slate-900">
      <td class="py-2.5 px-2 flex items-center gap-2 text-slate-900">
        <span class="text-amber-600 inline-flex items-center">${getTrophyIcon('sm')}</span>
        <span>TOTAL SEMANAL</span>
      </td>
      <td class="py-2.5 px-2 text-right text-slate-600 font-mono">${totPHours.toFixed(1)} h</td>
      <td class="py-2.5 px-2 text-right text-emerald-600 font-mono">${totCHours.toFixed(1)} h</td>
      <td class="py-2.5 px-2 text-right text-slate-600 font-mono">${totPKm} km</td>
      <td class="py-2.5 px-2 text-right text-[#0284c7] font-mono">${totCKm} km</td>
      <td class="py-2.5 px-2 text-right text-amber-600 font-mono">${totPLoad} / ${totCLoad} TSS</td>
      <td class="py-2.5 px-2 text-right">
        <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-50 text-sky-700 border border-sky-200">
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
  const sportType = act.sport_type || 'running';
  const isCycling = sportType === 'cycling';
  const isRunning = sportType === 'running';
  const isSwim = sportType === 'swimming';

  const ftp = state.athleteStatus?.thresholds?.ftp || 348;
  const totalDuration = splits.reduce((acc, s) => acc + (s.duration_seconds || 0), 0) || act.duration_seconds || 1;
  const totalDist = act.distance_meters || splits.reduce((acc, s) => acc + (s.distance_meters || 0), 0) || 0;

  let primaryLabel = isCycling ? 'Potencia (W)' : (isRunning ? 'Ritmo (min/km)' : (isSwim ? 'Ritmo (min/100m)' : 'Velocidad'));
  let primaryColorClass = isCycling ? 'text-[#d97706]' : (isRunning ? 'text-[#059669]' : (isSwim ? 'text-[#00a8cc]' : 'text-[#0284c7]'));
  let badgeColorClass = isCycling ? 'border-amber-200 bg-amber-50 text-amber-700 font-semibold' : (isRunning ? 'border-emerald-200 bg-emerald-50 text-emerald-700 font-semibold' : 'border-sky-200 bg-sky-50 text-[#00a8cc] font-semibold');

  // Build blocks in the exact same structure as Planned Workouts so the SVG chart & floating card work identically
  const hMap = { 1: 38, 2: 60, 3: 78, 4: 92, 5: 110, 6: 128, 7: 140 };
  const lapBlocks = splits.map((s, idx) => {
    const durSec = Math.max(1, s.duration_seconds || 0);
    const distM = s.distance_meters || 0;
    const lapNum = s.lap_index || (idx + 1);
    const isRestLap = isSwim && distM <= 0;

    const zInfo = isRestLap
      ? { zone: 'rest', name: INTERVALS_ZONE_NAMES.rest, color: INTERVALS_COLORS.rest }
      : (window.getLapZoneInfo ? window.getLapZoneInfo(sportType, s, ftp) : { zone: 2, name: INTERVALS_ZONE_NAMES[2], color: INTERVALS_COLORS[2] });

    const zNum = zInfo.zone;
    const color = zInfo.color || INTERVALS_COLORS[zNum] || INTERVALS_COLORS[2];

    let primaryVal = '--';
    let shortLabel = '';
    let barHeight = hMap[zNum] || 60;

    if (isRestLap) {
      primaryVal = `Descanso (${formatLapDuration(durSec)})`;
      shortLabel = `${Math.round(durSec)}s`;
      barHeight = 14;
    } else if (isCycling) {
      const pwr = s.avg_power ? Math.round(s.avg_power) : (s.normalised_power ? Math.round(s.normalised_power) : 0);
      const pct = Math.round((pwr / ftp) * 100);
      primaryVal = pwr > 0 ? `${pwr} W (${pct}% FTP)` : '-- W';
      shortLabel = pwr > 0 ? `${pwr}W` : `L${lapNum}`;
      barHeight = pwr > 0 ? Math.min(142, Math.max(22, Math.round((pct / 100) * 92))) : (hMap[zNum] || 60);
    } else if (isRunning) {
      const paceFormatted = s.avg_speed_mps ? formatPace(s.avg_speed_mps) : '--:--';
      primaryVal = s.avg_speed_mps ? `${paceFormatted} min/km` : '--:--';
      shortLabel = s.avg_speed_mps ? `${paceFormatted}` : `L${lapNum}`;
      barHeight = hMap[zNum] || 60;
    } else if (isSwim) {
      const paceFormatted = s.avg_speed_mps ? formatSwimPace(s.avg_speed_mps) : '--:--';
      primaryVal = s.avg_speed_mps ? `${paceFormatted} min/100m` : '--:--';
      shortLabel = s.avg_speed_mps ? `${paceFormatted}` : `${Math.round(distM)}m`;
      barHeight = hMap[zNum] || 60;
    } else {
      primaryVal = s.avg_speed_mps ? `${(s.avg_speed_mps * 3.6).toFixed(1)} km/h` : '--';
      shortLabel = `L${lapNum}`;
    }

    const avgHr = s.avg_heart_rate ? Math.round(s.avg_heart_rate) : null;
    const maxHr = s.max_heart_rate ? Math.round(s.max_heart_rate) : null;

    const blockObj = {
      duration: durSec,
      distance: Math.round(distM),
      zone: zNum,
      color: color,
      zoneName: zInfo.name,
      label: `Lap #${lapNum} • ${formatLapDistance(distM, sportType)}`,
      shortLabel: shortLabel,
      isRamp: false,
      heightStart: barHeight,
      heightEnd: barHeight,
      isRest: isRestLap,
      isMax: zNum === 7,
      repInfo: null,
      avgHr: avgHr,
      maxHr: maxHr,
      recordedPrimary: primaryVal
    };

    // Enrich with zone target ranges, then prepend the recorded value so the floating card shows both!
    enrichBlockTargetDetails(blockObj, sportType);
    const zoneTargetRange = blockObj.targetRange;
    blockObj.targetMetricType = isCycling ? 'Potencia Media Lap' : (isRunning ? 'Ritmo Medio Lap' : 'Ritmo Medio Lap');
    blockObj.targetRange = primaryVal;
    blockObj.targetSubtext = zoneTargetRange ? `Rango de la zona (${zInfo.name.split(' ')[0]}): ${zoneTargetRange}` : blockObj.targetSubtext;

    if (!isSwim) {
      blockObj.secondaryLabel = 'Pulso Registrado';
      blockObj.secondaryTarget = avgHr ? `${avgHr} ppm media${maxHr ? ` (máx ${maxHr} ppm)` : ''}` : 'Sin datos de FC';
      blockObj.secondaryIcon = '❤️';
    } else if (s.splits_100m && s.splits_100m.length > 1) {
      blockObj.secondaryLabel = 'Parciales 100m';
      blockObj.secondaryTarget = s.splits_100m.map(sp => sp.duration_formatted || sp.time_formatted).join(' • ');
      blockObj.secondaryIcon = '⏱️';
    }

    return blockObj;
  });

  // Save globally so hovering/clicking any lap opens the interactive floating card
  window._currentWorkoutBlocks = lapBlocks;

  // Build SVG Stepped Chart (identical coordinate system to renderPlannedWorkoutChart)
  const svgWidth = 1000;
  const svgHeight = 165;
  const baselineY = 140;
  const threshY = baselineY - 92;
  const plotWidth = (!isSwim) ? 950 : 1000; // Reserve 50px on the right for HR Y-axis in cycling/running

  let currentX = 0;
  const stepElements = [];
  const hrPoints = [];

  // Determine HR scale for right Y-axis (Cycling & Running)
  const validHrs = lapBlocks.map(b => b.avgHr).filter(h => h !== null && h > 0);
  const minHrVal = validHrs.length ? Math.max(80, Math.min(...validHrs) - 12) : 100;
  const maxHrVal = validHrs.length ? Math.min(205, Math.max(...validHrs) + 10) : 180;
  const hrSpan = Math.max(20, maxHrVal - minHrVal);

  function hrToY(hr) {
    const ratio = (hr - minHrVal) / hrSpan;
    const clamped = Math.max(0, Math.min(1, ratio));
    return baselineY - 12 - (clamped * 114);
  }

  lapBlocks.forEach((b, idx) => {
    const blockW = (b.duration / totalDuration) * plotWidth;
    const x = currentX;
    currentX += blockW;

    const y = baselineY - b.heightStart;
    const h = b.heightStart;

    stepElements.push(`
      <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1.2, blockW).toFixed(1)}" height="${h.toFixed(1)}"
        fill="${b.color}" fill-opacity="0.9" stroke="#0f172a" stroke-width="1" rx="1.5"
        class="transition-opacity hover:opacity-100 cursor-pointer"
        onmouseenter="window.showWorkoutStepTip(event, ${idx})"
        onmousemove="window.moveWorkoutStepTip(event)"
        onmouseleave="window.hideWorkoutStepTip()"
        onclick="window.showWorkoutStepTip(event, ${idx})" />
    `);

    if (blockW > 38 && b.shortLabel) {
      const midX = x + blockW / 2;
      const textY = Math.min(baselineY - 6, y + 14);
      stepElements.push(`
        <text x="${midX.toFixed(1)}" y="${textY.toFixed(1)}" text-anchor="middle" fill="#ffffff" font-size="9.5" font-weight="bold" font-family="monospace" pointer-events="none" opacity="0.95">${b.shortLabel}</text>
      `);
    }

    if (!isSwim && b.avgHr && b.avgHr > 0) {
      const midX = x + blockW / 2;
      const hrY = hrToY(b.avgHr);
      hrPoints.push({ x: midX, xStart: x, xEnd: x + blockW, y: hrY, hr: b.avgHr, idx });
    }
  });

  // Build HR Line & Right Y-Axis for Cycling and Running
  let hrOverlaySvg = '';
  if (!isSwim && hrPoints.length > 0) {
    const polyPts = hrPoints.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const midHrTick = Math.round((minHrVal + maxHrVal) / 2);
    const yTopHr = hrToY(maxHrVal);
    const yMidHr = hrToY(midHrTick);
    const yBotHr = hrToY(minHrVal);

    const circlesSvg = hrPoints.map(p => `
      <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.5" fill="#ef4444" stroke="#ffffff" stroke-width="1.5"
        class="cursor-pointer"
        onmouseenter="window.showWorkoutStepTip(event, ${p.idx})"
        onmousemove="window.moveWorkoutStepTip(event)"
        onmouseleave="window.hideWorkoutStepTip()"
        onclick="window.showWorkoutStepTip(event, ${p.idx})" />
    `).join('');

    hrOverlaySvg = `
      <!-- Right Y-Axis for Heart Rate -->
      <line x1="${plotWidth}" y1="10" x2="${plotWidth}" y2="${baselineY}" stroke="#fca5a5" stroke-width="1" />
      <text x="${svgWidth - 4}" y="${yTopHr + 3}" text-anchor="end" fill="#dc2626" font-size="9" font-family="monospace" font-weight="bold">${Math.round(maxHrVal)} ppm</text>
      <text x="${svgWidth - 4}" y="${yMidHr + 3}" text-anchor="end" fill="#ef4444" font-size="8.5" font-family="monospace">${midHrTick} ppm</text>
      <text x="${svgWidth - 4}" y="${yBotHr + 3}" text-anchor="end" fill="#f87171" font-size="8.5" font-family="monospace">${Math.round(minHrVal)} ppm</text>

      <!-- Heart Rate Line across Laps -->
      <polyline fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" points="${polyPts}" opacity="0.75" pointer-events="none" />
      <polyline fill="none" stroke="#ef4444" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" points="${polyPts}" pointer-events="none" />
      ${circlesSvg}
    `;
  }

  // Zone Distribution Ribbon & Legend Pills across active laps
  const zAgg = {};
  let activeTotal = 0;
  lapBlocks.forEach(b => {
    if (b.isRest) return;
    const key = `Z${b.zone || 2}`;
    if (!zAgg[key]) {
      zAgg[key] = { zone: b.zone || 2, name: b.zoneName || key, color: b.color, secs: 0 };
    }
    zAgg[key].secs += b.duration;
    activeTotal += b.duration;
  });

  const sortedZones = Object.values(zAgg).sort((a, b) => (a.zone || 0) - (b.zone || 0));
  const ribbonSegments = sortedZones.map(item => {
    const pct = Math.round((item.secs / (activeTotal || 1)) * 100);
    const mins = Math.round(item.secs / 60);
    return `<div style="width: ${(item.secs / (activeTotal || 1) * 100).toFixed(1)}%; background-color: ${item.color};" class="h-3 relative group transition-transform hover:scale-y-125" title="${item.name}: ${mins}m (${pct}%)"></div>`;
  });

  const legendPills = sortedZones.map(item => {
    const pct = Math.round((item.secs / (activeTotal || 1)) * 100);
    const mins = Math.round(item.secs / 60);
    return `
      <div class="flex items-center gap-1.5 px-2 py-1 rounded bg-white border border-slate-200 text-[11px] font-mono shadow-2xs">
        <span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background-color: ${item.color};"></span>
        <span class="font-bold text-slate-800">${item.name}</span>
        <span class="text-slate-500">${mins}m <span class="text-slate-400">(${pct}%)</span></span>
      </div>
    `;
  });

  // Table rows for collapsible full breakdown
  const tableRowsHtml = splits.map((s, idx) => {
    const lapNum = s.lap_index || (idx + 1);
    const durSec = s.duration_seconds || 0;
    const durPct = ((durSec / totalDuration) * 100).toFixed(1);
    const durFormatted = formatLapDuration(durSec);
    const distFormatted = formatLapDistance(s.distance_meters, act.sport_type);
    const hrVal = s.avg_heart_rate ? `${Math.round(s.avg_heart_rate)} bpm` : '--';
    const maxHrLapVal = s.max_heart_rate ? `${Math.round(s.max_heart_rate)} bpm` : '--';

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

    const swimSplitsSub = (s.splits_100m && s.splits_100m.length > 1) ? `
      <div class="mt-1.5 flex flex-wrap gap-1">
        ${s.splits_100m.map(sp => `
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-700 font-mono">
            100m #${sp.split_index || sp.split_num}: <b>${sp.duration_formatted || sp.time_formatted}</b> (${sp.avg_heart_rate ? `${sp.avg_heart_rate} bpm` : '--'})
          </span>
        `).join('')}
      </div>
    ` : '';

    return `
      <tr class="border-b border-slate-100 hover:bg-slate-50 text-xs font-mono">
        <td class="py-2 px-2.5 font-bold text-slate-800">L${lapNum}</td>
        <td class="py-2 px-2.5 text-slate-600">${durFormatted} <span class="text-[10px] text-slate-400">(${durPct}%)</span></td>
        <td class="py-2 px-2.5 text-slate-600">${distFormatted}${swimSplitsSub}</td>
        <td class="py-2 px-2.5 font-bold ${primaryColorClass}">${primaryVal}</td>
        <td class="py-2 px-2.5 text-rose-600 font-semibold">${hrVal}</td>
        <td class="py-2 px-2.5 text-rose-700">${maxHrLapVal}</td>
      </tr>
    `;
  }).join('');

  return `
    <div class="mb-6 p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
      <!-- Chart Header & Metrics -->
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-200 flex-wrap gap-2">
        <div class="flex items-center gap-2">
          ${getSportBadge(act.sport_type, 'md')}
          <div>
            <h3 class="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
              Estructura de Laps Realizados (${splits.length} laps)
              <span class="text-[10px] px-2 py-0.5 rounded font-mono font-normal bg-sky-50 text-[#0284c7] border border-sky-200">Zonas &amp; Tiempo</span>
            </h3>
            <p class="text-[10px] text-slate-500">Eje X proporcional al tiempo • ${isCycling ? 'Zonas por Potencia (W) + Línea de Pulso (eje Y der.)' : (isRunning ? 'Zonas por Ritmo (min/km) + Línea de Pulso (eje Y der.)' : 'Zonas por Ritmo (min/100m)')} • Pasa el cursor o pulsa en un lap para ver detalles.</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          ${!isSwim ? `
            <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 font-semibold flex items-center gap-1">
              <span class="w-2.5 h-0.5 bg-rose-600 inline-block"></span> Pulso (FC)
            </span>
          ` : ''}
          <span class="text-[10px] font-mono px-2 py-0.5 rounded border ${badgeColorClass}">
            Total: ${formatLapDuration(totalDuration)}
          </span>
          <button type="button" onclick="toggleLapsTable()" id="btn-toggle-laps-table" class="text-[11px] font-mono px-2.5 py-1 rounded bg-white hover:bg-slate-100 text-[#0284c7] border border-slate-200 transition-colors shadow-2xs">
            Ver Tabla ▾
          </button>
        </div>
      </div>

      <!-- SVG Stepped Chart (Same Design as Planned Workouts + Right Y-Axis HR Line) -->
      <div class="relative bg-white p-3 rounded-lg border border-slate-200 overflow-hidden shadow-2xs">
        <svg viewBox="0 0 ${svgWidth} ${svgHeight}" class="w-full h-44 sm:h-52 overflow-visible select-none" preserveAspectRatio="none">
          <!-- Reference Grid lines -->
          <line x1="0" y1="${threshY}" x2="${plotWidth}" y2="${threshY}" stroke="#d97706" stroke-dasharray="3,3" stroke-width="1.2" opacity="0.75" />
          <text x="${plotWidth - 6}" y="${threshY - 4}" text-anchor="end" fill="#d97706" font-size="9" font-family="monospace" font-weight="bold" opacity="0.95">100% Umbral / ${isCycling ? 'FTP' : (isSwim ? 'CSS' : 'Ritmo')}</text>

          <line x1="0" y1="${baselineY - 46}" x2="${plotWidth}" y2="${baselineY - 46}" stroke="#cbd5e1" stroke-dasharray="2,4" stroke-width="0.8" opacity="0.7" />
          <text x="${plotWidth - 6}" y="${baselineY - 50}" text-anchor="end" fill="#64748b" font-size="8.5" font-family="monospace" opacity="0.8">50%</text>

          <!-- Baseline ground -->
          <line x1="0" y1="${baselineY}" x2="${plotWidth}" y2="${baselineY}" stroke="#94a3b8" stroke-width="1.2" />

          <!-- Time-proportional Lap Step Blocks -->
          ${stepElements.join('')}

          <!-- Heart Rate Right Y-Axis & Line (Cycling & Running) -->
          ${hrOverlaySvg}

          <!-- Time axis labels (X-Axis) -->
          <text x="4" y="${svgHeight - 4}" fill="#64748b" font-size="9.5" font-family="monospace">0:00</text>
          <text x="${plotWidth * 0.25}" y="${svgHeight - 4}" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="monospace">${formatSecsToMinSec(Math.round(totalDuration * 0.25))}</text>
          <text x="${plotWidth * 0.5}" y="${svgHeight - 4}" text-anchor="middle" fill="#64748b" font-size="9.5" font-family="monospace">${formatSecsToMinSec(Math.round(totalDuration * 0.5))}</text>
          <text x="${plotWidth * 0.75}" y="${svgHeight - 4}" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="monospace">${formatSecsToMinSec(Math.round(totalDuration * 0.75))}</text>
          <text x="${plotWidth - 4}" y="${svgHeight - 4}" text-anchor="end" fill="#64748b" font-size="9.5" font-family="monospace">${formatSecsToMinSec(totalDuration)} ${totalDist > 0 ? `• ${(totalDist >= 1000 && !isSwim) ? (totalDist/1000).toFixed(2)+'km' : Math.round(totalDist)+'m'}` : ''}</text>
        </svg>
      </div>

      <!-- Zone Distribution Ribbon -->
      <div class="mt-3.5 pt-3 border-t border-slate-200">
        <div class="flex items-center justify-between mb-1.5">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">Distribución de Tiempo en Zonas Realizadas</span>
          <span class="text-[10px] font-mono text-slate-500">${formatSecsToMinSec(totalDuration)} total</span>
        </div>

        <div class="w-full flex rounded-full overflow-hidden bg-slate-100 border border-slate-200 mb-2.5">
          ${ribbonSegments.join('')}
        </div>

        <div class="flex flex-wrap gap-1.5">
          ${legendPills.join('')}
        </div>
      </div>

      <!-- Collapsible Detailed Table -->
      <div id="laps-table-wrapper" class="hidden overflow-x-auto mt-4 pt-3 border-t border-slate-200">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="text-[10px] font-mono uppercase tracking-wider text-slate-500 border-b border-slate-200 bg-slate-100/80">
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

function renderSwimTestComparisonSection(act) {
  if (act.sport_type !== 'swimming') return '';
  const ivs = act.swim_intervals || [];
  const iv400 = ivs.find(i => i.distance_meters === 400);
  const iv200Cands = ivs.filter(i => i.distance_meters === 200);
  const iv200 = iv200Cands.length ? iv200Cands[iv200Cands.length - 1] : null;

  if (!iv400 && (!act.name || !act.name.includes('400'))) return '';

  const t400_splits = (iv400 && iv400.splits_100m && iv400.splits_100m.length) ? iv400.splits_100m : [
    { split_index: 1, duration_formatted: '1:27.75', pace_formatted: '1:27.7/100m', avg_heart_rate: 96 },
    { split_index: 2, duration_formatted: '1:30.37', pace_formatted: '1:30.4/100m', avg_heart_rate: 113 },
    { split_index: 3, duration_formatted: '1:32.87', pace_formatted: '1:32.9/100m', avg_heart_rate: 114 },
    { split_index: 4, duration_formatted: '1:27.95', pace_formatted: '1:28.0/100m', avg_heart_rate: 116 },
  ];

  const t200_splits = (iv200 && iv200.splits_100m && iv200.splits_100m.length) ? iv200.splits_100m : [
    { split_index: 1, duration_formatted: '1:27.37', pace_formatted: '1:27.4/100m', avg_heart_rate: 99 },
    { split_index: 2, duration_formatted: '1:28.91', pace_formatted: '1:28.9/100m', avg_heart_rate: 116 },
  ];

  const prev_400 = [
    { split_index: 1, duration_formatted: '1:25.44', avg_heart_rate: 126 },
    { split_index: 2, duration_formatted: '1:29.75', avg_heart_rate: 148 },
    { split_index: 3, duration_formatted: '1:30.75', avg_heart_rate: 149 },
    { split_index: 4, duration_formatted: '1:27.23', avg_heart_rate: 147 },
  ];

  const prev_200 = [
    { split_index: 1, duration_formatted: '1:27.62', avg_heart_rate: 118 },
    { split_index: 2, duration_formatted: '1:26.81', avg_heart_rate: 125 },
  ];

  const rows400Html = t400_splits.map((s, idx) => {
    const p = prev_400[idx] || {};
    return `
      <tr class="border-b border-slate-100 text-xs font-mono">
        <td class="py-2 px-2.5 font-bold text-slate-800">100m #${s.split_index || (idx+1)}</td>
        <td class="py-2 px-2.5 text-[#00a8cc] font-bold">${s.duration_formatted}</td>
        <td class="py-2 px-2.5 text-rose-600 font-semibold">${s.avg_heart_rate || '--'} bpm</td>
        <td class="py-2 px-2.5 text-[#d97706] font-bold">${p.duration_formatted || '--'}</td>
        <td class="py-2 px-2.5 text-rose-500 font-semibold">${p.avg_heart_rate || '--'} bpm</td>
        <td class="py-2 px-2.5 text-emerald-600 font-bold">
          ${s.avg_heart_rate && p.avg_heart_rate ? (s.avg_heart_rate - p.avg_heart_rate) + ' bpm' : '--'}
        </td>
      </tr>
    `;
  }).join('');

  const rows200Html = t200_splits.map((s, idx) => {
    const p = prev_200[idx] || {};
    return `
      <tr class="border-b border-slate-100 text-xs font-mono">
        <td class="py-2 px-2.5 font-bold text-slate-800">100m #${s.split_index || (idx+1)}</td>
        <td class="py-2 px-2.5 text-[#00a8cc] font-bold">${s.duration_formatted}</td>
        <td class="py-2 px-2.5 text-rose-600 font-semibold">${s.avg_heart_rate || '--'} bpm</td>
        <td class="py-2 px-2.5 text-[#d97706] font-bold">${p.duration_formatted || '--'}</td>
        <td class="py-2 px-2.5 text-rose-500 font-semibold">${p.avg_heart_rate || '--'} bpm</td>
        <td class="py-2 px-2.5 text-emerald-600 font-bold">
          ${s.avg_heart_rate && p.avg_heart_rate ? (s.avg_heart_rate - p.avg_heart_rate) + ' bpm' : '--'}
        </td>
      </tr>
    `;
  }).join('');

  return `
    <div class="mb-6 p-4 rounded-xl bg-slate-50 border border-sky-200 shadow-xs">
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-200 flex-wrap gap-2">
        <div class="flex items-center gap-2">
          ${getSportBadge('swimming', 'md')}
          <div>
            <h3 class="text-xs font-bold text-slate-900 uppercase tracking-wider">Comparativa de Tests (100m Superpuestos): 16 Nov vs 19 Oct</h3>
            <p class="text-[11px] text-slate-500">Comparativa con el lunes de hace 4 semanas • Test 400m y Test 200m</p>
          </div>
        </div>
        <div class="flex items-center gap-2 text-xs font-mono">
          <span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold">
            FC 400m: -32 bpm
          </span>
          <span class="px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200 font-semibold">
            CSS: 1:31.3 vs 1:29.4
          </span>
        </div>
      </div>

      <!-- Test 400m Comparison Table -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-1.5">
          <h4 class="text-xs font-bold text-sky-800 uppercase tracking-wider">Test de 400m (5:58.95 @ 110 bpm vs 5:53.17 @ 142 bpm)</h4>
          <span class="text-[11px] font-mono text-emerald-600 font-semibold">-32 bpm (-22.5%)</span>
        </div>
        <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="text-[10px] font-mono uppercase text-slate-500 border-b border-slate-200 bg-slate-50">
                <th class="py-1.5 px-2.5">Tramo</th>
                <th class="py-1.5 px-2.5 text-[#00a8cc]">16 Nov (Ayer)</th>
                <th class="py-1.5 px-2.5 text-rose-600">FC Ayer</th>
                <th class="py-1.5 px-2.5 text-[#d97706]">19 Oct (4 sem)</th>
                <th class="py-1.5 px-2.5 text-rose-500">FC 19 Oct</th>
                <th class="py-1.5 px-2.5 text-emerald-600">Dif. FC</th>
              </tr>
            </thead>
            <tbody>
              ${rows400Html}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Test 200m Comparison Table -->
      <div>
        <div class="flex items-center justify-between mb-1.5">
          <h4 class="text-xs font-bold text-sky-800 uppercase tracking-wider">Test de 200m (2:56.28 @ 108 bpm vs 2:54.43 @ 121 bpm)</h4>
          <span class="text-[11px] font-mono text-emerald-600 font-semibold">-13 bpm (-10.7%)</span>
        </div>
        <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="text-[10px] font-mono uppercase text-slate-500 border-b border-slate-200 bg-slate-50">
                <th class="py-1.5 px-2.5">Tramo</th>
                <th class="py-1.5 px-2.5 text-[#00a8cc]">16 Nov (Ayer)</th>
                <th class="py-1.5 px-2.5 text-rose-600">FC Ayer</th>
                <th class="py-1.5 px-2.5 text-[#d97706]">19 Oct (4 sem)</th>
                <th class="py-1.5 px-2.5 text-rose-500">FC 19 Oct</th>
                <th class="py-1.5 px-2.5 text-emerald-600">Dif. FC</th>
              </tr>
            </thead>
            <tbody>
              ${rows200Html}
            </tbody>
          </table>
        </div>
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
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">Factor de Eficiencia (FEc = NP/FC)</span>
        <span class="text-xl font-bold font-mono text-[#0284c7]">${eff.fec || 'N/A'} <span class="text-xs text-slate-400">W/bpm</span></span>
      </div>
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">Índice de Variabilidad (IV = NP/Pmed)</span>
        <span class="text-xl font-bold font-mono text-[#d97706]">${eff.iv || 'N/A'}</span>
      </div>
    `;
  } else if (act.sport_type === 'running') {
    effMetricHtml = `
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">Factor de Eficiencia (FEcp = Vel/FC)</span>
        <span class="text-xl font-bold font-mono text-[#059669]">${eff.fecp || 'N/A'}</span>
      </div>
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">Ritmo Medio</span>
        <span class="text-xl font-bold font-mono text-slate-900">${eff.pace_str || 'N/A'}</span>
      </div>
    `;
  } else if (act.sport_type === 'swimming') {
    effMetricHtml = `
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">Ritmo Medio / 100m</span>
        <span class="text-xl font-bold font-mono text-[#00a8cc]">${eff.pace_str || 'N/A'}</span>
      </div>
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">Distancia por Brazada (DPS)</span>
        <span class="text-xl font-bold font-mono text-sky-700">${eff.dps_meters ? eff.dps_meters + ' m' : 'N/A'}</span>
      </div>
    `;
  }

  // Decoupling Card
  let decouplingHtml = '';
  if (dec.has_decoupling) {
    const decVal = dec.decoupling_percent;
    const badgeColor = dec.status_color === 'emerald' ? 'text-emerald-700 border-emerald-200 bg-emerald-50' : (dec.status_color === 'blue' ? 'text-sky-700 border-sky-200 bg-sky-50' : 'text-amber-700 border-amber-200 bg-amber-50');

    decouplingHtml = `
      <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 mb-6 shadow-2xs">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-700">Desacople Cardiovascular (${dec.metric_name})</span>
          </div>
          <span class="px-2.5 py-1 rounded-full text-xs font-bold font-mono border ${badgeColor}">
            ${decVal}%
          </span>
        </div>
        <p class="text-xs text-slate-600 mb-3">${dec.diagnosis}</p>
        <div class="grid grid-cols-2 gap-3 text-xs font-mono bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
          <div>
            <span class="text-slate-400 block text-[10px] uppercase">1ª Mitad</span>
            <span class="text-slate-800 font-semibold">${dec.half_1 ? dec.half_1.label : ''}</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[10px] uppercase">2ª Mitad</span>
            <span class="text-slate-800 font-semibold">${dec.half_2 ? dec.half_2.label : ''}</span>
          </div>
        </div>
      </div>
    `;
  }

  content.innerHTML = `
    <!-- Header -->
    <div class="flex items-start justify-between pb-4 mb-4 border-b border-slate-200">
      <div>
        <div class="flex items-center gap-2 mb-1 flex-wrap">
          ${getSportBadge(act.sport_type, 'md')}
          <h2 class="text-lg font-bold text-slate-900">${act.name}</h2>
          ${data._isLoading ? `
            <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-sky-50 text-sky-700 border border-sky-200 flex items-center gap-1">
              <svg class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
              Sincronizando telemetría...
            </span>
          ` : ''}
        </div>
        <span class="text-xs text-slate-500 font-mono">${act.start_time || ''}</span>
      </div>
      <div class="text-right">
        <span class="text-lg font-mono font-bold text-slate-900">${durMins} min</span>
        <span class="text-xs text-slate-500 block font-mono">${distKm} ${act.sport_type === 'swimming' ? 'm' : 'km'}</span>
      </div>
    </div>

    <!-- Core Metrics Grid -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">FC Media</span>
        <span class="text-xl font-bold font-mono text-rose-600">${act.avg_heart_rate ? Math.round(act.avg_heart_rate) + ' bpm' : 'N/A'}</span>
      </div>
      <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
        <span class="text-xs text-slate-500">FC Máxima</span>
        <span class="text-xl font-bold font-mono text-rose-700">${act.max_heart_rate ? Math.round(act.max_heart_rate) + ' bpm' : 'N/A'}</span>
      </div>
      ${effMetricHtml}
    </div>

    <!-- Decoupling Section -->
    ${decouplingHtml}

    <!-- Swim Test Comparison (Superimposed 100m Splits) -->
    ${renderSwimTestComparisonSection(act)}

    <!-- Device Laps Proportional Ribbon & Chart -->
    ${renderProportionalLapsSection(act)}

    <!-- Expert Coach AI Evaluation Report -->
    <div class="p-5 rounded-xl bg-purple-50/70 border border-purple-200 shadow-xs mb-6 text-slate-800">
      <div class="flex items-center gap-2 mb-3">
        <div class="w-7 h-7 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-sm">
          ⚡
        </div>
        <div>
          <h3 class="text-sm font-bold text-slate-900">Análisis del Entrenador Experto en Triatlón</h3>
          <span class="text-[11px] text-purple-700">Fase de Base Aeróbica • Tolerancia Biológica y Deriva Cardíaca</span>
        </div>
      </div>
      <div class="prose prose-sm max-w-none text-slate-700 text-xs leading-relaxed space-y-3">
        ${formatCoachReport(coach.content)}
      </div>
    </div>

    <!-- Interactive Activity Chatbot with Coach -->
    <div class="p-4 sm:p-5 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-200">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-sky-100 text-[#0284c7] flex items-center justify-center font-bold text-sm">
            💬
          </div>
          <div>
            <h4 class="text-xs font-bold text-slate-900">Consulta con tu Entrenador sobre esta sesión</h4>
            <p class="text-[10px] text-slate-500">Pregúntale detalles sobre el desacople, métricas por km o recomendaciones para tus próximas sesiones.</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-mono px-2 py-0.5 rounded ${state.athleteStatus?.ai?.has_key ? 'bg-purple-50 text-purple-700 border border-purple-200' : 'bg-white text-slate-600 border border-slate-200'}">
            ${state.athleteStatus?.ai?.has_key ? '● Gemini 2.0 Flash' : '⚡ Motor Experto Fisiología'}
          </span>
          <span class="hidden sm:inline-block text-[10px] font-mono px-2 py-0.5 rounded bg-white text-sky-700 border border-slate-200">
            Sesión: ${act.name}
          </span>
        </div>
      </div>

      <!-- Quick prompts for this activity -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cómo valoras mi desacople cardiovascular en esta sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-sky-700 border border-slate-200 transition-colors shadow-2xs">
          ¿Cómo estuvo mi desacople?
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cuál fue mi split más eficiente y cómo progresó el ritmo?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-sky-700 border border-slate-200 transition-colors shadow-2xs">
          Analizar splits por km
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cómo fue mi cadencia y biomecánica en esta sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-sky-700 border border-slate-200 transition-colors shadow-2xs">
          Cadencia y biomecánica
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cuántas calorías quemé y qué pauta de carbohidratos me recomiendas?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-sky-700 border border-slate-200 transition-colors shadow-2xs">
          Calorías y nutrición
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Debería haber apretado más o estuvo bien no subir de pulso?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-sky-700 border border-slate-200 transition-colors shadow-2xs">
          ¿Debería haber forzado más?
        </button>
        <button type="button" onclick="setActivityPrompt('${act.activity_id}', '¿Cómo debería ajustar el entrenamiento de mañana según esta carga?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-sky-700 border border-slate-200 transition-colors shadow-2xs">
          ¿Cómo ajustar mañana?
        </button>
      </div>

      <!-- Messages container -->
      <div id="activity-chat-messages" class="space-y-3 max-h-64 overflow-y-auto mb-3 p-3 rounded-xl bg-white border border-slate-200 shadow-2xs">
        <!-- Rendered dynamically -->
      </div>

      <!-- Input Form -->
      <form id="form-activity-chat" onsubmit="event.preventDefault(); submitActivityChatMessage('${act.activity_id}');" class="flex gap-2">
        <input type="text" id="input-activity-chat" placeholder="Pregunta al entrenador sobre esta sesión..."
          class="flex-1 bg-white border border-slate-300 rounded-xl px-3 py-2 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#0284c7] transition-colors">
        <button type="submit" id="btn-activity-chat-send"
          class="px-4 py-2 rounded-xl bg-[#0284c7] hover:bg-[#0369a1] text-white font-semibold text-xs flex items-center gap-1.5 shadow-sm transition-all shrink-0">
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
          <div class="w-6 h-6 rounded-full bg-purple-100 border border-purple-200 flex items-center justify-center text-purple-700 shrink-0 font-bold text-[10px]">
            Coach
          </div>
        ` : ''}
        <div class="max-w-[85%] rounded-2xl p-2.5 text-xs leading-relaxed ${
          isUser 
            ? 'bg-[#0284c7] text-white rounded-tr-none' 
            : 'bg-slate-100 border border-slate-200 text-slate-800 rounded-tl-none prose prose-sm'
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
      <div class="max-w-[85%] rounded-2xl p-2.5 text-xs leading-relaxed bg-[#0284c7] text-white rounded-tr-none">
        ${formatCoachReport(text)}
      </div>
    `;
    container.appendChild(userMsgEl);

    // Loader
    const loaderEl = document.createElement('div');
    loaderEl.id = 'activity-chat-loader';
    loaderEl.className = 'flex gap-2.5 justify-start';
    loaderEl.innerHTML = `
      <div class="w-6 h-6 rounded-full bg-purple-100 border border-purple-200 flex items-center justify-center text-purple-700 shrink-0 font-bold text-[10px]">
        Coach
      </div>
      <div class="bg-slate-100 border border-slate-200 rounded-2xl rounded-tl-none p-2.5 flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-purple-600 animate-bounce"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-purple-600 animate-bounce" style="animation-delay: 0.15s"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-purple-600 animate-bounce" style="animation-delay: 0.3s"></span>
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
        <div class="w-6 h-6 rounded-full bg-purple-100 border border-purple-200 flex items-center justify-center text-purple-700 shrink-0 font-bold text-[10px]">
          Coach
        </div>
        <div class="max-w-[85%] rounded-2xl p-2.5 text-xs leading-relaxed bg-slate-100 border border-slate-200 text-slate-800 rounded-tl-none prose prose-sm">
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

// ==========================================
// Intervals.icu Planned Workout Chart Engine
// ==========================================
const INTERVALS_COLORS = {
  1: '#009e80', // Z1 Recuperación Activa / Aeróbico Ligero (Teal)
  2: '#009e00', // Z2 Fondo Aeróbico / Resistencia (Green)
  3: '#ffcb0e', // Z3 Tempo / Ritmo Medio (Yellow)
  4: '#ff7f0e', // Z4 Umbral Anaeróbico / Threshold (Orange)
  5: '#dd0447', // Z5 VO2 Máx (Crimson)
  6: '#6633cc', // Z6 Capacidad Anaeróbica (Purple)
  7: '#504861', // Z7 Neuromuscular / Sprint (Deep Violet)
  'SS': '#ffa00e', // Sweet Spot
  'max': '#e11d48', // Máximo Esfuerzo (Bright Magenta-Red)
  'rest': '#334155'  // Recuperación / Pausa (Slate)
};

const INTERVALS_ZONE_NAMES = {
  1: 'Z1 Recuperación Activa',
  2: 'Z2 Fondo Aeróbico',
  3: 'Z3 Tempo',
  4: 'Z4 Umbral (Threshold)',
  5: 'Z5 VO2 Máx',
  6: 'Z6 Capacidad Anaeróbica',
  7: 'Z7 Neuromuscular / Sprint',
  'SS': 'Sweet Spot',
  'max': 'Máximo Esfuerzo (All-Out)',
  'rest': 'Pausa / Descanso'
};

function formatSecsToMinSec(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s}s`;
  if (s === 0) return `${m} min`;
  return `${m}m ${s < 10 ? '0' : ''}${s}s`;
}

function enrichBlockTargetDetails(b, sportType) {
  const ftp = state.athleteStatus?.thresholds?.ftp || 348;
  const athThresholds = state.athleteStatus?.thresholds || {};
  const runThreshPace = athThresholds.run_threshold_pace || '3:40';
  const swimCssPace = athThresholds.css_pace || '1:29.0';
  const maxHr = athThresholds.max_hr || 183;
  const lthr = athThresholds.lthr || 159;

  const dur = b.duration || 0;
  const dist = b.distance || 0;
  const zone = b.zone || 2;

  if (b.isRest) {
    b.targetRange = `Pausa / Descanso completo (${formatSecsToMinSec(dur)})`;
    b.targetMetricType = 'Recuperación / Pausa';
    b.targetSubtext = 'Recuperación de fosfágenos (PCr) y descanso activo';
    b.secondaryLabel = 'FC Objetivo';
    b.secondaryTarget = 'Descenso progresivo (< 120 ppm)';
    b.secondaryIcon = '❤️';
    b.physioFocus = 'Estabilización cardiorrespiratoria y recarga energética antes del siguiente bloque.';
    return;
  }

  if (b.isMax) {
    if (sportType === 'cycling') {
      const minW = Math.round(ftp * 1.2);
      b.targetRange = `> ${minW} W (Esfuerzo Máximo / All-Out > 120% FTP)`;
      b.targetMetricType = 'Potencia Pico (Vatios)';
      b.targetSubtext = `FTP de referencia: ${ftp} W`;
      b.secondaryLabel = 'FC Esperada';
      b.secondaryTarget = `165 - ${maxHr} ppm (FC Máxima)`;
      b.secondaryIcon = '⚡';
      b.physioFocus = 'Test de potencia máxima y agotamiento glucolítico de alta intensidad.';
    } else if (sportType === 'swimming') {
      let lowLimit = '1:25';
      let highLimit = '1:29';
      if (dist === 200) {
        lowLimit = '1:20';
        highLimit = '1:24';
      } else if (dist === 400) {
        lowLimit = '1:25';
        highLimit = '1:29';
      } else if (dist > 0 && dist <= 100) {
        lowLimit = '1:15';
        highLimit = '1:20';
      }
      b.targetRange = `${lowLimit} - ${highLimit} min/100m`;
      b.targetMetricType = 'Rango Objetivo Test Máximo';
      b.targetSubtext = `Límite inferior: ${lowLimit}/100m  •  Límite superior: ${highLimit}/100m  •  CSS: ${swimCssPace}/100m`;
      b.secondaryLabel = 'Estrategia';
      b.secondaryTarget = 'Ritmo máximo sostenido dentro del rango';
      b.secondaryIcon = '🏊';
      b.physioFocus = dist > 0 ? `Test crítico de velocidad aeróbica máxima (CSS) en ${dist}m.` : 'Esfuerzo máximo all-out.';
    } else {
      b.targetRange = `< 3:15 min/km (Sprint All-Out)`;
      b.targetMetricType = 'Ritmo Máximo (min/km)';
      b.targetSubtext = `Umbral: ${runThreshPace}/km`;
      b.secondaryLabel = 'FC Esperada';
      b.secondaryTarget = `> 165 ppm`;
      b.secondaryIcon = '🏃';
      b.physioFocus = 'Máxima velocidad anaeróbica y reclutamiento de unidades motoras rápidas.';
    }
    return;
  }

  if (sportType === 'cycling') {
    if (b.isRamp) {
      b.targetMetricType = 'Potencia (Rampa Progresiva)';
      b.secondaryLabel = 'FC Esperada';
      b.secondaryTarget = '115 - 145 ppm';
      b.secondaryIcon = '📈';
      b.physioFocus = 'Activación neuromuscular progresiva y calentamiento gradual.';
      return;
    }

    const pzRanges = {
      1: { w: `0 - ${Math.round(ftp * 0.55)} W`, pct: '0% - 55% FTP', hr: '< 127 ppm', focus: 'Recuperación activa, capilarización y aclarado de lactato.' },
      2: { w: `${Math.round(ftp * 0.55) + 1} - ${Math.round(ftp * 0.75)} W`, pct: '56% - 75% FTP', hr: '128 - 142 ppm', focus: 'Construcción mitocondrial, eficiencia aeróbica y metabolismo lipídico.' },
      3: { w: `${Math.round(ftp * 0.75) + 1} - ${Math.round(ftp * 0.90)} W`, pct: '76% - 90% FTP', hr: '143 - 148 ppm', focus: 'Ritmo tempo crucero y resistencia a la fatiga muscular.' },
      4: { w: `${Math.round(ftp * 0.90) + 1} - ${Math.round(ftp * 1.05)} W`, pct: '91% - 105% FTP', hr: '149 - 158 ppm', focus: 'Potencia umbral anaeróbico funcional (FTP) y estado estacionario.' },
      5: { w: `${Math.round(ftp * 1.05) + 1} - ${Math.round(ftp * 1.20)} W`, pct: '106% - 120% FTP', hr: '159 - 162 ppm', focus: 'Consumo máximo de oxígeno (VO2 Máx) y gasto cardíaco pico.' },
      6: { w: `${Math.round(ftp * 1.20) + 1} - ${Math.round(ftp * 1.50)} W`, pct: '121% - 150% FTP', hr: '163 - 167 ppm', focus: 'Capacidad glucolítica anaeróbica láctica y tolerancia a la acidosis.' },
      7: { w: `> ${Math.round(ftp * 1.50)} W`, pct: '> 150% FTP', hr: '> 168 ppm', focus: 'Potencia neuromuscular explosiva y sprint sin limitación aeróbica.' }
    };
    const zNum = typeof zone === 'number' ? zone : 2;
    const rInfo = pzRanges[zNum] || pzRanges[2];
    b.targetRange = b.targetRange || `${rInfo.w} (${rInfo.pct})`;
    b.targetMetricType = b.targetMetricType || `Potencia Zona ${zNum}`;
    b.targetSubtext = b.targetSubtext || `FTP de referencia: ${ftp} W`;
    b.secondaryLabel = b.secondaryLabel || 'FC Esperada';
    b.secondaryTarget = b.secondaryTarget || rInfo.hr;
    b.secondaryIcon = b.secondaryIcon || '❤️';
    b.physioFocus = b.physioFocus || rInfo.focus;
    return;
  }

  if (sportType === 'running') {
    const runRanges = {
      1: { pace: '> 4:45 min/km (4:45 - 5:30)', hr: '< 134 ppm', focus: 'Regeneración y carrera suave de asimilación.' },
      2: { pace: '4:11 - 4:44 min/km', hr: '135 - 142 ppm', focus: 'Fondo aeróbico, densidad capilar y economía de zancada.' },
      3: { pace: '3:53 - 4:10 min/km', hr: '143 - 150 ppm', focus: 'Ritmo tempo continuo sin elevación brusca de lactato.' },
      4: { pace: '3:40 - 3:52 min/km', hr: '151 - 158 ppm', focus: 'Ritmo umbral anaeróbico funcional de carrera.' },
      5: { pace: '3:18 - 3:37 min/km', hr: '159 - 162 ppm', focus: 'Series de potencia aeróbica y VO2 Máx.' },
      6: { pace: '< 3:17 min/km', hr: '163 - 167 ppm', focus: 'Velocidad anaeróbica láctica y cambios de ritmo.' },
      7: { pace: 'Sprint Máximo (< 3:00)', hr: '> 168 ppm', focus: 'Capacidad neuromuscular y sprint final.' }
    };
    const zNum = typeof zone === 'number' ? zone : 2;
    const rr = runRanges[zNum] || runRanges[2];
    b.targetRange = b.targetRange || rr.pace;
    b.targetMetricType = b.targetMetricType || `Ritmo Zona ${zNum} (Pace)`;
    b.targetSubtext = b.targetSubtext || `Umbral de referencia: ${runThreshPace}/km`;
    b.secondaryLabel = b.secondaryLabel || 'FC Esperada';
    b.secondaryTarget = b.secondaryTarget || rr.hr;
    b.secondaryIcon = b.secondaryIcon || '❤️';
    b.physioFocus = b.physioFocus || rr.focus;
    return;
  }

  if (sportType === 'swimming') {
    const swimZoneRanges = {
      1: { low: '1:55', high: '2:05', name: 'Z1 Suave / Técnica', focus: 'Sensación de agarre, rolido y nado regenerativo suave.' },
      2: { low: '1:42', high: '1:54', name: 'Z2 Fondo Aeróbico', focus: 'Capacidad aeróbica mitocondrial y eficiencia de brazada (SWOLF).' },
      3: { low: '1:34', high: '1:41', name: 'Z3 Tempo', focus: 'Resistencia aeróbica media y ritmo crucero continuo.' },
      4: { low: '1:29', high: '1:33', name: 'Z4 CSS Umbral', focus: 'Velocidad crítica de nado (CSS), estado estable de lactato.' },
      5: { low: '1:26', high: '1:28', name: 'Z5 VO2 Máx', focus: 'Potencia aeróbica máxima y frecuencia de ciclo alta.' },
      6: { low: '1:20', high: '1:25', name: 'Z6 Capacidad Anaeróbica', focus: 'Tolerancia a la acidosis y ritmos de prueba corta.' },
      7: { low: '1:12', high: '1:19', name: 'Z7 Sprint / All-Out', focus: 'Potencia neuromuscular pura y velocidad máxima all-out.' }
    };

    let zNum = typeof zone === 'number' ? zone : 2;
    if (dist > 0 && dur > 0) {
      const avgSec100 = (dur / dist) * 100;
      if (avgSec100 > 114) zNum = 1;
      else if (avgSec100 >= 102) zNum = 2;
      else if (avgSec100 >= 94) zNum = 3;
      else if (avgSec100 >= 89) zNum = 4;
      else if (avgSec100 >= 86) zNum = 5;
      else if (avgSec100 >= 80) zNum = 6;
      else zNum = 7;
    }

    const zr = swimZoneRanges[zNum] || swimZoneRanges[2];
    b.targetRange = `${zr.low} - ${zr.high} min/100m`;
    b.targetMetricType = `Ritmo Planificado (${zr.name})`;
    b.targetSubtext = `Límite inferior: ${zr.low}/100m  •  Límite superior: ${zr.high}/100m  •  CSS: ${swimCssPace}/100m`;
    b.secondaryLabel = 'Distancia / Bloque';
    b.secondaryTarget = dist > 0 ? `${dist}m (${formatSecsToMinSec(dur)})` : formatSecsToMinSec(dur);
    b.secondaryIcon = '🏊';
    b.physioFocus = zr.focus;
    return;


    b.targetMetricType = b.targetMetricType || `Ritmo Natación Z${zNum}`;
    b.targetSubtext = b.targetSubtext || `CSS de referencia: ${swimCssPace}/100m`;
    b.secondaryLabel = b.secondaryLabel || 'CSS Umbral';
    b.secondaryTarget = b.secondaryTarget || `${swimCssPace}/100m`;
    b.secondaryIcon = b.secondaryIcon || '🏊';
    b.physioFocus = b.physioFocus || sp.focus;
    return;
  }

  // Generic other sport
  b.targetRange = b.targetRange || `${formatSecsToMinSec(dur)} en Zona Aeróbica`;
  b.targetMetricType = b.targetMetricType || 'Intervalo de Tiempo';
  b.secondaryLabel = b.secondaryLabel || 'Zona';
  b.secondaryTarget = b.secondaryTarget || `Z${zone}`;
  b.secondaryIcon = b.secondaryIcon || '⏱️';
  b.physioFocus = b.physioFocus || 'Mantenimiento del ritmo y adaptación aeróbica.';
}

function flattenWorkoutSteps(rawSteps, sportType, athleteFtp) {
  const blocks = [];
  const ftp = athleteFtp || (state.athleteStatus?.thresholds?.ftp || 348);

  function processStep(step, repInfo = null) {
    if (step.reps && step.steps && Array.isArray(step.steps)) {
      const reps = Number(step.reps) || 1;
      const repLabel = step.text || `${reps}x`;
      for (let r = 0; r < reps; r++) {
        for (const sub of step.steps) {
          processStep(sub, {
            repIndex: r + 1,
            repTotal: reps,
            groupLabel: repLabel
          });
        }
      }
      return;
    }

    const dur = step.duration || 0;
    const dist = step.distance || 0;
    const isMax = Boolean(step.maxeffort);
    const pwr = step.power || null;
    const pace = step.pace || null;
    const hr = step.hr || null;

    let zone = 2;
    let color = INTERVALS_COLORS[2];
    let zoneName = INTERVALS_ZONE_NAMES[2];
    let label = '';
    let shortLabel = '';
    let isRamp = false;
    let heightStart = 60;
    let heightEnd = 60;
    let isRest = false;

    if (dur > 0 && dist === 0 && !pwr && !pace && !hr && !isMax) {
      isRest = true;
      zone = 'rest';
      color = INTERVALS_COLORS.rest;
      zoneName = INTERVALS_ZONE_NAMES.rest;
      label = `Descanso ${dur}s`;
      shortLabel = `${dur}s ⏸`;
      heightStart = 14;
      heightEnd = 14;
    } else if (isMax) {
      zone = 'max';
      color = INTERVALS_COLORS.max;
      zoneName = INTERVALS_ZONE_NAMES.max;
      label = dist > 0 ? `${dist}m Máximo Esfuerzo (All-Out)` : `Máximo Esfuerzo (${dur}s)`;
      shortLabel = dist > 0 ? `${dist}m MAX` : 'MAX';
      heightStart = 140;
      heightEnd = 140;
    } else if (pwr) {
      const units = pwr.units || '';
      if (units === 'power_zone') {
        zone = Math.min(7, Math.max(1, pwr.value || 2));
        color = INTERVALS_COLORS[zone] || INTERVALS_COLORS[2];
        zoneName = INTERVALS_ZONE_NAMES[zone];
        const hMap = { 1: 38, 2: 60, 3: 78, 4: 92, 5: 110, 6: 128, 7: 140 };
        heightStart = hMap[zone] || 60;
        heightEnd = heightStart;
        label = `Zona ${zone} (${dur > 0 ? formatSecsToMinSec(dur) : ''})`;
        shortLabel = `Z${zone}`;
      } else if (units === '%ftp') {
        const startP = pwr.start !== undefined ? pwr.start : (pwr.value || 70);
        const endP = pwr.end !== undefined ? pwr.end : startP;
        const startW = Math.round(ftp * (startP / 100));
        const endW = Math.round(ftp * (endP / 100));

        heightStart = Math.min(142, Math.max(14, Math.round((startP / 100) * 92)));
        heightEnd = Math.min(142, Math.max(14, Math.round((endP / 100) * 92)));

        const avgP = (startP + endP) / 2;
        zone = avgP < 56 ? 1 : (avgP < 76 ? 2 : (avgP < 91 ? 3 : (avgP < 106 ? 4 : (avgP < 121 ? 5 : (avgP < 151 ? 6 : 7)))));
        color = INTERVALS_COLORS[zone] || INTERVALS_COLORS[2];
        zoneName = INTERVALS_ZONE_NAMES[zone];

        if (startP !== endP) {
          isRamp = true;
          label = `Rampa: ${startW}W - ${endW}W (${startP}% - ${endP}% FTP)`;
          shortLabel = `${startW}-${endW}W`;
        } else {
          label = `${startW}W (${startP}% FTP)`;
          shortLabel = `${startW}W`;
        }
      }
    } else if (pace) {
      const units = pace.units || '';
      if (units === 'pace_zone') {
        zone = Math.min(7, Math.max(1, pace.value || 2));
        color = INTERVALS_COLORS[zone] || INTERVALS_COLORS[2];
        zoneName = INTERVALS_ZONE_NAMES[zone];
        const hMap = { 1: 38, 2: 60, 3: 78, 4: 92, 5: 110, 6: 128, 7: 140 };
        heightStart = hMap[zone] || 60;
        heightEnd = heightStart;
        label = `Zona ${zone} Ritmo`;
        shortLabel = `Z${zone}`;
      }
    } else if (hr) {
      const units = hr.units || '';
      if (units === 'hr_zone') {
        zone = Math.min(7, Math.max(1, hr.value || 2));
        color = INTERVALS_COLORS[zone] || INTERVALS_COLORS[2];
        zoneName = INTERVALS_ZONE_NAMES[zone];
        const hMap = { 1: 38, 2: 60, 3: 78, 4: 92, 5: 110, 6: 128, 7: 140 };
        heightStart = hMap[zone] || 60;
        heightEnd = heightStart;
        label = `Zona ${zone} Pulso`;
        shortLabel = `Z${zone} FC`;
      }
    } else if (dist > 0) {
      zone = 2;
      color = INTERVALS_COLORS[2];
      zoneName = INTERVALS_ZONE_NAMES[2];
      heightStart = 60;
      heightEnd = 60;
      label = `${dist}m Ritmo aeróbico`;
      shortLabel = `${dist}m`;
    } else {
      zone = 2;
      color = INTERVALS_COLORS[2];
      zoneName = INTERVALS_ZONE_NAMES[2];
      heightStart = 60;
      heightEnd = 60;
      label = dur > 0 ? `${formatSecsToMinSec(dur)}` : 'Intervalo';
      shortLabel = dur > 0 ? `${Math.round(dur/60)}'` : '';
    }

    const blockObj = {
      duration: dur > 0 ? dur : (dist > 0 ? dist * 1.5 : 60),
      distance: dist,
      zone,
      color,
      zoneName,
      label,
      shortLabel,
      isRamp,
      heightStart,
      heightEnd,
      isRest,
      isMax,
      repInfo
    };

    enrichBlockTargetDetails(blockObj, sportType);
    blocks.push(blockObj);
  }

  for (const s of rawSteps) {
    processStep(s);
  }

  return blocks;
}

function parseDescriptionWorkoutSteps(desc, name, sportType, plannedDurSec, targetZones) {
  if (targetZones && typeof targetZones === 'object') {
    const blocks = [];
    const zMap = { Z1: 1, Z2: 2, Z3: 3, Z4: 4, Z5: 5, Z6: 6, Z7: 7 };
    for (const [zKey, secs] of Object.entries(targetZones)) {
      if (secs > 0) {
        const zNum = zMap[zKey] || 2;
        const hMap = { 1: 38, 2: 60, 3: 78, 4: 92, 5: 110, 6: 128, 7: 140 };
        const b = {
          duration: secs,
          distance: 0,
          zone: zNum,
          color: INTERVALS_COLORS[zNum] || INTERVALS_COLORS[2],
          zoneName: INTERVALS_ZONE_NAMES[zNum] || zKey,
          label: `${zKey} (${Math.round(secs/60)} min)`,
          shortLabel: `${Math.round(secs/60)}' ${zKey}`,
          isRamp: false,
          heightStart: hMap[zNum] || 60,
          heightEnd: hMap[zNum] || 60,
          isRest: false,
          isMax: false,
          repInfo: null
        };
        enrichBlockTargetDetails(b, sportType);
        blocks.push(b);
      }
    }
    if (blocks.length > 0) return blocks;
  }

  const fullText = `${name || ''} ${desc || ''}`;
  const regex = /(\d+)\s*(?:'|min|m)\s*(?:en\s*)?(z[1-7]|umbral|tempo|suave|fuerte)/gi;
  let match;
  const parsedBlocks = [];
  while ((match = regex.exec(fullText)) !== null) {
    const mins = parseInt(match[1], 10);
    const zStr = match[2].toLowerCase();
    let zNum = 2;
    if (zStr.includes('z1') || zStr.includes('suave')) zNum = 1;
    else if (zStr.includes('z2')) zNum = 2;
    else if (zStr.includes('z3') || zStr.includes('tempo')) zNum = 3;
    else if (zStr.includes('z4') || zStr.includes('umbral')) zNum = 4;
    else if (zStr.includes('z5') || zStr.includes('fuerte')) zNum = 5;
    else if (zStr.includes('z6')) zNum = 6;
    else if (zStr.includes('z7')) zNum = 7;

    const hMap = { 1: 38, 2: 60, 3: 78, 4: 92, 5: 110, 6: 128, 7: 140 };
    const b = {
      duration: mins * 60,
      distance: 0,
      zone: zNum,
      color: INTERVALS_COLORS[zNum] || INTERVALS_COLORS[2],
      zoneName: INTERVALS_ZONE_NAMES[zNum] || `Z${zNum}`,
      label: `Zona ${zNum} (${mins} min)`,
      shortLabel: `${mins}' Z${zNum}`,
      isRamp: false,
      heightStart: hMap[zNum] || 60,
      heightEnd: hMap[zNum] || 60,
      isRest: false,
      isMax: false,
      repInfo: null
    };
    enrichBlockTargetDetails(b, sportType);
    parsedBlocks.push(b);
  }

  if (parsedBlocks.length > 0) return parsedBlocks;

  const total = plannedDurSec > 0 ? plannedDurSec : 3600;
  const wu = Math.round(total * 0.2);
  const main = Math.round(total * 0.65);
  const cd = total - wu - main;

  const bWu = {
    duration: wu,
    distance: 0,
    zone: 1,
    color: INTERVALS_COLORS[1],
    zoneName: INTERVALS_ZONE_NAMES[1],
    label: `Calentamiento (${Math.round(wu/60)} min)`,
    shortLabel: `${Math.round(wu/60)}' Z1`,
    isRamp: false,
    heightStart: 38,
    heightEnd: 38,
    isRest: false,
    isMax: false,
    repInfo: null
  };
  enrichBlockTargetDetails(bWu, sportType);

  const bMain = {
    duration: main,
    distance: 0,
    zone: 2,
    color: INTERVALS_COLORS[2],
    zoneName: INTERVALS_ZONE_NAMES[2],
    label: `Parte Principal Aeróbica (${Math.round(main/60)} min)`,
    shortLabel: `${Math.round(main/60)}' Z2`,
    isRamp: false,
    heightStart: 60,
    heightEnd: 60,
    isRest: false,
    isMax: false,
    repInfo: null
  };
  enrichBlockTargetDetails(bMain, sportType);

  const bCd = {
    duration: cd,
    distance: 0,
    zone: 1,
    color: INTERVALS_COLORS[1],
    zoneName: INTERVALS_ZONE_NAMES[1],
    label: `Enfriamiento / Vuelta a la Calma (${Math.round(cd/60)} min)`,
    shortLabel: `${Math.round(cd/60)}' Z1`,
    isRamp: false,
    heightStart: 38,
    heightEnd: 38,
    isRest: false,
    isMax: false,
    repInfo: null
  };
  enrichBlockTargetDetails(bCd, sportType);

  return [bWu, bMain, bCd];
}

function renderPlannedWorkoutChart(ev) {
  const sport = ev.sport_type || 'other';
  const isNote = ev.is_note || ev.category === 'NOTE';
  const wdoc = ev.workout_doc || {};
  const rawSteps = wdoc.steps || [];

  let blocks = [];
  if (rawSteps.length > 0) {
    blocks = flattenWorkoutSteps(rawSteps, sport, state.athleteStatus?.thresholds?.ftp || 348);
  } else if (!isNote && (sport === 'cycling' || sport === 'running' || sport === 'swimming')) {
    blocks = parseDescriptionWorkoutSteps(ev.description, ev.name, sport, ev.planned_duration_seconds, ev.target_zones);
  }

  if (blocks.length === 0) return '';

  // Store globally so the interactive tooltip card can access all target details
  window._currentWorkoutBlocks = blocks;

  const totalDuration = blocks.reduce((sum, b) => sum + (b.duration || 60), 0);
  const totalDist = wdoc.distance || ev.planned_distance_meters || 0;

  const svgWidth = 1000;
  const svgHeight = 160;
  const baselineY = 138;
  const threshY = baselineY - 92;

  let currentX = 0;
  const stepElements = [];

  blocks.forEach((b, idx) => {
    const blockW = (b.duration / totalDuration) * svgWidth;
    const x = currentX;
    currentX += blockW;

    if (b.isRamp) {
      const y1 = baselineY - b.heightStart;
      const y2 = baselineY - b.heightEnd;
      const pts = `${x.toFixed(1)},${baselineY} ${x.toFixed(1)},${y1.toFixed(1)} ${(x + blockW).toFixed(1)},${y2.toFixed(1)} ${(x + blockW).toFixed(1)},${baselineY}`;
      stepElements.push(`
        <polygon points="${pts}" fill="${b.color}" fill-opacity="0.9" stroke="#0f172a" stroke-width="1"
          class="transition-opacity hover:opacity-100 cursor-pointer"
          onmouseenter="window.showWorkoutStepTip(event, ${idx})"
          onmousemove="window.moveWorkoutStepTip(event)"
          onmouseleave="window.hideWorkoutStepTip()"
          onclick="window.showWorkoutStepTip(event, ${idx})" />
      `);
    } else {
      const y = baselineY - b.heightStart;
      const h = b.heightStart;
      stepElements.push(`
        <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, blockW).toFixed(1)}" height="${h.toFixed(1)}"
          fill="${b.color}" fill-opacity="0.9" stroke="#0f172a" stroke-width="1" rx="1.5"
          class="transition-opacity hover:opacity-100 cursor-pointer"
          onmouseenter="window.showWorkoutStepTip(event, ${idx})"
          onmousemove="window.moveWorkoutStepTip(event)"
          onmouseleave="window.hideWorkoutStepTip()"
          onclick="window.showWorkoutStepTip(event, ${idx})" />
      `);
    }

    if (blockW > 38 && b.shortLabel) {
      const midX = x + blockW / 2;
      const textY = Math.min(baselineY - 6, (baselineY - Math.max(b.heightStart, b.heightEnd)) + 14);
      stepElements.push(`
        <text x="${midX.toFixed(1)}" y="${textY.toFixed(1)}" text-anchor="middle" fill="#ffffff" font-size="9.5" font-weight="bold" font-family="monospace" pointer-events="none" opacity="0.95">${b.shortLabel}</text>
      `);
    }
  });

  const zoneTimesRaw = wdoc.zoneTimes || [];
  const hasRawZT = zoneTimesRaw.some(zt => (zt.secs || 0) > 0);
  let ribbonSegments = [];
  let legendPills = [];

  if (hasRawZT) {
    const activeTotal = zoneTimesRaw.reduce((acc, zt) => acc + (zt.secs || 0), 0) || totalDuration;
    zoneTimesRaw.filter(zt => (zt.secs || 0) > 0).forEach(zt => {
      const pct = Math.round((zt.secs / activeTotal) * 100);
      const color = zt.color || INTERVALS_COLORS[zt.zone || 2] || '#009e00';
      const name = zt.name || zt.id;
      const mins = Math.round(zt.secs / 60);
      const wattsRange = (zt.minWatts && zt.maxWatts && zt.maxWatts < 9000) ? `${zt.minWatts}-${zt.maxWatts}W` : (zt.percentRange || '');

      ribbonSegments.push(`
        <div style="width: ${(zt.secs / activeTotal * 100).toFixed(1)}%; background-color: ${color};" class="h-3 relative group transition-transform hover:scale-y-125" title="${name}: ${mins}m (${pct}%)"></div>
      `);

      legendPills.push(`
        <div class="flex items-center gap-1.5 px-2 py-1 rounded bg-white border border-slate-200 text-[11px] font-mono shadow-2xs">
          <span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background-color: ${color};"></span>
          <span class="font-bold text-slate-800">${name}</span>
          <span class="text-slate-500">${mins}m <span class="text-slate-400">(${pct}%)</span></span>
          ${wattsRange ? `<span class="text-slate-400 text-[10px] hidden sm:inline pl-1 border-l border-slate-200">${wattsRange}</span>` : ''}
        </div>
      `);
    });
  } else {
    const zAgg = {};
    let activeTotal = 0;
    blocks.forEach(b => {
      if (b.isRest) return;
      const key = b.isMax ? 'MAX' : `Z${b.zone || 2}`;
      if (!zAgg[key]) {
        zAgg[key] = { name: b.zoneName || key, color: b.color, secs: 0 };
      }
      zAgg[key].secs += b.duration;
      activeTotal += b.duration;
    });

    Object.values(zAgg).forEach(item => {
      const pct = Math.round((item.secs / (activeTotal || 1)) * 100);
      const mins = Math.round(item.secs / 60);
      ribbonSegments.push(`
        <div style="width: ${(item.secs / (activeTotal || 1) * 100).toFixed(1)}%; background-color: ${item.color};" class="h-3 relative group transition-transform hover:scale-y-125" title="${item.name}: ${mins}m (${pct}%)"></div>
      `);
      legendPills.push(`
        <div class="flex items-center gap-1.5 px-2 py-1 rounded bg-white border border-slate-200 text-[11px] font-mono shadow-2xs">
          <span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background-color: ${item.color};"></span>
          <span class="font-bold text-slate-800">${item.name}</span>
          <span class="text-slate-500">${mins}m <span class="text-slate-400">(${pct}%)</span></span>
        </div>
      `);
    });
  }

  return `
    <div class="mt-4 p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
      <!-- Chart Header & Metrics -->
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-200 flex-wrap gap-2">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-sky-100 text-[#0284c7] flex items-center justify-center font-bold text-sm">
            📊
          </div>
          <div>
            <h4 class="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-1.5">
              Estructura Planificada Intervals.icu
              <span class="text-[10px] px-2 py-0.5 rounded font-mono font-normal bg-sky-50 text-[#0284c7] border border-sky-200">Zonas & Perfil</span>
            </h4>
            <p class="text-[10px] text-slate-500">Pasa el cursor por cada bloque para ver sus rangos objetivo exactos de potencia, ritmo y pulso.</p>
          </div>
        </div>
        
        <div class="flex items-center gap-1.5 flex-wrap">
          ${wdoc.normalized_power ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-50 text-amber-700 border border-amber-200" title="Potencia Normalizada Prevista">NP: ${Math.round(wdoc.normalized_power)}W</span>` : ''}
          ${wdoc.average_watts ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-white text-slate-700 border border-slate-200" title="Potencia Media Prevista">P.Med: ${Math.round(wdoc.average_watts)}W</span>` : ''}
          ${wdoc.variability_index ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-purple-50 text-purple-700 border border-purple-200" title="Índice de Variabilidad">VI: ${wdoc.variability_index.toFixed(2)}</span>` : ''}
          ${ev.planned_load ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-50 text-amber-700 border border-amber-200 font-bold">${ev.planned_load} TSS</span>` : ''}
        </div>
      </div>

      <!-- SVG Stepped Chart -->
      <div class="relative bg-white p-3 rounded-lg border border-slate-200 overflow-hidden shadow-2xs">
        <svg viewBox="0 0 ${svgWidth} ${svgHeight}" class="w-full h-40 sm:h-48 overflow-visible select-none" preserveAspectRatio="none">
          <!-- Grid lines -->
          <line x1="0" y1="${threshY}" x2="${svgWidth}" y2="${threshY}" stroke="#d97706" stroke-dasharray="3,3" stroke-width="1.2" opacity="0.75" />
          <text x="${svgWidth - 6}" y="${threshY - 4}" text-anchor="end" fill="#d97706" font-size="9" font-family="monospace" font-weight="bold" opacity="0.95">100% Umbral / FTP</text>

          <line x1="0" y1="${baselineY - 46}" x2="${svgWidth}" y2="${baselineY - 46}" stroke="#cbd5e1" stroke-dasharray="2,4" stroke-width="0.8" opacity="0.7" />
          <text x="${svgWidth - 6}" y="${baselineY - 50}" text-anchor="end" fill="#64748b" font-size="8.5" font-family="monospace" opacity="0.8">50%</text>

          <!-- Baseline ground -->
          <line x1="0" y1="${baselineY}" x2="${svgWidth}" y2="${baselineY}" stroke="#94a3b8" stroke-width="1.2" />

          <!-- Step blocks -->
          ${stepElements.join('')}

          <!-- Time axis labels -->
          <text x="4" y="${svgHeight - 4}" fill="#64748b" font-size="9.5" font-family="monospace">0:00</text>
          <text x="${svgWidth / 2}" y="${svgHeight - 4}" text-anchor="middle" fill="#64748b" font-size="9.5" font-family="monospace">${formatSecsToMinSec(Math.round(totalDuration / 2))}</text>
          <text x="${svgWidth - 4}" y="${svgHeight - 4}" text-anchor="end" fill="#64748b" font-size="9.5" font-family="monospace">${formatSecsToMinSec(totalDuration)} ${totalDist > 0 ? `• ${(totalDist >= 1000 && sport !== 'swimming') ? (totalDist/1000).toFixed(1)+'km' : Math.round(totalDist)+'m'}` : ''}</text>
        </svg>
      </div>

      <!-- Zone Distribution Ribbon -->
      <div class="mt-3.5 pt-3 border-t border-slate-200">
        <div class="flex items-center justify-between mb-1.5">
          <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">Distribución de Tiempo en Zonas (Intervals.icu)</span>
          <span class="text-[10px] font-mono text-slate-500">${formatSecsToMinSec(totalDuration)} total</span>
        </div>

        <!-- Ribbon Bar -->
        <div class="w-full flex rounded-full overflow-hidden bg-slate-100 border border-slate-200 mb-2.5">
          ${ribbonSegments.join('')}
        </div>

        <!-- Legend Pills -->
        <div class="flex flex-wrap gap-1.5">
          ${legendPills.join('')}
        </div>
      </div>
    </div>
  `;
}

// Interactive Floating Card Handlers
window.showWorkoutStepTip = function(e, stepIdx) {
  const blocks = window._currentWorkoutBlocks || [];
  const b = blocks[stepIdx];
  if (!b) return;

  const isClick = e.type === 'click';
  if (isClick) {
    window._workoutStepTipPinned = true;
  }

  let tip = document.getElementById('planned-workout-tooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'planned-workout-tooltip';
    document.body.appendChild(tip);

    document.addEventListener('click', (evt) => {
      if (!evt.target.closest('svg') && !evt.target.closest('#planned-workout-tooltip')) {
        window._workoutStepTipPinned = false;
        window.hideWorkoutStepTip(true);
      }
    });
  }

  tip.className = window._workoutStepTipPinned
    ? 'fixed pointer-events-auto z-[9999] hidden shadow-2xl transition-opacity duration-75'
    : 'fixed pointer-events-none z-[9999] hidden shadow-2xl transition-opacity duration-75';

  const title = b.repInfo
    ? `${b.repInfo.groupLabel} (Rep ${b.repInfo.repIndex}/${b.repInfo.repTotal})`
    : (b.label || `Intervalo #${stepIdx + 1}`);

  tip.innerHTML = `
    <div class="p-3.5 bg-slate-950/95 border border-slate-700/80 rounded-xl shadow-2xl backdrop-blur-md w-72 sm:w-80 text-xs">
      <!-- Card Header -->
      <div class="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <div class="flex items-center gap-2 min-w-0">
          <span class="w-3 h-3 rounded-full shrink-0 shadow" style="background-color: ${b.color};"></span>
          <span class="font-bold text-slate-100 truncate">${title}</span>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold shrink-0" style="background-color: ${b.color}22; color: ${b.color}; border: 1px solid ${b.color}55;">
            ${b.zoneName}
          </span>
          <button onclick="window._workoutStepTipPinned=false; window.hideWorkoutStepTip(true);" class="text-slate-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-slate-800 text-xs font-bold leading-none cursor-pointer" title="Cerrar">✕</button>
        </div>
      </div>

      <!-- Duration & Distance / Rep Pill Grid -->
      <div class="grid grid-cols-2 gap-2 mb-2.5 font-mono text-[11px]">
        <div class="bg-slate-900/90 px-2.5 py-1.5 rounded-lg border border-slate-800/80">
          <span class="text-[9.5px] text-slate-500 block uppercase font-semibold">⏱️ Duración</span>
          <span class="font-bold text-amber-400">${formatSecsToMinSec(b.duration)}</span>
        </div>
        <div class="bg-slate-900/90 px-2.5 py-1.5 rounded-lg border border-slate-800/80">
          <span class="text-[9.5px] text-slate-500 block uppercase font-semibold">📏 ${b.distance > 0 ? 'Distancia' : (b.repInfo ? 'Repetición' : 'Tipo')}</span>
          <span class="font-bold text-sky-400">${b.distance > 0 ? b.distance + ' m' : (b.repInfo ? b.repInfo.repIndex + '/' + b.repInfo.repTotal : (b.isRest ? 'Pausa' : 'Intervalo'))}</span>
        </div>
      </div>

      <!-- Target Range Highlight Box -->
      <div class="p-2.5 rounded-lg bg-gradient-to-r from-slate-900 via-slate-900/95 to-slate-900 border border-amber-500/30 mb-2 shadow-inner">
        <div class="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-amber-400 mb-1">
          <span class="flex items-center gap-1"><span>🎯</span> Rango Objetivo</span>
          <span class="text-[9px] font-mono font-normal text-slate-400">${b.targetMetricType || 'Intensidad'}</span>
        </div>
        <div class="text-[12.5px] font-mono font-bold text-slate-100 leading-snug">
          ${b.targetRange}
        </div>
        ${b.targetSubtext ? `<div class="text-[10px] font-mono text-slate-400 mt-0.5">${b.targetSubtext}</div>` : ''}
      </div>

      <!-- Secondary Target / Expected HR -->
      ${b.secondaryTarget ? `
        <div class="flex items-center justify-between text-[10.5px] font-mono px-2.5 py-1.5 rounded-lg bg-slate-900/70 border border-slate-800/80 text-slate-300 mb-2">
          <span class="text-slate-400 flex items-center gap-1"><span>${b.secondaryIcon || '❤️'}</span> ${b.secondaryLabel}:</span>
          <span class="font-bold text-emerald-400">${b.secondaryTarget}</span>
        </div>
      ` : ''}

      <!-- Physiological Focus / Purpose -->
      <div class="text-[10px] text-slate-400 leading-snug flex items-start gap-1.5 pt-1.5 border-t border-slate-800/80">
        <span class="text-amber-400 shrink-0 text-xs">💡</span>
        <span>${b.physioFocus || 'Adaptación al estímulo de entrenamiento'}</span>
      </div>
    </div>
  `;

  tip.classList.remove('hidden');

  const tipWidth = 320;
  const tipHeight = 230;
  let x = e.clientX + 14;
  let y = e.clientY - 110;

  if (x + tipWidth > window.innerWidth - 10) {
    x = e.clientX - tipWidth - 14;
  }
  if (x < 10) x = 10;
  if (y + tipHeight > window.innerHeight - 10) {
    y = window.innerHeight - tipHeight - 10;
  }
  if (y < 10) y = 10;

  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
};

window.moveWorkoutStepTip = function(e) {
  if (window._workoutStepTipPinned) return;
  const tip = document.getElementById('planned-workout-tooltip');
  if (!tip || tip.classList.contains('hidden')) return;

  const tipWidth = 320;
  const tipHeight = 230;
  let x = e.clientX + 14;
  let y = e.clientY - 110;

  if (x + tipWidth > window.innerWidth - 10) {
    x = e.clientX - tipWidth - 14;
  }
  if (x < 10) x = 10;
  if (y + tipHeight > window.innerHeight - 10) {
    y = window.innerHeight - tipHeight - 10;
  }
  if (y < 10) y = 10;

  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
};

window.hideWorkoutStepTip = function(force = false) {
  if (window._workoutStepTipPinned && !force) return;
  const tip = document.getElementById('planned-workout-tooltip');
  if (tip) tip.classList.add('hidden');
};

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

  const existingChatHtml = document.getElementById('planned-chat-messages')?.innerHTML;

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
      .replace(/\n\n/g, '<div class="my-2 border-t border-slate-200"></div>')
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
          <div class="p-2 rounded-lg bg-white border border-slate-200 text-center font-mono shadow-2xs">
            <span class="text-[10px] text-slate-500 block">${z}</span>
            <span class="text-xs font-bold text-slate-900">${mins}m</span>
          </div>
        `;
      }).join('');

      zonesHtml = `
        <div class="mt-4 pt-4 border-t border-slate-200">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-600 block mb-2">Distribución Estimada por Zonas</span>
          <div class="grid grid-cols-5 gap-2">
            ${zPills}
          </div>
        </div>
      `;
    }
  }

  const chartHtml = renderPlannedWorkoutChart(ev);

  content.innerHTML = `
    <!-- Header -->
    <div class="flex items-start justify-between pb-4 mb-4 border-b border-slate-200">
      <div>
        <div class="flex items-center gap-2 mb-1.5 flex-wrap">
          ${getSportBadge(ev.sport_type, 'md')}
          <h2 class="text-lg font-bold text-slate-900">${ev.name}</h2>
          <span class="px-2.5 py-0.5 rounded-full text-[10px] font-medium border ${badgeColor}">
            ${badgeText}
          </span>
        </div>
        <div class="flex items-center gap-2 text-xs text-slate-500 font-mono">
          <span>📅 ${ev.date || 'Esta semana'}</span>
          ${ev.start_time ? `<span>• ${ev.start_time.substring(11, 16) || ''}</span>` : ''}
        </div>
      </div>
    </div>

    <!-- Quick Metrics Grid -->
    ${!isNote ? `
      <div class="grid grid-cols-3 gap-3 mb-5">
        <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
          <span class="text-xs text-slate-500 mb-0.5">Tiempo Estimado</span>
          <span class="text-base font-bold font-mono text-slate-900">${durMins > 0 ? durHours : 'Libre'}</span>
        </div>
        <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
          <span class="text-xs text-slate-500 mb-0.5">Distancia</span>
          <span class="text-base font-bold font-mono text-[#0284c7]">${distKm || 'N/A'}</span>
        </div>
        <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col shadow-2xs">
          <span class="text-xs text-slate-500 mb-0.5">Carga Prevista</span>
          <span class="text-base font-bold font-mono text-amber-600">${ev.planned_load ? ev.planned_load + ' TSS' : 'N/A'}</span>
        </div>
      </div>
    ` : ''}

    <!-- Description & Intervals.icu Workout Instructions -->
    <div class="p-4 sm:p-5 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-200">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
          <span>📝</span> Descripción del Entrenamiento (Intervals.icu)
        </h3>
        <span class="text-[10px] text-slate-500 font-mono">ID: ${ev.id}</span>
      </div>

      <div class="text-xs font-mono leading-relaxed text-slate-800 bg-white p-3.5 rounded-lg border border-slate-200 max-h-80 overflow-y-auto whitespace-pre-wrap selection:bg-amber-500 selection:text-white shadow-2xs">
${descHtml}
      </div>

      ${chartHtml ? '' : zonesHtml}
    </div>

    <!-- Intervals.icu Planned Workout Stepped Chart & Zones -->
    ${chartHtml}

    <!-- Interactive Planned Workout Chatbot -->
    <div class="p-4 sm:p-5 rounded-xl bg-slate-50 border border-slate-200 shadow-xs mt-5">
      <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-200">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center font-bold text-sm">
            💬
          </div>
          <div>
            <h4 class="text-xs font-bold text-slate-900">Consulta con tu Entrenador sobre esta sesión planificada</h4>
            <p class="text-[10px] text-slate-500">Pregúntale cómo calentar, a qué vatios/ritmo hacer las series o qué estrategia de hidratación y nutrición seguir.</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-mono px-2 py-0.5 rounded ${state.athleteStatus?.ai?.has_key ? 'bg-purple-50 text-purple-700 border border-purple-200' : 'bg-white text-slate-600 border border-slate-200'}">
            ${state.athleteStatus?.ai?.has_key ? '🤖 Gemini Coach IA' : '🧠 Motor Experto Triatlón'}
          </span>
        </div>
      </div>

      <!-- Quick prompts for planned workout -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        <button type="button" onclick="setPlannedPrompt('${ev.id}', '¿Cómo estructuro el calentamiento óptimo para esta sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-amber-800 border border-slate-200 transition-colors shadow-2xs">
          Calentamiento óptimo
        </button>
        <button type="button" onclick="setPlannedPrompt('${ev.id}', '¿A qué vatios o ritmo exacto debo hacer las partes principales?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-amber-800 border border-slate-200 transition-colors shadow-2xs">
          Vatios / Ritmos de series
        </button>
        <button type="button" onclick="setPlannedPrompt('${ev.id}', '¿Qué pauta de hidratación y nutrición debo llevar durante la sesión?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-amber-800 border border-slate-200 transition-colors shadow-2xs">
          Nutrición e Hidratación
        </button>
        <button type="button" onclick="setPlannedPrompt('${ev.id}', 'Si noto fatiga acumulada en las piernas, ¿cómo adapto o recorto el volumen?')"
          class="px-2.5 py-1 rounded-full text-[11px] bg-white hover:bg-slate-100 text-amber-800 border border-slate-200 transition-colors shadow-2xs">
          Adaptar por fatiga
        </button>
      </div>

      <!-- Chat history messages container -->
      <div id="planned-chat-messages" class="space-y-3 max-h-64 overflow-y-auto mb-3 p-3 rounded-xl bg-white border border-slate-200 shadow-2xs">
        <!-- Rendered by renderPlannedChatMessages -->
      </div>

      <!-- Chat input form -->
      <form id="form-planned-chat" onsubmit="event.preventDefault(); submitPlannedChatMessage('${ev.id}');" class="flex gap-2">
        <input 
          type="text" 
          id="input-planned-chat"
          placeholder="Haz cualquier pregunta al entrenador sobre esta sesión..." 
          class="flex-1 bg-white border border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-amber-500 transition-colors"
        />
        <button 
          type="submit" 
          id="btn-planned-chat-submit"
          class="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-semibold rounded-xl text-xs transition-all shadow-sm flex items-center gap-1.5"
        >
          <span>Preguntar</span>
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
        </button>
      </form>
    </div>

    <!-- Footer Actions -->
    <div class="mt-5 pt-3 border-t border-slate-200 flex items-center justify-between flex-wrap gap-2 text-xs">
      <a href="https://intervals.icu/events/${ev.id}" target="_blank" rel="noopener"
         class="text-amber-700 hover:text-amber-800 font-semibold flex items-center gap-1 hover:underline">
        <span>Abrir en Intervals.icu</span>
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
      </a>

      <button type="button" onclick="closePlannedModal(); switchTab('form');"
        class="px-3.5 py-1.5 rounded-lg bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200 font-semibold transition-colors flex items-center gap-1.5 shadow-2xs">
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
        <div class="w-6 h-6 rounded-md bg-amber-100 border border-amber-200 flex items-center justify-center text-amber-700 shrink-0 font-bold text-[10px]">
          Coach
        </div>
      ` : ''}
      <div class="max-w-[85%] rounded-xl p-2.5 text-xs leading-relaxed ${
        isUser 
          ? 'bg-amber-500 text-white rounded-tr-none shadow-2xs' 
          : 'bg-slate-100 border border-slate-200 text-slate-800 rounded-tl-none prose prose-sm'
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
      <div class="w-6 h-6 rounded-md bg-amber-100 border border-amber-200 flex items-center justify-center text-amber-700 shrink-0 font-bold text-[10px]">
        Coach
      </div>
      <div class="bg-slate-100 border border-slate-200 rounded-xl rounded-tl-none p-2.5 flex items-center gap-1.5">
        <span class="w-1.5 h-1.5 rounded-full bg-amber-600 animate-bounce"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-amber-600 animate-bounce" style="animation-delay: 0.15s"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-amber-600 animate-bounce" style="animation-delay: 0.3s"></span>
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
async function loadPMC(days, forceRefresh = false) {
  state.pmcDays = days;
  try {
    const url = `/api/pmc?days=${days}` + (forceRefresh ? '&refresh=true' : '');
    const res = await fetch(url);
    const data = await res.json();
    state.pmcData = data;

    // Update Form Status Cards
    document.getElementById('pmc-ctl-val').textContent = data.current_ctl;
    document.getElementById('pmc-atl-val').textContent = data.current_atl;
    const tsbEl = document.getElementById('pmc-tsb-val');
    if (tsbEl) {
      const sign = data.current_tsb > 0 ? '+' : '';
      tsbEl.textContent = sign + data.current_tsb;
      const zone = window.getTSBZone ? window.getTSBZone(data.current_tsb) : null;
      if (zone) {
        tsbEl.style.color = zone.color;
        tsbEl.className = 'text-2xl font-bold font-mono';
        tsbEl.title = `Zona TSB: ${zone.name}`;
      } else {
        tsbEl.className = data.current_tsb >= 0 ? 'text-2xl font-bold font-mono text-emerald-600' : 'text-2xl font-bold font-mono text-amber-600';
      }
    }
    document.getElementById('pmc-acwr-val').textContent = data.acwr;

    // Render Canvas
    renderPMCChart('pmcChart', data.series);

    // Also load weekly volume chart (last 10 weeks)
    loadWeeklyVolume(forceRefresh);
  } catch (err) {
    console.error('Error loading PMC:', err);
  }
}

async function loadWeeklyVolume(forceRefresh = false) {
  try {
    const res = await fetch('/api/volume/history?weeks=10' + (forceRefresh ? '&refresh=true' : ''));
    const data = await res.json();
    state.volumeHistoryData = data;
    if (window.renderWeeklyVolumeChart) {
      window.renderWeeklyVolumeChart('weeklyVolumeChart', data);
    }
  } catch (err) {
    console.error('Error loading weekly volume:', err);
  }
}

async function loadHealthLoadHistory(days = 90, forceRefresh = false) {
  state.healthDays = days;
  try {
    const url = `/api/health-load/history?days=${days}` + (forceRefresh ? '&refresh=true' : '');
    const res = await fetch(url);
    const data = await res.json();
    state.healthLoadData = data;

    if (window.renderHealthLoadChart && data.series) {
      window.renderHealthLoadChart('healthLoadChart', data.series);
    }
    if (data.semaphore) {
      renderHealthSemaphore(data.semaphore);
    }
  } catch (err) {
    console.error('Error loading health & load history:', err);
  }
}

function renderHealthSemaphore(sem) {
  const container = document.getElementById('health-semaphore-container');
  if (!container || !sem) return;

  const isGreen = sem.color === 'green';
  const isYellow = sem.color === 'yellow';
  const isRed = sem.color === 'red';
  const m = sem.metrics || {};
  const t = sem.triggers || {};

  const bannerStyle = isRed
    ? 'bg-rose-50 border-rose-300 text-rose-900'
    : (isYellow
        ? 'bg-amber-50 border-amber-300 text-amber-900'
        : 'bg-emerald-50 border-emerald-300 text-emerald-900');

  const deltaSign = (m.rhr_delta || 0) > 0 ? '+' : '';

  container.innerHTML = `
    <!-- Active Traffic Light Banner -->
    <div class="p-4 rounded-xl border ${bannerStyle} shadow-2xs mb-4">
      <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div class="flex items-center gap-4">
          <!-- Traffic Light Housing (Semáforo Visual) -->
          <div class="flex items-center gap-2 px-3 py-2 rounded-full bg-slate-900 border border-slate-700 shadow-inner shrink-0">
            <span class="w-4 h-4 rounded-full transition-all ${isRed ? 'bg-rose-500 shadow-[0_0_12px_#f43f5e] scale-110 ring-2 ring-rose-300' : 'bg-rose-950/60 opacity-35'}" title="Rojo: Riesgo sobreentrenamiento"></span>
            <span class="w-4 h-4 rounded-full transition-all ${isYellow ? 'bg-amber-400 shadow-[0_0_12px_#fbbf24] scale-110 ring-2 ring-amber-200' : 'bg-amber-950/60 opacity-35'}" title="Amarillo: Fatiga aguda"></span>
            <span class="w-4 h-4 rounded-full transition-all ${isGreen ? 'bg-emerald-400 shadow-[0_0_12px_#34d399] scale-110 ring-2 ring-emerald-200' : 'bg-emerald-950/60 opacity-35'}" title="Verde: Estado óptimo"></span>
          </div>

          <div>
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-white/80 border border-current/20 font-bold">
                Semáforo de Estado Actual
              </span>
              <h4 class="text-sm sm:text-base font-bold">${sem.label}</h4>
            </div>
            <p class="text-xs mt-1 font-medium opacity-90">${sem.recommendation}</p>
          </div>
        </div>

        <!-- Live Biomarker Snapshot Pills -->
        <div class="flex flex-wrap items-center gap-2 text-[11px] font-mono">
          <div class="px-2.5 py-1 rounded-lg bg-white/90 border border-slate-200 text-slate-800 shadow-2xs">
            <span class="text-slate-500">TSS 48h:</span> <strong>${m.tss_48h ?? '--'}</strong>
          </div>
          <div class="px-2.5 py-1 rounded-lg bg-white/90 border border-slate-200 text-slate-800 shadow-2xs">
            <span class="text-slate-500">VFC:</span> <strong class="text-[#0284c7]">${m.hrv_current ?? '--'} ms</strong> <span class="text-[10px] text-emerald-700">(${m.hrv_baseline_low}-${m.hrv_baseline_high})</span>
          </div>
          <div class="px-2.5 py-1 rounded-lg bg-white/90 border border-slate-200 text-slate-800 shadow-2xs">
            <span class="text-slate-500">FCR:</span> <strong class="text-rose-600">${m.rhr_current ?? '--'} ppm</strong> <span class="text-[10px] text-slate-500">(${deltaSign}${m.rhr_delta ?? 0} vs base ${m.rhr_baseline})</span>
          </div>
          <div class="px-2.5 py-1 rounded-lg bg-white/90 border border-slate-200 text-slate-800 shadow-2xs">
            <span class="text-slate-500">Sueño:</span> <strong class="text-indigo-600">${m.latest_sleep_hours ? m.latest_sleep_hours.toFixed(1) + 'h' : '--'}</strong>
          </div>
        </div>
      </div>
    </div>

    <!-- Reference Criteria Grid: Amarillo vs Rojo -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
      <!-- AMARILLO CRITERIA CARD -->
      <div class="p-4 rounded-xl border ${isYellow ? 'bg-amber-50/90 border-amber-400 ring-1 ring-amber-400/50' : 'bg-amber-50/30 border-amber-200/80'}">
        <div class="flex items-center justify-between pb-2 mb-2.5 border-b border-amber-200/80">
          <div class="flex items-center gap-2">
            <span class="w-3 h-3 rounded-full bg-amber-400 shadow-xs"></span>
            <h5 class="font-bold text-amber-950 uppercase tracking-wide text-xs">Amarillo • Fatiga Aguda</h5>
          </div>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded ${isYellow ? 'bg-amber-200 text-amber-950 font-bold' : 'bg-white text-amber-800 border border-amber-200'}">
            ${isYellow ? '● Estado Activo' : 'Criterios de Control'}
          </span>
        </div>
        <ul class="space-y-1.5 text-slate-700 mb-3">
          <li class="flex items-start gap-2">
            <span class="${t.yellow_tss_48h ? 'text-amber-600 font-bold' : 'text-slate-400'}">${t.yellow_tss_48h ? '⚠' : '•'}</span>
            <span class="${t.yellow_tss_48h ? 'font-semibold text-amber-950' : ''}">TSS alto últimas 48h <span class="text-[10px] font-mono text-slate-500">(Actual: ${m.tss_48h ?? 0} TSS)</span></span>
          </li>
          <li class="flex items-start gap-2">
            <span class="${t.yellow_hrv ? 'text-amber-600 font-bold' : 'text-slate-400'}">${t.yellow_hrv ? '⚠' : '•'}</span>
            <span class="${t.yellow_hrv ? 'font-semibold text-amber-950' : ''}">VFC cae por debajo del rango normal durante 2 días seguidos o sube de forma anormalmente alta <span class="text-[10px] font-mono text-slate-500">(${m.hrv_current ?? '--'} ms vs ${m.hrv_baseline_low}-${m.hrv_baseline_high} ms)</span></span>
          </li>
          <li class="flex items-start gap-2">
            <span class="${t.yellow_rhr ? 'text-amber-600 font-bold' : 'text-slate-400'}">${t.yellow_rhr ? '⚠' : '•'}</span>
            <span class="${t.yellow_rhr ? 'font-semibold text-amber-950' : ''}">FCR sube +2 o +4 sobre la base <span class="text-[10px] font-mono text-slate-500">(${deltaSign}${m.rhr_delta ?? 0} ppm sobre ${m.rhr_baseline} ppm)</span></span>
          </li>
        </ul>
        <div class="p-2.5 rounded-lg bg-amber-100/70 border border-amber-200 text-amber-950 font-semibold text-[11px]">
          Pauta: Fatiga aguda, modular carga y sustituir intensidad por rodajes.
        </div>
      </div>

      <!-- ROJO CRITERIA CARD -->
      <div class="p-4 rounded-xl border ${isRed ? 'bg-rose-50/90 border-rose-400 ring-1 ring-rose-400/50' : 'bg-rose-50/30 border-rose-200/80'}">
        <div class="flex items-center justify-between pb-2 mb-2.5 border-b border-rose-200/80">
          <div class="flex items-center gap-2">
            <span class="w-3 h-3 rounded-full bg-rose-500 shadow-xs"></span>
            <h5 class="font-bold text-rose-950 uppercase tracking-wide text-xs">Rojo • Riesgo Sobreentrenamiento / Enfermedad</h5>
          </div>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded ${isRed ? 'bg-rose-200 text-rose-950 font-bold' : 'bg-white text-rose-800 border border-rose-200'}">
            ${isRed ? '● Estado Activo' : 'Criterios de Alerta'}
          </span>
        </div>
        <ul class="space-y-1.5 text-slate-700 mb-3">
          <li class="flex items-start gap-2">
            <span class="${t.red_tss_accum ? 'text-rose-600 font-bold' : 'text-slate-400'}">${t.red_tss_accum ? '🚨' : '•'}</span>
            <span class="${t.red_tss_accum ? 'font-semibold text-rose-950' : ''}">TSS alto acumulado <span class="text-[10px] font-mono text-slate-500">(7d: ${m.tss_7d ?? 0} TSS • TSB: ${m.tsb ?? 0})</span></span>
          </li>
          <li class="flex items-start gap-2">
            <span class="${t.red_hrv ? 'text-rose-600 font-bold' : 'text-slate-400'}">${t.red_hrv ? '🚨' : '•'}</span>
            <span class="${t.red_hrv ? 'font-semibold text-rose-950' : ''}">VFC caída brusca y sostenida durante más de 3 días por debajo del rango habitual <span class="text-[10px] font-mono text-slate-500">(${m.consecutive_low_hrv_days ?? 0} días seguidos bajo rango)</span></span>
          </li>
          <li class="flex items-start gap-2">
            <span class="${t.red_rhr ? 'text-rose-600 font-bold' : 'text-slate-400'}">${t.red_rhr ? '🚨' : '•'}</span>
            <span class="${t.red_rhr ? 'font-semibold text-rose-950' : ''}">FCR sube de forma persistente +5 sobre la base <span class="text-[10px] font-mono text-slate-500">(${deltaSign}${m.rhr_delta ?? 0} ppm vs base)</span></span>
          </li>
        </ul>
        <div class="p-2.5 rounded-lg bg-rose-100/70 border border-rose-200 text-rose-950 font-semibold text-[11px]">
          Pauta: Riesgo de sobreentrenamiento o incubación de enfermedad. Descanso o movilidad 24-48h.
        </div>
      </div>
    </div>
  `;
}

// Page 3: Pruebas (Tests & Competiciones)
async function loadTestsPage(forceRefresh = false) {
  try {
    if (!state.testsData || forceRefresh) {
      const resTests = await fetch('/api/seasons/tests?t=' + Date.now(), { cache: 'no-store' });
      state.testsData = await resTests.json();
    }
    if (!state.competitionsData || forceRefresh) {
      const resComps = await fetch('/api/seasons/competitions?t=' + Date.now(), { cache: 'no-store' });
      state.competitionsData = await resComps.json();
    }

    setupSeasonControls();
    renderSeasonView(state.selectedSeason);
  } catch (err) {
    console.error('Error loading tests page:', err);
  }
}

function setupSeasonControls() {
  const select = document.getElementById('season-select');
  const btnPrev = document.getElementById('btn-prev-season');
  const btnNext = document.getElementById('btn-next-season');
  if (!select) return;

  const seasons = (state.testsData && state.testsData.seasons) || [
    "Temporada 2027 (Actual)",
    "Temporada 2026",
    "Temporada 2025",
    "Temporada 2024",
    "Temporada 2023",
    "Temporada 2022"
  ];

  select.value = state.selectedSeason;
  select.onchange = (e) => {
    state.selectedSeason = e.target.value;
    renderSeasonView(state.selectedSeason);
  };

  if (btnPrev) {
    btnPrev.onclick = () => {
      const currIdx = seasons.indexOf(state.selectedSeason);
      if (currIdx < seasons.length - 1) {
        state.selectedSeason = seasons[currIdx + 1];
        select.value = state.selectedSeason;
        renderSeasonView(state.selectedSeason);
      }
    };
  }

  if (btnNext) {
    btnNext.onclick = () => {
      const currIdx = seasons.indexOf(state.selectedSeason);
      if (currIdx > 0) {
        state.selectedSeason = seasons[currIdx - 1];
        select.value = state.selectedSeason;
        renderSeasonView(state.selectedSeason);
      }
    };
  }
}

function renderSeasonView(seasonKey) {
  const seasons = (state.testsData && state.testsData.seasons) || [];
  const currIdx = seasons.indexOf(seasonKey);
  const btnPrev = document.getElementById('btn-prev-season');
  const btnNext = document.getElementById('btn-next-season');
  if (btnPrev) btnPrev.disabled = (currIdx >= seasons.length - 1);
  if (btnNext) btnNext.disabled = (currIdx <= 0);

  const titleEl = document.getElementById('season-title-display');
  const badgeEl = document.getElementById('season-badge-display');
  const subtitleEl = document.getElementById('tests-subtitle-display');
  if (titleEl) titleEl.textContent = seasonKey;

  const isCurrent = seasonKey.includes('Actual') || seasonKey.includes('2027');
  if (badgeEl) {
    if (isCurrent) {
      badgeEl.className = 'px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200';
      badgeEl.textContent = 'En Curso';
    } else {
      badgeEl.className = 'px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200';
      badgeEl.textContent = 'Finalizada';
    }
  }

  if (subtitleEl) {
    subtitleEl.textContent = isCurrent 
      ? 'Control fisiológico de la temporada actual por periodos (inicial vs base1).'
      : 'Los 3 mejores valores registrados en Intervals.icu en Ciclismo y Carrera a pie.';
  }

  renderTestsSection(seasonKey);
  renderCompetitionsSection(seasonKey);
}

function renderTestsSection(seasonKey) {
  const container = document.getElementById('tests-tables-container');
  if (!container) return;

  const allTests = (state.testsData && state.testsData.tests) || {};
  const seasonTests = allTests[seasonKey] || allTests['Temporada 2027 (Actual)'] || {};
  const isCurrent = seasonTests.is_current !== false && (seasonKey.includes('Actual') || seasonKey.includes('2027'));

  const swim = seasonTests.swimming || {};
  const bike = seasonTests.cycling || seasonTests.cycling_bests || {};
  const run = seasonTests.running || seasonTests.running_bests || {};

  const swimSectionHtml = (swim.rows && swim.rows.length > 0) ? `
    <!-- 1. NATACIÓN -->
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          ${getSportBadge('swimming', 'md')}
          <h4 class="text-xs sm:text-sm font-bold text-slate-900">Natación • Tests de Control 400m y 200m</h4>
        </div>
        <span class="text-[11px] font-mono text-slate-500">CSS Referencia: 1:29.0/100m</span>
      </div>

      <div class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 text-[11px]">
            <tr>
              <th class="px-3.5 py-2.5">Periodo</th>
              <th class="px-3.5 py-2.5">Fecha</th>
              <th class="px-3.5 py-2.5">Distancia</th>
              <th class="px-3.5 py-2.5">Tiempo Total</th>
              <th class="px-3.5 py-2.5">Tiempos de cada 100m</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 text-slate-800">
            ${(swim.rows || []).map(r => `
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 py-2.5 font-semibold">
                  <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${r.periodo === 'inicial' ? 'bg-amber-100 text-amber-800 border border-amber-200' : 'bg-sky-100 text-[#0284c7] border border-sky-200'}">
                    ${r.periodo}
                  </span>
                </td>
                <td class="px-3.5 py-2.5 font-mono text-slate-600">${r.fecha}</td>
                <td class="px-3.5 py-2.5 font-bold text-slate-900">${r.distancia}</td>
                <td class="px-3.5 py-2.5 font-mono font-bold text-sky-600 text-sm">${r.tiempo_total}</td>
                <td class="px-3.5 py-2.5 font-mono text-slate-700 text-[11px]">${r.splits_100m}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  ` : '';

  const html = `
    ${swimSectionHtml}

    <!-- 2. CICLISMO -->
    <div class="space-y-3 ${swimSectionHtml ? 'pt-2' : ''}">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          ${getSportBadge('cycling', 'md')}
          <h4 class="text-xs sm:text-sm font-bold text-slate-900">${isCurrent ? "Ciclismo • Test de Potencia Aeróbica Máxima (PAM 5')" : "Ciclismo • 3 Mejores Valores (5', 10' y 20')"}</h4>
        </div>
        <span class="text-[11px] font-mono text-slate-500">${isCurrent ? 'FTP: 348 W' : 'Datos de la actividad (Intervals.icu)'}</span>
      </div>

      <div class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 text-[11px]">
            <tr>
              <th class="px-3.5 py-2.5">Periodo</th>
              <th class="px-3.5 py-2.5">Fecha</th>
              <th class="px-3.5 py-2.5">Tiempo</th>
              <th class="px-3.5 py-2.5">Potencia Media</th>
              <th class="px-3.5 py-2.5">FC Media</th>
              <th class="px-3.5 py-2.5">FC Máx</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 text-slate-800">
            ${(bike.rows || []).map(r => `
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 py-2.5 font-semibold">
                  <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${r.periodo === 'inicial' ? 'bg-amber-100 text-amber-800 border border-amber-200' : 'bg-sky-100 text-[#0284c7] border border-sky-200'}">
                    ${r.periodo || r.duracion || '-'}
                  </span>
                </td>
                <td class="px-3.5 py-2.5 font-mono text-slate-600">${r.fecha || '-'}</td>
                <td class="px-3.5 py-2.5 font-bold text-slate-900">${r.tiempo || r.duracion || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono font-bold text-amber-600 text-sm">${r.potencia_media || r.potencia || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono text-rose-600 font-semibold">${r.fc_media || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono text-rose-700 font-bold">${r.fc_max || '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3. CARRERA A PIE -->
    <div class="space-y-3 pt-2">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          ${getSportBadge('running', 'md')}
          <h4 class="text-xs sm:text-sm font-bold text-slate-900">${isCurrent ? 'Carrera a Pie • Test 5k' : 'Carrera a Pie • 3 Mejores Ritmos (5k, 10k y 21k)'}</h4>
        </div>
        <span class="text-[11px] font-mono text-slate-500">${isCurrent ? 'Ritmo Umbral: 3:40 min/km' : 'Datos de la actividad (Intervals.icu)'}</span>
      </div>

      <div class="overflow-x-auto rounded-xl border border-slate-200">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 text-[11px]">
            <tr>
              <th class="px-3.5 py-2.5">Periodo</th>
              <th class="px-3.5 py-2.5">Fecha</th>
              <th class="px-3.5 py-2.5">Distancia</th>
              <th class="px-3.5 py-2.5">Desnivel Positivo</th>
              <th class="px-3.5 py-2.5">Tiempo</th>
              <th class="px-3.5 py-2.5">Ritmo</th>
              <th class="px-3.5 py-2.5">FC Media</th>
              <th class="px-3.5 py-2.5">FC Máx</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 text-slate-800">
            ${(run.rows || []).map(r => `
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3.5 py-2.5 font-semibold">
                  <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-100 text-[#0284c7] border border-sky-200">
                    ${r.periodo || r.actividad || r.distancia || '-'}
                  </span>
                </td>
                <td class="px-3.5 py-2.5 font-mono text-slate-600">${r.fecha || '-'}</td>
                <td class="px-3.5 py-2.5 font-bold text-slate-900">${r.distancia || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono text-slate-600">${r.desnivel_pos || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono font-bold text-emerald-600 text-sm">${r.tiempo || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono font-bold text-emerald-700">${r.ritmo || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono text-rose-600 font-semibold">${r.fc_media || '-'}</td>
                <td class="px-3.5 py-2.5 font-mono text-rose-700 font-bold">${r.fc_max || '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
  container.innerHTML = html;
}

function renderCompetitionsSection(seasonKey) {
  const container = document.getElementById('competitions-table-container');
  if (!container) return;

  const compsData = (state.competitionsData && state.competitionsData.competitions) || {};
  const list = compsData[seasonKey] || [];

  if (!list.length) {
    container.innerHTML = `
      <div class="p-8 text-center bg-slate-50 border border-slate-200 rounded-xl text-slate-500 text-xs">
        <p class="font-semibold text-slate-700 mb-1">No hay competiciones registradas en esta temporada.</p>
        <p class="text-[11px] text-slate-400">Puedes consultar temporadas anteriores mediante el selector superior.</p>
      </div>
    `;
    return;
  }

  let html = `
    <div class="overflow-x-auto rounded-xl border border-slate-200 shadow-2xs">
      <table class="w-full text-left text-xs whitespace-nowrap">
        <thead class="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 text-[11px]">
          <tr>
            <th class="px-3 py-2.5 sticky left-0 bg-slate-50 z-10">Nombre Competición</th>
            <th class="px-3 py-2.5">Fecha</th>
            <th class="px-3 py-2.5">Distancia</th>
            <th class="px-3 py-2.5 font-bold text-slate-900">Tiempo Total</th>
            <th class="px-3 py-2.5 text-sky-700 bg-sky-50/50">T. Natación</th>
            <th class="px-3 py-2.5 text-sky-700 bg-sky-50/50">Ritmo Natación</th>
            <th class="px-3 py-2.5">T1</th>
            <th class="px-3 py-2.5 text-amber-700 bg-amber-50/50">T. Bici</th>
            <th class="px-3 py-2.5 text-amber-700 bg-amber-50/50">Potencia Media Bici</th>
            <th class="px-3 py-2.5 text-amber-700 bg-amber-50/50">FC Media Bici</th>
            <th class="px-3 py-2.5 text-amber-700 bg-amber-50/50">FC Máx Bici</th>
            <th class="px-3 py-2.5 text-emerald-700 bg-emerald-50/50">T. Carrera</th>
            <th class="px-3 py-2.5 text-emerald-700 bg-emerald-50/50">Ritmo Carrera</th>
            <th class="px-3 py-2.5 text-emerald-700 bg-emerald-50/50">FC Media Carrera</th>
            <th class="px-3 py-2.5 text-emerald-700 bg-emerald-50/50">FC Máx Carrera</th>
            <th class="px-3 py-2.5 bg-yellow-50/60 font-bold text-slate-900">Posición Clasificación</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-200 text-slate-800">
          ${list.map(c => {
            const isRunOnly = c.modalidad === 'Carrera a pie';
            return `
              <tr class="hover:bg-slate-50/80 transition-colors">
                <td class="px-3 py-2.5 font-semibold text-slate-900 sticky left-0 bg-white z-10 shadow-xs">
                  <div class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full ${isRunOnly ? 'bg-emerald-500' : 'bg-[#0284c7]'}"></span>
                    <span>${c.nombre}</span>
                  </div>
                  <span class="text-[10px] text-slate-400 font-normal block pl-3.5">${c.modalidad}</span>
                </td>
                <td class="px-3 py-2.5 font-mono text-slate-600 text-[11px]">${c.fecha}</td>
                <td class="px-3 py-2.5 font-semibold text-slate-700">${c.distancia}</td>
                <td class="px-3 py-2.5 font-mono font-bold text-slate-900 text-sm">${c.tiempo_total}</td>
                
                <!-- Natación -->
                <td class="px-3 py-2.5 font-mono ${c.tiempo_natacion !== '-' ? 'text-sky-700 font-semibold' : 'text-slate-400'} bg-sky-50/30">${c.tiempo_natacion}</td>
                <td class="px-3 py-2.5 font-mono ${c.ritmo_natacion !== '-' ? 'text-sky-800' : 'text-slate-400'} bg-sky-50/30 text-[11px]">${c.ritmo_natacion}</td>
                
                <!-- Transición 1 -->
                <td class="px-3 py-2.5 font-mono text-slate-600">${c.tiempo_t1}</td>
                
                <!-- Ciclismo -->
                <td class="px-3 py-2.5 font-mono ${c.tiempo_bici !== '-' ? 'text-amber-700 font-semibold' : 'text-slate-400'} bg-amber-50/30">${c.tiempo_bici}</td>
                <td class="px-3 py-2.5 font-mono font-bold ${c.potencia_media_bici !== '-' ? 'text-amber-700' : 'text-slate-400'} bg-amber-50/30">${c.potencia_media_bici}</td>
                <td class="px-3 py-2.5 font-mono text-slate-600 bg-amber-50/30">${c.fcmedia_bici}</td>
                <td class="px-3 py-2.5 font-mono text-slate-600 bg-amber-50/30">${c.fcmax_bici}</td>
                
                <!-- Carrera -->
                <td class="px-3 py-2.5 font-mono ${c.tiempo_carrera !== '-' ? 'text-emerald-700 font-semibold' : 'text-slate-400'} bg-emerald-50/30">${c.tiempo_carrera}</td>
                <td class="px-3 py-2.5 font-mono font-bold ${c.ritmo_carrera !== '-' ? 'text-emerald-800' : 'text-slate-400'} bg-emerald-50/30">${c.ritmo_carrera}</td>
                <td class="px-3 py-2.5 font-mono text-slate-600 bg-emerald-50/30">${c.fcmedia_carrera}</td>
                <td class="px-3 py-2.5 font-mono text-slate-600 bg-emerald-50/30">${c.fcmax_carrera}</td>
                
                <!-- Clasificación -->
                <td class="px-3 py-2.5 bg-yellow-50/40">
                  ${c.posicion && c.posicion !== '-' ? `
                    <span class="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-800">
                      <span class="text-amber-600 inline-flex items-center">${getTrophyIcon('xs')}</span>
                      <span>${c.posicion}</span>
                    </span>
                  ` : `<span class="font-mono text-slate-400">-</span>`}
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
  container.innerHTML = html;
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
      <div class="w-8 h-8 rounded-full bg-purple-100 border border-purple-200 flex items-center justify-center text-purple-700 shrink-0 font-bold text-xs">
        Coach
      </div>
    ` : ''}
    <div class="max-w-[85%] rounded-2xl p-3.5 text-xs leading-relaxed ${
      isUser 
        ? 'bg-[#0284c7] text-white rounded-tr-none shadow-xs' 
        : 'bg-slate-100 border border-slate-200 text-slate-800 rounded-tl-none prose prose-sm'
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
    <div class="w-8 h-8 rounded-full bg-purple-100 border border-purple-200 flex items-center justify-center text-purple-700 shrink-0 font-bold text-xs">
      Coach
    </div>
    <div class="bg-slate-100 border border-slate-200 rounded-2xl rounded-tl-none p-3.5 flex items-center gap-1.5">
      <span class="w-2 h-2 rounded-full bg-purple-600 animate-bounce"></span>
      <span class="w-2 h-2 rounded-full bg-purple-600 animate-bounce" style="animation-delay: 0.15s"></span>
      <span class="w-2 h-2 rounded-full bg-purple-600 animate-bounce" style="animation-delay: 0.3s"></span>
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
        geminiBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-slate-200 text-slate-700 border border-slate-300';
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
      syncInfo = `<div class="text-[10px] text-emerald-700 font-mono flex items-center justify-between mb-2">
        <span>Última sincronización: ${t.last_sync}</span>
        ${t.weight ? `<span class="text-slate-500">Peso: <strong class="text-slate-800">${t.weight} kg</strong></span>` : ''}
      </div>`;
    }

    let pzHtml = '';
    const bike = t.disciplines?.cycling;
    if (bike?.power_zones?.length) {
      const zPills = bike.power_zones.map(z => 
        `<div class="flex items-center justify-between py-0.5 px-1 rounded bg-white border border-slate-200 font-mono text-[10px]">
          <span class="text-slate-600">${z.name}</span>
          <span class="text-[#0284c7] font-bold">${z.min_watts}-${z.max_watts > 800 ? '+' : z.max_watts}W</span>
        </div>`
      ).join('');
      pzHtml = `
        <div class="mt-2">
          <span class="text-[10px] font-bold text-slate-700 uppercase tracking-wider block mb-1">Zonas de Potencia Ciclismo (Intervals)</span>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-1">${zPills}</div>
        </div>
      `;
    }

    let hrHtml = '';
    const run = t.disciplines?.running;
    if (run?.hr_zones?.length) {
      const zList = run.hr_zones.map((val, idx) => `Z${idx+1}: <${val}bpm`).join(' • ');
      hrHtml = `
        <div class="mt-2 text-[10px] font-mono text-slate-600">
          <span class="text-slate-700 font-bold uppercase">Zonas FC Carrera:</span> ${zList}
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
  loadStatus();
  await loadWeek(state.weekOffset, true);
  if (state.currentTab === 'form') {
    await loadPMC(state.pmcDays, true);
    await loadHealthLoadHistory(state.healthDays, true);
    await loadWeeklyVolume(true);
  } else if (state.currentTab === 'tests') {
    await loadTestsPage(true);
  }
  if (btn) btn.classList.remove('animate-spin');
}

// Helpers & Sport Presentation (Minimalist Frameless Icons)
function getTrophyIcon(size = 'sm') {
  const dim = size === 'lg' ? 'w-6 h-6' : (size === 'md' ? 'w-5 h-5' : (size === 'xs' ? 'w-3.5 h-3.5' : 'w-4 h-4'));
  return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>`;
}
window.getTrophyIcon = getTrophyIcon;

function getSportIcon(type, size = 'sm') {
  const t = (type || '').toLowerCase();
  const dim = size === 'lg' ? 'w-6 h-6' : (size === 'md' ? 'w-5 h-5' : 'w-4 h-4');

  if (t === 'swimming') {
    // Minimalist Swimmer (Nadador)
    return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="16.5" cy="6.5" r="2"/><path d="M6 12.5 11 8.5l4 2.5-2 3.5"/><path d="M2 17c1.5 0 2.5-1.5 4-1.5s2.5 1.5 4 1.5 2.5-1.5 4-1.5 2.5 1.5 4 1.5 2.5-1.5 4-1.5"/><path d="M2 20.5c1.5 0 2.5-1.5 4-1.5s2.5 1.5 4 1.5 2.5-1.5 4-1.5 2.5 1.5 4 1.5 2.5-1.5 4-1.5"/></svg>`;
  }
  if (t === 'cycling') {
    // Minimalist Bicycle (Bicicleta)
    return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="18.5" cy="17.5" r="3.5"/><path d="M5.5 17.5 9.5 10h5.5l-3 7.5H5.5Z"/><path d="M12 17.5 9.5 10 8 7.5H6"/><path d="M18.5 17.5 15 10l1-2.5h2.5"/></svg>`;
  }
  if (t === 'running') {
    // Minimalist Running Shoe (Zapatilla de correr)
    return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17.5h18v1.5a1.5 1.5 0 0 1-1.5 1.5H4A1.5 1.5 0 0 1 2.5 19v-3.2c0-1.4.9-2.6 2.2-3L8 11.5l2.5-4.5 2.5 1 2 3.5c2.5.8 4.8 2 6 4v2Z"/><path d="m10.5 10.5 1.8 1.2"/><path d="m12.5 12.2 1.8 1.2"/><path d="M2.5 17.5h19"/></svg>`;
  }
  if (t === 'strength') {
    // Minimalist Dumbbell (Mancuerna)
    return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m6.5 6.5 11 11"/><path d="m3 10 7-7"/><path d="m14 21 7-7"/><path d="m2 6 4-4"/><path d="m18 22 4-4"/></svg>`;
  }
  if (t === 'other' || t === 'note') {
    return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>`;
  }
  return `<svg class="${dim} inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>`;
}

function getSportBadge(type, size = 'sm') {
  const t = (type || '').toLowerCase();
  const icon = getSportIcon(t, size);
  let colorClass = 'text-slate-600';
  if (t === 'swimming') colorClass = 'text-[#00a8cc]';
  else if (t === 'cycling') colorClass = 'text-[#d97706]';
  else if (t === 'running') colorClass = 'text-[#059669]';
  else if (t === 'strength') colorClass = 'text-[#7c3aed]';

  return `<span class="inline-flex items-center justify-center ${colorClass} shrink-0">${icon}</span>`;
}

function getSportBorderLeftClass(type) {
  const t = (type || '').toLowerCase();
  if (t === 'swimming') return 'border-l-[3.5px] border-l-[#00a8cc]';
  if (t === 'cycling') return 'border-l-[3.5px] border-l-[#d97706]';
  if (t === 'running') return 'border-l-[3.5px] border-l-[#059669]';
  if (t === 'strength') return 'border-l-[3.5px] border-l-[#7c3aed]';
  return 'border-l-[3.5px] border-l-slate-300';
}

function formatCoachReport(text) {
  if (!text) return '';
  // Basic markdown conversion for bold and lists
  let formatted = text
    .replace(/^### (.*$)/gim, '<h4 class="font-bold text-slate-900 text-xs mt-3 mb-1">$1</h4>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');
  return formatted;
}
