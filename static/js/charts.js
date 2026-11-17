/**
 * Charting engine for Triathlon Performance & Health Platform.
 * Builds and updates the PMC curve (CTL/ATL/TSB) and zone distribution graphs.
 */

let pmcChartInstance = null;
let workoutSplitsChartInstance = null;

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
          borderColor: '#00A3E0',
          backgroundColor: 'rgba(0, 163, 224, 0.1)',
          borderWidth: 2.5,
          pointRadius: seriesData.length > 60 ? 0 : 2,
          pointHoverRadius: 5,
          tension: 0.3,
          yAxisID: 'y'
        },
        {
          label: 'Fatiga (ATL)',
          data: atlValues,
          borderColor: '#EC4899',
          backgroundColor: 'rgba(236, 72, 153, 0.05)',
          borderWidth: 2,
          pointRadius: seriesData.length > 60 ? 0 : 2,
          pointHoverRadius: 5,
          tension: 0.3,
          yAxisID: 'y'
        },
        {
          label: 'Frescura / Forma (TSB)',
          data: tsbValues,
          borderColor: '#10B981',
          borderWidth: 2,
          borderDash: [4, 4],
          pointRadius: 0,
          pointHoverRadius: 5,
          tension: 0.2,
          yAxisID: 'y1'
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
            color: '#94a3b8',
            font: { family: 'Inter', size: 12, weight: 600 },
            usePointStyle: true,
            boxWidth: 8
          }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#f8fafc',
          bodyColor: '#cbd5e1',
          borderColor: '#334155',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: function(context) {
              const label = context.dataset.label || '';
              const val = context.parsed.y;
              return `${label}: ${val}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(51, 65, 85, 0.25)' },
          ticks: {
            color: '#64748b',
            maxTicksLimit: 10,
            font: { family: 'Inter', size: 11 }
          }
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(51, 65, 85, 0.25)' },
          title: {
            display: true,
            text: 'Carga (CTL / ATL)',
            color: '#94a3b8',
            font: { family: 'Inter', size: 11 }
          },
          ticks: { color: '#64748b' }
        },
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          title: {
            display: true,
            text: 'TSB (Balance)',
            color: '#10B981',
            font: { family: 'Inter', size: 11 }
          },
          ticks: { color: '#10B981' }
        }
      }
    }
  });
}

function renderWorkoutSplitsChart(canvasId, splits, sportType) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !splits || splits.length === 0) return;

  if (workoutSplitsChartInstance) {
    workoutSplitsChartInstance.destroy();
  }

  const isCycling = sportType === 'cycling';
  const isRunning = sportType === 'running';
  const isSwim = sportType === 'swimming';

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
    yAxisLabel = 'Potencia (W)';
    yAxisColor = '#F59E0B'; // amber
  } else if (isRunning) {
    // Pace in seconds per km (smaller is faster)
    outputValues = splits.map(s => s.avg_speed_mps && s.avg_speed_mps > 0 ? Math.round(1000 / s.avg_speed_mps) : null);
    yAxisLabel = 'Ritmo (min/km)';
    yAxisColor = '#10B981'; // emerald
  } else if (isSwim) {
    // Pace in seconds per 100m
    outputValues = splits.map(s => s.avg_speed_mps && s.avg_speed_mps > 0 ? Math.round(100 / s.avg_speed_mps) : null);
    yAxisLabel = 'Ritmo (min/100m)';
    yAxisColor = '#06B6D4'; // cyan
  } else {
    outputValues = splits.map(s => s.avg_speed_mps ? Math.round(s.avg_speed_mps * 60) : 0);
    yAxisLabel = 'Velocidad';
  }

  const validOutputs = outputValues.filter(v => v !== null && v > 0);
  const minOut = validOutputs.length ? Math.min(...validOutputs) : 0;
  const maxOut = validOutputs.length ? Math.max(...validOutputs) : 100;

  workoutSplitsChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: yAxisLabel,
          data: outputValues,
          backgroundColor: isCycling ? 'rgba(245, 158, 11, 0.45)' : (isRunning ? 'rgba(16, 185, 129, 0.45)' : 'rgba(6, 182, 212, 0.45)'),
          borderColor: yAxisColor,
          borderWidth: 1.5,
          borderRadius: 4,
          yAxisID: 'y'
        },
        {
          label: 'FC Media (bpm)',
          data: hrValues,
          type: 'line',
          borderColor: '#EF4444',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          tension: 0.25,
          yAxisID: 'y1'
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
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 }, usePointStyle: true, boxWidth: 6 }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#f8fafc',
          bodyColor: '#cbd5e1',
          borderColor: '#334155',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: function(context) {
              if (context.dataset.yAxisID === 'y1') {
                return `FC Media: ${context.parsed.y} bpm`;
              }
              const val = context.parsed.y;
              if (isCycling) {
                return `Potencia: ${val} W`;
              } else if (isRunning) {
                const m = Math.floor(val / 60);
                const s = Math.round(val % 60);
                return `Ritmo: ${m}:${s.toString().padStart(2, '0')}/km`;
              } else if (isSwim) {
                const m = Math.floor(val / 60);
                const s = Math.round(val % 60);
                return `Ritmo: ${m}:${s.toString().padStart(2, '0')}/100m`;
              }
              return `${context.dataset.label}: ${val}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(51, 65, 85, 0.2)' },
          ticks: { color: '#64748b', font: { size: 10 } }
        },
        y: {
          position: 'left',
          reverse: isRunning || isSwim,
          min: (isRunning || isSwim) ? Math.max(0, minOut - 15) : undefined,
          max: (isRunning || isSwim) ? maxOut + 15 : undefined,
          grid: { color: 'rgba(51, 65, 85, 0.2)' },
          ticks: {
            color: yAxisColor,
            font: { size: 10 },
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
            font: { size: 10, weight: 600 }
          }
        },
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: {
            color: '#EF4444',
            font: { size: 10 },
            callback: function(val) {
              return `${val} bpm`;
            }
          },
          title: {
            display: true,
            text: 'FC (bpm)',
            color: '#EF4444',
            font: { size: 10, weight: 600 }
          }
        }
      }
    }
  });
}
