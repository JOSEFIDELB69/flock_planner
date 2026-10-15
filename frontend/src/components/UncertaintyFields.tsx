"use client";

import type { Confidence, Uncertainty } from "@/lib/types";

export const DEFAULT_UNCERTAINTY: Uncertainty = { high: [-10, 25], medium: [-15, 50], low: [-25, 100] };
const LABEL: Record<Confidence, string> = { high: "Confianza alta", medium: "Confianza media", low: "Confianza baja" };

/** Rango optimista/pesimista (%) que usa la simulación Monte Carlo para las tareas sin rango propio. */
export function UncertaintyFields({ value, onChange }: { value: Uncertainty; onChange: (v: Uncertainty) => void }) {
  const set = (k: Confidence, i: 0 | 1, n: number) => {
    const r: [number, number] = [...value[k]];
    r[i] = i === 0 ? Math.max(-95, Math.min(0, n)) : Math.max(0, Math.min(500, n));
    onChange({ ...value, [k]: r });
  };
  return (
    <fieldset className="full seniority-factors">
      <legend>Rangos de incertidumbre para el pronóstico (%)</legend>
      <div className="row">
        {(["high", "medium", "low"] as Confidence[]).map((k) => (
          <div key={k} className="small uncertainty-row">
            <strong>{LABEL[k]}</strong>{" "}
            <input className="input sm" style={{ width: 70 }} type="number" min={-95} max={0} value={value[k][0]} aria-label={`${LABEL[k]}: optimista %`} onChange={(e) => set(k, 0, Number(e.target.value))} />
            {" / +"}
            <input className="input sm" style={{ width: 70 }} type="number" min={0} max={500} value={value[k][1]} aria-label={`${LABEL[k]}: pesimista %`} onChange={(e) => set(k, 1, Number(e.target.value))} />
          </div>
        ))}
      </div>
      <span className="help">
        La probabilidad de cumplimiento se calcula simulando el plan 500 veces (Monte Carlo). Las tareas sin rango propio varían entre estos porcentajes según la confianza de su historia. Ej.: confianza baja −25 / +100 → una tarea de 10 h puede llevar entre 7,5 y 20 h.
      </span>
    </fieldset>
  );
}
