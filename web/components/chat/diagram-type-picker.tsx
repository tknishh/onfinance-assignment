"use client";

import { useState } from "react";
import { Check, Layers, Plus, X } from "lucide-react";
import { useDiagramTypes } from "@/hooks/use-conversations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

type Props = {
  value: string[];
  onChange: (v: string[]) => void;
  /** When true, chips are read-only and Add opens the picker for new kinds. */
  followUp?: boolean;
  onAddKind?: (kind: string) => void;
};

export function DiagramTypePicker({
  value,
  onChange,
  followUp = false,
  onAddKind,
}: Props) {
  const { data: types = [] } = useDiagramTypes();
  const [open, setOpen] = useState(false);

  function toggle(v: string) {
    if (followUp) {
      if (!value.includes(v)) onAddKind?.(v);
      setOpen(false);
      return;
    }
    if (value.includes(v)) {
      if (value.length === 1) return;
      onChange(value.filter((x) => x !== v));
    } else {
      onChange([...value, v]);
    }
  }

  function selectCategory(cat: string) {
    if (followUp) return;
    const ids = types.filter((t) => t.category === cat).map((t) => t.value);
    onChange(Array.from(new Set([...value, ...ids])));
  }

  function clearToDefaults() {
    onChange(["sequence", "component", "class", "activity", "deployment"]);
  }

  const available = followUp
    ? types.filter((t) => !value.includes(t.value))
    : types;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-border bg-muted px-3 text-xs font-medium text-foreground hover:bg-muted/80">
            {followUp ? (
              <>
                <Plus className="h-3.5 w-3.5" />
                Add
              </>
            ) : (
              <>
                <Layers className="h-3.5 w-3.5" />
                Diagram types
                <Badge className="rounded-full bg-brand-yellow px-1.5 py-0 text-[10px] font-semibold text-ink-on-yellow">
                  {value.length}
                </Badge>
              </>
            )}
          </PopoverTrigger>
          <PopoverContent
            className="w-[min(92vw,28rem)] rounded-2xl p-3"
            align="start"
          >
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">
                {followUp ? "Add a diagram" : "Diagram types"}
              </p>
              {!followUp && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="rounded-full"
                  onClick={clearToDefaults}
                >
                  Reset
                </Button>
              )}
            </div>
            <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
              {Object.entries(
                available.reduce<Record<string, typeof types>>((acc, t) => {
                  (acc[t.category] ||= []).push(t);
                  return acc;
                }, {})
              ).map(([cat, items]) => (
                <div key={cat} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {cat}
                    </span>
                    {!followUp && (
                      <button
                        type="button"
                        className="text-[11px] font-medium text-foreground underline-offset-2 hover:underline"
                        onClick={() => selectCategory(cat)}
                      >
                        Select all
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {items.map((t) => {
                      const on = value.includes(t.value);
                      return (
                        <button
                          key={t.value}
                          type="button"
                          title={t.description}
                          onClick={() => toggle(t.value)}
                          className={cn(
                            "flex items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-xs transition",
                            on
                              ? "border-foreground/40 bg-accent ring-1 ring-foreground/20"
                              : "border-border bg-card hover:bg-muted"
                          )}
                        >
                          {!followUp && (
                            <span
                              className={cn(
                                "flex size-4 shrink-0 items-center justify-center rounded-md border",
                                on
                                  ? "border-foreground bg-foreground text-background"
                                  : "border-muted-foreground/40"
                              )}
                            >
                              {on && <Check className="size-3" />}
                            </span>
                          )}
                          <span className="font-medium capitalize text-foreground">
                            {t.value.replaceAll("_", " ")}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
              {followUp && available.length === 0 && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  All diagram types are already included.
                </p>
              )}
            </div>
          </PopoverContent>
        </Popover>

        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {value.map((v) => (
            <Badge
              key={v}
              variant="outline"
              className="h-7 shrink-0 gap-1 rounded-full border-border bg-muted px-2.5 text-xs capitalize text-foreground"
            >
              {v.replaceAll("_", " ")}
              {!followUp && (
                <button
                  type="button"
                  onClick={() => toggle(v)}
                  aria-label={`Remove ${v}`}
                  className="rounded-full p-0.5 text-muted-foreground hover:bg-card hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );
}
