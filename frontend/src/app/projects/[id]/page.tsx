"use client";

import { AlertTriangle, CalendarClock, Clock, Gauge, Layers, ListChecks, Users } from "lucide-react";
import Link from "next/link";

import { DonutChart, HoursBarChart, TrendChart } from "@/components/charts";
import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Card, EmptyState, ErrorState, Loading, PageHeader, Progress, Stat } from "@/components/ui";
import { fmtDate, fmtHours, fmtMoney, fmtNum, fmtPct, SCENARIO_STATUS_LABEL } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { WorkflowSteps } from "@/components/WorkflowSteps";
import type { Bottleneck, Milestone, ProfileMetrics, Risk } from "@/lib/types";

type Dash = {
  backlog: { hours_by_profile: Record<string, number>; epic_hours: { code: string; title: string; hours: number }[] };
  active_version: null | {
    id: number;
    version_number: number;
    label: string;
    is_baseline: boolean;
    duration: number;
    completion_date: string;
    start_date: string;
    planned_effort: number;
    base_effort: number;
    by_profile: ProfileMetrics[];
    main_bottleneck: string | null;
    bottlenecks: Bottleneck[];
    risks: Risk[];
    milestones: Milestone[];
    total_cost: number | null;
    total_daily_capacity: number;
    meets_target: boolean | null;
    delta_vs_baseline_days?: number;
    delta_vs_baseline_pct?: number;
  };
  baseline: null | { id: number; version_number: number; duration: number; completion_date: string };
  versions_trend: { version_number: number; label: string; duration: number; is_baseline: boolean }[];
  scenarios: { id: number; name: string; status: string; duration: number | null; variation_pct: number | null; time_savings_days: number | null }[];
};

export default function ProjectOverview() {
  const { project } = useProject();
  const { data, error, loading, reload } = useApi<Dash>(`/projects/${project.id}/dashboard`);
  const v = data?.active_version;
  const names = Object.fromEntries((v?.by_profile ?? []).map((p) => [p.profile_key, p.profile_name]));
  const top = v?.bottlenecks?.[0];

  return (
    <>
      <PageHeader title={project.name} description={project.business_objective || project.description || "Sin objetivo de negocio cargado."} />
      <div style={{ marginBottom: 20 }}>
        <WorkflowSteps p={project} />
      </div>
      {loading && !data && <Loading />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {data && (
        <div className="stack">
          {!v && (
            <Alert tone="info" title="Todavía no hay un plan confirmado">
              Los indicadores de duración y capacidad aparecen cuando confirmás la planificación inicial. <Link href={`/projects/${project.id}/planning`}>Ir a Planificación</Link>
            </Alert>
          )}
          <div className="grid kpis">
            <Stat brand label="Duración estimada" value={v ? `${v.duration} días` : "—"} icon={<CalendarClock size={16} aria-hidden />} hint={v ? `Versión activa v${v.version_number}${v.is_baseline ? " (línea base)" : ""}` : "Sin plan confirmado"} />
            <Stat label="Fin estimado" value={fmtDate(v?.completion_date)} icon={<CalendarClock size={16} aria-hidden />} hint={v?.meets_target === false ? "No cumple la fecha objetivo" : project.target_date ? `Objetivo: ${fmtDate(project.target_date)}` : undefined} />
            <Stat label="Esfuerzo total estimado" value={fmtHours(v?.planned_effort ?? project.total_hours)} icon={<Clock size={16} aria-hidden />} hint={v ? `${fmtNum(v.base_effort)} h base + revisión y retrabajo` : "Horas base del backlog"} />
            <Stat label="Épicas / historias" value={`${project.epic_count} / ${project.story_count}`} icon={<Layers size={16} aria-hidden />} hint={`${project.task_count} subtareas`} />
            <Stat label="Capacidad diaria del equipo" value={v ? fmtHours(v.total_daily_capacity) : "—"} icon={<Users size={16} aria-hidden />} hint="Horas productivas efectivas por día" />
            <Stat
              label="Diferencia vs. línea base"
              value={v && data.baseline && v.delta_vs_baseline_days !== undefined ? `${v.delta_vs_baseline_days > 0 ? "+" : ""}${v.delta_vs_baseline_days} días` : "—"}
              icon={<Gauge size={16} aria-hidden />}
              hint={data.baseline ? `Comparado con la línea base v${data.baseline.version_number} (${data.baseline.duration} días)${v?.delta_vs_baseline_pct !== undefined ? ` · ${fmtPct(v.delta_vs_baseline_pct, 1, true)}` : ""}` : "Sin línea base"}
            />
          </div>

          <div className="grid c2">
            <Card title="Horas por perfil" sub={v ? `Horas planificadas de la versión v${v.version_number}` : "Horas base del backlog actual"}>
              <HoursBarChart
                data={
                  v
                    ? v.by_profile.filter((p) => p.planned_hours > 0).map((p) => ({ name: p.profile_name, value: p.planned_hours }))
                    : Object.entries(data.backlog.hours_by_profile).map(([k, h]) => ({ name: k, value: h }))
                }
              />
            </Card>
            <Card title="Distribución del esfuerzo por épica" sub="Horas base del backlog actual">
              {data.backlog.epic_hours.length ? <DonutChart data={data.backlog.epic_hours.map((e) => ({ name: `${e.code} ${e.title}`, value: e.hours }))} /> : <EmptyState title="Sin backlog">Generá o cargá el backlog para ver la distribución.</EmptyState>}
            </Card>
          </div>

          {v && (
            <div className="grid c3">
              <Card title="Utilización de capacidad" sub="Horas asignadas / disponibles durante el plan">
                <ul className="list-plain">
                  {v.by_profile.map((p) => (
                    <li key={p.profile_key}>
                      <div className="row between small">
                        <span>
                          {p.profile_name} · {p.members} pers.
                        </span>
                        <strong>{fmtPct(p.utilization * 100)}</strong>
                      </div>
                      <Progress value={p.utilization} label={`Utilización ${p.profile_name}`} />
                    </li>
                  ))}
                </ul>
              </Card>
              <Card title="Perfil con mayor carga" sub="Cuello de botella principal según el motor">
                {top ? (
                  <>
                    <h3>{top.profile_name}</h3>
                    <ul className="ac-list">
                      {top.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                    <Link className="btn secondary sm mt" href={`/projects/${project.id}/optimization`}>
                      Optimizar planificación y duración
                    </Link>
                  </>
                ) : (
                  <p className="muted">Sin datos.</p>
                )}
              </Card>
              <Card title="Riesgos principales">
                {v.risks.length ? (
                  <ul className="list-plain">
                    {v.risks.map((r) => (
                      <li key={r.title} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
                        <AlertTriangle size={16} color={r.severity === "high" ? "var(--danger)" : "var(--warning)"} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
                        <div>
                          <strong>{r.title}</strong> <Badge tone={r.severity === "high" ? "danger" : "warning"}>{r.severity === "high" ? "Alta" : r.severity === "medium" ? "Media" : "Baja"}</Badge>
                          <div className="subtle">{r.detail}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">El motor no detectó riesgos relevantes.</p>
                )}
              </Card>
            </div>
          )}

          <div className="grid c2">
            <Card title="Evolución de la duración entre versiones" sub="Días laborables por versión">
              <TrendChart data={data.versions_trend.map((t) => ({ name: `v${t.version_number}${t.is_baseline ? " (base)" : ""}`, value: t.duration }))} />
            </Card>
            <Card title="Escenarios" sub={data.baseline ? `Diferencias frente a la línea base v${data.baseline.version_number}` : undefined} actions={<Link className="btn ghost sm" href={`/projects/${project.id}/optimization`}>Ver todos</Link>}>
              {data.scenarios.length ? (
                <div className="table-wrap">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>Escenario</th>
                      <th>Estado</th>
                      <th className="num">Días</th>
                      <th className="num">Variación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.scenarios.slice(0, 6).map((s) => (
                      <tr key={s.id}>
                        <td>{s.name}</td>
                        <td>
                          <Badge tone={s.status === "applied" ? "success" : "info"}>{SCENARIO_STATUS_LABEL[s.status]}</Badge>
                        </td>
                        <td className="num">{s.duration ?? "—"}</td>
                        <td className="num">{fmtPct(s.variation_pct, 1, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              ) : (
                <EmptyState title="Sin escenarios" icon={<ListChecks size={26} aria-hidden />}>
                  Después de confirmar la línea base podés simular alternativas de equipo.
                </EmptyState>
              )}
            </Card>
          </div>
          {v?.total_cost !== null && v?.total_cost !== undefined && (
            <p className="subtle">
              Coste por horas asignadas de la versión activa: {fmtMoney(v.total_cost, project.currency)}. Cuello de botella: {names[v.main_bottleneck ?? ""] ?? "—"}.
            </p>
          )}
        </div>
      )}
    </>
  );
}
