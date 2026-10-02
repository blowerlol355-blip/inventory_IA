"use client";

import { FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { AttachmentList } from "@/components/attachment-list";
import { pageLabel } from "@/lib/files";
import type { Attachment, Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

// [1] o [1][3] o [1, 2] → enlaces "#cite-N" que se renderizan como botones.
function linkCitations(text: string): string {
  return text.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, group: string) =>
    group
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
}

interface AnswerProps {
  text: string;
  citations: Citation[];
  attachments?: Attachment[];
  activeKey?: string | null;
  onCite: (citation: Citation) => void;
}

export function Answer({ text, citations, attachments = [], activeKey, onCite }: AnswerProps) {
  const byNumber = new Map(citations.map((c) => [c.n, c]));

  return (
    <div className="flex flex-col gap-3">
      <div className="prose prose-sm max-w-none dark:prose-invert [&_p]:my-1.5 [&_ul]:my-1.5">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => {
              const match = href?.match(/^#cite-(\d+)$/);
              const citation = match ? byNumber.get(Number(match[1])) : undefined;
              if (!match) return <a href={href}>{children}</a>;
              if (!citation) return <sup className="text-muted-foreground">[{match[1]}]</sup>;
              return (
                <button
                  type="button"
                  onClick={() => onCite(citation)}
                  title={`${citation.filename}, ${pageLabel(citation.content_type)} ${citation.page}`}
                  className="mx-0.5 rounded bg-primary/10 px-1 align-super text-[0.7rem] font-semibold text-primary hover:bg-primary/20"
                >
                  {citation.n}
                </button>
              );
            },
          }}
        >
          {linkCitations(text)}
        </ReactMarkdown>
      </div>

      {citations.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {citations.map((c) => {
            const key = `${c.document_id}:${c.page}:${c.n}`;
            return (
              <button
                key={key}
                type="button"
                onClick={() => onCite(c)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs hover:bg-muted",
                  activeKey === key && "border-primary bg-muted",
                )}
              >
                <FileText className="size-3.5" />
                <span className="font-semibold">[{c.n}]</span> {c.filename} · {pageLabel(c.content_type, true)} {c.page}
              </button>
            );
          })}
        </div>
      )}

      <AttachmentList files={attachments} />
    </div>
  );
}

export const citationKey = (c: Citation) => `${c.document_id}:${c.page}:${c.n}`;
