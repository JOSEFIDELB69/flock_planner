"use client";

import { Pencil, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { TaskModal } from "@/components/BacklogEditors";
import { useProject } from "@/components/ProjectContext";
import { Badge, Card, EmptyState, ErrorState, IconButton, Loading, PageHeader, SimulatedNotice, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CONFIDENCE_LABEL, CONFIDENCE_TONE, fmtNum, TASK_CATEGORY_LABEL } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Backlog, Story, Task, TeamProfile } from "@/lib/types";

type Row = Task & { story: Story; epicCode: string; epicTitle: string };
type SortKey = "code" | "estimated_hours" | "profile_key" | "story";
const STATUS = { todo: "Pendiente", in_progress: "En curso", done: "Hecha" } as Record<string, string>;

export default function BacklogPage() {
  const { project } = useProject();
  const toast = useToast();
  const backlog = useApi<Backlog>(`/projects/${project.id}/backlog`);
  const team = useApi<TeamProfile[]>(`/projects/${project.id}/team`);
  const [q, setQ] = useState("");
  const [profile, setProfile] = useState("");
  const [epic, setEpic] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "code", dir: 1 });
  const [edit, setEdit] = useState<{ story: Story; task: Task } | null>(null);
  const names = Object.fromEntries((team.data ?? []).map((p) => [p.profile_key, p.profile_name]));

  const all: Row[] = useMemo(
    () => (backlog.data?.epics ?? []).flatMap((e) => e.stories.flatMap((s) => s.tasks.map((t) => ({ ...t, story: s, epicCode: e.code, epicTitle: e.title })))),
    [backlog.data],
  );
  const rows = useMemo(() => {
    const list = all.filter(
      (r) =>
        (!q || `${r.code} ${r.title} ${r.story.title}`.toLowerCase().includes(q.toLowerCase())) &&
        (!profile || r.profile_key === profile) &&
        (!epic || r.epicCode === epic) &&
        (!category || r.category === category),
    );
    const val = (r: Row) => (sort.key === "story" ? r.story.code : r[sort.key]);
    return [...list].sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * sort.dir);
  }, [all, q, profile, epic, category, sort]);
  const total = rows.reduce((s, r) => s + r.estimated_hours, 0);

  const th = (key: SortKey, label: string, num = false) => (
    <th className={num ? "num" : ""} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : 1 }))}>
        {label} {sort.key === key ? (sort.dir === 1 ? "▲" : "▼") : ""}
      </button>
    </th>
  );

  const setStatus = async (t: Row, status: string) => {
    try {
      await api(`/tasks/${t.id}`, { method: "PATCH", body: { status } });
      await backlog.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader title="Backlog" description="Vista plana de todas las subtareas con filtros y ordenación. Para editar la estructura usá Épicas e historias." />
      {backlog.data?.is_simulated && (
        <div style={{ marginBottom: 20 }}>
          <SimulatedNotice what="Las tareas y horas" />
        </div>
      )}
      <Card>
        <div className="toolbar">
          <div className="search grow">
            <Search size={16} aria-hidden />
            <input className="input" placeholder="Buscar subtarea o historia" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar en el backlog" />
          </div>
          <select className="select" style={{ width: 190 }} value={profile} onChange={(e) => setProfile(e.target.value)} aria-label="Filtrar por perfil">
            <option value="">Todos los perfiles</option>
            {Array.from(new Set(all.map((r) => r.profile_key))).map((k) => (
              <option key={k} value={k}>
                {names[k] ?? k}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 190 }} value={epic} onChange={(e) => setEpic(e.target.value)} aria-label="Filtrar por épica">
            <option value="">Todas las épicas</option>
            {(backlog.data?.epics ?? []).map((e) => (
              <option key={e.code} value={e.code}>
                {e.code} · {e.title}
              </option>
            ))}
          </select>
          <select className="select" style={{ width: 190 }} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Filtrar por categoría">
            <option value="">Todas las categorías</option>
            {Object.entries(TASK_CATEGORY_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>
        {backlog.loading && !backlog.data && <Loading />}
        {backlog.error && <ErrorState message={backlog.error} onRetry={backlog.reload} />}
        {backlog.data && all.length === 0 && (
          <EmptyState title="El backlog está vacío" action={<Link className="btn" href={`/projects/${project.id}/stories`}>Ir a Épicas e historias</Link>}>
            Generalo con IA o crealo manualmente.
          </EmptyState>
        )}
        {rows.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  {th("code", "Subtarea")}
                  {th("story", "Historia")}
                  <th>Épica</th>
                  {th("profile_key", "Perfil")}
                  <th>Categoría</th>
                  {th("estimated_hours", "Horas", true)}
                  <th>Confianza</th>
                  <th>Estado</th>
                  <th>
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <span className="mono">{r.code}</span> {r.title}
                    </td>
                    <td>
                      <span className="mono">{r.story.code}</span> <span className="subtle">{r.story.title}</span>
                    </td>
                    <td className="mono">{r.epicCode}</td>
                    <td>{names[r.profile_key] ?? <Badge tone="warning">{r.profile_key}</Badge>}</td>
                    <td>{TASK_CATEGORY_LABEL[r.category] ?? r.category}</td>
                    <td className="num">{fmtNum(r.estimated_hours)}</td>
                    <td>
                      <Badge tone={CONFIDENCE_TONE[r.story.estimate_confidence]}>{CONFIDENCE_LABEL[r.story.estimate_confidence]}</Badge>
                    </td>
                    <td>
                      <select className="select sm" value={r.status} onChange={(e) => setStatus(r, e.target.value)} aria-label={`Estado de ${r.code}`}>
                        {Object.entries(STATUS).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <IconButton label={`Editar ${r.code}`} onClick={() => setEdit({ story: r.story, task: r })}>
                        <Pencil size={16} />
                      </IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={5}>{rows.length} subtareas filtradas</td>
                  <td className="num">{fmtNum(total)}</td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>
      {edit && <TaskModal story={edit.story} task={edit.task} team={team.data ?? []} onClose={() => setEdit(null)} onSaved={backlog.reload} />}
    </>
  );
}
