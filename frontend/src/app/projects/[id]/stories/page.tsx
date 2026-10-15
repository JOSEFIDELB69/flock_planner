"use client";

import { ChevronDown, ChevronRight, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";

import { EpicModal, StoryModal, TaskModal } from "@/components/BacklogEditors";
import { DependencyGraph } from "@/components/Gantt";
import { ObservationsPanel } from "@/components/ObservationsPanel";
import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, IconButton, Loading, PageHeader, SimulatedNotice, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CONFIDENCE_LABEL, CONFIDENCE_TONE, fmtHours, fmtNum, PRIORITY_LABEL, PRIORITY_TONE, TASK_CATEGORY_LABEL, toggled } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { useHashScroll } from "@/lib/useHashScroll";
import type { Analysis, Backlog, BacklogObservation, Epic, Story, Task, TeamProfile } from "@/lib/types";

type Del = { kind: "epic" | "story" | "task"; id: number; label: string };

export default function StoriesPage() {
  const { project, reload: reloadProject, system } = useProject();
  const pid = project.id;
  const toast = useToast();
  const backlog = useApi<Backlog>(`/projects/${pid}/backlog`);
  const team = useApi<TeamProfile[]>(`/projects/${pid}/team`);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [epicModal, setEpicModal] = useState<{ epic?: Epic } | null>(null);
  const [storyModal, setStoryModal] = useState<{ epicId: number; story?: Story } | null>(null);
  const [taskModal, setTaskModal] = useState<{ story: Story; task?: Task } | null>(null);
  const [del, setDel] = useState<Del | null>(null);
  const [gen, setGen] = useState<{ open: boolean; extra: string; busy: boolean; apply: boolean }>({ open: false, extra: "", busy: false, apply: true });
  const observations = useApi<BacklogObservation[]>(`/projects/${pid}/backlog/observations`);
  const analyses = useApi<Analysis[]>(`/projects/${pid}/requirements/analyses`);
  const obs = observations.data ?? [];
  const obsCorrections = obs.filter((o) => o.status === "correction").length;
  const obsAccepted = obs.filter((o) => o.status === "accepted" && o.kind === "assumption").length;
  const latestAnalysis = analyses.data?.[0];
  const hasUnansweredQuestions = !!latestAnalysis?.result.clarification_questions.some((_, i) => !latestAnalysis.answers?.[String(i)]?.trim());

  const epics = backlog.data?.epics ?? [];
  useHashScroll(epics.length > 0);
  const profileName = Object.fromEntries((team.data ?? []).map((p) => [p.profile_key, p.profile_name]));
  const refresh = async () => {
    await Promise.all([backlog.reload(), reloadProject()]);
  };
  const toggle = (id: number) => setCollapsed((s) => toggled(s, id));

  const generate = async () => {
    setGen((g) => ({ ...g, busy: true }));
    try {
      const r = await api<Backlog & { feedback_applied?: boolean }>(`/projects/${pid}/backlog/generate`, { body: { replace_existing: epics.length > 0, additional_instructions: gen.extra, apply_observations: gen.apply } });
      toast("success", `Backlog generado: ${r.story_count} historias y ${r.task_count} subtareas${r.feedback_applied ? ", con tus correcciones y supuestos aceptados" : ""}. Revisá las observaciones y ajustá las estimaciones.`);
      setGen({ open: false, extra: "", busy: false, apply: true });
      await Promise.all([refresh(), observations.reload()]);
    } catch (e) {
      toast("danger", errorMessage(e));
      setGen((g) => ({ ...g, busy: false }));
    }
  };

  const doDelete = async () => {
    if (!del) return;
    try {
      await api(`/${del.kind === "epic" ? "epics" : del.kind === "story" ? "stories" : "tasks"}/${del.id}`, { method: "DELETE" });
      toast("success", `${del.label} eliminado.`);
      setDel(null);
      await refresh();
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader
        title="Épicas e historias"
        description="Estructura Proyecto → Épicas → Historias → Subtareas. Todo es editable antes de confirmar la planificación; las versiones ya guardadas no cambian."
        actions={
          <>
            <Button variant="secondary" icon={<Plus size={18} />} onClick={() => setEpicModal({})}>
              Nueva épica
            </Button>
            <Button icon={<Sparkles size={18} />} onClick={() => setGen((g) => ({ ...g, open: true }))} disabled={!system?.ai_available || project.requirement_count === 0} title={!system?.ai_available ? "La IA no está disponible: revisá la sesión de Claude Code en el backend" : project.requirement_count === 0 ? "Cargá requisitos primero" : undefined}>
              {epics.length ? "Regenerar con IA" : "Generar backlog con IA"}
            </Button>
          </>
        }
      />
      <div className="stack">
        {backlog.data?.is_simulated && <SimulatedNotice what="Las épicas, historias y horas de este backlog" />}
        {epics.length > 0 && (
          <ObservationsPanel
            projectId={pid}
            items={obs}
            hasUnansweredQuestions={hasUnansweredQuestions}
            onChanged={(o) => observations.setData(obs.map((x) => (x.id === o.id ? o : x)))}
            onRegenerate={() => setGen((g) => ({ ...g, open: true, apply: true }))}
          />
        )}
        {backlog.data && (
          <div className="grid kpis">
            <Card>
              <div className="stat">
                <span className="label">Épicas / historias / subtareas</span>
                <span className="value">
                  {epics.length} / {backlog.data.story_count} / {backlog.data.task_count}
                </span>
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="label">Esfuerzo base</span>
                <span className="value">{fmtHours(backlog.data.total_hours)}</span>
                <span className="hint">{Object.entries(backlog.data.hours_by_profile).map(([k, h]) => `${profileName[k] ?? k}: ${fmtNum(h)} h`).join(" · ")}</span>
              </div>
            </Card>
          </div>
        )}
        {backlog.loading && !backlog.data && <Loading />}
        {backlog.error && <ErrorState message={backlog.error} onRetry={backlog.reload} />}
        {backlog.data && epics.length === 0 && (
          <Card>
            <EmptyState title="Todavía no hay backlog" action={<div className="row"><Button onClick={() => setEpicModal({})}>Crear épica manual</Button></div>}>
              Generalo con IA a partir de los requisitos analizados o crealo manualmente.
            </EmptyState>
          </Card>
        )}
        {epics.map((e) => (
          <section key={e.id} id={e.code} className="tree-epic anchor-target" aria-label={`Épica ${e.code}`}>
            <header>
              <button className="disclosure" aria-expanded={!collapsed.has(e.id)} aria-label={collapsed.has(e.id) ? "Expandir épica" : "Contraer épica"} onClick={() => toggle(e.id)}>
                {collapsed.has(e.id) ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
              </button>
              <span className="mono">{e.code}</span>
              <h4 style={{ flex: 1 }}>{e.title}</h4>
              <Badge tone={PRIORITY_TONE[e.priority]}>{PRIORITY_LABEL[e.priority]}</Badge>
              {e.source === "demo" && <Badge tone="warning">Simulada</Badge>}
              {e.source === "ai" && <Badge tone="primary">IA</Badge>}
              <span className="subtle">{fmtHours(e.total_hours)}</span>
              <Button size="sm" variant="ghost" icon={<Plus size={16} />} onClick={() => setStoryModal({ epicId: e.id })}>
                Historia
              </Button>
              <IconButton label={`Editar ${e.code}`} onClick={() => setEpicModal({ epic: e })}>
                <Pencil size={16} />
              </IconButton>
              <IconButton label={`Eliminar ${e.code}`} onClick={() => setDel({ kind: "epic", id: e.id, label: `${e.code} ${e.title}` })}>
                <Trash2 size={16} />
              </IconButton>
            </header>
            {!collapsed.has(e.id) && e.description && <p className="subtle" style={{ padding: "8px 15px 0 45px", margin: 0 }}>{e.description}</p>}
            {!collapsed.has(e.id) &&
              e.stories.map((s) => (
                <div key={s.id} id={s.code} className="tree-story anchor-target">
                  <header>
                    <span className="mono">{s.code}</span>
                    <strong style={{ flex: 1 }}>{s.title}</strong>
                    <Badge tone={PRIORITY_TONE[s.priority]}>{PRIORITY_LABEL[s.priority]}</Badge>
                    <Badge title="Valor de negocio">Valor {s.business_value}</Badge>
                    <Badge tone={CONFIDENCE_TONE[s.estimate_confidence]}>Confianza {CONFIDENCE_LABEL[s.estimate_confidence].toLowerCase()}</Badge>
                    <Badge tone={s.estimate_status === "revised" ? "success" : ""}>{s.estimate_status === "revised" ? "Estimación revisada" : "Estimación inicial"}</Badge>
                    <span className="subtle">{fmtHours(s.total_hours)}</span>
                    <IconButton label={`Editar ${s.code}`} onClick={() => setStoryModal({ epicId: e.id, story: s })}>
                      <Pencil size={16} />
                    </IconButton>
                    <IconButton label={`Eliminar ${s.code}`} onClick={() => setDel({ kind: "story", id: s.id, label: `${s.code} ${s.title}` })}>
                      <Trash2 size={16} />
                    </IconButton>
                  </header>
                  {s.description && <p className="small" style={{ margin: "6px 0 0", whiteSpace: "pre-line" }}>{s.description}</p>}
                  {s.acceptance_criteria.length > 0 && (
                    <ul className="ac-list">
                      {s.acceptance_criteria.map((c, i) => (
                        <li key={i}>
                          <strong>Dado</strong> {c.given}, <strong>cuando</strong> {c.when}, <strong>entonces</strong> {c.then}.
                        </li>
                      ))}
                    </ul>
                  )}
                  {s.depends_on_ids.length > 0 && (
                    <p className="subtle" style={{ margin: "6px 0 0" }}>
                      Depende de: {s.depends_on_ids.map((d) => epics.flatMap((x) => x.stories).find((x) => x.id === d)?.code).join(", ")}
                    </p>
                  )}
                  {(s.assumptions || s.risks) && (
                    <p className="subtle" style={{ margin: "6px 0 0" }}>
                      {s.assumptions && <>Supuestos: {s.assumptions} </>}
                      {s.risks && <>· Riesgos: {s.risks}</>}
                    </p>
                  )}
                  <div className="tree-tasks table-wrap">
                    <table className="table compact">
                      <thead>
                        <tr>
                          <th>Subtarea</th>
                          <th>Categoría</th>
                          <th>Perfil</th>
                          <th className="num">Horas</th>
                          <th>Depende de</th>
                          <th>
                            <span className="sr-only">Acciones</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {s.tasks.map((t) => (
                          <tr key={t.id} id={t.code} className="anchor-target">
                            <td>
                              <span className="mono">{t.code}</span> {t.title}
                              {t.done_criteria && <div className="subtle">Hecho cuando: {t.done_criteria}</div>}
                            </td>
                            <td>{TASK_CATEGORY_LABEL[t.category] ?? t.category}</td>
                            <td>{profileName[t.profile_key] ?? <Badge tone="warning">{t.profile_key} (sin perfil)</Badge>}</td>
                            <td className="num">
                              {fmtNum(t.estimated_hours)}
                              {t.estimate_status === "revised" && <div className="subtle">inicial {fmtNum(t.original_estimate_hours)}</div>}
                            </td>
                            <td className="subtle">{t.depends_on_ids.map((d) => s.tasks.find((x) => x.id === d)?.code ?? d).join(", ") || "—"}</td>
                            <td style={{ whiteSpace: "nowrap" }}>
                              <IconButton label={`Editar ${t.code}`} onClick={() => setTaskModal({ story: s, task: t })}>
                                <Pencil size={16} />
                              </IconButton>
                              <IconButton label={`Eliminar ${t.code}`} onClick={() => setDel({ kind: "task", id: t.id, label: `${t.code} ${t.title}` })}>
                                <Trash2 size={16} />
                              </IconButton>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Button size="sm" variant="ghost" icon={<Plus size={16} />} onClick={() => setTaskModal({ story: s })}>
                    Subtarea
                  </Button>
                </div>
              ))}
          </section>
        ))}
        {epics.length > 0 && (
          <Card title="Diagrama de dependencias entre historias">
            <DependencyGraph stories={epics.flatMap((e) => e.stories)} />
          </Card>
        )}
      </div>

      {epicModal && <EpicModal projectId={pid} epic={epicModal.epic} onClose={() => setEpicModal(null)} onSaved={refresh} />}
      {storyModal && <StoryModal epicId={storyModal.epicId} story={storyModal.story} epics={epics} onClose={() => setStoryModal(null)} onSaved={refresh} />}
      {taskModal && <TaskModal story={taskModal.story} task={taskModal.task} team={team.data ?? []} onClose={() => setTaskModal(null)} onSaved={refresh} />}
      {del && (
        <ConfirmDialog title="Confirmar eliminación" danger confirmLabel="Eliminar" onCancel={() => setDel(null)} onConfirm={doDelete}>
          <p>
            Vas a eliminar <strong>{del.label}</strong>
            {del.kind === "epic" ? " con todas sus historias y subtareas" : del.kind === "story" ? " con todas sus subtareas" : ""}. Las versiones de plan ya guardadas conservan su copia.
          </p>
        </ConfirmDialog>
      )}
      {gen.open && (
        <ConfirmDialog
          title={epics.length ? "Regenerar el backlog con IA" : "Generar backlog con IA"}
          confirmLabel={epics.length ? "Reemplazar backlog actual" : "Generar backlog"}
          danger={epics.length > 0}
          loading={gen.busy}
          onCancel={() => setGen({ open: false, extra: "", busy: false, apply: true })}
          onConfirm={generate}
        >
          {epics.length > 0 && <Alert tone="warning">El backlog actual ({backlog.data?.story_count} historias) se reemplazará. Las versiones de plan guardadas no se modifican.</Alert>}
          <p className="mt">Se enviarán a la IA los requisitos activos, el último análisis y tus respuestas de aclaración. La generación puede tardar hasta un par de minutos.</p>
          <Field label="Indicaciones adicionales (opcional)" help="Por ejemplo: priorizar el módulo de reservas, no incluir app móvil.">
            {(id) => <textarea id={id} className="textarea" value={gen.extra} onChange={(e) => setGen((g) => ({ ...g, extra: e.target.value }))} maxLength={4000} />}
          </Field>
          {(obsCorrections > 0 || obsAccepted > 0) && (
            <label className="checkbox mt">
              <input type="checkbox" checked={gen.apply} onChange={(e) => setGen((g) => ({ ...g, apply: e.target.checked }))} />
              Enviar mis decisiones sobre las observaciones anteriores ({obsCorrections} {obsCorrections === 1 ? "corrección" : "correcciones"}, {obsAccepted} {obsAccepted === 1 ? "supuesto aceptado" : "supuestos aceptados"})
            </label>
          )}
          {obs.some((o) => o.status === "pending") && <p className="subtle small">Las observaciones pendientes no se envían: el agente puede volver a suponer lo mismo.</p>}
        </ConfirmDialog>
      )}
    </>
  );
}
