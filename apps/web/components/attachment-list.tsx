"use client";

import { Download, FileArchive, FileText } from "lucide-react";
import { toast } from "sonner";

import { downloadGeneratedFile, formatSize, OPERATION_LABELS } from "@/lib/files";
import type { Attachment } from "@/lib/types";

/** Tarjetas de descarga de los archivos que generó el agente en una respuesta. */
export function AttachmentList({ files }: { files: Attachment[] }) {
  if (!files.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {files.map((file) => {
        const Icon = file.content_type === "application/zip" ? FileArchive : FileText;
        return (
          <button
            key={file.id}
            type="button"
            onClick={() => downloadGeneratedFile(file.id).catch(() => toast.error("No se pudo descargar"))}
            className="flex items-center gap-3 rounded-lg border bg-muted/40 px-3 py-2 text-left text-sm hover:bg-muted"
            title="Descargar"
          >
            <Icon className="size-5 shrink-0 text-primary" />
            <span className="min-w-0">
              <span className="block truncate font-medium">{file.filename}</span>
              <span className="block text-xs text-muted-foreground">
                {OPERATION_LABELS[file.operation] ?? file.operation} · {formatSize(file.size_bytes)}
              </span>
            </span>
            <Download className="size-4 shrink-0 text-muted-foreground" />
          </button>
        );
      })}
    </div>
  );
}
