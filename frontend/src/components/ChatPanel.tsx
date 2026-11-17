import { useEffect, useRef, useState } from "react";
import { deleteSession, getSessionMessages, listSessions, mapSessionMessages, streamChat } from "../api/client";
import type { ChatMessage, SessionInfo } from "../types";
import { SourceCitationList } from "./SourceCitation";

export function ChatPanel({ documentIds, selectedLabel }: { documentIds: string[]; selectedLabel: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryQuestion, setRetryQuestion] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const refreshSessions = async () => { const data = await listSessions(); setSessions(data.sessions); };
  useEffect(() => { let active = true; listSessions().then((data) => { if (active) setSessions(data.sessions); }).catch(() => undefined); return () => { active = false; }; }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const selectSession = async (id: string) => { try { const data = await getSessionMessages(id); setSessionId(id); setMessages(mapSessionMessages(data.messages)); setError(null); } catch (e) { setError(e instanceof Error ? e.message : "Could not load chat."); } };
  const newChat = () => { controller.current?.abort(); setSessionId(null); setMessages([]); setError(null); setRetryQuestion(null); setLoading(false); };
  const removeSession = async () => { if (!sessionId || !confirm("Delete this conversation?")) return; await deleteSession(sessionId); newChat(); await refreshSessions(); };

  const send = async (override?: string) => {
    const question = (override ?? input).trim();
    if (!question || loading || !documentIds.length) return;
    const user: ChatMessage = { id: crypto.randomUUID(), role: "user", content: question, status: "complete" };
    const assistantId = crypto.randomUUID();
    setMessages((current) => [...current, user, { id: assistantId, role: "assistant", content: "", sources: [], status: "pending" }]);
    setInput(""); setLoading(true); setError(null); setRetryQuestion(null);
    let content = "";
    const abort = new AbortController(); controller.current = abort;
    try {
      await streamChat(question, sessionId, documentIds, {
        onSession: setSessionId,
        onSources: (sources) => setMessages((items) => items.map((item) => item.id === assistantId ? { ...item, sources } : item)),
        onToken: (token) => { content += token; setMessages((items) => items.map((item) => item.id === assistantId ? { ...item, content } : item)); },
        onDone: (id) => { setSessionId(id); setMessages((items) => items.map((item) => item.id === assistantId ? { ...item, status: "complete" } : item)); },
      }, abort.signal);
      await refreshSessions();
    } catch (e) {
      const stopped = abort.signal.aborted;
      const message = stopped ? "Generation stopped." : e instanceof Error ? e.message : "Generation failed.";
      setError(message); setRetryQuestion(question);
      setMessages((items) => items.map((item) => item.id === assistantId ? { ...item, content: content || message, status: "failed" } : item));
    } finally { setLoading(false); controller.current = null; }
  };

  const exportMarkdown = () => { const body = messages.map((message) => `${message.role === "user" ? "## Question" : "## Answer"}\n\n${message.content}${message.sources?.length ? `\n\nSources: ${message.sources.map((s) => `${s.filename}, p. ${s.page}`).join("; ")}` : ""}`).join("\n\n"); const url = URL.createObjectURL(new Blob([`# CiteWeave conversation\n\n${body}`], { type: "text/markdown" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "citeweave-conversation.md"; anchor.click(); URL.revokeObjectURL(url); };

  return <div className="chat-panel">
    <div className="chat-toolbar"><div><p className="eyebrow">Research thread</p><h2>{sessionId ? sessions.find((s) => s.id === sessionId)?.title || "Conversation" : "New conversation"}</h2><small>{selectedLabel}</small></div><div className="toolbar-actions"><button onClick={newChat}>New</button><button onClick={exportMarkdown} disabled={!messages.length}>Export</button>{sessionId && <button className="danger" onClick={() => void removeSession()}>Delete</button>}</div></div>
    {sessions.length > 0 && <label className="session-select"><span>Recent conversation</span><select value={sessionId || ""} onChange={(event) => event.target.value ? void selectSession(event.target.value) : newChat()}><option value="">New conversation</option>{sessions.map((session) => <option value={session.id} key={session.id}>{session.title || "Untitled chat"}</option>)}</select></label>}
    <div className="messages" aria-live="polite">{messages.length === 0 ? <div className="chat-empty"><div className="weave-mark">CW</div><h3>Ask across your research library</h3><p>Select one or more documents, then ask for comparisons, summaries, or evidence. Every supported answer includes page-level citations.</p></div> : messages.map((message) => <article key={message.id} className={`message ${message.role} ${message.status || ""}`}><div className="message-label">{message.role === "user" ? "You" : "CiteWeave"}{message.status === "failed" && " · failed"}</div><div className="message-content">{message.content || <span className="streaming">Reading your sources…</span>}</div>{message.role === "assistant" && message.content && <button className="copy" onClick={() => void navigator.clipboard.writeText(message.content)}>Copy answer</button>}{message.sources && <SourceCitationList sources={message.sources} />}</article>)}<div ref={bottom} /></div>
    {error && <div className="chat-error" role="alert"><span>{error}</span>{retryQuestion && !loading && <button onClick={() => void send(retryQuestion)}>Retry</button>}</div>}
    <div className="composer"><label htmlFor="question">Question</label><textarea id="question" value={input} disabled={loading || !documentIds.length} placeholder={documentIds.length ? "Ask a question grounded in the selected PDFs…" : "Select at least one document to begin"} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} /><button className={loading ? "stop" : "send"} onClick={() => loading ? controller.current?.abort() : void send()} disabled={!loading && (!input.trim() || !documentIds.length)}>{loading ? "Stop generating" : "Send"}</button></div>
  </div>;
}
