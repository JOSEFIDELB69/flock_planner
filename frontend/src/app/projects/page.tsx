"use client";

import { Plus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, IconButton, Loading, PageHeader, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtNum, PROJECT_STATUS_LABEL, toggled } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Project } from "@/lib/types";

type SortKey = "name" | "updated_at" | "total_hours" | "estimated_completion_date";
type Deleting = { projects: Project[]; text: string };
const LAST_PROJECT_KEY = "pm_agent_last_project";

export default function ProjectsPage() {
  const toast = useToast();
  const [archived, setArchived] = useState(false);
  const { data, error, loading, reload } = useApi<Project[]>(`/projects?include_archived=${archived}`);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "updated_at", dir: -1 });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState<Deleting | null>(null);
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => {
    const list = (data ?? []).filter((p) => (!q || `${p.name} ${p.owner}`.toLowerCase().includes(q.toLowerCase())) && (!status || p.status === status));
    return [...list].sort((a, b) => {
      const va = a[sort.key] ?? "";
      const vb = b[sort.key] ?? "";
      return (va > vb ? 1 : va < vb ? -1 : 0) * sort.dir;
    });
  }, [data, q, status, sort]);

  const visibleSelected = rows.filter((p) => selected.has(p.id));
  const allVisibleSelected = rows.length > 0 && visibleSelected.length === rows.length;
  const toggle = (id: number) => setSelected((s) => toggled(s, id));
  const toggleAll = () => setSelected(allVisibleSelected ? new Set() : new Set(rows.map((p) => p.id)));

  const th = (key: SortKey, label: string, num = false) => (
    <th className={num ? "num" : ""} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : 1 }))}>
        {label} {sort.key === key ? (sort.dir === 1 ? "▲" : "▼") : ""}
      </button>
    </th>
  );

  // una eliminación individual confirma con el nombre del proyecto; varias, con la palabra ELIMINAR
  const single = deleting?.projects.length === 1 ? deleting.projects[0] : null;
  const expected = single ? single.name : "ELIMINAR";
  const confirmOk = !!deleting && (single ? deleting.text.trim() === single.name : deleting.text.trim().toUpperCase() === "ELIMINAR");

  const doDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      const ids = deleting.projects.map((p) => p.id);
      if (single) await api(`/projects/${single.id}?confirm=true`, { method: "DELETE" });
      else await api(`/projects/delete`, { body: { ids, confirm: true, confirmation_text: deleting.text } });
      try {
        if (ids.map(String).includes(localStorage.getItem(LAST_PROJECT_KEY) ?? "")) localStorage.removeItem(LAST_PROJECT_KEY);
      } catch {
        /* sin almacenamiento */
      }
      toast("success", ids.length === 1 ? `Proyecto «${deleting.projects[0].name}» eliminado.` : `Se eliminaron ${ids.length} proyectos.`);
      setSelected(new Set());
      setDeleting(null);
      await reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Proyectos"
        description="Todos los proyectos funcionan en modo autónomo; la integración con JIRA es opcional."
        actions={
          <Link className="btn" href="/projects/new">
            <Plus size={18} aria-hidden /> Nuevo proyecto
          </Link>
        }
      />
      <Card>
        <div className="toolbar">
          <div className="search grow">
            <Search size={16} aria-hidden />
            <input className="input" placeholder="Buscar por nombre o responsable" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar proyectos" />
          </div>
          <select className="select" style={{ width: 180 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtrar por estado">
            <option value="">Todos los estados</option>
            <option value="draft">Borrador</option>
            <option value="active">Activo</option>
            <option value="archived">Archivado</option>
          </select>
          <label className="checkbox">
            <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Incluir archivados
          </label>
          {/* acciones sobre la selección en la misma barra: la tabla no se desplaza al seleccionar */}
          <div className="bulk-actions" role="region" aria-label="Acciones sobre la selección" aria-live="polite">
            {visibleSelected.length > 0 && (
              <>
                <span>{visibleSelected.length} {visibleSelected.length === 1 ? "seleccionado" : "seleccionados"}</span>
                <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                  Quitar selección
                </Button>
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={() => setDeleting({ projects: visibleSelected, text: "" })}>
                  Eliminar seleccionados
                </Button>
              </>
            )}
          </div>
        </div>
        {loading && !data && <Loading />}
        {error && <ErrorState message={error} onRetry={reload} />}
        {data && rows.length === 0 && (
          <EmptyState title={data.length ? "Sin resultados" : "Todavía no hay proyectos"} action={!data.length && <Link className="btn" href="/projects/new">Crear proyecto</Link>}>
            {data.length ? "Probá con otros filtros." : "Creá un proyecto para empezar."}
          </EmptyState>
        )}
        {rows.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input type="checkbox" checked={allVisibleSelected} ref={(el) => { if (el) el.indeterminate = visibleSelected.length > 0 && !allVisibleSelected; }} onChange={toggleAll} aria-label="Seleccionar todos los proyectos visibles" />
                  </th>
                  {th("name", "Proyecto")}
                  <th>Estado</th>
                  <th>Modo</th>
                  <th className="num">Requisitos/Requerimientos</th>
                  <th className="num">Historias</th>
                  {th("total_hours", "Horas", true)}
                  {th("estimated_completion_date", "Fin estimado")}
                  {th("updated_at", "Modificado")}
                  <th>
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className={selected.has(p.id) ? "selected" : ""}>
                    <td>
                      <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} aria-label={`Seleccionar ${p.name}`} />
                    </td>
                    <td>
                      <Link href={`/projects/${p.id}`}>{p.name}</Link>
                      <div className="subtle">{p.owner || "Sin responsable"}</div>
                    </td>
                    <td>
                      <Badge tone={p.status === "active" ? "success" : ""}>{PROJECT_STATUS_LABEL[p.status]}</Badge>
                    </td>
                    <td>{p.mode === "jira" ? "Integrado" : "Autónomo"}</td>
                    <td className="num">{p.requirement_count}</td>
                    <td className="num">{p.story_count}</td>
                    <td className="num">{fmtNum(p.total_hours)}</td>
                    <td>{fmtDate(p.estimated_completion_date)}</td>
                    <td>{fmtDate(p.updated_at)}</td>
                    <td>
                      <IconButton label={`Eliminar ${p.name}`} onClick={() => setDeleting({ projects: [p], text: "" })}>
                        <Trash2 size={16} />
                      </IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {deleting && (
        <ConfirmDialog
          title={single ? "Eliminar proyecto" : `Eliminar ${deleting.projects.length} proyectos`}
          danger
          confirmLabel={single ? "Eliminar definitivamente" : `Eliminar ${deleting.projects.length} proyectos`}
          confirmDisabled={!confirmOk}
          loading={busy}
          onCancel={() => setDeleting(null)}
          onConfirm={doDelete}
        >
          <Alert tone="danger">
            Se eliminarán requisitos, backlog, versiones del plan, escenarios y exportaciones. No se puede deshacer. Si querés conservar el historial, archivá el proyecto desde su configuración.
          </Alert>
          {!single && (
            <ul className="ac-list" style={{ color: "var(--ink)", maxHeight: 160, overflowY: "auto" }}>
              {deleting.projects.map((p) => (
                <li key={p.id}>{p.name}</li>
              ))}
            </ul>
          )}
          {deleting.projects.some((p) => p.mode === "jira") && (
            <p className="small muted mt">Las incidencias ya publicadas en JIRA no se borran: solo se elimina el vínculo local.</p>
          )}
          <Field label={single ? `Escribí el nombre del proyecto (${single.name}) para confirmar` : "Escribí ELIMINAR para confirmar"} className="mt">
            {(id) => <input id={id} className="input" value={deleting.text} onChange={(e) => setDeleting({ ...deleting, text: e.target.value })} autoComplete="off" placeholder={expected} />}
          </Field>
        </ConfirmDialog>
      )}
    </>
  );
}
