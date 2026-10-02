# ADR-003: Citas por número de fuente

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Cada afirmación de la respuesta debe enlazar al documento y la página de donde sale, y el
enlace debe abrir el PDF en esa página.

## Decisión

Los fragmentos recuperados se numeran `[1..n]` dentro de etiquetas `<fuente>` con su documento
y página. El modelo cita con esos números (`[2]`, `[1][3]`). El backend traduce cada número a
`{document_id, filename, page, snippet}` y guarda solo las fuentes realmente citadas en
`messages.citations`. Los números que no corresponden a ninguna fuente se descartan.

## Consecuencias

- La cita no depende de que el modelo copie bien nombres de archivo o números de página.
- Una cita inventada no puede apuntar a un documento inexistente.
- El frontend convierte `[n]` en botones que abren el visor en la página citada.
- La exactitud de las citas se mide en la Fase 3 comparando con la página esperada.
