"use client";

import { Download, FileText, Paperclip, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";

import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, fmtNum } from "@/lib/format";
import type { ProjectDocument, SystemStatus } from "@/lib/types";

import { Alert, Badge, Button, Card, ConfirmDialog, IconButton, useToast } from "./ui";

const KIND: Record<string, string> = { pdf: "PDF", docx: "Word", text: "Texto" };
const STATUS: Record<string, [string, string]> = {
  pending: ["Sin procesar", ""],
  processing: ["El agente lo está leyendo", "info"],
  processed: ["Procesado", "success"],
  error: ["Error", "danger"],
};

function fmtSize(bytes: number) {
  return bytes >= 1_000_000 ? `${fmtNum(bytes / 1_000_000)} MB` : `${fmtNum(bytes / 1000, 0)} KB`;
}

/** Documentos adjuntos: el archivo se guarda tal cual y se le entrega al agente, que extrae requisitos sugeridos. */
export function DocumentsPanel({
  projectId,
  documents,
  system,
  onChanged,
}: {
  projectId: number;
  documents: ProjectDocument[];
  system: SystemStatus | null;
  onChanged: () => Promise<void>;
}) {
  const toast = useToast();
  const [working, setWorking] = useState<{ id: number | null; label: string } | null>(null);
  const [deleting, setDeleting] = useState<ProjectDocument | null>(null);
  const aiReady = !!system?.ai_available;

  const extract = async (doc: ProjectDocument) => {
    setWorking({ id: doc.id, label: `El agente está leyendo «${doc.filename}»… puede tardar 1–2 minutos.` });
    try {
      const r = await api<ProjectDocument>(`/documents/${doc.id}/extract`, { method: "POST" });
      toast(
        r.requirements_created ? "success" : "warning",
        r.requirements_created
          ? `El agente propuso ${r.requirements_created} requisitos desde «${doc.filename}». Revisalos y confirmalos.`
          : `El agente no encontró requisitos en «${doc.filename}». Mirá sus observaciones.`,
      );
    } catch (e) {
      toast("danger", `No se pudo procesar «${doc.filename}». ${errorMessage(e)}`);
    } finally {
      setWorking(null);
      await onChanged();
    }
  };

  const upload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setWorking({ id: null, label: `Adjuntando «${file.name}»…` });
    let doc: ProjectDocument | null = null;
    try {
      doc = await api<ProjectDocument>(`/projects/${projectId}/documents`, { form });
      toast("success", `«${doc.filename}» quedó adjunto al proyecto.`);
    } catch (e) {
      toast("danger", errorMessage(e));
      setWorking(null);
      return;
    }
    await onChanged();
    if (aiReady) await extract(doc);
    else setWorking(null);
  };

  const remove = async () => {
    if (!deleting) return;
    try {
      await api(`/documents/${deleting.id}`, { method: "DELETE" });
      toast("success", `Se quitó el adjunto «${deleting.filename}». Los requisitos extraídos se conservan.`);
      setDeleting(null);
      await onChanged();
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  return (
    <Card
      title="Documentos adjuntos"
      sub="El archivo se guarda tal cual y el agente lo lee para proponer requisitos. Vos los confirmás o rechazás."
      actions={
        <label className={`btn sm ${working ? "disabled" : ""}`}>
          {working && working.id === null ? <span className="spinner" aria-hidden /> : <Paperclip size={16} aria-hidden />} Adjuntar documento
          <input
            type="file"
            accept=".docx,.pdf,.txt,.text,.md,.markdown,.csv,.tsv,.log,text/*,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="sr-only"
            disabled={!!working}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void upload(f);
            }}
          />
        </label>
      }
    >
      {!aiReady && <Alert tone="info">La IA no está disponible: podés adjuntar documentos ahora y pedirle al agente que los lea cuando Claude Code tenga una sesión iniciada.</Alert>}
      {working && (
        <div className="alert info mt" role="status" aria-live="polite">
          <span className="spinner" aria-hidden />
          <div>{working.label}</div>
        </div>
      )}
      {documents.length === 0 ? (
        <p className="muted small mt">
          Adjuntá un Word (.docx), un PDF (también escaneado) o un archivo de texto plano. Hasta 10 MB.
        </p>
      ) : (
        <ul className="list-plain mt">
          {documents.map((d) => {
            const [label, tone] = STATUS[d.status] ?? [d.status, ""];
            const busyHere = working?.id === d.id;
            return (
              <li key={d.id}>
                <div className="row between" style={{ alignItems: "flex-start" }}>
                  <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", minWidth: 0 }}>
                    <FileText size={18} aria-hidden style={{ flexShrink: 0, marginTop: 2, color: "var(--primary-text)" }} />
                    <div style={{ minWidth: 0 }}>
                      <a href={`/api/v1/documents/${d.id}/download`} download={d.filename} style={{ wordBreak: "break-word" }}>
                        {d.filename}
                      </a>
                      <div className="subtle">
                        {KIND[d.kind]} · {fmtSize(d.size_bytes)} · {fmtDateTime(d.created_at)} · {d.created_by}
                      </div>
                    </div>
                  </div>
                  <div className="row" style={{ gap: 4 }}>
                    <Badge tone={busyHere ? "info" : tone}>{busyHere ? STATUS.processing[0] : label}</Badge>
                    {d.status === "processed" && <Badge tone="primary">{d.requirements_created} requisitos</Badge>}
                    {d.is_simulated && <Badge tone="warning">Simulado</Badge>}
                    <IconButton label={d.status === "pending" ? `Que el agente lea ${d.filename}` : `Volver a procesar ${d.filename}`} onClick={() => extract(d)} disabled={!!working || !aiReady}>
                      <RefreshCw size={16} />
                    </IconButton>
                    <a className="icon-btn" href={`/api/v1/documents/${d.id}/download`} download={d.filename} aria-label={`Descargar ${d.filename}`} title={`Descargar ${d.filename}`}>
                      <Download size={16} />
                    </a>
                    <IconButton label={`Quitar adjunto ${d.filename}`} onClick={() => setDeleting(d)} disabled={!!working}>
                      <Trash2 size={16} />
                    </IconButton>
                  </div>
                </div>
                {d.status === "error" && d.error && <p className="small" style={{ color: "var(--danger)", margin: "6px 0 0 28px" }}>{d.error}</p>}
                {d.status === "processed" && d.summary && (
                  <details style={{ margin: "6px 0 0 28px" }}>
                    <summary className="small muted" style={{ cursor: "pointer" }}>
                      Lo que leyó el agente{d.ai_model ? ` (${d.ai_model})` : ""}
                    </summary>
                    <p className="small" style={{ whiteSpace: "pre-line", margin: "6px 0 0" }}>{d.summary}</p>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {deleting && (
        <ConfirmDialog title="Quitar documento adjunto" danger confirmLabel="Quitar adjunto" onCancel={() => setDeleting(null)} onConfirm={remove}>
          <p>
            Vas a quitar <strong>{deleting.filename}</strong> del proyecto. Los requisitos que el agente extrajo se conservan, pero pierden el vínculo con el documento.
          </p>
        </ConfirmDialog>
      )}
    </Card>
  );
}
