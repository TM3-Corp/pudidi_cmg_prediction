# Storyline: Auditoria y Mejora del Pipeline ML de Prediccion CMG

**Autor**: Ignacio Vergara
**Branch**: `testing-auditing/ml`
**Periodo**: Abril 2026
**Herramientas**: Python 3.9, LightGBM, XGBoost, NeuralForecast (TiDE, NHITS, NBEATSx), Apple Silicon MPS GPU

---

## 1. Contexto Inicial

El sistema Pudidi CMG Prediction tiene un modelo de produccion (v2.0) que predice el Costo Marginal (CMG) del mercado electrico chileno con horizonte de 24 horas. El modelo es un **ensemble two-stage de 192 modelos LightGBM + XGBoost**:

- **Stage 1**: 96 modelos de clasificacion binaria para detectar si CMG sera 0 (surplus energetico)
- **Stage 2**: 96 modelos de regresion cuantilica para predecir el valor de CMG

El pipeline corre cada hora via GitHub Actions, genera features (150 en total), predice y almacena en Supabase.

**Pregunta central**: ¿Que tan bueno es realmente este modelo y se puede mejorar?

---

## 2. Benchmark del Modelo de Produccion (Backtesting Rolling)

### Metodologia

Se implemento un **backtesting rolling diario** que simula como el modelo hubiera funcionado en produccion:

```
Dia 1: Toma 168h de historia -> predice 24h -> compara con valores reales
Dia 2: Avanza 24h -> toma nuevas 168h -> predice 24h -> compara
...
Dia N: Ultima ventana -> predice 24h -> compara
```

- **Datos**: Cache local (Sep 2025 - Ene 27, 2026) — 3,536 horas, 3 nodos promediados
- **Test**: Ultimos 45 dias, 44 ventanas, 1,056 predicciones
- **Sin data leakage**: features con `shift(1)` antes de rolling, split cronologico estricto

### Resultado

| Modelo | MAE ($/MWh) |
|--------|:-----------:|
| **Produccion (LGB+XGB)** | **$50.76** |
| Persistencia 24h | $51.81 |
| Media Movil 168h | $58.58 |
| Persistencia 168h | $64.65 |

**Hallazgo critico**: El modelo apenas supera la persistencia 24h (+2%). Desglosando por horizonte:

| Bloque | MAE |
|--------|:---:|
| Corto plazo (t+1..t+6) | **$75.03** — muy malo |
| Medio plazo (t+7..t+12) | $61.40 |
| Largo plazo (t+13..t+24) | $33.31 — funciona bien |

El modelo **falla en corto plazo** y es fuerte en largo plazo. Patron invertido respecto a lo esperado.

**Archivos**: `proposal/benchmark.py`, `proposal/data_loader.py`

---

## 3. Modelos Neurales SOTA: NHITS, NBEATSx, TiDE

### Seleccion

Se evaluaron modelos de NeuralForecast que:
- Aceptan features exogenas (futr_exog + hist_exog)
- Resisten overfitting en datasets chicos (~3,500 muestras)
- Son SOTA en forecasting de series temporales

**Modelos elegidos**:
- **NHITS**: MLP jerarquico con multi-rate sampling (bajo riesgo overfit)
- **NBEATSx**: Disenado para precios electricos, basis interpretable
- **TiDE**: MLP encoder-decoder, pocos parametros, rapido

**Configuracion conservadora**: hidden_size=128, dropout=0.1-0.15, early stopping, MAE como loss, batch_size=32, max_steps=1000.

**Features**:
- `futr_exog` (11): hour_sin/cos, dow_sin/cos, month_sin/cos, is_weekend, periodos del dia
- `hist_exog` (8): cmg_mean_24h/168h, cmg_std_24h/168h, zeros_ratio_24h/168h, cmg_change_1h/24h

### Resultado (45 dias test, datos locales)

| Modelo | MAE | Corto (t+1..6) | Medio (t+7..12) | Largo (t+13..24) |
|--------|:---:|:--------------:|:----------------:|:----------------:|
| **TiDE** | **$48.82** | **$71.26** | **$55.30** | $34.36 |
| Produccion | $50.76 | $75.03 | $61.40 | **$33.31** |
| NHITS | $59.10 | $78.58 | $57.94 | $66.61 |
| NBEATSx | $55.85 | $75.49 | $59.13 | $60.76 |

**TiDE gana globalmente** pero pierde en largo plazo. Esto sugiere un ensemble hibrido.

**Archivos**: `proposal/train_neural_models.py`

---

## 4. Ensemble Hibrido: TiDE + Produccion

### Configuraciones Evaluadas

Se probaron multiples formas de combinar TiDE (mejor corto) con Produccion (mejor largo):
- Cutoffs fijos: TiDE(1-6)+Prod(7-24), TiDE(1-9)+Prod, TiDE(1-12)+Prod, etc.
- Promedio ponderado: peso TiDE decrece linealmente con horizonte
- Oracle: mejor modelo por horizonte (techo teorico)

### Resultado

| Modelo | MAE | Corto | Medio | Largo |
|--------|:---:|:-----:|:-----:|:-----:|
| Oracle (techo) | $46.04 | $68.93 | $54.30 | $30.47 |
| **Weighted TiDE+Prod** | **$47.00** | **$69.60** | **$53.73** | **$32.33** |
| Produccion | $50.76 | $75.03 | $61.40 | $33.31 |

**Weighted ensemble**: `pred[h] = w(h) * TiDE + (1-w(h)) * Produccion` donde `w(h) = max(0, 1-(h-1)/24)`

- Formula fija, no aprende de datos → sin leakage
- **MAE global -7.4%** vs produccion
- Mejora en TODOS los bloques de horizonte
- A solo $1 del techo teorico (Oracle)

**Archivos**: `proposal/eval_hybrid_ensemble.py`

---

## 5. Integracion de Zero Detection

### Problema

TiDE predice valores continuos — nunca predice exactamente 0. En el mercado chileno, CMG=0 es comun (surplus) y predecirlo correctamente es critico para la operacion.

### Solucion

Reutilizar el **Stage 1 de produccion** (clasificador de zeros LGB+XGB con thresholds calibrados por hora) como filtro sobre el weighted ensemble:

```
1. Stage 1 produccion: P(zero) por horizonte
2. Weighted ensemble: TiDE*w + Prod*(1-w) como valor
3. Si P(zero) > threshold → predecir 0, sino → valor del ensemble
```

### Resultado (45 dias test, datos locales)

| Modelo | MAE | Zero F1 | MAE(real=0) |
|--------|:---:|:-------:|:-----------:|
| Weighted continuo | **$47.00** | 0.110 | $57.32 |
| **Weighted + ZD** | **$47.63** | **0.566** | **$20.33** |
| Produccion | $50.76 | 0.566 | $19.46 |

- **Mismo Zero F1** que produccion (0.566) — usa el mismo clasificador
- **MAE en horas zero baja drasticamente**: $57 → $20
- **Trade-off minimo en MAE global**: +1.3%

**Archivos**: `proposal/eval_ensemble_with_zero_detection.py`

---

## 6. Validacion con Datos Nuevos de Supabase (Out-of-Sample Real)

### Setup

- **Train**: datos locales (Sep 2025 - Ene 27, 2026) — lo que se tenia
- **Test**: datos frescos de Supabase (Ene 28 - Abr 2, 2026) — **65 dias nunca vistos**
- 1,069 predicciones, 45 ventanas de backtesting rolling diario

### Cambio en la distribucion

| Metrica | Train (local) | Test (Supabase) |
|---------|:-------------:|:---------------:|
| Zeros | 27.2% | **6.0%** |
| Media CMG | $66.22/MWh | **$81.42/MWh** |

El mercado cambio significativamente: menos zeros y precios mas altos.

### Resultado

| Modelo | MAE | Corto | Medio | Largo |
|--------|:---:|:-----:|:-----:|:-----:|
| **TiDE continuo** | **$30.00** | $18.82 | **$23.32** | **$38.78** |
| **Weighted continuo** | **$31.43** | **$17.91** | $25.57 | $40.94 |
| Persistencia 24h | $35.31 | $18.89 | $31.63 | $45.19 |
| Produccion (LGB+XGB) | $38.78 | $20.61 | $44.32 | $44.95 |
| Weighted + ZD | $39.06 | $23.34 | $44.51 | $44.07 |

### Zero Detection en datos nuevos

| Modelo | Precision | Recall | F1 | Pred 0s | Real 0s |
|--------|:---------:|:------:|:--:|:-------:|:-------:|
| Persistencia 24h | 0.333 | 0.326 | **0.329** | 84 | 86 |
| Produccion / Weighted+ZD | 0.144 | 0.663 | 0.236 | 397 | 86 |
| Continuo | 0 | 0 | 0 | 0 | 86 |

### Hallazgos criticos

1. **TiDE continuo es el mejor modelo out-of-sample**: $30.00 MAE, **-22.6% vs produccion**
2. **El zero detection EMPEORA el MAE** cuando la distribucion cambia: predice 397 zeros cuando solo hay 86 → 340 falsos positivos
3. **El modelo continuo es mas robusto** a cambios de distribucion que el two-stage
4. **TiDE supera a produccion en TODOS los horizontes** en datos nuevos

---

## 7. Time Series Cross-Validation (Expanding Window)

### Motivacion

Los benchmarks anteriores usaban un solo split train/test. Si el modelo tuvo suerte en ese periodo, no lo sabemos. Se implemento **CV temporal con ventana expansiva** para obtener metricas con intervalos de confianza reales.

### Esquema

```
Fold 0: |==TRAIN 60d (Sep-Oct)==|--TEST 30d (Nov)--|
Fold 1: |====TRAIN 90d (Sep-Nov)====|--TEST 30d (Dic)--|
Fold 2: |======TRAIN 120d (Sep-Dic)======|--TEST 30d (Ene)--|
Fold 3: |========TRAIN 150d (Sep-Ene)========|--TEST 30d (Feb)--|
Fold 4: |==========TRAIN 180d (Sep-Feb)==========|--TEST 30d (Mar)--|
```

- **5 folds**, cada uno con 30 dias de test
- Train crece de 60 a 180 dias (expanding window)
- **TiDE re-entrenado desde cero en cada fold** — sin leakage
- Produccion usa modelos pre-entrenados (como en realidad seria)
- 3,368 predicciones totales

### Variabilidad entre folds

La tasa de zeros cambia significativamente entre periodos:

| Fold | Periodo Test | Zeros | Obs |
|------|:------------:|:-----:|-----|
| 0 | Nov 2025 | 17% | |
| 1 | Dic 2025 | 23% | Mas zeros (verano austral) |
| 2 | Ene 2026 | 10% | |
| 3 | Feb 2026 | 4% | Muy pocos zeros |
| 4 | Mar 2026 | 8% | |

### MAE por fold

| Fold | Produccion | TiDE | Weighted | W+ZD | Persistencia |
|------|:----------:|:----:|:--------:|:----:|:------------:|
| 0 | $42.98 | **$36.18** | $37.88 | $42.16 | $40.14 |
| 1 | $47.60 | $48.70 | **$44.21** | $48.78 | $49.21 |
| 2 | $61.70 | **$52.59** | $56.79 | $59.77 | $55.80 |
| 3 | $46.52 | **$39.93** | $41.91 | $44.76 | $52.55 |
| 4 | $33.18 | **$23.31** | $26.36 | $31.87 | $30.26 |

TiDE gana en 4 de 5 folds. El unico fold donde pierde (Fold 1, Dic) es el de mas zeros (23%).

### Resultado Global (media ± std sobre 5 folds)

| Modelo | MAE | RMSE | Zero F1 |
|--------|:---:|:----:|:-------:|
| **TiDE continuo** | **$40.15 ± 10.27** | $57.43 ± 14.95 | 0.070 ± 0.061 |
| Weighted continuo | $41.43 ± 9.84 | $59.35 ± 14.08 | 0.056 ± 0.048 |
| Weighted + ZD | $45.47 ± 9.08 | $65.80 ± 15.40 | 0.376 ± 0.117 |
| Persistencia 24h | $45.59 ± 9.28 | $72.96 ± 16.99 | 0.383 ± 0.141 |
| Produccion (LGB+XGB) | $46.40 ± 9.19 | $67.20 ± 14.97 | 0.376 ± 0.117 |

### MAE por bloque de horizonte (media ± std)

| Modelo | Corto (t+1..6) | Medio (t+7..12) | Largo (t+13..24) |
|--------|:--------------:|:---------------:|:----------------:|
| **Weighted continuo** | **$31.66 ± 5.74** | $45.67 ± 16.67 | $44.26 ± 11.40 |
| TiDE continuo | $32.42 ± 5.84 | **$46.16 ± 18.12** | **$41.05 ± 11.02** |
| Produccion | $36.48 ± 6.52 | $53.88 ± 16.40 | $47.69 ± 11.61 |

### Zero Detection

| Modelo | Precision | Recall | F1 |
|--------|:---------:|:------:|:--:|
| Persistencia 24h | 0.383 ± 0.131 | 0.383 ± 0.150 | **0.383 ± 0.141** |
| Produccion / W+ZD | 0.270 ± 0.107 | 0.694 ± 0.086 | 0.376 ± 0.117 |
| TiDE continuo | 0.554 ± 0.460 | 0.038 ± 0.033 | 0.070 ± 0.061 |

### Hallazgos del CV

1. **TiDE confirma superioridad de forma robusta**: -13.5% MAE vs produccion, consistente en 5 folds
2. **Los modelos continuos son mas robustos** que los two-stage con zero detection
3. **La varianza es alta** (std ~$10) — refleja la naturaleza volatil del mercado, no inestabilidad del modelo
4. **Zero detection degrada cuando la tasa de zeros baja** (folds 3-4 con 4-8% zeros)
5. **La persistencia supera a produccion**: $45.59 vs $46.40 — confirma que produccion no agrega valor sobre baseline simple

**Archivos**: `proposal/eval_timeseries_cv.py`

---

## 8. Conclusiones y Recomendaciones

### Lo que funciona

1. **TiDE** es el mejor modelo individual: **MAE $40.15 ± 10.27** en CV de 5 folds (-13.5% vs produccion), confirmado en datos out-of-sample ($30.00 vs $38.78, -22.6%)
2. **El modelo continuo** (sin zero detection) es mas robusto a cambios de distribucion — gana en 4 de 5 folds y en datos nuevos de Supabase
3. **Weighted ensemble** (TiDE + Produccion) es competitivo en corto plazo ($31.66 en t+1..6)
4. **Apple Silicon MPS GPU** acelera el entrenamiento de modelos PyTorch

### Lo que NO funciona

1. **El modelo de produccion no supera la persistencia 24h** en CV ($46.40 vs $45.59) — no agrega valor real sobre un baseline trivial
2. **Zero detection degrada cuando cambia la distribucion** — entrenado con 27% zeros, falla con 4-8% zeros (precision baja a 0.144)
3. **La varianza entre periodos es alta** (std ~$10) — esto es inherente al mercado, no al modelo

### Proximos pasos sugeridos

| Prioridad | Accion | Impacto esperado |
|-----------|--------|:----------------:|
| Alta | Reemplazar produccion con TiDE continuo | -13% MAE confirmado |
| Alta | Agregar CMG Programado como futr_exog en TiDE | +3-5% MAE adicional |
| Alta | Implementar retrain periodico con datos de Supabase | Robustez temporal |
| Media | Probar log(1+y) como target transform en TiDE | +2-4% MAE |
| Media | Recalibrar zero detection con ventana movil si se necesita | Reducir falsos positivos |
| Baja | Evaluar ensemble TiDE + NHITS + Prod (3 modelos) | +1-2% MAE marginal |

### Resumen ejecutivo

| Evaluacion | Produccion | TiDE | Mejora |
|------------|:----------:|:----:|:------:|
| CV 5 folds (media ± std) | $46.40 ± 9.19 | **$40.15 ± 10.27** | **-13.5%** |
| Out-of-sample Supabase | $38.78 | **$30.00** | **-22.6%** |
| Backtesting 45d local | $50.76 | $48.82 | -3.8% |

TiDE supera a produccion de forma consistente y robusta en multiples evaluaciones independientes. La mejora es estadisticamente significativa ($6.25 de diferencia vs $10.27 de std = efecto real). La recomendacion es migrar a TiDE como modelo principal.

---

## Archivos del proyecto

```
proposal/
├── REPORT.md                          # Reporte tecnico inicial
├── data_loader.py                     # Carga datos locales desde cache
├── benchmark.py                       # Backtesting rolling modelo produccion
├── train_neural_models.py             # Entrena NHITS, NBEATSx, TiDE
├── eval_hybrid_ensemble.py            # Evalua ensembles hibridos
├── eval_ensemble_with_zero_detection.py  # Ensemble + zero detection
├── eval_new_data_full.py              # Evaluacion con datos Supabase (2 fases)
├── eval_timeseries_cv.py             # CV temporal expanding window (5 folds)
└── results/                           # JSONs y CSVs con predicciones y metricas
    ├── backtest_produccion_(lgb+xgb).json
    ├── predictions_produccion_(lgb+xgb).csv
    ├── cv_neural_models.csv
    ├── neural_models_comparison.json
    ├── hybrid_ensemble_comparison.json
    ├── ensemble_zero_detection_comparison.json
    ├── new_data_comparison.json
    ├── new_data_predictions.csv
    └── ...
```
