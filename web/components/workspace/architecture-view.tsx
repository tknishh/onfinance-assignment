"use client";

import type { DesignModel } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { downloadText } from "@/lib/svg";

export function ArchitectureView({ model }: { model: DesignModel }) {
  const layers: Record<string, string[]> = {};
  for (const c of model.components) {
    (layers[c.layer || "Core"] ||= []).push(c.name);
  }
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold">{model.system_name}</h2>
          {model.summary && (
            <p className="mt-1 text-sm text-muted-foreground">{model.summary}</p>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          className="shrink-0 rounded-full"
          onClick={() =>
            downloadText(
              "design_model.json",
              JSON.stringify(model, null, 2),
              "application/json"
            )
          }
        >
          Download JSON
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
        <Card className="shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Components</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {Object.entries(layers).map(([layer, names]) => (
              <div key={layer}>
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {layer}
                </div>
                <div className="mt-1">{names.join(", ")}</div>
              </div>
            ))}
            {!Object.keys(layers).length && (
              <span className="text-muted-foreground">None</span>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Actors</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {model.actors.map((a) => (
                <div key={a.name}>{a.name}</div>
              ))}
              {!model.actors.length && (
                <span className="text-muted-foreground">None</span>
              )}
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Data stores</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {model.data_stores.map((d) => (
                <div key={d.name}>
                  {d.name}
                  {d.technology ? (
                    <span className="text-muted-foreground">
                      {" "}
                      ({d.technology})
                    </span>
                  ) : null}
                </div>
              ))}
              {!model.data_stores.length && (
                <span className="text-muted-foreground">None</span>
              )}
            </CardContent>
          </Card>
          <Card className="shadow-none">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">External systems</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {model.external_systems.map((e) => (
                <div key={e.name}>{e.name}</div>
              ))}
              {!model.external_systems.length && (
                <span className="text-muted-foreground">None</span>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {!!model.main_flow.length && (
        <Card className="shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Main flow</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {[...model.main_flow]
              .sort((a, b) => a.step - b.step)
              .map((s) => (
                <div key={s.step} className="flex flex-wrap items-baseline gap-1.5">
                  <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold">
                    {s.step}
                  </span>
                  <span className="font-medium">{s.source}</span>
                  <span className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    →
                  </span>
                  <span className="font-medium">{s.target}</span>
                  <span className="text-muted-foreground">· {s.message}</span>
                </div>
              ))}
          </CardContent>
        </Card>
      )}

      {!!model.entities.length && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {model.entities.map((e) => (
            <Card key={e.name} className="shadow-none">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">{e.name}</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                {e.attributes.join(", ") || "—"}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
