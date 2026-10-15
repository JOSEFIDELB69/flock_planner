"use client";

import { Download, FileText } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useProject } from "@/components/ProjectContext";
import { Alert, Button, Card, EmptyState, ErrorState, Loading, PageHeader, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, fmtNum } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ExportItem, PlanVersionSummary } from "@/lib/types";

const TYPES = [
  { key: "full", title: "Informe completo", desc: "Portada, resumen, alcance, requisitos, épicas, historias, criterios de aceptación, subtareas, estimaciones, equipo, supuestos, dependencias, cronograma, riesgos y versión." },
  { key: "executive", title: "Informe ejecutivo", desc: "Objetivo, alcance, duración, esfuerzo, equipo, hitos, riesgos principales y supuestos." },
  { key: "optimization", title: "Informe de optimización", desc: "Línea base, escenarios comparados, cambios de capacidad, plazos, costes, cuellos de botella, recomendación y escenario aplicado." },
] as const;

export default function ReportsPage() {
  const { project } = useProject();
  const toast = useToast();
  const versions = useApi<PlanVersionSummary[]>(`/projects/${project.id}/plans`);
  const exports = useApi<ExportItem[]>(`/projects/${project.id}/exports`);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    if (versions.data && versionId === null) setVersionId(versions.data.find((v) => v.is_active)?.id ?? versions.data[0]?.id ?? null);
  }, [versions.data, versionId]);
  const vnum = Object.fromEntries((versions.data ?? []).map((v) => [v.id, v.version_number]));

  const download = (e: ExportItem) => {
    const a = document.createElement("a");
    a.href = `/api/v1/exports/${e.id}`;
    a.download = e.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const generate = async (type: string) => {
    if (!versionId) return;
    setBusy(type);
    try {
      const e = await api<ExportItem>(`/plans/${versionId}/exports/pdf`, { body: { report_type: type } });
      toast("success", `PDF generado: ${e.filename} (${fmtNum(e.size_bytes / 1024, 0)} KB).`);
      download(e);
      await exports.reload();
    } catch (err) {
      toast("danger", `No pudimos generar el PDF. ${errorMessage(err)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader title="Informes y exportaciones" description="PDF generados en el servidor con los datos guardados de la versión elegida. No se necesita JIRA." />
      {versions.loading && !versions.data && <Loading />}
      {versions.error && <ErrorState message={versions.error} onRetry={versions.reload} />}
      {versions.data && versions.data.length === 0 && (
        <Card>
          <EmptyState title="Todavía no hay versiones del plan" action={<Link className="btn" href={`/projects/${project.id}/planning`}>Ir a Planificación</Link>}>
            Los informes se generan a partir de una versión confirmada del plan.
          </EmptyState>
        </Card>
      )}
      {versions.data && versions.data.length > 0 && (
        <div className="stack">
          <Card>
            <div className="row">
              <label htmlFor="ver" className="muted">
                Versión del plan para el informe
              </label>
              <select id="ver" className="select" style={{ width: 380 }} value={versionId ?? ""} onChange={(e) => setVersionId(Number(e.target.value))}>
                {versions.data.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number} · {v.label}
                    {v.is_baseline ? " (línea base)" : ""}
                    {v.is_active ? " (activa)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </Card>
          <div className="grid c3">
            {TYPES.map((t) => (
              <Card key={t.key} title={t.title}>
                <p className="muted">{t.desc}</p>
                <Button icon={<FileText size={18} />} onClick={() => generate(t.key)} loading={busy === t.key} disabled={!versionId}>
                  Generar y descargar PDF
                </Button>
              </Card>
            ))}
          </div>
          <Alert tone="info">Las estimaciones del informe son proyecciones calculadas con los supuestos documentados, no garantías.</Alert>
          <Card title="Historial de exportaciones">
            {exports.loading && !exports.data && <Loading />}
            {exports.data && exports.data.length === 0 && <p className="muted">Todavía no generaste informes.</p>}
            {exports.data && exports.data.length > 0 && (
              <div className="table-wrap">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>Archivo</th>
                      <th>Tipo</th>
                      <th>Versión</th>
                      <th className="num">Tamaño</th>
                      <th>Generado</th>
                      <th>
                        <span className="sr-only">Descargar</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {exports.data.map((e) => (
                      <tr key={e.id}>
                        <td className="mono">{e.filename}</td>
                        <td>{TYPES.find((t) => t.key === e.report_type)?.title}</td>
                        <td>v{vnum[e.plan_version_id] ?? "?"}</td>
                        <td className="num">{fmtNum(e.size_bytes / 1024, 0)} KB</td>
                        <td>
                          {fmtDateTime(e.created_at)} <span className="subtle">· {e.created_by}</span>
                        </td>
                        <td>
                          <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => download(e)}>
                            Descargar
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
