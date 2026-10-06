"use client";

import { useMemo, useState } from "react";
import { MoreHorizontal, Plus, Search, Trash2, Workflow } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useConversations } from "@/hooks/use-conversations";
import type { ConversationOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

type Props = {
  userId: string | null;
  conversationId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
};

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startThat = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = (startToday.getTime() - startThat.getTime()) / 86_400_000;
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return "Earlier";
}

function groupConversations(items: ConversationOut[]) {
  const order = ["Today", "Yesterday", "Earlier"] as const;
  const groups: Record<string, ConversationOut[]> = {
    Today: [],
    Yesterday: [],
    Earlier: [],
  };
  for (const c of items) {
    groups[dayLabel(c.created_at)].push(c);
  }
  return order
    .filter((k) => groups[k].length > 0)
    .map((k) => ({ label: k, items: groups[k] }));
}

export function Sidebar({ userId, conversationId, onSelect, onNew }: Props) {
  const { data: conversations = [] } = useConversations(userId);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const queryClient = useQueryClient();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, query]);

  const groups = useMemo(() => groupConversations(filtered), [filtered]);

  async function confirmDelete() {
    if (deleteId == null || !userId) return;
    try {
      await api.deleteConversation(deleteId, userId);
      toast.success("Conversation deleted");
      if (conversationId === deleteId) onNew();
      queryClient.invalidateQueries({ queryKey: ["conversations", userId] });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDeleteId(null);
    }
  }

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 border-b border-sidebar-border px-4 py-3">
        <div className="flex size-8 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground">
          <Workflow className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-semibold">Conversations</div>
          <div className="text-[11px] text-muted-foreground">Your designs</div>
        </div>
      </div>
      <div className="space-y-2 p-3">
        <Button className="w-full rounded-full" onClick={onNew}>
          <Plus className="mr-2 h-4 w-4" />
          New design
        </Button>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search…"
            className="h-8 rounded-full bg-background pl-8 text-sm"
          />
        </div>
      </div>
      <ScrollArea className="flex-1 px-2">
        <div className="space-y-4 pb-4">
          {filtered.length === 0 && (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">
              {conversations.length === 0
                ? "No conversations yet. Generate a design to start."
                : "No matches."}
            </p>
          )}
          {groups.map((g) => (
            <div key={g.label} className="space-y-1">
              <div className="px-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {g.label}
              </div>
              {g.items.map((c) => (
                <div
                  key={c.id}
                  className={cn(
                    "group flex items-center gap-1 rounded-xl px-2 py-2 text-sm hover:bg-sidebar-accent",
                    conversationId === c.id && "bg-sidebar-accent"
                  )}
                >
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => onSelect(c.id)}
                  >
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate font-medium">
                        {c.title}
                      </span>
                      {c.latest_version_no != null && (
                        <Badge
                          variant="secondary"
                          className="shrink-0 rounded-full text-[10px]"
                        >
                          v{c.latest_version_no}
                        </Badge>
                      )}
                    </div>
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      className={cn(
                        "inline-flex size-7 items-center justify-center rounded-md hover:bg-background",
                        conversationId === c.id
                          ? "opacity-70"
                          : "opacity-40 group-hover:opacity-100"
                      )}
                      aria-label="Conversation actions"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        variant="destructive"
                        onClick={() => setDeleteId(c.id)}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ))}
            </div>
          ))}
        </div>
      </ScrollArea>

      <Dialog open={deleteId != null} onOpenChange={() => setDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This removes the design, diagrams, and feedback for this chat.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
