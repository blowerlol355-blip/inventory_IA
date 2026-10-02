"use client";

import { Eye, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { UploadZone } from "@/components/upload-zone";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import {
  openDocumentFile,
  useDeleteDocument,
  useDocumentEvents,
  useDocuments,
  useRetryDocument,
} from "@/lib/documents";
import type { DocumentItem, DocumentStatus } from "@/lib/types";

const STATUS: Record<DocumentStatus, { label: string; variant: "secondary" | "outline" | "default" | "destructive" }> = {
  pending: { label: "En cola", variant: "outline" },
  processing: { label: "Procesando", variant: "secondary" },
  ready: { label: "Listo", variant: "default" },
  failed: { label: "Falló", variant: "destructive" },
};

const DOC_TYPES: Record<string, string> = {
  factura: "Factura",
  contrato: "Contrato",
  estado_de_cuenta: "Estado de cuenta",
  otro: "Otro",
};

function formatSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function StatusBadge({ doc }: { doc: DocumentItem }) {
  const { label, variant } = STATUS[doc.status];
  const busy = doc.status === "pending" || doc.status === "processing";
  return (
    <Badge variant={variant} title={doc.error ?? undefined}>
      {busy && <Loader2 className="animate-spin" />} {label}
    </Badge>
  );
}

export default function DocumentsPage() {
  const { user } = useAuth();
  const { data: documents, isLoading, error } = useDocuments();
  const retry = useRetryDocument();
  const remove = useDeleteDocument();
  useDocumentEvents();
  const canEdit = user?.role === "admin" || user?.role === "editor";

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-6 overflow-y-auto p-6">
      <div>
        <h1 className="text-2xl font-semibold">Documentos</h1>
        <p className="text-sm text-muted-foreground">
          Sube facturas, contratos o estados de cuenta. Cuando estén listos podrás preguntar
          sobre ellos en el chat.
        </p>
      </div>

      {canEdit && <UploadZone />}

      {isLoading && <p className="text-muted-foreground">Cargando documentos…</p>}
      {error && <p className="text-destructive">No se pudieron cargar los documentos.</p>}
      {documents && documents.length === 0 && (
        <p className="text-muted-foreground">Todavía no hay documentos.</p>
      )}

      {documents && documents.length > 0 && (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="p-3 font-medium">Archivo</th>
                <th className="p-3 font-medium">Tipo</th>
                <th className="p-3 font-medium">Estado</th>
                <th className="p-3 font-medium">Páginas</th>
                <th className="p-3 font-medium">Subido</th>
                <th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-t">
                  <td className="p-3">
                    <div className="font-medium">{doc.filename}</div>
                    <div className="text-xs text-muted-foreground">{formatSize(doc.size_bytes)}</div>
                    {doc.status === "failed" && doc.error && (
                      <div className="text-xs text-destructive">{doc.error}</div>
                    )}
                  </td>
                  <td className="p-3">{doc.doc_type ? (DOC_TYPES[doc.doc_type] ?? doc.doc_type) : "—"}</td>
                  <td className="p-3">
                    <StatusBadge doc={doc} />
                  </td>
                  <td className="p-3">{doc.page_count ?? "—"}</td>
                  <td className="p-3 text-muted-foreground">
                    {new Date(doc.created_at).toLocaleString("es")}
                  </td>
                  <td className="p-3">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Ver archivo"
                        onClick={() => openDocumentFile(doc.id).catch(() => toast.error("No se pudo abrir"))}
                      >
                        <Eye />
                      </Button>
                      {canEdit && doc.status === "failed" && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Reintentar"
                          onClick={() => retry.mutate(doc.id)}
                        >
                          <RotateCcw />
                        </Button>
                      )}
                      {canEdit && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Eliminar"
                          onClick={() => {
                            if (confirm(`¿Eliminar ${doc.filename}?`)) remove.mutate(doc.id);
                          }}
                        >
                          <Trash2 />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
