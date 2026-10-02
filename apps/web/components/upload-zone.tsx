"use client";

import { Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useUploadDocuments } from "@/lib/documents";
import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.xlsx,.pptx,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.webp";
const MAX_MB = 20;

export function UploadZone() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useUploadDocuments();

  function send(fileList: FileList | null) {
    const files = Array.from(fileList ?? []);
    if (!files.length) return;
    const tooBig = files.filter((f) => f.size > MAX_MB * 1024 * 1024);
    if (tooBig.length) {
      toast.error(`Superan ${MAX_MB} MB: ${tooBig.map((f) => f.name).join(", ")}`);
      return;
    }
    upload.mutate(files, {
      onSuccess: (docs) => toast.success(`${docs.length} documento(s) en proceso`),
      onError: (err) => {
        const details =
          err instanceof ApiError && Array.isArray(err.details)
            ? (err.details as { filename: string; reason: string }[])
                .map((d) => `${d.filename}: ${d.reason}`)
                .join("\n")
            : undefined;
        toast.error(err instanceof ApiError ? err.message : "Error al subir", {
          description: details,
        });
      },
    });
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    send(event.dataTransfer.files);
  }

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      disabled={upload.isPending}
      className={cn(
        "flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
        dragging ? "border-primary bg-muted" : "border-border hover:bg-muted/50",
      )}
    >
      <Upload className="size-6 text-muted-foreground" />
      <span className="font-medium">
        {upload.isPending ? "Subiendo…" : "Arrastra archivos aquí o haz clic para elegir"}
      </span>
      <span className="text-sm text-muted-foreground">
        PDF, Word, Excel, PowerPoint, CSV, TXT o imágenes · hasta {MAX_MB} MB por archivo
      </span>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          send(e.target.files);
          e.target.value = "";
        }}
      />
    </button>
  );
}
