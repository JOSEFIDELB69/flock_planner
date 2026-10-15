"use client";

import { Eye, Lightbulb, Play, Plus, RefreshCw, Sparkles, Trash2, Wand2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { HoursBarChart } from "@/components/charts";
import { useProject } from "@/components/ProjectContext";
import { cleanTeam, TeamEditor } from "@/components/TeamEditor";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, IconButton, Loading, Modal, PageHeader, Progress, SimulatedNotice, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtHours, fmtMoney, fmtNum, fmtPct, SCENARIO_STATUS_LABEL, signedDays } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { DEFAULT_SENIORITY_FACTORS, SeniorityFactorsFields } from "@/components/SeniorityFactors";
import type { ComparisonMetrics, PlanVersion, Scenario, SeniorityMix, TeamProfile } from "@/lib/types";

type Explanation = { explanation: string; recommended_scenario: string; rationale: string; caveats: string[]; is_simulated: boolean };

/** Mismo criterio que el backend: menor duración, menor coste de equipo, menos personas agregadas, nombre. */
function recommendationKey(s: Scenario): [number, number, number, string] {
  const m = s.comparison_metrics!;
  return [m.scenario_duration, m.staffing_cost_delta ?? 0, m.added_people ?? 0, s.name];
}

function compareKeys(a: [number, number, number, string], b: [number, number, number, string]) {
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return (a[i] as number) - (b[i] as number);
  return a[3].localeCompare(b[3]);
}

function gapSummary(m: ComparisonMetrics): string | null {
  const pct = m.scenario_contingency_pct ?? 0;
  if (!pct && !(m.baseline_contingency_pct ?? 0)) return null;
  return pct ? `Reserva por imprevistos ${fmtNum(pct)} % (+${m.scenario_contingency_days ?? 0} días)` : "Sin reserva por imprevistos";
}

function capacitySummary(m: ComparisonMetrics) {
  const changes = m.capacity_changes.filter((c) => c.quantity_delta || c.daily_capacity_delta);
  const parts = changes.map((c) => (c.quantity_delta ? `${c.quantity_delta > 0 ? "+" : ""}${c.quantity_delta} ${c.profile_name}` : `${c.profile_name} ${c.daily_capacity_delta > 0 ? "+" : ""}${fmtNum(c.daily_capacity_delta)} h/día`));
  const gap = gapSummary(m);
  if (gap) parts.push(gap);
  return parts.length ? parts.join(" · ") : "Sin cambios de capacidad";
}

export default function OptimizationPage() {
  const { project, reload: reloadProject, system } = useProject();
  const toast = useToast();
  const scenarios = useApi<Scenario[]>(`/projects/${project.id}/scenarios`);
  const active = useApi<PlanVersion>(project.active_plan_version_id ? `/plans/${project.active_plan_version_id}` : null);
  const versions = useApi<{ id: number; version_number: number; is_baseline: boolean; estimated_duration: number; estimated_completion_date: string }[]>(`/projects/${project.id}/plans`);
  const baseline = versions.data?.find((v) => v.is_baseline);
  const [builder, setBuilder] = useState<{ name: string; description: string; team: TeamProfile[]; start_date: string; coordination: number; qa_after_dev: boolean; gap: number; seniority: SeniorityMix; editingId?: number } | null>(null);
  const [detail, setDetail] = useState<Scenario | null>(null);
  const [applying, setApplying] = useState<{ s: Scenario; reason: string } | null>(null);
  const [deleting, setDeleting] = useState<Scenario | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [quickGap, setQuickGap] = useState(10);

  const list = scenarios.data ?? [];
  const simulated = list.filter((s) => s.comparison_metrics);
  const best = useMemo(() => [...simulated].sort((a, b) => compareKeys(recommendationKey(a), recommendationKey(b)))[0], [simulated]);
  const noGain = Array.from(new Set(simulated.flatMap((s) => s.comparison_metrics?.profiles_without_gain ?? [])));
  const names = Object.fromEntries((active.data?.team_configuration ?? []).map((p) => [p.profile_key, p.profile_name]));

  const refresh = async () => {
    await Promise.all([scenarios.reload(), reloadProject(), versions.reload(), active.reload()]);
  };

  const openBuilder = (from?: Scenario) => {
    const team = from?.team_configuration ?? active.data?.team_configuration ?? [];
    const params = from?.planning_parameters ?? active.data?.planning_parameters;
    setBuilder({
      name: from ? `${from.name} (copia)` : `Escenario ${String.fromCharCode(65 + list.length)}`,
      description: from?.description ?? "",
      team: JSON.parse(JSON.stringify(team)),
      start_date: params?.start_date ?? "",
      coordination: params?.coordination_overhead_pct ?? 5,
      gap: params?.contingency_pct ?? 0,
      qa_after_dev: params?.qa_after_dev ?? true,
      seniority: { ...DEFAULT_SENIORITY_FACTORS, ...(params?.seniority_factors ?? {}) },
    });
  };

  const saveScenario = async () => {
    if (!builder) return;
    if (!builder.name.trim()) {
      toast("warning", "Ingresá un nombre para el escenario.");
      return;
    }
    setBusy("create");
    try {
      const s = await api<Scenario>(`/projects/${project.id}/scenarios`, {
        body: {
          name: builder.name,
          description: builder.description,
          team_configuration: cleanTeam(builder.team),
          planning_parameters: { start_date: builder.start_date || null, coordination_overhead_pct: builder.coordination, qa_after_dev: builder.qa_after_dev, contingency_pct: builder.gap, seniority_factors: builder.seniority },
          simulate: true,
        },
      });
      if (s.status === "error") toast("warning", `Escenario guardado, pero la simulación falló: ${s.error_message}`);
      else toast("success", `Simulación lista: ${s.estimated_duration} días laborables. La línea base no se modificó.`);
      setBuilder(null);
      await scenarios.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const simulateGap = async () => {
    if (!active.data) return;
    setBusy("gap");
    try {
      const p = active.data.planning_parameters;
      const s = await api<Scenario>(`/projects/${project.id}/scenarios`, {
        body: {
          name: `Plan activo + reserva ${quickGap} %`,
          description: `Equipo y parámetros de la versión v${active.data.version_number} con ${quickGap} % de reserva por imprevistos.`,
          team_configuration: cleanTeam(active.data.team_configuration),
          planning_parameters: { start_date: p.start_date, review_overhead_pct: p.review_overhead_pct, rework_pct: p.rework_pct, coordination_overhead_pct: p.coordination_overhead_pct, qa_after_dev: p.qa_after_dev, contingency_pct: quickGap },
          simulate: true,
        },
      });
      const m = s.comparison_metrics;
      toast("success", m ? `Simulación lista: ${m.scenario_duration} días laborables (${m.scenario_contingency_days ?? 0} de reserva). La línea base no se modificó.` : "Escenario creado.");
      await scenarios.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const suggest = async () => {
    setBusy("suggest");
    try {
      const created = await api<Scenario[]>(`/projects/${project.id}/scenarios/suggest`, { body: {} });
      toast(created.length ? "success" : "info", created.length ? `Se simularon ${created.length} escenarios sugeridos.` : "Los escenarios sugeridos ya estaban creados para esta versión.");
      await scenarios.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const resimulate = async (s: Scenario) => {
    setBusy(`sim${s.id}`);
    try {
      await api(`/scenarios/${s.id}/simulate`, { method: "POST" });
      await scenarios.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!applying) return;
    setBusy("apply");
    try {
      const r = await api<{ version: PlanVersion }>(`/scenarios/${applying.s.id}/apply`, { body: { confirm: true, change_reason: applying.reason } });
      toast("success", `Escenario aplicado: se creó la versión v${r.version.version_number} como plan activo. La línea base se conserva.`);
      setApplying(null);
      await refresh();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const explain = async () => {
    setBusy("explain");
    try {
      setExplanation(await api<Explanation>(`/projects/${project.id}/scenarios/explain`, { body: { scenario_ids: [] } }));
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (!project.has_baseline) {
    return (
      <>
        <PageHeader title="Optimización de escenarios" />
        <Card>
          <EmptyState title="Primero confirmá la línea base" action={<Link className="btn" href={`/projects/${project.id}/planning`}>Ir a Planificación</Link>}>
            Los escenarios se simulan sobre una copia de la configuración y se comparan siempre contra la línea base.
          </EmptyState>
        </Card>
      </>
    );
  }

  const chartData = [
    ...(baseline ? [{ name: `Línea base v${baseline.version_number}`, dias: baseline.estimated_duration }] : []),
    ...simulated.map((s) => ({ name: s.name.length > 22 ? `${s.name.slice(0, 21)}…` : s.name, dias: s.comparison_metrics!.scenario_duration })),
  ];

  return (
    <>
      <PageHeader
        title="Optimizar planificación y duración"
        description={
          baseline
            ? `Simulá cambios de equipo y capacidad sin tocar la línea base. Todas las diferencias se comparan con la línea base v${baseline.version_number} (${baseline.estimated_duration} días laborables, fin ${fmtDate(baseline.estimated_completion_date)}).`
            : "Simulá cambios de equipo y capacidad sin tocar la línea base."
        }
        actions={
          <>
            <Button variant="secondary" icon={<Wand2 size={18} />} onClick={suggest} loading={busy === "suggest"}>
              Sugerir escenarios
            </Button>
            <Button variant="secondary" icon={<Sparkles size={18} />} onClick={explain} loading={busy === "explain"} disabled={!simulated.length || !system?.ai_available}>
              Explicar con IA
            </Button>
            <Button icon={<Plus size={18} />} onClick={() => openBuilder()} disabled={!active.data}>
              Nuevo escenario
            </Button>
          </>
        }
      />
      {scenarios.loading && !scenarios.data && <Loading />}
      {scenarios.error && <ErrorState message={scenarios.error} onRetry={scenarios.reload} />}
      <div className="stack">
        <Alert tone="info">
          Sumar personas no reduce el plazo en la misma proporción: las dependencias, la granularidad de las tareas y la coordinación limitan la paralelización. Todas las cifras salen del motor de planificación; la IA solo explica.
        </Alert>
        <Card title="Reserva por imprevistos" sub="Reserva de tiempo que se suma al final del plan: % de la duración del trabajo, en días laborables. No cambia horas ni tareas.">
          <div className="row" style={{ alignItems: "flex-end" }}>
            <Field label="Reserva (%)">
              {(id) => <input id={id} type="number" min={0} max={100} step={1} className="input" style={{ width: 120 }} value={quickGap} onChange={(e) => setQuickGap(Math.max(0, Math.min(100, Number(e.target.value))))} />}
            </Field>
            <Button icon={<Play size={16} />} onClick={simulateGap} loading={busy === "gap"} disabled={!active.data || quickGap <= 0}>
              Simular plan activo con reserva
            </Button>
            <span className="subtle">También podés combinar la reserva con cambios de equipo en «Nuevo escenario».</span>
          </div>
          {(active.data?.metrics.contingency_days ?? 0) > 0 && (
            <p className="subtle mt">
              El plan activo ya incluye una reserva del {fmtNum(active.data!.metrics.contingency_pct ?? 0)} % ({active.data!.metrics.contingency_days} días).
            </p>
          )}
        </Card>
        {scenarios.data && list.length === 0 && (
          <Card>
            <EmptyState title="Todavía no hay escenarios" icon={<Lightbulb size={26} aria-hidden />} action={<div className="row"><Button onClick={suggest} loading={busy === "suggest"}>Sugerir escenarios</Button><Button variant="secondary" onClick={() => openBuilder()}>Crear escenario manual</Button></div>}>
              Probá, por ejemplo, un desarrollador Backend adicional, más capacidad de QA o mayor dedicación del equipo actual.
            </EmptyState>
          </Card>
        )}
        {simulated.length > 0 && (
          <>
            <Card title="Comparación de escenarios" sub={baseline ? `Diferencias respecto de la línea base v${baseline.version_number}` : undefined}>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Escenario</th>
                      <th>Estado</th>
                      <th className="num">Días</th>
                      <th className="num">Ahorro</th>
                      <th className="num">Variación</th>
                      <th>Fin</th>
                      <th className="num">Coste equipo</th>
                      <th>Cuello de botella</th>
                      <th>
                        <span className="sr-only">Acciones</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((s) => {
                      const m = s.comparison_metrics;
                      return (
                        <tr key={s.id} className={best?.id === s.id ? "selected" : ""}>
                          <td style={{ minWidth: 230 }}>
                            <strong>{s.name}</strong> {best?.id === s.id && <Badge tone="outline">Recomendado</Badge>}
                            {(!m || capacitySummary(m) !== s.name) && <div className="subtle">{m ? capacitySummary(m) : s.status === "error" ? s.error_message : "Sin simular"}</div>}
                          </td>
                          <td>
                            <Badge tone={s.status === "applied" ? "success" : s.status === "error" ? "danger" : "info"}>{SCENARIO_STATUS_LABEL[s.status]}</Badge>
                            {s.source === "suggested" && <div className="subtle">Sugerido</div>}
                          </td>
                          <td className="num">{m?.scenario_duration ?? "—"}</td>
                          <td className="num">{m ? signedDays(m.time_savings_days) : "—"}</td>
                          <td className="num">{m ? fmtPct(m.variation_pct, 1, true) : "—"}</td>
                          <td>{fmtDate(m?.scenario_completion_date)}</td>
                          <td className="num">
                            {m?.scenario_staffing_cost != null ? fmtMoney(m.scenario_staffing_cost, project.currency) : "—"}
                            {m?.staffing_cost_delta != null && m.staffing_cost_delta !== 0 && <div className="subtle">{m.staffing_cost_delta > 0 ? "+" : ""}{fmtNum(m.staffing_cost_delta, 0)}</div>}
                          </td>
                          <td>{m?.scenario_main_bottleneck ? names[m.scenario_main_bottleneck] ?? m.scenario_main_bottleneck : "—"}</td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            {m && (
                              <IconButton label={`Ver detalle de ${s.name}`} onClick={() => setDetail(s)}>
                                <Eye size={16} />
                              </IconButton>
                            )}
                            {s.status !== "applied" && (
                              <IconButton label={`Volver a simular ${s.name}`} onClick={() => resimulate(s)} disabled={busy === `sim${s.id}`}>
                                <RefreshCw size={16} />
                              </IconButton>
                            )}
                            <IconButton label={`Duplicar ${s.name}`} onClick={() => openBuilder(s)}>
                              <Plus size={16} />
                            </IconButton>
                            {s.status === "simulated" && (
                              <IconButton label={`Aplicar ${s.name}`} onClick={() => setApplying({ s, reason: "" })}>
                                <Play size={16} />
                              </IconButton>
                            )}
                            {s.status !== "applied" && (
                              <IconButton label={`Eliminar ${s.name}`} onClick={() => setDeleting(s)}>
                                <Trash2 size={16} />
                              </IconButton>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="subtle mt">
                Variación = (duración del escenario − duración de la línea base) / duración de la línea base × 100. Ahorro = línea base − escenario. Coste de equipo = horas pagadas durante el plan × tarifa (configurá tarifas en Equipo).
              </p>
            </Card>
            <div className="grid c2">
              <Card title="Duración por escenario" sub="Días laborables (incluye la línea base)">
                <HoursBarChart data={chartData.map((d) => ({ name: d.name, value: d.dias }))} unit="días" height={Math.max(160, chartData.length * 42)} />
              </Card>
              {best && (
                <Card title="Recomendación del motor">
                  <p>
                    <strong>{best.name}</strong>: {best.comparison_metrics!.scenario_duration} días laborables ({signedDays(best.comparison_metrics!.time_savings_days)} frente a la línea base).
                  </p>
                  <p className="subtle">Criterio: menor duración; con empate, menor coste de equipo y menos personas agregadas. Considerá además los riesgos y la disponibilidad real.</p>
                </Card>
              )}
            </div>
          </>
        )}

        {active.data && (
          <div className="grid c2">
            <Card title="Análisis de cuellos de botella" sub={`Plan activo v${active.data.version_number}`}>
              <ul className="list-plain">
                {active.data.metrics.bottlenecks.map((b) => (
                  <li key={b.profile_key}>
                    <div className="row between">
                      <strong>{b.profile_name}</strong>
                      <span className="small">{fmtPct(b.utilization * 100)} de utilización</span>
                    </div>
                    <Progress value={b.utilization} label={`Utilización ${b.profile_name}`} />
                    {b.reasons.length > 0 && <div className="subtle">{b.reasons.join("; ")}</div>}
                  </li>
                ))}
              </ul>
              {active.data.metrics.by_profile.some((p) => p.is_qa && p.avg_wait_days >= 1) && <Alert tone="warning">Hay esperas entre desarrollo y pruebas: las tareas de QA esperan en promedio más de un día.</Alert>}
              {noGain.length > 0 && (
                <Alert tone="info" title="Perfiles que no mejoran el plazo">
                  Sumar una persona en {noGain.map((k) => names[k] ?? k).join(", ")} no reduce la duración: el límite está en otro perfil o en las dependencias.
                </Alert>
              )}
            </Card>
            <Card title="Tareas con alta incertidumbre" sub="Historias con confianza baja en la estimación">
              {active.data.metrics.risks.filter((r) => r.title.includes("confianza") || r.title.includes("Concentración")).length ? (
                <ul className="list-plain">
                  {active.data.metrics.risks
                    .filter((r) => r.title.includes("confianza") || r.title.includes("Concentración"))
                    .map((r) => (
                      <li key={r.title}>
                        <strong>{r.title}</strong>
                        <div className="subtle">{r.detail}</div>
                      </li>
                    ))}
                </ul>
              ) : (
                <p className="muted">No hay concentraciones de conocimiento ni estimaciones de confianza baja relevantes.</p>
              )}
            </Card>
          </div>
        )}

        {explanation && (
          <Card title="Explicación de los escenarios" sub={explanation.is_simulated ? "Simulada (modo demostración)" : "Redactada por IA a partir de las métricas del motor"}>
            {explanation.is_simulated && <SimulatedNotice what="La explicación" />}
            <p style={{ whiteSpace: "pre-line" }} className="mt">
              {explanation.explanation}
            </p>
            {explanation.recommended_scenario && (
              <p>
                <strong>Escenario recomendado por la IA:</strong> {explanation.recommended_scenario}. {explanation.rationale}
              </p>
            )}
            {explanation.caveats.length > 0 && (
              <ul className="ac-list">
                {explanation.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>

      {builder && (
        <Modal
          title={builder.editingId ? "Editar escenario" : "Nuevo escenario (simulación)"}
          onClose={() => setBuilder(null)}
          wide
          footer={
            <>
              <Button variant="secondary" onClick={() => setBuilder(null)}>
                Cancelar
              </Button>
              <Button onClick={saveScenario} loading={busy === "create"} icon={<Play size={16} />}>
                Simular escenario
              </Button>
            </>
          }
        >
          <Alert tone="info">Los cambios se aplican sobre una copia de la configuración. La línea base y el plan activo no se modifican.</Alert>
          <div className="form-grid mt">
            <Field label="Nombre" required>{(id) => <input id={id} className="input" value={builder.name} onChange={(e) => setBuilder({ ...builder, name: e.target.value })} maxLength={200} />}</Field>
            <Field label="Fecha de inicio">{(id) => <input id={id} type="date" className="input" value={builder.start_date} onChange={(e) => setBuilder({ ...builder, start_date: e.target.value })} />}</Field>
            <Field label="Descripción" className="full">{(id) => <input id={id} className="input" value={builder.description} onChange={(e) => setBuilder({ ...builder, description: e.target.value })} />}</Field>
            <Field label="Coordinación por persona adicional (%)" help="Supuesto de paralelización: cuánto se pierde de eficiencia al sumar gente a un perfil.">
              {(id) => <input id={id} type="number" min={0} max={50} className="input" value={builder.coordination} onChange={(e) => setBuilder({ ...builder, coordination: Number(e.target.value) })} />}
            </Field>
            <Field label="Reserva por imprevistos (%)" help="Reserva de tiempo que se suma al final: % de la duración del trabajo, redondeado hacia arriba en días laborables. No cambia horas ni tareas.">
              {(id) => <input id={id} type="number" min={0} max={100} step={1} className="input" value={builder.gap} onChange={(e) => setBuilder({ ...builder, gap: Math.max(0, Math.min(100, Number(e.target.value))) })} />}
            </Field>
            <SeniorityFactorsFields value={builder.seniority} onChange={(v) => setBuilder({ ...builder, seniority: v })} />
            <label className="checkbox" style={{ alignSelf: "end" }}>
              <input type="checkbox" checked={builder.qa_after_dev} onChange={(e) => setBuilder({ ...builder, qa_after_dev: e.target.checked })} /> QA después del desarrollo de cada historia
            </label>
          </div>
          <h4 className="mt" style={{ marginBottom: 10 }}>
            Equipo del escenario
          </h4>
          <TeamEditor team={builder.team} onChange={(team) => setBuilder({ ...builder, team })} />
        </Modal>
      )}

      {detail && detail.comparison_metrics && detail.results && (
        <Modal title={`Detalle: ${detail.name}`} onClose={() => setDetail(null)} wide>
          <div className="row" style={{ marginBottom: 10 }}>
            <Badge tone={detail.status === "applied" ? "success" : "info"}>{detail.status === "applied" ? "Aplicado al plan" : "Simulación (no aplicada)"}</Badge>
            <span className="subtle">Comparado con la línea base v{detail.comparison_metrics.baseline_version_number}</span>
          </div>
          <dl className="kv">
            <dt>Duración</dt>
            <dd>
              {detail.comparison_metrics.baseline_duration} → <strong>{detail.comparison_metrics.scenario_duration} días</strong> ({fmtPct(detail.comparison_metrics.variation_pct, 1, true)})
            </dd>
            <dt>Fin estimado</dt>
            <dd>
              {fmtDate(detail.comparison_metrics.baseline_completion_date)} → <strong>{fmtDate(detail.comparison_metrics.scenario_completion_date)}</strong>
            </dd>
            <dt>Horas totales</dt>
            <dd>
              {fmtHours(detail.comparison_metrics.baseline_effort)} → {fmtHours(detail.comparison_metrics.scenario_effort)}
            </dd>
            <dt>Coste por horas</dt>
            <dd>
              {fmtMoney(detail.comparison_metrics.baseline_cost, project.currency)} → {fmtMoney(detail.comparison_metrics.scenario_cost, project.currency)}
            </dd>
            <dt>Coste de equipo</dt>
            <dd>
              {fmtMoney(detail.comparison_metrics.baseline_staffing_cost, project.currency)} → {fmtMoney(detail.comparison_metrics.scenario_staffing_cost, project.currency)}
            </dd>
            <dt>Capacidad</dt>
            <dd>{capacitySummary(detail.comparison_metrics)}</dd>
            <dt>Reserva por imprevistos</dt>
            <dd>
              {fmtNum(detail.comparison_metrics.baseline_contingency_pct ?? 0)} % → {fmtNum(detail.comparison_metrics.scenario_contingency_pct ?? 0)} %
              {(detail.comparison_metrics.scenario_contingency_days ?? 0) > 0 && ` (${detail.comparison_metrics.scenario_work_duration} días de trabajo + ${detail.comparison_metrics.scenario_contingency_days} de reserva)`}
            </dd>
            {detail.comparison_metrics.scenario_p80 && (
              <>
                <dt>Fecha con 80 % de confianza (P80)</dt>
                <dd>
                  {detail.comparison_metrics.baseline_p80 ? fmtDate(detail.comparison_metrics.baseline_p80.date) : "— (línea base sin pronóstico)"} → {fmtDate(detail.comparison_metrics.scenario_p80.date)} ({detail.comparison_metrics.scenario_p80.working_days} días de trabajo)
                </dd>
                <dt>Probabilidad de cumplir su fecha</dt>
                <dd>
                  {detail.comparison_metrics.baseline_probability_plan != null ? `${Math.round(detail.comparison_metrics.baseline_probability_plan * 100)} %` : "—"} → {Math.round((detail.comparison_metrics.scenario_probability_plan ?? 0) * 100)} %
                </dd>
              </>
            )}
          </dl>
          <h4 className="mt" style={{ marginBottom: 8 }}>
            Utilización por perfil
          </h4>
          <div className="table-wrap">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Perfil</th>
                  <th className="num">Personas</th>
                  <th className="num">Capacidad/día</th>
                  <th className="num">Horas</th>
                  <th className="num">Utilización base → escenario</th>
                  <th className="num">Espera QA/media</th>
                </tr>
              </thead>
              <tbody>
                {detail.results.by_profile.map((p) => {
                  const ch = detail.comparison_metrics!.capacity_changes.find((c) => c.profile_key === p.profile_key);
                  return (
                    <tr key={p.profile_key}>
                      <td>{p.profile_name}</td>
                      <td className="num">
                        {ch?.baseline_quantity} → {p.members}
                      </td>
                      <td className="num">{fmtNum(p.daily_capacity)} h</td>
                      <td className="num">{fmtNum(p.planned_hours)}</td>
                      <td className="num">
                        {fmtPct((ch?.baseline_utilization ?? 0) * 100)} → {fmtPct(p.utilization * 100)}
                      </td>
                      <td className="num">{p.avg_wait_days ? `${fmtNum(p.avg_wait_days)} d` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <h4 className="mt" style={{ marginBottom: 8 }}>
            Riesgos y supuestos
          </h4>
          <ul className="ac-list" style={{ color: "var(--ink)" }}>
            {detail.results.risks.map((r) => (
              <li key={r.title}>
                <strong>{r.title}</strong>: {r.detail}
              </li>
            ))}
            {detail.results.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Modal>
      )}

      {applying && applying.s.comparison_metrics && (
        <ConfirmDialog title={`Aplicar «${applying.s.name}»`} confirmLabel="Aplicar escenario" loading={busy === "apply"} onCancel={() => setApplying(null)} onConfirm={apply}>
          <p>Vista previa de los cambios:</p>
          <ul className="ac-list" style={{ color: "var(--ink)" }}>
            <li>{capacitySummary(applying.s.comparison_metrics)}</li>
            <li>
              Duración: {applying.s.comparison_metrics.baseline_duration} → {applying.s.comparison_metrics.scenario_duration} días laborables ({signedDays(applying.s.comparison_metrics.time_savings_days)} frente a la línea base)
            </li>
            <li>Fin estimado: {fmtDate(applying.s.comparison_metrics.scenario_completion_date)}</li>
          </ul>
          <Alert tone="info">
            Se creará una versión nueva como plan activo y el equipo del proyecto pasará a ser el del escenario. La línea base, las versiones anteriores y los demás escenarios se conservan.
          </Alert>
          <Field label="Motivo del cambio" className="mt">
            {(id) => <input id={id} className="input" value={applying.reason} onChange={(e) => setApplying({ ...applying, reason: e.target.value })} placeholder="Por ejemplo: aprobado por el comité para cumplir la fecha objetivo" maxLength={2000} />}
          </Field>
        </ConfirmDialog>
      )}
      {deleting && (
        <ConfirmDialog
          title="Eliminar escenario"
          danger
          confirmLabel="Eliminar escenario"
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            try {
              await api(`/scenarios/${deleting.id}`, { method: "DELETE" });
              setDeleting(null);
              await scenarios.reload();
            } catch (e) {
              toast("danger", errorMessage(e));
            }
          }}
        >
          <p>
            Vas a eliminar la simulación <strong>{deleting.name}</strong>. No afecta a ninguna versión del plan.
          </p>
        </ConfirmDialog>
      )}
    </>
  );
}
