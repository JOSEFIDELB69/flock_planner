"use client";

import { useMemo } from "react";

import { fmtDate, fmtNum } from "@/lib/format";
import type { Milestone, ScheduledTask } from "@/lib/types";

type Mode = "story" | "member" | "epic";

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Cronograma calculado por el motor. Barras con contorno oscuro = camino crítico. */
export function Gantt({
  schedule,
  startDate,
  criticalIds,
  profileOrder,
  qaKeys,
  mode,
  milestones = [],
}: {
  schedule: ScheduledTask[];
  startDate: string;
  criticalIds: Set<string>;
  profileOrder: string[];
  qaKeys: Set<string>;
  mode: Mode;
  milestones?: Milestone[];
}) {
  const { groups, end } = useMemo(() => {
    // el eje llega hasta el último hito (p. ej. la entrega con reserva por imprevistos)
    const lastMilestone = Math.max(0, ...milestones.map((m) => (new Date(`${m.date}T00:00:00`).getTime() - new Date(`${startDate}T00:00:00`).getTime()) / 86400000 + 1));
    const end = Math.max(1, Math.ceil(Math.max(...schedule.map((s) => s.finish), 1, lastMilestone)));
    const map = new Map<string, { label: string; items: ScheduledTask[] }>();
    for (const s of schedule) {
      const key = mode === "member" ? s.member_id : mode === "epic" ? s.epic_id : s.story_id;
      const label = mode === "member" ? s.member_name || "Sin asignar" : mode === "epic" ? s.epic_title : s.story_title;
      if (!map.has(key)) map.set(key, { label, items: [] });
      map.get(key)!.items.push(s);
    }
    const groups = Array.from(map.values()).sort((a, b) => Math.min(...a.items.map((x) => x.start)) - Math.min(...b.items.map((x) => x.start)));
    return { groups, end };
  }, [schedule, mode, milestones, startDate]);

  const pct = (v: number) => `${(v / end) * 100}%`;
  const weeks = Array.from({ length: Math.floor(end / 7) + 1 }, (_, i) => i * 7);
  const barClass = (s: ScheduledTask) => {
    if (qaKeys.has(s.profile_key)) return "qa";
    const idx = profileOrder.indexOf(s.profile_key);
    return idx === 1 ? "p2" : idx === 3 ? "p4" : idx > 3 ? "other" : "";
  };
  const showTasks = mode !== "epic" && schedule.length <= 250;

  return (
    <div className="gantt" role="figure" aria-label="Cronograma de la planificación">
      <div className="gantt-grid" style={{ gridTemplateColumns: "minmax(220px, 28%) 1fr" }}>
        <div className="gantt-label group" style={{ borderTop: 0 }}>
          {mode === "member" ? "Persona" : mode === "epic" ? "Épica" : "Historia / tarea"}
        </div>
        <div className="gantt-scale">
          {weeks.map((w) => (
            <span key={w} style={{ left: pct(w) }}>
              {fmtDate(addDays(startDate, w)).slice(0, 5)}
            </span>
          ))}
        </div>
        {groups.map((g) => {
          const gs = Math.min(...g.items.map((x) => x.start));
          const gf = Math.max(...g.items.map((x) => x.finish));
          return (
            <GroupRows key={g.label + gs} label={g.label}>
              <div className="gantt-track group">
                {weeks.map((w) => (
                  <i key={w} className="gantt-weekline" style={{ left: pct(w) }} />
                ))}
                {mode === "member" ? (
                  g.items.map((s) => (
                    <span
                      key={s.task_id}
                      className={`gantt-bar ${barClass(s)} ${criticalIds.has(s.task_id) ? "critical" : ""}`}
                      style={{ left: pct(s.start), width: pct(Math.max(s.finish - s.start, 0.05)) }}
                      title={`${s.title} · ${fmtDate(s.start_date)} → ${fmtDate(s.end_date)} · ${fmtNum(s.effective_hours)} h`}
                    />
                  ))
                ) : (
                  <span className="gantt-bar other" style={{ left: pct(gs), width: pct(Math.max(gf - gs, 0.05)), opacity: 0.55 }} title={`${g.label}`} />
                )}
              </div>
              {showTasks && mode === "story" &&
                g.items.map((s) => (
                  <TaskRow key={s.task_id} s={s} pct={pct} weeks={weeks} cls={`${barClass(s)} ${criticalIds.has(s.task_id) ? "critical" : ""}`} />
                ))}
            </GroupRows>
          );
        })}
        {milestones.length > 0 && (
          <>
            <div className="gantt-label group">Hitos</div>
            <div className="gantt-track group">
              {milestones.map((m) => {
                const day = (new Date(`${m.date}T00:00:00`).getTime() - new Date(`${startDate}T00:00:00`).getTime()) / 86400000 + 1;
                return <span key={m.name} className="gantt-bar milestone" style={{ left: `calc(${pct(day)} - 6px)` }} title={`${m.name}: ${fmtDate(m.date)}`} />;
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function GroupRows({ label, children }: { label: string; children: React.ReactNode }) {
  const [track, ...rest] = Array.isArray(children) ? children : [children];
  return (
    <>
      <div className="gantt-label group" title={label}>
        {label}
      </div>
      {track}
      {rest}
    </>
  );
}

function TaskRow({ s, pct, weeks, cls }: { s: ScheduledTask; pct: (v: number) => string; weeks: number[]; cls: string }) {
  return (
    <>
      <div className="gantt-label" title={`${s.title} — ${s.member_name}`}>
        <span className="subtle">{s.member_name} · </span>
        {s.title}
      </div>
      <div className="gantt-track">
        {weeks.map((w) => (
          <i key={w} className="gantt-weekline" style={{ left: pct(w) }} />
        ))}
        <span
          className={`gantt-bar ${cls}`}
          style={{ left: pct(s.start), width: pct(Math.max(s.finish - s.start, 0.05)) }}
          title={`${s.title} · ${fmtDate(s.start_date)} → ${fmtDate(s.end_date)} · ${fmtNum(s.effective_hours)} h${s.wait_days > 0 ? ` · esperó ${fmtNum(s.wait_days)} días` : ""}`}
        />
      </div>
    </>
  );
}

/** Diagrama de dependencias entre historias por niveles (izquierda → derecha). */
export function DependencyGraph({ stories }: { stories: { id: number; code: string; title: string; depends_on_ids: number[] }[] }) {
  const layout = useMemo(() => {
    const byId = new Map(stories.map((s) => [s.id, s]));
    const level = new Map<number, number>();
    const visit = (id: number, stack: Set<number>): number => {
      if (level.has(id)) return level.get(id)!;
      if (stack.has(id)) return 0;
      stack.add(id);
      const s = byId.get(id);
      const l = s && s.depends_on_ids.length ? Math.max(...s.depends_on_ids.filter((d) => byId.has(d)).map((d) => visit(d, stack) + 1), 0) : 0;
      level.set(id, l);
      return l;
    };
    stories.forEach((s) => visit(s.id, new Set()));
    const cols: number[][] = [];
    stories.forEach((s) => {
      const l = level.get(s.id) ?? 0;
      (cols[l] ??= []).push(s.id);
    });
    const pos = new Map<number, { x: number; y: number }>();
    cols.forEach((ids, c) => ids.forEach((id, r) => pos.set(id, { x: 20 + c * 240, y: 20 + r * 64 })));
    const width = Math.max(1, cols.length) * 240 + 20;
    const height = Math.max(...cols.map((c) => c.length), 1) * 64 + 20;
    return { pos, width, height, byId };
  }, [stories]);
  const edges = stories.flatMap((s) => s.depends_on_ids.filter((d) => layout.pos.has(d)).map((d) => ({ from: d, to: s.id })));
  if (!edges.length) return <p className="muted">No hay dependencias explícitas entre historias. El motor aplica igualmente la secuencia desarrollo → QA dentro de cada historia.</p>;
  return (
    <div className="dep-graph">
      <svg width={layout.width} height={layout.height} role="img" aria-label="Diagrama de dependencias entre historias">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ink-subtle)" />
          </marker>
        </defs>
        {edges.map((e) => {
          const a = layout.pos.get(e.from)!;
          const b = layout.pos.get(e.to)!;
          return <path key={`${e.from}-${e.to}`} d={`M ${a.x + 200} ${a.y + 22} C ${a.x + 220} ${a.y + 22}, ${b.x - 20} ${b.y + 22}, ${b.x} ${b.y + 22}`} fill="none" stroke="var(--ink-subtle)" strokeWidth={1.5} markerEnd="url(#arrow)" />;
        })}
        {stories.map((s) => {
          const p = layout.pos.get(s.id)!;
          return (
            <g key={s.id} transform={`translate(${p.x},${p.y})`}>
              <rect width={200} height={44} rx={10} fill="var(--surface)" stroke="var(--border-strong)" />
              <text x={10} y={18} fontSize={12} fontWeight={700}>
                {s.code}
              </text>
              <text x={10} y={34} fontSize={12}>
                {s.title.length > 28 ? `${s.title.slice(0, 27)}…` : s.title}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
