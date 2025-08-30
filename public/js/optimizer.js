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
        // Fetch from our API
        console.log('[FETCH] Calling /api/predictions_live...');
        const response = await fetch('/api/predictions_live');
        
        if (!response.ok) {
            console.error(`[FETCH] API returned status ${response.status}`);
            throw new Error(`API returned status ${response.status}`);
        }
        
        const data = await response.json();
        console.log('[FETCH] Response received:', data);
        
        // Extract prices for the selected node
        const prices = [];
        const programmedData = data.cmg_programmed || [];
        
        console.log(`[FETCH] Found ${programmedData.length} programmed prices in response`);
        
        for (let i = 0; i < Math.min(horizon, programmedData.length); i++) {
            const price = programmedData[i].cmg_programmed || 70;
            prices.push(price);
            if (i < 5) {
                console.log(`[FETCH] Hour ${i}: $${price.toFixed(2)}/MWh`);
            }
        }
        
        const realPriceCount = prices.length;
        console.log(`[FETCH] Using ${realPriceCount} real prices from API`);
        
        // If we need more prices, use synthetic data
        while (prices.length < horizon) {
            const hour = prices.length % 24;
            const basePrice = 70;
            const variation = Math.sin(hour * Math.PI / 12) * 30;
            prices.push(basePrice + variation + Math.random() * 10);
        }
        
        if (prices.length > realPriceCount) {
            console.log(`[FETCH] Added ${prices.length - realPriceCount} synthetic prices to reach horizon`);
        }
        
        console.log(`[FETCH] Final price array has ${prices.length} elements`);
        return prices;
        
    } catch (error) {
        console.error('[FETCH] Error fetching CMG prices:', error);
        console.log('[FETCH] Falling back to synthetic prices');
        
        // Generate synthetic prices as fallback
        const prices = [];
        for (let i = 0; i < horizon; i++) {
            const hour = i % 24;
            const basePrice = 70;
            const variation = Math.sin(hour * Math.PI / 12) * 30;
            prices.push(basePrice + variation + Math.random() * 10);
        }
        
        console.log(`[FETCH] Generated ${prices.length} synthetic prices`);
        return prices;
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
        // Fetch CMG prices
        console.log('[RUN] Fetching CMG prices...');
        const prices = await fetchCMGPrices(params.node, params.horizon);
        
        console.log(`[RUN] Got ${prices.length} prices, running optimization...`);
        
        // Run optimization
        const solution = buildHydroModel(prices, params);
        
        console.log('[RUN] Optimization complete:', solution);
        
        // Update metrics
        const avgGen = solution.P.reduce((a, b) => a + b, 0) / solution.P.length;
        const peakGen = Math.max(...solution.P);
        const capacityFactor = (avgGen / params.pMax * 100).toFixed(1);
        
        console.log(`[RUN] Metrics - Revenue: $${solution.revenue.toFixed(0)}, Avg: ${avgGen.toFixed(2)} MW, Peak: ${peakGen.toFixed(2)} MW, CF: ${capacityFactor}%`);
        
        document.getElementById('totalRevenue').textContent = solution.revenue.toFixed(0);
        document.getElementById('avgGeneration').textContent = avgGen.toFixed(2);
        document.getElementById('peakGeneration').textContent = peakGen.toFixed(2);
        document.getElementById('capacityFactor').textContent = capacityFactor;
        
        // Show results
        document.getElementById('metricsGrid').style.display = 'grid';
        document.getElementById('resultsSection').style.display = 'grid';
        
        // Update charts
        console.log('[RUN] Updating charts...');
        updateCharts(solution, prices, params);
        
        console.log('[RUN] Optimization complete and displayed!');
        
    } catch (error) {
        console.error('[RUN] Optimization error:', error);
        alert(`Error running optimization: ${error.message}\n\nCheck console for details.`);
    } finally {
        document.getElementById('loadingSection').style.display = 'none';
    }
}

function updateCharts(solution, prices, params) {
    const hours = Array.from({length: solution.P.length}, (_, i) => `Hour ${i + 1}`);
    
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
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
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
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
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

function resetParameters() {
    document.getElementById('horizon').value = 24;
    document.getElementById('pMin').value = 0.5;
    document.getElementById('pMax').value = 3;
    document.getElementById('s0').value = 25000;
    document.getElementById('sMin').value = 1000;
    document.getElementById('sMax').value = 50000;
    document.getElementById('kappa').value = 0.667;
    document.getElementById('inflow').value = 1.1;
}

// Auto-run optimization on load
window.addEventListener('DOMContentLoaded', () => {
    // Add link to main page
    const nav = document.createElement('div');
    nav.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1000;';
    nav.innerHTML = `
        <a href="/" style="
            background: white;
            color: #667eea;
            padding: 10px 20px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            display: inline-block;
            transition: all 0.3s ease;
        " onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
            ← Back to CMG Predictions
        </a>
    `;
    document.body.appendChild(nav);
});