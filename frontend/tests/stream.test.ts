import { describe, expect, it, vi } from "vitest";
import { parseEvent, streamChat } from "../src/api/client";

function responseFrom(text: string) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }), { status: 200 });
}

describe("SSE parsing", () => {
  it("parses a typed event", () => {
    expect(parseEvent('event: token\ndata: "hello"')).toEqual({ event: "token", data: "hello" });
  });

  it("handles sources, tokens, and stream completion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom(
      'event: session\ndata: {"session_id":"s1"}\n\nevent: sources\ndata: []\n\nevent: token\ndata: "hello"\n\nevent: done\ndata: {"session_id":"s1"}\n\n')));
    const events: string[] = [];
    await streamChat("question", null, ["doc"], {
      onSession: (id) => events.push(`session:${id}`), onSources: () => events.push("sources"),
      onToken: (token) => events.push(token), onDone: (id) => events.push(`done:${id}`),
    }, new AbortController().signal);
    expect(events).toEqual(["session:s1", "sources", "hello", "done:s1"]);
  });

  it("surfaces server error events", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom('event: error\ndata: {"message":"Ollama unavailable"}\n\n')));
    await expect(streamChat("q", null, ["doc"], { onSession() {}, onSources() {}, onToken() {}, onDone() {} }, new AbortController().signal)).rejects.toThrow("Ollama unavailable");
  });

  it("rejects a stream that ends without a terminal event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom('event: token\ndata: "partial"\n\n')));
    await expect(streamChat("q", null, ["doc"], { onSession() {}, onSources() {}, onToken() {}, onDone() {} }, new AbortController().signal)).rejects.toThrow("ended unexpectedly");
  });
});
