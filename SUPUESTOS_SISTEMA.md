# Supuestos del Sistema de Predicción CMG
**Sistema Pudidi - Predicción y Optimización de Precios de Energía**

**Última actualización:** 18 de Noviembre, 2025
**Versión:** 1.0

---

## 1. FUENTES DE DATOS

### A) CMG Real (Precios Reales del Mercado)
**Fuente:** SIP API - Coordinador Eléctrico Nacional
**URL:** `https://portal.api.coordinador.cl/documentacion?service=sipubv2`
**Tipo:** Datos CMG Online
**Actualización:** Cada hora (Proceso automático en GitHub Actions)
**Nodos Principales:**Dalcahue (110) y Nva. Pto. Montt (220)
---

### B) CMG Programado (Pronósticos Oficiales del Coordinador)
**Fuente:** Portal Coordinador - Descarga manual/automática
**URL:** `https://portal.coordinador.cl`
**Tipo:** Pronósticos oficiales a 72 horas
**Actualización:** Cada hora
**Nodo:** Nva. Pto. Montt (220)


### C) Predicciones ML (Modelo Interno)
**Fuente:** Railway ML Backend + Modelos locales
**URL:** Railway servicio privado (acceso vía proxy Vercel)
**Tipo:** Predicciones generadas por modelos LightGBM + XGBoost
**Actualización:** Cada hora (junto con datos actualizados de CMG Online)
**Horizonte:** 24 horas (t+1 hasta t+24)
---

## 2. MODELO DE MACHINE LEARNING

### Arquitectura: Two-Stage Ensemble

**ETAPA 1: Zero Detection (Clasificación Binaria)**
- **Objetivo:** Detectar cuándo CMG = $0 (condiciones de excedente)
- **Modelos:** LightGBM + XGBoost
- **Entrada:** 78 features base (tiempo, lags, estadísticas rolling)
- **Salida:** Probabilidad de CMG = 0 para cada horizonte
- **Calibración:** Umbrales de decisión definidos en base a maximización de ingresos 
- **Total modelos:** 24 horizontes × 2 algoritmos × 2 (base + meta) = **96 modelos**

**ETAPA 2: Value Prediction (Regresión Cuantil)**
- **Objetivo:** Predecir valor exacto del CMG (si no es cero)
- **Modelos:** LightGBM Quantile Regression + XGBoost
- **Entrada:** 78 features base + 72 meta-features (de Etapa 1) = **150 features**
- **Salida:** Valor de CMG con intervalos de confianza (q10, q50, q90)
- **Total modelos:** 24 horizontes × 4 tipos (median + q10 + q90 + xgb) = **96 modelos**

**TOTAL:** **192 modelos entrenados**

---

## 3. ENTRENAMIENTO DEL MODELO

### Estado Actual: **Modelos Estáticos (entrenados una vez)**

**Fecha de Último Entrenamiento:**
- Zero Detection: ~Septiembre 2025
- Value Prediction: ~Septiembre 2025

**Datos de Entrenamiento:**
- **Dataset:** `traindataset_2023plus.parquet`
- **Rango:** Enero 2023 - Septiembre 2025 (~19,000 registros horarios)
- **Tamaño:** 2.3 MB comprimido
- **Cobertura:** ~2.5 años de datos históricos

**Scripts de Entrenamiento:**
- `scripts/train_zero_detection_models_gpu.py` (Etapa 1)
- `scripts/train_value_prediction_gpu.py` (Etapa 2)


**Razones:**
1. Entrenamiento requiere GPU (costoso en cloud)
2. Proceso toma ~2-3 horas para ambas etapas
3. Requiere validación manual de métricas
4. No hay degradación significativa detectada aún

**Frecuencia Recomendada de Re-entrenamiento:**
- **Mensual:** Actualizar con datos más recientes
- **Después de eventos significativos:** Fallas de grid, cambios de política
- **Si performance degrada:** MAE > 50% sobre baseline
---

## 4. SUPUESTOS CLAVE DEL MODELO

### A) Features de Tiempo
**Supuesto:** Patrones estacionales y hora del día son predictivos

**Features:**
- `hour`: Hora del día (0-23)
- `day_of_week`: Día de la semana (0-6)
- `month`: Mes del año (1-12)
- `is_weekend`: Binario (sábado/domingo)
- `is_peak_hour`: Binario (horas 9-20)

**Validez:** Históricamente comprobado - CMG tiene patrones diurnos y semanales

---

### B) Features de Lag (Valores Pasados)
**Supuesto:** El CMG reciente es predictivo del CMG futuro (fuerte auto-correlación de la serie)

**Lags usados:**
- 1h, 2h, 3h, 6h, 12h, 24h, 48h, 72h, 168h (1 semana)

---

### C) Rolling Statistics
**Supuesto:** Volatilidad reciente y tendencias son predictivas

**Ventanas:**
- Media móvil: 6h, 12h, 24h
- Desviación estándar: 6h, 12h, 24h
- Min/Max: 12h, 24h

---

### D) Estacionalidad Semanal
**Supuesto:** El CMG de la misma hora hace 1 semana es informativo

**Feature:** `cmg_lag_168h` (lag de 7 días)
---

### E) Zero-Risk Meta-Features
**Supuesto:** Predicciones de "riesgo de CMG=0" de diferentes horizontes son informativas

**Features:** 72 meta-features (probabilidades de zero de Etapa 1)

**Uso:** Informar predicciones en Etapa 2 (Value Prediction) en caso de predicción de CMG != 0.

---

## 5. ¿SE USA EL TRACK ERROR DEL COORDINADOR?

**Estado Actual:**
- **Tenemos los datos:** CMG Programado y CMG Real (Online)
- **NO se calcula track error** en tiempo real, representa oportunidad de mejora.

### Oportunidad de Mejora:

**Hipótesis:** El track error del Coordinador podría usarse para:

1. **Calibración adaptativa:**
pseudocódigo:

   ```python
   if coordinador_overestimates_recently:
       apply_correction_factor = 0.95  # Reduce predicción
   ```

2. **Feature adicional:**
   - `mean_track_error_24h`: Error promedio del Coordinador últimas 24h
   - `trend_track_error`: Si el error está creciendo o decreciendo

3. **Ensemble inteligente:**
   - Combinar ML prediction + CMG Programado según performance reciente
   - Peso dinámico basado en track error

**Implementación recomendada:**
```python
# Calcular track error cada hora
track_error = cmg_programado - cmg_real

# Usar como feature
features['coordinador_error_mean_24h'] = track_error.rolling(24).mean()
features['coordinador_error_std_24h'] = track_error.rolling(24).std()
```

**Ventajas:**
- Aprovechar información valiosa ya disponible
- Mejorar accuracy sin re-entrenar modelo completo
- Adaptación rápida a cambios en performance del Coordinador

**Estado:** **⏳ Pendiente de implementación**

---

## 6. SUPUESTOS DE OPTIMIZACIÓN (Optimizer)


### A) Afluente Constante
**Supuesto:** Caudal afluente (Q_in) es constante durante el horizonte de optimización

**Valor:** Calculado como:
```python
Q_in = (Volumen_inicial - Volumen_final_deseado + Suma_generación) / 24
```

**Limitación:** No considera:
- Variaciones diarias de caudal
- Pronósticos de lluvia
- Estacionalidad

**Oportunidad 2026:** Ver Punto 4 - Usar pronósticos de lluvia para estimar afluente variable

---

### B) Precios Conocidos
**Supuesto:** Los precios futuros son conocidos con certeza

**Fuentes usadas:**
- **Opción 1:** CMG Programado (pronóstico Coordinador)
- **Opción 2:** ML Predictions (modelo interno)

**Realidad:** Los precios son inciertos

**Implicación:** La optimización es determinística (no maneja incertidumbre)

**Mejora posible:**
- Optimización robusta (considera intervalos de confianza)
- Stochastic programming (múltiples escenarios)

---

## 7. SUPUESTOS DE PERFORMANCE ANALYSIS

### A) Métricas Usadas
**MAE (Mean Absolute Error):** Error promedio absoluto

```
MAE = mean(|predicción - real|)
```

**Supuesto:** MAE es suficiente para evaluar modelo

**Otras métricas NO usadas actualmente:**
- RMSE (penaliza errores grandes más)
- MAPE (error porcentual)
- Accuracy en detectar zeros
- Revenue loss (error ponderado por precio)

---

### B) Horizonte de Evaluación
**Supuesto:** Evaluamos performance a 24 horas (todos los horizontes juntos)

**No evaluamos:**
- Performance por horizonte (t+1 vs t+24)
- Performance por hora del día
- Performance por condición de mercado (escasez vs excedente)

---

## 🔍 8. LIMITACIONES Y SUPOSICIONES CONOCIDAS

### A) Datos
- ✅ **Disponemos:** CMG Real, CMG Programado, ML Predictions
- ❌ **NO disponemos:** Pronósticos meteorológicos integrados
- ❌ **NO disponemos:** Datos de demanda/oferta del sistema
- ❌ **NO disponemos:** Precios de combustibles
- ❌ **NO disponemos:** Estado de centrales (mantenimientos)

### B) Modelo
- ✅ **Fortaleza:** Robusto a datos faltantes
- ✅ **Fortaleza:** Intervalos de confianza (quantile regression)
- ❌ **Debilidad:** No se re-entrena automáticamente
- ❌ **Debilidad:** No usa track error del Coordinador
- ❌ **Debilidad:** No captura eventos extremos bien

### C) Optimización
- ✅ **Fortaleza:** Solución óptima garantizada (LP)
- ✅ **Fortaleza:** Rápida (~1 segundo)
- ❌ **Debilidad:** Determinística (no maneja incertidumbre de precios)
- ❌ **Debilidad:** Afluente constante (no realista)
- ❌ **Debilidad:** No considera costos de arranque/parada

### D) Infraestructura
- ✅ **Fortaleza:** Supabase (sin límite de storage)
- ✅ **Fortaleza:** Actualizaciones horarias automáticas
- ✅ **Fortaleza:** Frontend rápido y responsivo
- ❌ **Debilidad:** Railway ML backend (single point of failure)
- ❌ **Debilidad:** Depende de API del Coordinador (puede fallar)

---

