/**
 * Charting engine for Triathlon Performance & Health Platform.
 * Builds and updates the PMC curve (CTL/ATL/TSB) and zone distribution graphs.
 */

let pmcChartInstance = null;
let workoutSplitsChartInstance = null;
let weeklyVolumeChartInstance = null;
let healthLoadChartInstance = null;

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
          backgroundColor: '#1e293b',
          titleColor: '#ffffff',
          bodyColor: '#e2e8f0',
          borderColor: '#475569',
          borderWidth: 1,
          padding: 12,
          bodyFont: { family: 'Inter, sans-serif' },
          titleFont: { family: 'Inter, sans-serif', weight: 600 },
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
  if (sportType === 'cycling') {
    const pwr = s.avg_power || s.normalised_power || 0;
    const pct = (pwr / ftp) * 100;
    let z = 1, name = 'Z1 Recuperación Activa';
    if (pct < 56) { z = 1; name = 'Z1 Recuperación Activa'; }
    else if (pct < 76) { z = 2; name = 'Z2 Fondo Aeróbico'; }
    else if (pct < 91) { z = 3; name = 'Z3 Tempo'; }
    else if (pct < 106) { z = 4; name = 'Z4 Umbral'; }
    else if (pct < 121) { z = 5; name = 'Z5 VO2 Máx'; }
    else if (pct < 151) { z = 6; name = 'Z6 Capacidad Anaeróbica'; }
    else { z = 7; name = 'Z7 Neuromuscular / Sprint'; }
    return { zone: z, name, color: INTERVALS_ZONE_COLORS[z] };
  }

  if (sportType === 'running') {
    const secKm = (s.avg_speed_mps && s.avg_speed_mps > 0) ? (1000 / s.avg_speed_mps) : 0;
    let z = 1, name = 'Z1 Recuperación Activa';
    if (secKm > 285) { z = 1; name = 'Z1 Recuperación Activa'; }
    else if (secKm >= 251) { z = 2; name = 'Z2 Fondo Aeróbico'; }
    else if (secKm >= 233) { z = 3; name = 'Z3 Tempo'; }
    else if (secKm >= 220) { z = 4; name = 'Z4 Umbral'; }
    else if (secKm >= 198) { z = 5; name = 'Z5 VO2 Máx'; }
    else if (secKm >= 180) { z = 6; name = 'Z6 Capacidad Anaeróbica'; }
    else { z = 7; name = 'Z7 Neuromuscular / Sprint'; }
    return { zone: z, name, color: INTERVALS_ZONE_COLORS[z] };
  }

  if (sportType === 'swimming') {
    const sec100 = (s.avg_speed_mps && s.avg_speed_mps > 0) ? (100 / s.avg_speed_mps) : 0;
    let z = 1, name = 'Z1 Suave / Técnica';
    if (sec100 > 114) { z = 1; name = 'Z1 Suave / Técnica'; }
    else if (sec100 >= 102) { z = 2; name = 'Z2 Fondo Aeróbico'; }
    else if (sec100 >= 94) { z = 3; name = 'Z3 Tempo'; }
    else if (sec100 >= 89) { z = 4; name = 'Z4 CSS Umbral'; }
    else if (sec100 >= 86) { z = 5; name = 'Z5 VO2 Máx'; }
    else if (sec100 >= 80) { z = 6; name = 'Z6 Capacidad Anaeróbica'; }
    else { z = 7; name = 'Z7 Sprint / All-Out'; }
    return { zone: z, name, color: INTERVALS_ZONE_COLORS[z] };
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
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          display: false // Shown in custom header badges
        },
        tooltip: {
          backgroundColor: '#1e293b',
          titleColor: '#ffffff',
          bodyColor: '#e2e8f0',
          borderColor: '#475569',
          borderWidth: 1,
          padding: 10,
          titleFont: { family: 'Inter, sans-serif', weight: 600, size: 12 },
          bodyFont: { family: 'Inter, sans-serif', size: 12 },
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
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: false // Shown in custom compact header legend
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#ffffff',
          bodyColor: '#e2e8f0',
          borderColor: '#334155',
          borderWidth: 1,
          padding: 11,
          titleFont: { family: 'Inter, sans-serif', weight: 700, size: 12 },
          bodyFont: { family: 'JetBrains Mono, monospace', size: 11 },
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
