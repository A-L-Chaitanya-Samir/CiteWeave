import { useCallback, useEffect, useState } from "react";
import { getHealth, getReadiness, listDocuments } from "./api/client";
import { ChatPanel } from "./components/ChatPanel";
import { DocumentUpload } from "./components/DocumentUpload";
import type { DocumentInfo, ReadinessStatus } from "./types";

export default function App() {
  const [backend, setBackend] = useState(false);
  const [readiness, setReadiness] = useState<ReadinessStatus | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [statusOpen, setStatusOpen] = useState(false);

  const refreshDocuments = useCallback(async () => {
    const data = await listDocuments();
    setDocuments(data.documents);
    setSelected((current) => {
      const available = new Set(data.documents.map((doc) => doc.document_id));
      const retained = new Set([...current].filter((id) => available.has(id)));
      if (current.size === 0) data.documents.forEach((doc) => retained.add(doc.document_id));
      return retained;
    });
  }, []);

  useEffect(() => {
    let active = true;
    Promise.allSettled([getHealth(), getReadiness(), listDocuments()]).then(([health, ready, docs]) => {
      if (!active) return;
      setBackend(health.status === "fulfilled");
      if (ready.status === "fulfilled") setReadiness(ready.value);
      if (docs.status === "fulfilled") { setDocuments(docs.value.documents); setSelected(new Set(docs.value.documents.map((doc) => doc.document_id))); }
    });
    return () => { active = false; };
  }, []);

  const ready = readiness?.status === "ready";
  const selectedLabel = selected.size === documents.length && documents.length ? `All ${documents.length} documents selected` : `${selected.size} of ${documents.length} documents selected`;
  return <div className="app-shell">
    <header className="app-header"><div className="brand"><div className="brand-mark"><span>C</span><span>W</span></div><div><h1>CiteWeave</h1><p>Traceable research across every document.</p></div></div><button className={`system-pill ${ready ? "ready" : "warning"}`} onClick={() => setStatusOpen(!statusOpen)} aria-expanded={statusOpen}><span />{ready ? "Systems ready" : backend ? "Setup needed" : "Backend offline"}</button></header>
    {statusOpen && <section className="status-drawer" aria-label="System status"><Status name="Backend" ok={backend} detail={backend ? "FastAPI is responding" : "Start FastAPI on port 8000"} /><Status name="SQLite" ok={readiness?.sqlite.ok} detail={readiness?.sqlite.detail} /><Status name="Chroma" ok={readiness?.chroma.ok} detail={readiness?.chroma.detail} /><Status name="Ollama" ok={readiness?.ollama.ok} detail={readiness?.ollama.detail || "Local model service"} /><Status name="Models" ok={readiness?.models.ok} detail={readiness?.models.detail || readiness?.ollama_models.join(", ")} /></section>}
    <main className="workspace"><aside><DocumentUpload documents={documents} selected={selected} onSelection={setSelected} onRefresh={refreshDocuments} /></aside><section className="research"><ChatPanel documentIds={[...selected]} selectedLabel={selectedLabel} /></section></main>
    <footer>Local-first · Your documents and questions stay on this machine</footer>
  </div>;
}

function Status({ name, ok, detail }: { name: string; ok?: boolean; detail?: string | null }) { return <div className="status-item"><span className={ok ? "ok" : "bad"}>{ok ? "✓" : "!"}</span><div><strong>{name}</strong><small>{detail || (ok ? "Ready" : "Unavailable")}</small></div></div>; }
