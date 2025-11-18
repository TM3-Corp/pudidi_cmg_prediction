# Supuestos del Sistema de Predicción CMG
**Sistema Pudidi - Predicción y Optimización de Precios de Energía**

**Última actualización:** 18 de Noviembre, 2025
**Versión:** 1.0

---

## 📊 1. FUENTES DE DATOS

### A) CMG Real (Precios Reales del Mercado)
**Fuente:** SIP API - Coordinador Eléctrico Nacional
**URL:** `https://sipub.coordinador.cl/api/integracion/exportData`
**Tipo:** Datos operacionales en tiempo real
**Actualización:** Cada hora (GitHub Actions cron: `0 * * * *`)
**Nodo Principal:** NVA_P.MONTT___220 (Nueva Puerto Montt 220kV)
**Almacenamiento:**
- **Primary:** Supabase tabla `cmg_online` (~1,000 registros activos)
- **Histórico:** Nov 2025 - presente
- **Backup:** GitHub Gist (legacy, Sep 2 - Nov 17)

**Script:** `scripts/smart_cmg_online_update.py`

---

### B) CMG Programado (Pronósticos Oficiales del Coordinador)
**Fuente:** Portal Coordinador - Descarga manual/automática
**URL:** `https://portal.coordinador.cl`
**Tipo:** Pronósticos oficiales a 72 horas
**Actualización:** Cada hora
**Nodo:** NVA_P.MONTT___220
**Almacenamiento:**
- **Primary:** Supabase tabla `cmg_programado` (44,573 registros)
- **Cobertura:** Oct 20, 2025 - presente (29 días backfilled + ongoing)
- **Formato:** Snapshot cada hora con pronósticos para t+1 hasta t+72

**Script:** `scripts/store_cmg_programado.py`

**⚠️ Nota Importante:** Se completó una migración de esquema el 17-18 de Nov 2025:
- Antes: 696 registros con esquema antiguo (datetime, fetched_at, cmg_programmed)
- Después: 44,573 registros con nuevo esquema (forecast_datetime, target_datetime, cmg_usd)

---

### C) Predicciones ML (Modelo Interno)
**Fuente:** Railway ML Backend + Modelos locales
**URL:** Railway servicio privado (acceso vía proxy Vercel)
**Tipo:** Predicciones generadas por modelos LightGBM + XGBoost
**Actualización:** Cada hora (junto con CMG Online)
**Horizonte:** 24 horas (t+1 hasta t+24)
**Almacenamiento:**
- **Primary:** Supabase tabla `ml_predictions` (~1,000 registros)
- **Archivo Local:** `data/ml_predictions/latest.json`
- **Archivo Histórico:** `data/ml_predictions/archive/YYYY-MM-DD-HH.json`

**Script:** `scripts/ml_hourly_forecast.py`

---

## 🤖 2. MODELO DE MACHINE LEARNING

### Arquitectura: Two-Stage Ensemble

**ETAPA 1: Zero Detection (Clasificación Binaria)**
- **Objetivo:** Detectar cuándo CMG = $0 (condiciones de excedente)
- **Modelos:** LightGBM + XGBoost
- **Entrada:** 78 features base (tiempo, lags, estadísticas rolling)
- **Salida:** Probabilidad de CMG = 0 para cada horizonte
- **Calibración:** Umbrales dinámicos por hora del día
- **Total modelos:** 24 horizontes × 2 algoritmos × 2 (base + meta) = **96 modelos**

**ETAPA 2: Value Prediction (Regresión Cuantil)**
- **Objetivo:** Predecir valor exacto del CMG (si no es cero)
- **Modelos:** LightGBM Quantile Regression + XGBoost
- **Entrada:** 78 features base + 72 meta-features (de Etapa 1) = **150 features**
- **Salida:** CMG predicho con intervalos de confianza (q10, q50, q90)
- **Total modelos:** 24 horizontes × 4 tipos (median + q10 + q90 + xgb) = **96 modelos**

**TOTAL:** **192 modelos entrenados**
**Tamaño:** 84 MB (directorio `models_24h/`)
**Almacenamiento:** Local en el servicio Railway

---

## 🔄 3. ENTRENAMIENTO DEL MODELO

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

### ¿Se Sigue Entrenando el Modelo?

**❌ NO** - Los modelos NO se re-entrenan automáticamente

**Razones:**
1. Entrenamiento requiere GPU (costoso en cloud)
2. Proceso toma ~2-3 horas para ambas etapas
3. Requiere validación manual de métricas
4. No hay degradación significativa detectada aún

**Frecuencia Recomendada de Re-entrenamiento:**
- **Mensual:** Actualizar con datos más recientes
- **Después de eventos significativos:** Fallas de grid, cambios de política
- **Si performance degrada:** MAE > 50% sobre baseline

**Métricas de Performance Actuales:**
- Test MAE (Mean Absolute Error): $32.43 /MWh
- Baseline MAE (persistence model): $32.20 /MWh
- **Interpretación:** Modelo ligeramente mejor que "usar valor de ayer"

---

## 📐 4. SUPUESTOS CLAVE DEL MODELO

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
**Supuesto:** El CMG reciente es predictivo del CMG futuro (persistencia)

**Lags usados:**
- 1h, 2h, 3h, 6h, 12h, 24h, 48h, 72h, 168h (1 semana)

**Manejo de datos faltantes:**
- NaN → relleno con 0
- `min_periods=1` en rolling windows (permite cálculo con ventanas incompletas)
- Prevención de data leakage: `shift(1)` antes de rolling stats

---

### C) Rolling Statistics
**Supuesto:** Volatilidad reciente y tendencias son predictivas

**Ventanas:**
- Media móvil: 6h, 12h, 24h
- Desviación estándar: 6h, 12h, 24h
- Min/Max: 12h, 24h

**Crítico:** Se usa `shift(1)` ANTES de calcular rolling para evitar data leakage

---

### D) Estacionalidad Semanal
**Supuesto:** El CMG de la misma hora hace 1 semana es informativo

**Feature:** `cmg_lag_168h` (lag de 7 días)

**Manejo de faltantes:** Backward fill si lag de 7 días no disponible

---

### E) Zero-Risk Meta-Features
**Supuesto:** Predicciones de "riesgo de CMG=0" de diferentes horizontes son informativas

**Features:** 72 meta-features (probabilidades de zero de Etapa 1)

**Uso:** Solo en Etapa 2 (Value Prediction)

---

## 🎯 5. ¿SE USA EL TRACK ERROR DEL COORDINADOR?

### Respuesta: **NO, actualmente NO se usa**

**Track Error** = Diferencia entre CMG Programado vs CMG Real

**Estado Actual:**
- ✅ **Tenemos los datos:** CMG Programado (tabla `cmg_programado`) y CMG Real (tabla `cmg_online`)
- ❌ **NO se calcula track error** en tiempo real
- ❌ **NO se usa para mejorar predicciones ML**

### Oportunidad de Mejora:

**Hipótesis:** El track error del Coordinador podría usarse para:

1. **Calibración adaptativa:**
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

## 🔧 6. SUPUESTOS DE OPTIMIZACIÓN (Optimizer)

### A) Parámetros Físicos
**Supuesto:** Sistema hidroeléctrico con estos parámetros fijos

- **Q_MAX:** 3.75 m³/s (caudal máximo turbinado)
- **Q_MIN:** 0 m³/s (puede dejar de generar)
- **S_MAX:** 28,000 m³ (capacidad máxima embalse)
- **S_MIN:** 0 m³ (embalse puede vaciarse)
- **Eficiencia:** ~98 kW/m³/s (constante simplificada)

**Validez:** Basado en especificaciones técnicas del proyecto

---

### B) Condición de Ciclicidad
**Supuesto:** El embalse debe terminar con la misma cantidad de agua con la que inició

**Constraint:** `S[final] = S[inicial]`

**Razón:** Operación sostenible día a día (no agotar recurso)

**Impacto:** Reduce grados de libertad, pero asegura viabilidad operacional

---

### C) Afluente Constante
**Supuesto:** Caudal afluente (Q_in) es constante durante el horizonte de optimización

**Valor:** Calculado como:
```python
Q_in = (Volumen_inicial - Volumen_final_deseado + Suma_generación) / 24
```

**Limitación:** No considera:
- Variaciones diarias de caudal
- Pronósticos de lluvia
- Estacionalidad

**⚠️ Oportunidad 2026:** Ver Punto 4 - Usar pronósticos de lluvia para estimar afluente variable

---

### D) Precios Conocidos
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

## 📈 7. SUPUESTOS DE PERFORMANCE ANALYSIS

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

## 📋 9. RESUMEN EJECUTIVO

| Aspecto | Estado Actual | Supuesto Clave |
|---------|---------------|----------------|
| **Datos CMG Real** | Supabase (Nov 2025-presente) | SIP API es confiable y actualizado |
| **Datos CMG Programado** | Supabase (Oct 20-presente, 44K registros) | Coordinador publica pronósticos horarios |
| **ML Training** | **ESTÁTICO** (Sept 2025) | Modelo no degrada significativamente |
| **ML Features** | 78 base + 72 meta = 150 | Lags y rolling stats son predictivos |
| **Track Error** | **NO SE USA** | Podría mejorar accuracy si se implementa |
| **Re-training** | Manual (mensual recomendado) | Performance actual es aceptable |
| **Optimización** | Determinística, afluente constante | Precios conocidos, recurso hídrico predecible |
| **Performance** | MAE ~$32/MWh | Comparable a baseline (persistencia) |

---

## ✅ 10. VALIDEZ DE SUPUESTOS

### Validados en Operación:
1. ✅ Patrones de tiempo (hora/día) son predictivos
2. ✅ Lags son informativos (persistencia existe)
3. ✅ CMG Programado del Coordinador es útil como referencia
4. ✅ Optimización LP encuentra soluciones factibles

### Requieren Validación Continua:
1. ⚠️ Performance del modelo vs. baseline (MAE mensual)
2. ⚠️ Completitud de datos (gaps en SIP API)
3. ⚠️ Estabilidad del Railway ML backend

### Oportunidades de Mejora:
1. 💡 Integrar track error del Coordinador como feature
2. 💡 Re-entrenamiento automático mensual
3. 💡 Usar pronósticos de lluvia para estimar afluente variable
4. 💡 Optimización estocástica (manejar incertidumbre de precios)

---

## 📞 CONTACTO Y REFERENCIAS

**Documentación Técnica:**
- `ML_PIPELINE_DOCUMENTATION.md` - Pipeline completo de ML
- `ARCHITECTURE.md` - Arquitectura del sistema
- `CLAUDE.md` - Estado actual y notas de sesión

**Scripts Clave:**
- `scripts/ml_hourly_forecast.py` - Generación de predicciones ML
- `scripts/smart_cmg_online_update.py` - Actualización CMG Real
- `scripts/store_cmg_programado.py` - Almacenamiento CMG Programado

**Base de Datos:**
- Supabase URL: https://btyfbrclgmphcjgrvcgd.supabase.co
- Tablas: `cmg_online`, `cmg_programado`, `ml_predictions`

---

**Fecha de Creación:** 18 de Noviembre, 2025
**Autor:** Sistema Pudidi - Documentación Técnica
**Versión:** 1.0 - Primera Edición Completa
