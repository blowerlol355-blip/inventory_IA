# ADR-002: Embeddings con Voyage AI

- **Estado:** aceptada (reemplaza la versión inicial con un modelo local)
- **Fecha:** 2026-10-01

## Contexto

Claude no ofrece un endpoint de embeddings. Los documentos están en español y se trocean en
fragmentos de ~500 tokens. El proyecto se despliega sin Docker, en servicios con capa gratuita
(512 MB de RAM habituales).

## Opciones consideradas

| Opción | Límite de entrada | Requisitos | Problema |
|---|---|---|---|
| paraphrase-multilingual-MiniLM (local) | 128 tokens | 0,2 GB | Truncaría ~75% de cada fragmento |
| multilingual-e5-large (local) | 512 tokens | ~3 GB de RAM, 2,2 GB de descarga | No cabe en un hosting gratuito |
| **Voyage AI `voyage-4` (API)** | 32.000 tokens | API key | Dependencia externa, costo por token |

## Decisión

`voyage-4` vía el SDK oficial (`voyageai.AsyncClient`), dimensión 1024, multilingüe. Es el
proveedor de embeddings que recomienda Anthropic. Se usa `input_type="document"` al indexar y
`input_type="query"` al buscar, lo que mejora la recuperación. Los fragmentos se envían en
lotes de 64 con reintentos automáticos.

## Consecuencias

- El servidor no carga ningún modelo: arranca rápido y cabe en 512 MB.
- Los fragmentos de 500 tokens se embeben completos (el límite es 32K).
- Una API key más (`VOYAGE_API_KEY`). Sin método de pago, Voyage limita mucho las peticiones
  por minuto; con uno, los primeros 200M tokens siguen siendo gratuitos.
- La interfaz `Embedder` permite cambiar de proveedor; cambiar la dimensión exige migrar la
  columna `chunks.embedding` y reindexar.
- Los tests usan un embedder determinista por hashing: sin red ni costo.
