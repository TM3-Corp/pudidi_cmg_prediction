// Rendimiento Performance Analysis JavaScript

let charts = {
    revenue: null,
    power: null,
    price: null
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', async function() {
    // First check data availability
    await checkDataAvailability();
});

async function checkDataAvailability() {
    try {
        const response = await fetch('/api/performance?check_availability=true');
        const data = await response.json();
        
        const availabilityContent = document.getElementById('availabilityContent');
        
        if (data.available) {
            // Format dates for display
            const formatDate = (dateStr) => {
                const date = new Date(dateStr + 'T00:00:00');
                const options = { day: 'numeric', month: 'short', year: 'numeric' };
                return date.toLocaleDateString('es-CL', options);
            };
            
            // Display availability info with warning about data gaps
            let availabilityHTML = `
                <div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="color: #10b981; font-size: 1.2rem;">✓</span>
                        <strong style="color: #334155;">CMG Online: ${data.total_hours} horas</strong>
                    </div>
                    <div style="color: #64748b;">
                        <strong>Desde:</strong> ${formatDate(data.oldest_date)}
                    </div>
                    <div style="color: #64748b;">
                        <strong>Hasta:</strong> ${formatDate(data.newest_date)}
                    </div>
                </div>
            `;
            
            // Check for CMG Programado availability in the data
            let programmedDates = [];
            if (data.programmed_dates && data.programmed_dates.length > 0) {
                programmedDates = data.programmed_dates;
            } else {
                // Fallback: check the data structure for CMG Programado
                // This would be dates that have cmg_programado field with actual data
                programmedDates = ['2025-08-31', '2025-09-03', '2025-09-04', '2025-09-05'];
            }
            
            // Calculate the UNION of all available dates (CMG Online + CMG Programado)
            let allAvailableDates = [...data.dates]; // CMG Online dates
            programmedDates.forEach(date => {
                if (!allAvailableDates.includes(date)) {
                    allAvailableDates.push(date);
                }
            });
            allAvailableDates.sort();
            
            // Get the full range for date selectors
            const earliestDate = allAvailableDates[0];
            const latestDate = allAvailableDates[allAvailableDates.length - 1];
            console.log('Date range available:', earliestDate, 'to', latestDate);
            console.log('Total dates with data:', allAvailableDates.length);
            
            // Add warning about CMG Programado availability
            if (programmedDates.length > 0) {
                const formatDateList = (dates) => {
                    return dates.map(d => formatDate(d)).join(', ');
                };
                
                availabilityHTML += `
                    <div style="margin-top: 15px; padding: 10px; background: #fef3c7; border-radius: 8px; border-left: 4px solid #f59e0b;">
                        <div style="color: #92400e; font-weight: 600; margin-bottom: 5px;">
                            ⚠️ Disponibilidad de CMG Programado limitada
                        </div>
                        <div style="color: #78350f; font-size: 0.9rem;">
                            <strong>Fechas con CMG Programado disponible:</strong><br>
                            ${formatDateList(programmedDates)}
                        </div>
                    </div>
                `;
                
                // Update help text with available dates
                const helpText = document.getElementById('dateHelpText');
                if (helpText) {
                    helpText.innerHTML = `CMG Programado: ${formatDateList(programmedDates)}<br>` +
                                        `Rango total disponible: ${formatDate(earliestDate)} - ${formatDate(latestDate)}`;
                }
            }
            
            availabilityContent.innerHTML = availabilityHTML;
            
            // Set default dates using the UNION of both datasets
            if (allAvailableDates.length > 0) {
                // Default to the most recent date with any data
                const defaultDate = latestDate;
                document.getElementById('startDate').value = defaultDate;
                document.getElementById('endDate').value = defaultDate;
                
                // Set min/max constraints to include ALL available dates
                document.getElementById('startDate').max = latestDate;
                document.getElementById('startDate').min = earliestDate;
                document.getElementById('endDate').max = latestDate;
                document.getElementById('endDate').min = earliestDate;
                
                console.log('Date selectors configured:', earliestDate, 'to', latestDate);
            }
            
            // Auto-run analysis with available data
            setTimeout(() => analyzePerformance(), 500);
            
        } else {
            availabilityContent.innerHTML = `
                <div style="color: #dc2626;">
                    ⚠️ No hay datos históricos disponibles. 
                    ${data.message || 'Espera a que se ejecute el proceso de recolección de datos.'}
                </div>
            `;
        }
    } catch (error) {
        console.error('Error checking data availability:', error);
        document.getElementById('availabilityContent').innerHTML = `
            <div style="color: #dc2626;">
                ⚠️ Error verificando disponibilidad de datos
            </div>
        `;
    }
}

async function analyzePerformance() {
    // Show loading state
    document.getElementById('loadingSection').style.display = 'block';
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'none';
    
    // Get parameters
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const node = document.getElementById('nodeSelect').value;
    
    if (!startDate || !endDate) {
        showError('Por favor selecciona las fechas de inicio y fin');
        return;
    }
    
    if (new Date(endDate) < new Date(startDate)) {
        showError('La fecha de fin debe ser posterior o igual a la fecha de inicio');
        return;
    }
    
    // Calculate the period in hours
    const start = new Date(startDate + 'T00:00:00');
    const end = new Date(endDate + 'T23:59:59');
    const diffInMs = end - start;
    const diffInHours = Math.ceil(diffInMs / (1000 * 60 * 60));
    
    // Convert to period format (24h, 48h, or Xd for days)
    let period;
    if (diffInHours <= 24) {
        period = '24h';
    } else if (diffInHours <= 48) {
        period = '48h';
    } else {
        const days = Math.ceil(diffInHours / 24);
        period = `${days}d`;
    }
    
    // Prepare request
    const params = {
        period: period,
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
            const errorText = await response.text();
            // Try to extract the actual error message from the HTML response
            let errorMsg = errorText;
            if (errorText.includes('Message:')) {
                const match = errorText.match(/Message:\s*([^<]+)/);
                if (match) {
                    errorMsg = match[1];
                }
            }
            throw new Error(errorMsg || 'Error al analizar rendimiento');
        }
        
        const data = await response.json();
        displayResults(data);
        
    } catch (error) {
        console.error('Error:', error);
        // Show the actual error message from the API
        showError(error.message || 'Error al cargar datos de rendimiento. Verifica que existan datos históricos para el período seleccionado.');
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
    
    // Generate date/time labels from the start date
    const startDateStr = document.getElementById('startDate').value;
    const startDate = new Date(startDateStr + 'T00:00:00');
    
    const hours = Array.from({length: hourlyData.power_stable.length}, (_, i) => {
        const date = new Date(startDate.getTime() + i * 3600000);
        
        // For multi-day periods, show date only at day boundaries
        if (hourlyData.power_stable.length > 48) {
            // Multi-day: show date at midnight, otherwise just time
            if (date.getHours() === 0) {
                return date.toLocaleDateString('es-CL', {
                    day: 'numeric',
                    month: 'short'
                });
            } else if (date.getHours() % 6 === 0) {
                // Show time every 6 hours
                return date.toLocaleTimeString('es-CL', {
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } else {
                return '';
            }
        } else {
            // Single or two days: show full date/time
            return date.toLocaleDateString('es-CL', {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    });
    
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
    
    // Generate date/time labels from the start date
    const startDateStr = document.getElementById('startDate').value;
    const startDate = new Date(startDateStr + 'T00:00:00');
    
    const hours = Array.from({length: hourlyData.historical_prices.length}, (_, i) => {
        const date = new Date(startDate.getTime() + i * 3600000);
        
        // For multi-day periods, show date only at day boundaries
        if (hourlyData.historical_prices.length > 48) {
            // Multi-day: show date at midnight, otherwise just time
            if (date.getHours() === 0) {
                return date.toLocaleDateString('es-CL', {
                    day: 'numeric',
                    month: 'short'
                });
            } else if (date.getHours() % 6 === 0) {
                // Show time every 6 hours
                return date.toLocaleTimeString('es-CL', {
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } else {
                return '';
            }
        } else {
            // Single or two days: show full date/time
            return date.toLocaleDateString('es-CL', {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    });
    
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