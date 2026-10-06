"use client";

import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DiagramResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  diagram: DiagramResult;
  conversationId: number;
  userId: string;
};

function EditorBody({
  diagram,
  conversationId,
  userId,
  onClose,
}: {
  diagram: DiagramResult;
  conversationId: number;
  userId: string;
  onClose: () => void;
}) {
  const [code, setCode] = useState(diagram.plantuml);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const queryClient = useQueryClient();
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.render(diagram.diagram_id, code, userId);
      toast.success("Re-rendered and saved");
      queryClient.invalidateQueries({
        queryKey: ["timeline", conversationId, userId],
      });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          Edit PlantUML — {diagram.kind.replaceAll("_", " ")}
        </DialogTitle>
      </DialogHeader>
      <div className="overflow-hidden rounded-lg border">
        <CodeMirror
          value={code}
          height="min(60vh, 520px)"
          theme={dark ? oneDark : "light"}
          onChange={setCode}
          basicSetup={{ lineNumbers: true, foldGutter: true }}
        />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={save} disabled={busy}>
          Render & save
        </Button>
      </DialogFooter>
    </>
  );
}

export function CodeEditorDialog({
  open,
  onOpenChange,
  diagram,
  conversationId,
  userId,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl sm:max-w-3xl">
        {open && (
          <EditorBody
            key={diagram.diagram_id}
            diagram={diagram}
            conversationId={conversationId}
            userId={userId}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
