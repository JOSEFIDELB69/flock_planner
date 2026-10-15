"use client";

import { useState } from "react";

import { useUnsavedChanges } from "@/lib/hooks";
import { WEEKDAYS } from "@/lib/format";
import type { Project } from "@/lib/types";

import { Button, Field } from "./ui";

export type ProjectInput = {
  name: string;
  description: string;
  business_objective: string;
  owner: string;
  target_date: string | null;
  timezone: string;
  calendar_configuration: { working_days: number[]; hours_per_day: number; holidays: string[] };
  mode: "standalone" | "jira";
  currency: string;
  status?: string;
};

const EMPTY: ProjectInput = {
  name: "",
  description: "",
  business_objective: "",
  owner: "",
  target_date: null,
  timezone: "America/Argentina/Buenos_Aires",
  calendar_configuration: { working_days: [0, 1, 2, 3, 4], hours_per_day: 8, holidays: [] },
  mode: "standalone",
  currency: "USD",
};

export function ProjectForm({ initial, onSubmit, submitLabel, saving }: { initial?: Project; onSubmit: (data: ProjectInput) => Promise<boolean>; submitLabel: string; saving: boolean }) {
  const start: ProjectInput = initial
    ? {
        name: initial.name,
        description: initial.description,
        business_objective: initial.business_objective,
        owner: initial.owner,
        target_date: initial.target_date,
        timezone: initial.timezone,
        calendar_configuration: initial.calendar_configuration,
        mode: initial.mode,
        currency: initial.currency,
      }
    : EMPTY;
  const [form, setForm] = useState<ProjectInput>(start);
  const [holidaysText, setHolidaysText] = useState(start.calendar_configuration.holidays.join("\n"));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);

  const set = <K extends keyof ProjectInput>(k: K, v: ProjectInput[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setDirty(true);
  };
  const toggleDay = (d: number) => {
    const days = form.calendar_configuration.working_days;
    set("calendar_configuration", { ...form.calendar_configuration, working_days: days.includes(d) ? days.filter((x) => x !== d) : [...days, d].sort() });
  };

  const submit = async (e: React.FormEvent, status?: string) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = "Ingresá un nombre.";
    if (!form.calendar_configuration.working_days.length) errs.days = "Elegí al menos un día laborable.";
    const holidays = holidaysText
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const bad = holidays.filter((h) => !/^\d{4}-\d{2}-\d{2}$/.test(h));
    if (bad.length) errs.holidays = `Fechas inválidas: ${bad.join(", ")}. Usá el formato aaaa-mm-dd.`;
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const ok = await onSubmit({ ...form, calendar_configuration: { ...form.calendar_configuration, holidays }, ...(status ? { status } : {}) });
    if (ok) setDirty(false);
  };

  return (
    <form onSubmit={(e) => submit(e)} noValidate>
      <div className="form-grid">
        <Field label="Nombre" required error={errors.name} className="full">
          {(id) => <input id={id} className="input" value={form.name} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errors.name} maxLength={200} />}
        </Field>
        <Field label="Descripción" className="full">
          {(id) => <textarea id={id} className="textarea" value={form.description} onChange={(e) => set("description", e.target.value)} />}
        </Field>
        <Field label="Objetivo de negocio" className="full" help="Qué resultado de negocio busca el proyecto.">
          {(id) => <textarea id={id} className="textarea" value={form.business_objective} onChange={(e) => set("business_objective", e.target.value)} />}
        </Field>
        <Field label="Responsable">{(id) => <input id={id} className="input" value={form.owner} onChange={(e) => set("owner", e.target.value)} />}</Field>
        <Field label="Fecha objetivo" help="Opcional. Se compara con el fin estimado.">
          {(id) => <input id={id} type="date" className="input" value={form.target_date ?? ""} onChange={(e) => set("target_date", e.target.value || null)} />}
        </Field>
        <Field label="Zona horaria">{(id) => <input id={id} className="input" value={form.timezone} onChange={(e) => set("timezone", e.target.value)} />}</Field>
        <Field label="Moneda o unidad presupuestaria">
          {(id) => <input id={id} className="input" value={form.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} maxLength={10} />}
        </Field>
        <div className="field full">
          <span className="label">Días laborables</span>
          <div className="weekday-picker" role="group" aria-label="Días laborables">
            {WEEKDAYS.map((d, i) => (
              <button type="button" key={d} className="chip" aria-pressed={form.calendar_configuration.working_days.includes(i)} onClick={() => toggleDay(i)}>
                {d}
              </button>
            ))}
          </div>
          {errors.days && <span className="error">{errors.days}</span>}
        </div>
        <Field label="Horas de la jornada laboral" help="Jornada nominal. Las horas productivas se configuran por perfil en Equipo.">
          {(id) => (
            <input
              id={id}
              type="number"
              min={1}
              max={24}
              step={0.5}
              className="input"
              value={form.calendar_configuration.hours_per_day}
              onChange={(e) => set("calendar_configuration", { ...form.calendar_configuration, hours_per_day: Number(e.target.value) })}
            />
          )}
        </Field>
        <Field label="Modo de funcionamiento" help="El modo autónomo no requiere JIRA. Podés cambiarlo luego.">
          {(id) => (
            <select id={id} className="select" value={form.mode} onChange={(e) => set("mode", e.target.value as ProjectInput["mode"])}>
              <option value="standalone">Autónomo (sin JIRA)</option>
              <option value="jira">Integrado con JIRA Cloud (opcional)</option>
            </select>
          )}
        </Field>
        <Field label="Feriados relevantes" className="full" error={errors.holidays} help="Una fecha por línea en formato aaaa-mm-dd. Se excluyen del calendario.">
          {(id) => <textarea id={id} className="textarea" value={holidaysText} onChange={(e) => (setHolidaysText(e.target.value), setDirty(true))} placeholder={"2026-12-25\n2027-01-01"} aria-invalid={!!errors.holidays} />}
        </Field>
      </div>
      <div className="row mt">
        <Button type="submit" loading={saving}>
          {submitLabel}
        </Button>
        {!initial && (
          <Button variant="secondary" onClick={(e) => submit(e as unknown as React.FormEvent, "draft")} disabled={saving}>
            Guardar como borrador
          </Button>
        )}
      </div>
    </form>
  );
}
