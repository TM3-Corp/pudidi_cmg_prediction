"""
Railway ML Backend - FastAPI server for CMG predictions

Serves ML predictions and threshold configurations
Deployed on Railway, called by Vercel frontend
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import csv
from pathlib import Path
from datetime import datetime
import uvicorn

app = FastAPI(
    title="CMG ML Prediction API",
    description="ML forecasting backend for CMG predictions",
    version="1.0.0"
)

# CORS - Allow Vercel frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pudidicmgprediction.vercel.app",
        "http://localhost:3000",
        "*"  # Allow all for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths to data and models (relative to railway_ml_backend/)
BASE_DIR = Path(__file__).parent.parent
PREDICTIONS_FILE = BASE_DIR / "data" / "ml_predictions" / "latest.json"
THRESHOLDS_FILE = BASE_DIR / "models_24h" / "zero_detection" / "optimal_thresholds.csv"


@app.get("/")
def root():
    """API root - health check"""
    return {
        "service": "CMG ML Prediction API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "predictions": "/api/ml_forecast",
            "thresholds": "/api/ml_thresholds",
            "health": "/health"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    predictions_exist = PREDICTIONS_FILE.exists()
    thresholds_exist = THRESHOLDS_FILE.exists()

    return {
        "status": "healthy" if (predictions_exist and thresholds_exist) else "degraded",
        "predictions_available": predictions_exist,
        "thresholds_available": thresholds_exist,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/ml_forecast")
def get_ml_forecast():
    """
    Get 24-hour ML predictions

    Returns:
        JSON with predictions including:
        - datetime, horizon, cmg_predicted
        - zero_probability, decision_threshold
        - confidence intervals (10th, 50th, 90th percentiles)
    """
    try:
        if not PREDICTIONS_FILE.exists():
            raise HTTPException(
                status_code=404,
                detail="ML predictions not yet generated"
            )

        # Load predictions
        with open(PREDICTIONS_FILE, 'r') as f:
            ml_data = json.load(f)

        # Transform to chart-friendly format
        chart_data = []

        for forecast in ml_data['forecasts']:
            target_dt = datetime.fromisoformat(forecast['target_datetime'])

            chart_data.append({
                'datetime': forecast['target_datetime'],
                'hour': target_dt.hour,
                'horizon': forecast['horizon'],
                'cmg_predicted': forecast['predicted_cmg'],
                'zero_probability': forecast['zero_probability'],
                'decision_threshold': forecast['decision_threshold'],
                'value_prediction': forecast['value_prediction'],
                'confidence_lower': forecast['confidence_interval']['lower_10th'],
                'confidence_median': forecast['confidence_interval']['median'],
                'confidence_upper': forecast['confidence_interval']['upper_90th'],
                'is_ml_prediction': True
            })

        # Response
        response = {
            'success': True,
            'model_version': ml_data['model_version'],
            'generated_at': ml_data['generated_at'],
            'base_datetime': ml_data['base_datetime'],
            'model_performance': ml_data['model_performance'],
            'predictions_count': len(chart_data),
            'predictions': chart_data,
            'status': {
                'available': True,
                'last_update': ml_data['generated_at'],
                'horizons': len(chart_data)
            }
        }

        return response

    except FileNotFoundError:
        return {
            'success': False,
            'error': 'ML predictions not yet generated',
            'message': 'Predictions are generated hourly. Please check back shortly.',
            'predictions': [],
            'status': {
                'available': False,
                'last_update': None
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml_thresholds")
def get_ml_thresholds():
    """
    Get optimal decision thresholds for all 24 horizons

    Returns:
        JSON with thresholds including:
        - optimal_threshold, current_threshold
        - safe adjustment range (min_allowed, max_allowed)
        - performance metrics (precision, recall, f1, auc)
    """
    try:
        if not THRESHOLDS_FILE.exists():
            raise HTTPException(
                status_code=404,
                detail="Optimal thresholds not found"
            )

        # Parse CSV
        thresholds_data = []

        with open(THRESHOLDS_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                horizon_str = row['horizon']
                if horizon_str.startswith('t+'):
                    horizon = int(horizon_str.replace('t+', ''))

                    optimal_threshold = float(row['threshold'])

                    # Calculate safe range (±20% from optimal, constrained to [0.1, 0.9])
                    min_threshold = max(0.1, optimal_threshold * 0.8)
                    max_threshold = min(0.9, optimal_threshold * 1.2)

                    thresholds_data.append({
                        'horizon': horizon,
                        'horizon_label': horizon_str,
                        'optimal_threshold': round(optimal_threshold, 4),
                        'current_threshold': round(optimal_threshold, 4),  # Default to optimal
                        'min_allowed': round(min_threshold, 4),
                        'max_allowed': round(max_threshold, 4),
                        'precision': float(row.get('precision', 0)),
                        'recall': float(row.get('recall', 0)),
                        'f1': float(row.get('f1', 0)),
                        'auc': float(row.get('auc', 0))
                    })

        # Response
        response = {
            'success': True,
            'thresholds': thresholds_data,
            'metadata': {
                'optimization_method': 'F1-maximization',
                'training_date': '2025-10-08',
                'horizons_count': len(thresholds_data),
                'threshold_range': {
                    'min': round(min([t['optimal_threshold'] for t in thresholds_data]), 4),
                    'max': round(max([t['optimal_threshold'] for t in thresholds_data]), 4)
                }
            },
            'info': {
                'description': 'Decision thresholds for zero-CMG classification',
                'adjustable': True,
                'safe_range_note': 'Adjustments limited to ±20% from optimal value',
                'impact': 'Lower threshold = more zero predictions (conservative), Higher threshold = fewer zero predictions (aggressive)'
            }
        }

        return response

    except FileNotFoundError:
        return {
            'success': False,
            'error': 'Thresholds configuration not found',
            'message': 'Optimal thresholds have not been configured yet',
            'thresholds': []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# For local development
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
