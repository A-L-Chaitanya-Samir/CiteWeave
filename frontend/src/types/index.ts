export interface SourceCitation { document_id: string; filename: string; page: number; snippet: string; score?: number | null }
export interface DocumentInfo { document_id: string; filename: string; chunk_count: number; size_bytes: number; status: string; uploaded_at: string; ingested_at?: string | null; error_message?: string | null }
export interface UploadResult { filename: string; status: string; document?: DocumentInfo | null; error?: string | null }
export interface ChatMessage { id: string; role: "user" | "assistant"; content: string; sources?: SourceCitation[]; status?: string }
export interface SessionInfo { id: string; title: string | null; created_at: string; updated_at: string }
export interface ComponentStatus { ok: boolean; detail?: string | null }
export interface ReadinessStatus { status: string; sqlite: ComponentStatus; chroma: ComponentStatus; ollama: ComponentStatus; models: ComponentStatus; ollama_models: string[]; message?: string | null }
