"use client";

import { Download, Eye, PlugZap, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useProject } from "@/components/ProjectContext";
import { Alert, Badge, Button, Card, ConfirmDialog, ErrorState, Field, Loading, PageHeader, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApi, useUnsavedChanges } from "@/lib/hooks";
import type { JiraConfig, JiraIssueType, JiraPreview, JiraRemoteProject } from "@/lib/types";

type Run = { id: number; status: string; summary: Record<string, number | string>; results: { code: string; status: string; key: string | null; message: string }[]; requested_by: string; created_at: string };
type Mapping = { epic: string; story: string; task: string };
const STATUS: Record<string, [string, string]> = {
  not_configured: ["Sin configurar", ""],
  configured: ["Configurada, sin validar", "warning"],
  validated: ["Conexión validada", "success"],
  error: ["Error de conexión", "danger"],
};
const KIND_LABEL: Record<keyof Mapping, string> = { epic: "Épicas", story: "Historias", task: "Subtareas" };
const LEVEL_LABEL: Record<number, string> = { 1: "nivel épica", 0: "nivel estándar", [-1]: "subtarea" };

export default function IntegrationsPage() {
  const { project } = useProject();
  const toast = useToast();
  const cfg = useApi<JiraConfig>(`/projects/${project.id}/integrations/jira/configuration`);
  const runs = useApi<Run[]>(`/projects/${project.id}/integrations/jira/runs`);
  const [form, setForm] = useState({ enabled: false, site_url: "", account_email: "", api_token: "" });
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  // destino de la publicación: se lee del JIRA conectado, no es configuración
  const [remoteProjects, setRemoteProjects] = useState<JiraRemoteProject[] | null>(null);
  const [targetKey, setTargetKey] = useState("");
  const [issueTypes, setIssueTypes] = useState<JiraIssueType[]>([]);
  const [mapping, setMapping] = useState<Mapping>({ epic: "", story: "", task: "" });
  const [preview, setPreview] = useState<JiraPreview | null>(null);
  const [publishing, setPublishing] = useState<{ text: string } | null>(null);
  useUnsavedChanges(dirty);
  const standalone = project.mode !== "jira";

  useEffect(() => {
    if (cfg.data) setForm({ enabled: cfg.data.enabled, site_url: cfg.data.site_url, account_email: cfg.data.account_email, api_token: "" });
  }, [cfg.data]);
  const set = (k: string, v: unknown) => (setForm((f) => ({ ...f, [k]: v })), setDirty(true));

  const save = async () => {
    setBusy("save");
    try {
      const out = await api<JiraConfig>(`/projects/${project.id}/integrations/jira/configuration`, {
        method: "PUT",
        body: { enabled: form.enabled, site_url: form.site_url, account_email: form.account_email, api_token: form.api_token || null },
      });
      cfg.setData(out);
      setDirty(false);
      toast("success", "Conexión guardada. El token se guardó cifrado y no se vuelve a mostrar.");
      if (preview) await loadPreview(); // la vista previa refleja el nuevo estado sin tener que regenerarla
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setBusy("test");
    try {
      const r = await api<{ account: string; visible_projects: number }>(`/projects/${project.id}/integrations/jira/test`, { method: "POST" });
      toast("success", `Conexión validada como ${r.account}. Proyectos visibles: ${r.visible_projects}.`);
      await loadProjects();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
      await cfg.reload();
    }
  };

  const loadProjects = async () => {
    setBusy("projects");
    try {
      const list = await api<JiraRemoteProject[]>(`/projects/${project.id}/integrations/jira/remote-projects`);
      setRemoteProjects(list);
      if (!list.length) toast("warning", "La cuenta no tiene acceso a ningún proyecto de JIRA.");
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const chooseProject = async (key: string) => {
    setTargetKey(key);
    setPreview(null);
    setIssueTypes([]);
    setMapping({ epic: "", story: "", task: "" });
    if (!key) return;
    setBusy("types");
    try {
      const r = await api<{ issue_types: JiraIssueType[]; suggested_mapping: Mapping }>(`/projects/${project.id}/integrations/jira/remote-issue-types?key=${encodeURIComponent(key)}`);
      setIssueTypes(r.issue_types);
      setMapping(r.suggested_mapping);
      const missing = (Object.keys(r.suggested_mapping) as (keyof Mapping)[]).filter((k) => !r.suggested_mapping[k]);
      if (missing.length) toast("warning", `No encontramos un tipo adecuado para: ${missing.map((k) => KIND_LABEL[k].toLowerCase()).join(", ")}. Elegilo manualmente.`);
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const enableNow = async () => {
    if (!cfg.data) return;
    setBusy("enable");
    try {
      const out = await api<JiraConfig>(`/projects/${project.id}/integrations/jira/configuration`, {
        method: "PUT",
        body: { enabled: true, site_url: cfg.data.site_url, account_email: cfg.data.account_email, api_token: null },
      });
      cfg.setData(out);
      setForm((f) => ({ ...f, enabled: true, site_url: out.site_url }));
      toast("success", "Integración con JIRA habilitada para este proyecto.");
      await loadPreview();
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const loadPreview = async () => {
    setBusy("preview");
    try {
      setPreview(await api<JiraPreview>(`/projects/${project.id}/integrations/jira/preview`, { body: { project_key: targetKey, issue_type_mapping: mapping } }));
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    if (!preview || !publishing) return;
    setBusy("publish");
    try {
      const r = await api<Run>(`/projects/${project.id}/integrations/jira/publish`, {
        body: { project_key: preview.project_key, issue_type_mapping: preview.issue_type_mapping, confirm: true, confirmation_text: publishing.text, preview_fingerprint: preview.fingerprint },
      });
      toast(r.status === "completed" ? "success" : "warning", `Publicación ${r.status === "completed" ? "completa" : "parcial"} en ${preview.project_key}: ${r.summary.created} creadas, ${r.summary.skipped} omitidas, ${r.summary.errors} con error.`);
      setPublishing(null);
      await Promise.all([runs.reload(), loadPreview()]);
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const status = cfg.data ? STATUS[cfg.data.configuration_status] : null;
  const validated = cfg.data?.configuration_status === "validated";
  const chosen = remoteProjects?.find((p) => p.key === targetKey);

  return (
    <>
      <PageHeader title="Integraciones" description="La integración con JIRA Cloud es opcional y está desactivada por defecto. Flock Planner funciona completo sin ella." />
      {standalone && (
        <div style={{ marginBottom: 20 }}>
          <Alert tone="info" title="Proyecto en modo autónomo">
            Podés configurar y validar la conexión y ver la vista previa, pero no se escribe nada en JIRA. Para publicar, cambiá el modo a «Integrado» en <Link href={`/projects/${project.id}/settings`}>Configuración del proyecto</Link>.
          </Alert>
        </div>
      )}
      {cfg.loading && !cfg.data && <Loading />}
      {cfg.error && <ErrorState message={cfg.error} onRetry={cfg.reload} />}
      {cfg.data && (
        <div className="stack">
          <div className="grid c2">
            <Card title="Conexión con JIRA Cloud" sub="Solo los datos de acceso. El proyecto y los tipos de incidencia se eligen al publicar." actions={status && <Badge tone={status[1]}>{status[0]}</Badge>}>
              {!cfg.data.has_secret && !form.api_token && <p className="subtle">Necesitás un API token de Atlassian (id.atlassian.com → Seguridad → Tokens de API).</p>}
              {cfg.data.last_error && <Alert tone="danger">{cfg.data.last_error}</Alert>}
              <div className="form-grid mt">
                <label className="checkbox full">
                  <input type="checkbox" checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Habilitar integración con JIRA para este proyecto
                </label>
                <Field label="URL del sitio" className="full" help="Podés pegar cualquier URL de tu JIRA; se conserva solo el sitio (https://tuempresa.atlassian.net).">
                  {(id) => <input id={id} className="input" value={form.site_url} onChange={(e) => set("site_url", e.target.value)} placeholder="https://" />}
                </Field>
                <Field label="Email de la cuenta">{(id) => <input id={id} className="input" type="email" value={form.account_email} onChange={(e) => set("account_email", e.target.value)} autoComplete="off" />}</Field>
                <Field label="API token" help={cfg.data.has_secret ? "Hay un token guardado (cifrado). Dejalo vacío para conservarlo." : "Se guarda cifrado en el servidor y nunca se muestra."}>
                  {(id) => <input id={id} className="input" type="password" value={form.api_token} onChange={(e) => set("api_token", e.target.value)} autoComplete="new-password" placeholder={cfg.data?.has_secret ? "••••••••" : ""} />}
                </Field>
              </div>
              <div className="row mt">
                <Button onClick={save} loading={busy === "save"} disabled={!dirty}>
                  Guardar conexión
                </Button>
                <Button variant="secondary" icon={<PlugZap size={18} />} onClick={test} loading={busy === "test"} disabled={dirty || !cfg.data.has_secret}>
                  Validar conexión
                </Button>
              </div>
              {cfg.data.last_validated_at && <p className="subtle mt">Última validación: {fmtDateTime(cfg.data.last_validated_at)}</p>}
            </Card>
            <Card title="Cómo protege Flock Planner tu JIRA">
              <ul className="ac-list" style={{ color: "var(--ink)" }}>
                <li>Nada se publica automáticamente al generar el plan.</li>
                <li>Los proyectos y tipos de incidencia se leen del JIRA conectado; antes de publicar se verifica que existan.</li>
                <li>Siempre hay vista previa y confirmación explícita (escribís la clave del proyecto destino).</li>
                <li>Si el backlog o el destino cambian después de la vista previa, la publicación se rechaza.</li>
                <li>Los elementos ya publicados se omiten al reintentar: no se crean duplicados.</li>
                <li>El token se guarda cifrado y no aparece en registros ni respuestas.</li>
              </ul>
            </Card>
          </div>

          <Card title="Publicar en JIRA" sub="1. Elegí el proyecto destino · 2. Revisá los tipos detectados · 3. Generá la vista previa · 4. Confirmá">
            {!validated ? (
              <p className="muted">Validá la conexión para cargar los proyectos de tu JIRA.</p>
            ) : (
              <>
                <div className="form-grid">
                  <Field label="Proyecto de JIRA destino" help={chosen ? `${chosen.type === "software" ? "Software" : chosen.type}${chosen.style === "next-gen" ? " · gestionado por el equipo" : chosen.style === "classic" ? " · gestionado por la empresa" : ""}` : "Lista leída de tu JIRA."}>
                    {(id) =>
                      remoteProjects ? (
                        <select id={id} className="select" value={targetKey} onChange={(e) => chooseProject(e.target.value)} disabled={busy === "types"}>
                          <option value="">Elegí un proyecto…</option>
                          {remoteProjects.map((p) => (
                            <option key={p.key} value={p.key}>
                              {p.key} · {p.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <Button aria-label="Cargar proyectos de JIRA" variant="secondary" icon={<Download size={16} />} onClick={loadProjects} loading={busy === "projects"}>
                          Cargar proyectos de JIRA
                        </Button>
                      )
                    }
                  </Field>
                  {busy === "types" && <Loading label="Leyendo tipos de incidencia…" />}
                </div>
                {targetKey && issueTypes.length > 0 && (
                  <>
                    <h4 className="mt" style={{ marginBottom: 6 }}>
                      Tipos de incidencia en {targetKey}
                    </h4>
                    <p className="subtle" style={{ marginTop: 0 }}>
                      Sugeridos según la jerarquía de JIRA. Podés cambiarlos entre los tipos que existen en el proyecto.
                    </p>
                    <div className="form-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
                      {(Object.keys(KIND_LABEL) as (keyof Mapping)[]).map((k) => (
                        <Field key={k} label={KIND_LABEL[k]}>
                          {(id) => (
                            <select id={id} className="select" value={mapping[k]} onChange={(e) => (setMapping((m) => ({ ...m, [k]: e.target.value })), setPreview(null))}>
                              <option value="">Elegí un tipo…</option>
                              {issueTypes.map((t) => (
                                <option key={t.id + t.name} value={t.name}>
                                  {t.name} ({LEVEL_LABEL[t.hierarchy_level] ?? `nivel ${t.hierarchy_level}`})
                                </option>
                              ))}
                            </select>
                          )}
                        </Field>
                      ))}
                    </div>
                    <div className="row mt">
                      <Button variant="secondary" icon={<Eye size={18} />} onClick={loadPreview} loading={busy === "preview"} disabled={!mapping.epic || !mapping.story || !mapping.task}>
                        Generar vista previa
                      </Button>
                      <span className="subtle">La vista previa no escribe nada en JIRA.</span>
                    </div>
                  </>
                )}
              </>
            )}

            {preview && (
              <>
                <hr className="divider" />
                <div className="row">
                  <strong>Destino: {preview.project_key}</strong>
                  <Badge tone="info">{preview.counts.epic} épicas</Badge>
                  <Badge tone="info">{preview.counts.story} historias</Badge>
                  <Badge tone="info">{preview.counts.task} subtareas</Badge>
                  <Badge>{preview.already_published} ya publicadas (se omiten)</Badge>
                </div>
                {preview.remote_duplicates.length > 0 && (
                  <Alert tone="warning" title="Posibles duplicados en JIRA">
                    Hay incidencias con la etiqueta de este proyecto que no están vinculadas localmente: {preview.remote_duplicates.map((d) => d.key).join(", ")}.
                  </Alert>
                )}
                <div className="table-wrap mt" style={{ maxHeight: 420, overflowY: "auto" }}>
                  <table className="table compact">
                    <thead>
                      <tr>
                        <th>Tipo en JIRA</th>
                        <th>Código</th>
                        <th>Resumen</th>
                        <th>Padre</th>
                        <th className="num">Horas</th>
                        <th>JIRA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.items.map((i) => (
                        <tr key={`${i.local_type}${i.local_id}`}>
                          <td>{preview.issue_type_mapping[i.local_type]}</td>
                          <td className="mono">{i.code}</td>
                          <td title={i.description}>{i.summary}</td>
                          <td className="mono">{i.parent_code ?? "—"}</td>
                          <td className="num">{i.estimated_hours ?? "—"}</td>
                          <td>{i.existing_key ? <Badge tone="success">{i.existing_key}</Badge> : <Badge>Se creará</Badge>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="row mt">
                  <Button variant="brand" icon={<Send size={18} />} disabled={!preview.can_publish || Object.values(preview.counts).every((n) => n === 0)} onClick={() => setPublishing({ text: "" })}>
                    Publicar en JIRA
                  </Button>
                </div>
                {!preview.can_publish && (
                  <div className="mt">
                    <strong className="small">Para habilitar la publicación falta:</strong>
                    <ul className="list-plain small">
                      {[
                        { ok: !standalone, text: "Proyecto en modo integrado", fix: <Link href={`/projects/${project.id}/settings`}>Cambiar en Configuración del proyecto</Link> },
                        {
                          ok: cfg.data.enabled,
                          text: "Integración habilitada",
                          fix: (
                            <Button size="sm" variant="secondary" onClick={enableNow} loading={busy === "enable"}>
                              Habilitar integración
                            </Button>
                          ),
                        },
                        { ok: validated, text: "Conexión validada", fix: "Tocá «Validar conexión»" },
                        { ok: preview.pending_fields.length === 0, text: "Destino y tipos de incidencia válidos", fix: preview.pending_fields.join(" · ") },
                      ].map((c) => (
                        <li key={c.text} className="row" style={{ flexWrap: "nowrap" }}>
                          <Badge tone={c.ok ? "success" : "danger"}>{c.ok ? "✓ Listo" : "✗ Falta"}</Badge>
                          <span>{c.text}</span>
                          {!c.ok && <span className="subtle">· {c.fix}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </Card>

          {runs.data && runs.data.length > 0 && (
            <Card title="Registro de publicaciones">
              <ul className="list-plain">
                {runs.data.map((r) => (
                  <li key={r.id}>
                    <div className="row between">
                      <span>
                        <Badge tone={r.status === "completed" ? "success" : r.status === "partial" ? "warning" : "danger"}>{r.status === "completed" ? "Completa" : r.status === "partial" ? "Parcial" : "Fallida"}</Badge> {r.summary.project_key ? `${r.summary.project_key} · ` : ""}
                        {r.summary.created} creadas · {r.summary.skipped} omitidas · {r.summary.errors} errores
                      </span>
                      <span className="subtle">
                        {fmtDateTime(r.created_at)} · {r.requested_by}
                      </span>
                    </div>
                    {r.results.filter((x) => x.status === "error").length > 0 && (
                      <ul className="ac-list">
                        {r.results
                          .filter((x) => x.status === "error")
                          .map((x) => (
                            <li key={x.code}>
                              {x.code}: {x.message}
                            </li>
                          ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
      {publishing && preview && (
        <ConfirmDialog
          title="Confirmar publicación en JIRA"
          confirmLabel="Publicar incidencias"
          danger
          loading={busy === "publish"}
          confirmDisabled={publishing.text.trim().toUpperCase() !== preview.project_key}
          onCancel={() => setPublishing(null)}
          onConfirm={publish}
        >
          <p>
            Se crearán <strong>{preview.counts.epic + preview.counts.story + preview.counts.task}</strong> incidencias en el proyecto <strong>{preview.project_key}</strong> ({preview.issue_type_mapping.epic} / {preview.issue_type_mapping.story} / {preview.issue_type_mapping.task}). Esta acción escribe en un sistema externo.
          </p>
          <Field label={`Escribí ${preview.project_key} para confirmar`}>{(id) => <input id={id} className="input" value={publishing.text} onChange={(e) => setPublishing({ text: e.target.value })} autoComplete="off" />}</Field>
        </ConfirmDialog>
      )}
    </>
  );
}
