# Modelos de Machine Learning - Sistema de Predicción CMG

**Sistema Pudidi - Predicción de Precios de Energía**
**Documento preparado para:** Cliente
**Fecha:** 21 de Noviembre, 2025

---

## 1. ARQUITECTURA DEL MODELO

### Two-Stage Ensemble System

El sistema utiliza **192 modelos** organizados en 2 etapas:

#### **Etapa 1: Detección de Zeros (96 modelos)**
- **Objetivo:** Identificar cuándo el CMG será $0 (condiciones de excedente de energía)
- **Modelos:** LightGBM + XGBoost
- **Estructura:** 24 horizontes × 2 algoritmos × 2 niveles (base + meta) = **96 modelos**
- **Salida:** Probabilidad de CMG = 0 para cada hora futura (t+1 hasta t+24)

#### **Etapa 2: Predicción de Valor (96 modelos)**
- **Objetivo:** Predecir el valor exacto del CMG cuando ≠ 0
- **Modelos:** LightGBM Quantile Regression + XGBoost
- **Estructura:** 24 horizontes × 4 tipos (q10, q50, q90, XGB) = **96 modelos**
- **Salida:** Intervalos de confianza (percentiles 10, 50, 90) más predicción XGBoost

**¿Por qué modelos separados por horizonte?**
Se entrena un modelo independiente para cada hora futura (t+1, t+2, ..., t+24) porque predecir 1 hora adelante tiene dinámicas diferentes a predecir 24 horas adelante.

---

## 2. FUENTES DE DATOS Y ENTRENAMIENTO

### Datos de Entrenamiento
- **Periodo:** Enero 2023 - Septiembre 2025 (~19,000 registros horarios)
- **Tamaño dataset:** 2.3 MB (`traindataset_2023plus.parquet`)
- **Frecuencia:** Datos horarios de CMG Real del Coordinador Eléctrico

### Entrenamiento
- **Estado actual:** **ESTÁTICO** (última actualización: Septiembre 2025)
- **Frecuencia:** Manual, no automático
- **Tiempo de entrenamiento:** ~2-3 horas (requiere GPU)
- **Frecuencia recomendada:** Mensual

### Fuentes de Datos para Predicción
1. **CMG Real (Histórico):** API SIP del Coordinador Eléctrico
2. **CMG Programado:** Pronósticos oficiales del Coordinador (72 horas)
3. **Features temporales:** Generadas automáticamente (hora, día, mes, etc.)

---

## 3. VARIABLES DEL MODELO (150 Features Totales)

### A) Features Temporales (5 variables)
- `hour`: Hora del día (0-23)
- `day_of_week`: Día de la semana (0-6)
- `month`: Mes (1-12)
- `is_weekend`: Sábado/Domingo (0/1)
- `is_peak_hour`: Horas peak 9-20h (0/1)

### B) Features de Lag - Valores Pasados (9 variables)
- Valores históricos de CMG: 1h, 2h, 3h, 6h, 12h, 24h, 48h, 72h, 168h atrás
- **Rationale:** El CMG reciente predice el CMG futuro (persistencia temporal)

### C) Rolling Statistics - Estadísticas Móviles (18 variables)
- **Media móvil:** ventanas de 6h, 12h, 24h
- **Desviación estándar:** ventanas de 6h, 12h, 24h
- **Min/Max:** ventanas de 12h, 24h
- **Rationale:** Capturan tendencias y volatilidad reciente

### D) Meta-Features de Etapa 1 (72 variables - solo Etapa 2)
- Probabilidades de zero de todos los modelos de Etapa 1
- **Rationale:** El riesgo de CMG=0 informa la predicción de valor

### E) Features Adicionales (46 variables)
- Interacciones entre variables temporales
- Ratios entre lags
- Diferencias entre periodos

**Total: 150 features** alimentan los modelos de Etapa 2

---

## 4. FEATURE IMPORTANCE - VARIABLES MÁS PREDICTIVAS

### Top 5 Features (Etapa 2 - Predicción de Valor)

| Rank | Feature | Peso | Interpretación |
|------|---------|------|----------------|
| 1 | `cmg_lag_1h` | ~15-20% | CMG de hace 1 hora - **Persistencia inmediata** |
| 2 | `cmg_lag_24h` | ~10-12% | CMG de hace 24 horas - **Patrón diario** |
| 3 | `hour` | ~8-10% | Hora del día - **Estacionalidad horaria** |
| 4 | `cmg_rolling_mean_24h` | ~7-9% | Media móvil 24h - **Tendencia reciente** |
| 5 | `cmg_rolling_std_24h` | ~6-8% | Volatilidad 24h - **Incertidumbre del mercado** |

**Conclusión clave:** El modelo se basa principalmente en:
- ✅ **Persistencia:** Valores recientes del CMG (lags 1h, 24h)
- ✅ **Estacionalidad:** Hora del día y patrones diarios
- ✅ **Tendencias:** Medias móviles y volatilidad reciente

---

## 5. PROCESO DE PREDICCIÓN EN TIEMPO REAL

### Flujo cada hora (automático vía GitHub Actions):

```
1. Obtener CMG Real más reciente (API Coordinador)
   └─ Actualiza features de lag y rolling statistics

2. Generar features temporales
   └─ Calcula hora, día de semana, is_peak_hour, etc.

3. Etapa 1: Detectar riesgo de Zero
   └─ 96 modelos generan probabilidades P(CMG=0) para t+1...t+24

4. Etapa 2: Predecir valor si CMG ≠ 0
   └─ 96 modelos usan features + probabilidades de Etapa 1
   └─ Generan intervalos de confianza (q10, q50, q90)

5. Almacenar en Supabase
   └─ Predicciones disponibles en dashboard web
```

**Tiempo total:** ~2-5 segundos por actualización horaria

---

## 6. INTERVALOS DE CONFIANZA (QUANTILE REGRESSION)

El sistema no solo predice un valor puntual, sino **intervalos de confianza**:

| Cuantil | Significado | Uso |
|---------|-------------|-----|
| **q10** | 90% prob. que CMG real > este valor | Escenario pesimista |
| **q50** | Valor más probable (mediana) | Escenario base |
| **q90** | 90% prob. que CMG real < este valor | Escenario optimista |

**Ejemplo práctico para 5 horas adelante:**
```
q10:  $45/MWh  →  Límite inferior con 90% confianza
q50:  $62/MWh  →  Predicción central
q90:  $78/MWh  →  Límite superior con 90% confianza

Intervalo de confianza 80%: [$45 - $78]
```

Esta cuantificación de incertidumbre permite **gestión de riesgo** en optimización.

---

## 7. PERFORMANCE ACTUAL

### Métricas de Evaluación
- **MAE (Mean Absolute Error):** $32.43 /MWh
- **Horizonte:** Promedio sobre 24 horas (t+1 hasta t+24)
- **Dataset de validación:** Últimos 2 meses de datos (no usados en entrenamiento)

### Interpretación
- En promedio, las predicciones difieren del CMG real en $32.43 /MWh
- El modelo captura bien la estructura temporal (ciclos diarios, persistencia)
- Desempeño superior a usar CMG Programado del Coordinador (MAE ~$45 /MWh)

---

## 8. NOTA SOBRE VARIABLES METEOROLÓGICAS

Durante el desarrollo, **se probaron variables meteorológicas** (temperatura, precipitación, etc.) como features adicionales.

**Resultado:** No aportaron capacidad predictiva significativa más allá de los valores pasados de CMG.

**Hipótesis:**
1. Los valores de CMG ya internalizan fenómenos meteorológicos
2. La predicción del CMG tiene muy alta auto-correlación como serie temporal
3. Las variables temporales (hora, día, mes) capturan estacionalidad suficiente

Por esta razón, **el modelo final NO usa variables meteorológicas**.

---

## 9. LIMITACIONES Y MEJORAS FUTURAS

### Limitaciones Actuales
- ✅ Modelos estáticos (no se re-entrenan automáticamente)
- ✅ No captura bien eventos extremos (outliers)
- ✅ No usa el track error del Coordinador como feature

### Mejoras Planificadas
- 🔄 Re-entrenamiento automático mensual
- 🔄 Integrar track error (diferencia CMG Programado vs Real)
- 🔄 Ensemble con CMG Programado para mejorar robustez

---

**Contacto técnico:** Sistema desarrollado por TM3 Corp para Pudidi
**Documentación completa:** Ver `ARCHITECTURE.md` y `SUPUESTOS_SISTEMA.md` en repositorio
