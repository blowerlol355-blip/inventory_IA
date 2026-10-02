# FinDocs AI

Plataforma SaaS multiusuario para consultar documentos financieros (facturas, contratos,
estados de cuenta) en lenguaje natural, con **respuestas citadas** al documento y la página
de origen.

No entrena ningún modelo: usa **RAG** (Retrieval-Augmented Generation) sobre Supabase
Postgres + pgvector, con Google Gemini (capa gratuita) como LLM detrás de una interfaz propia: cambiar a Claude
u otro proveedor es solo configuración.

> Proyecto de portafolio. Todos los documentos son **sintéticos**, generados por script.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Auth y organizaciones, subida, parsing/OCR, chat con citas | ✅ Implementada |
| 2 | Agente con herramientas: búsqueda, conversión de formatos y compresión | ✅ Implementado |
| 2 | Extracción estructurada, consultas SQL de totales, revisión de datos | Pendiente |
| 3 | Búsqueda híbrida, reranking, panel de evaluación | Pendiente |
| 4 | Roles por carpeta, defensa contra prompt injection, demo pública | Pendiente |

**Criterio de salida de la Fase 1:** subir un PDF y obtener una respuesta con la cita
correcta. Lo verifica `apps/api/tests/test_api_flow.py` contra PostgreSQL real.

## Arquitectura

```
Navegador (Next.js) ──► API FastAPI ──┬──► Supabase Postgres + pgvector (datos, vectores, cola)
        ▲                             ├──► Supabase Storage (bucket privado, URLs firmadas)
        │ SSE: tokens + citas         ├──► Gemini: agente, clasificación, OCR (o Claude)
        └─────────────────────────────┴──► Gemini embeddings (o Voyage AI)
```

**Una pregunta** (agente con herramientas, ver [ADR-006](docs/adr/006-agente-con-herramientas-de-archivos.md)):
1. El LLM recibe la pregunta y el historial, y decide qué herramientas usar:
   `search_documents`, `list_documents`, `convert_document` o `compress_files`.
2. `search_documents`: embedding de la consulta y búsqueda en pgvector, filtrada por
   `organization_id` antes de llegar al LLM. Devuelve fragmentos numerados.
3. Las herramientas de archivos convierten o comprimen y guardan el resultado en
   `generated_files` (descargable con URL firmada).
4. El LLM responde citando `[1]`, `[2]`… que el backend traduce a `{documento, página}`.
5. Todo llega por streaming (SSE): tokens, progreso de cada herramienta y archivos creados.

Ejemplos: *"¿cuál es el total de la factura F-000003?"*, *"convierte la planilla de gastos a
CSV"*, *"comprime todas las facturas en un ZIP"*, *"baja el peso de la factura escaneada"*.

**Un documento** (worker con cola en Postgres, `FOR UPDATE SKIP LOCKED`):
`pending → processing → parsing → OCR con el LLM (visión) en páginas escaneadas → clasificación (reglas; LLM solo si es ambiguo) →
troceado ~500 tokens, 50 de solapamiento, sin cruzar páginas → embeddings → ready | failed`.

**Formatos:** PDF, Word, Excel (cada hoja es una "página"), PowerPoint (cada diapositiva es una
"página"), CSV, TXT e imágenes (PNG, JPG, WebP, TIFF). El tipo se valida por los bytes del
archivo; CSV y TXT, por extensión más contenido de texto válido.

**Conversiones** (Python puro, sin LibreOffice):

| Desde | Hacia |
|---|---|
| PDF | Word, TXT, PNG / JPG / WebP (varias páginas → ZIP) |
| Word | PDF, TXT |
| Excel | CSV (varias hojas → ZIP), PDF, TXT |
| CSV | Excel, PDF, TXT |
| PowerPoint | PDF (una página por diapositiva), TXT |
| Imagen | PNG, JPG, WebP, PDF |
| TXT | PDF, Word |

Office → PDF conserva texto y tablas, no el diseño original. **Compresión:** ZIP de varios
archivos, o versión liviana de PDFs (reduce las imágenes internas) e imágenes.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16 + TypeScript, Tailwind, shadcn/ui, TanStack Query, react-pdf |
| Documentos | PyMuPDF, python-docx, openpyxl, python-pptx, Pillow |
| API | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic |
| Base de datos | Supabase Postgres + pgvector (HNSW) + full-text (`tsvector`, GIN), RLS activado |
| Archivos | Supabase Storage (bucket privado, URLs firmadas de 5 min) |
| Cola de tareas | Tabla `documents` en Postgres con `SKIP LOCKED` (sin Redis) |
| LLM | Gemini `gemini-3.8-flash` (SDK `google-genai`) o Claude `claude-opus-5-5`, detrás de `services/llm/` |
| Embeddings | Gemini `gemini-embedding-001` o Voyage AI `voyage-4` (1024 dim, multilingüe) |
| Auth | JWT propio (access 15 min + refresh 7 días), contraseñas con Argon2 |
| Calidad | pytest, ruff, mypy, ESLint, GitHub Actions |

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/) (instala Python solo) y Node 20+.

### 1. Servicios externos (gratis para empezar)

1. **Supabase**: crea un proyecto en [supabase.com](https://supabase.com).
   - *Connect* → *Session pooler*: copia la cadena de conexión y cambia
     `postgresql://` por `postgresql+asyncpg://` → `DATABASE_URL`.
   - *Project Settings → API Keys*: la URL del proyecto → `SUPABASE_URL` y una
     **secret key** (`sb_secret_...`) → `SUPABASE_SECRET_KEY`.
   - No hace falta crear tablas ni el bucket: lo hacen la migración y la API.
2. **Google AI Studio** (gratis, sin tarjeta): crea una clave en
   [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → `GEMINI_API_KEY`.
   Cubre el chat, el OCR, la clasificación y los embeddings. La capa gratuita tiene una cuota
   diaria pequeña por modelo: la API usa una cadena de modelos y salta al siguiente cuando
   uno se agota o está saturado.
   Comprueba la clave con `uv run python -m app.scripts.check_ai` (desde `apps/api`).
3. *(Opcional)* Claude y Voyage AI: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`,
   `EMBEDDING_PROVIDER=voyage` + `VOYAGE_API_KEY`. Al cambiar de embeddings, reindexa con
   `uv run python -m app.scripts.reindex`.

```bash
cp .env.example .env    # y completa los valores
```

### 2. API (incluye el worker de ingesta)

```bash
cd apps/api
uv sync
uv run alembic upgrade head          # crea tablas, índices y activa RLS en Supabase
uv run uvicorn app.main:app --reload # http://localhost:8000/docs
```

### 3. Web

```bash
cd apps/web
npm install
npm run dev                          # http://localhost:3000
```

### 4. Documentos de prueba

```bash
uv run --project apps/api python data/generator/generate.py --out data/samples
```

Genera 12 facturas (una escaneada, para probar el OCR), 4 contratos, un estado de cuenta, una
política de gastos (Word), una planilla de gastos con 2 hojas (Excel), una presentación de
resultados (PowerPoint), movimientos (CSV), notas de reunión (TXT), una factura en JPG,
archivos **vacíos** de cada formato en `data/samples/vacios/` y `ground_truth.json` con los
datos exactos de cada uno. Súbelos desde la pantalla Documentos.

Sin API keys de IA puedes probar el flujo con `LLM_PROVIDER=fake` y `EMBEDDING_PROVIDER=hash`
en `.env` (respuestas de prueba que citan la primera fuente; no sirven para medir calidad).

## Tests

```bash
cd apps/api
uv run pytest
uv run ruff check . && uv run mypy app
```

- **Unitarios** (sin red): troceado, parsing de todos los formatos y marcado de páginas para
  OCR, tipo real de archivo, cada conversión y compresión, seguridad de tokens, citas.
- **Integración** (Postgres con pgvector; usan `DATABASE_URL` del `.env` o
  `TEST_DATABASE_URL`; aíslan sus tablas en el esquema `findocs_test` con `schema_translate_map`): flujo completo registro → subida → procesamiento → pregunta → cita en
  la página correcta, OCR de un PDF escaneado, aislamiento entre organizaciones, errores con
  formato uniforme, login/refresh, cola concurrente con `SKIP LOCKED` y el agente
  convirtiendo y comprimiendo archivos (con un proveedor "guionado" en lugar de Claude), sin
  poder tocar archivos de otra organización. Trabajan en el esquema
  `findocs_test`, que se crea y se borra: **no tocan tus tablas reales**. Si no hay base de
  datos, se omiten.

## API

Versionada bajo `/api/v1`; todo salvo `/auth/*` y `/health` exige `Authorization: Bearer`.
Errores con formato uniforme `{code, message, details}`. Límite de 30 preguntas por minuto
por usuario.

| Método | Ruta | Función |
|---|---|---|
| POST | `/auth/register` | Crea organización y usuario administrador |
| POST | `/auth/login` | Access y refresh token |
| POST | `/auth/refresh` | Renueva tokens |
| GET | `/auth/me` | Usuario actual |
| POST | `/documents` | Sube uno o varios archivos (multipart, máx. 20 MB c/u) |
| GET | `/documents` | Lista con filtros `status`, `doc_type` |
| GET | `/documents/events` | Cambios de estado en vivo (SSE) |
| GET | `/documents/{id}` | Metadatos |
| GET | `/documents/{id}/file` | URL firmada temporal |
| POST | `/documents/{id}/retry` | Reintenta un documento fallido |
| DELETE | `/documents/{id}` | Elimina documento y fragmentos |
| POST | `/conversations` | Crea conversación |
| GET | `/conversations` | Lista conversaciones del usuario |
| GET | `/conversations/{id}/messages` | Historial |
| POST | `/conversations/{id}/messages` | Pregunta; respuesta en streaming (SSE): `token`, `tool`, `sources`, `file`, `done` |
| GET | `/files` | Archivos generados por el agente |
| GET | `/files/{id}/url` | URL firmada de descarga |
| DELETE | `/files/{id}` | Elimina un archivo generado |

## Seguridad (Fase 1)

- Toda consulta filtra por `organization_id`; el LLM nunca recibe fragmentos de otra
  organización. Un documento ajeno responde 404 (no se revela que existe).
- Las herramientas del agente validan sus argumentos con Pydantic y actúan siempre con la
  organización del usuario autenticado, nunca con datos que vengan del modelo.
- RLS activado en todas las tablas: la API REST pública de Supabase no expone ningún dato.
- Bucket privado; el navegador solo recibe URLs firmadas que expiran en 5 minutos. La secret
  key de Supabase solo existe en el servidor.
- Tipo de archivo validado por sus bytes, no por la extensión.
- El contenido de los documentos (y de las imágenes en OCR) va delimitado y el prompt indica
  que es dato, no instrucción. La defensa completa contra prompt injection llega en la Fase 4.

## Decisiones técnicas

- [ADR-001: RAG en lugar de fine-tuning](docs/adr/001-rag-en-lugar-de-fine-tuning.md)
- [ADR-002: Embeddings con Voyage AI](docs/adr/002-embeddings-voyage.md)
- [ADR-003: Citas por número de fuente](docs/adr/003-citas-numeradas.md)
- [ADR-004: Un stream SSE de estado por organización](docs/adr/004-stream-de-estado-por-organizacion.md)
- [ADR-005: Supabase y cola de tareas en PostgreSQL](docs/adr/005-supabase-y-cola-en-postgres.md)
- [ADR-006: Agente con herramientas y conversión de archivos](docs/adr/006-agente-con-herramientas-de-archivos.md)
- [ADR-007: Gemini como proveedor gratuito por defecto](docs/adr/007-gemini-proveedor-gratuito.md)

## Estructura

```
findocs-ai/
├── apps/
│   ├── web/                 # Next.js: login, documentos, chat con visor de PDF, archivos
│   └── api/                 # FastAPI + worker de ingesta
│       ├── app/
│       │   ├── api/v1/      # routers por recurso
│       │   ├── core/        # config, BD, seguridad, errores, rate limit
│       │   ├── models/      # SQLAlchemy
│       │   ├── schemas/     # Pydantic
│       │   ├── services/
│       │   │   ├── ingestion/   # parsing, troceado, pipeline (OCR con el LLM)
│       │   │   ├── retrieval/   # embeddings (Gemini/Voyage) y búsqueda
│       │   │   ├── agent/       # agente: bucle, herramientas, fuentes y citas
│       │   │   ├── files/       # conversión de formatos y compresión
│       │   │   ├── llm/         # interfaz común + Gemini + Claude + falso
│       │   │   └── storage.py   # Supabase Storage
│       │   ├── scripts/     # check_ai (claves) y reindex
│       │   └── workers/     # cola en Postgres y worker
│       ├── alembic/
│       └── tests/
├── data/generator/          # documentos sintéticos + verdad de referencia
├── docs/adr/
└── .github/workflows/ci.yml
```
