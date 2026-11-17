import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentUpload } from "../src/components/DocumentUpload";
import { SourceCitationList } from "../src/components/SourceCitation";
import { ChatPanel } from "../src/components/ChatPanel";

const api = vi.hoisted(() => ({
  listSessions: vi.fn(), getSessionMessages: vi.fn(), deleteSession: vi.fn(), streamChat: vi.fn(),
  uploadDocuments: vi.fn(), deleteDocument: vi.fn(), reindexDocument: vi.fn(),
}));
vi.mock("../src/api/client", async (original) => ({ ...(await original()), ...api, mapSessionMessages: (items: unknown[]) => items }));

const document = { document_id: "d1", filename: "paper.pdf", chunk_count: 4, size_bytes: 200,
  status: "complete", uploaded_at: "2026-01-01T00:00:00Z" };

beforeEach(() => { api.listSessions.mockResolvedValue({ sessions: [] }); api.streamChat.mockReset(); });

describe("document panel", () => {
  it("validates uploads in the browser", async () => {
    const view = render(<DocumentUpload documents={[]} selected={new Set()} onSelection={() => undefined} onRefresh={async () => undefined} />);
    const input = view.container.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["text"], "notes.txt", { type: "text/plain" })] } });
    expect(await screen.findByText("notes.txt is not a PDF.")).toBeInTheDocument();
  });

  it("updates document selection", () => {
    const onSelection = vi.fn();
    render(<DocumentUpload documents={[document]} selected={new Set(["d1"])} onSelection={onSelection} onRefresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect([...onSelection.mock.calls[0][0]]).toEqual([]);
  });
});

it("expands a page citation", () => {
  render(<SourceCitationList sources={[{ document_id: "d1", filename: "paper.pdf", page: 3, snippet: "quoted evidence", score: .91 }]} />);
  fireEvent.click(screen.getByRole("button", { name: /page 3/ }));
  expect(screen.getByText("quoted evidence")).toBeVisible();
  expect(screen.getByText("91% match")).toBeInTheDocument();
});

describe("chat panel", () => {
  it("loads a selected recent session", async () => {
    api.listSessions.mockResolvedValue({ sessions: [{ id: "s1", title: "Prior work", created_at: "", updated_at: "" }] });
    api.getSessionMessages.mockResolvedValue({ session_id: "s1", messages: [{ id: "m1", role: "assistant", content: "Saved answer", sources: [] }] });
    render(<ChatPanel documentIds={["d1"]} selectedLabel="1 document selected" />);
    const select = await screen.findByRole("combobox");
    fireEvent.change(select, { target: { value: "s1" } });
    expect(await screen.findByText("Saved answer")).toBeInTheDocument();
  });

  it("cleans up loading state and offers retry after stream failure", async () => {
    api.streamChat.mockRejectedValue(new Error("Ollama unavailable"));
    render(<ChatPanel documentIds={["d1"]} selectedLabel="1 document selected" />);
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "What happened?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect((await screen.findAllByText("Ollama unavailable")).length).toBe(2);
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Stop generating" })).not.toBeInTheDocument());
  });
});
