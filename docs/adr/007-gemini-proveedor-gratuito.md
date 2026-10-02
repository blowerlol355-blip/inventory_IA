# ADR-007: Gemini como proveedor gratuito por defecto

- **Estado:** aceptada (complementa ADR-002)
- **Fecha:** 2026-10-01

## Contexto

Es un proyecto de portafolio: cualquiera debería poder levantarlo y usar la demo sin pagar.
Claude y Voyage AI requieren crédito o tarjeta para un uso cómodo.

## Decisión

- Proveedor por defecto: **Google Gemini** con una sola clave gratuita de Google AI Studio.
  - LLM: `gemini-3.8-flash` (agente con *function calling*, salida JSON con esquema, visión
    para OCR). El esfuerzo se traduce a presupuesto de razonamiento (`low` = sin razonar).
  - Embeddings: `gemini-embedding-001` a 1024 dimensiones (la misma columna `vector(1024)`;
    no hace falta migración). Con dimensión reducida se normalizan los vectores.
- Claude y Voyage se mantienen como implementaciones alternativas de las mismas interfaces
  (`LLMProvider`, `Embedder`); se eligen con `LLM_PROVIDER` y `EMBEDDING_PROVIDER`.
- Los turnos del modelo se reenvían intactos en el bucle de herramientas (Gemini exige
  devolver sus *thought signatures*). Gemini no siempre devuelve id en las llamadas a
  funciones: el proveedor genera uno y guarda el nombre en el turno, opaco para el agente.
- **Cadena de modelos.** La capa gratuita da una cuota diaria pequeña *por modelo* (~20
  peticiones/día en los "flash") y tiene picos de demanda (503). Ante un 429 o 503 el
  proveedor pasa al siguiente modelo al instante y deja el agotado en pausa (15 min si es
  cuota, 1 min si es saturación). El chat empieza por los modelos "flash"
  (`GEMINI_FALLBACK_MODELS`); clasificar y OCR, por los "lite" (`GEMINI_TASK_MODELS`), para
  no gastar la cuota del chat.
- **Clasificación por reglas primero.** Palabras clave por tipo, con más peso para el título
  (primera línea). Solo los casos ambiguos llegan al LLM. En el set de demostración clasifica
  bien los 47 documentos con texto sin ninguna llamada al LLM.

## Consecuencias

- Coste cero para desarrollar y para la demo.
- Cambiar de modelo de embeddings exige reindexar (`python -m app.scripts.reindex`): vectores
  de modelos distintos no son comparables.
- Con mucho tráfico la capa gratuita se queda corta; pasar a la de pago o a Claude es solo
  configuración.
- En la capa gratuita, Google puede usar los datos para mejorar sus productos: aceptable con
  documentos sintéticos, no con documentos reales de clientes.
