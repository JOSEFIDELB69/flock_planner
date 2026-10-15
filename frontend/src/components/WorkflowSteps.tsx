"use client";

import Link from "next/link";

type P = { id: number; requirement_count: number; story_count: number; has_baseline: boolean; active_version_number: number | null; export_count: number };

export function WorkflowSteps({ p }: { p: P }) {
  const steps = [
    { label: "Proyecto", done: true, href: "settings" },
    { label: "Requisitos/Requerimientos", done: p.requirement_count > 0, href: "requirements" },
    { label: "Backlog", done: p.story_count > 0, href: "stories" },
    { label: "Estimación", done: p.story_count > 0, href: "estimates" },
    { label: "Línea base", done: p.has_baseline, href: "planning" },
    { label: "Optimización", done: (p.active_version_number ?? 0) > 1, href: "optimization" },
    { label: "PDF", done: p.export_count > 0, href: "reports" },
  ];
  const current = steps.findIndex((s) => !s.done);
  return (
    <ol className="steps" aria-label="Flujo de trabajo">
      {steps.map((s, i) => (
        <li key={s.label} className={`step ${s.done ? "done" : ""} ${i === current ? "current" : ""}`} aria-current={i === current ? "step" : undefined}>
          <span className="n" aria-hidden>
            {s.done ? "✓" : i + 1}
          </span>
          <Link href={`/projects/${p.id}/${s.href}`}>{s.label}</Link>
        </li>
      ))}
    </ol>
  );
}
