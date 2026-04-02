# Reporte de Analisis: ML Pipeline CMG Prediction

**Fecha**: 2026-03-31
**Branch**: `testing-auditing/ml`
**Autor**: Analisis automatizado

---

## 1. Modelo en Produccion (v2.0)

### Arquitectura: Two-Stage Ensemble (LightGBM + XGBoost)

```
Input: 168h historicas (1 semana)
          |
    Feature Engineering (150 features)
          |
    +-----+-----+
    |             |
Stage 1:       Stage 2:
Zero Detection  Value Prediction
(96 modelos)   (96 modelos)
    |             |
    +-----+-----+
          |
    Decision Logic
    (threshold por hora)
          |
    Output: 24h forecast + intervalos de confianza
```

### Stage 1 - Zero Detection (Clasificacion Binaria)
- **Modelos**: 48 LightGBM + 48 XGBoost (1 por horizonte x 2 algoritmos)
- **Objetivo**: Detectar si CMG sera 0 (surplus energetico, comun en mercado chileno)
- **Ensemble**: P_zero = (P_lgb + P_xgb) / 2
- **Calibracion**: Meta-calibrador LogisticRegression (ECE: 0.159 -> 0.011, mejora 93%)
- **Thresholds**: 24 umbrales optimizados por hora del dia (F1-maximization)
  - Rango: 0.360 - 0.371
  - Frecuencia de zeros: 15% (medianoche) a 59% (10:00 AM)

### Stage 2 - Value Prediction (Regresion Cuantilica)
- **Modelos por horizonte**: LGB Median + LGB Q10 + LGB Q90 + XGBoost
- **Ensemble**: value = (lgb_median + xgb) / 2
- **Intervalos de confianza**: [Q10, Q90] = 80% CI
- **Total**: 96 modelos (24 horizontes x 4 tipos)

### Feature Engineering (150 features totales)

| Categoria | Cantidad | Detalle |
|-----------|----------|---------|
| Temporales | 11 | hour, day_of_week, month (ciclico sin/cos), weekend/night/morning |
| Lags | 8 | 1h, 2h, 3h, 6h, 12h, 24h, 48h, 168h |
| Rolling Stats | 30 | Windows [6,12,24,48,168h] x {mean, std, min, max, range, CV} |
| Patrones Zero | 12 | zeros_count/ratio por ventana, hours_since_zero |
| Tendencia | 8 | cmg_trend y cmg_change en multiples ventanas |
| Estacionalidad | 5 | same_hour_yesterday/last_week, 7d_median |
| CMG Programado | 4+ | cmg_prog_t+h, spread, vs_mean |
| Meta-features | 72 | Zero risk predictions de Stage 1 (3 x 24 horizontes) |

### Anti-Leakage (Critico)
```python
# CORRECTO: shift ANTES de rolling
shifted_series = df['CMG'].shift(1)
df['cmg_mean_24h'] = shifted_series.rolling(24, min_periods=1).mean()

# INCORRECTO (LEAKAGE!):
df['cmg_mean_24h'] = df['CMG'].rolling(24).mean()  # incluye valor actual
```

### Performance en Produccion
| Metrica | Valor |
|---------|-------|
| MAE Modelo | ~$32.43/MWh |
| MAE Baseline (persistencia) | $32.20/MWh |
| Zero Detection F1 | 0.744 |
| Tamano total modelos | 84 MB |
| Tiempo inferencia | <100ms (24h forecast) |
| Features mas importantes | cmg_lag_1h (15-20%), cmg_lag_24h (10-12%), hour (8-10%) |

### Observacion Critica
> El modelo apenas supera el baseline de persistencia ($32.43 vs $32.20 MAE).
> Esto sugiere que CMG es altamente autocorrelacionado y los lags dominan.
> Hay espacio significativo de mejora.

---

## 2. Propuestas Experimentales (Branch Ignacio_test)

### 2.1 NeuralProphet (`legacy_ignacio/neuralprophet_model.ipynb`)

**Arquitectura**: Hybrid Prophet + AR-Net (redes neuronales autoregresivas)

**Configuracion**:
```python
NeuralProphet(
    n_lags=168,                    # 1 semana de lags
    yearly_seasonality=False,
    weekly_seasonality=True,
    daily_seasonality=True,
    seasonality_mode='multiplicative',
    n_changepoints=20,
    learning_rate=0.01,
    epochs=100,
    batch_size=64,
    loss_func='MSE'
)
```

**Resultados**:
- MAE reportado: ~10 (commit message "Neural_Prophet_advanced_MAE10")
- **Limitacion**: Evaluacion rolling 1-step-ahead (NO comparable con 24h ahead)
- Modelo guardado: `data/Test_i/modelo.np` (~46 MB)
- Fortaleza: Buena cuantificacion de incertidumbre e interpretabilidad

**Estado**: Investigacion. No comparable directamente con produccion.

### 2.2 TSMixer (`legacy_ignacio/TSMIXER_Model.ipynb`)

**Arquitectura**: Time-Series Mixer (Google Research) via NeuralForecast

**Metodologia**:
- Entrenamiento en 2 fases con backtesting rolling
- Input: Serie temporal cruda 168h (sin features externas)
- Backtesting: 72 horas (3 dias) con ventana deslizante

**Configuracion**:
```python
TSMixer(
    h=24,                          # Horizonte 24 horas
    input_size=168,                # 1 semana de historia
    n_series=1,
    max_steps=2000,
    learning_rate=1e-3,
    batch_size=32,
    scaler_type='standard'
)
```

**Resultados**: MAE ~$34/MWh estimado (evaluacion diferente a produccion)

**Estado**: Investigacion. Arquitectura all-MLP prometedora pero sin ventaja clara.

### 2.3 Modelos Experimentales en `models_experimental/`
- `enhanced_tsmixer/` - TSMixer con features adicionales
- `hybrid_tsmixer/` - Ensemble TSMixer + modelos tradicionales
- Scripts de entrenamiento en `scripts/training/`:
  - `train_enhanced_tsmixer.py`
  - `train_hybrid_tsmixer_ensemble.py`
  - `optuna_tsmixer_search.py` (hyperparameter search)

---

## 3. Conexion Supabase - Acceso a Data

### Configuracion
```bash
# Variables de entorno requeridas
SUPABASE_URL=https://btyfbrclgmphcjgrvcgd.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
```

### Tablas Principales

| Tabla | Registros | Contenido | Unique Key |
|-------|-----------|-----------|------------|
| `cmg_online` | Continuo desde Nov 2025 | CMG real (SIP API) | (datetime, node) |
| `cmg_programado` | 44,573+ registros | CMG forecast (Coordinador) | (forecast_datetime, target_datetime, node_id) |
| `ml_predictions` | Continuo horario | Predicciones ML 24h | (forecast_datetime, target_datetime) |
| `nodes` | ~6 nodos | Metadata de nodos | (code) |

### Nodos Activos
| Codigo | Nombre | Voltaje |
|--------|--------|---------|
| NVA_P.MONTT___220 | Puerto Montt | 220kV |
| DALCAHUE______110 | Dalcahue | 110kV |
| PIDPID________110 | Pidpid | 110kV |

### Cliente Existente
```python
from lib.utils.supabase_client import SupabaseClient

supabase = SupabaseClient()

# CMG Online (valores reales)
data = supabase.get_cmg_online(start_date='2026-03-01', end_date='2026-03-31', limit=10000)

# CMG Programado (forecast coordinador)
data = supabase.get_cmg_programado(start_date='2026-03-01', end_date='2026-03-31', latest_forecast_only=True)

# ML Predictions
data = supabase.get_ml_predictions(start_date='2026-03-01', end_date='2026-03-31')

# Integridad de datos (RPC)
# POST /rest/v1/rpc/check_data_integrity con {p_start_date, p_end_date}
```

### Timezone
- **DB**: Todo en UTC (TIMESTAMPTZ)
- **Local**: America/Santiago (UTC-3 o UTC-4 con DST)
- **Views disponibles**: `cmg_online_santiago`, `cmg_programado_santiago`, `ml_predictions_santiago`

---

## 4. Gaps Identificados y Oportunidades

### 4.1 Performance del Modelo Actual
- MAE apenas supera persistencia -> **hay espacio de mejora significativo**
- Top features son lags simples -> el modelo no esta capturando patrones complejos
- Sin features exogenas reales (meteorologia, demanda, generacion)

### 4.2 Evaluacion No Estandarizada
- Produccion, NeuralProphet y TSMixer usan metricas/splits diferentes
- **Se necesita un benchmark unificado** con:
  - Mismo periodo de test
  - Mismas metricas (MAE, RMSE, MAPE por horizonte)
  - Misma metodologia de backtesting

### 4.3 Datos Disponibles No Explotados
- `cmg_programado` como feature (parcialmente usado)
- Patrones cross-node (correlaciones entre nodos)
- Datos de ~5 meses en Supabase para entrenar

### 4.4 Arquitecturas No Exploradas
- Transformers temporales (TFT, PatchTST)
- LSTM/GRU con attention
- Modelos de difusion para series temporales
- Stacking ensemble (meta-learner sobre multiples arquitecturas)

---

## 5. Proximos Pasos Sugeridos

1. **Crear data loader unificado** -> `proposal/data_loader.py` (incluido)
2. **Definir benchmark estandar** con periodo fijo y metricas comunes
3. **Evaluar modelo actual** con el benchmark para tener baseline real
4. **Testear arquitecturas alternativas** bajo las mismas condiciones
5. **Analizar features exogenas** que puedan agregar valor predictivo

---

## Archivos en esta carpeta

| Archivo | Descripcion |
|---------|-------------|
| `REPORT.md` | Este reporte |
| `data_loader.py` | Utilidad para cargar data desde Supabase para experimentacion |
| `benchmark.py` | Framework de evaluacion estandarizado |
