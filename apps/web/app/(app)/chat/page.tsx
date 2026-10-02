"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquarePlus, SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Answer, citationKey } from "@/components/answer";
import { CitationPanel } from "@/components/citation-panel";
import { ToolActivity } from "@/components/tool-activity";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAsk, useConversations, useMessages } from "@/lib/chat";
import type { Citation, Conversation } from "@/lib/types";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "¿Cuál es el total a pagar de la factura F-000003?",
  "¿Qué contratos tienen renovación automática?",
  "Convierte la planilla de gastos a CSV",
  "Comprime todas las facturas en un ZIP",
];

/** Fuentes cuyo número aparece citado en el texto (para mostrar durante el streaming). */
function citedIn(text: string, sources: Citation[]): Citation[] {
  const cited = new Set(
    Array.from(text.matchAll(/\[([\d,\s]+)\]/g)).flatMap((m) =>
      m[1].split(",").map((n) => Number(n.trim())),
    ),
  );
  return sources.filter((s) => cited.has(s.n));
}

export default function ChatPage() {
  const queryClient = useQueryClient();
  const { data: conversations } = useConversations();
  const [activeId, setActiveId] = useState<string | null>(null);
  const { data: messages } = useMessages(activeId);
  const { ask, pending, clearPending } = useAsk();
  const [question, setQuestion] = useState("");
  const [citation, setCitation] = useState<Citation | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending?.text]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || (pending && !pending.error)) return;
    clearPending();
    let conversationId = activeId;
    if (!conversationId) {
      const conv = await api<Conversation>("/api/v1/conversations", {
        method: "POST",
        body: JSON.stringify({}),
      });
      queryClient.setQueryData<Conversation[]>(["conversations"], (list) => [conv, ...(list ?? [])]);
      conversationId = conv.id;
      setActiveId(conv.id);
    }
    setQuestion("");
    await ask(conversationId, content);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(question);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(question);
    }
  }

  const busy = Boolean(pending && !pending.error);
  const empty = !activeId || (messages?.length === 0 && !pending);

  return (
    <div
      className={cn(
        "grid h-full",
        citation ? "grid-cols-[240px_1fr_minmax(360px,40%)]" : "grid-cols-[240px_1fr]",
      )}
    >
      {/* Conversaciones */}
      <aside className="flex min-h-0 flex-col border-r">
        <div className="p-3">
          <Button
            variant="outline"
            className="w-full"
            onClick={() => {
              setActiveId(null);
              setCitation(null);
              clearPending();
            }}
          >
            <MessageSquarePlus /> Nueva conversación
          </Button>
        </div>
        <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {conversations?.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => {
                setActiveId(c.id);
                setCitation(null);
                clearPending();
              }}
              className={cn(
                "block w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                c.id === activeId && "bg-muted font-medium",
              )}
            >
              {c.title}
            </button>
          ))}
        </nav>
      </aside>

      {/* Mensajes */}
      <section className="flex min-h-0 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
            {empty && (
              <div className="mt-16 flex flex-col items-center gap-4 text-center">
                <h1 className="text-xl font-semibold">Pregunta sobre tus documentos</h1>
                <p className="text-sm text-muted-foreground">
                  Cada respuesta cita el documento y la página de donde sale.
                </p>
                <div className="flex flex-col gap-2">
                  {EXAMPLES.map((example) => (
                    <Button key={example} variant="outline" onClick={() => void send(example)}>
                      {example}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {messages?.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="self-end rounded-2xl bg-primary px-4 py-2 text-primary-foreground">
                  {m.content}
                </div>
              ) : (
                <Answer
                  key={m.id}
                  text={m.content}
                  citations={m.citations ?? []}
                  attachments={m.attachments ?? []}
                  activeKey={citation ? citationKey(citation) : null}
                  onCite={setCitation}
                />
              ),
            )}

            {pending && (
              <>
                {!messages?.some((m) => m.role === "user" && m.content === pending.question) && (
                  <div className="self-end rounded-2xl bg-primary px-4 py-2 text-primary-foreground">
                    {pending.question}
                  </div>
                )}
                <ToolActivity steps={pending.tools} />
                {pending.text || pending.files.length ? (
                  <Answer
                    text={pending.text}
                    citations={citedIn(pending.text, pending.sources)}
                    attachments={pending.files}
                    onCite={setCitation}
                  />
                ) : (
                  !pending.error &&
                  !pending.tools.some((t) => t.status === "running") && (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" /> Pensando…
                    </p>
                  )
                )}
                {pending.error && <p className="text-sm text-destructive">{pending.error}</p>}
              </>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <form onSubmit={onSubmit} className="border-t p-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Escribe tu pregunta… (Enter para enviar, Shift+Enter para nueva línea)"
              rows={2}
              maxLength={2000}
              className="min-h-0 resize-none"
            />
            <Button type="submit" size="icon-lg" disabled={busy || !question.trim()} title="Enviar">
              {busy ? <Loader2 className="animate-spin" /> : <SendHorizontal />}
            </Button>
          </div>
        </form>
      </section>

      {/* Documento citado */}
      {citation && <CitationPanel citation={citation} onClose={() => setCitation(null)} />}
    </div>
  );
}
