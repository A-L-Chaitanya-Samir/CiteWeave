import { useRef, useState } from "react";
import { deleteDocument, reindexDocument, uploadDocuments } from "../api/client";
import type { DocumentInfo, UploadResult } from "../types";

type Props = { documents: DocumentInfo[]; selected: Set<string>; onSelection: (next: Set<string>) => void; onRefresh: () => Promise<void> };

export function DocumentUpload({ documents, selected, onSelection, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);
  const input = useRef<HTMLInputElement>(null);

  const handleFiles = async (list: FileList | null) => {
    if (!list?.length) return;
    const files = Array.from(list);
    const invalid = files.find((file) => !file.name.toLowerCase().endsWith(".pdf") || file.type && file.type !== "application/pdf");
    if (invalid) return setNotice(`${invalid.name} is not a PDF.`);
    if (files.length > 10) return setNotice("Choose no more than 10 PDFs at once.");
    const oversized = files.find((file) => file.size > 25 * 1024 * 1024);
    if (oversized) return setNotice(`${oversized.name} exceeds 25 MB.`);
    setBusy(true); setNotice(null); setResults([]);
    try {
      const response = await uploadDocuments(files);
      setResults(response.results);
      setNotice(response.message);
      await onRefresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Upload failed."); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  };

  const toggle = (id: string) => { const next = new Set(selected); if (next.has(id)) next.delete(id); else next.add(id); onSelection(next); };
  const remove = async (doc: DocumentInfo) => {
    if (!confirm(`Delete ${doc.filename} and all indexed chunks?`)) return;
    try { await deleteDocument(doc.document_id); const next = new Set(selected); next.delete(doc.document_id); onSelection(next); await onRefresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Delete failed."); }
  };
  const reindex = async (doc: DocumentInfo) => {
    setNotice(`Re-indexing ${doc.filename}…`);
    try { await reindexDocument(doc.document_id); setNotice(`${doc.filename} was re-indexed.`); await onRefresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Re-index failed."); }
  };

  return <div className="document-panel">
    <div className={`drop-zone ${dragging ? "dragging" : ""}`} role="button" tabIndex={0}
      aria-label="Upload PDF documents" onClick={() => input.current?.click()}
      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); input.current?.click(); } }}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); void handleFiles(event.dataTransfer.files); }}>
      <input ref={input} type="file" accept="application/pdf,.pdf" multiple onChange={(event) => void handleFiles(event.target.files)} />
      <span className="upload-mark">＋</span><strong>{busy ? "Indexing locally…" : "Drop PDFs or browse"}</strong>
      <small>Up to 10 files · 25 MB each</small>
    </div>
    <div aria-live="polite" className="notice">{notice}</div>
    {results.length > 0 && <ul className="upload-results">{results.map((result) => <li key={result.filename} className={result.status}>{result.filename}: {result.error || result.status}</li>)}</ul>}
    <div className="panel-heading"><div><p className="eyebrow">Library</p><h2>Indexed documents</h2></div>{documents.length > 0 && <button className="text-button" onClick={() => onSelection(selected.size === documents.length ? new Set() : new Set(documents.map((doc) => doc.document_id)))}>{selected.size === documents.length ? "Clear" : "Select all"}</button>}</div>
    {documents.length === 0 ? <div className="empty-small">Your indexed PDFs will appear here.</div> : <ul className="documents">{documents.map((doc) => <li key={doc.document_id}>
      <label><input type="checkbox" checked={selected.has(doc.document_id)} onChange={() => toggle(doc.document_id)} /><span><strong title={doc.filename}>{doc.filename}</strong><small>{doc.chunk_count} chunks · {new Date(doc.uploaded_at).toLocaleDateString()}</small></span></label>
      <div className="row-actions"><button onClick={() => void reindex(doc)} aria-label={`Re-index ${doc.filename}`}>Re-index</button><button className="danger" onClick={() => void remove(doc)} aria-label={`Delete ${doc.filename}`}>Delete</button></div>
    </li>)}</ul>}
  </div>;
}
