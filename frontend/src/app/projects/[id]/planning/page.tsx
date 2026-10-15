"use client";

import { Calculator, RefreshCw, ShieldCheck, SlidersHorizontal, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PlanView } from "@/components/PlanView";
import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, Loading, PageHeader, SimulatedNotice, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { DEFAULT_SENIORITY_FACTORS, SeniorityFactorsFields } from "@/components/SeniorityFactors";
import { DEFAULT_UNCERTAINTY, UncertaintyFields } from "@/components/UncertaintyFields";
import type { PlanPreview, PlanVersion, PlanVersionSummary, SeniorityMix, Uncertainty } from "@/lib/types";

type Params = { start_date: string; review_overhead_pct: number; rework_pct: number; coordination_overhead_pct: number; qa_after_dev: boolean; contingency_pct: number; seniority_factors: SeniorityMix; uncertainty: Uncertainty };

function nextWorkingDay(days: number[]): string {
  const d = new Date();
  for (let i = 0; i < 14; i++) {
    const wd = (d.getDay() + 6) % 7;
    if (days.includes(wd)) break;
    d.setDate(d.getDate() + 1);
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function PlanningPage() {
  const { project, reload: reloadProject, system } = useProject();
  const toast = useToast();
  const versions = useApi<PlanVersionSummary[]>(`/projects/${project.id}/plans`);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const viewId = selectedId ?? project.active_plan_version_id;
  const version = useApi<PlanVersion>(viewId ? `/plans/${viewId}` : null);
  const [params, setParams] = useState<Params>({
    start_date: nextWorkingDay(project.calendar_configuration.working_days),
    review_overhead_pct: 10,
    rework_pct: 10,
    coordination_overhead_pct: 5,
    qa_after_dev: true,
    contingency_pct: 0,
    seniority_factors: DEFAULT_SENIORITY_FACTORS,
    uncertainty: DEFAULT_UNCERTAINTY,
  });
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | "baseline" | "recalc">(null);
  const [reason, setReason] = useState("");
  const [showParams, setShowParams] = useState(false);
  const hasBaseline = project.has_baseline;

  useEffect(() => {
    if (version.data && !preview) {
      const p = version.data.planning_parameters;
      setParams({ start_date: p.start_date, review_overhead_pct: p.review_overhead_pct, rework_pct: p.rework_pct, coordination_overhead_pct: p.coordination_overhead_pct, qa_after_dev: p.qa_after_dev, contingency_pct: p.contingency_pct ?? 0, seniority_factors: { ...DEFAULT_SENIORITY_FACTORS, ...(p.seniority_factors ?? {}) }, uncertainty: { ...DEFAULT_UNCERTAINTY, ...(p.uncertainty ?? {}) } });
    }
  }, [version.data, preview]);

  const runPreview = async () => {
    setBusy("preview");
    try {
      setPreview(await api<PlanPreview>(`/projects/${project.id}/plans/generate`, { body: { confirm: false, parameters: params } }));
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const confirmPlan = async () => {
    setBusy("confirm");
    try {
      const v = await api<PlanVersion>(`/projects/${project.id}/plans/generate`, { body: { confirm: true, parameters: params, change_reason: reason } });
      toast("success", v.is_baseline ? "Línea base guardada. Ya podés optimizar el equipo y la duración." : `Versión v${v.version_number} guardada como plan activo.`);
      setPreview(null);
      setConfirm(null);
      setReason("");
      setSelectedId(null);
      await Promise.all([reloadProject(), versions.reload()]);
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const recalc = async () => {
    if (!viewId) return;
    setBusy("recalc");
    try {
      const v = await api<PlanVersion>(`/plans/${viewId}/recalculate`, { body: { change_reason: reason || "Recalculo con el backlog y el equipo actuales", use_current_team: true } });
      toast("success", `Se creó la versión v${v.version_number}. La versión anterior se conserva.`);
      setConfirm(null);
      setReason("");
      setSelectedId(null);
      await Promise.all([reloadProject(), versions.reload()]);
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const summary = async () => {
    if (!viewId) return;
    setBusy("summary");
    try {
      await api(`/plans/${viewId}/summary`, { method: "POST" });
      toast("success", "Resumen ejecutivo generado a partir de las métricas del motor.");
      await version.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const paramForm = (
    <div className="form-grid">
      <Field label="Inicio de la planificación">{(id) => <input id={id} type="date" className="input" value={params.start_date} onChange={(e) => setParams({ ...params, start_date: e.target.value })} />}</Field>
      <Field label="Revisión de código (%)" help="Se suma a las tareas que no son de QA.">
        {(id) => <input id={id} type="number" min={0} max={200} className="input" value={params.review_overhead_pct} onChange={(e) => setParams({ ...params, review_overhead_pct: Number(e.target.value) })} />}
      </Field>
      <Field label="Retrabajo (%)" help="Correcciones tras QA, sobre tareas que no son de QA.">
        {(id) => <input id={id} type="number" min={0} max={200} className="input" value={params.rework_pct} onChange={(e) => setParams({ ...params, rework_pct: Number(e.target.value) })} />}
      </Field>
      <Field label="Coordinación por persona adicional (%)" help="Pérdida de eficiencia por persona extra en un mismo perfil.">
        {(id) => <input id={id} type="number" min={0} max={50} className="input" value={params.coordination_overhead_pct} onChange={(e) => setParams({ ...params, coordination_overhead_pct: Number(e.target.value) })} />}
      </Field>
      <Field label="Reserva por imprevistos (%)" help="Reserva de tiempo al final del plan: % de la duración, en días laborables. No cambia horas ni tareas.">
        {(id) => <input id={id} type="number" min={0} max={100} className="input" value={params.contingency_pct} onChange={(e) => setParams({ ...params, contingency_pct: Math.max(0, Math.min(100, Number(e.target.value))) })} />}
      </Field>
      <SeniorityFactorsFields value={params.seniority_factors} onChange={(v) => setParams({ ...params, seniority_factors: v })} />
      <UncertaintyFields value={params.uncertainty} onChange={(v) => setParams({ ...params, uncertainty: v })} />
      <label className="checkbox full">
        <input type="checkbox" checked={params.qa_after_dev} onChange={(e) => setParams({ ...params, qa_after_dev: e.target.checked })} />
        QA de cada historia después de su desarrollo
      </label>
      <p className="subtle full">
        Calendario: días laborables y feriados del proyecto ({project.calendar_configuration.holidays.length} feriados). Se editan en <Link href={`/projects/${project.id}/settings`}>Configuración del proyecto</Link>.
      </p>
    </div>
  );

  return (
    <>
      <PageHeader
        title="Planificación"
        description="El motor determinista calcula la duración calendario: no divide horas por personas, sino que asigna tareas respetando dependencias, capacidad y calendario."
        actions={
          hasBaseline ? (
            <>
              <Button variant="secondary" icon={<Calculator size={18} />} onClick={() => setShowParams((v) => !v)}>
                Nueva vista previa
              </Button>
              <Button variant="secondary" icon={<RefreshCw size={18} />} onClick={() => setConfirm("recalc")} disabled={!viewId}>
                Recalcular con datos actuales
              </Button>
              <Link className="btn" href={`/projects/${project.id}/optimization`}>
                <SlidersHorizontal size={18} aria-hidden /> Optimizar planificación y duración
              </Link>
            </>
          ) : undefined
        }
      />

      {(!hasBaseline || showParams || preview) && (
        <Card title={hasBaseline ? "Vista previa con otros parámetros" : "Planificación inicial"} sub={hasBaseline ? "Si la confirmás se guarda como versión nueva; la línea base no cambia." : "Calculá la vista previa, revisala y confirmala: la primera planificación confirmada queda como línea base inmutable."} className="pad-lg">
          {project.story_count === 0 ? (
            <EmptyState title="No hay backlog para planificar" action={<Link className="btn" href={`/projects/${project.id}/stories`}>Ir a Épicas e historias</Link>} />
          ) : (
            <>
              {paramForm}
              <div className="row mt">
                <Button icon={<Calculator size={18} />} onClick={runPreview} loading={busy === "preview"}>
                  Calcular vista previa
                </Button>
                {preview && (
                  <Button variant="brand" icon={<ShieldCheck size={18} />} onClick={() => setConfirm("baseline")}>
                    {hasBaseline ? "Guardar como nueva versión" : "Confirmar como línea base"}
                  </Button>
                )}
              </div>
            </>
          )}
        </Card>
      )}

      {preview && (
        <div className="stack mt">
          <Alert tone="warning" title="Vista previa: estimación preliminar, todavía no guardada">
            Revisá el resultado. Nada se guarda hasta que confirmes.
          </Alert>
          <PlanView metrics={preview.result} schedule={preview.result.schedule} team={preview.team_configuration} currency={project.currency} />
        </div>
      )}

      {!preview && hasBaseline && (
        <div className="stack mt">
          {versions.data && versions.data.length > 1 && (
            <div className="row">
              <label htmlFor="ver" className="muted">
                Versión
              </label>
              <select id="ver" className="select" style={{ width: 360 }} value={viewId ?? ""} onChange={(e) => setSelectedId(Number(e.target.value))}>
                {versions.data.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} · {v.label}
                    {v.is_baseline ? " (línea base)" : ""}
                    {v.is_active ? " (activa)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
          {version.loading && !version.data && <Loading />}
          {version.error && <ErrorState message={version.error} onRetry={version.reload} />}
          {version.data && (
            <>
              <Card>
                <div className="row between">
                  <div className="row">
                    <h3>
                      v{version.data.version_number} · {version.data.label}
                    </h3>
                    {version.data.is_baseline && <Badge tone="primary">Línea base · inmutable</Badge>}
                    {version.data.is_active && <Badge tone="success">Plan activo confirmado</Badge>}
                  </div>
                  <span className="subtle">
                    {fmtDateTime(version.data.created_at)} · {version.data.created_by} · inicio {fmtDate(version.data.start_date)}
                  </span>
                </div>
                {version.data.change_reason && <p className="muted mt">Motivo: {version.data.change_reason}</p>}
                <hr className="divider" />
                <div className="row between">
                  <h4>Resumen ejecutivo</h4>
                  <Button size="sm" variant="secondary" icon={<Sparkles size={16} />} onClick={summary} loading={busy === "summary"} disabled={!system?.ai_available}>
                    {version.data.executive_summary ? "Regenerar con IA" : "Redactar con IA"}
                  </Button>
                </div>
                {version.data.executive_summary ? (
                  <>
                    {version.data.executive_summary_simulated && <SimulatedNotice what="El resumen" />}
                    <p className="mt" style={{ whiteSpace: "pre-line" }}>
                      {version.data.executive_summary}
                    </p>
                    <p className="subtle">Redactado a partir de las métricas calculadas; la IA no modifica fechas ni cifras.</p>
                  </>
                ) : (
                  <p className="muted mt">Sin resumen. Podés redactarlo con IA o exportar el PDF, que incluye un resumen calculado.</p>
                )}
              </Card>
              <PlanView metrics={version.data.metrics} schedule={version.data.schedule} team={version.data.team_configuration} currency={project.currency} />
            </>
          )}
        </div>
      )}

      {confirm === "baseline" && preview && (
        <ConfirmDialog title={hasBaseline ? "Guardar nueva versión" : "Confirmar línea base"} confirmLabel={hasBaseline ? "Guardar versión" : "Confirmar línea base"} loading={busy === "confirm"} onCancel={() => setConfirm(null)} onConfirm={confirmPlan}>
          <p>
            {hasBaseline
              ? "Se creará una versión nueva que pasará a ser el plan activo. La línea base y las versiones anteriores se conservan."
              : "Esta primera planificación quedará guardada como línea base inmutable: servirá de referencia para comparar escenarios y versiones."}
          </p>
          <p>
            Duración: <strong>{preview.result.duration_working_days} días laborables</strong> · fin <strong>{fmtDate(preview.result.completion_date)}</strong>.
          </p>
          <Field label="Motivo o comentario (opcional)">{(id) => <input id={id} className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} />}</Field>
        </ConfirmDialog>
      )}
      {confirm === "recalc" && (
        <ConfirmDialog title="Recalcular plan" confirmLabel="Crear versión recalculada" loading={busy === "recalc"} onCancel={() => setConfirm(null)} onConfirm={recalc}>
          <p>Se creará una versión nueva con el backlog y el equipo actuales y los parámetros de la versión seleccionada. Ninguna versión existente se modifica.</p>
          <Field label="Motivo del cambio">{(id) => <input id={id} className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} />}</Field>
        </ConfirmDialog>
      )}
    </>
  );
}
