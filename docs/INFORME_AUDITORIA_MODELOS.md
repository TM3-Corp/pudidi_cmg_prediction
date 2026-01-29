# Informe Pedagógico: Auditoría de Modelos y Prevención de Data Leakage

## Tabla de Contenidos

1. [Introducción](#1-introducción)
2. [¿Qué es el Data Leakage?](#2-qué-es-el-data-leakage)
3. [Análisis del Caso: NeuralProphet](#3-análisis-del-caso-neuralprophet)
4. [Buenas Prácticas: Modelos de Producción](#4-buenas-prácticas-modelos-de-producción)
5. [Comparación de Resultados](#5-comparación-de-resultados)
6. [Lecciones Aprendidas](#6-lecciones-aprendidas)
7. [Conclusiones](#7-conclusiones)

---

## 1. Introducción

Este documento tiene como objetivo servir como guía educativa sobre uno de los errores más comunes y difíciles de detectar en el desarrollo de modelos de predicción de series temporales: el **data leakage** (fuga de datos).

El contexto es el sistema de predicción de Costos Marginales Generados (CMG) del mercado eléctrico chileno, donde se propuso evaluar un nuevo modelo basado en NeuralProphet como alternativa a los modelos de producción actuales (LightGBM + XGBoost).

Durante el proceso de auditoría, se identificó una oportunidad de mejora en la metodología de evaluación del modelo propuesto. Este informe documenta el hallazgo de manera constructiva, con el objetivo de:

- **Explicar** qué es el data leakage y cómo identificarlo
- **Demostrar** cómo los modelos de producción previenen este problema
- **Compartir** las lecciones aprendidas para futuros desarrollos

El propósito de este documento es **educativo**, no crítico. Detectar y corregir estos problemas es parte natural del proceso de desarrollo de modelos de machine learning.

---

## 2. ¿Qué es el Data Leakage?

### 2.1 Una Analogía Simple

> Imagina que estás haciendo un examen de historia sobre la Segunda Guerra Mundial, pero accidentalmente el profesor te deja ver las respuestas mientras haces el examen. Tu calificación será excelente, pero no refleja tu conocimiento real.
>
> Cuando llegue el próximo examen (sin acceso a las respuestas), tu rendimiento será muy diferente.

Esto es exactamente lo que ocurre con el data leakage en modelos de machine learning: el modelo obtiene acceso (directo o indirecto) a información del futuro durante el entrenamiento o evaluación, lo que infla artificialmente sus métricas de rendimiento.

### 2.2 Tipos de Data Leakage en Series Temporales

Existen dos tipos principales de leakage en predicción de series temporales:

#### Tipo 1: Leakage en Features (Ingeniería de Características)

Ocurre cuando se calculan características usando datos que no estarían disponibles en el momento de la predicción.

```python
# INCORRECTO: La media incluye la hora actual
df['cmg_mean_24h'] = df['CMG'].rolling(24).mean()

# CORRECTO: shift(1) excluye la hora actual
shifted_series = df['CMG'].shift(1)
df['cmg_mean_24h'] = shifted_series.rolling(24).mean()
```

#### Tipo 2: Leakage en Evaluación (Rolling Forecast)

Ocurre cuando durante la evaluación se alimentan valores reales al modelo en lugar de sus propias predicciones.

```python
# INCORRECTO: Usa el valor real
nueva_fila = pd.DataFrame({'ds': [fecha_hora], 'y': [valor_real]})

# CORRECTO: Usa el valor predicho
nueva_fila = pd.DataFrame({'ds': [fecha_hora], 'y': [prediccion]})
```

### 2.3 Visualización del Flujo Temporal

```
Tiempo →    t-3    t-2    t-1    t      t+1    t+2    t+3
            ─────────────────────────────────────────────
Conocido:   [✓]    [✓]    [✓]    [?]    [?]    [?]    [?]
            └─────────────────┘   └─────────────────────┘
               PASADO (OK)           FUTURO (NO usar)
                 ↓                        ↓
            Disponible para         Solo disponible
            features y modelo       DESPUÉS del hecho
```

**Regla de oro**: En el momento `t`, solo podemos usar información de `t-1` y anteriores. Cualquier uso de información de `t` o posterior constituye data leakage.

---

## 3. Análisis del Caso: NeuralProphet

### 3.1 El Enfoque Propuesto

El modelo NeuralProphet propuesto utilizaba un enfoque de **rolling forecast** (predicción rodante) con las siguientes características:

- **168 lags autorregresivos** (`n_lags=168`): el modelo usa las últimas 168 horas de CMG como features
- **Predicción hora por hora**: se predice una hora a la vez y se actualiza el histórico
- **Actualización iterativa**: después de cada predicción, se agrega un nuevo punto al histórico

Este es un enfoque válido y común para modelos de series temporales. El problema surgió en la implementación de la actualización del histórico.

### 3.2 El Problema Identificado

Durante la auditoría se identificó que el rolling forecast actualizaba el histórico con **valores reales** en lugar de **valores predichos**:

```python
# ❌ ORIGINAL (con leakage)              # ✅ CORREGIDO (sin leakage)
# ─────────────────────────────────────────────────────────────────────
for i in range(len(df_test)):            for i in range(len(df_test)):
    # Predecir                               # Predecir
    future = model.make_future_dataframe(    future = model.make_future_dataframe(
        df_rolling, periods=1)                   df_rolling, periods=1)
    forecast = model.predict(future)         forecast = model.predict(future)
    prediccion = forecast['yhat1'].iloc[-1]  prediccion = forecast['yhat1'].iloc[-1]

    # Actualizar histórico                   # Actualizar histórico
    nueva_fila = pd.DataFrame({              nueva_fila = pd.DataFrame({
        'ds': [fecha_hora],                      'ds': [fecha_hora],
        'y': [valor_real]  # ← PROBLEMA          'y': [prediccion]  # ← CORRECTO
    })                                       })
    df_rolling = pd.concat(...)              df_rolling = pd.concat(...)
```

La diferencia parece pequeña, pero sus consecuencias son significativas.

### 3.3 Visualización del Impacto

Como el modelo usa 168 lags (`n_lags=168`), cada valor real filtrado contamina las siguientes predicciones:

| Hora de Predicción | Valores Reales en Features | % Contaminación |
|:------------------:|:--------------------------:|:---------------:|
| 1                  | 0                          | 0% (válida)     |
| 6                  | 5                          | 3.0%            |
| 12                 | 11                         | 6.5%            |
| 24                 | 23                         | 13.7%           |

Esto significa que **solo la primera predicción era verdaderamente out-of-sample**. Las demás predicciones tenían acceso progresivo a información del futuro.

### 3.4 Comparación de Métricas

Al corregir la metodología, observamos una diferencia significativa en las métricas:

| Métrica | Con Leakage | Sin Leakage | Observación |
|---------|:-----------:|:-----------:|-------------|
| MAE     | $10.88      | $244.26     | El modelo corregido muestra su rendimiento real |

Esta diferencia de 22x ilustra cuán dramáticamente el data leakage puede distorsionar las métricas de evaluación.

---

## 4. Buenas Prácticas: Modelos de Producción

Los modelos de producción (LightGBM + XGBoost) implementan prácticas rigurosas para prevenir el data leakage. A continuación se documentan estas prácticas como referencia.

### 4.1 El Patrón shift(1)

El archivo `scripts/ml_feature_engineering.py` implementa la regla de oro para evitar leakage en features:

```python
def _add_rolling_features(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
    """
    Add rolling statistics with PROPER SHIFT to prevent leakage

    CRITICAL FIX: shift(1) BEFORE rolling() to exclude current hour
    """
    for window in self.rolling_windows:
        # CORRECTO: shift(1) asegura que solo usamos datos pasados
        shifted_series = df[cmg_column].shift(1)

        # Luego calculamos estadísticas sobre la serie desplazada
        df[f'cmg_mean_{window}h'] = shifted_series.rolling(
            window, min_periods=1
        ).mean()
        # ... más estadísticas
```

*Fuente: `scripts/ml_feature_engineering.py:156-202`*

### 4.2 Ejemplo Visual del Patrón shift(1)

```
Hora:          0      1      2      3      4      ...    24
CMG real:     45.2   48.1   46.3   49.5   47.2   ...   50.1

Sin shift (INCORRECTO para predecir hora 24):
─────────────────────────────────────────────────────────────
mean_24h[hora 24] = mean(CMG de horas 1 a 24)
                          └─── incluye hora 24 = leakage! ───┘

Con shift(1) (CORRECTO para predecir hora 24):
─────────────────────────────────────────────────────────────
mean_24h[hora 24] = mean(CMG de horas 0 a 23)
                          └─── solo datos pasados ✓ ─────────┘
```

### 4.3 Feature Engineering en Producción

El sistema de producción genera características de manera cuidadosa:

| Categoría | Cantidad | Método Anti-Leakage |
|-----------|:--------:|---------------------|
| Lags de CMG | 6 | `shift(lag)` directamente |
| Estadísticas Rolling | 36 | `shift(1)` antes de `rolling()` |
| Patrones de Ceros | 8 | `shift(1)` sobre indicadores |
| Features Temporales | 28 | Derivadas de timestamp (sin leakage) |
| **Total Base** | **78** | |
| Meta-features | 72 | Calculadas sobre features ya seguras |
| **Total** | **150** | |

Cada feature está diseñada para usar **únicamente información disponible en el momento de la predicción**.

---

## 5. Comparación de Resultados

### 5.1 Metodología de Comparación Justa

Para obtener una comparación válida, se aplicó la misma metodología rigurosa a todos los modelos:

| Parámetro | Valor |
|-----------|-------|
| Período de prueba | Últimos 14 días de datos disponibles |
| Tamaño del test | 336 horas |
| Horizontes evaluados | t+1, t+6, t+12, t+24 |
| Método de evaluación | Out-of-sample verdadero (sin leakage) |

### 5.2 Resultados por Horizonte (MAE en USD/MWh)

| Horizonte | Persistence (Baseline) | LightGBM | XGBoost | ML Ensemble | NeuralProphet (Corregido) |
|:---------:|:----------------------:|:--------:|:-------:|:-----------:|:-------------------------:|
| t+1       | $59.36                 | **$46.45** | $60.67 | $53.30     | $184.47                   |
| t+6       | $78.97                 | $69.85   | $70.76  | **$70.09** | $220.26                   |
| t+12      | $93.08                 | $79.53   | **$76.15** | $77.70  | $284.94                   |
| t+24      | $85.78                 | $85.34   | **$73.32** | $78.82  | $287.39                   |
| **PROM**  | **$79.30**             | $70.29   | $70.23  | **$69.97** | **$244.26**               |

### 5.3 Interpretación de Resultados

**ML Ensemble (LightGBM + XGBoost)**:
- Supera al baseline en todos los horizontes
- Mejora promedio del 11.7% sobre persistence
- LightGBM destaca en horizontes cortos (t+1: 22% mejor que baseline)
- XGBoost destaca en horizontes largos (t+24: 14.5% mejor que baseline)

**NeuralProphet (Corregido)**:
- Al corregir la metodología, observamos que el modelo necesita ajustes adicionales
- El rendimiento actual sugiere que la arquitectura o hiperparámetros podrían optimizarse
- Este resultado no invalida el enfoque, sino que muestra la importancia de la evaluación rigurosa

### 5.4 Contexto Histórico de Rendimiento

Para dar contexto a estos números, es útil comparar con el rendimiento histórico documentado:

| Modelo/Período | MAE (USD/MWh) | Metodología | Estado |
|----------------|:-------------:|-------------|:------:|
| ML Producción (histórico) | ~$30-33 | Sin leakage | ✓ Válido |
| ML Ensemble (comparación actual) | $69.97 | Sin leakage | ✓ Válido |
| Persistence Baseline | $79.30 | Sin leakage | ✓ Válido |
| NeuralProphet (original) | $10.88 | Con leakage | Requiere revisión |
| NeuralProphet (corregido) | $244.26 | Sin leakage | ✓ Válido |

**Nota**: La diferencia entre el MAE histórico (~$30-33) y el actual ($69.97) se debe a diferentes períodos de prueba y condiciones del mercado eléctrico. Lo importante es que un MAE de $10.88 era considerablemente más bajo que cualquier modelo previo, lo cual debió ser una señal de alerta.

---

## 6. Lecciones Aprendidas

### 6.1 Checklist Anti-Leakage

Antes de reportar métricas de un modelo de series temporales, verificar:

- [ ] **¿Se usa `shift(1)` antes de `rolling()`?**
  - Las estadísticas rolling deben calcularse sobre datos desplazados

- [ ] **¿La evaluación usa solo datos disponibles en ese momento?**
  - En rolling forecast, actualizar con predicciones, no valores reales

- [ ] **¿El tamaño del test set es suficiente?**
  - Mínimo 720 horas (30 días) para resultados estadísticamente significativos

- [ ] **¿Se compara contra un baseline simple?**
  - Persistence (valor de ayer a la misma hora) es un buen baseline

- [ ] **¿Las métricas son "demasiado buenas" para ser verdad?**
  - Si mejoran significativamente sobre modelos anteriores, investigar

### 6.2 Señales de Alerta

Los siguientes patrones pueden indicar presencia de data leakage:

| Señal | Descripción | Acción Recomendada |
|-------|-------------|---------------------|
| MAE inusualmente bajo | Métricas muy superiores a modelos anteriores | Revisar metodología de evaluación |
| Mejora con el tiempo | Predicciones mejoran conforme avanza el test | Verificar si se filtran valores reales |
| Predicciones "perfectas" | Errores cercanos a cero consistentemente | Auditar el pipeline completo |
| Sin degradación por horizonte | t+24 igual de bueno que t+1 | Analizar features y evaluación |

### 6.3 Mejores Prácticas para Evaluación

1. **Separación temporal estricta**: El conjunto de prueba debe ser posterior al de entrenamiento
2. **Sin información futura**: Verificar que ningún feature use datos del futuro
3. **Múltiples horizontes**: Evaluar t+1, t+6, t+12, t+24 para entender el comportamiento
4. **Baseline obligatorio**: Siempre comparar contra persistence como mínimo
5. **Validación cruzada temporal**: Usar `TimeSeriesSplit` cuando sea posible

---

## 7. Conclusiones

### 7.1 Valor del Proceso de Auditoría

El proceso de auditoría realizado demuestra la importancia de:

- **Revisión metodológica rigurosa** antes de tomar decisiones basadas en métricas
- **Reproducibilidad** de los experimentos para verificar resultados
- **Documentación clara** de la metodología utilizada

Este análisis nos permite tener confianza en las decisiones técnicas del proyecto.

### 7.2 Sobre el Data Leakage

El data leakage es un error **común y fácil de cometer**, especialmente en series temporales donde la frontera entre pasado y futuro es sutil. Los puntos clave son:

- No es un error "grave" sino una oportunidad de aprendizaje
- Puede ocurrir incluso a equipos experimentados
- La detección temprana evita problemas mayores en producción
- La prevención requiere prácticas sistemáticas (como el patrón `shift(1)`)

### 7.3 Recomendación Técnica

Basado en la evaluación rigurosa realizada:

| Modelo | MAE Promedio | vs Baseline | Recomendación |
|--------|:------------:|:-----------:|---------------|
| **ML Ensemble** | **$69.97** | -11.7% | Mantener en producción |
| Persistence | $79.30 | 0% | Baseline de referencia |
| NeuralProphet | $244.26 | +208% | Investigar optimizaciones |

El **ML Ensemble (LightGBM + XGBoost)** continúa siendo la mejor opción para producción, con una mejora consistente sobre el baseline en todos los horizontes de predicción.

### 7.4 Próximos Pasos Sugeridos

Para quien desee continuar explorando NeuralProphet u otros modelos:

1. **Revisar hiperparámetros**: El número de lags (168) podría necesitar ajuste
2. **Experimentar con arquitectura**: Probar diferentes configuraciones de capas
3. **Feature engineering adicional**: Incorporar features externas (temperatura, demanda)
4. **Ensemble híbrido**: Combinar NeuralProphet con modelos de gradient boosting

---

## Referencias

| Archivo | Descripción |
|---------|-------------|
| `scripts/ml_feature_engineering.py` | Implementación de features con prevención de leakage |
| `notebooks/neuralprophet_corrected.ipynb` | Evaluación corregida de NeuralProphet |
| `notebooks/model_comparison_fair.ipynb` | Comparación justa de todos los modelos |
| `docs/MODEL_COMPARISON_REPORT.md` | Reporte técnico detallado de la comparación |

---

*Documento generado: 2026-01-28*
*Sistema de Predicción CMG - Auditoría de Modelos*
