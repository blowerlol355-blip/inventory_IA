# ADR-006: Agente con herramientas y conversión de archivos en Python puro

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

El chat era un flujo fijo (reescribir → buscar → responder). Los usuarios también quieren
pedirle a la IA tareas sobre sus archivos: "convierte la planilla a CSV", "comprime todas las
facturas en un ZIP", "baja el peso de este escaneo". El diseño de la Fase 2 ya preveía que el
LLM eligiera herramientas (tool use).

## Decisión

**Agente con cuatro herramientas** (`services/agent/tools.py`):

| Herramienta | Qué hace |
|---|---|
| `search_documents` | Búsqueda vectorial con fuentes numeradas para citar |
| `list_documents` | Lista documentos y archivos generados, con ids y formatos convertibles |
| `convert_document` | Convierte un archivo a otro formato |
| `compress_files` | ZIP de varios archivos o versión liviana de PDFs e imágenes |

- **Bucle manual** en lugar del tool runner del SDK: necesitamos tokens en vivo hacia el
  navegador, eventos de progreso por herramienta (`tool`, `sources`, `file`), el contexto del
  usuario autenticado en cada herramienta y una interfaz de LLM propia (independiente del
  proveedor). Los turnos del modelo se reenvían sin modificar dentro del bucle (Claude exige
  devolver intactos sus bloques de razonamiento) y los resultados de varias herramientas van
  juntos en un solo mensaje. Máximo 8 pasos por pregunta.
- **Seguridad:** herramientas con `strict: true`; aun así cada argumento se valida con Pydantic
  antes de ejecutar (los esquemas estrictos no admiten límites de longitud ni de cantidad). El
  `organization_id` sale siempre del usuario autenticado; un id de otra organización se trata
  como inexistente. Un error de herramienta vuelve al modelo como `is_error` para que lo explique.
- **Conversión en Python puro** (`services/files/`): PyMuPDF, python-docx, openpyxl,
  python-pptx y Pillow. Matriz: PDF → Word/TXT/imágenes; Word → PDF/TXT; Excel → CSV/PDF/TXT;
  CSV → Excel/PDF/TXT; PowerPoint → PDF/TXT; imagen ↔ imagen/PDF; TXT → PDF/Word. Varias
  salidas (páginas, hojas) se entregan en un ZIP.
- **Resultados en `generated_files`**, separados de los documentos fuente: no se indexan, se
  descargan con URLs firmadas que fuerzan el nombre del archivo, y pueden ser origen de otra
  herramienta (convertir y luego comprimir).
- **Ingesta ampliada:** Excel (cada hoja es una "página"), PowerPoint (cada diapositiva es una
  "página", con notas), CSV y TXT; las citas dicen "hoja 2" o "diapositiva 3".

## Alternativas descartadas

- **LibreOffice** para Office → PDF con fidelidad visual: requiere ~350 MB de binarios del
  sistema y un servidor con Docker, en contra de ADR-005. La conversión propia conserva texto y
  tablas, no el diseño; queda documentado en la descripción de la herramienta para que el
  agente lo advierta.

## Consecuencias

- Una pregunta puede encadenar varias herramientas; el costo por pregunta aumenta con el
  número de pasos (queda registrado en `messages.tool_calls`, tokens y latencia).
- Las conversiones de Office → PDF no son idénticas al original.
- Los archivos vacíos se suben pero quedan como `failed` con el mensaje "No se encontró texto";
  una página PDF en blanco no consume una llamada de OCR.
