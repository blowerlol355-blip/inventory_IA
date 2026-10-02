"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Debe configurarse en el mismo módulo que usa <Document>/<Page> (ver README de react-pdf).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const normalize = (text: string) => text.toLowerCase().replace(/\s+/g, " ").trim();

const escapeHtml = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

interface PdfViewerProps {
  url: string;
  page: number;
  /** Texto del fragmento citado: se resalta en la página. */
  highlight?: string;
}

export default function PdfViewer({ url, page, highlight }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number>();
  const [numPages, setNumPages] = useState<number>();

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const target = useMemo(() => normalize(highlight ?? ""), [highlight]);

  return (
    <div ref={containerRef} className="w-full">
      <Document
        file={url}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        loading={<p className="p-4 text-sm text-muted-foreground">Cargando PDF…</p>}
        error={<p className="p-4 text-sm text-destructive">No se pudo cargar el PDF.</p>}
      >
        <Page
          pageNumber={page}
          width={width}
          customTextRenderer={({ str }) => {
            const piece = normalize(str);
            const hit = target && piece.length >= 4 && target.includes(piece);
            return hit ? `<mark>${escapeHtml(str)}</mark>` : escapeHtml(str);
          }}
        />
      </Document>
      {numPages && (
        <p className="py-2 text-center text-xs text-muted-foreground">
          Página {page} de {numPages}
        </p>
      )}
    </div>
  );
}
