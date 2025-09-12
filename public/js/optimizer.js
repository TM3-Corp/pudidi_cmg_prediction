// PUDIDI Optimizer - Client-side optimization using simplex algorithm

let generationChart = null;
let storageChart = null;

// Linear Programming Solver - Simplex Method
class SimplexSolver {
    constructor() {
        this.tableau = [];
        this.basicVars = [];
        this.nonBasicVars = [];
    }

    solve(c, A, b, bounds) {
        // Convert to standard form: maximize c'x subject to Ax <= b, x >= 0
        const m = A.length;
        const n = c.length;
        
        // Build initial tableau
        this.tableau = [];
        this.basicVars = [];
        this.nonBasicVars = [];
        
        // Add slack variables
        for (let i = 0; i < m; i++) {
            const row = [...A[i]];
            for (let j = 0; j < m; j++) {
                row.push(i === j ? 1 : 0);
            }
            row.push(b[i]);
            this.tableau.push(row);
            this.basicVars.push(n + i);
        }
        
        // Objective row
        const objRow = c.map(val => -val);
        for (let i = 0; i < m; i++) {
            objRow.push(0);
        }
        objRow.push(0);
        this.tableau.push(objRow);
        
        for (let i = 0; i < n; i++) {
            this.nonBasicVars.push(i);
        }
        
        // Simplex iterations
        let maxIter = 1000;
        while (maxIter-- > 0) {
            // Find entering variable (most negative in objective row)
            const objRow = this.tableau[this.tableau.length - 1];
            let pivotCol = -1;
            let minVal = 0;
            
            for (let j = 0; j < objRow.length - 1; j++) {
                if (objRow[j] < minVal) {
                    minVal = objRow[j];
                    pivotCol = j;
                }
            }
            
            if (pivotCol === -1) break; // Optimal
            
            // Find leaving variable (minimum ratio test)
            let pivotRow = -1;
            let minRatio = Infinity;
            
            for (let i = 0; i < this.tableau.length - 1; i++) {
                if (this.tableau[i][pivotCol] > 0) {
                    const ratio = this.tableau[i][this.tableau[i].length - 1] / this.tableau[i][pivotCol];
                    if (ratio < minRatio) {
                        minRatio = ratio;
                        pivotRow = i;
                    }
                }
            }
            
            if (pivotRow === -1) {
                console.warn("Unbounded solution");
                break;
            }
            
            // Pivot
            this.pivot(pivotRow, pivotCol);
        }
        
        // Extract solution
        const solution = new Array(n).fill(0);
        for (let i = 0; i < this.basicVars.length; i++) {
            if (this.basicVars[i] < n) {
                solution[this.basicVars[i]] = this.tableau[i][this.tableau[i].length - 1];
            }
        }
        
        return solution;
    }
    
    pivot(row, col) {
        const pivotVal = this.tableau[row][col];
        
        // Normalize pivot row
        for (let j = 0; j < this.tableau[row].length; j++) {
            this.tableau[row][j] /= pivotVal;
        }
        
        // Eliminate column in other rows
        for (let i = 0; i < this.tableau.length; i++) {
            if (i !== row) {
                const factor = this.tableau[i][col];
                for (let j = 0; j < this.tableau[i].length; j++) {
                    this.tableau[i][j] -= factor * this.tableau[row][j];
                }
            }
        }
        
        // Update basic variables
        this.basicVars[row] = col;
    }
}

// Hydro optimization model
function buildHydroModel(prices, params) {
    const T = prices.length;
    const dt = 1; // hourly steps
    const volPerStep = 3600 * dt; // seconds per step
    
    // Decision variables: P_t for t = 0..T-1
    // We'll solve a simplified version using discretization
    
    // For demonstration, we'll use a greedy heuristic
    // In production, you'd want a proper LP solver
    
    const P = [];
    const Q = [];
    const S = [params.s0];
    
    // Sort hours by price (greedy approach)
    const priceIndices = prices.map((p, i) => ({price: p, index: i}))
        .sort((a, b) => b.price - a.price);
    
    // Initialize with minimum generation
    for (let t = 0; t < T; t++) {
        P[t] = params.pMin;
        Q[t] = params.kappa * P[t];
    }
    
    // Try to generate more during high price hours
    for (const {index: t} of priceIndices) {
        // Check if we can increase generation
        const additionalPower = params.pMax - P[t];
        const additionalWater = additionalPower * params.kappa * volPerStep;
        
        // Check storage constraints
        let storageOk = true;
        let tempS = params.s0;
        
        const tempP = [...P];
        tempP[t] = params.pMax;
        
        for (let i = 0; i <= t; i++) {
            tempS += (params.inflow - params.kappa * tempP[i]) * volPerStep;
            if (tempS < params.sMin || tempS > params.sMax) {
                storageOk = false;
                break;
            }
        }
        
        if (storageOk) {
            // Check rest of horizon
            tempS = params.s0;
            for (let i = 0; i < T; i++) {
                tempS += (params.inflow - params.kappa * tempP[i]) * volPerStep;
                if (tempS < params.sMin || tempS > params.sMax) {
                    storageOk = false;
                    break;
                }
            }
        }
        
        if (storageOk) {
            P[t] = params.pMax;
            Q[t] = params.kappa * P[t];
        }
    }
    
    // Calculate storage trajectory
    let currentS = params.s0;
    for (let t = 0; t < T; t++) {
        currentS += (params.inflow - Q[t]) * volPerStep;
        S.push(currentS);
    }
    
    // Calculate revenue
    let revenue = 0;
    for (let t = 0; t < T; t++) {
        revenue += prices[t] * P[t] * dt;
    }
    
    return { P, Q, S, revenue };
}

async function fetchCMGPrices(node, horizon) {
    console.log(`[FETCH] Fetching CMG prices for node: ${node}, horizon: ${horizon} hours`);
    
    try {
        // First, try to fetch programmed data from cache API
        console.log('[FETCH] Attempting to fetch programmed CMG data from cache...');
        const cacheResponse = await fetch('/api/cache?type=programmed');
        
        let prices = [];
        let realPriceCount = 0;
        
        if (cacheResponse.ok) {
            const cacheData = await cacheResponse.json();
            console.log('[FETCH] Cache data retrieved:', cacheData);
            
            // Extract prices from programmed data (PMontt220)
            if (cacheData.data && Array.isArray(cacheData.data)) {
                console.log(`[FETCH] Found ${cacheData.data.length} programmed prices in cache`);
                
                // Sort by datetime to ensure correct order
                const sortedData = cacheData.data.sort((a, b) => {
                    return new Date(a.datetime) - new Date(b.datetime);
                });
                
                for (let i = 0; i < Math.min(horizon, sortedData.length); i++) {
                    const record = sortedData[i];
                    const price = record.cmg_programmed || 70;
                    prices.push(price);
                    if (i < 5) {
                        console.log(`[FETCH] Hour ${i} (${record.datetime}): $${price.toFixed(2)}/MWh`);
                    }
                }
                
                realPriceCount = prices.length;
                console.log(`[FETCH] Using ${realPriceCount} real PMontt220 prices from cache`);
            }
        } else {
            console.log('[FETCH] Cache not accessible, trying API fallback...');
            
            // Fallback to API endpoint
            const apiResponse = await fetch('/api/cmg/current');
            if (apiResponse.ok) {
                const apiData = await apiResponse.json();
                console.log('[FETCH] API response:', apiData);
                
                // Try to get programmed data from API response
                if (apiData.programmed && apiData.programmed.data) {
                    const programmedData = apiData.programmed.data;
                    
                    for (let i = 0; i < Math.min(horizon, programmedData.length); i++) {
                        const price = programmedData[i].cmg_programmed || 70;
                        prices.push(price);
                        if (i < 5) {
                            console.log(`[FETCH] Hour ${i}: $${price.toFixed(2)}/MWh`);
                        }
                    }
                    
                    realPriceCount = prices.length;
                    console.log(`[FETCH] Using ${realPriceCount} real prices from API`);
                }
            }
        }
        
        // Check if we have enough data
        if (prices.length < horizon) {
            console.error(`[FETCH] Insufficient data: ${prices.length} hours available but ${horizon} requested`);
            throw new Error(`Solo hay ${prices.length} horas de datos disponibles. Por favor reduzca el horizonte.`);
        }
        
        console.log(`[FETCH] Final price array has ${prices.length} elements`);
        console.log(`[FETCH] Price range: $${Math.min(...prices).toFixed(2)} - $${Math.max(...prices).toFixed(2)}/MWh`);
        return prices;
        
    } catch (error) {
        console.error('[FETCH] Error fetching CMG prices:', error);
        // Re-throw the error to be handled by the caller
        throw error;
    }
}

async function runOptimization() {
    console.log('[RUN] Starting optimization...');
    
    // Show loading
    document.getElementById('loadingSection').style.display = 'block';
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('metricsGrid').style.display = 'none';
    
    // Get parameters
    const params = {
        node: document.getElementById('nodeSelect').value,
        horizon: parseInt(document.getElementById('horizon').value),
        pMin: parseFloat(document.getElementById('pMin').value),
        pMax: parseFloat(document.getElementById('pMax').value),
        s0: parseFloat(document.getElementById('s0').value),
        sMin: parseFloat(document.getElementById('sMin').value),
        sMax: parseFloat(document.getElementById('sMax').value),
        kappa: parseFloat(document.getElementById('kappa').value),
        inflow: parseFloat(document.getElementById('inflow').value)
    };
    
    console.log('[RUN] Parameters:', params);
    
    // Validate parameters
    if (params.pMin >= params.pMax) {
        alert('Error: Minimum power must be less than maximum power');
        document.getElementById('loadingSection').style.display = 'none';
        return;
    }
    
    if (params.sMin >= params.sMax) {
        alert('Error: Minimum storage must be less than maximum storage');
        document.getElementById('loadingSection').style.display = 'none';
        return;
    }
    
    if (params.s0 < params.sMin || params.s0 > params.sMax) {
        alert('Error: Initial storage must be between min and max storage');
        document.getElementById('loadingSection').style.display = 'none';
        return;
    }
    
    try {
        // Validate horizon against available data
        const availableHours = parseInt(document.getElementById('horizon').max) || 0;
        if (params.horizon > availableHours) {
            throw new Error(`Horizonte excede los datos disponibles (máximo ${availableHours} horas)`);
        }
        
        console.log('[RUN] Calling backend optimizer API...');
        
        // Call backend API for Linear Programming optimization
        const response = await fetch('/api/optimizer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                node: params.node,
                horizon: params.horizon,
                p_min: params.pMin,
                p_max: params.pMax,
                s0: params.s0,
                s_min: params.sMin,
                s_max: params.sMax,
                kappa: params.kappa,
                inflow: params.inflow
            })
        });
        
        if (!response.ok) {
            const text = await response.text();
            console.error('[RUN] Backend error:', text);
            throw new Error(`Backend returned ${response.status}: ${text.substring(0, 100)}`);
        }
        
        const result = await response.json();
        console.log('[RUN] Backend response:', result);
        
        if (result.success && result.solution) {
            const solution = result.solution;
            const prices = result.prices;
            
            console.log('[RUN] Optimization method:', solution.optimization_method);
            console.log('[RUN] Solver success:', solution.solver_success);
            console.log('[RUN] Backend optimization complete:', solution);
        
            // Update metrics
            document.getElementById('totalRevenue').textContent = solution.revenue.toFixed(0);
            document.getElementById('avgGeneration').textContent = solution.avg_generation.toFixed(2);
            document.getElementById('peakGeneration').textContent = solution.peak_generation.toFixed(2);
            document.getElementById('capacityFactor').textContent = solution.capacity_factor.toFixed(1);
            
            console.log(`[RUN] Metrics - Revenue: $${solution.revenue.toFixed(0)}, Method: ${solution.optimization_method}`);
            
            // Show results
            document.getElementById('metricsGrid').style.display = 'grid';
            document.getElementById('resultsSection').style.display = 'grid';
            
            // Update charts
            console.log('[RUN] Updating charts...');
            updateCharts(solution, prices, params);
            
            console.log('[RUN] Optimization complete and displayed!');
        } else {
            // Fallback to client-side if backend fails
            console.log('[RUN] Backend failed, using client-side optimization...');
            const prices = await fetchCMGPrices(params.node, params.horizon);
            const solution = buildHydroModel(prices, params);
            
            // Update metrics
            const avgGen = solution.P.reduce((a, b) => a + b, 0) / solution.P.length;
            const peakGen = Math.max(...solution.P);
            const capacityFactor = (avgGen / params.pMax * 100).toFixed(1);
            
            document.getElementById('totalRevenue').textContent = solution.revenue.toFixed(0);
            document.getElementById('avgGeneration').textContent = avgGen.toFixed(2);
            document.getElementById('peakGeneration').textContent = peakGen.toFixed(2);
            document.getElementById('capacityFactor').textContent = capacityFactor;
            
            // Show results
            document.getElementById('metricsGrid').style.display = 'grid';
            document.getElementById('resultsSection').style.display = 'grid';
            
            // Update charts
            updateCharts(solution, prices, params);
        }
        
    } catch (error) {
        console.error('[RUN] Optimization error:', error);
        alert(`Error running optimization: ${error.message}\n\nCheck console for details.`);
    } finally {
        document.getElementById('loadingSection').style.display = 'none';
    }
}

function updateCharts(solution, prices, params) {
    // Generate datetime labels starting from the current hour (at 00 minutes)
    const now = new Date();
    // Round to the start of current hour
    now.setMinutes(0, 0, 0); 
    
    const dateTimeLabels = [];
    const hours = Array.from({length: solution.P.length}, (_, i) => {
        const date = new Date(now.getTime() + i * 3600000); // Add i hours
        const dateStr = date.toLocaleDateString('es-CL', { month: 'short', day: 'numeric' });
        const timeStr = date.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false });
        dateTimeLabels.push({ date, dateStr, timeStr });
        return `${dateStr} ${timeStr}`;
    });
    
    // Populate results table
    populateResultsTable(solution, prices, dateTimeLabels);
    
    // Generation & Prices Chart
    const genCtx = document.getElementById('generationChart').getContext('2d');
    
    if (generationChart) {
        generationChart.destroy();
    }
    
    generationChart = new Chart(genCtx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: 'Generation (MW)',
                    data: solution.P,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    yAxisID: 'y',
                    tension: 0,
                    fill: true,
                    stepped: 'middle'
                },
                {
                    label: 'Price ($/MWh)',
                    data: prices,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    yAxisID: 'y1',
                    tension: 0.2,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.5,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 10
                    }
                }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Generation (MW)'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Price ($/MWh)'
                    },
                    grid: {
                        drawOnChartArea: false,
                    }
                }
            }
        }
    });
    
    // Storage Chart
    const storageCtx = document.getElementById('storageChart').getContext('2d');
    
    if (storageChart) {
        storageChart.destroy();
    }
    
    const storageHours = ['Initial', ...hours];
    
    storageChart = new Chart(storageCtx, {
        type: 'line',
        data: {
            labels: storageHours,
            datasets: [
                {
                    label: 'Storage (m³)',
                    data: solution.S,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    tension: 0,
                    fill: true,
                    stepped: 'middle'
                },
                {
                    label: 'Max Storage',
                    data: Array(solution.S.length).fill(params.sMax),
                    borderColor: '#ef4444',
                    borderDash: [5, 5],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'Min Storage',
                    data: Array(solution.S.length).fill(params.sMin),
                    borderColor: '#ef4444',
                    borderDash: [5, 5],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.5,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 10
                    }
                }
            },
            scales: {
                y: {
                    title: {
                        display: true,
                        text: 'Storage (m³)'
                    }
                }
            }
        }
    });
}

function populateResultsTable(solution, prices, dateTimeLabels) {
    const tbody = document.getElementById('resultsTableBody');
    tbody.innerHTML = ''; // Clear existing rows
    
    for (let i = 0; i < solution.P.length; i++) {
        const row = tbody.insertRow();
        
        // Hour number
        row.insertCell(0).textContent = i + 1;
        
        // Date/Time
        const dateCell = row.insertCell(1);
        dateCell.textContent = `${dateTimeLabels[i].dateStr} ${dateTimeLabels[i].timeStr}`;
        
        // Generation in kW (MW * 1000)
        const genCell = row.insertCell(2);
        genCell.textContent = Math.round(solution.P[i] * 1000);
        genCell.style.textAlign = 'right';
        
        // Storage
        const storageCell = row.insertCell(3);
        storageCell.textContent = Math.round(solution.S[i + 1] || solution.S[i]);
        storageCell.style.textAlign = 'right';
        
        // Price
        const priceCell = row.insertCell(4);
        priceCell.textContent = prices[i].toFixed(2);
        priceCell.style.textAlign = 'right';
        
        // Add subtle row styling
        if (i % 2 === 1) {
            row.style.backgroundColor = '#f8fafc';
        }
        row.style.borderBottom = '1px solid #e2e8f0';
    }
}

function copyTableToClipboard() {
    const table = document.getElementById('resultsTable');
    const rows = table.querySelectorAll('tr');
    
    let text = '';
    rows.forEach((row, index) => {
        const cells = row.querySelectorAll('th, td');
        const rowData = Array.from(cells).map(cell => cell.textContent).join('\t');
        text += rowData + '\n';
    });
    
    // Copy to clipboard
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('copyTableBtn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '✅ Copiado!';
        setTimeout(() => {
            btn.innerHTML = originalText;
        }, 2000);
    }).catch(err => {
        console.error('Error copying to clipboard:', err);
        alert('Error al copiar. Por favor, seleccione y copie manualmente.');
    });
}

function resetParameters() {
    document.getElementById('horizon').value = 48;  // Changed default to 48
    document.getElementById('pMin').value = 0.5;
    document.getElementById('pMax').value = 3;
    document.getElementById('s0').value = 25000;
    document.getElementById('sMin').value = 1000;
    document.getElementById('sMax').value = 50000;
    document.getElementById('kappa').value = 0.667;
    document.getElementById('inflow').value = 1.1;
}

// Function to update data availability info
async function updateDataAvailability() {
    try {
        const response = await fetch('/api/cache?type=programmed');
        if (response.ok) {
            const data = await response.json();
            if (data.data && Array.isArray(data.data)) {
                const sortedData = data.data.sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
                
                if (sortedData.length > 0) {
                    const startDate = new Date(sortedData[0].datetime);
                    const endDate = new Date(sortedData[sortedData.length - 1].datetime);
                    const availableHours = sortedData.length;
                    
                    // Format dates for display
                    const formatDate = (date) => {
                        return date.toLocaleDateString('es-CL', {
                            day: 'numeric',
                            month: 'short',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    };
                    
                    // Update display
                    const availDiv = document.getElementById('dataAvailability');
                    availDiv.innerHTML = `
                        <strong style="color: #059669;">✓ ${availableHours} horas disponibles</strong><br>
                        Desde: ${formatDate(startDate)}<br>
                        Hasta: ${formatDate(endDate)}
                    `;
                    
                    // Update horizon max value
                    const horizonInput = document.getElementById('horizon');
                    horizonInput.max = availableHours;
                    
                    // If current value exceeds max, adjust it
                    if (parseInt(horizonInput.value) > availableHours) {
                        horizonInput.value = availableHours;
                    }
                    
                    // Add validation message
                    horizonInput.title = `Máximo ${availableHours} horas de datos disponibles`;
                    
                    return availableHours;
                }
            }
        }
        
        // If we couldn't get data info
        document.getElementById('dataAvailability').innerHTML = 
            '<span style="color: #dc2626;">⚠️ No se pudo verificar la disponibilidad de datos</span>';
        return 0;
        
    } catch (error) {
        console.error('Error fetching data availability:', error);
        document.getElementById('dataAvailability').innerHTML = 
            '<span style="color: #dc2626;">⚠️ Error al verificar disponibilidad</span>';
        return 0;
    }
}

// Auto-run optimization on load
window.addEventListener('DOMContentLoaded', () => {
    // Update data availability on load
    updateDataAvailability();
    
    // Removed duplicate back button - using the one in HTML instead
});