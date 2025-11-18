# Supuestos del Sistema de Predicción CMG - Resumen Ejecutivo

**Sistema Pudidi - Predicción y Optimización de Precios de Energía**
**Fecha:** 18 de Noviembre, 2025

---

## 1. FUENTES DE DATOS

**Datos de Entrada:**
- **CMG Real:** Precios históricos del Coordinador (SIP API)
- **CMG Programado:** Pronósticos oficiales del Coordinador (Portal Coordinador)
- **Features Temporales:** Hora, día de semana, mes, año

**Nodos:** Dalcahue 110kV y Nueva Puerto Montt 220kV

---

## 2. MODELO DE PREDICCIÓN DE CMG

### Arquitectura
**Two-Stage Ensemble** (192 modelos totales)
1. **Etapa 1 - Detección de Zeros:** Identifica cuándo CMG = $0 (96 modelos)
2. **Etapa 2 - Predicción de Valor:** Predice CMG cuando ≠ 0 (96 modelos)

#### ¿Por qué 96 modelos en cada etapa?

**Modelos por horizonte temporal:**
- Se entrenan **modelos independientes** para cada horizonte de predicción (t+1, t+2, ..., t+24)
- **Razón:** La dinámica de predicción cambia con la distancia temporal. Predecir 1 hora adelante es diferente a predecir 24 horas adelante.
- **Ejemplo:** El modelo para t+1 se especializa en patrones de muy corto plazo, mientras que el modelo para t+24 captura ciclos diarios completos.

**Etapa 1: Detección de Zeros (96 modelos)**
```
24 horizontes × 2 algoritmos × 2 niveles = 96 modelos

Algoritmos: LightGBM, XGBoost
Niveles: Base models + Meta models (con features adicionales)
```
- **LightGBM:** Algoritmo gradient boosting optimizado para velocidad
- **XGBoost:** Algoritmo alternativo para diversificación y ensemble
- **Meta models:** Usan predicciones de base models como features adicionales

**Etapa 2: Predicción de Valor (96 modelos)**
```
24 horizontes × 4 tipos = 96 modelos

Tipos: q10, q50 (mediana), q90, XGBoost
```

**Cuantiles para Intervalos de Confianza:**
1. **q10 (Percentil 10):** "90% de probabilidad que el CMG real sea **mayor** a este valor"
   - Escenario pesimista / precio mínimo esperado

2. **q50 (Mediana):** "Valor más probable (50% probabilidad arriba/abajo)"
   - Predicción central / escenario base

3. **q90 (Percentil 90):** "90% de probabilidad que el CMG real sea **menor** a este valor"
   - Escenario optimista / precio máximo esperado

4. **XGBoost:** Algoritmo alternativo para comparación y ensemble

**Ejemplo práctico - Predicción para t+5 (5 horas adelante):**
```
q10:  $45/MWh  →  Rango inferior (90% seguro CMG > $45)
q50:  $62/MWh  →  Valor más probable
q90:  $78/MWh  →  Rango superior (90% seguro CMG < $78)
XGBoost: $60/MWh  →  Predicción alternativa

Intervalo de confianza 80%: [$45 - $78]
```

**Ventaja de múltiples cuantiles:**
- Cuantificación de **incertidumbre** (no solo punto estimado)
- Permite **gestión de riesgo** en optimización (usar q10 para decisiones conservadoras)
- **Análisis de sensibilidad** con escenarios optimista/base/pesimista

### Features Principales (150 features totales)

**A) Features Temporales**
- `hour`: Hora del día (0-23)
- `day_of_week`: Día de semana (0-6)
- `month`: Mes del año (1-12)
- `is_peak_hour`: Horas peak (9-20h)

**B) Features de Lag (Valores Pasados)**
- Lags: 1h, 2h, 3h, 6h, 12h, 24h, 48h, 72h, 168h
- **Supuesto:** Persistencia - el CMG reciente predice el CMG futuro

**C) Rolling Statistics**
- Media móvil: 6h, 12h, 24h
- Desviación estándar: 6h, 12h, 24h
- Min/Max: 12h, 24h
- **Supuesto:** Volatilidad reciente es predictiva

**D) Meta-Features (solo Etapa 2)**
- Probabilidades de zero de Etapa 1 (72 features)
- **Supuesto:** Riesgo de CMG=0 informa predicción de valor

### Feature Importance

**Top 5 Features más importantes:**
1. `cmg_lag_1h` (lag de 1 hora) - **Peso: ~15-20%**
2. `cmg_lag_24h` (lag de 24 horas) - **Peso: ~10-12%**
3. `hour` (hora del día) - **Peso: ~8-10%**
4. `cmg_rolling_mean_24h` (media 24h) - **Peso: ~7-9%**
5. `cmg_rolling_std_24h` (volatilidad 24h) - **Peso: ~6-8%**

**Interpretación:** El modelo se basa principalmente en **persistencia** (valores recientes) y **estacionalidad** (hora del día).
**Nota**: Todos los modelos fueron entrenados con variables meteorológicas. Sin embargo, no aportaron capacidad predictiva al modelo, más allá de lo aportado por los valores pasados de la serie de CMG. Esto puede deberse a que a) los valores de CMG obtenidos ya internalizan fenómenos meteorologicos y b) la predicción del CMG futuro tiene una alta auto-correlación como serie.

### Performance Actual
- **MAE (Mean Absolute Error):** $32.43 /MWh
- **Horizonte:** 24 horas (t+1 hasta t+24)

### Entrenamiento
- **Estado:** **ESTÁTICO** (últimos modelos entrenados en Septiembre 2025)
- **Dataset:** Enero 2023 - Septiembre 2025 (~19,000 registros horarios)
- **Re-entrenamiento:** Manual, no automático
- **Frecuencia recomendada para etapas futuras:** Mensual

---

## 3. OPTIMIZADOR HIDROELÉCTRICO

### Objetivo
Maximizar ingresos por venta de energía dado un pronóstico de precios CMG.

### Parámetros Físicos (Ejemplo)
- **Q_MAX:** 3.75 m³/s (caudal máximo turbinado)
- **Q_MIN:** 0 m³/s (puede dejar de generar)
- **S_MAX:** 28,000 m³ (capacidad máxima embalse)
- **S_MIN:** 0 m³ (embalse puede vaciarse)
- **Eficiencia:** ~98 kW por m³/s turbinado

### Supuestos Clave

**A) Afluente Constante**
- **Supuesto:** El caudal afluente (Q_in) es constante durante el horizonte
- **Limitación:** No considera pronósticos meteorológicos

**B) Ciclicidad del Embalse**
- **Supuesto:** Volumen final = Volumen inicial (operación sostenible)
- **Razón:** No agotar recurso hídrico día a día

### Método de Optimización
- **Técnica:** Linear Programming (LP)
- **Solver:** PuLP (Python)

### Formulación

**Función Objetivo:**
```
Maximizar: Σ (P[t] × CMG[t] × Δt)

Donde:
- P[t] = Potencia generada en hora t (MW)
- CMG[t] = Precio en hora t ($/MWh)
- Δt = 1 hora
```

**Restricciones:**
```
1. Balance hídrico: S[t+1] = S[t] + Q_in - Q_turb[t]
2. Límites de caudal: Q_MIN ≤ Q_turb[t] ≤ Q_MAX
3. Límites de embalse: S_MIN ≤ S[t] ≤ S_MAX
4. Ciclicidad: S[24] = S[0]
5. Conversión: P[t] = κ × Q_turb[t] (κ = eficiencia)
```

---

## 4. SUPUESTOS CRÍTICOS Y LIMITACIONES

### ¿Se usa el Track Error del Coordinador?

**NO.** Actualmente no se utiliza la diferencia entre CMG Programado vs CMG Real como feature.

**Oportunidad identificada:**
- Calcular `track_error = cmg_programado - cmg_real`
- Agregar como features: `track_error_mean_24h`, `track_error_std_24h`
- **Potencial mejora:** 10-20% reducción en MAE

### Limitaciones:

1. **Afluente constante** - No considera variabilidad hidrológica real
2. **Sin pronósticos meteorológicos** - No anticipa cambios en disponibilidad hídrica

---

## 5. OPORTUNIDADES DE MEJORA

### Corto Plazo
1. **Integrar track error** como feature para modelos ML 
2. **Re-entrenamiento automático** mensual vía GitHub Actions
3. **Pronósticos hídricos** usando lluvia proyectada + estudio hidrológico

---