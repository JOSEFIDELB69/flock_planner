"use client";

import { CalendarClock, Clock, FolderKanban, Plus, Sparkles } from "lucide-react";
import Link from "next/link";

import { HoursBarChart } from "@/components/charts";
import { Alert, Badge, Card, EmptyState, ErrorState, Loading, PageHeader, Stat } from "@/components/ui";
import { fmtDate, fmtHours, fmtNum, PROJECT_STATUS_LABEL } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Project, SystemStatus } from "@/lib/types";

type Dash = { active_projects: number; draft_projects: number; total_projects: number; total_hours: number; projects: Project[] };

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi<Dash>("/dashboard");
  const { data: system } = useApi<SystemStatus>("/system/status");

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Estado de los proyectos con datos persistidos. Entrá a un proyecto para ver su planificación detallada."
        actions={
          <Link className="btn" href="/projects/new">
            <Plus size={18} aria-hidden /> Nuevo proyecto
          </Link>
        }
      />
      {system && !system.ai_available && (
        <div style={{ marginBottom: 20 }}>
          <Alert tone="info" title="IA no configurada">
            Podés usar Flock Planner completo de forma manual (requisitos, backlog, planificación, escenarios y PDF). Para el análisis y la generación con IA, el backend necesita la CLI de Claude Code con una sesión iniciada.
          </Alert>
        </div>
      )}
      {system?.ai_provider === "demo" && (
        <div style={{ marginBottom: 20 }}>
          <Alert tone="warning" title="Modo demostración activo">
            Las funciones de IA devuelven resultados simulados con heurísticas locales y se marcan como tales.
          </Alert>
        </div>
      )}
      {loading && !data && <Loading />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {data && (
        <div className="stack">
          <div className="grid kpis">
            <Stat brand label="Proyectos activos" value={data.active_projects} icon={<FolderKanban size={16} aria-hidden />} hint={`${data.draft_projects} en borrador`} />
            <Stat label="Proyectos totales" value={data.total_projects} icon={<FolderKanban size={16} aria-hidden />} />
            <Stat label="Esfuerzo estimado (backlog)" value={fmtHours(data.total_hours)} icon={<Clock size={16} aria-hidden />} hint="Suma de horas base de todas las tareas" />
            <Stat
              label="Próxima entrega estimada"
              value={fmtDate(data.projects.map((p) => p.estimated_completion_date).filter(Boolean).sort()[0] ?? null)}
              icon={<CalendarClock size={16} aria-hidden />}
              hint="Según la versión activa de cada proyecto"
            />
          </div>
          {data.projects.length === 0 ? (
            <Card>
              <EmptyState
                title="Todavía no hay proyectos"
                icon={<Sparkles size={26} aria-hidden />}
                action={
                  <Link className="btn" href="/projects/new">
                    Crear el primer proyecto
                  </Link>
                }
              >
                Creá un proyecto, cargá requisitos y Flock Planner te ayuda a convertirlos en un plan estimado y calendarizado.
              </EmptyState>
            </Card>
          ) : (
            <div className="grid c8-4">
              <Card title="Proyectos" sub="Ordenados por última modificación">
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Proyecto</th>
                        <th>Estado</th>
                        <th className="num">Historias</th>
                        <th className="num">Horas</th>
                        <th className="num">Duración</th>
                        <th>Fin estimado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.projects.map((p) => (
                        <tr key={p.id}>
                          <td>
                            <Link href={`/projects/${p.id}`}>{p.name}</Link>
                            <div className="subtle">{p.owner || "Sin responsable"}</div>
                          </td>
                          <td>
                            <Badge tone={p.status === "active" ? "success" : ""}>{PROJECT_STATUS_LABEL[p.status]}</Badge>{" "}
                            {p.has_baseline ? <Badge tone="primary">v{p.active_version_number}</Badge> : <Badge>Sin plan</Badge>}
                          </td>
                          <td className="num">{p.story_count}</td>
                          <td className="num">{fmtNum(p.total_hours)}</td>
                          <td className="num">{p.estimated_duration ? `${p.estimated_duration} días` : "—"}</td>
                          <td>{fmtDate(p.estimated_completion_date)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
              <Card title="Horas por proyecto" sub="Esfuerzo base del backlog">
                <HoursBarChart data={data.projects.filter((p) => p.total_hours > 0).map((p) => ({ name: p.name, value: p.total_hours }))} />
              </Card>
            </div>
          )}
        </div>
      )}
    </>
  );
}
