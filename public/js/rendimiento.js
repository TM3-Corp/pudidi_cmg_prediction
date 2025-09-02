// Rendimiento Performance Analysis JavaScript

let currentPeriod = '24h';
let charts = {
    revenue: null,
    power: null,
    price: null
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Set default date to yesterday (more likely to have complete data)
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    document.getElementById('startDate').value = yesterday.toISOString().split('T')[0];
    
    // Setup period selector buttons
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentPeriod = this.dataset.period;
        });
    });
    
    // Load initial analysis
    analyzePerformance();
});

async function analyzePerformance() {
    // Show loading state
    document.getElementById('loadingSection').style.display = 'block';
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'none';
    
    // Get parameters
    const startDate = document.getElementById('startDate').value;
    const node = document.getElementById('nodeSelect').value;
    
    if (!startDate) {
        showError('Por favor selecciona una fecha de inicio');
        return;
    }
    
    // Prepare request
    const params = {
        period: currentPeriod,
        start_date: startDate + 'T00:00:00',
        node: node,
        p_min: 0.5,
        p_max: 3.0,
        s0: 25000,
        s_min: 1000,
        s_max: 50000,
        kappa: 0.667,
        inflow: 2.5
    };
    
    try {
        const response = await fetch('/api/performance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        
        if (!response.ok) {
            const error = await response.text();
            throw new Error(error || 'Error al analizar rendimiento');
        }
        
        const data = await response.json();
        displayResults(data);
        
    } catch (error) {
        console.error('Error:', error);
        showError('Error al cargar datos de rendimiento. Verifica que existan datos históricos para el período seleccionado.');
    } finally {
        document.getElementById('loadingSection').style.display = 'none';
    }
}

function displayResults(data) {
    document.getElementById('resultsSection').style.display = 'block';
    
    const summary = data.summary;
    const hourlyData = data.hourly_data;
    const dailyPerformance = data.daily_performance;
    
    // Update summary metrics
    document.getElementById('revenueStable').textContent = `$${formatNumber(summary.revenue_stable)}`;
    document.getElementById('pStable').textContent = summary.p_stable.toFixed(2);
    
    document.getElementById('revenueProgrammed').textContent = `$${formatNumber(summary.revenue_programmed)}`;
    const improvementDelta = document.getElementById('improvementDelta');
    if (summary.improvement_vs_stable > 0) {
        improvementDelta.innerHTML = `<span class="positive">+${summary.improvement_vs_stable.toFixed(1)}% vs base</span>`;
    } else {
        improvementDelta.innerHTML = `<span class="negative">${summary.improvement_vs_stable.toFixed(1)}% vs base</span>`;
    }
    
    document.getElementById('revenueHindsight').textContent = `$${formatNumber(summary.revenue_hindsight)}`;
    
    document.getElementById('efficiency').textContent = `${summary.efficiency.toFixed(1)}%`;
    const efficiencyStatus = document.getElementById('efficiencyStatus');
    if (summary.efficiency >= 90) {
        efficiencyStatus.innerHTML = '<span class="positive">Excelente</span>';
    } else if (summary.efficiency >= 75) {
        efficiencyStatus.innerHTML = '<span class="positive">Bueno</span>';
    } else if (summary.efficiency >= 60) {
        efficiencyStatus.innerHTML = 'Regular';
    } else {
        efficiencyStatus.innerHTML = '<span class="negative">Mejorable</span>';
    }
    
    // Create charts
    createRevenueChart(summary);
    createPowerChart(hourlyData);
    createPriceChart(hourlyData);
    
    // Show daily table for multi-day periods
    if (dailyPerformance && dailyPerformance.length > 0) {
        displayDailyTable(dailyPerformance);
        document.getElementById('dailyTableCard').style.display = 'block';
    } else {
        document.getElementById('dailyTableCard').style.display = 'none';
    }
}

function createRevenueChart(summary) {
    const ctx = document.getElementById('revenueChart').getContext('2d');
    
    if (charts.revenue) {
        charts.revenue.destroy();
    }
    
    charts.revenue = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Generación Estable', 'CMG Programado', 'Óptimo (Hindsight)'],
            datasets: [{
                data: [
                    summary.revenue_stable,
                    summary.revenue_programmed,
                    summary.revenue_hindsight
                ],
                backgroundColor: ['#94a3b8', '#667eea', '#10b981'],
                borderWidth: 0,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `$${formatNumber(context.raw)}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + formatNumber(value);
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

function createPowerChart(hourlyData) {
    const ctx = document.getElementById('powerChart').getContext('2d');
    
    if (charts.power) {
        charts.power.destroy();
    }
    
    // Generate hour labels
    const hours = Array.from({length: hourlyData.power_stable.length}, (_, i) => `H${i + 1}`);
    
    charts.power = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: 'Generación Estable',
                    data: hourlyData.power_stable,
                    borderColor: '#94a3b8',
                    backgroundColor: 'rgba(148, 163, 184, 0.1)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: false
                },
                {
                    label: 'CMG Programado',
                    data: hourlyData.power_programmed,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: false
                },
                {
                    label: 'Óptimo (Hindsight)',
                    data: hourlyData.power_hindsight,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: false
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
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.raw.toFixed(2) + ' MW';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Potencia (MW)'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        }
    });
}

function createPriceChart(hourlyData) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    
    if (charts.price) {
        charts.price.destroy();
    }
    
    // Generate hour labels
    const hours = Array.from({length: hourlyData.historical_prices.length}, (_, i) => `H${i + 1}`);
    
    charts.price = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: 'CMG Real (Online)',
                    data: hourlyData.historical_prices,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: false
                },
                {
                    label: 'CMG Programado',
                    data: hourlyData.programmed_prices,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    tension: 0.1,
                    fill: false
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
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': $' + context.raw.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Precio ($/MWh)'
                    },
                    ticks: {
                        callback: function(value) {
                            return '$' + value;
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        }
    });
}

function displayDailyTable(dailyPerformance) {
    const tbody = document.getElementById('dailyTableBody');
    tbody.innerHTML = '';
    
    dailyPerformance.forEach(day => {
        const row = tbody.insertRow();
        
        row.insertCell(0).textContent = `Día ${day.day}`;
        row.insertCell(1).textContent = '$' + formatNumber(day.revenue_stable);
        row.insertCell(2).textContent = '$' + formatNumber(day.revenue_programmed);
        row.insertCell(3).textContent = '$' + formatNumber(day.revenue_hindsight);
        
        const efficiencyCell = row.insertCell(4);
        efficiencyCell.textContent = day.efficiency.toFixed(1) + '%';
        
        // Color code efficiency
        if (day.efficiency >= 90) {
            efficiencyCell.style.color = '#10b981';
        } else if (day.efficiency >= 75) {
            efficiencyCell.style.color = '#3b82f6';
        } else if (day.efficiency < 60) {
            efficiencyCell.style.color = '#ef4444';
        }
        
        // Align right
        row.querySelectorAll('td:not(:first-child)').forEach(cell => {
            cell.classList.add('text-right');
        });
    });
}

function formatNumber(num) {
    return num.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    document.getElementById('loadingSection').style.display = 'none';
    document.getElementById('resultsSection').style.display = 'none';
}