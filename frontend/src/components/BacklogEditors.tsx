"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { api, errorMessage } from "@/lib/api";
import { CONFIDENCE_LABEL, PRIORITY_LABEL, TASK_CATEGORY_LABEL } from "@/lib/format";
import { useUnsavedChanges } from "@/lib/hooks";
import type { AcceptanceCriterion, Epic, Story, Task, TeamProfile } from "@/lib/types";

import { Alert, Button, Field, IconButton, Modal, useToast } from "./ui";

function useDirtyClose(onClose: () => void) {
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);
  const close = () => {
    if (dirty && !confirm("Hay cambios sin guardar. ¿Querés descartarlos?")) return;
    onClose();
  };
  return { dirty, setDirty, close };
}

export function EpicModal({ projectId, epic, onClose, onSaved }: { projectId: number; epic?: Epic; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [form, setForm] = useState({ title: epic?.title ?? "", description: epic?.description ?? "", priority: epic?.priority ?? "medium" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { setDirty, close } = useDirtyClose(onClose);
  const set = (k: string, v: string) => (setForm((f) => ({ ...f, [k]: v })), setDirty(true));
  const save = async () => {
    if (!form.title.trim()) return setError("Ingresá un título.");
    setSaving(true);
    try {
      if (epic) await api(`/epics/${epic.id}`, { method: "PATCH", body: form });
      else await api(`/projects/${projectId}/epics`, { body: form });
      toast("success", epic ? "Épica actualizada." : "Épica creada.");
      setDirty(false);
      onClose();
      await onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title={epic ? `Editar ${epic.code}` : "Nueva épica"} onClose={close} footer={<><Button variant="secondary" onClick={close}>Cancelar</Button><Button onClick={save} loading={saving}>Guardar épica</Button></>}>
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="form-grid">
        <Field label="Título" required className="full">{(id) => <input id={id} className="input" value={form.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="Descripción" className="full">{(id) => <textarea id={id} className="textarea" value={form.description} onChange={(e) => set("description", e.target.value)} />}</Field>
        <Field label="Prioridad">
          {(id) => (
            <select id={id} className="select" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
              {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </Field>
      </div>
    </Modal>
  );
}

export function StoryModal({ epicId, story, epics, onClose, onSaved }: { epicId: number; story?: Story; epics: Epic[]; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const allStories = epics.flatMap((e) => e.stories).filter((s) => s.id !== story?.id);
  const [form, setForm] = useState({
    title: story?.title ?? "",
    description: story?.description ?? "",
    priority: story?.priority ?? "medium",
    business_value: story?.business_value ?? 5,
    estimate_confidence: story?.estimate_confidence ?? "medium",
    assumptions: story?.assumptions ?? "",
    risks: story?.risks ?? "",
    epic_id: story?.epic_id ?? epicId,
    depends_on_ids: story?.depends_on_ids ?? [],
  });
  const [criteria, setCriteria] = useState<AcceptanceCriterion[]>(story?.acceptance_criteria ?? [{ given: "", when: "", then: "" }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { setDirty, close } = useDirtyClose(onClose);
  const set = (k: string, v: unknown) => (setForm((f) => ({ ...f, [k]: v })), setDirty(true));
  const setAc = (i: number, k: keyof AcceptanceCriterion, v: string) => (setCriteria((cs) => cs.map((c, j) => (j === i ? { ...c, [k]: v } : c))), setDirty(true));

  const save = async () => {
    if (!form.title.trim()) return setError("Ingresá un título.");
    setSaving(true);
    const acceptance_criteria = criteria.filter((c) => c.given.trim() || c.when.trim() || c.then.trim());
    try {
      if (story) {
        await api(`/stories/${story.id}`, { method: "PATCH", body: { ...form, acceptance_criteria } });
      } else {
        const { depends_on_ids, epic_id, ...rest } = form;
        const created = await api<Story>(`/epics/${epic_id}/stories`, { body: { ...rest, acceptance_criteria } });
        if (depends_on_ids.length) await api(`/stories/${created.id}`, { method: "PATCH", body: { depends_on_ids } });
      }
      toast("success", story ? "Historia actualizada." : "Historia creada.");
      setDirty(false);
      onClose();
      await onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={story ? `Editar ${story.code}` : "Nueva historia de usuario"} onClose={close} wide footer={<><Button variant="secondary" onClick={close}>Cancelar</Button><Button onClick={save} loading={saving}>Guardar historia</Button></>}>
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="form-grid">
        <Field label="Título" required className="full">{(id) => <input id={id} className="input" value={form.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="Descripción" className="full" help="Formato sugerido: Como [usuario], quiero [capacidad], para [beneficio].">
          {(id) => <textarea id={id} className="textarea" value={form.description} onChange={(e) => set("description", e.target.value)} />}
        </Field>
        <Field label="Épica">
          {(id) => (
            <select id={id} className="select" value={form.epic_id} onChange={(e) => set("epic_id", Number(e.target.value))}>
              {epics.map((e) => <option key={e.id} value={e.id}>{e.code} · {e.title}</option>)}
            </select>
          )}
        </Field>
        <Field label="Prioridad">
          {(id) => (
            <select id={id} className="select" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
              {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </Field>
        <Field label="Valor de negocio (1 a 10)">
          {(id) => <input id={id} type="number" min={1} max={10} className="input" value={form.business_value} onChange={(e) => set("business_value", Number(e.target.value))} />}
        </Field>
        <Field label="Confianza de la estimación">
          {(id) => (
            <select id={id} className="select" value={form.estimate_confidence} onChange={(e) => set("estimate_confidence", e.target.value)}>
              {Object.entries(CONFIDENCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </Field>
        <Field label="Depende de (historias)" className="full" help="Ctrl/Cmd + clic para elegir varias. No se permiten dependencias circulares.">
          {(id) => (
            <select id={id} multiple className="select" style={{ minHeight: 90 }} value={form.depends_on_ids.map(String)} onChange={(e) => set("depends_on_ids", Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}>
              {allStories.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.title}</option>)}
            </select>
          )}
        </Field>
        <div className="field full">
          <span className="label">Criterios de aceptación (Given / When / Then)</span>
          {criteria.map((c, i) => (
            <div key={i} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
              <input className="input sm" aria-label={`Dado (criterio ${i + 1})`} placeholder="Dado…" value={c.given} onChange={(e) => setAc(i, "given", e.target.value)} />
              <input className="input sm" aria-label={`Cuando (criterio ${i + 1})`} placeholder="Cuando…" value={c.when} onChange={(e) => setAc(i, "when", e.target.value)} />
              <input className="input sm" aria-label={`Entonces (criterio ${i + 1})`} placeholder="Entonces…" value={c.then} onChange={(e) => setAc(i, "then", e.target.value)} />
              <IconButton label={`Quitar criterio ${i + 1}`} onClick={() => (setCriteria((cs) => cs.filter((_, j) => j !== i)), setDirty(true))}>
                <Trash2 size={16} />
              </IconButton>
            </div>
          ))}
          <div>
            <Button size="sm" variant="ghost" icon={<Plus size={16} />} onClick={() => setCriteria((cs) => [...cs, { given: "", when: "", then: "" }])}>
              Agregar criterio
            </Button>
          </div>
        </div>
        <Field label="Supuestos" className="full">{(id) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={form.assumptions} onChange={(e) => set("assumptions", e.target.value)} />}</Field>
        <Field label="Riesgos" className="full">{(id) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={form.risks} onChange={(e) => set("risks", e.target.value)} />}</Field>
      </div>
    </Modal>
  );
}

export function TaskModal({ story, task, team, onClose, onSaved }: { story: Story; task?: Task; team: TeamProfile[]; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [form, setForm] = useState({
    title: task?.title ?? "",
    description: task?.description ?? "",
    category: task?.category ?? "backend",
    profile_key: task?.profile_key ?? team[0]?.profile_key ?? "backend",
    estimated_hours: task?.estimated_hours ?? 4,
    optimistic_hours: task?.optimistic_hours ?? null,
    pessimistic_hours: task?.pessimistic_hours ?? null,
    done_criteria: task?.done_criteria ?? "",
    risks: task?.risks ?? "",
    depends_on_ids: task?.depends_on_ids ?? [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { setDirty, close } = useDirtyClose(onClose);
  const set = (k: string, v: unknown) => (setForm((f) => ({ ...f, [k]: v })), setDirty(true));
  const siblings = story.tasks.filter((t) => t.id !== task?.id);
  const profileKnown = team.some((p) => p.profile_key === form.profile_key);

  const save = async () => {
    if (!form.title.trim()) return setError("Ingresá un título.");
    if (!(form.estimated_hours >= 0)) return setError("Las horas deben ser 0 o más.");
    if ((form.optimistic_hours === null) !== (form.pessimistic_hours === null)) return setError("Completá las dos horas del rango (optimista y pesimista) o dejá ambas vacías.");
    if (form.optimistic_hours !== null && form.pessimistic_hours !== null && !(form.optimistic_hours <= form.estimated_hours && form.estimated_hours <= form.pessimistic_hours && form.pessimistic_hours > form.optimistic_hours))
      return setError("El rango debe cumplir: optimista ≤ horas estimadas ≤ pesimista.");
    setSaving(true);
    try {
      if (task) await api(`/tasks/${task.id}`, { method: "PATCH", body: form });
      else await api(`/stories/${story.id}/tasks`, { body: form });
      toast("success", task ? "Subtarea actualizada." : "Subtarea creada.");
      setDirty(false);
      onClose();
      await onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={task ? `Editar ${task.code}` : `Nueva subtarea en ${story.code}`} onClose={close} wide footer={<><Button variant="secondary" onClick={close}>Cancelar</Button><Button onClick={save} loading={saving}>Guardar subtarea</Button></>}>
      {error && <Alert tone="danger">{error}</Alert>}
      {!profileKnown && <Alert tone="warning">El perfil «{form.profile_key}» no está en el equipo. Agregalo en Equipo y capacidad antes de planificar.</Alert>}
      <div className="form-grid mt">
        <Field label="Título" required className="full">{(id) => <input id={id} className="input" value={form.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="Descripción" className="full">{(id) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={form.description} onChange={(e) => set("description", e.target.value)} />}</Field>
        <Field label="Categoría">
          {(id) => (
            <select id={id} className="select" value={form.category} onChange={(e) => set("category", e.target.value)}>
              {Object.entries(TASK_CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </Field>
        <Field label="Perfil responsable">
          {(id) => (
            <select id={id} className="select" value={form.profile_key} onChange={(e) => set("profile_key", e.target.value)}>
              {!profileKnown && <option value={form.profile_key}>{form.profile_key} (no está en el equipo)</option>}
              {team.map((p) => <option key={p.profile_key} value={p.profile_key}>{p.profile_name}</option>)}
            </select>
          )}
        </Field>
        <Field label="Horas estimadas (esfuerzo)" help={task && task.original_estimate_hours !== form.estimated_hours ? `Estimación inicial: ${task.original_estimate_hours} h` : "Esfuerzo neto; el motor suma revisión y retrabajo."}>
          {(id) => <input id={id} type="number" min={0} step={0.5} className="input" value={form.estimated_hours} onChange={(e) => set("estimated_hours", Number(e.target.value))} />}
        </Field>
        <Field label="Rango para el pronóstico (opcional)" help="Optimista y pesimista en horas. Vacío = se usa el rango según la confianza de la historia.">
          {(id) => (
            <div className="row" style={{ gap: 8 }}>
              <input id={id} type="number" min={0} step={0.5} className="input" style={{ width: 110 }} placeholder="Optimista" aria-label="Horas optimistas" value={form.optimistic_hours ?? ""} onChange={(e) => set("optimistic_hours", e.target.value === "" ? null : Number(e.target.value))} />
              <span className="subtle">a</span>
              <input type="number" min={0} step={0.5} className="input" style={{ width: 110 }} placeholder="Pesimista" aria-label="Horas pesimistas" value={form.pessimistic_hours ?? ""} onChange={(e) => set("pessimistic_hours", e.target.value === "" ? null : Number(e.target.value))} />
            </div>
          )}
        </Field>
        <Field label="Depende de (subtareas de la historia)" help="Ctrl/Cmd + clic para elegir varias.">
          {(id) => (
            <select id={id} multiple className="select" style={{ minHeight: 70 }} value={form.depends_on_ids.map(String)} onChange={(e) => set("depends_on_ids", Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}>
              {siblings.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.title}</option>)}
            </select>
          )}
        </Field>
        <Field label="Criterio de finalización" className="full">{(id) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={form.done_criteria} onChange={(e) => set("done_criteria", e.target.value)} />}</Field>
        <Field label="Riesgos" className="full">{(id) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={form.risks} onChange={(e) => set("risks", e.target.value)} />}</Field>
      </div>
    </Modal>
  );
}
