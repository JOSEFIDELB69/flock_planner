"use client";

import { GitCompare, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { TrendChart } from "@/components/charts";
import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, Loading, Modal, PageHeader, Tabs, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtHours, fmtMoney, fmtPct, signedDays } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AuditEntry, ComparisonMetrics, PlanVersionSummary } from "@/lib/types";

type Cmp = { from_version: { version_number: number; label: string }; to_version: { version_number: number; label: string }; metrics: ComparisonMetrics };

const ENTITY: Record<string, string> = {
  project: "Proyecto",
  requirement: "Requisito",
  analysis: "Análisis IA",
  backlog: "Backlog",
  epic: "Épica",
  story: "Historia",
  task: "Subtarea",
  team: "Equipo",
  plan_version: "Versión de plan",
  scenario: "Escenario",
  export: "Exportación",
  integration: "Integración",
  jira_publish: "Publicación JIRA",
  estimates: "Estimaciones",
};

export default function VersionsPage() {
  const { project, reload: reloadProject } = useProject();
  const toast = useToast();
  const versions = useApi<PlanVersionSummary[]>(`/projects/${project.id}/plans`);
  const audit = useApi<AuditEntry[]>(`/projects/${project.id}/audit?limit=200`);
  const [tab, setTab] = useState<"versions" | "audit">("versions");
  const [cmp, setCmp] = useState<Cmp | null>(null);
  const [restore, setRestore] = useState<{ v: PlanVersionSummary; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [entity, setEntity] = useState("");
  const list = versions.data ?? [];
  const activeId = list.find((v) => v.is_active)?.id;

  const compare = async (v: PlanVersionSummary) => {
    if (!activeId) return;
    try {
      setCmp(await api<Cmp>(`/plans/${v.id}/compare/${activeId}`));
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  const doRestore = async () => {
    if (!restore) return;
    setBusy(true);
    try {
      const v = await api<{ version_number: number }>(`/plans/${restore.v.id}/restore`, { body: { change_reason: restore.reason } });
      toast("success", `Se creó la versión v${v.version_number} con el contenido de v${restore.v.version_number}. No se borró historial.`);
      setRestore(null);
      await Promise.all([versions.reload(), audit.reload(), reloadProject()]);
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const auditRows = (audit.data ?? []).filter((a) => !entity || a.entity_type === entity);

  return (
    <>
      <PageHeader title="Versiones e historial" description="Cada confirmación o escenario aplicado crea una versión nueva. La línea base es inmutable; restaurar crea una versión nueva en lugar de borrar historial." />
      <Tabs
        tabs={[
          { key: "versions", label: `Versiones del plan (${list.length})` },
          { key: "audit", label: "Auditoría de cambios" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "versions" && (
        <div className="stack">
          {versions.loading && !versions.data && <Loading />}
          {versions.error && <ErrorState message={versions.error} onRetry={versions.reload} />}
          {versions.data && list.length === 0 && (
            <Card>
              <EmptyState title="Sin versiones" action={<Link className="btn" href={`/projects/${project.id}/planning`}>Ir a Planificación</Link>}>
                Confirmá la planificación inicial para crear la línea base.
              </EmptyState>
            </Card>
          )}
          {list.length > 1 && (
            <Card title="Evolución de la duración estimada">
              <TrendChart data={[...list].reverse().map((v) => ({ name: `v${v.version_number}`, value: v.estimated_duration }))} />
            </Card>
          )}
          {list.length > 0 && (
            <Card>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Versión</th>
                      <th>Estado</th>
                      <th className="num">Duración</th>
                      <th>Fin estimado</th>
                      <th className="num">Esfuerzo</th>
                      <th className="num">Coste</th>
                      <th>Creada</th>
                      <th>Motivo</th>
                      <th>
                        <span className="sr-only">Acciones</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((v) => (
                      <tr key={v.id} className={v.is_active ? "selected" : ""}>
                        <td>
                          <strong>v{v.version_number}</strong> <span className="subtle">{v.label}</span>
                        </td>
                        <td>
                          {v.is_baseline && <Badge tone="primary">Línea base</Badge>} {v.is_active && <Badge tone="success">Activa</Badge>} {v.source_scenario_id && <Badge>Desde escenario</Badge>}
                        </td>
                        <td className="num">{v.estimated_duration} días</td>
                        <td>{fmtDate(v.estimated_completion_date)}</td>
                        <td className="num">{fmtHours(v.estimated_effort)}</td>
                        <td className="num">{fmtMoney(v.total_cost, project.currency)}</td>
                        <td>
                          {fmtDateTime(v.created_at)}
                          <div className="subtle">{v.created_by}</div>
                        </td>
                        <td className="subtle" style={{ maxWidth: 260 }}>
                          {v.change_reason || "—"}
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {!v.is_active && (
                            <>
                              <Button size="sm" variant="ghost" icon={<GitCompare size={14} />} onClick={() => compare(v)}>
                                Comparar con activa
                              </Button>
                              <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => setRestore({ v, reason: "" })}>
                                Restaurar
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
      {tab === "audit" && (
        <Card>
          <div className="toolbar">
            <select className="select" style={{ width: 220 }} value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="Filtrar por entidad">
              <option value="">Todas las entidades</option>
              {Object.entries(ENTITY).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <span className="subtle">Los secretos nunca se registran.</span>
          </div>
          {audit.loading && !audit.data && <Loading />}
          {audit.error && <ErrorState message={audit.error} onRetry={audit.reload} />}
          {auditRows.length === 0 && audit.data && <EmptyState title="Sin registros" />}
          {auditRows.length > 0 && (
            <div className="table-wrap">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Usuario</th>
                    <th>Entidad</th>
                    <th>Acción</th>
                    <th>Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {auditRows.map((a) => (
                    <tr key={a.id}>
                      <td style={{ whiteSpace: "nowrap" }}>{fmtDateTime(a.created_at)}</td>
                      <td>{a.actor}</td>
                      <td>
                        {ENTITY[a.entity_type] ?? a.entity_type} {a.entity_id && <span className="subtle">#{a.entity_id}</span>}
                      </td>
                      <td>{a.action}</td>
                      <td className="subtle" style={{ maxWidth: 420, wordBreak: "break-word" }}>
                        {a.reason && <div>Motivo: {a.reason}</div>}
                        {a.after && JSON.stringify(a.after).slice(0, 220)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {cmp && (
        <Modal title={`v${cmp.from_version.version_number} frente a la versión activa v${cmp.to_version.version_number}`} onClose={() => setCmp(null)}>
          <dl className="kv">
            <dt>Duración</dt>
            <dd>
              {cmp.metrics.baseline_duration} → {cmp.metrics.scenario_duration} días ({fmtPct(cmp.metrics.variation_pct, 1, true)}, {signedDays(cmp.metrics.time_savings_days)})
            </dd>
            <dt>Fin estimado</dt>
            <dd>
              {fmtDate(cmp.metrics.baseline_completion_date)} → {fmtDate(cmp.metrics.scenario_completion_date)}
            </dd>
            <dt>Esfuerzo</dt>
            <dd>
              {fmtHours(cmp.metrics.baseline_effort)} → {fmtHours(cmp.metrics.scenario_effort)}
            </dd>
            <dt>Equipo</dt>
            <dd>
              {cmp.metrics.capacity_changes.filter((c) => c.quantity_delta).map((c) => `${c.profile_name}: ${c.baseline_quantity} → ${c.scenario_quantity}`).join(" · ") || "Sin cambios de cantidad"}
            </dd>
          </dl>
        </Modal>
      )}
      {restore && (
        <ConfirmDialog title={`Restaurar v${restore.v.version_number}`} confirmLabel="Crear versión restaurada" loading={busy} onCancel={() => setRestore(null)} onConfirm={doRestore}>
          <Alert tone="info">Se creará una versión nueva con el backlog, el equipo y los parámetros de v{restore.v.version_number}, que pasará a ser el plan activo. No se elimina ninguna versión.</Alert>
          <Field label="Motivo" className="mt">
            {(id) => <input id={id} className="input" value={restore.reason} onChange={(e) => setRestore({ ...restore, reason: e.target.value })} maxLength={2000} />}
          </Field>
        </ConfirmDialog>
      )}
    </>
  );
}
