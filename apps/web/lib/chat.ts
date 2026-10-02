"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { streamSse } from "@/lib/sse";
import type {
  Attachment,
  ChatMessage,
  Citation,
  Conversation,
  DoneEvent,
  ToolStep,
} from "@/lib/types";

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<Conversation[]>("/api/v1/conversations"),
  });
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => api<ChatMessage[]>(`/api/v1/conversations/${conversationId}/messages`),
    enabled: Boolean(conversationId),
  });
}

export interface PendingAnswer {
  question: string;
  text: string;
  sources: Citation[];
  tools: ToolStep[];
  files: Attachment[];
  error?: string;
}

function upsertTool(tools: ToolStep[], step: ToolStep): ToolStep[] {
  const index = tools.findIndex((t) => t.id === step.id);
  if (index === -1) return [...tools, step];
  const copy = [...tools];
  copy[index] = step;
  return copy;
}

/** Envía una pregunta y expone la respuesta (texto, herramientas, archivos) mientras llega. */
export function useAsk() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAnswer | null>(null);

  const ask = useCallback(
    async (conversationId: string, question: string) => {
      setPending({ question, text: "", sources: [], tools: [], files: [] });
      try {
        for await (const event of streamSse(`/api/v1/conversations/${conversationId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: question }),
        })) {
          const data = JSON.parse(event.data);
          switch (event.event) {
            case "token":
              setPending((p) => p && { ...p, text: p.text + (data as { text: string }).text });
              break;
            case "tool":
              setPending((p) => p && { ...p, tools: upsertTool(p.tools, data as ToolStep) });
              break;
            case "sources":
              setPending((p) => p && { ...p, sources: [...p.sources, ...(data as Citation[])] });
              break;
            case "file":
              setPending((p) => p && { ...p, files: [...p.files, data as Attachment] });
              void queryClient.invalidateQueries({ queryKey: ["generated-files"] });
              break;
            case "error":
              setPending((p) => p && { ...p, error: (data as { message: string }).message });
              return;
            case "done": {
              const done = data as DoneEvent;
              await queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
              void queryClient.invalidateQueries({ queryKey: ["conversations"] });
              setPending(null);
              return done;
            }
          }
        }
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Se perdió la conexión";
        setPending((p) => p && { ...p, error: message });
      }
    },
    [queryClient],
  );

  return { ask, pending, clearPending: () => setPending(null) };
}
