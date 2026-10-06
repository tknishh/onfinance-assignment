"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { DesignModel, LiveState, TimelineOut, VersionOut } from "@/lib/types";

type Opts = {
  userId: string | null;
  conversationId: number | null;
  setConversationId: (id: number | null) => void;
  setSelectedVersionId: (id: number | null) => void;
  kinds: string[];
};

export function useChatStream({
  userId,
  conversationId,
  setConversationId,
  setSelectedVersionId,
  kinds,
}: Opts) {
  const [live, setLive] = useState<LiveState | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef(conversationId);
  const queryClient = useQueryClient();

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  const send = useCallback(
    async (message: string, opts?: { kinds?: string[] }) => {
      if (!userId || !message.trim()) return;
      abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setLive({ userMessage: message, diagrams: {} });

      try {
        await fetchEventSource("/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            message,
            conversation_id: conversationIdRef.current,
            diagram_types: opts?.kinds ?? kinds,
          }),
          signal: controller.signal,
          openWhenHidden: true,
          onmessage(ev) {
            const data = ev.data ? JSON.parse(ev.data) : null;
            if (ev.event === "conversation") {
              setConversationId(data.id);
              conversationIdRef.current = data.id;
              queryClient.invalidateQueries({ queryKey: ["conversations", userId] });
            } else if (ev.event === "intent") {
              setLive((prev) =>
                prev ? { ...prev, intent: data } : prev
              );
            } else if (ev.event === "design_model") {
              setLive((prev) =>
                prev ? { ...prev, designModel: data as DesignModel | null } : prev
              );
            } else if (ev.event === "diagram_started") {
              setLive((prev) => {
                if (!prev) return prev;
                return {
                  ...prev,
                  diagrams: {
                    ...prev.diagrams,
                    [data.kind]: { status: "queued" },
                  },
                };
              });
            } else if (ev.event === "diagram") {
              setLive((prev) => {
                if (!prev) return prev;
                return {
                  ...prev,
                  diagrams: {
                    ...prev.diagrams,
                    [data.kind]: {
                      status: data.is_valid ? "done" : "failed",
                      data,
                    },
                  },
                };
              });
            } else if (ev.event === "answer") {
              setLive((prev) =>
                prev ? { ...prev, answer: data.content } : prev
              );
            } else if (ev.event === "version") {
              const version = data as VersionOut;
              setSelectedVersionId(version.id);
              const cid = conversationIdRef.current;
              if (cid != null) {
                queryClient.setQueriesData<TimelineOut>(
                  { queryKey: ["timeline", cid] },
                  (old) => {
                    if (!old) return old;
                    const versions = [...old.versions];
                    const idx = versions.findIndex((v) => v.id === version.id);
                    if (idx >= 0) versions[idx] = version;
                    else versions.push(version);
                    return { ...old, versions };
                  }
                );
              }
            } else if (ev.event === "error") {
              setLive((prev) =>
                prev ? { ...prev, error: data.message } : prev
              );
              toast.error(data.message || "Something went wrong");
            } else if (ev.event === "done") {
              void (async () => {
                if (data.conversation_id != null) {
                  setConversationId(data.conversation_id);
                  conversationIdRef.current = data.conversation_id;
                  await queryClient.invalidateQueries({
                    queryKey: ["timeline", data.conversation_id],
                  });
                }
                if (data.version_id != null) {
                  setSelectedVersionId(data.version_id);
                }
                await queryClient.invalidateQueries({
                  queryKey: ["conversations", userId],
                });
                setLive(null);
              })();
            }
          },
          onerror(err) {
            // Throw to stop retries
            throw err;
          },
        });
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          toast.error((e as Error).message || "Stream failed");
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [
      userId,
      kinds,
      abort,
      setConversationId,
      setSelectedVersionId,
      queryClient,
    ]
  );

  return { send, abort, live, isStreaming };
}
