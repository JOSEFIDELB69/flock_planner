"use client";

import { CheckCheck, ChevronDown, ChevronRight } from "lucide-react";
import Link from "next/link";
import { Fragment, useState } from "react";

import { HoursBarChart } from "@/components/charts";
import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Loading, PageHeader, SimulatedNotice, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CONFIDENCE_LABEL, CONFIDENCE_TONE, fmtHours, fmtNum, fmtPct, toggled } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Backlog, Confidence, Task, TeamProfile } from "@/lib/types";

// rangos por defecto según la confianza de la historia (los mismos que usa el motor si la tarea no tiene rango propio)
const DEFAULT_RANGE: Record<Confidence, [number, number]> = { high: [-10, 25], medium: [-15, 50], low: [-25, 100] };
type Edit = { o: string; m: string; p: string };
const editOf = (t: Task): Edit => ({ o: t.optimistic_hours === null ? "" : String(t.optimistic_hours), m: String(t.estimated_hours), p: t.pessimistic_hours === null ? "" : String(t.pessimistic_hours) });
const sameEdit = (a: Edit, b: Edit) => a.o === b.o && Number(a.m) === Number(b.m) && a.p === b.p;

export default function EstimatesPage() {
  const { project } = useProject();
  const toast = useToast();
  const backlog = useApi<Backlog>(`/projects/${project.id}/backlog`);
  const team = useApi<TeamProfile[]>(`/projects/${project.id}/team`);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [edits, setEdits] = useState<Record<number, Edit>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);

  const profiles = (team.data ?? []).map((p) => p.profile_key);
  const names = Object.fromEntries((team.data ?? []).map((p) => [p.profile_key, p.profile_name]));
  const b = backlog.data;
  const stories = (b?.epics ?? []).flatMap((e) => e.stories.map((s) => ({ ...s, epicCode: e.code })));
  const extraProfiles = Object.keys(b?.hours_by_profile ?? {}).filter((k) => !profiles.includes(k));
  const cols = [...profiles, ...extraProfiles];
  const lowHours = stories.filter((s) => s.estimate_confidence === "low").reduce((x, s) => x + s.total_hours, 0);
  const revised = stories.filter((s) => s.estimate_status === "revised").length;

  const saveHours = async (taskId: number) => {
    const e = edits[taskId];
    if (!e) return;
    const v = Number(e.m);
    if (e.m === "" || !(v >= 0)) {
      toast("warning", "Ingresá un número de horas válido (0 o más).");
      return;
    }
    if ((e.o === "") !== (e.p === "")) {
      toast("warning", "Completá las dos horas del rango (optimista y pesimista) o dejá ambas vacías.");
      return;
    }
    const o = e.o === "" ? null : Number(e.o);
    const p = e.p === "" ? null : Number(e.p);
    if (o !== null && p !== null && !(o <= v && v <= p && p > o)) {
      toast("warning", "El rango debe cumplir: optimista ≤ estimado ≤ pesimista.");
      return;
    }
    setSaving(taskId);
    try {
      await api(`/tasks/${taskId}`, { method: "PATCH", body: { estimated_hours: v, optimistic_hours: o, pessimistic_hours: p } });
      setEdits((e) => {
        const n = { ...e };
        delete n[taskId];
        return n;
      });
      await backlog.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setSaving(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Estimaciones"
        description="Esfuerzo en horas por perfil, subtarea, historia y épica. La IA propone y vos ajustás: los cambios manuales marcan la estimación como revisada."
        actions={
          <>
            <Button variant="secondary" icon={<CheckCheck size={18} />} onClick={() => setConfirming(true)} disabled={!stories.length}>
              Marcar todo como revisado
            </Button>
            <Link className="btn" href={`/projects/${project.id}/planning`}>
              Continuar a Planificación
            </Link>
          </>
        }
      />
      {backlog.loading && !b && <Loading />}
      {backlog.error && <ErrorState message={backlog.error} onRetry={backlog.reload} />}
      {b && stories.length === 0 && (
        <Card>
          <EmptyState title="No hay estimaciones" action={<Link className="btn" href={`/projects/${project.id}/stories`}>Ir a Épicas e historias</Link>}>
            Primero generá o cargá el backlog.
          </EmptyState>
        </Card>
      )}
      {b && stories.length > 0 && (
        <div className="stack">
          {b.is_simulated && <SimulatedNotice what="Las horas estimadas" />}
          <Alert tone="info" title="Esfuerzo no es duración">
            Estas horas son esfuerzo de trabajo. La duración calendario la calcula el motor de planificación con la capacidad del equipo, las dependencias y el calendario laboral (más un {`10 %`} de revisión y un {`10 %`} de retrabajo por defecto en tareas que no son de QA).
          </Alert>
          <div className="grid kpis">
            <Card>
              <div className="stat">
                <span className="label">Esfuerzo base total</span>
                <span className="value">{fmtHours(b.total_hours)}</span>
                <span className="hint">Suma consistente de subtareas → historias → épicas</span>
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="label">Historias revisadas</span>
                <span className="value">
                  {revised} / {stories.length}
                </span>
                <span className="hint">El resto conserva la estimación inicial</span>
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="label">Horas con confianza baja</span>
                <span className="value">{fmtHours(lowHours)}</span>
                <span className="hint">{fmtPct(b.total_hours ? (lowHours / b.total_hours) * 100 : 0)} del esfuerzo · mayor incertidumbre</span>
              </div>
            </Card>
          </div>
          <div className="grid c2">
            <Card title="Horas por perfil">
              <HoursBarChart data={cols.filter((k) => b.hours_by_profile[k]).map((k) => ({ name: names[k] ?? k, value: b.hours_by_profile[k] }))} />
              {extraProfiles.length > 0 && <Alert tone="warning">Hay tareas con perfiles fuera del equipo: {extraProfiles.join(", ")}. Agregalos en Equipo y capacidad.</Alert>}
            </Card>
            <Card title="Horas por épica">
              <HoursBarChart data={b.epics.map((e) => ({ name: `${e.code} ${e.title}`, value: e.total_hours }))} />
            </Card>
          </div>
          <Card title="Detalle por historia" sub="Expandí una historia para ajustar las horas de sus subtareas">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Historia</th>
                    {cols.map((k) => (
                      <th key={k} className="num">
                        {names[k] ?? k}
                      </th>
                    ))}
                    <th className="num">Total</th>
                    <th>Confianza</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {stories.map((s) => (
                    <Fragment key={s.id}>
                      <tr className="clickable" onClick={() => setOpen((o) => toggled(o, s.id))}>
                        <td>
                          <button className="disclosure" aria-expanded={open.has(s.id)} aria-label={open.has(s.id) ? `Contraer ${s.code}` : `Expandir ${s.code}`}>
                            {open.has(s.id) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          </button>{" "}
                          <span className="mono">{s.code}</span> {s.title}
                          {s.assumptions && <div className="subtle">Supuestos: {s.assumptions}</div>}
                        </td>
                        {cols.map((k) => (
                          <td key={k} className="num">
                            {s.hours_by_profile[k] ? fmtNum(s.hours_by_profile[k]) : "—"}
                          </td>
                        ))}
                        <td className="num">
                          <strong>{fmtNum(s.total_hours)}</strong>
                        </td>
                        <td>
                          <Badge tone={CONFIDENCE_TONE[s.estimate_confidence]}>{CONFIDENCE_LABEL[s.estimate_confidence]}</Badge>
                        </td>
                        <td>
                          <Badge tone={s.estimate_status === "revised" ? "success" : ""}>{s.estimate_status === "revised" ? "Revisada" : "Inicial"}</Badge>
                        </td>
                      </tr>
                      {open.has(s.id) &&
                        s.tasks.map((t) => (
                          <tr key={`t${t.id}`}>
                            <td style={{ paddingLeft: 50 }}>
                              <span className="mono">{t.code}</span> {t.title} <span className="subtle">· {names[t.profile_key] ?? t.profile_key}</span>
                              {t.risks && <div className="subtle">Riesgo: {t.risks}</div>}
                            </td>
                            <td colSpan={cols.length}>
                              {(() => {
                                const cur = edits[t.id] ?? editOf(t);
                                const [lo, hi] = DEFAULT_RANGE[s.estimate_confidence];
                                const auto = (pctv: number) => fmtNum(Math.max(0, (Number(cur.m) || 0) * (1 + pctv / 100)));
                                const setField = (k: keyof Edit, v: string) => setEdits((x) => ({ ...x, [t.id]: { ...(x[t.id] ?? editOf(t)), [k]: v } }));
                                const field = (k: keyof Edit, label: string, placeholder?: string) => (
                                  <label className="range-field">
                                    <span>{label}</span>
                                    <input className="input sm" type="number" min={0} step={0.5} aria-label={`${label} de ${t.code}`} placeholder={placeholder} value={cur[k]} onChange={(e) => setField(k, e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveHours(t.id)} />
                                  </label>
                                );
                                return (
                                  <div className="row range-edit" style={{ justifyContent: "flex-end" }}>
                                    {field("o", "Optimista", `auto ${auto(lo)}`)}
                                    {field("m", "Estimado")}
                                    {field("p", "Pesimista", `auto ${auto(hi)}`)}
                                    <Button size="sm" variant="secondary" disabled={!edits[t.id] || sameEdit(edits[t.id], editOf(t))} loading={saving === t.id} onClick={() => saveHours(t.id)}>
                                      Guardar
                                    </Button>
                                  </div>
                                );
                              })()}
                            </td>
                            <td className="num subtle">{t.estimate_status === "revised" ? `inicial ${fmtNum(t.original_estimate_hours)}` : ""}</td>
                            <td colSpan={2} />
                          </tr>
                        ))}
                    </Fragment>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td>Total</td>
                    {cols.map((k) => (
                      <td key={k} className="num">
                        {fmtNum(b.hours_by_profile[k] ?? 0)}
                      </td>
                    ))}
                    <td className="num">{fmtNum(b.total_hours)}</td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        </div>
      )}
      {confirming && (
        <ConfirmDialog
          title="Marcar estimaciones como revisadas"
          confirmLabel="Marcar como revisadas"
          onCancel={() => setConfirming(false)}
          onConfirm={async () => {
            try {
              await api(`/projects/${project.id}/estimates/confirm`, { method: "POST" });
              toast("success", "Todas las estimaciones quedaron como revisadas.");
              setConfirming(false);
              await backlog.reload();
            } catch (e) {
              toast("danger", errorMessage(e));
            }
          }}
        >
          <p>Confirmás que revisaste las horas de todas las historias. Esto distingue en informes las estimaciones iniciales (de la IA) de las revisadas por el equipo.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
