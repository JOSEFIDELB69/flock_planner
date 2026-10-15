"use client";

import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Fragment, useState } from "react";

import { fmtNum, slugKey } from "@/lib/format";
import type { MemberAvailability, SeniorityLevel, SeniorityMix, TeamProfile } from "@/lib/types";

import { SENIORITY_LABELS, SENIORITY_LEVELS, SENIORITY_NAMES, seniorityApplies } from "./SeniorityFactors";
import { Button, IconButton } from "./ui";

export const CATALOG: Omit<TeamProfile, "quantity" | "available_hours_per_day" | "dedication_percentage" | "hourly_rate" | "availability_configuration">[] = [
  { profile_key: "frontend", profile_name: "Desarrollador Frontend", is_qa: false },
  { profile_key: "backend", profile_name: "Desarrollador Backend", is_qa: false },
  { profile_key: "qa", profile_name: "QA Engineer", is_qa: true },
  { profile_key: "devops", profile_name: "DevOps", is_qa: false },
  { profile_key: "uxui", profile_name: "Diseñador UX/UI", is_qa: false },
  { profile_key: "architect", profile_name: "Arquitecto de software", is_qa: false },
  { profile_key: "security", profile_name: "Especialista en seguridad", is_qa: false },
  { profile_key: "data", profile_name: "Data Engineer", is_qa: false },
];

const EMPTY_MIX: SeniorityMix = { sr: 0, ssr: 0, jr: 0 };

/** Seniority de cada persona del perfil: primero los SR, luego los SSR y luego los JR (igual que el motor). */
export function memberSeniorities(p: TeamProfile): (SeniorityLevel | null)[] {
  const mix = p.availability_configuration?.seniority ?? EMPTY_MIX;
  const out: (SeniorityLevel | null)[] = SENIORITY_LEVELS.flatMap((k) => Array<SeniorityLevel>(Math.max(0, mix[k] ?? 0)).fill(k)).slice(0, p.quantity);
  return [...out, ...Array<null>(Math.max(0, p.quantity - out.length)).fill(null)];
}

/** Si baja la cantidad, recorta la seniority empezando por JR, luego SSR y luego SR. */
function fitMix(mix: SeniorityMix | null | undefined, quantity: number): SeniorityMix | null {
  if (!mix) return null;
  const out = { ...mix };
  let excess = out.sr + out.ssr + out.jr - quantity;
  for (const k of ["jr", "ssr", "sr"] as SeniorityLevel[]) {
    const cut = Math.min(out[k], Math.max(0, excess));
    out[k] -= cut;
    excess -= cut;
  }
  return out;
}

export function newProfile(key: string, name: string, isQa = false): TeamProfile {
  return { profile_key: key, profile_name: name, quantity: 1, available_hours_per_day: 6, dedication_percentage: 100, hourly_rate: null, is_qa: isQa, availability_configuration: { members: [] } };
}

/** Editor de perfiles y capacidades. Se usa en Equipo y en los escenarios de optimización. */
export function TeamEditor({ team, onChange, compact }: { team: TeamProfile[]; onChange: (t: TeamProfile[]) => void; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const [custom, setCustom] = useState("");
  const update = (key: string, patch: Partial<TeamProfile>) => onChange(team.map((p) => (p.profile_key === key ? { ...p, ...patch } : p)));
  const members = (p: TeamProfile): MemberAvailability[] => p.availability_configuration?.members ?? [];
  const setMembers = (p: TeamProfile, ms: MemberAvailability[]) => update(p.profile_key, { availability_configuration: { ...p.availability_configuration, members: ms } });
  const setQuantity = (p: TeamProfile, quantity: number) =>
    update(p.profile_key, { quantity, availability_configuration: { ...p.availability_configuration, seniority: fitMix(p.availability_configuration?.seniority, quantity) } });
  const setMix = (p: TeamProfile, level: SeniorityLevel, n: number) => {
    const mix = { ...EMPTY_MIX, ...(p.availability_configuration?.seniority ?? {}) };
    const others = mix.sr + mix.ssr + mix.jr - mix[level];
    mix[level] = Math.max(0, Math.min(p.quantity - others, Math.round(n || 0)));
    update(p.profile_key, { availability_configuration: { ...p.availability_configuration, seniority: mix } });
  };
  const available = CATALOG.filter((c) => !team.some((p) => p.profile_key === c.profile_key));

  return (
    <div>
      <div className="table-wrap">
        <table className="table compact">
          <thead>
            <tr>
              <th>Perfil</th>
              <th className="num">Cantidad</th>
              <th title="Cuántas personas del perfil son Senior, Semi senior y Junior">Seniority (SR / SSR / JR)</th>
              <th className="num">Horas productivas/día</th>
              <th className="num">Dedicación %</th>
              {!compact && <th className="num">Tarifa/hora</th>}
              <th>QA</th>
              <th className="num">Capacidad nominal/día</th>
              <th>
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {team.map((p) => (
              <Fragment key={p.profile_key}>
                <tr>
                  <td>
                    <button className="disclosure" aria-expanded={open === p.profile_key} aria-label={`Disponibilidad individual de ${p.profile_name}`} onClick={() => setOpen(open === p.profile_key ? null : p.profile_key)}>
                      {open === p.profile_key ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </button>{" "}
                    <input className="input sm" style={{ width: 200 }} value={p.profile_name} aria-label="Nombre del perfil" onChange={(e) => update(p.profile_key, { profile_name: e.target.value })} />
                    <div className="subtle mono" style={{ marginLeft: 28 }}>
                      {p.profile_key}
                    </div>
                  </td>
                  <td className="num">
                    <input className="input sm" style={{ width: 70 }} type="number" min={0} max={100} value={p.quantity} aria-label={`Cantidad de ${p.profile_name}`} onChange={(e) => setQuantity(p, Math.max(0, Math.round(Number(e.target.value))))} />
                  </td>
                  <td>
                    {seniorityApplies(p) ? (
                      <div className="seniority-mix">
                        {SENIORITY_LEVELS.map((k) => (
                          <label key={k} title={SENIORITY_NAMES[k]}>
                            <span>{SENIORITY_LABELS[k]}</span>
                            <input className="input sm" type="number" min={0} max={p.quantity} value={p.availability_configuration?.seniority?.[k] ?? 0} aria-label={`${SENIORITY_NAMES[k]} en ${p.profile_name}`} onChange={(e) => setMix(p, k, Number(e.target.value))} />
                          </label>
                        ))}
                      </div>
                    ) : (
                      <span className="subtle">—</span>
                    )}
                  </td>
                  <td className="num">
                    <input className="input sm" style={{ width: 80 }} type="number" min={0.5} max={24} step={0.5} value={p.available_hours_per_day} aria-label={`Horas productivas de ${p.profile_name}`} onChange={(e) => update(p.profile_key, { available_hours_per_day: Number(e.target.value) })} />
                  </td>
                  <td className="num">
                    <input className="input sm" style={{ width: 80 }} type="number" min={1} max={100} value={p.dedication_percentage} aria-label={`Dedicación de ${p.profile_name}`} onChange={(e) => update(p.profile_key, { dedication_percentage: Number(e.target.value) })} />
                  </td>
                  {!compact && (
                    <td className="num">
                      <input className="input sm" style={{ width: 90 }} type="number" min={0} step={1} value={p.hourly_rate ?? ""} placeholder="—" aria-label={`Tarifa de ${p.profile_name}`} onChange={(e) => update(p.profile_key, { hourly_rate: e.target.value === "" ? null : Number(e.target.value) })} />
                    </td>
                  )}
                  <td>
                    <input type="checkbox" checked={p.is_qa} aria-label={`${p.profile_name} es QA`} onChange={(e) => update(p.profile_key, { is_qa: e.target.checked })} />
                  </td>
                  <td className="num">{fmtNum(p.quantity * p.available_hours_per_day * (p.dedication_percentage / 100))} h</td>
                  <td>
                    <IconButton label={`Quitar ${p.profile_name}`} onClick={() => onChange(team.filter((x) => x.profile_key !== p.profile_key))}>
                      <Trash2 size={16} />
                    </IconButton>
                  </td>
                </tr>
                {open === p.profile_key && (
                  <tr>
                    <td colSpan={compact ? 8 : 9} style={{ background: "var(--surface-subtle)" }}>
                      <p className="small muted">Disponibilidad individual (opcional). Sin datos, cada persona usa los valores del perfil al 100 %. Las ausencias excluyen esos días.</p>
                      {Array.from({ length: p.quantity }, (_, i) => {
                        const m = members(p)[i] ?? { name: "", availability_percentage: 100, hours_per_day: null, absences: [] };
                        const setM = (patch: Partial<MemberAvailability>) => {
                          const ms = Array.from({ length: p.quantity }, (_, j) => members(p)[j] ?? { name: "", availability_percentage: 100, hours_per_day: null, absences: [] });
                          ms[i] = { ...m, ...patch };
                          setMembers(p, ms);
                        };
                        const level = seniorityApplies(p) ? memberSeniorities(p)[i] : null;
                        return (
                          <div key={i} className="row" style={{ marginBottom: 8, alignItems: "flex-start" }}>
                            {seniorityApplies(p) && (
                              <span className={`badge ${level ? "primary" : ""}`} style={{ minWidth: 44, justifyContent: "center", marginTop: 6 }} title={level ? SENIORITY_NAMES[level] : "Sin seniority definida: sin ajuste de tiempo"}>
                                {level ? SENIORITY_LABELS[level] : "—"}
                              </span>
                            )}
                            <input className="input sm" style={{ width: 180 }} placeholder={`${p.profile_name} ${i + 1}`} value={m.name} aria-label={`Nombre persona ${i + 1}`} onChange={(e) => setM({ name: e.target.value })} />
                            <label className="small">
                              Disponibilidad %{" "}
                              <input className="input sm" style={{ width: 70 }} type="number" min={0} max={100} value={m.availability_percentage} onChange={(e) => setM({ availability_percentage: Number(e.target.value) })} />
                            </label>
                            <label className="small">
                              Horas/día propias{" "}
                              <input className="input sm" style={{ width: 70 }} type="number" min={0.5} max={24} step={0.5} placeholder="perfil" value={m.hours_per_day ?? ""} onChange={(e) => setM({ hours_per_day: e.target.value === "" ? null : Number(e.target.value) })} />
                            </label>
                            <div className="stack" style={{ gap: 4 }}>
                              {m.absences.map((a, ai) => (
                                <div key={ai} className="row small">
                                  Ausencia
                                  <input className="input sm" type="date" value={a.start} aria-label="Desde" onChange={(e) => setM({ absences: m.absences.map((x, k) => (k === ai ? { ...x, start: e.target.value } : x)) })} />
                                  a
                                  <input className="input sm" type="date" value={a.end} aria-label="Hasta" onChange={(e) => setM({ absences: m.absences.map((x, k) => (k === ai ? { ...x, end: e.target.value } : x)) })} />
                                  <IconButton label="Quitar ausencia" onClick={() => setM({ absences: m.absences.filter((_, k) => k !== ai) })}>
                                    <Trash2 size={14} />
                                  </IconButton>
                                </div>
                              ))}
                              <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => setM({ absences: [...m.absences, { start: "", end: "" }] })}>
                                Ausencia o vacaciones
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row mt">
        {available.length > 0 && (
          <select
            className="select sm"
            style={{ width: 240 }}
            value=""
            aria-label="Agregar perfil del catálogo"
            onChange={(e) => {
              const c = CATALOG.find((x) => x.profile_key === e.target.value);
              if (c) onChange([...team, newProfile(c.profile_key, c.profile_name, c.is_qa)]);
            }}
          >
            <option value="">Agregar perfil del catálogo…</option>
            {available.map((c) => (
              <option key={c.profile_key} value={c.profile_key}>
                {c.profile_name}
              </option>
            ))}
          </select>
        )}
        <input className="input sm" style={{ width: 220 }} placeholder="Otro perfil (nombre)" value={custom} onChange={(e) => setCustom(e.target.value)} aria-label="Nombre de perfil personalizado" />
        <Button
          size="sm"
          variant="secondary"
          icon={<Plus size={14} />}
          disabled={!custom.trim() || team.some((p) => p.profile_key === slugKey(custom))}
          onClick={() => {
            onChange([...team, newProfile(slugKey(custom), custom.trim())]);
            setCustom("");
          }}
        >
          Agregar
        </Button>
      </div>
    </div>
  );
}

/** Limpia ausencias incompletas antes de enviar al backend. */
export function cleanTeam(team: TeamProfile[]): TeamProfile[] {
  return team.map((p) => ({
    profile_key: p.profile_key,
    profile_name: p.profile_name,
    quantity: p.quantity,
    available_hours_per_day: p.available_hours_per_day,
    dedication_percentage: p.dedication_percentage,
    hourly_rate: p.hourly_rate,
    is_qa: p.is_qa,
    availability_configuration: {
      members: (p.availability_configuration?.members ?? []).slice(0, p.quantity).map((m) => ({ ...m, absences: m.absences.filter((a) => a.start && a.end) })),
      seniority: seniorityApplies(p) ? fitMix(p.availability_configuration?.seniority, p.quantity) : null,
    },
  }));
}
