/**
 * Charting engine for Triathlon Performance & Health Platform.
 * Builds and updates the PMC curve (CTL/ATL/TSB) and zone distribution graphs.
 */

let pmcChartInstance = null;
let workoutSplitsChartInstance = null;
let weeklyVolumeChartInstance = null;
let healthLoadChartInstance = null;

// ==========================================
// Shared Interactive Floating HTML Tooltip (with top-right ✕ button)
// for all charts in the Progresión tab (PMC, Health/Load, Weekly Volume)
// ==========================================
let _progTooltipEl = null;
let _progTooltipChart = null;
let _progTooltipPinned = false;
let _progTooltipAllowUpdate = false;
let _progTooltipDismissedUntilLeave = false;

function getOrCreateProgressionTooltip() {
  if (!_progTooltipEl) {
    const el = document.createElement('div');
    el.id = 'progression-chart-tooltip';
    el.style.position = 'absolute';
    el.style.zIndex = '9999';
    el.style.display = 'none';
    el.style.opacity = '0';
    el.style.transition = 'opacity 120ms ease';
    el.style.maxWidth = '320px';
    el.style.minWidth = '210px';
    el.className = 'bg-slate-900/95 text-slate-100 border border-slate-700 rounded-xl shadow-2xl backdrop-blur-md p-3 text-xs';
    document.body.appendChild(el);

    // Close when clicking outside the tooltip and outside any progression chart canvas
    document.addEventListener('click', (evt) => {
      if (!_progTooltipEl || _progTooltipEl.style.display === 'none') return;
      if (evt.target.closest('#progression-chart-tooltip')) return;
      if (evt.target.closest('#pmcChart, #healthLoadChart, #weeklyVolumeChart')) return;
      closeProgressionTooltip();
    });

    _progTooltipEl = el;
  }
  return _progTooltipEl;
}

function closeProgressionTooltip(evt) {
  if (evt) {
    evt.stopPropagation();
    evt.preventDefault();
  }
  _progTooltipPinned = false;
  _progTooltipAllowUpdate = false;
  _progTooltipDismissedUntilLeave = true;

  if (_progTooltipEl) {
    _progTooltipEl.style.opacity = '0';
    _progTooltipEl.style.display = 'none';
    _progTooltipEl.style.pointerEvents = 'none';
  }

  if (_progTooltipChart) {
    try {
      _progTooltipChart.setActiveElements([]);
      if (_progTooltipChart.tooltip && _progTooltipChart.tooltip.setActiveElements) {
        _progTooltipChart.tooltip.setActiveElements([], { x: 0, y: 0 });
      }
      _progTooltipChart.update('none');
    } catch (e) {
      // ignore if chart already destroyed
    }
    _progTooltipChart = null;
  }
}
window.closeProgressionTooltip = closeProgressionTooltip;

function handleProgressionChartClick(event, elements, chart) {
  if (!chart) return;
  _progTooltipDismissedUntilLeave = false;
  _progTooltipAllowUpdate = true;
  _progTooltipPinned = true;
  _progTooltipChart = chart;

  if (elements && elements.length > 0) {
    const targetIdx = elements[0].index;
    const activeEls = [];
    (chart.data.datasets || []).forEach((ds, dsIdx) => {
      if (chart.isDatasetVisible(dsIdx)) {
        activeEls.push({ datasetIndex: dsIdx, index: targetIdx });
      }
    });
    chart.setActiveElements(activeEls);
    if (chart.tooltip && chart.tooltip.setActiveElements) {
      chart.tooltip.setActiveElements(activeEls, { x: event.x, y: event.y });
    }
    chart.update('none');
  } else if (chart.tooltip) {
    progressionChartExternalTooltip({ chart, tooltip: chart.tooltip });
  }
  _progTooltipAllowUpdate = false;
}

function progressionChartExternalTooltip(context) {
  const { chart, tooltip } = context;
  const tooltipEl = getOrCreateProgressionTooltip();

  // If user just clicked ✕, ignore lingering hover events until pointer leaves or user clicks a new day
  if (_progTooltipDismissedUntilLeave && !_progTooltipAllowUpdate) {
    if (tooltip.opacity === 0) {
      _progTooltipDismissedUntilLeave = false;
    }
    return;
  }

  // If pinned on a clicked day, keep the card locked on that day so user can click ✕ cleanly
  if (_progTooltipPinned && !_progTooltipAllowUpdate) {
    return;
  }

  // Hide if no tooltip
  if (!tooltip || tooltip.opacity === 0) {
    if (!_progTooltipPinned) {
      tooltipEl.style.opacity = '0';
      tooltipEl.style.display = 'none';
      tooltipEl.style.pointerEvents = 'none';
    }
    return;
  }

  _progTooltipChart = chart;

  // Build HTML content preserving Chart.js callbacks (title, body, labelColors, afterBody)
  const titleLines = tooltip.title || [];
  const bodyLines = (tooltip.body || []).map(b => b.lines);
  const afterBodyLines = tooltip.afterBody || [];
  const labelColors = tooltip.labelColors || [];

  const titleHtml = titleLines.map(t => `<div class="font-bold text-white text-[12px] leading-snug pr-1">${t}</div>`).join('');

  const bodyHtml = bodyLines.map((lines, i) => {
    const colors = labelColors[i] || {};
    const swatchColor = colors.backgroundColor || colors.borderColor || '#38bdf8';
    const borderColor = colors.borderColor || swatchColor;
    const isSolidColor = typeof swatchColor === 'string' && !swatchColor.startsWith('Canvas');
    const swatchHtml = isSolidColor
      ? `<span class="w-2.5 h-2.5 rounded-xs shrink-0 mt-0.5 inline-block" style="background-color:${swatchColor}; border: 1px solid ${typeof borderColor === 'string' ? borderColor : swatchColor};"></span>`
      : '';
    return lines.map(line => `
      <div class="flex items-start gap-2 text-[11px] font-mono text-slate-200 leading-snug">
        ${swatchHtml}
        <span>${line}</span>
      </div>
    `).join('');
  }).join('');

  const afterBodyHtml = afterBodyLines.length > 0
    ? `<div class="mt-2 pt-1.5 border-t border-slate-700/80 space-y-0.5">
        ${afterBodyLines.map(line => `<div class="text-[11px] font-mono text-indigo-300 font-semibold">${line}</div>`).join('')}
       </div>`
    : '';

  tooltipEl.innerHTML = `
    <div class="flex items-start justify-between gap-2 pb-2 mb-2 border-b border-slate-700/80">
      <div class="min-w-0 flex-1">${titleHtml}</div>
      <button type="button"
              id="btn-close-progression-tooltip"
              aria-label="Cerrar ventana"
              title="Cerrar"
              class="w-6 h-6 -mt-1 -mr-1 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-700/90 active:bg-slate-600 transition-colors cursor-pointer shrink-0">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    </div>
    <div class="space-y-1">
      ${bodyHtml}
    </div>
    ${afterBodyHtml}
  `;

  const closeBtn = tooltipEl.querySelector('#btn-close-progression-tooltip');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeProgressionTooltip);
    closeBtn.addEventListener('touchend', closeProgressionTooltip, { passive: false });
  }

  tooltipEl.style.display = 'block';
  tooltipEl.style.pointerEvents = 'auto';
  tooltipEl.style.opacity = '1';

  // Position cleanly near the tapped/hovered point, clamped within viewport width
  const rect = chart.canvas.getBoundingClientRect();
  const caretX = tooltip.caretX || (rect.width / 2);
  const caretY = tooltip.caretY || (rect.height / 2);

  const tipW = tooltipEl.offsetWidth || 250;
  const tipH = tooltipEl.offsetHeight || 120;

  let left = rect.left + window.scrollX + caretX + 12;
  let top = rect.top + window.scrollY + caretY - tipH - 12;

  // Keep horizontally inside visible screen
  const maxLeft = window.scrollX + window.innerWidth - tipW - 10;
  const minLeft = window.scrollX + 10;
  if (left > maxLeft) {
    left = rect.left + window.scrollX + caretX - tipW - 12;
  }
  if (left < minLeft) left = minLeft;
  if (left > maxLeft) left = maxLeft;

  // If too high above top of viewport, place below the caret instead
  const minTop = window.scrollY + 10;
  if (top < minTop) {
    top = rect.top + window.scrollY + caretY + 14;
  }

  tooltipEl.style.left = `${Math.round(left)}px`;
  tooltipEl.style.top = `${Math.round(top)}px`;
}

/**
 * Helper to determine TSB zone classification, name and color.
 * Follows Joe Friel / TrainingPeaks / Intervals.icu standards:
 * - < -30: Fatiga Crítica / Alto Riesgo (Rose/Red #f43f5e)
 * - -30 a -10: Sobrecarga Productiva (Amber #f59e0b)
 * - -10 a +10: Neutro / Mantenimiento (Slate #94a3b8)
 * - +10 a +25: Pico de Forma / Frescura (Emerald #10b981)
 * - > +25: Transición / Desentrenamiento (Purple #a855f7)
 */
function getTSBZone(val) {
  if (val === null || val === undefined || isNaN(val)) {
    return { name: 'Desconocido', color: '#94a3b8', bgClass: 'bg-slate-400', textClass: 'text-slate-600' };
  }
  if (val < -30) {
    return { name: 'Fatiga Crítica', color: '#f43f5e', bgClass: 'bg-rose-500', textClass: 'text-rose-600' };
  }
  if (val < -10) {
    return { name: 'Sobrecarga Productiva', color: '#f59e0b', bgClass: 'bg-amber-500', textClass: 'text-amber-600' };
  }
  if (val <= 10) {
    return { name: 'Neutro', color: '#94a3b8', bgClass: 'bg-slate-400', textClass: 'text-slate-600' };
  }
  if (val <= 25) {
    return { name: 'Pico de Forma', color: '#10b981', bgClass: 'bg-emerald-500', textClass: 'text-emerald-600' };
  }
  return { name: 'Transición', color: '#a855f7', bgClass: 'bg-purple-500', textClass: 'text-purple-600' };
}
window.getTSBZone = getTSBZone;

function renderPMCChart(canvasId, seriesData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (pmcChartInstance) {
    closeProgressionTooltip();
    pmcChartInstance.destroy();
  }

  const labels = seriesData.map(d => d.date);
  const ctlValues = seriesData.map(d => d.ctl);
  const atlValues = seriesData.map(d => d.atl);
  const tsbValues = seriesData.map(d => d.tsb);

  pmcChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Forma / Fitness (CTL)',
          data: ctlValues,
          borderColor: '#0284c7', // TrainingPeaks Blue
          backgroundColor: 'rgba(2, 132, 199, 0.12)',
          fill: true,
          borderWidth: 2.5,
          pointRadius: seriesData.length > 60 ? 0 : 2,
          pointHoverRadius: 5,
          tension: 0.3,
          yAxisID: 'y'
        },
        {
          label: 'Fatiga (ATL)',
          data: atlValues,
          borderColor: '#ec4899', // TrainingPeaks Magenta
          backgroundColor: 'rgba(236, 72, 153, 0.05)',
          fill: false,
          borderWidth: 2,
          pointRadius: seriesData.length > 60 ? 0 : 2,
          pointHoverRadius: 5,
          tension: 0.3,
          yAxisID: 'y'
        },
        {
          label: 'Frescura / Balance (TSB)',
          data: tsbValues,
          borderColor: '#f59e0b', // Fallback base color
          borderWidth: 2.5,
          pointRadius: seriesData.length > 90 ? 0 : 2,
          pointHoverRadius: 6,
          pointBackgroundColor: function(context) {
            const val = context.raw;
            return getTSBZone(val).color;
          },
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          tension: 0.25,
          yAxisID: 'y1',
          segment: {
            borderColor: function(ctx) {
              if (!ctx.p0 || !ctx.p1) return '#94a3b8';
              const v0 = ctx.p0.parsed.y;
              const v1 = ctx.p1.parsed.y;
              const c0 = getTSBZone(v0).color;
              const c1 = getTSBZone(v1).color;
              if (c0 === c1) return c0;

              const chartCtx = ctx.chart.ctx;
              const gradient = chartCtx.createLinearGradient(ctx.p0.x, ctx.p0.y, ctx.p1.x, ctx.p1.y);
              gradient.addColorStop(0, c0);
              gradient.addColorStop(1, c1);
              return gradient;
            }
          }
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: handleProgressionChartClick,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: '#475569',
            font: { family: 'Inter, sans-serif', size: 12, weight: 600 },
            usePointStyle: true,
            boxWidth: 8
          }
        },
        tooltip: {
          enabled: false,
          external: progressionChartExternalTooltip,
          callbacks: {
            label: function(context) {
              const label = context.dataset.label || '';
              const val = context.parsed.y;
              if (context.datasetIndex === 2) {
                const zone = getTSBZone(val);
                const sign = val > 0 ? '+' : '';
                return `${label}: ${sign}${val} (${zone.name})`;
              }
              return `${label}: ${val}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(0, 0, 0, 0.06)' },
          ticks: {
            color: '#64748b',
            maxTicksLimit: 10,
            font: { family: 'Inter, sans-serif', size: 11 }
          }
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(0, 0, 0, 0.06)' },
          title: {
            display: true,
            text: 'Carga (CTL / ATL)',
            color: '#475569',
            font: { family: 'Inter, sans-serif', size: 11, weight: 600 }
          },
          ticks: { color: '#64748b', font: { family: 'Inter, sans-serif' } }
        },
        y1: {
          position: 'right',
          grid: {
            drawOnChartArea: true,
            color: function(context) {
              if (context.tick && context.tick.value === 0) {
                return 'rgba(100, 116, 139, 0.4)';
              }
              return 'rgba(0, 0, 0, 0.03)';
            },
            lineWidth: function(context) {
              return (context.tick && context.tick.value === 0) ? 1.5 : 1;
            }
          },
          title: {
            display: true,
            text: 'TSB (Balance)',
            color: '#d97706',
            font: { family: 'Inter, sans-serif', size: 11, weight: 600 }
          },
          ticks: { color: '#d97706', font: { family: 'Inter, sans-serif' } }
        }
      }
    }
  });
}

const INTERVALS_ZONE_COLORS = {
  1: '#009e80', // Z1 Recuperación Activa (Teal)
  2: '#009e00', // Z2 Fondo Aeróbico (Green)
  3: '#ffcb0e', // Z3 Tempo (Yellow)
  4: '#ff7f0e', // Z4 Umbral Anaeróbico / Threshold (Orange)
  5: '#dd0447', // Z5 VO2 Máx (Crimson)
  6: '#6633cc', // Z6 Capacidad Anaeróbica (Purple)
  7: '#504861'  // Z7 Neuromuscular / Sprint (Deep Violet)
};

function getLapZoneInfo(sportType, s, ftp = 348) {
  const th = (window.state && window.state.athleteStatus && window.state.athleteStatus.thresholds) || {};
  const disc = th.disciplines || {};

  if (sportType === 'cycling') {
    const bikeCfg = disc.cycling || {};
    const liveFtp = bikeCfg.ftp || th.ftp || ftp || 348;
    const pcts = Array.isArray(bikeCfg.power_zone_pcts) && bikeCfg.power_zone_pcts.length >= 7
      ? bikeCfg.power_zone_pcts
      : [55, 75, 90, 105, 120, 150, 999];
    const pwr = s.avg_power || s.normalised_power || 0;
    const pct = liveFtp > 0 ? (pwr / liveFtp) * 100 : 0;
    const names = [
      'Z1 Recuperación Activa',
      'Z2 Fondo Aeróbico',
      'Z3 Tempo',
      'Z4 Umbral',
      'Z5 VO2 Máx',
      'Z6 Capacidad Anaeróbica',
      'Z7 Neuromuscular / Sprint'
    ];
    let z = 7;
    for (let i = 0; i < 7; i++) {
      if (pct <= pcts[i]) {
        z = i + 1;
        break;
      }
    }
    return { zone: z, name: names[z - 1], color: INTERVALS_ZONE_COLORS[z] };
  }

  if (sportType === 'running') {
    const runCfg = disc.running || {};
    const runTp = runCfg.threshold_speed_mps || 4.5455;
    const pcts = Array.isArray(runCfg.pace_zone_pcts) && runCfg.pace_zone_pcts.length >= 7
      ? runCfg.pace_zone_pcts
      : [77.5, 87.7, 94.3, 100.0, 103.4, 111.5, 999.0];
    const spd = s.avg_speed_mps || 0;
    const pct = (spd > 0 && runTp > 0) ? (spd / runTp) * 100 : 0;
    const names = [
      'Z1 Recuperación Activa',
      'Z2 Fondo Aeróbico',
      'Z3 Tempo',
      'Z4 Umbral',
      'Z5 VO2 Máx',
      'Z6 Capacidad Anaeróbica',
      'Z7 Neuromuscular / Sprint'
    ];
    let z = 7;
    for (let i = 0; i < 7; i++) {
      if (pct <= pcts[i]) {
        z = i + 1;
        break;
      }
    }
    return { zone: z, name: names[z - 1], color: INTERVALS_ZONE_COLORS[z] };
  }

  if (sportType === 'swimming') {
    const swimCfg = disc.swimming || {};
    const swimTp = swimCfg.threshold_speed_mps || 1.1236;
    const pcts = Array.isArray(swimCfg.pace_zone_pcts) && swimCfg.pace_zone_pcts.length >= 7
      ? swimCfg.pace_zone_pcts
      : [77.5, 87.7, 94.3, 100.0, 103.4, 111.5, 999.0];
    const spd = s.avg_speed_mps || 0;
    const pct = (spd > 0 && swimTp > 0) ? (spd / swimTp) * 100 : 0;
    const names = [
      'Z1 Suave / Técnica',
      'Z2 Fondo Aeróbico',
      'Z3 Tempo',
      'Z4 CSS Umbral',
      'Z5 VO2 Máx',
      'Z6 Capacidad Anaeróbica',
      'Z7 Sprint / All-Out'
    ];
    let z = 7;
    for (let i = 0; i < 7; i++) {
      if (pct <= pcts[i]) {
        z = i + 1;
        break;
      }
    }
    return { zone: z, name: names[z - 1], color: INTERVALS_ZONE_COLORS[z] };
  }

  return { zone: 2, name: 'Z2', color: '#0284c7' };
}
window.getLapZoneInfo = getLapZoneInfo;

function renderWorkoutSplitsChart(canvasId, splits, sportType) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !splits || splits.length === 0) return;

  if (workoutSplitsChartInstance) {
    workoutSplitsChartInstance.destroy();
  }

  const isCycling = sportType === 'cycling';
  const isRunning = sportType === 'running';
  const isSwim = sportType === 'swimming';

  const ftp = (window.state && window.state.athleteStatus && window.state.athleteStatus.thresholds && window.state.athleteStatus.thresholds.ftp) || 348;

  const labels = splits.map((s, idx) => {
    const lapNum = s.lap_index || (idx + 1);
    const durSec = s.duration_seconds || 0;
    const durM = Math.floor(durSec / 60);
    const durS = Math.round(durSec % 60);
    return `L${lapNum} (${durM}:${durS.toString().padStart(2, '0')})`;
  });

  const hrValues = splits.map(s => s.avg_heart_rate ? Math.round(s.avg_heart_rate) : null);

  let outputValues = [];
  let yAxisLabel = '';
  let yAxisColor = '#00A3E0';

  if (isCycling) {
    outputValues = splits.map(s => s.avg_power ? Math.round(s.avg_power) : (s.normalised_power ? Math.round(s.normalised_power) : 0));
    yAxisLabel = 'Potencia Media (W)';
    yAxisColor = '#f59e0b';
  } else if (isRunning) {
    outputValues = splits.map(s => s.avg_speed_mps && s.avg_speed_mps > 0 ? Math.round(1000 / s.avg_speed_mps) : null);
    yAxisLabel = 'Ritmo Medio (min/km)';
    yAxisColor = '#059669';
  } else if (isSwim) {
    outputValues = splits.map(s => s.avg_speed_mps && s.avg_speed_mps > 0 ? Math.round(100 / s.avg_speed_mps) : null);
    yAxisLabel = 'Ritmo Medio (min/100m)';
    yAxisColor = '#00a8cc';
  } else {
    outputValues = splits.map(s => s.avg_speed_mps ? Math.round(s.avg_speed_mps * 60) : 0);
    yAxisLabel = 'Velocidad';
  }

  // Calculate zone and individual color for each lap
  const zoneInfoList = splits.map(s => getLapZoneInfo(sportType, s, ftp));
  const barColors = zoneInfoList.map(z => z.color);

  const validOutputs = outputValues.filter(v => v !== null && v > 0);
  const minOut = validOutputs.length ? Math.min(...validOutputs) : 0;
  const maxOut = validOutputs.length ? Math.max(...validOutputs) : 100;

  // Build datasets:
  // - Cycling & Running: Bars colored by training zone + Line with Heart Rate
  // - Swimming: ONLY the average pace bars colored by training zone (no HR line)
  const datasets = [
    {
      label: yAxisLabel,
      data: outputValues,
      backgroundColor: barColors,
      borderColor: barColors,
      borderWidth: 1.5,
      borderRadius: 4,
      yAxisID: 'y'
    }
  ];

  if (!isSwim) {
    datasets.push({
      label: 'FC Media (ppm)',
      data: hrValues,
      type: 'line',
      borderColor: '#ef4444',
      backgroundColor: 'rgba(239, 68, 68, 0.1)',
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.25,
      yAxisID: 'y1'
    });
  }

  const scalesConfig = {
    x: {
      grid: { color: 'rgba(0, 0, 0, 0.05)' },
      ticks: { color: '#64748b', font: { family: 'Inter, sans-serif', size: 10 } }
    },
    y: {
      position: 'left',
      reverse: isRunning || isSwim,
      min: (isRunning || isSwim) ? Math.max(0, minOut - 15) : undefined,
      max: (isRunning || isSwim) ? maxOut + 15 : undefined,
      grid: { color: 'rgba(0, 0, 0, 0.05)' },
      ticks: {
        color: yAxisColor,
        font: { family: 'Inter, sans-serif', size: 10 },
        callback: function(val) {
          if (isCycling) return `${val} W`;
          if (isRunning) {
            const m = Math.floor(val / 60);
            const s = Math.round(val % 60);
            return `${m}:${s.toString().padStart(2, '0')}/km`;
          }
          if (isSwim) {
            const m = Math.floor(val / 60);
            const s = Math.round(val % 60);
            return `${m}:${s.toString().padStart(2, '0')}`;
          }
          return val;
        }
      },
      title: {
        display: true,
        text: yAxisLabel,
        color: yAxisColor,
        font: { family: 'Inter, sans-serif', size: 10, weight: 600 }
      }
    }
  };

  if (!isSwim) {
    scalesConfig.y1 = {
      position: 'right',
      grid: { drawOnChartArea: false },
      ticks: {
        color: '#ef4444',
        font: { family: 'Inter, sans-serif', size: 10 },
        callback: function(val) {
          return `${val} ppm`;
        }
      },
      title: {
        display: true,
        text: 'FC (ppm)',
        color: '#ef4444',
        font: { family: 'Inter, sans-serif', size: 10, weight: 600 }
      }
    };
  }

  workoutSplitsChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#475569', font: { family: 'Inter, sans-serif', size: 11, weight: 600 }, usePointStyle: true, boxWidth: 6 }
        },
        tooltip: {
          backgroundColor: '#1e293b',
          titleColor: '#ffffff',
          bodyColor: '#e2e8f0',
          borderColor: '#475569',
          borderWidth: 1,
          padding: 10,
          titleFont: { family: 'Inter, sans-serif', weight: 600 },
          bodyFont: { family: 'Inter, sans-serif' },
          callbacks: {
            label: function(context) {
              if (context.dataset.yAxisID === 'y1') {
                return `❤️ FC Media: ${context.parsed.y} ppm`;
              }
              const idx = context.dataIndex;
              const zInfo = zoneInfoList[idx];
              const zTag = zInfo ? ` • ${zInfo.name}` : '';
              const val = context.parsed.y;
              if (isCycling) {
                return `⚡ Potencia: ${val} W${zTag}`;
              } else if (isRunning) {
                const m = Math.floor(val / 60);
                const s = Math.round(val % 60);
                return `🏃 Ritmo: ${m}:${s.toString().padStart(2, '0')}/km${zTag}`;
              } else if (isSwim) {
                const m = Math.floor(val / 60);
                const s = Math.round(val % 60);
                return `🏊 Ritmo: ${m}:${s.toString().padStart(2, '0')}/100m${zTag}`;
              }
              return `${context.dataset.label}: ${val}${zTag}`;
            }
          }
        }
      },
      scales: scalesConfig
    }
  });
}

function renderWeeklyVolumeChart(canvasId, volumeData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !volumeData || !volumeData.labels) return;

  if (weeklyVolumeChartInstance) {
    closeProgressionTooltip();
    weeklyVolumeChartInstance.destroy();
  }

  const weeks = volumeData.weeks || [];

  weeklyVolumeChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: volumeData.labels,
      datasets: [
        {
          label: 'Horas Planificadas',
          data: volumeData.planned,
          backgroundColor: 'rgba(2, 132, 199, 0.25)',
          borderColor: '#0284c7',
          borderWidth: 2,
          borderRadius: 6,
          barPercentage: 0.85,
          categoryPercentage: 0.8,
        },
        {
          label: 'Horas Reales',
          data: volumeData.actual,
          backgroundColor: weeks.map(w => w.is_current ? 'rgba(5, 150, 105, 0.75)' : '#059669'),
          borderColor: '#047857',
          borderWidth: 1.5,
          borderRadius: 6,
          barPercentage: 0.85,
          categoryPercentage: 0.8,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: handleProgressionChartClick,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          display: false // Shown in custom header badges
        },
        tooltip: {
          enabled: false,
          external: progressionChartExternalTooltip,
          callbacks: {
            title: function(items) {
              if (!items || !items.length) return '';
              const idx = items[0].dataIndex;
              const w = weeks[idx];
              return `${items[0].label} (${w ? w.date_range : ''})${w && w.is_current ? ' • Semana en curso' : ''}`;
            },
            label: function(ctx) {
              const val = ctx.parsed.y;
              if (ctx.datasetIndex === 0) {
                return `⏱️ Planificado: ${val.toFixed(1)} h`;
              } else {
                const idx = ctx.dataIndex;
                const w = weeks[idx];
                const pct = w ? w.completion_percent : 0;
                return `✅ Real: ${val.toFixed(1)} h (${pct}% cumplimiento)`;
              }
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: '#64748b',
            font: { family: 'Inter, sans-serif', size: 11, weight: 600 }
          }
        },
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(226, 232, 240, 0.8)',
            borderDash: [3, 3]
          },
          ticks: {
            color: '#64748b',
            font: { family: 'JetBrains Mono, monospace', size: 11 },
            callback: function(v) { return v + ' h'; }
          },
          title: {
            display: true,
            text: 'Horas Semanales',
            color: '#64748b',
            font: { family: 'Inter, sans-serif', size: 11, weight: 600 }
          }
        }
      }
    }
  });
}
window.renderWeeklyVolumeChart = renderWeeklyVolumeChart;

function renderHealthLoadChart(canvasId, seriesData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !Array.isArray(seriesData) || seriesData.length === 0) return;

  if (healthLoadChartInstance) {
    closeProgressionTooltip();
    healthLoadChartInstance.destroy();
  }

  const labels = seriesData.map(d => d.label || d.date.slice(5));
  const showPoints = seriesData.length <= 65;

  const zoneDefs = [
    { key: 'Z1', label: 'TSS Z1', color: '#009e80' },
    { key: 'Z2', label: 'TSS Z2', color: '#009e00' },
    { key: 'Z3', label: 'TSS Z3', color: '#ffcb0e' },
    { key: 'Z4', label: 'TSS Z4', color: '#ff7f0e' },
    { key: 'Z5', label: 'TSS Z5', color: '#dd0447' },
    { key: 'Z6', label: 'TSS Z6', color: '#6633cc' },
    { key: 'Z7', label: 'TSS Z7', color: '#504861' },
    { key: 'strength', label: 'TSS Fuerza', color: '#111827' }
  ];

  // Stacked TSS Bar Datasets (Left Y-Axis)
  const barDatasets = zoneDefs.map(z => ({
    type: 'bar',
    label: z.label,
    data: seriesData.map(d => (d.tss_zones && d.tss_zones[z.key]) ? d.tss_zones[z.key] : 0),
    backgroundColor: z.color,
    borderColor: z.color,
    borderWidth: 0,
    stack: 'daily_tss',
    yAxisID: 'y',
    order: 3,
    barPercentage: 0.78,
    categoryPercentage: 0.85
  }));

  // Right Y-Axis Datasets:
  // 1. Garmin Personal Normal Range Upper & Lower (shaded very light green between them)
  const hrvUpperDataset = {
    type: 'line',
    label: 'Rango Normal VFC (Máx)',
    data: seriesData.map(d => d.hrv_baseline_high),
    borderColor: 'rgba(16, 185, 129, 0.28)',
    backgroundColor: 'rgba(16, 185, 129, 0.14)',
    borderWidth: 1,
    borderDash: [3, 3],
    pointRadius: 0,
    pointHoverRadius: 0,
    fill: '+1', // Fills area down to hrvLowerDataset
    tension: 0.25,
    yAxisID: 'y1',
    order: 2
  };

  const hrvLowerDataset = {
    type: 'line',
    label: 'Rango Normal VFC (Mín)',
    data: seriesData.map(d => d.hrv_baseline_low),
    borderColor: 'rgba(16, 185, 129, 0.28)',
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderDash: [3, 3],
    pointRadius: 0,
    pointHoverRadius: 0,
    fill: false,
    tension: 0.25,
    yAxisID: 'y1',
    order: 2
  };

  // 2. VFC (HRV) Line in Blue
  const hrvLineDataset = {
    type: 'line',
    label: 'VFC Nocturna (ms)',
    data: seriesData.map(d => d.hrv),
    borderColor: '#0284c7',
    backgroundColor: '#0284c7',
    borderWidth: 2.4,
    pointRadius: showPoints ? 2.5 : 0,
    pointHoverRadius: 5,
    pointBackgroundColor: function(context) {
      const idx = context.dataIndex;
      const d = seriesData[idx];
      if (!d || d.hrv === null) return '#0284c7';
      if (d.hrv < d.hrv_baseline_low) return '#f59e0b';
      return '#0284c7';
    },
    spanGaps: true,
    tension: 0.25,
    yAxisID: 'y1',
    order: 1
  };

  // 3. FC Reposo (RHR) Line in Red
  const rhrLineDataset = {
    type: 'line',
    label: 'FC Reposo (ppm)',
    data: seriesData.map(d => d.rhr),
    borderColor: '#ef4444',
    backgroundColor: '#ef4444',
    borderWidth: 2.2,
    pointRadius: showPoints ? 2.2 : 0,
    pointHoverRadius: 5,
    spanGaps: true,
    tension: 0.25,
    yAxisID: 'y1',
    order: 1
  };

  healthLoadChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        ...barDatasets,
        hrvUpperDataset,
        hrvLowerDataset,
        hrvLineDataset,
        rhrLineDataset
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: handleProgressionChartClick,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: false // Shown in custom compact header legend
        },
        tooltip: {
          enabled: false,
          external: progressionChartExternalTooltip,
          filter: function(item) {
            // Only show non-zero TSS zones and main HRV/RHR lines (hide helper baseline lines)
            if (item.dataset.label.startsWith('Rango Normal VFC')) return false;
            if (item.dataset.stack === 'daily_tss' && (!item.parsed.y || item.parsed.y <= 0.1)) return false;
            return true;
          },
          callbacks: {
            title: function(items) {
              if (!items || !items.length) return '';
              const d = seriesData[items[0].dataIndex];
              if (!d) return items[0].label;
              const sleepTxt = d.sleep_hours !== null && d.sleep_hours !== undefined ? `${d.sleep_hours.toFixed(1)} h` : '--';
              return `${d.date}  •  TSS Total: ${d.total_tss}  •  Sueño: ${sleepTxt}`;
            },
            label: function(context) {
              const idx = context.dataIndex;
              const d = seriesData[idx];
              const lbl = context.dataset.label || '';
              const val = context.parsed.y;
              if (lbl === 'VFC Nocturna (ms)') {
                const rangeStr = d ? ` (Rango Garmin: ${d.hrv_baseline_low}-${d.hrv_baseline_high} ms)` : '';
                return `💙 VFC: ${val !== null ? Math.round(val) + ' ms' : '--'}${rangeStr}`;
              }
              if (lbl === 'FC Reposo (ppm)') {
                return `❤️ FC Reposo: ${val !== null ? val + ' ppm' : '--'}`;
              }
              const pct = (d && d.total_tss > 0) ? Math.round((val / d.total_tss) * 100) : 0;
              return `▪ ${lbl}: ${val.toFixed(1)} TSS (${pct}%)`;
            },
            afterBody: function(items) {
              if (!items || !items.length) return [];
              const d = seriesData[items[0].dataIndex];
              if (!d) return [];
              const sleepStr = d.sleep_hours !== null && d.sleep_hours !== undefined
                ? `☾ Horas de Sueño: ${d.sleep_hours.toFixed(1)} h${d.sleep_score ? ` (Score: ${d.sleep_score})` : ''}`
                : '☾ Horas de Sueño: --';
              return [sleepStr];
            }
          }
        }
      },
      scales: {
        x: {
          stacked: true,
          grid: { color: 'rgba(0, 0, 0, 0.04)' },
          ticks: {
            color: '#475569',
            maxTicksLimit: seriesData.length <= 35 ? 35 : (seriesData.length <= 65 ? 20 : 14),
            font: { family: 'Inter, sans-serif', size: 10, weight: 600 }
          }
        },
        xSleep: {
          position: 'bottom',
          offset: true,
          grid: { display: false, drawTicks: false },
          border: { display: false },
          ticks: {
            color: function(ctx) {
              const d = seriesData[ctx.index];
              if (!d || !d.sleep_hours) return '#94a3b8';
              if (d.sleep_hours < 6.5) return '#d97706';
              return '#4f46e5';
            },
            maxTicksLimit: seriesData.length <= 35 ? 35 : (seriesData.length <= 65 ? 20 : 14),
            font: { family: 'JetBrains Mono, monospace', size: 9.5, weight: 600 },
            callback: function(val, index) {
              const d = seriesData[index];
              if (!d || d.sleep_hours === null || d.sleep_hours === undefined) return '-';
              return `${d.sleep_hours.toFixed(1)}h`;
            }
          },
          title: {
            display: true,
            text: '☾ Horas de Sueño Diarias',
            color: '#6366f1',
            font: { family: 'Inter, sans-serif', size: 10, weight: 600 },
            padding: { top: 2 }
          }
        },
        y: {
          stacked: true,
          position: 'left',
          beginAtZero: true,
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
          title: {
            display: true,
            text: 'Carga Diaria (TSS por Zonas)',
            color: '#334155',
            font: { family: 'Inter, sans-serif', size: 11, weight: 600 }
          },
          ticks: {
            color: '#475569',
            font: { family: 'JetBrains Mono, monospace', size: 10 }
          }
        },
        y1: {
          position: 'right',
          min: 25,
          suggestedMax: 145,
          grid: { drawOnChartArea: false },
          title: {
            display: true,
            text: 'VFC (ms) / FC Reposo (ppm)',
            color: '#0284c7',
            font: { family: 'Inter, sans-serif', size: 11, weight: 600 }
          },
          ticks: {
            color: '#0284c7',
            font: { family: 'JetBrains Mono, monospace', size: 10 }
          }
        }
      }
    }
  });
}
window.renderHealthLoadChart = renderHealthLoadChart;
