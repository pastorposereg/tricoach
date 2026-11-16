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

  const labels = splits.map((s, idx) => `Km/Lap ${idx + 1}`);
  const hrValues = splits.map(s => s.avg_heart_rate);
  const outputValues = splits.map(s => {
    if (sportType === 'cycling') {
      return s.avg_power || 0;
    } else {
      // Speed in min/km or m/s
      return s.avg_speed_mps ? Math.round(s.avg_speed_mps * 60) : 0;
    }
  });

  workoutSplitsChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: sportType === 'cycling' ? 'Potencia (W)' : 'Velocidad (m/min)',
          data: outputValues,
          backgroundColor: 'rgba(0, 163, 224, 0.5)',
          borderColor: '#00A3E0',
          borderWidth: 1.5,
          yAxisID: 'y'
        },
        {
          label: 'FC Media (bpm)',
          data: hrValues,
          type: 'line',
          borderColor: '#EF4444',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.2,
          yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(51, 65, 85, 0.2)' },
          ticks: { color: '#64748b', font: { size: 10 } }
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(51, 65, 85, 0.2)' },
          ticks: { color: '#00A3E0', font: { size: 10 } }
        },
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { color: '#EF4444', font: { size: 10 } }
        }
      }
    }
  });
}
