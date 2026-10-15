"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

const FEATURES = [
  ["Lee tus documentos", "adjuntás un Word, PDF o texto plano; queda guardado tal cual y el agente propone los requisitos que encuentra."],
  ["Analiza requisitos con IA (Claude Code)", "detecta actores, ambigüedades, riesgos e información faltante, y hace preguntas de aclaración."],
  ["Genera el backlog", "épicas, historias con criterios Dado/Cuando/Entonces y subtareas por perfil con horas. Todo es editable. Los supuestos del agente quedan para que los aceptes o corrijas."],
  ["Planifica con un motor determinista", "calcula fechas respetando dependencias, capacidad real, seniority (SR/SSR/JR), calendario, feriados y ausencias; identifica el camino crítico y los cuellos de botella."],
  ["Estima con probabilidad (Monte Carlo)", "cada tarea tiene un rango optimista–estimado–pesimista; el motor simula el plan 500 veces y te dice con qué probabilidad se cumple cada fecha (P50, P80, P90) y qué reserva por imprevistos hace falta."],
  ["Guarda una línea base inmutable", "y lleva el historial de versiones."],
  ["Optimiza", "simula alternativas de equipo y una reserva por imprevistos, y compara plazo, coste y riesgos contra la línea base."],
  ["Exporta PDF profesionales", "informe completo, ejecutivo y de optimización, con la marca Flock."],
  ["Publica en JIRA (opcional)", "solo después de una vista previa y tu confirmación explícita."],
];

type Step = { title: string; slug: string | null; text: string };
const STEPS: Step[] = [
  { title: "Crear el proyecto", slug: null, text: "En Proyectos → Nuevo proyecto: nombre, objetivo, responsable, fecha objetivo, días laborables y feriados. Arranca con 1 Frontend, 1 Backend y 1 QA." },
  { title: "Cargar requisitos", slug: "requirements", text: "En Requisitos/Requerimientos: «Adjuntar documento» (Word, PDF o texto plano; el agente lo lee y propone requisitos «sugeridos»), «Pegar texto» con viñetas o «Nuevo requisito». Confirmá o rechazá los sugeridos, de a uno o seleccionando varios." },
  { title: "Analizar con IA", slug: "requirements", text: "Botón «Analizar con IA». Respondé las preguntas de aclaración (o continuá con supuestos explícitos) y guardá. Elegí qué requisitos sugeridos incorporar." },
  { title: "Generar el backlog", slug: "stories", text: "En Épicas e historias → «Generar backlog con IA». Revisá, editá, agregá o borrá épicas, historias y subtareas; ajustá dependencias." },
  { title: "Revisar las observaciones", slug: "stories", text: "En «Observaciones de la generación», aceptá cada supuesto correcto o corregilo indicando qué es lo correcto (con enlace al requisito). Después «Regenerar con correcciones»: el agente recibe tus decisiones como información confirmada." },
  { title: "Revisar estimaciones", slug: "estimates", text: "Ajustá las horas por subtarea y, si querés, su rango optimista / pesimista (vacío = según la confianza de la historia). Lo que cambiás queda como «revisado»." },
  { title: "Configurar el equipo", slug: "team", text: "Perfiles, cantidad, seniority (cuántos SR, SSR y JR en desarrollo y QA), horas productivas por día, dedicación, tarifas (para costes), vacaciones y ausencias." },
  { title: "Planificar", slug: "planning", text: "Ajustá los parámetros (revisión, retrabajo, reserva por imprevistos, el % de tiempo por seniority —por defecto SR −15 %, JR +30 %— y los rangos de incertidumbre por confianza), «Calcular vista previa», revisá cronograma, cuellos de botella y la «Probabilidad de cumplimiento» (simulación Monte Carlo: conviene comprometer la fecha P80), y «Confirmar como línea base»." },
  { title: "Optimizar", slug: "optimization", text: "Sugerir escenarios, Nuevo escenario (equipo, seniority, reserva por imprevistos) o Reserva por imprevistos. Compará y, si uno te convence, aplicalo (▶): se crea una versión nueva y la línea base se conserva." },
  { title: "Exportar", slug: "reports", text: "Elegí la versión y generá el PDF completo, ejecutivo o de optimización." },
  { title: "Publicar en JIRA (opcional)", slug: "integrations", text: "Pasá el proyecto a modo integrado, cargá URL, email y token, validá la conexión, elegí el proyecto destino (los tipos se detectan solos), generá la vista previa y publicá escribiendo la clave." },
];

export function HelpPanel({ open, onClose, projectId }: { open: boolean; onClose: () => void; projectId: string | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>(".icon-btn")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  const href = (s: Step) => (s.slug === null ? "/projects/new" : projectId ? `/projects/${projectId}/${s.slug}` : null);

  return (
    <div className="overlay drawer-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside id="help-panel" className="drawer" role="dialog" aria-modal="true" aria-labelledby="help-title" ref={ref}>
        <div className="modal-head">
          <h2 id="help-title">Ayuda · Flock Planner</h2>
          <button type="button" className="icon-btn" aria-label="Cerrar ayuda" title="Cerrar ayuda" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">
          <h3>Qué hace</h3>
          <p className="muted">
            Convierte requisitos de negocio en un <strong>plan de desarrollo estimado, calendarizado y comparable</strong>, listo para presentar en PDF y, si querés, publicar en JIRA.
          </p>
          <ul className="help-list">
            {FEATURES.map(([t, d]) => (
              <li key={t}>
                <strong>{t}:</strong> {d}
              </li>
            ))}
          </ul>
          <p className="help-note">La IA propone y explica; las fechas y cifras salen siempre del motor de planificación.</p>
          <h3 className="mt">Cómo se estima</h3>
          <ul className="help-list small">
            <li><strong>Horas base:</strong> el agente divide cada historia en subtareas de 2 a 24 h y estima el esfuerzo neto de una persona, con un rango optimista–pesimista y una confianza por historia. Vos las revisás en Estimaciones.</li>
            <li><strong>Plazo:</strong> el motor suma revisión y retrabajo, aplica seniority, capacidad, coordinación, dependencias y calendario. Mismos datos → mismo resultado.</li>
            <li><strong>Probabilidad (Monte Carlo):</strong> el motor recalcula el plan 500 veces sorteando las horas de cada tarea dentro de su rango (distribución triangular, con correlación entre tareas porque los desvíos suelen ir en el mismo sentido). Así obtenés la fecha con 50, 80 y 90 % de confianza y la probabilidad de cumplir la fecha del plan y la fecha objetivo. Semilla fija: el resultado es reproducible.</li>
          </ul>

          <h3 className="mt">Pasos para usarla</h3>
          <p className="subtle">Las opciones del proyecto están en la barra lateral, dentro de «Proyecto activo». Desde cualquier solapa, «← Volver al proyecto» te lleva a su resumen.{!projectId && " Entrá a un proyecto para que los pasos te lleven directo a cada sección."}</p>
          <ol className="help-steps">
            {STEPS.map((s, i) => {
              const link = href(s);
              return (
                <li key={s.title}>
                  <span className="n" aria-hidden>
                    {i + 1}
                  </span>
                  <div>
                    {link ? (
                      <Link href={link} onClick={onClose}>
                        <strong>{s.title}</strong>
                      </Link>
                    ) : (
                      <strong>{s.title}</strong>
                    )}
                    <div className="small muted">{s.text}</div>
                  </div>
                </li>
              );
            })}
          </ol>
          <p className="small muted">
            Además: <strong>Versiones</strong> muestra el historial, compara y restaura versiones, con auditoría de cambios. El <strong>Dashboard</strong> resume todos los proyectos. En <strong>Proyectos</strong> y en <strong>Requisitos/Requerimientos</strong> podés eliminar de a uno o seleccionar varios (o todos) y eliminarlos juntos, con confirmación.
          </p>

          <h3 className="mt">Para que funcione</h3>
          <ul className="help-list small">
            <li>El backend y el frontend tienen que estar en ejecución.</li>
            <li>La IA necesita la CLI de Claude Code con una sesión iniciada. Cada operación de IA tarda 1–2 minutos.</li>
            <li>Sin IA, todo lo demás funciona cargando requisitos y backlog a mano.</li>
            <li>Si no ves un cambio reciente de la aplicación, recargá con Ctrl + F5.</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
