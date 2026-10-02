"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "@/lib/api";
import { streamSse } from "@/lib/sse";
import type { DocumentItem } from "@/lib/types";

const DOCUMENTS_KEY = ["documents"];
const RECONNECT_MS = 3000;

export function useDocuments() {
  return useQuery({
    queryKey: DOCUMENTS_KEY,
    queryFn: () => api<DocumentItem[]>("/api/v1/documents"),
  });
}

function upsert(list: DocumentItem[] | undefined, doc: DocumentItem): DocumentItem[] {
  if (!list) return [doc];
  const index = list.findIndex((d) => d.id === doc.id);
  if (index === -1) return [doc, ...list];
  const copy = [...list];
  copy[index] = doc;
  return copy;
}

/** Escucha el stream SSE de estados y actualiza la caché de la lista en vivo. */
export function useDocumentEvents() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const controller = new AbortController();
    async function listen() {
      while (!controller.signal.aborted) {
        try {
          for await (const event of streamSse("/api/v1/documents/events", {
            signal: controller.signal,
          })) {
            if (event.event !== "document") continue;
            const doc = JSON.parse(event.data) as DocumentItem;
            queryClient.setQueryData<DocumentItem[]>(DOCUMENTS_KEY, (list) => upsert(list, doc));
          }
        } catch {
          // Conexión cortada: se reintenta salvo que el componente se haya desmontado.
        }
        if (!controller.signal.aborted) await new Promise((r) => setTimeout(r, RECONNECT_MS));
      }
    }
    void listen();
    return () => controller.abort();
  }, [queryClient]);
}

export function useUploadDocuments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      return api<DocumentItem[]>("/api/v1/documents", { method: "POST", body: form });
    },
    onSuccess: (docs) =>
      queryClient.setQueryData<DocumentItem[]>(DOCUMENTS_KEY, (list) =>
        docs.reduce((acc, doc) => upsert(acc, doc), list),
      ),
  });
}

export function useRetryDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<DocumentItem>(`/api/v1/documents/${id}/retry`, { method: "POST" }),
    onSuccess: (doc) =>
      queryClient.setQueryData<DocumentItem[]>(DOCUMENTS_KEY, (list) => upsert(list, doc)),
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/api/v1/documents/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) =>
      queryClient.setQueryData<DocumentItem[]>(DOCUMENTS_KEY, (list) =>
        list?.filter((d) => d.id !== id),
      ),
  });
}

export async function openDocumentFile(id: string) {
  const { url } = await api<{ url: string }>(`/api/v1/documents/${id}/file`);
  window.open(url, "_blank", "noopener");
}
