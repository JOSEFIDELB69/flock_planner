"use client";

import type { SeniorityLevel, SeniorityMix } from "@/lib/types";

export const SENIORITY_LEVELS: SeniorityLevel[] = ["sr", "ssr", "jr"];
export const SENIORITY_LABELS: Record<SeniorityLevel, string> = { sr: "SR", ssr: "SSR", jr: "JR" };
export const SENIORITY_NAMES: Record<SeniorityLevel, string> = { sr: "Senior", ssr: "Semi senior", jr: "Junior" };
export const DEFAULT_SENIORITY_FACTORS: SeniorityMix = { sr: -15, ssr: 0, jr: 30 };

/** La seniority aplica a los perfiles de desarrollo y QA (no a UX/UI, arquitectura ni seguridad). */
const NON_DEV = ["uxui", "architect", "security"];
export const seniorityApplies = (p: { profile_key: string; is_qa: boolean }) => p.is_qa || !NON_DEV.includes(p.profile_key);

export const signedPct = (v: number) => (v > 0 ? `+${v} %` : v < 0 ? `${v} %` : "sin ajuste");

/** Campos para configurar cuánto cambia el tiempo de trabajo según la seniority. */
export function SeniorityFactorsFields({ value, onChange }: { value: SeniorityMix; onChange: (v: SeniorityMix) => void }) {
  return (
    <fieldset className="full seniority-factors">
      <legend>Ajuste del tiempo de trabajo por seniority (%)</legend>
      <div className="row">
        {SENIORITY_LEVELS.map((k) => (
          <label key={k} className="small">
            {SENIORITY_NAMES[k]} ({SENIORITY_LABELS[k]}){" "}
            <input
              className="input sm"
              style={{ width: 80 }}
              type="number"
              min={-80}
              max={300}
              step={1}
              value={value[k]}
              aria-label={`Ajuste de tiempo ${SENIORITY_NAMES[k]}`}
              onChange={(e) => onChange({ ...value, [k]: Math.max(-80, Math.min(300, Number(e.target.value))) })}
            />
          </label>
        ))}
      </div>
      <span className="help">
        Se aplica a las tareas de cada persona de desarrollo y QA según su seniority (se define en Equipo). Positivo = tarda más; negativo = tarda menos. Ej.: JR +30 % → una tarea de 10 h le lleva 13 h. Las personas sin seniority no tienen ajuste.
      </span>
    </fieldset>
  );
}
