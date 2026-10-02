export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentItem {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  doc_type: string | null;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  email: string;
  role: "admin" | "editor" | "viewer";
  organization_id: string;
  organization_name: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export interface Citation {
  n: number;
  document_id: string;
  filename: string;
  page: number;
  snippet: string;
  content_type?: string;
}

/** Archivo creado por una herramienta del agente (conversión, ZIP, compresión). */
export interface Attachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  operation: "convert" | "zip" | "reduce";
}

export interface GeneratedFile extends Attachment {
  sources: { id: string; filename: string }[];
  conversation_id: string | null;
  created_at: string;
}

export interface ToolStep {
  id: string;
  name: string;
  label: string;
  status: "running" | "done" | "error";
  summary?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  attachments: Attachment[] | null;
  created_at: string;
}

export interface DoneEvent {
  message_id: string;
  content: string;
  citations: Citation[];
  attachments: Attachment[];
  usage: { input_tokens: number; output_tokens: number };
  latency_ms: number;
}
