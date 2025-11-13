/**
 * Supabase Client for Pudidi CMG Frontend
 * ========================================
 * Replaces Gist/Cache file fetching with Supabase REST API
 *
 * Uses anon key for public read-only access
 */

const SUPABASE_URL = 'https://btyfbrclgmphcjgrvcgd.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwMDk1MjksImV4cCI6MjA3NjU4NTUyOX0.WQK2xJMa6YWUABsXq2MQwJGpOQHt5GfZJ5pLe7MZIi8';

class SupabaseAPI {
    constructor() {
        this.baseURL = `${SUPABASE_URL}/rest/v1`;
        this.headers = {
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
            'Content-Type': 'application/json'
        };
    }

    /**
     * Get CMG Online (actual values)
     * @param {Object} params - Query parameters
     * @param {string} params.startDate - Start date (YYYY-MM-DD)
     * @param {string} params.endDate - End date (YYYY-MM-DD)
     * @param {string} params.node - Node name (optional)
     * @param {number} params.limit - Max records (default 1000)
     */
    async getCMGOnline(params = {}) {
        const {
            startDate,
            endDate,
            node,
            limit = 1000
        } = params;

        const queryParams = new URLSearchParams({
            select: '*',
            order: 'datetime.asc',
            limit: limit.toString()
        });

        if (startDate) {
            queryParams.append('date', `gte.${startDate}`);
        }
        if (endDate) {
            queryParams.append('date', `lte.${endDate}`);
        }
        if (node) {
            queryParams.append('node', `eq.${node}`);
        }

        const url = `${this.baseURL}/cmg_online?${queryParams}`;
        const response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Get CMG Programado (official forecasts)
     * @param {Object} params - Query parameters
     * @param {string} params.startDate - Start date (YYYY-MM-DD)
     * @param {string} params.endDate - End date (YYYY-MM-DD)
     * @param {number} params.limit - Max records (default 1000)
     */
    async getCMGProgramado(params = {}) {
        const {
            startDate,
            endDate,
            limit = 1000
        } = params;

        const queryParams = new URLSearchParams({
            select: '*',
            order: 'datetime.asc',
            limit: limit.toString()
        });

        if (startDate) {
            queryParams.append('date', `gte.${startDate}`);
        }
        if (endDate) {
            queryParams.append('date', `lte.${endDate}`);
        }

        const url = `${this.baseURL}/cmg_programado?${queryParams}`;
        const response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Get ML Predictions
     * @param {Object} params - Query parameters
     * @param {string} params.forecastDatetime - Specific forecast datetime
     * @param {string} params.startDate - Start date for forecast_datetime
     * @param {string} params.endDate - End date for forecast_datetime
     * @param {number} params.limit - Max records (default 5000)
     */
    async getMLPredictions(params = {}) {
        const {
            forecastDatetime,
            startDate,
            endDate,
            limit = 5000
        } = params;

        const queryParams = new URLSearchParams({
            select: '*',
            order: 'forecast_datetime.desc,target_datetime.asc',
            limit: limit.toString()
        });

        if (forecastDatetime) {
            queryParams.append('forecast_datetime', `eq.${forecastDatetime}`);
        }
        if (startDate) {
            queryParams.append('forecast_datetime', `gte.${startDate}`);
        }
        if (endDate) {
            queryParams.append('forecast_datetime', `lte.${endDate}`);
        }

        const url = `${this.baseURL}/ml_predictions?${queryParams}`;
        const response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Get latest ML forecast (most recent 24-hour prediction)
     */
    async getLatestMLForecast() {
        // First get the latest forecast_datetime
        let url = `${this.baseURL}/ml_predictions?select=forecast_datetime&order=forecast_datetime.desc&limit=1`;
        let response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        const latest = await response.json();
        if (latest.length === 0) {
            return [];
        }

        const latestForecastTime = latest[0].forecast_datetime;

        // Now get all predictions from that forecast
        url = `${this.baseURL}/ml_predictions?forecast_datetime=eq.${latestForecastTime}&order=target_datetime.asc`;
        response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Get available forecast dates/times for ML predictions
     * Returns unique forecast_datetime values
     */
    async getAvailableMLForecasts() {
        const url = `${this.baseURL}/ml_predictions?select=forecast_datetime&order=forecast_datetime.desc&limit=500`;
        const response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        const data = await response.json();

        // Get unique forecast datetimes
        const uniqueForecasts = [...new Set(data.map(d => d.forecast_datetime))];

        // Group by date and hour
        const grouped = {};
        uniqueForecasts.forEach(dt => {
            const date = dt.split('T')[0];
            const hour = new Date(dt).getUTCHours();

            if (!grouped[date]) {
                grouped[date] = [];
            }
            grouped[date].push({
                datetime: dt,
                hour: hour
            });
        });

        return grouped;
    }

    /**
     * Get latest 24 hours of CMG Online data
     */
    async getLatest24HoursCMG() {
        const url = `${this.baseURL}/cmg_online?select=*&order=datetime.desc&limit=72`;  // 3 nodes × 24 hours
        const response = await fetch(url, { headers: this.headers });

        if (!response.ok) {
            throw new Error(`Supabase API error: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Format Supabase data to match old Gist structure
     * (for compatibility with existing frontend code)
     */
    formatCMGOnlineAsCache(records) {
        return {
            metadata: {
                last_update: new Date().toISOString(),
                total_records: records.length
            },
            data: records.map(r => ({
                datetime: r.datetime,
                date: r.date,
                hour: r.hour,
                node: r.node,
                cmg_usd: r.cmg_usd,
                source: r.source || 'supabase'
            }))
        };
    }

    formatMLPredictionsAsCache(records) {
        // Group by forecast_datetime
        const grouped = {};
        records.forEach(r => {
            const forecastKey = r.forecast_datetime;
            if (!grouped[forecastKey]) {
                grouped[forecastKey] = {
                    forecast_time: r.forecast_datetime,
                    model_version: r.model_version,
                    predictions: []
                };
            }
            grouped[forecastKey].predictions.push({
                horizon: r.horizon,
                target_datetime: r.target_datetime,
                cmg: r.cmg_predicted,
                prob_zero: r.prob_zero,
                threshold: r.threshold
            });
        });

        // Convert to daily_data structure
        const daily_data = {};
        Object.values(grouped).forEach(forecast => {
            const date = forecast.forecast_time.split('T')[0];
            const hour = new Date(forecast.forecast_time).getUTCHours();

            if (!daily_data[date]) {
                daily_data[date] = { ml_forecasts: {} };
            }
            daily_data[date].ml_forecasts[hour.toString()] = forecast;
        });

        return {
            metadata: {
                last_update: new Date().toISOString(),
                total_forecasts: records.length
            },
            daily_data: daily_data
        };
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SupabaseAPI;
}

// Create global instance
const supabaseAPI = new SupabaseAPI();
