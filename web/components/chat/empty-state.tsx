"use client";

import { ArrowRight } from "lucide-react";
import { useExamples } from "@/hooks/use-conversations";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type Props = {
  onPick: (prompt: string) => void;
};

/** One-line teasers — full prompt goes into the composer on click. */
const TEASERS: Record<string, string> = {
  "SEBI compliance": "Monitor SEBI circulars, gaps, and org impact.",
  "Order checkout": "E-commerce checkout with payments and inventory.",
  "Data pipeline": "Batch ETL from S3 through Spark into a warehouse.",
};

export function EmptyState({ onPick }: Props) {
  const { data: examples = [] } = useExamples();
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-2 pt-8 sm:pt-10">
      <div className="space-y-2 text-center">
        <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-[2rem]">
          What are you designing?
        </h1>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          Describe a software system. Get matching UML diagrams.
        </p>
      </div>
      <div className="grid w-full gap-3 sm:grid-cols-3">
        {examples.map((ex) => (
          <Card
            key={ex.label}
            role="button"
            tabIndex={0}
            className="cursor-pointer rounded-2xl border border-border bg-card/90 shadow-none transition hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-md"
            onClick={() => onPick(ex.prompt)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onPick(ex.prompt);
              }
            }}
          >
            <CardHeader className="space-y-1.5 p-4">
              <CardTitle className="flex items-center justify-between text-sm text-foreground">
                {ex.label}
                <ArrowRight className="h-3.5 w-3.5 opacity-50" />
              </CardTitle>
              <CardDescription className="line-clamp-2 text-xs text-muted-foreground">
                {TEASERS[ex.label] || ex.prompt.slice(0, 80)}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}
