"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { GeneratedFile } from "@/lib/types";

const FILES_KEY = ["generated-files"];

export function useGeneratedFiles() {
  return useQuery({
    queryKey: FILES_KEY,
    queryFn: () => api<GeneratedFile[]>("/api/v1/files"),
  });
}

export function useDeleteGeneratedFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/api/v1/files/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) =>
      queryClient.setQueryData<GeneratedFile[]>(FILES_KEY, (list) => list?.filter((f) => f.id !== id)),
  });
}

/** Pide una URL firmada (con nombre de descarga) y la abre. */
export async function downloadGeneratedFile(id: string) {
  const { url } = await api<{ url: string }>(`/api/v1/files/${id}/url`);
  window.location.assign(url);
}

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const OPERATION_LABELS: Record<string, string> = {
  convert: "Conversión",
  zip: "ZIP",
  reduce: "Comprimido",
};

/** "página", "hoja" o "diapositiva" según el formato del documento citado. */
export function pageLabel(contentType?: string, short = false): string {
  if (contentType?.includes("spreadsheetml")) return "hoja";
  if (contentType?.includes("presentationml")) return short ? "diap." : "diapositiva";
  return short ? "p." : "página";
}
