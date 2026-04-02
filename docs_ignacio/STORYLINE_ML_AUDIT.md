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

## 7. Conclusiones y Recomendaciones

### Lo que funciona

1. **TiDE** es el mejor modelo individual, especialmente en corto/medio plazo
2. **Weighted ensemble (TiDE + Produccion)** captura lo mejor de ambos mundos en datos historicos
3. **El modelo continuo** (sin zero detection) es mas robusto a cambios de distribucion
4. **Apple Silicon MPS GPU** acelera el entrenamiento de modelos PyTorch

### Lo que hay que mejorar

1. **Zero detection necesita recalibracion periodica** — los thresholds entrenados con 27% zeros no sirven cuando bajan a 6%
2. **Features de CMG Programado** no se estan usando en TiDE (el documento del jefe reporta +3.9% mejora con ellos)
3. **Log transform** como target no se probo en TiDE (reportado +4.1% mejora en produccion)

### Proximos pasos sugeridos

| Prioridad | Accion | Impacto esperado |
|-----------|--------|:----------------:|
| Alta | Agregar CMG Programado como futr_exog en TiDE | +3-5% MAE |
| Alta | Implementar recalibracion automatica de zero thresholds | Evitar degradacion |
| Media | Probar log(1+y) como target transform en TiDE | +2-4% MAE |
| Media | Conectar Supabase al pipeline de entrenamiento para retrain periodico | Robustez |
| Baja | Evaluar ensemble TiDE + NHITS + Prod (3 modelos) | +1-2% MAE |

### Resumen ejecutivo

El modelo de produccion actual (LGB+XGB two-stage) tiene **MAE $38.78 en datos nuevos**. El modelo TiDE propuesto logra **MAE $30.00 (-22.6%)** con una arquitectura mas simple, sin zero detection, y entrenado solo con datos historicos. La recomendacion es migrar a TiDE como modelo principal y recalibrar el zero detection periodicamente si se requiere prediccion explicita de zeros.

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
