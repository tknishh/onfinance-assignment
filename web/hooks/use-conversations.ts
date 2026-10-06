"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useConversations(userId: string | null) {
  return useQuery({
    queryKey: ["conversations", userId],
    queryFn: () => api.conversations(userId!),
    enabled: !!userId,
  });
}

export function useTimeline(
  conversationId: number | null,
  userId: string | null
) {
  return useQuery({
    queryKey: ["timeline", conversationId, userId],
    queryFn: () => api.timeline(conversationId!, userId!),
    enabled: conversationId != null && !!userId,
  });
}

export function useDiagramTypes() {
  return useQuery({
    queryKey: ["diagram-types"],
    queryFn: () => api.diagramTypes(),
    staleTime: 60_000,
  });
}

export function useExamples() {
  return useQuery({
    queryKey: ["examples"],
    queryFn: () => api.examples(),
    staleTime: 60_000,
  });
}
