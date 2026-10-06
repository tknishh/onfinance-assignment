"use client";

import { useRef, useState } from "react";
import { History, Workflow } from "lucide-react";
import { useUserId } from "@/hooks/use-user-id";
import { useTimeline } from "@/hooks/use-conversations";
import { useChatStream } from "@/hooks/use-chat-stream";
import { Sidebar } from "@/components/sidebar";
import { ChatTimeline } from "@/components/chat/chat-timeline";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import { EmptyState } from "@/components/chat/empty-state";
import { DiagramWorkspace } from "@/components/workspace/diagram-workspace";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";

const DEFAULT_KINDS = [
  "sequence",
  "component",
  "class",
  "activity",
  "deployment",
];

export function AppShell() {
  const userId = useUserId();
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [selectedTab, setSelectedTab] = useState("architecture");
  const [kinds, setKinds] = useState(DEFAULT_KINDS);
  const [draft, setDraft] = useState("");
  const [jsonMode, setJsonMode] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const composerRef = useRef<ComposerHandle>(null);

  const { data: timeline } = useTimeline(conversationId, userId);
  const { send, abort, live, isStreaming } = useChatStream({
    userId,
    conversationId,
    setConversationId,
    setSelectedVersionId,
    kinds,
  });

  const resolvedVersionId = (() => {
    if (!timeline?.versions.length) return selectedVersionId;
    if (
      selectedVersionId != null &&
      timeline.versions.some((v) => v.id === selectedVersionId)
    ) {
      return selectedVersionId;
    }
    return timeline.versions[timeline.versions.length - 1].id;
  })();

  // Keep chips in sync with the active conversation's diagram set.
  const activeKinds =
    conversationId != null && timeline?.versions.length
      ? (() => {
          const v =
            timeline.versions.find((x) => x.id === resolvedVersionId) ||
            timeline.versions[timeline.versions.length - 1];
          return v?.diagram_types?.length ? v.diagram_types : kinds;
        })()
      : kinds;

  function onNew() {
    setConversationId(null);
    setSelectedVersionId(null);
    setSelectedTab("architecture");
    setHistoryOpen(false);
    setViewerOpen(false);
    setKinds(DEFAULT_KINDS);
  }

  function openDiagram(versionId: number, kind: string) {
    setSelectedVersionId(versionId);
    setSelectedTab(kind);
    setViewerOpen(true);
  }

  function openArchitecture(versionId: number) {
    setSelectedVersionId(versionId);
    setSelectedTab("architecture");
    setViewerOpen(true);
  }

  function pickSample(prompt: string) {
    setJsonMode(false);
    setDraft(prompt);
    requestAnimationFrame(() => composerRef.current?.focus());
  }

  function addKind(kind: string) {
    send(`also add a ${kind.replaceAll("_", " ")} diagram`);
  }

  const isEmptyHome = !conversationId && !live;

  const composer = (
    <Composer
      ref={composerRef}
      hasConversation={conversationId != null}
      kinds={activeKinds}
      onKindsChange={setKinds}
      isStreaming={isStreaming}
      onSend={(m) => send(m)}
      onAbort={abort}
      draft={draft}
      onDraftChange={setDraft}
      jsonMode={jsonMode}
      onJsonModeChange={setJsonMode}
      onAddKind={addKind}
      embedded={isEmptyHome}
    />
  );

  return (
    <div
      className={`flex h-dvh flex-col bg-background ${isEmptyHome ? "of-grid" : ""}`}
    >
      <header className="flex items-center gap-2 border-b border-border/80 bg-background/95 px-3 py-2.5 backdrop-blur-md sm:gap-3 sm:px-4">
        <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
          <SheetTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                className="h-9 gap-2 rounded-full px-2.5 sm:px-3"
                aria-label="History"
              />
            }
          >
            <History className="h-4 w-4" />
            <span className="hidden text-sm font-medium sm:inline">History</span>
          </SheetTrigger>
          <SheetContent side="left" className="w-80 p-0 sm:max-w-sm">
            <Sidebar
              userId={userId}
              conversationId={conversationId}
              onSelect={(id) => {
                setConversationId(id);
                setHistoryOpen(false);
                setViewerOpen(false);
              }}
              onNew={onNew}
            />
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-xl bg-foreground text-background shadow-sm sm:size-9 sm:rounded-2xl">
            <Workflow className="h-4 w-4" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">UML Studio</div>
            <div className="hidden text-[11px] text-muted-foreground sm:block">
              by OnFinance AI
            </div>
          </div>
        </div>

        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>

      <div className="flex min-h-0 w-full flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isEmptyHome ? (
            <>
              <EmptyState onPick={pickSample} />
              {composer}
            </>
          ) : (
            <ChatTimeline
              timeline={timeline}
              live={live}
              selectedVersionId={resolvedVersionId}
              selectedTab={selectedTab}
              viewerOpen={viewerOpen}
              onOpenDiagram={openDiagram}
              onOpenArchitecture={openArchitecture}
            />
          )}
        </div>
        {!isEmptyHome && composer}
      </div>

      <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
        <DialogContent
          showCloseButton
          className="flex h-[min(92vh,900px)] w-[min(96vw,1100px)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
        >
          <DialogHeader className="sr-only">
            <DialogTitle>Diagram viewer</DialogTitle>
            <DialogDescription>
              View and navigate generated UML diagrams. Press Escape to close.
            </DialogDescription>
          </DialogHeader>
          {timeline && userId ? (
            <DiagramWorkspace
              timeline={timeline}
              versionId={resolvedVersionId}
              selectedTab={selectedTab}
              userId={userId}
              onVersionChange={setSelectedVersionId}
              onTabChange={setSelectedTab}
              onApplyRevision={(c) => {
                setViewerOpen(false);
                send(c);
              }}
              onClose={() => setViewerOpen(false)}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
              No diagrams yet
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
