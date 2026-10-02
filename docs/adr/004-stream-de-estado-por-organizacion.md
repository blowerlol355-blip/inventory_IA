# ADR-004: Un stream SSE de estado por organización

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

El diseño original propone `GET /documents/{id}/status` (SSE) por documento. Al subir muchos
archivos a la vez, el navegador abriría una conexión por documento y, con HTTP/1.1, solo
mantiene ~6 conexiones simultáneas por dominio: el resto de peticiones (incluido el chat)
quedaría bloqueado.

## Decisión

Un único endpoint `GET /api/v1/documents/events` emite un evento `document` cada vez que cambia
el estado de cualquier documento de la organización del usuario. El frontend abre una sola
conexión y actualiza la caché de TanStack Query. El servidor consulta cambios cada 1,5 s.

## Consecuencias

- Una conexión por pestaña, independientemente de cuántos documentos se suban.
- El sondeo a la base es barato a esta escala; si crece, se puede reemplazar por
  `LISTEN/NOTIFY` de PostgreSQL o pub/sub de Redis sin cambiar el contrato del endpoint.
