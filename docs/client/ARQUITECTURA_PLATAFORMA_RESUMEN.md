# Arquitectura de la Plataforma - Sistema de Predicción CMG

**Sistema Pudidi - Predicción de Precios de Energía**
**Documento preparado para:** Cliente
**Fecha:** 21 de Noviembre, 2025

---

## 1. ARQUITECTURA GENERAL

Sistema distribuido con **4 componentes principales**:

| Componente | Tecnología | Función |
|------------|-----------|---------|
| **Frontend + API** | Vercel | 6 Dashboards interactivos + 11 API endpoints |
| **ML Backend** | Railway | Inferencia con 192 modelos ML (103 MB) |
| **Base de Datos** | Supabase | PostgreSQL con 46K+ registros históricos |
| **Automatización** | GitHub Actions | Pipeline de datos horario (ejecuta cada hora :05) |

**URL Producción:** https://pudidicmgprediction.vercel.app

---

## 2. DIAGRAMA DE ARQUITECTURA

```mermaid
graph TB
    Users[👥 USUARIOS FINALES<br/>Navegador Web / Mobile]

    subgraph Vercel[" VERCEL "]
        Frontend[📱 Frontend<br/>6 HTML Dashboards<br/>Vanilla JS + Tailwind]
        API[🔌 API Gateway<br/>11 Python Endpoints<br/>Serverless Functions]
    end

    Railway[🤖 RAILWAY ML BACKEND<br/>FastAPI Server<br/>192 Modelos ML - 103 MB<br/>/ml_forecast, /ml_thresholds]

    Supabase[🗄️ SUPABASE DATABASE<br/>PostgreSQL 15<br/>3 Tablas - 46K+ registros<br/>cmg_online, cmg_programado, ml_predictions]

    subgraph GitHub[" GITHUB ACTIONS "]
        Pipeline[⚙️ Pipeline Horario<br/>Ejecuta cada hora :05<br/>Duración: 2-5 minutos]
    end

    subgraph External[" FUENTES EXTERNAS "]
        SIP[📡 SIP API<br/>CMG Real]
        Coord[🏢 Coordinador<br/>CMG Programado]
        Gist[💾 GitHub Gist<br/>Backup]
    end

    Users -->|HTTPS| Frontend
    Frontend --> API
    API -->|Proxy| Railway
    API -->|Query| Supabase
    Pipeline -->|Store| Supabase
    Pipeline -->|Store| Railway
    Pipeline -->|Backup| Gist
    Pipeline -->|Fetch| SIP
    Pipeline -->|Scrape| Coord
    Pipeline -->|Push & Deploy| Vercel

    style Vercel fill:#0070f3,stroke:#0070f3,stroke-width:2px,color:#fff
    style Railway fill:#0B0D0E,stroke:#0B0D0E,stroke-width:2px,color:#fff
    style Supabase fill:#3ECF8E,stroke:#3ECF8E,stroke-width:2px,color:#000
    style GitHub fill:#24292e,stroke:#24292e,stroke-width:2px,color:#fff
    style External fill:#f6f8fa,stroke:#d0d7de,stroke-width:2px,color:#000
```

---

## 3. FLUJO DE DATOS - PIPELINE HORARIO

**Trigger:** Cada hora a los :05 minutos (ej: 10:05, 11:05, 12:05...)
**Duración:** 2-5 minutos por ejecución
**Workflow:** `.github/workflows/cmg_online_hourly.yml`

```mermaid
flowchart TD
    Start([⏰ Trigger: Cada hora :05]) --> Step1

    Step1[🌐 1. Scrape CMG Programado<br/>Playwright → Portal Coordinador<br/>download_cmg_programado_simple.py]
    Step1 --> Step2

    Step2[📝 2. Procesar CSV<br/>Extrae PMontt220 → JSON<br/>process_pmontt_programado.py]
    Step2 --> Step3

    Step3[📡 3. Fetch CMG Online<br/>SIP API v4 paginación<br/>smart_cmg_online_update.py]
    Step3 --> Step4

    Step4[🤖 4. Generar Predicciones ML<br/>192 modelos → 24h forecast<br/>ml_hourly_forecast.py]
    Step4 --> Step5

    Step5[💾 5. Almacenar en Supabase<br/>INSERT: cmg_online<br/>INSERT: cmg_programado<br/>INSERT: ml_predictions]
    Step5 --> Step6

    Step6[📦 6. Backup en Gist<br/>Dual-write strategy<br/>3 JSON files]
    Step6 --> Step7

    Step7[🔄 7. Sincronizar Cache<br/>cp data/cache/*.json<br/>→ public/data/cache/]
    Step7 --> Step8

    Step8[🚀 8. Git Commit & Push<br/>git push → Vercel deploy<br/>Zero-downtime]
    Step8 --> End

    End([✅ Datos actualizados<br/>Disponible en ~7 minutos])

    style Start fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#fff
    style End fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#fff
    style Step1 fill:#2196F3,stroke:#1976D2,stroke-width:2px,color:#fff
    style Step2 fill:#2196F3,stroke:#1976D2,stroke-width:2px,color:#fff
    style Step3 fill:#2196F3,stroke:#1976D2,stroke-width:2px,color:#fff
    style Step4 fill:#FF9800,stroke:#F57C00,stroke-width:2px,color:#fff
    style Step5 fill:#9C27B0,stroke:#7B1FA2,stroke-width:2px,color:#fff
    style Step6 fill:#9C27B0,stroke:#7B1FA2,stroke-width:2px,color:#fff
    style Step7 fill:#607D8B,stroke:#455A64,stroke-width:2px,color:#fff
    style Step8 fill:#E91E63,stroke:#C2185B,stroke-width:2px,color:#fff
```

---

## 4. COMPONENTES DETALLADOS

### A) Frontend - 6 Dashboards

| Dashboard | Archivo | Función |
|-----------|---------|---------|
| Principal | `index.html` | Precios en tiempo real, gráficos 24h |
| ML Config | `ml_config.html` | Configuración y predicciones ML |
| Optimizador | `optimizer.html` | Optimización hidro con Linear Programming |
| Rendimiento | `rendimiento.html` | Análisis de performance de pronósticos |
| Comparación | `forecast_comparison.html` | Comparación detallada ML vs Coordinador |
| Heatmap | `performance_heatmap.html` | Mapa de calor de accuracy por horizonte |

**Stack:** HTML5 + Vanilla JavaScript + Tailwind CSS + Chart.js

### B) API Gateway - 11 Endpoints

**Datos Core:**
- `GET /api/index.py` - Datos principales del dashboard
- `GET /api/cmg/current.py` - CMG histórico

**ML Predictions:**
- `GET /api/ml_forecast.py` - Predicciones 24h desde Supabase
- `GET /api/ml_thresholds.py` - Umbrales de decisión (proxy a Railway)

**Optimización:**
- `POST /api/optimizer.py` - Optimización lineal de generación

**Performance:**
- `POST /api/performance.py` - Comparar pronósticos vs reales
- `GET /api/performance_heatmap.py` - Heatmap de accuracy
- `GET /api/performance_range.py` - Análisis por rango de fechas
- `GET /api/historical_comparison.py` - Comparación histórica detallada

**Utilidades:**
- `GET /api/cache.py` - Archivos en caché
- `GET /api/debug/supabase.py` - Debug de conexión

### C) ML Backend - Railway

**¿Por qué Railway?**
- Modelos ML pesan **103 MB** → No caben en Vercel (límite 250 MB por función)
- Railway permite containers sin límite de tamaño
- Sin cold starts (container siempre activo)

**Tecnología:**
- FastAPI (Python 3.11)
- 192 modelos pre-entrenados (96 zero detection + 96 value prediction)
- Dockerfile con Python 3.11-slim

**Endpoints:**
- `GET /api/ml_forecast` → Genera predicciones para 24 horas
- `GET /api/ml_thresholds` → Retorna umbrales calibrados
- `GET /health` → Health check

### D) Base de Datos - Supabase

**3 Tablas Principales:**

| Tabla | Registros | Actualización | Función |
|-------|-----------|---------------|---------|
| `cmg_online` | ~1,500 | Cada hora | Precios reales (últimas 48h) |
| `cmg_programado` | 44,573 | Cada hora | Pronósticos Coordinador (Oct 20 - Nov 18) |
| `ml_predictions` | ~1,000 | Cada hora | Predicciones ML (últimos 2 días) |

**Esquema `cmg_programado`:**
```sql
forecast_datetime TIMESTAMPTZ  -- Cuándo se generó el pronóstico
target_datetime TIMESTAMPTZ    -- Qué hora se está prediciendo
horizon INT                    -- Distancia temporal (1-24)
node VARCHAR                   -- Nodo eléctrico (PMontt220)
cmg_usd DECIMAL                -- Precio en USD/MWh
```

### E) Automatización - GitHub Actions

**Workflows Activos:**
1. `cmg_online_hourly.yml` - Pipeline principal (cada hora :05)
2. `daily_optimization.yml` - Optimización diaria (17:00 Chilean time) [Opcional]
3. `cmg_5pm_snapshot.yml` - Snapshot diario [Opcional]

**Ventajas:**
- Gratis (2000 minutos/mes en free tier)
- Logs accesibles 90 días
- Re-intento automático si falla

---

## 5. RESILIENCIA - ESTRATEGIA DUAL-WRITE

Cada dato se escribe simultáneamente en **2 lugares** para garantizar alta disponibilidad:

```mermaid
flowchart LR
    Pipeline[⚙️ GitHub Actions<br/>Pipeline]

    subgraph Primary[" 🎯 PRIMARY STORAGE "]
        Supabase[💾 Supabase PostgreSQL<br/>✓ Queries SQL rápidas<br/>✓ Índices optimizados<br/>✓ Backup automático]
    end

    subgraph Secondary[" 🔄 SECONDARY STORAGE "]
        Gist[📦 GitHub Gist<br/>✓ Sin rate limits<br/>✓ JSON estático<br/>✓ Acceso público]
    end

    Frontend[🖥️ Frontend]
    API[🔌 API]

    Pipeline -->|Write| Supabase
    Pipeline -->|Write| Gist

    API -->|Read| Supabase
    Frontend -.->|Fallback| Gist

    subgraph Recovery[" 🛡️ RECUPERACIÓN AUTOMÁTICA "]
        R1[❌ Si Supabase falla<br/>→ Frontend lee desde Gist]
        R2[❌ Si Railway falla<br/>→ API usa caché de Supabase]
        R3[❌ Si GitHub Actions falla<br/>→ Re-intento próxima hora]
    end

    style Primary fill:#3ECF8E,stroke:#2E7D32,stroke-width:3px,color:#000
    style Secondary fill:#FFC107,stroke:#F57F17,stroke-width:3px,color:#000
    style Recovery fill:#f8f9fa,stroke:#dee2e6,stroke-width:2px,color:#000
    style Supabase fill:#fff,stroke:#3ECF8E,stroke-width:2px
    style Gist fill:#fff,stroke:#FFC107,stroke-width:2px
```

---

## 6. STACK TECNOLÓGICO

### Backend
- Python 3.11 (API + ML + Scripts)
- FastAPI (Railway ML backend)
- LightGBM + XGBoost (192 modelos ML)
- PuLP (Linear programming optimizer)
- Playwright (Web scraping)

### Frontend
- HTML5 + Vanilla JavaScript (ES6+)
- Tailwind CSS 3.x
- Chart.js 4.x

### Database
- PostgreSQL 15 (via Supabase)
- PostgREST (Auto-generated REST API)

### DevOps
- Git + GitHub (Version control)
- GitHub Actions (CI/CD)
- Docker (Railway containerization)

---

## 7. CARACTERÍSTICAS TÉCNICAS CLAVE

### Latencia
- Frontend load: <1 segundo (CDN)
- API response: <500ms promedio
- ML inference: <2 segundos para 24 predicciones

### Confiabilidad
- Uptime: 99%+ (GitHub Actions)
- Dual-write strategy (redundancia)
- Auto-recovery ante fallas

### Seguridad
- HTTPS en todos los endpoints
- Environment variables para credenciales
- CORS configurado
- RLS (Row Level Security) en Supabase

### Actualización
- Pipeline horario automático
- Zero-downtime deployments (Vercel)
- Cache invalidation automático

---

**Documento preparado por:** TM3 Corp para Pudidi
**Contacto técnico:** Ver repositorio GitHub
**URL Repositorio:** https://github.com/TM3-Corp/pudidi_cmg_prediction
