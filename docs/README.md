# 📚 Documentación - Sistema Pudidi CMG Prediction

Documentación completa del sistema de predicción y optimización de precios de energía.

---

## 📖 Índice

### 🎯 [Documentación para Cliente](./client/)

Documentos preparados para entregar al cliente con explicaciones técnicas pero accesibles:

- **[Modelos de Machine Learning](./client/MODELOS_ML_RESUMEN.md)** - Explicación detallada de los 192 modelos ML, variables predictivas, feature importance, y proceso de entrenamiento
- **[Arquitectura de la Plataforma](./client/ARQUITECTURA_PLATAFORMA_RESUMEN.md)** - Diagrama completo de arquitectura con Vercel, Railway, Supabase, y GitHub Actions. Incluye diagramas Mermaid profesionales.

### 🔧 [Documentación Interna](./internal/)

Documentación técnica para desarrolladores y mantenimiento del sistema:

- **[ARCHITECTURE.md](./internal/ARCHITECTURE.md)** - Arquitectura técnica completa con patrones MVC, API endpoints, y estructura de base de datos
- **[CLAUDE.md](./internal/CLAUDE.md)** - Context y continuidad de sesiones para Claude Code, incluye estado actual del proyecto
- **[SUPUESTOS_SISTEMA.md](./internal/SUPUESTOS_SISTEMA.md)** - Supuestos detallados del sistema ML y optimizador
- **[SUPUESTOS_SISTEMA_RESUMEN.md](./internal/SUPUESTOS_SISTEMA_RESUMEN.md)** - Resumen ejecutivo de supuestos
- **[MIGRATION_ROADMAP.md](./internal/MIGRATION_ROADMAP.md)** - Roadmap de migración de Gist a Supabase
- **[DATA_FORMAT_DOCUMENTATION.md](./internal/DATA_FORMAT_DOCUMENTATION.md)** - Formatos de datos y schemas
- **[ML_PIPELINE_DOCUMENTATION.md](./internal/ML_PIPELINE_DOCUMENTATION.md)** - Pipeline completo de ML

### 📊 [Benchmarks](./benchmarks/)

Model performance documentation and experiment logs:

- **[PRODUCTION_MODELS.md](./benchmarks/PRODUCTION_MODELS.md)** - Current production model specifications, architecture, and performance metrics
- **[EXPERIMENTAL_RESULTS.md](./benchmarks/EXPERIMENTAL_RESULTS.md)** - Log of all model experiments with dates, configurations, and results
- **[METHODOLOGY.md](./benchmarks/METHODOLOGY.md)** - Fair evaluation methodology (walk-forward validation, test periods)

### 📘 [Guías](./guides/)

Tutoriales paso a paso para setup y deployment:

- **[START_HERE.md](./guides/START_HERE.md)** - Guía de inicio rápido para nuevos desarrolladores
- **[RAILWAY_DEPLOYMENT_GUIDE.md](./guides/RAILWAY_DEPLOYMENT_GUIDE.md)** - Guía completa de deployment en Railway
- **[RAILWAY_QUICK_START.md](./guides/RAILWAY_QUICK_START.md)** - Quick start para Railway
- **[GITHUB_SECRETS_SETUP.md](./guides/GITHUB_SECRETS_SETUP.md)** - Configuración de secrets para GitHub Actions

---

## 🚀 Quick Links

- **Producción:** https://pudidicmgprediction.vercel.app
- **Repositorio:** https://github.com/TM3-Corp/pudidi_cmg_prediction
- **Supabase Dashboard:** https://btyfbrclgmphcjgrvcgd.supabase.co

---

## 📊 Vista Rápida del Sistema

```
┌─────────────────────────────────────────────────────────┐
│                    USUARIOS FINALES                     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  VERCEL        │
              │  Frontend      │
              │  + API Gateway │
              └───┬────────┬───┘
                  │        │
         ┌────────┘        └──────────┐
         │                            │
         ▼                            ▼
  ┌─────────────┐          ┌──────────────────┐
  │  RAILWAY    │          │  SUPABASE        │
  │  ML Backend │          │  PostgreSQL      │
  │  192 Models │          │  46K+ Records    │
  └─────────────┘          └──────────────────┘
         ▲                            ▲
         │                            │
         └────────────┬───────────────┘
                      │
              ┌───────▼────────┐
              │ GITHUB ACTIONS │
              │ Hourly Updates │
              └────────────────┘
```

---

## 🛠️ Tecnologías

- **Frontend:** HTML5, Vanilla JS, Tailwind CSS, Chart.js
- **Backend:** Python 3.11, FastAPI, Vercel Serverless Functions
- **ML:** LightGBM, XGBoost (192 modelos pre-entrenados)
- **Database:** PostgreSQL 15 (via Supabase)
- **DevOps:** GitHub Actions, Docker, Railway, Vercel
- **Optimization:** PuLP (Linear Programming)

---

## 📝 Contribuir

Para contribuir a la documentación:

1. Edita archivos en la carpeta correspondiente (`client/`, `internal/`, `guides/`)
2. Asegúrate de mantener el formato Markdown
3. Incluye diagramas Mermaid cuando sea apropiado
4. Actualiza este README si agregas nuevos documentos

---

**Última actualización:** Enero 29, 2026
**Mantenido por:** TM3 Corp
