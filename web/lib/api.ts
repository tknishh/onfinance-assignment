import type {
  ConversationOut,
  DiagramResult,
  DiagramTypeInfo,
  ExampleInfo,
  TimelineOut,
} from "./types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  conversations: (userId: string) =>
    json<ConversationOut[]>(`/api/conversations?user_id=${encodeURIComponent(userId)}`),
  deleteConversation: (id: number, userId: string) =>
    json<{ ok: boolean }>(
      `/api/conversations/${id}?user_id=${encodeURIComponent(userId)}`,
      { method: "DELETE" }
    ),
  timeline: (id: number, userId: string) =>
    json<TimelineOut>(
      `/api/conversations/${id}/timeline?user_id=${encodeURIComponent(userId)}`
    ),
  diagramTypes: () => json<DiagramTypeInfo[]>("/api/diagram-types"),
  examples: () => json<ExampleInfo[]>("/api/examples"),
  feedback: (body: {
    user_id: string;
    version_id: number;
    diagram_id?: number | null;
    rating: -1 | 1;
    comment?: string | null;
  }) => json<{ ok: boolean }>("/api/feedback", { method: "POST", body: JSON.stringify(body) }),
  render: (diagramId: number, plantuml: string, userId: string) =>
    json<DiagramResult>(`/api/diagrams/${diagramId}/render`, {
      method: "POST",
      body: JSON.stringify({ plantuml, user_id: userId }),
    }),
};
