# Oportunidades de Mejora para 2026
**Sistema Pudidi - Roadmap de Innovación**

**Fecha:** 18 de Noviembre, 2025
**Versión:** 1.0

---

## 🎯 RESUMEN EJECUTIVO

Este documento identifica **4 oportunidades clave** para mejorar el Sistema de Predicción CMG durante 2026:

1. **Integración de Pronósticos Hídricos** (Prioridad ALTA)
2. **Re-entrenamiento Automático con Track Error** (Prioridad ALTA)
3. **Optimización Estocástica** (Prioridad MEDIA)
4. **Expansión Multi-Central** (Prioridad MEDIA)

**ROI Estimado:** Incremento potencial del 15-25% en revenue anual

---

## 📍 OPORTUNIDAD 1: Integración de Pronósticos Hídricos

### Problema Actual

El optimizador asume **caudal afluente constante** durante el horizonte de optimización (24-72 horas).

**Supuesto Actual:**
```python
Q_in = (S0 - S_final + Suma_generación) / 24
```

**Limitación:** Ignora variaciones reales del caudal debido a:
- Lluvias pronosticadas
- Deshielo estacional
- Eventos climáticos extremos

### Solución Propuesta

**Usar pronósticos de lluvia para extrapolar caudal afluente variable**

#### Paso 1: Integrar Datos Meteorológicos

**Fuentes Potenciales:**
1. **DMC (Dirección Meteorológica de Chile)**
   - URL: https://www.meteochile.gob.cl
   - Datos: Pronósticos de precipitación 72 horas
   - Cobertura: Puerto Montt, Dalcahue, zona del proyecto
   - **Costo:** GRATIS (API pública)

2. **OpenWeather API**
   - URL: https://openweathermap.org/api
   - Datos: Precipitación horaria pronosticada
   - Resolución: 1 hora
   - **Costo:** ~$40 USD/mes (plan profesional)

3. **NOAA GFS Model** (Global Forecast System)
   - URL: https://nomads.ncep.noaa.gov/
   - Datos: Modelo numérico global, precipitación
   - Resolución: 0.25° (~28 km)
   - **Costo:** GRATIS

**Recomendación:** Comenzar con DMC (gratis) y OpenWeather (backup)

---

#### Paso 2: Modelo Lluvia → Caudal

**Enfoque:** Usar el **estudio hidrológico del proyecto** para calibrar la relación lluvia-caudal

**Ecuación Básica:**
```
Q(t) = Q_base + α * P(t-lag) + β * P(t-2*lag) + ...
```

Donde:
- `Q(t)` = Caudal en hora t (m³/s)
- `Q_base` = Caudal base sin lluvia
- `P(t)` = Precipitación acumulada (mm)
- `lag` = Tiempo de concentración (horas) - del estudio hidrológico
- `α, β` = Coeficientes de respuesta - calibrados con datos históricos

**Parámetros del Estudio Hidrológico Necesarios:**
1. Área de captación (km²)
2. Tiempo de concentración (horas)
3. Coeficiente de escorrentía
4. Curva número (CN) - para diferentes condiciones de humedad

---

#### Paso 3: Integración en el Optimizador

**Modificación del Optimizer:**

**ANTES (Q constante):**
```python
def optimize_hydro_lp(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    # inflow es CONSTANTE
    ...
```

**DESPUÉS (Q variable):**
```python
def optimize_hydro_lp(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow_forecast, horizon):
    # inflow_forecast es un ARRAY de 24-72 valores
    # inflow_forecast[t] = caudal pronosticado para hora t

    for t in range(horizon):
        # Ecuación de balance hídrico con Q variable
        S[t+1] = S[t] + inflow_forecast[t] - P[t] / kappa
    ...
```

**Ventajas:**
- ✅ Aprovecha mejor el recurso hídrico disponible
- ✅ Evita turbinar excesivamente antes de lluvias esperadas
- ✅ Maximiza turbinado durante escasez pronosticada

**Ejemplo Real:**

```
Escenario SIN pronóstico hídrico:
- Hora 0-24: Turbinad o constante 2.5 m³/s
- Hora 12: Lluvia 20mm → Embalse se llena, se pierde agua

Escenario CON pronóstico hídrico:
- Hora 0-11: Turbinado alto 3.2 m³/s (vacía embalse pre-lluvia)
- Hora 12-24: Turbinado bajo 1.8 m³/s (aprovecha afluente de lluvia)
- Resultado: +8% revenue, 0% pérdida de agua
```

---

### Implementación

**Fase 1 (1-2 meses):**
1. Contactar DMC y OpenWeather para APIs
2. Recopilar datos históricos de lluvia y caudal (si disponibles)
3. Calibrar modelo lluvia-caudal usando estudio hidrológico

**Fase 2 (2-3 meses):**
1. Modificar `lib/utils/optimizer_lp.py` para aceptar `inflow_forecast[]`
2. Crear script `scripts/fetch_weather_forecast.py`
3. Integrar en workflow hourly
4. Validar en backtest (datos históricos)

**Fase 3 (1 mes):**
1. Deploy a producción
2. A/B testing: optimizar con Q constante vs Q variable
3. Medir improvement real

**Recursos Necesarios:**
- Desarrollador Python: 40 horas
- Ingeniero Hidrólogo (consultoría): 8-16 horas
- Costo APIs: $40 USD/mes

**ROI Esperado:**
- Incremento revenue: **5-12%**
- Payback: **2-3 meses**

---

## 📍 OPORTUNIDAD 2: Re-entrenamiento Automático + Track Error

### Problema Actual

1. **Modelos ML estáticos** (entrenados Sept 2025, no se actualizan)
2. **Track error del Coordinador NO se usa** como feature

### Solución Propuesta

#### Parte A: Re-entrenamiento Mensual Automático

**Script:** `scripts/auto_retrain_monthly.py`

**Lógica:**
```python
# Ejecutar 1er día de cada mes
1. Fetch últimos 18 meses de datos CMG (Supabase)
2. Re-generar features (78 base features)
3. Entrenar modelos Stage 1 (Zero Detection)
4. Entrenar modelos Stage 2 (Value Prediction)
5. Validar MAE en holdout set
6. Si MAE < MAE_anterior + 10%:
     Deploy nuevos modelos
   Else:
     Alertar y mantener modelos anteriores
```

**Infraestructura:**
- GitHub Actions cron: `0 2 1 * *` (2 AM, día 1 de cada mes)
- Usar Railway con GPU ($20/mes durante entrenamiento)
- Guardar modelos en Railway Volumes (persistente)

**Ventajas:**
- ✅ Modelos siempre actualizados con patrones recientes
- ✅ Captura cambios estructurales del mercado
- ✅ Adaptación a nuevas políticas energéticas

---

#### Parte B: Track Error como Feature

**Hipótesis:** El error histórico del Coordinador es predictivo de su error futuro

**Nuevas Features:**
```python
# Calcular track error cada hora
track_error = cmg_programado - cmg_real

# Features adicionales
features['coordinador_error_mean_6h'] = track_error.shift(1).rolling(6).mean()
features['coordinador_error_mean_24h'] = track_error.shift(1).rolling(24).mean()
features['coordinador_error_std_24h'] = track_error.shift(1).rolling(24).std()
features['coordinador_bias_sign'] = np.sign(track_error.shift(1).rolling(24).mean())
features['coordinador_overestimation'] = (track_error > 5).shift(1).rolling(24).mean()
```

**Ventajas:**
- ✅ Mejora accuracy ML al detectar sesgo sistemático del Coordinador
- ✅ Permite ensemble inteligente (ML vs Programado) basado en track error reciente
- ✅ No requiere nuevas fuentes de datos (ya está en Supabase!)

**Ejemplo:**

```
Escenario: Coordinador sobreestima consistentemente en horas peak

SIN track error feature:
- ML prediction: $45/MWh
- Coordinador: $65/MWh
- Real: $48/MWh
- Error ML: $3, Error Coordinador: $17

CON track error feature:
- ML aprende: "Si Coordinador sobreestima últimas 24h → ajustar hacia abajo"
- ML prediction ajustada: $47/MWh
- Real: $48/MWh
- Error ML: $1 ✅
```

---

### Implementación

**Fase 1 (1 mes):**
1. Implementar cálculo de track error en `lib/utils/supabase_client.py`
2. Agregar 5 features de track error a `scripts/ml_feature_engineering.py`
3. Backtest: Re-entrenar modelos con features nuevas, medir MAE improvement

**Fase 2 (1 mes):**
1. Si MAE mejora > 5%: Deploy modelos con track error
2. Crear `scripts/auto_retrain_monthly.py`
3. Configurar GitHub Actions + Railway

**Fase 3 (ongoing):**
1. Monitoreo mensual de MAE
2. Dashboard con track error visualizado

**Recursos Necesarios:**
- Desarrollador ML: 60 horas
- Railway GPU: $20 USD/mes (solo durante re-entrenamiento)

**ROI Esperado:**
- Reducción MAE: **10-20%**
- Mejora en eficiencia optimización: **5-8%**
- Payback: **4-6 meses**

---

## 📍 OPORTUNIDAD 3: Optimización Estocástica

### Problema Actual

El optimizador es **determinístico** - asume que los precios futuros son conocidos con certeza.

**Realidad:** Los precios son **inciertos** - tienen error

### Solución Propuesta

**Optimización Robusta** - considera intervalos de confianza

#### Enfoque: Two-Stage Stochastic Programming

**Idea:**
```
Generar N escenarios de precios futuros (usando q10, q50, q90 del modelo ML)
Optimizar para minimizar worst-case o maximizar expected value
```

**Ejemplo con 3 escenarios:**

```python
# Escenario 1: Precio bajo (q10)
prices_low = ml_predictions['lower_10th']

# Escenario 2: Precio medio (q50)
prices_mid = ml_predictions['median']

# Escenario 3: Precio alto (q90)
prices_high = ml_predictions['upper_90th']

# Optimizar para maximizar expected revenue
solution = optimize_stochastic([
    (prices_low, prob=0.2),
    (prices_mid, prob=0.6),
    (prices_high, prob=0.2)
])
```

**Ventajas:**
- ✅ Decisiones más robustas ante incertidumbre
- ✅ Evita "all-in" en horas con alta incertidumbre
- ✅ Aprovecha intervalos de confianza ya generados por ML

**Trade-off:**
- Computacionalmente más costoso (3x optimizaciones)
- Revenue esperado ligeramente menor, pero con menos varianza (menos riesgo)

---

### Implementación

**Fase 1 (2 meses):**
1. Implementar `lib/utils/optimizer_stochastic.py`
2. Usar librería `pyomo` o `cvxpy` con soporte para escenarios
3. Backtest con datos históricos

**Fase 2 (1 mes):**
1. A/B testing: optimización determinística vs estocástica
2. Medir Sharpe ratio (revenue/volatilidad)
3. Deploy si mejora riesgo-ajustado

**Recursos Necesarios:**
- Desarrollador especializado en optimización: 80 horas
- Librería: cvxpy (open source, gratis)

**ROI Esperado:**
- Reducción volatilidad revenue: **20-30%**
- Incremento revenue esperado: **0-3%** (neutral a positivo)
- **Valor:** Menor riesgo operacional

---

## 📍 OPORTUNIDAD 4: Expansión Multi-Central

### Contexto

Actualmente el sistema optimiza **una sola central** a la vez (Puerto Montt, Pid-Pid, o Dalcahue).

**Pregunta:** ¿Hay oportunidades de optimización coordinada?

### Escenarios Potenciales

#### Escenario A: Múltiples Centrales en Cascada

Si las centrales están en el mismo río (aguas arriba/abajo):

**Optimización conjunta:**
```
max Σ (Revenue_Central_1 + Revenue_Central_2)

s.t.:
  Q_in_Central_2 = Q_out_Central_1 + Afluentes_intermedios
  ... (constraints normales para cada central)
```

**Ventajas:**
- ✅ Coordina turbinado para maximizar revenue total
- ✅ Evita conflictos operacionales

**Pre-requisitos:**
- Las centrales deben estar hidrológicamente conectadas
- Necesita acuerdo operacional si son diferentes dueños

---

#### Escenario B: Múltiples Centrales Independientes (Portfolio)

Si las centrales son independientes geográficamente:

**Optimización de portfolio:**
```python
# Para cada central i:
solve_optimal_schedule(central_i, params_i)

# Analizar correlación de revenues
corr_matrix = correlate([revenue_1, revenue_2, revenue_3])

# Identificar oportunidades de hedging natural
```

**Insights posibles:**
- Central A tiene mejor performance en verano (deshielo)
- Central B tiene mejor performance en invierno (lluvias)
- Diversificación reduce riesgo

**Valor:**
- Gestión de riesgo de portfolio
- Priorización de inversiones en mantenimiento
- Estrategia comercial (contratos a plazo)

---

### Implementación

**Fase 1 (1 mes):**
1. Investigar topología hidrológica de las centrales
2. Si hay cascada: diseñar optimizador multi-central
3. Si independientes: análisis de portfolio

**Fase 2 (2-3 meses):**
1. Implementar según escenario aplicable
2. Backtest con datos históricos

**Recursos Necesarios:**
- Ingeniero Hidrólogo (consultoría): 16 horas
- Desarrollador: 60 horas

**ROI Esperado:**
- Escenario A (cascada): **8-15%** increment revenue total
- Escenario B (portfolio): **Gestión de riesgo** (valor no-monetario directo)

---

## 🏆 OPORTUNIDADES ADICIONALES (Brainstorming)

### 5. Integración con Mercado Spot de Energía

**Idea:** Participar en arbitraje spot

- Comprar energía barata (CMG bajo) para llenar embalse (bombeo)
- Vender energía cara (CMG alto) turbinando

**Requisitos:**
- Central con capacidad de bombeo (pumped-storage)
- Análisis regulatorio (permisos para comprar energía)

**Valor Potencial:** 20-40% revenue increase si viable

---

### 6. Machine Learning para Detección de Eventos Extremos

**Idea:** Modelo especializado para detectar CMG extremos (>$100/MWh o <$5/MWh)

**Features adicionales:**
- Alertas de mantenimientos programados (centrales grandes)
- Pronósticos de viento (eólica) y lluvia (hidro)
- Precio de combustibles (gas natural, carbón)

**Valor:** Capturar oportunidades de arbitraje en eventos raros

---

### 7. Dashboard Predictivo para Operadores

**Idea:** Herramienta de decisión en tiempo real

**Funcionalidades:**
- Alarma si CMG próximo > $80/MWh → "Turbinar al máximo ahora"
- Recomendación de Q_in esperado próximas 72h
- Simulación "What-if" interactiva

**Valor:** Empodera operadores con información accionable

---

### 8. Integración con Sistema SCADA

**Idea:** Automatización completa

- Sistema lee datos SCADA en tiempo real (nivel embalse, caudal, potencia)
- Ejecuta optimización cada hora
- Envía setpoints automáticamente al PLC

**Requisitos:**
- Integración OPC-UA o Modbus TCP
- Aprobación regulatoria (control automático)

**Valor:** Elimina intervención manual, respuesta inmediata a cambios

---

## 📊 PRIORIZACIÓN Y ROADMAP

### Matriz Impacto vs Esfuerzo

| Oportunidad | Impacto Revenue | Esfuerzo (horas) | Prioridad |
|-------------|----------------|------------------|-----------|
| **1. Pronósticos Hídricos** | 🟢🟢🟢 Alto (5-12%) | 100-120 | **ALTA** |
| **2. Track Error + Auto-retrain** | 🟢🟢 Medio-Alto (5-8%) | 60-80 | **ALTA** |
| **3. Optimización Estocástica** | 🟡 Bajo-Medio (0-3%) | 80-100 | **MEDIA** |
| **4. Multi-Central** | 🟢🟢 Medio (8-15% si cascada) | 80-100 | **MEDIA** |
| **5. Arbitraje Spot** | 🟢🟢🟢 Alto (20-40%) | 200+ | **Explorar** |
| **6. Eventos Extremos** | 🟡 Bajo-Medio (2-5%) | 40-60 | **BAJA** |
| **7. Dashboard Operadores** | ⚪ No-monetario | 60-80 | **MEDIA** |
| **8. Integración SCADA** | ⚪ Eficiencia operativa | 150-200 | **BAJA** |

---

### Roadmap Recomendado 2026

**Q1 2026 (Ene-Mar):**
- ✅ Implementar **Pronósticos Hídricos** (Oportunidad 1)
- ✅ Agregar **Track Error features** (Oportunidad 2A)

**Q2 2026 (Abr-Jun):**
- ✅ Implementar **Re-entrenamiento automático** (Oportunidad 2B)
- ⏳ Investigar **Multi-Central** (Oportunidad 4)

**Q3 2026 (Jul-Sep):**
- ⏳ Implementar **Optimización Estocástica** (Oportunidad 3)
- ⏳ Dashboard Operadores (Oportunidad 7) - si presupuesto disponible

**Q4 2026 (Oct-Dic):**
- ⏳ Evaluar **Arbitraje Spot** (Oportunidad 5) - análisis de viabilidad regulatoria
- ⏳ Explorar integración SCADA (Oportunidad 8) - fase de diseño

---

## 💰 ESTIMACIÓN DE VALOR TOTAL

**Baseline Revenue Anual** (estimado): $150,000 USD

**Con todas las mejoras implementadas:**

| Mejora | Incremento | Revenue Adicional |
|--------|-----------|-------------------|
| Pronósticos Hídricos | +8% | $12,000 USD/año |
| Track Error + Retrain | +6% | $9,000 USD/año |
| Optimización Estocástica | +2% | $3,000 USD/año |
| Multi-Central (si aplica) | +10% | $15,000 USD/año |
| **TOTAL** | **+26%** | **~$39,000 USD/año** |

**Inversión total estimada:** $15,000 - $20,000 USD (desarrollo + consultoría)

**ROI:** 2-2.5x en primer año

**Payback:** 5-6 meses

---

## ✅ CONCLUSIONES Y RECOMENDACIONES

### Recomendaciones Inmediatas (Próximos 3 meses):

1. **PRIORIDAD 1:** Integrar pronósticos hídricos usando DMC + OpenWeather
   - **Acción:** Contactar DMC esta semana, obtener API key
   - **Acción:** Revisar estudio hidrológico del proyecto (área captación, tiempo concentración)

2. **PRIORIDAD 2:** Agregar track error del Coordinador como features ML
   - **Acción:** Modificar `ml_feature_engineering.py` (trabajo de 1 semana)
   - **Acción:** Backtest con datos históricos para validar mejora

3. **Explorar:** Viabilidad de optimización multi-central
   - **Acción:** Reunión con ingeniero hidrólogo para evaluar conectividad

### Consideraciones Clave:

- **Datos son el activo más valioso:** Con 44K registros en Supabase (Oct 20 - presente), ahora tenemos base sólida para entrenar modelos mejores

- **Automatización primero:** Re-entrenamiento manual es insostenible - automatizar antes de escalar

- **Validar siempre en backtest:** Nunca deploy una mejora sin validar en datos históricos

- **ROI >> Costo:** Las oportunidades 1 y 2 tienen payback de 2-6 meses - altamente recomendadas

---

## 📞 PRÓXIMOS PASOS

**Acción Inmediata:**
1. Revisar este documento con equipo técnico
2. Priorizar oportunidades según objetivos de negocio
3. Asignar recursos para Q1 2026 (Pronósticos Hídricos + Track Error)

**Contacto:**
- Para consultas técnicas: Ver `ML_PIPELINE_DOCUMENTATION.md` y `ARCHITECTURE.md`
- Para supuestos del sistema: Ver `SUPUESTOS_SISTEMA.md`

---

**Fecha de Creación:** 18 de Noviembre, 2025
**Autor:** Sistema Pudidi - Documentación Estratégica
**Versión:** 1.0 - Roadmap 2026
