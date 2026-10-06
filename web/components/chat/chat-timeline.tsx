"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";
import type { LiveState, TimelineOut } from "@/lib/types";
import { AssistantCard } from "@/components/chat/assistant-card";
import { GenerationProgress } from "@/components/chat/generation-progress";

type Props = {
  timeline?: TimelineOut;
  live: LiveState | null;
  selectedVersionId: number | null;
  selectedTab: string;
  viewerOpen: boolean;
  onOpenDiagram: (versionId: number, kind: string) => void;
  onOpenArchitecture: (versionId: number) => void;
};

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <button
        type="button"
        title="Click to copy"
        onClick={() => {
          void navigator.clipboard.writeText(content);
          toast.success("Copied");
        }}
        className="max-w-[85%] whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-2.5 text-left text-sm text-foreground shadow-sm transition hover:border-foreground/20"
      >
        {content}
      </button>
    </div>
  );
}

export function ChatTimeline({
  timeline,
  live,
  selectedVersionId,
  selectedTab,
  viewerOpen,
  onOpenDiagram,
  onOpenArchitecture,
}: Props) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline?.messages.length, live]);

  const versionsById = new Map(
    (timeline?.versions || []).map((v) => [v.id, v])
  );

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-6">
      {(timeline?.messages || []).map((m) =>
        m.role === "user" ? (
          <UserBubble key={m.id} content={m.content} />
        ) : (
          <AssistantCard
            key={m.id}
            message={m}
            version={m.version_id ? versionsById.get(m.version_id) : undefined}
            selectedVersionId={selectedVersionId}
            selectedTab={selectedTab}
            viewerOpen={viewerOpen}
            onOpenDiagram={onOpenDiagram}
            onOpenArchitecture={onOpenArchitecture}
          />
        )
      )}
      {live && (
        <>
          <UserBubble content={live.userMessage} />
          <GenerationProgress live={live} />
        </>
      )}
      <div ref={bottom} />
    </div>
  );
}
