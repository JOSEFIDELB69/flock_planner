"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { fmtDate, fmtHours, fmtMoney, fmtNum, fmtPct } from "@/lib/format";
import type { Forecast, PlanMetrics, ScheduledTask, TeamProfile } from "@/lib/types";

import { ForecastChart, HoursBarChart } from "./charts";
import { Gantt } from "./Gantt";
import { Badge, Card, Progress, Stat, Tabs } from "./ui";

const pct = (p: number) => `${Math.round(p * 100)} %`;

/** Probabilidad de cumplimiento: resultado de la simulación Monte Carlo sobre el mismo motor. */
function ForecastCard({ f, metrics }: { f: Forecast; metrics: PlanMetrics }) {
  const tone = f.probability_plan >= 0.8 ? "success" : f.probability_plan >= 0.5 ? "warning" : "danger";
  const marks = [{ days: metrics.duration_working_days, label: "Plan" }, { days: f.p80.working_days, label: "P80" }];
  return (
    <Card title="Probabilidad de cumplimiento" sub={`Simulación Monte Carlo: ${f.runs} escenarios del mismo plan, variando las horas de cada tarea dentro de su rango optimista–pesimista.`}>
      <div className="grid kpis forecast-kpis">
        <Stat label="Cumplir la fecha del plan" value={pct(f.probability_plan)} hint={`${fmtDate(metrics.completion_date)}${metrics.contingency_days ? ` (incluye ${metrics.contingency_days} días de reserva)` : ""}`} />
        <Stat label="50 % de confianza (P50)" value={fmtDate(f.p50.date)} hint={`${f.p50.working_days} días laborables de trabajo`} />
        <Stat label="80 % de confianza (P80)" value={fmtDate(f.p80.date)} hint={`${f.p80.working_days} días · recomendado para comprometer`} />
        <Stat label="90 % de confianza (P90)" value={fmtDate(f.p90.date)} hint={`${f.p90.working_days} días laborables de trabajo`} />
      </div>
      <div className={`alert ${tone} mt`} role="status">
        <div>
          {f.probability_plan >= 0.8
            ? `La fecha del plan tiene buen respaldo: se cumple en el ${pct(f.probability_plan)} de los escenarios.`
            : `La fecha del plan se cumple solo en el ${pct(f.probability_plan)} de los escenarios. Para comprometer con 80 % de confianza, usá una reserva por imprevistos de al menos ${f.contingency_for_p80_pct} % o comprometé el ${fmtDate(f.p80.date)}.`}
          {f.probability_target !== null && metrics.target_date && ` Fecha objetivo (${fmtDate(metrics.target_date)}): ${pct(f.probability_target)} de probabilidad.`}
        </div>
      </div>
      <ForecastChart data={f.curve} marks={marks} />
      <p className="subtle small">
        Esfuerzo base simulado: {fmtNum(f.base_hours_range[0])} h (optimista) · {fmtNum(f.base_hours_range[1])} h (estimado) · {fmtNum(f.base_hours_range[2])} h (pesimista). {f.tasks_with_own_range} tareas tienen rango propio; el resto usa el de la confianza de su historia (alta {f.uncertainty.high[0]}/+{f.uncertainty.high[1]} %, media {f.uncertainty.medium[0]}/+{f.uncertainty.medium[1]} %, baja {f.uncertainty.low[0]}/+{f.uncertainty.low[1]} %). Semilla fija: los mismos datos dan el mismo resultado.
      </p>
    </Card>
  );
}

const CONSTRAINT = { dependency: "Dependencia", resource: "Recurso ocupado", start: "Inicio del plan" };

export function PlanView({ metrics, schedule, team, currency }: { metrics: PlanMetrics; schedule: ScheduledTask[]; team: TeamProfile[]; currency: string }) {
  const [mode, setMode] = useState<"story" | "member" | "epic">("story");
  const critical = new Set(metrics.critical_path.map((c) => c.task_id));
  const profileOrder = team.map((p) => p.profile_key);
  const qaKeys = new Set(team.filter((p) => p.is_qa).map((p) => p.profile_key));
  const names = Object.fromEntries(team.map((p) => [p.profile_key, p.profile_name]));

  return (
    <div className="stack">
      <div className="grid kpis">
        <Stat
          brand
          label="Duración estimada"
          value={`${metrics.duration_working_days} días`}
          hint={
            metrics.contingency_days
              ? `${metrics.work_duration_days} de trabajo + ${metrics.contingency_days} de reserva por imprevistos (${fmtNum(metrics.contingency_pct ?? 0)} %)`
              : `${metrics.calendar_days} días corridos`
          }
        />
        <Stat label="Inicio → fin estimado" value={fmtDate(metrics.completion_date)} hint={`Desde ${fmtDate(metrics.start_date)}${metrics.target_date ? ` · objetivo ${fmtDate(metrics.target_date)}` : ""}`} />
        <Stat label="Esfuerzo planificado" value={fmtHours(metrics.planned_effort_hours)} hint={`${fmtNum(metrics.base_effort_hours)} h base + revisión y retrabajo`} />
        <Stat label="Cuello de botella principal" value={metrics.main_bottleneck ? names[metrics.main_bottleneck] ?? metrics.main_bottleneck : "—"} hint={metrics.bottlenecks[0]?.reasons.join("; ")} />
        {metrics.total_cost !== null && <Stat label="Coste por horas asignadas" value={fmtMoney(metrics.total_cost, currency)} hint={metrics.total_staffing_cost !== null ? `Coste de equipo durante el plan: ${fmtMoney(metrics.total_staffing_cost, currency)}` : undefined} />}
      </div>
      {metrics.meets_target === false && (
        <div className="alert danger" role="status">
          <AlertTriangle size={18} aria-hidden />
          <div>La fecha estimada ({fmtDate(metrics.completion_date)}) supera la fecha objetivo ({fmtDate(metrics.target_date)}). Probá alternativas en Optimización de escenarios.</div>
        </div>
      )}

      {metrics.forecast && <ForecastCard f={metrics.forecast} metrics={metrics} />}

      <Card title="Cronograma" sub="Calculado por el motor respetando dependencias, capacidad y calendario. Contorno oscuro = camino crítico.">
        <Tabs
          tabs={[
            { key: "story", label: "Por historia" },
            { key: "member", label: "Por persona" },
            { key: "epic", label: "Por épica" },
          ]}
          value={mode}
          onChange={setMode}
        />
        <Gantt schedule={schedule} startDate={metrics.start_date} criticalIds={critical} profileOrder={profileOrder} qaKeys={qaKeys} mode={mode} milestones={metrics.milestones} />
        <div className="legend">
          {team
            .filter((p) => metrics.by_profile.find((b) => b.profile_key === p.profile_key && b.planned_hours > 0))
            .map((p, i) => (
              <span key={p.profile_key}>
                <i style={{ background: p.is_qa ? "var(--chart-3)" : i === 1 ? "var(--chart-2)" : i === 3 ? "var(--chart-4)" : i > 3 ? "var(--chart-other)" : "var(--chart-1)" }} />
                {p.profile_name}
              </span>
            ))}
          <span>
            <i style={{ background: "transparent", boxShadow: "0 0 0 2px var(--ink)" }} />
            Camino crítico
          </span>
          <span>
            <i style={{ background: "var(--accent)", transform: "rotate(45deg)" }} />
            Hito
          </span>
        </div>
      </Card>

      <div className="grid c2">
        <Card title="Capacidad y utilización por perfil" sub="Horas asignadas sobre horas disponibles entre el inicio y el fin">
          <div className="table-wrap">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Perfil</th>
                  <th className="num">Personas</th>
                  <th className="num">Cap./día</th>
                  <th className="num">Planif.</th>
                  <th className="num">Disp.</th>
                  <th>Utilización</th>
                  <th className="num">Espera media</th>
                </tr>
              </thead>
              <tbody>
                {metrics.by_profile.map((p) => (
                  <tr key={p.profile_key}>
                    <td>{p.profile_name}</td>
                    <td className="num">{p.members}</td>
                    <td className="num">{fmtNum(p.daily_capacity)} h</td>
                    <td className="num">{fmtNum(p.planned_hours)}</td>
                    <td className="num">{fmtNum(p.available_hours)}</td>
                    <td style={{ minWidth: 120 }}>
                      <div className="small">{fmtPct(p.utilization * 100)}</div>
                      <Progress value={p.utilization} label={`Utilización ${p.profile_name}`} />
                    </td>
                    <td className="num">{p.avg_wait_days ? `${fmtNum(p.avg_wait_days)} d` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle mt">Espera media: días que las tareas del perfil esperan, ya listas, a que se libere una persona (por ejemplo, pruebas esperando a QA).</p>
        </Card>
        <Card title="Horas planificadas por perfil">
          <HoursBarChart data={metrics.by_profile.filter((p) => p.planned_hours > 0).map((p) => ({ name: p.profile_name, value: p.planned_hours }))} />
        </Card>
      </div>

      <div className="grid c2">
        <Card title="Camino crítico" sub="Aproximación con restricciones de recursos: cadena de tareas que determina la fecha de fin">
          <ol className="list-plain">
            {metrics.critical_path.map((c) => (
              <li key={c.task_id}>
                <div className="row between">
                  <strong>{c.title}</strong>
                  <Badge tone={c.constraint === "resource" ? "warning" : "info"}>{CONSTRAINT[c.constraint]}</Badge>
                </div>
                <div className="subtle">
                  {names[c.profile_key] ?? c.profile_key} · {c.member_name} · {fmtDate(c.start_date)} → {fmtDate(c.end_date)} · {fmtNum(c.effective_hours)} h
                </div>
              </li>
            ))}
          </ol>
        </Card>
        <div className="stack">
          <Card title="Hitos">
            <ul className="list-plain">
              {metrics.milestones.map((m) => (
                <li key={m.name} className="row between">
                  <span>{m.name}</span>
                  <strong>{fmtDate(m.date)}</strong>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Cuellos de botella">
            <ul className="list-plain">
              {metrics.bottlenecks.map((b) => (
                <li key={b.profile_key}>
                  <div className="row between">
                    <strong>{b.profile_name}</strong>
                    <span className="subtle">
                      {fmtPct(b.critical_share * 100)} del camino crítico · utilización {fmtPct(b.utilization * 100)}
                    </span>
                  </div>
                  {b.reasons.length > 0 && <div className="subtle">{b.reasons.join("; ")}</div>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <div className="grid c2">
        <Card title="Supuestos de planificación">
          <ul className="ac-list" style={{ color: "var(--ink)" }}>
            {metrics.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Card>
        <Card title="Riesgos e incertidumbre">
          {metrics.risks.length === 0 ? (
            <p className="muted">El motor no detectó riesgos relevantes.</p>
          ) : (
            <ul className="list-plain">
              {metrics.risks.map((r) => (
                <li key={r.title}>
                  <strong>{r.title}</strong> <Badge tone={r.severity === "high" ? "danger" : "warning"}>{r.severity === "high" ? "Alta" : "Media"}</Badge>
                  <div className="subtle">{r.detail}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
