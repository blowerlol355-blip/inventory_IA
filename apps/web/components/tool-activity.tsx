"use client";

import { CircleAlert, CircleCheck, FileArchive, FileOutput, FolderSearch, Loader2, Search } from "lucide-react";

import type { ToolStep } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof Search> = {
  search_documents: Search,
  list_documents: FolderSearch,
  convert_document: FileOutput,
  compress_files: FileArchive,
};

/** Lo que el agente está haciendo: una línea por herramienta, con su estado. */
export function ToolActivity({ steps }: { steps: ToolStep[] }) {
  if (!steps.length) return null;
  return (
    <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
      {steps.map((step) => {
        const Icon = ICONS[step.name] ?? Search;
        return (
          <li key={step.id} className="flex items-center gap-2">
            <Icon className="size-3.5" />
            <span className={cn(step.status === "error" && "text-destructive")}>
              {step.label}
              {step.summary && step.status !== "running" ? ` · ${step.summary}` : "…"}
            </span>
            {step.status === "running" && <Loader2 className="size-3.5 animate-spin" />}
            {step.status === "done" && <CircleCheck className="size-3.5 text-primary" />}
            {step.status === "error" && <CircleAlert className="size-3.5 text-destructive" />}
          </li>
        );
      })}
    </ul>
  );
}
