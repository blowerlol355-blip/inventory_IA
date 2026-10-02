# ADR-005: Supabase y cola de tareas en PostgreSQL (sin Docker ni Redis)

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

El diseño inicial usaba Docker Compose con PostgreSQL, Redis (cola Arq), MinIO y Tesseract.
Para un proyecto de portafolio importa que cualquiera pueda levantarlo y que la demo pública
cueste cero: sin contenedores locales ni servicios que mantener.

## Decisión

- **Base de datos:** Supabase Postgres (incluye pgvector). Conexión por el *session pooler*
  (IPv4). Cada conexión fija `search_path` a `public, extensions`, porque Supabase instala las
  extensiones en el esquema `extensions`. El esquema de las tablas NO se elige con
  `search_path` sino con `schema_translate_map` de SQLAlchemy (el esquema va escrito en cada
  consulta): el pooler reutiliza conexiones del servidor entre clientes y un `SET` de una sesión
  se filtró a otra durante el desarrollo, mezclando datos de tests con datos reales.
- **Archivos:** Supabase Storage por su API REST, en un bucket **privado** que la API crea al
  arrancar si no existe. El navegador solo recibe URLs firmadas de 5 minutos. La secret key
  viaja en el header `apikey` y nunca llega al frontend.
- **Cola:** la tabla `documents`. Un documento `pending` es un trabajo; el worker lo reclama con
  `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id`, así varios
  workers nunca toman el mismo. Los documentos atascados en `processing` (proceso caído) vuelven
  a la cola tras 15 minutos. Por defecto el worker corre dentro de la API (un solo proceso);
  con `RUN_WORKER_IN_API=false` corre aparte (`python -m app.workers.main`).
- **OCR:** Claude con visión en lugar de Tesseract: no requiere binarios del sistema y lee
  tablas y montos mejor.
- **Rate limit:** se cuentan las preguntas del último minuto en `messages`: funciona igual con
  una o varias réplicas.
- **Seguridad de Supabase:** Supabase publica el esquema `public` por su API REST. Todas las
  tablas tienen RLS activado y sin políticas, así que los roles `anon`/`authenticated` no
  pueden leer nada; la API se conecta como dueña de las tablas.

## Consecuencias

- Para desarrollar basta Python (uv) y Node; nada que instalar en el sistema.
- Menos piezas: sin Redis ni MinIO. La cola en Postgres es suficiente para este volumen y
  transaccional con los datos.
- El OCR consume tokens de Claude (solo en páginas escaneadas).
- Los tests de integración usan un esquema propio (`findocs_test`, vía `schema_translate_map`)
  que se borra y recrea, así que pueden correr contra el mismo proyecto de Supabase sin tocar
  los datos reales. En CI
  corren contra un PostgreSQL con pgvector levantado por GitHub Actions.
