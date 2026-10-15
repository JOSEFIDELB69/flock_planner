"use client";

import { Check, ExternalLink, MessageSquareWarning, Pencil, RotateCcw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, errorMessage } from "@/lib/api";
import type { BacklogObservation } from "@/lib/types";

import { Alert, Badge, Button, Card, useToast } from "./ui";

const STATUS: Record<BacklogObservation["status"], { label: string; tone: string }> = {
  pending: { label: "Pendiente", tone: "warning" },
  accepted: { label: "Aceptado", tone: "success" },
  correction: { label: "A corregir", tone: "danger" },
};

/**
 * Supuestos y advertencias de la última generación del backlog. Cada uno se acepta o se corrige;
 * las correcciones y los aceptados se envían al agente en la próxima regeneración.
 */
export function ObservationsPanel({
  projectId,
  items,
  hasUnansweredQuestions,
  onChanged,
  onRegenerate,
}: {
  projectId: number;
  items: BacklogObservation[];
  hasUnansweredQuestions: boolean;
  onChanged: (o: BacklogObservation) => void;
  onRegenerate: () => void;
}) {
  const toast = useToast();
  const [editing, setEditing] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  if (items.length === 0) return null;

  const pending = items.filter((o) => o.status === "pending").length;
  const corrections = items.filter((o) => o.status === "correction").length;
  const accepted = items.filter((o) => o.status === "accepted").length;
  const visible = showResolved ? items : items.filter((o) => o.status !== "accepted" || o.id === editing);
  const base = `/projects/${projectId}`;

  const save = async (o: BacklogObservation, status: BacklogObservation["status"], correction = "") => {
    setBusy(o.id);
    try {
      const updated = await api<BacklogObservation>(`/backlog-observations/${o.id}`, { method: "PATCH", body: { status, correction } });
      onChanged(updated);
      setEditing(null);
      setText("");
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const linkHref = (l: BacklogObservation["links"][number]) => (l.type === "requirement" ? `${base}/requirements?q=${encodeURIComponent(l.code)}` : `${base}/stories#${l.code}`);

  return (
    <Card
      title={
        <span className="row" style={{ gap: 8 }}>
          <MessageSquareWarning size={18} aria-hidden /> Observaciones de la generación
        </span>
      }
      sub="Lo que el agente tuvo que suponer o ajustar. Aceptá lo que es correcto y corregí lo que no: tus decisiones se envían al agente cuando regenerás el backlog."
      actions={
        <div className="row" style={{ gap: 6 }}>
          {pending > 0 && <Badge tone="warning">{pending} pendientes</Badge>}
          {accepted > 0 && <Badge tone="success">{accepted} aceptados</Badge>}
          {corrections > 0 && <Badge tone="danger">{corrections} a corregir</Badge>}
        </div>
      }
    >
      {corrections > 0 && (
        <Alert
          tone="info"
          title={`${corrections} ${corrections === 1 ? "corrección lista" : "correcciones listas"} para aplicar`}
          action={
            <Button size="sm" icon={<Sparkles size={14} />} onClick={onRegenerate}>
              Regenerar con correcciones
            </Button>
          }
        >
          El backlog actual todavía no las refleja. Al regenerar, el agente las recibe como información confirmada (junto con los supuestos aceptados). También podés corregir el requisito o responder las preguntas de aclaración antes.
        </Alert>
      )}
      {pending === 0 && corrections === 0 && <Alert tone="success">Revisaste todas las observaciones. El backlog queda alineado con los supuestos aceptados.</Alert>}

      <ul className="obs-list">
        {visible.map((o) => (
          <li key={o.id} className={`obs-item ${o.status}`}>
            <div className="obs-head">
              <Badge tone={o.kind === "warning" ? "" : "primary"}>{o.kind === "warning" ? "Advertencia" : "Supuesto"}</Badge>
              <Badge tone={STATUS[o.status].tone}>{STATUS[o.status].label}</Badge>
              {o.links.map((l) => (
                <Link key={l.code} className="badge" href={linkHref(l)} title={l.type === "requirement" ? "Abrir el requisito para editarlo" : "Ver en el backlog"}>
                  {l.code} <ExternalLink size={11} aria-hidden />
                </Link>
              ))}
            </div>
            <p className="obs-text">{o.text}</p>
            {o.status === "correction" && editing !== o.id && (
              <p className="obs-correction">
                <strong>Lo correcto:</strong> {o.correction}
              </p>
            )}

            {editing === o.id ? (
              <div className="obs-edit">
                <label className="small" htmlFor={`obs-${o.id}`}>
                  ¿Qué es lo correcto?
                </label>
                <textarea id={`obs-${o.id}`} className="textarea" style={{ minHeight: 70 }} value={text} maxLength={4000} autoFocus onChange={(e) => setText(e.target.value)} placeholder="Ej.: los siniestros se reciben del sistema core por una API REST; no hay carga manual." />
                <p className="subtle small" style={{ margin: "4px 0 8px" }}>
                  Si el cambio es de alcance, conviene además{" "}
                  {o.links.some((l) => l.type === "requirement") ? (
                    <>editar el requisito ({o.links.filter((l) => l.type === "requirement").map((l, i) => (
                      <span key={l.code}>{i > 0 && ", "}<Link href={linkHref(l)}>{l.code}</Link></span>
                    ))})</>
                  ) : (
                    <Link href={`${base}/requirements`}>agregar o editar el requisito</Link>
                  )}
                  {hasUnansweredQuestions && (
                    <>
                      {" "}o <Link href={`${base}/requirements#analisis`}>responder las preguntas de aclaración</Link>
                    </>
                  )}
                  .
                </p>
                <div className="row">
                  <Button size="sm" onClick={() => save(o, "correction", text)} loading={busy === o.id} disabled={!text.trim()}>
                    Guardar corrección
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => (setEditing(null), setText(""))}>
                    Cancelar
                  </Button>
                </div>
              </div>
            ) : (
              <div className="row obs-actions">
                {o.status !== "accepted" && (
                  <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => save(o, "accepted")} disabled={busy === o.id}>
                    {o.kind === "warning" ? "Entendido" : "Aceptar"}
                  </Button>
                )}
                <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => (setEditing(o.id), setText(o.correction))} disabled={busy === o.id}>
                  {o.status === "correction" ? "Editar corrección" : "Corregir"}
                </Button>
                {o.status !== "pending" && (
                  <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => save(o, "pending")} disabled={busy === o.id}>
                    Volver a pendiente
                  </Button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {items.length > visible.length || showResolved ? (
        <Button size="sm" variant="ghost" onClick={() => setShowResolved((v) => !v)}>
          {showResolved ? "Ocultar las aceptadas" : `Ver también las aceptadas (${accepted})`}
        </Button>
      ) : null}
    </Card>
  );
}
