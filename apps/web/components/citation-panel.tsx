"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import dynamic from "next/dynamic";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useDocuments } from "@/lib/documents";
import { pageLabel } from "@/lib/files";
import type { Citation } from "@/lib/types";

// pdf.js usa APIs del navegador: se carga solo en el cliente.
const PdfViewer = dynamic(() => import("@/components/pdf-viewer"), {
  ssr: false,
  loading: () => <p className="p-4 text-sm text-muted-foreground">Cargando visor…</p>,
});

// Las URLs firmadas expiran a los 5 minutos: se piden de nuevo antes.
const SIGNED_URL_STALE_MS = 4 * 60_000;

export function CitationPanel({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const { data: documents } = useDocuments();
  const contentType =
    citation.content_type || documents?.find((d) => d.id === citation.document_id)?.content_type;
  const { data, error } = useQuery({
    queryKey: ["file-url", citation.document_id],
    queryFn: () => api<{ url: string }>(`/api/v1/documents/${citation.document_id}/file`),
    staleTime: SIGNED_URL_STALE_MS,
  });

  return (
    <aside className="flex h-full flex-col border-l">
      <div className="flex items-start gap-2 border-b p-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{citation.filename}</p>
          <p className="text-xs text-muted-foreground">Fuente [{citation.n}] · {pageLabel(contentType)} {citation.page}</p>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} title="Cerrar">
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <blockquote className="mb-3 border-l-2 pl-3 text-xs text-muted-foreground">
          {citation.snippet}…
        </blockquote>
        {error && <p className="text-sm text-destructive">No se pudo abrir el documento.</p>}
        {data &&
          (contentType?.startsWith("image/") ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={data.url} alt={citation.filename} className="w-full rounded border" />
          ) : contentType === "application/pdf" || contentType === undefined ? (
            <PdfViewer url={data.url} page={citation.page} highlight={citation.snippet} />
          ) : (
            <p className="text-sm text-muted-foreground">
              La vista previa solo está disponible para PDF e imágenes.{" "}
              <a className="underline" href={data.url} target="_blank" rel="noreferrer">
                Descargar el documento original
              </a>
            </p>
          ))}
      </div>
    </aside>
  );
}
