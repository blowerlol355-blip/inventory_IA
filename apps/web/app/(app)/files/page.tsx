"use client";

import { Download, FileArchive, FileText, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import {
  downloadGeneratedFile,
  formatSize,
  OPERATION_LABELS,
  useDeleteGeneratedFile,
  useGeneratedFiles,
} from "@/lib/files";

export default function FilesPage() {
  const { user } = useAuth();
  const { data: files, isLoading, error } = useGeneratedFiles();
  const remove = useDeleteGeneratedFile();
  const canEdit = user?.role === "admin" || user?.role === "editor";

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-6 overflow-y-auto p-6">
      <div>
        <h1 className="text-2xl font-semibold">Archivos generados</h1>
        <p className="text-sm text-muted-foreground">
          Conversiones, ZIP y versiones comprimidas que creó la IA desde el chat. Pídele, por
          ejemplo: <i>“convierte el contrato 2 a Word”</i> o <i>“comprime las facturas en un ZIP”</i>.
        </p>
      </div>

      {isLoading && <p className="text-muted-foreground">Cargando…</p>}
      {error && <p className="text-destructive">No se pudieron cargar los archivos.</p>}
      {files && files.length === 0 && (
        <p className="text-muted-foreground">Todavía no se generó ningún archivo.</p>
      )}

      {files && files.length > 0 && (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="p-3 font-medium">Archivo</th>
                <th className="p-3 font-medium">Operación</th>
                <th className="p-3 font-medium">Origen</th>
                <th className="p-3 font-medium">Creado</th>
                <th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {files.map((file) => {
                const Icon = file.content_type === "application/zip" ? FileArchive : FileText;
                return (
                  <tr key={file.id} className="border-t">
                    <td className="p-3">
                      <div className="flex items-center gap-2 font-medium">
                        <Icon className="size-4 text-primary" /> {file.filename}
                      </div>
                      <div className="text-xs text-muted-foreground">{formatSize(file.size_bytes)}</div>
                    </td>
                    <td className="p-3">
                      <Badge variant="secondary">{OPERATION_LABELS[file.operation] ?? file.operation}</Badge>
                    </td>
                    <td className="max-w-xs p-3 text-xs text-muted-foreground">
                      {file.sources.map((s) => s.filename).join(", ")}
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {new Date(file.created_at).toLocaleString("es")}
                    </td>
                    <td className="p-3">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="Descargar"
                          onClick={() =>
                            downloadGeneratedFile(file.id).catch(() => toast.error("No se pudo descargar"))
                          }
                        >
                          <Download />
                        </Button>
                        {canEdit && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            title="Eliminar"
                            onClick={() => {
                              if (confirm(`¿Eliminar ${file.filename}?`)) remove.mutate(file.id);
                            }}
                          >
                            <Trash2 />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
