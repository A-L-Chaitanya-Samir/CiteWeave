import type { ChatMessage, DocumentInfo, ReadinessStatus, SessionInfo, SourceCitation, UploadResult } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const getHealth = () => request<{ status: string; service: string }>("/health");
export const getReadiness = () => request<ReadinessStatus>("/ready");
export const listDocuments = () => request<{ documents: DocumentInfo[] }>("/api/documents");
export const deleteDocument = (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" });
export const reindexDocument = (id: string) => request<DocumentInfo>(`/api/documents/${id}/reindex`, { method: "POST" });

export async function uploadDocuments(files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<{ results: UploadResult[]; total_chunks: number; message: string }>("/api/documents/upload", { method: "POST", body: form });
}

export const listSessions = () => request<{ sessions: SessionInfo[] }>("/api/sessions");
export const deleteSession = (id: string) => request<void>(`/api/sessions/${id}`, { method: "DELETE" });
export const getSessionMessages = (id: string) => request<{ session_id: string; messages: Array<ChatMessage & { created_at: string }> }>(`/api/sessions/${id}/messages`);

export type StreamCallbacks = {
  onSession: (id: string) => void;
  onSources: (sources: SourceCitation[]) => void;
  onToken: (token: string) => void;
  onDone: (id: string) => void;
};

export function parseEvent(block: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try { return { event, data: JSON.parse(dataLines.join("\n")) }; }
  catch { throw new Error(`Malformed ${event} stream event.`); }
}

export async function streamChat(question: string, sessionId: string | null, documentIds: string[], callbacks: StreamCallbacks, signal: AbortSignal): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST", headers: { "Content-Type": "application/json" }, signal,
    body: JSON.stringify({ question, session_id: sessionId, document_ids: documentIds.length ? documentIds : null }),
  });
  if (!response.ok || !response.body) throw new Error(`Stream request failed (${response.status}).`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const parsed = parseEvent(block);
      if (!parsed) continue;
      if (parsed.event === "session") callbacks.onSession((parsed.data as { session_id: string }).session_id);
      else if (parsed.event === "sources") callbacks.onSources(parsed.data as SourceCitation[]);
      else if (parsed.event === "token") callbacks.onToken(parsed.data as string);
      else if (parsed.event === "done") { terminal = true; callbacks.onDone((parsed.data as { session_id: string }).session_id); }
      else if (parsed.event === "error") { throw new Error((parsed.data as { message?: string }).message || "Generation failed."); }
      else throw new Error(`Unknown stream event: ${parsed.event}`);
    }
  }
  if (!terminal) throw new Error("The response stream ended unexpectedly.");
}

export const mapSessionMessages = (raw: Array<ChatMessage>): ChatMessage[] => raw.map((item) => ({ ...item, role: item.role as "user" | "assistant" }));
