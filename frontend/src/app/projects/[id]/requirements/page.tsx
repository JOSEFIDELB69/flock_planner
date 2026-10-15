"use client";

import { Check, FileText, FileUp, History, Pencil, Plus, Search, Sparkles, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DocumentsPanel } from "@/components/DocumentsPanel";
import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, IconButton, Loading, Modal, PageHeader, SimulatedNotice, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, toggled, PRIORITY_LABEL, PRIORITY_TONE, REQ_STATUS_LABEL, REQ_STATUS_TONE, REQ_TYPE_LABEL } from "@/lib/format";
import { useApi, useUnsavedChanges } from "@/lib/hooks";
import { useHashScroll } from "@/lib/useHashScroll";
import type { Analysis, AuditEntry, ProjectDocument, Requirement } from "@/lib/types";

type Draft = Partial<Requirement> & { title: string };
const EMPTY: Draft = { title: "", description: "", type: "functional", priority: "medium", status: "draft", source: "manual", group_name: "", assumptions: "", risks: "" };

export default function RequirementsPage() {
  const { project, reload: reloadProject, system } = useProject();
  const pid = project.id;
  const toast = useToast();
  const reqs = useApi<Requirement[]>(`/projects/${pid}/requirements`);
  const analyses = useApi<Analysis[]>(`/projects/${pid}/requirements/analyses`);
  const docs = useApi<ProjectDocument[]>(`/projects/${pid}/documents`);
  const [q, setQ] = useState("");
  // ?q=REQ-012 (desde las observaciones del backlog) filtra la lista; #analisis lleva a las preguntas de aclaración
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("q");
    if (initial) setQ(initial);
  }, []);
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [group, setGroup] = useState("");
  const [editing, setEditing] = useState<Draft | null>(null);
  const [deleting, setDeleting] = useState<Requirement | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [history, setHistory] = useState<{ req: Requirement; rows: AuditEntry[] } | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const list = reqs.data ?? [];
  const groups = useMemo(() => Array.from(new Set(list.map((r) => r.group_name).filter(Boolean))).sort(), [list]);
  const rows = list.filter(
    (r) =>
      (!q || `${r.code} ${r.title} ${r.description}`.toLowerCase().includes(q.toLowerCase())) &&
      (!type || r.type === type) &&
      (!status || r.status === status) &&
      (!group || r.group_name === group),
  );
  const visibleSelected = rows.filter((r) => selected.has(r.id));
  const allVisibleSelected = rows.length > 0 && visibleSelected.length === rows.length;
  const toggle = (id: number) => setSelected((s) => toggled(s, id));
  const toggleAll = () => setSelected(allVisibleSelected ? new Set() : new Set(rows.map((r) => r.id)));
  const latest = analyses.data?.[0] ?? null;
  useHashScroll(!!latest);
  const refresh = async () => {
    await Promise.all([reqs.reload(), reloadProject(), docs.reload()]);
  };
  const docName = (id: number | null) => (id ? docs.data?.find((d) => d.id === id)?.filename : undefined);
  const suggestedCount = list.filter((r) => r.status === "suggested").length;

  const bulkStatus = async (newStatus: "confirmed" | "rejected") => {
    setBulkBusy(true);
    try {
      const r = await api<{ updated: number }>(`/projects/${pid}/requirements/status`, { body: { ids: visibleSelected.map((x) => x.id), status: newStatus } });
      toast("success", `${r.updated} requisitos marcados como ${newStatus === "confirmed" ? "confirmados" : "rechazados"}.`);
      setSelected(new Set());
      await reqs.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const setReqStatus = async (r: Requirement, s: string) => {
    try {
      await api(`/requirements/${r.id}`, { method: "PATCH", body: { status: s } });
      toast("success", `${r.code} marcado como ${REQ_STATUS_LABEL[s].toLowerCase()}.`);
      await reqs.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  const analyze = async () => {
    setAnalyzing(true);
    try {
      await api(`/projects/${pid}/requirements/analyze`, { method: "POST" });
      toast("success", "Análisis guardado. Revisá las preguntas de aclaración antes de generar el backlog.");
      await analyses.reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const openHistory = async (r: Requirement) => {
    try {
      setHistory({ req: r, rows: await api<AuditEntry[]>(`/requirements/${r.id}/history`) });
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader
        title="Requisitos/Requerimientos"
        description="Cargá requisitos funcionales y no funcionales. Revisalos antes de enviarlos a la IA: el análisis nunca modifica tus requisitos sin tu confirmación."
        actions={
          <>
            <Button variant="secondary" icon={<FileUp size={18} />} onClick={() => setBulkOpen(true)}>
              Pegar texto
            </Button>
            <Button variant="secondary" icon={<Plus size={18} />} onClick={() => setEditing({ ...EMPTY })}>
              Nuevo requisito
            </Button>
            <Button icon={<Sparkles size={18} />} onClick={analyze} loading={analyzing} disabled={!list.length || !system?.ai_available} title={!system?.ai_available ? "La IA no está disponible: revisá la sesión de Claude Code en el backend" : undefined}>
              Analizar con IA
            </Button>
          </>
        }
      />
      {system && !system.ai_available && (
        <div style={{ marginBottom: 20 }}>
          <Alert tone="info">El análisis con IA no está disponible: el backend no encuentra Claude Code con una sesión iniciada. Podés continuar y crear el backlog manualmente en Épicas e historias.</Alert>
        </div>
      )}

      <div className="stack">
        <DocumentsPanel projectId={pid} documents={docs.data ?? []} system={system} onChanged={refresh} />
        {suggestedCount > 0 && (
          <Alert tone="warning" title={`${suggestedCount} requisitos sugeridos pendientes de revisión`} action={<Button size="sm" variant="secondary" onClick={() => setStatus("suggested")}>Ver sugeridos</Button>}>
            Los propuso el agente a partir de documentos adjuntos. No se usan en el análisis ni en el backlog hasta que los confirmes (de a uno o seleccionándolos).
          </Alert>
        )}
        <Card>
          <div className="toolbar">
            <div className="search grow">
              <Search size={16} aria-hidden />
              <input className="input" placeholder="Buscar por código, título o descripción" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar requisitos" />
            </div>
            <select className="select" style={{ width: 170 }} value={type} onChange={(e) => setType(e.target.value)} aria-label="Filtrar por tipo">
              <option value="">Todos los tipos</option>
              {Object.entries(REQ_TYPE_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <select className="select" style={{ width: 160 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtrar por estado">
              <option value="">Todos los estados</option>
              {Object.entries(REQ_STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            {groups.length > 0 && (
              <select className="select" style={{ width: 170 }} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Filtrar por grupo">
                <option value="">Todos los grupos</option>
                {groups.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            )}
            {/* acciones sobre la selección en la misma barra: la tabla no se desplaza al seleccionar */}
            <div className="bulk-actions" role="region" aria-label="Acciones sobre la selección" aria-live="polite">
              {visibleSelected.length > 0 && (
                <>
                  <span>{visibleSelected.length} {visibleSelected.length === 1 ? "seleccionado" : "seleccionados"}</span>
                  <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                    Quitar selección
                  </Button>
                  <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => bulkStatus("confirmed")} loading={bulkBusy}>
                    Confirmar
                  </Button>
                  <Button size="sm" variant="secondary" icon={<X size={14} />} onClick={() => bulkStatus("rejected")} disabled={bulkBusy}>
                    Rechazar
                  </Button>
                  <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={() => setBulkDeleting(true)}>
                    Eliminar seleccionados
                  </Button>
                </>
              )}
            </div>
          </div>
          {reqs.loading && !reqs.data && <Loading />}
          {reqs.error && <ErrorState message={reqs.error} onRetry={reqs.reload} />}
          {reqs.data && rows.length === 0 && (
            <EmptyState title={list.length ? "Sin resultados" : "Todavía no hay requisitos"} action={!list.length && <Button onClick={() => setBulkOpen(true)}>Pegar requisitos en texto libre</Button>}>
              {list.length ? "Probá con otros filtros." : "Podés escribirlos uno por uno, pegar un texto con viñetas o importar un documento Word, PDF o de texto plano."}
            </EmptyState>
          )}
          {rows.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>
                      <input type="checkbox" checked={allVisibleSelected} ref={(el) => { if (el) el.indeterminate = visibleSelected.length > 0 && !allVisibleSelected; }} onChange={toggleAll} aria-label={q || type || status || group ? "Seleccionar todos los requisitos filtrados" : "Seleccionar todos los requisitos"} />
                    </th>
                    <th>Código</th>
                    <th>Requisito</th>
                    <th>Tipo</th>
                    <th>Prioridad</th>
                    <th>Estado</th>
                    <th>Fuente</th>
                    <th>
                      <span className="sr-only">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className={selected.has(r.id) ? "selected" : ""}>
                      <td>
                        <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label={`Seleccionar ${r.code}`} />
                      </td>
                      <td className="mono">{r.code}</td>
                      <td style={{ maxWidth: 480 }}>
                        <strong>{r.title}</strong>
                        {r.description && r.description !== r.title && <div className="subtle">{r.description.slice(0, 220)}</div>}
                        <div className="row" style={{ gap: 6, marginTop: 4 }}>
                          {r.group_name && <Badge>{r.group_name}</Badge>}
                          {r.source_document_id && (
                            <a className="badge primary" href={`/api/v1/documents/${r.source_document_id}/download`} title="Descargar el documento de origen">
                              <FileText size={12} aria-hidden /> {docName(r.source_document_id) ?? "documento"}
                            </a>
                          )}
                          {r.duplicate_of_id && <Badge tone="warning">Duplica a {list.find((x) => x.id === r.duplicate_of_id)?.code}</Badge>}
                          {r.depends_on_ids.length > 0 && <Badge tone="info">Depende de {r.depends_on_ids.map((id) => list.find((x) => x.id === id)?.code).join(", ")}</Badge>}
                          {r.related_ids.length > 0 && <Badge>Relacionado con {r.related_ids.map((id) => list.find((x) => x.id === id)?.code).join(", ")}</Badge>}
                        </div>
                      </td>
                      <td>{REQ_TYPE_LABEL[r.type]}</td>
                      <td>
                        <Badge tone={PRIORITY_TONE[r.priority]}>{PRIORITY_LABEL[r.priority]}</Badge>
                      </td>
                      <td>
                        <Badge tone={REQ_STATUS_TONE[r.status]}>{REQ_STATUS_LABEL[r.status]}</Badge>
                      </td>
                      <td className="subtle">{r.source}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        {r.status !== "confirmed" && (
                          <IconButton label={`Confirmar ${r.code}`} onClick={() => setReqStatus(r, "confirmed")}>
                            <Check size={16} />
                          </IconButton>
                        )}
                        {r.status !== "rejected" && (
                          <IconButton label={`Rechazar ${r.code}`} onClick={() => setReqStatus(r, "rejected")}>
                            <X size={16} />
                          </IconButton>
                        )}
                        <IconButton label={`Editar ${r.code}`} onClick={() => setEditing({ ...r })}>
                          <Pencil size={16} />
                        </IconButton>
                        <IconButton label={`Historial de ${r.code}`} onClick={() => openHistory(r)}>
                          <History size={16} />
                        </IconButton>
                        <IconButton label={`Eliminar ${r.code}`} onClick={() => setDeleting(r)}>
                          <Trash2 size={16} />
                        </IconButton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {list.length > 0 && <p className="subtle mt">{list.length} requisitos · los rechazados y duplicados no se envían a la IA ni se planifican.</p>}
        </Card>

        {analyses.loading && !analyses.data && <Loading label="Cargando análisis…" />}
        {latest && (
          <div id="analisis" className="anchor-target">
            <AnalysisPanel analysis={latest} onChanged={async () => (await analyses.reload(), await refresh())} projectId={pid} />
          </div>
        )}
      </div>

      {editing && <RequirementModal draft={editing} all={list} projectId={pid} onClose={() => setEditing(null)} onSaved={refresh} />}
      {bulkOpen && <BulkModal projectId={pid} onClose={() => setBulkOpen(false)} onSaved={refresh} />}
      {bulkDeleting && (
        <ConfirmDialog
          title={`Eliminar ${visibleSelected.length} requisitos`}
          danger
          loading={bulkBusy}
          confirmLabel={`Eliminar ${visibleSelected.length} requisitos`}
          onCancel={() => setBulkDeleting(false)}
          onConfirm={async () => {
            setBulkBusy(true);
            try {
              const r = await api<{ deleted: number }>(`/projects/${pid}/requirements/delete`, { body: { ids: visibleSelected.map((x) => x.id), confirm: true } });
              toast("success", `Se eliminaron ${r.deleted} requisitos.`);
              setSelected(new Set());
              setBulkDeleting(false);
              await refresh();
            } catch (e) {
              toast("danger", errorMessage(e));
            } finally {
              setBulkBusy(false);
            }
          }}
        >
          <p>Vas a eliminar estos requisitos. Cada eliminación queda en la auditoría del proyecto, pero no se pueden recuperar desde la interfaz. El backlog y las versiones del plan ya generados no cambian.</p>
          <ul className="ac-list" style={{ color: "var(--ink)", maxHeight: 200, overflowY: "auto" }}>
            {visibleSelected.map((r) => (
              <li key={r.id}>
                <span className="mono">{r.code}</span> · {r.title}
              </li>
            ))}
          </ul>
        </ConfirmDialog>
      )}
      {deleting && (
        <ConfirmDialog
          title="Eliminar requisito"
          danger
          confirmLabel={`Eliminar ${deleting.code}`}
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            try {
              await api(`/requirements/${deleting.id}`, { method: "DELETE" });
              toast("success", `${deleting.code} eliminado.`);
              setDeleting(null);
              await refresh();
            } catch (e) {
              toast("danger", errorMessage(e));
            }
          }}
        >
          <p>
            Vas a eliminar <strong>{deleting.code} · {deleting.title}</strong>. El cambio queda en la auditoría del proyecto, pero el requisito no se puede recuperar desde la interfaz.
          </p>
        </ConfirmDialog>
      )}
      {history && (
        <Modal title={`Historial de ${history.req.code}`} onClose={() => setHistory(null)} wide>
          <ul className="list-plain">
            {history.rows.map((h) => (
              <li key={h.id}>
                <div className="row between">
                  <strong>{h.action === "create" ? "Creación" : h.action === "update" ? "Modificación" : h.action}</strong>
                  <span className="subtle">
                    {fmtDateTime(h.created_at)} · {h.actor}
                  </span>
                </div>
                {h.action === "update" && h.before && h.after && (
                  <ul className="ac-list">
                    {Object.keys(h.after)
                      .filter((k) => JSON.stringify(h.before?.[k]) !== JSON.stringify(h.after?.[k]))
                      .map((k) => (
                        <li key={k}>
                          {k}: <s>{String(JSON.stringify(h.before?.[k]) ?? "")}</s> → {String(JSON.stringify(h.after?.[k]) ?? "")}
                        </li>
                      ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Modal>
      )}
    </>
  );
}

function RequirementModal({ draft, all, projectId, onClose, onSaved }: { draft: Draft; all: Requirement[]; projectId: number; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [form, setForm] = useState<Draft>(draft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);
  const others = all.filter((r) => r.id !== draft.id);
  const set = (k: keyof Requirement, v: unknown) => {
    setForm((f) => ({ ...f, [k]: v }));
    setDirty(true);
  };
  const close = () => {
    if (dirty && !confirm("Hay cambios sin guardar. ¿Querés descartarlos?")) return;
    onClose();
  };

  const save = async () => {
    if (!form.title.trim()) {
      setError("Ingresá un título.");
      return;
    }
    setSaving(true);
    try {
      const body = {
        title: form.title,
        description: form.description,
        type: form.type,
        priority: form.priority,
        status: form.status,
        source: form.source,
        group_name: form.group_name,
        assumptions: form.assumptions,
        risks: form.risks,
      };
      if (draft.id) {
        await api(`/requirements/${draft.id}`, {
          method: "PATCH",
          body: { ...body, duplicate_of_id: form.duplicate_of_id ?? null, related_ids: form.related_ids ?? [], depends_on_ids: form.depends_on_ids ?? [] },
        });
      } else {
        await api(`/projects/${projectId}/requirements`, { body });
      }
      toast("success", draft.id ? "Requisito actualizado." : "Requisito creado.");
      setDirty(false);
      onClose();
      await onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const multi = (key: "related_ids" | "depends_on_ids", label: string) => (
    <Field label={label} className="full" help="Ctrl/Cmd + clic para elegir varios.">
      {(id) => (
        <select id={id} multiple className="select" style={{ minHeight: 90 }} value={(form[key] ?? []).map(String)} onChange={(e) => set(key, Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}>
          {others.map((r) => (
            <option key={r.id} value={r.id}>
              {r.code} · {r.title}
            </option>
          ))}
        </select>
      )}
    </Field>
  );

  return (
    <Modal
      title={draft.id ? `Editar ${draft.code}` : "Nuevo requisito"}
      onClose={close}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button onClick={save} loading={saving}>
            Guardar requisito
          </Button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="form-grid mt">
        <Field label="Título" required className="full">
          {(id) => <input id={id} className="input" value={form.title} onChange={(e) => set("title", e.target.value)} maxLength={300} />}
        </Field>
        <Field label="Descripción" className="full">
          {(id) => <textarea id={id} className="textarea" value={form.description} onChange={(e) => set("description", e.target.value)} />}
        </Field>
        <Field label="Tipo">
          {(id) => (
            <select id={id} className="select" value={form.type} onChange={(e) => set("type", e.target.value)}>
              {Object.entries(REQ_TYPE_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Prioridad">
          {(id) => (
            <select id={id} className="select" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
              {Object.entries(PRIORITY_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Estado">
          {(id) => (
            <select id={id} className="select" value={form.status} onChange={(e) => set("status", e.target.value)}>
              {Object.entries(REQ_STATUS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Fuente">{(id) => <input id={id} className="input" value={form.source} onChange={(e) => set("source", e.target.value)} />}</Field>
        <Field label="Grupo" help="Agrupa requisitos relacionados (por ejemplo, un módulo).">
          {(id) => <input id={id} className="input" value={form.group_name} onChange={(e) => set("group_name", e.target.value)} list="req-groups" />}
        </Field>
        <datalist id="req-groups">
          {Array.from(new Set(all.map((r) => r.group_name).filter(Boolean))).map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
        {draft.id && (
          <Field label="Duplicado de">
            {(id) => (
              <select id={id} className="select" value={form.duplicate_of_id ?? ""} onChange={(e) => set("duplicate_of_id", e.target.value ? Number(e.target.value) : null)}>
                <option value="">No es duplicado</option>
                {others.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.code} · {r.title}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}
        <Field label="Supuestos" className="full">
          {(id) => <textarea id={id} className="textarea" value={form.assumptions} onChange={(e) => set("assumptions", e.target.value)} />}
        </Field>
        <Field label="Riesgos" className="full">
          {(id) => <textarea id={id} className="textarea" value={form.risks} onChange={(e) => set("risks", e.target.value)} />}
        </Field>
        {draft.id && others.length > 0 && (
          <>
            {multi("depends_on_ids", "Depende de")}
            {multi("related_ids", "Relacionado con")}
          </>
        )}
      </div>
    </Modal>
  );
}

function BulkModal({ projectId, onClose, onSaved }: { projectId: number; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [source, setSource] = useState("texto libre");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useUnsavedChanges(text.length > 0);

  const save = async () => {
    setBusy(true);
    try {
      const created = await api<Requirement[]>(`/projects/${projectId}/requirements/bulk`, { body: { text, source } });
      toast("success", `Se crearon ${created.length} requisitos en borrador.`);
      setText("");
      onClose();
      await onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Pegar requisitos en texto libre"
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={save} loading={busy} disabled={!text.trim()}>
            Crear requisitos
          </Button>
        </>
      }
    >
      <p className="muted">
        Usá una viñeta o un número por requisito, o separalos con una línea en blanco. Para trabajar con un archivo (Word, PDF o texto), usá <strong>Adjuntar documento</strong>: queda adjunto al proyecto y el agente lo lee.
      </p>
      {error && <Alert tone="danger">{error}</Alert>}
      <Field label="Texto" className="mt">
        {(id) => <textarea id={id} className="textarea" style={{ minHeight: 260 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={"- El paciente puede reservar turnos online.\n- El administrador gestiona agendas.\n- El sistema envía recordatorios por email."} />}
      </Field>
      <Field label="Fuente" className="mt">
        {(id) => <input id={id} className="input" value={source} onChange={(e) => setSource(e.target.value)} />}
      </Field>
    </Modal>
  );
}

function AnalysisPanel({ analysis, onChanged, projectId }: { analysis: Analysis; onChanged: () => Promise<void>; projectId: number }) {
  const toast = useToast();
  const r = analysis.result;
  const [answers, setAnswers] = useState<Record<string, string>>(analysis.answers ?? {});
  const [proceed, setProceed] = useState(analysis.proceed_with_assumptions);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const dirty = JSON.stringify(answers) !== JSON.stringify(analysis.answers ?? {}) || proceed !== analysis.proceed_with_assumptions;
  useUnsavedChanges(dirty);

  const saveAnswers = async () => {
    setBusy("answers");
    try {
      await api(`/analyses/${analysis.id}/answers`, { method: "PUT", body: { answers, proceed_with_assumptions: proceed } });
      toast("success", "Respuestas guardadas. Se usarán al generar el backlog.");
      await onChanged();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const accept = async () => {
    setBusy("accept");
    try {
      const created = await api<Requirement[]>(`/analyses/${analysis.id}/accept-suggestions`, { body: { indexes: selected } });
      toast("success", `Se incorporaron ${created.length} requisitos sugeridos.`);
      setSelected([]);
      await onChanged();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const section = (title: string, items: string[]) =>
    items.length > 0 && (
      <div>
        <h4 style={{ marginBottom: 6 }}>{title}</h4>
        <ul className="ac-list" style={{ color: "var(--ink)" }}>
          {items.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      </div>
    );
  const unanswered = r.clarification_questions.filter((_, i) => !answers[String(i)]?.trim()).length;

  return (
    <Card title="Análisis de requisitos" sub={`${analysis.is_simulated ? "Simulado" : `IA (${analysis.model})`} · ${fmtDateTime(analysis.created_at)} · ${analysis.created_by}`}>
      {analysis.is_simulated && <SimulatedNotice what="El análisis y las preguntas" />}
      {r.summary && <p className="mt">{r.summary}</p>}
      <div className="grid c3 mt">
        {section("Objetivos", r.objectives)}
        {section("Actores", r.actors)}
        {section("Funcionalidades", r.functionalities)}
        {section("Restricciones", r.constraints)}
        {section("Requisitos no funcionales", r.non_functional)}
        {section("Integraciones", r.integrations)}
        {section("Dependencias", r.dependencies)}
        {section("Ambigüedades", r.ambiguities)}
        {section("Riesgos", r.risks)}
        {section("Información faltante", r.missing_information)}
      </div>

      <hr className="divider" />
      <h3>Preguntas de aclaración</h3>
      <p className="muted">Respondé lo que esté confirmado por el negocio. Las preguntas sin respuesta no se completan con suposiciones de la IA.</p>
      {r.clarification_questions.length === 0 ? (
        <p className="muted">No hay preguntas pendientes.</p>
      ) : (
        <div className="stack" style={{ gap: 15 }}>
          {r.clarification_questions.map((qq, i) => (
            <Field key={i} label={`${i + 1}. ${qq.question}`} help={`${qq.why_it_matters} · Impacto ${qq.impact === "high" ? "alto" : qq.impact === "medium" ? "medio" : "bajo"}`}>
              {(id) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={answers[String(i)] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [String(i)]: e.target.value }))} placeholder="Respuesta confirmada (opcional)" />}
            </Field>
          ))}
        </div>
      )}
      <label className="checkbox mt">
        <input type="checkbox" checked={proceed} onChange={(e) => setProceed(e.target.checked)} />
        Continuar con supuestos explícitos para las preguntas sin responder ({unanswered})
      </label>
      <div className="row mt">
        <Button onClick={saveAnswers} loading={busy === "answers"} disabled={!dirty}>
          Guardar respuestas
        </Button>
        <Link className="btn secondary" href={`/projects/${projectId}/stories`}>
          Ir a generar el backlog
        </Link>
      </div>

      {r.suggested_requirements.length > 0 && (
        <>
          <hr className="divider" />
          <h3>Requisitos sugeridos</h3>
          <p className="muted">Elegí cuáles incorporar. Ninguno se agrega sin tu confirmación.</p>
          <ul className="list-plain">
            {r.suggested_requirements.map((s, i) => (
              <li key={i}>
                <label className="checkbox" style={{ alignItems: "flex-start" }}>
                  <input type="checkbox" checked={selected.includes(i)} onChange={(e) => setSelected((xs) => (e.target.checked ? [...xs, i] : xs.filter((x) => x !== i)))} />
                  <span>
                    <strong>{s.title}</strong> <Badge>{REQ_TYPE_LABEL[s.type] ?? s.type}</Badge> <Badge tone={PRIORITY_TONE[s.priority]}>{PRIORITY_LABEL[s.priority]}</Badge>
                    <div className="subtle">{s.description}</div>
                    {s.rationale && <div className="subtle">Motivo: {s.rationale}</div>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <Button className="mt" variant="secondary" onClick={accept} disabled={!selected.length} loading={busy === "accept"}>
            Incorporar seleccionados ({selected.length})
          </Button>
        </>
      )}
    </Card>
  );
}
