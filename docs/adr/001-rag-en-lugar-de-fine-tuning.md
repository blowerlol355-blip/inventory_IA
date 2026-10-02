# ADR-001: RAG en lugar de fine-tuning

- **Estado:** aceptada
- **Fecha:** 2026-10-01

## Contexto

Los usuarios suben documentos nuevos todo el tiempo y necesitan preguntar sobre ellos de
inmediato, con la fuente exacta de cada dato. Los documentos son privados de cada organización.

## Decisión

No se entrena ni ajusta ningún modelo. Se usa Retrieval-Augmented Generation: los documentos
se trocean, se indexan como vectores en PostgreSQL (pgvector) y, en cada pregunta, se recuperan
los fragmentos relevantes de la organización del usuario y se le pasan al LLM como contexto.

## Consecuencias

- Un documento nuevo está disponible en segundos, sin reentrenar.
- Cada respuesta es trazable: el modelo solo ve fragmentos con documento y página conocidos.
- El aislamiento entre organizaciones se aplica en la consulta SQL, antes de llegar al LLM;
  con fine-tuning los datos de un cliente quedarían mezclados en los pesos del modelo.
- La calidad depende de la recuperación: se mide con el golden set (Fase 3) y se mejora con
  búsqueda híbrida y reranking.
