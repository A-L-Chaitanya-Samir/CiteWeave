import { useState } from "react";
import type { SourceCitation as Source } from "../types";

export function SourceCitationList({ sources }: { sources: Source[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!sources.length) return null;
  return <div className="citations"><p className="eyebrow">Evidence</p>{sources.map((source) => {
    const key = `${source.document_id}-${source.page}`;
    const open = expanded === key;
    return <div key={key} className="citation">
      <button type="button" aria-expanded={open} onClick={() => setExpanded(open ? null : key)}>
        <span>{source.filename} · page {source.page}</span>
        {source.score != null && <span>{Math.round(source.score * 100)}% match</span>}
      </button>
      {open && <p>{source.snippet}</p>}
    </div>;
  })}</div>;
}
