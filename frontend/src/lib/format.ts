/** Formato argentino (1.234,5 · dd/mm/aaaa) y etiquetas de la interfaz. */

export function fmtNum(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("es-AR", { maximumFractionDigits: decimals, minimumFractionDigits: 0 }).format(value);
}

export function fmtHours(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${fmtNum(value)} h`;
}

export function fmtPct(value: number | null | undefined, decimals = 0, signed = false): string {
  if (value === null || value === undefined) return "—";
  const s = fmtNum(Math.abs(value), decimals);
  if (!signed) return `${value < 0 ? "-" : ""}${s} %`;
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${s} %`;
}

export function fmtMoney(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined) return "—";
  return `${currency} ${fmtNum(value, 0)}`;
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function signedDays(value: number): string {
  if (value === 0) return "sin cambios";
  return value > 0 ? `${value} días menos` : `${Math.abs(value)} días más`;
}

/** Variación porcentual del plazo frente a la línea base (misma fórmula que el backend). */
export function variationPct(baseline: number, scenario: number): number {
  if (!baseline) return 0;
  return Math.round(((scenario - baseline) / baseline) * 100 * 100) / 100;
}

export const PRIORITY_LABEL: Record<string, string> = { low: "Baja", medium: "Media", high: "Alta", critical: "Crítica" };
export const PRIORITY_TONE: Record<string, string> = { low: "", medium: "info", high: "warning", critical: "danger" };
export const CONFIDENCE_LABEL: Record<string, string> = { low: "Baja", medium: "Media", high: "Alta" };
export const CONFIDENCE_TONE: Record<string, string> = { low: "danger", medium: "warning", high: "success" };
export const REQ_TYPE_LABEL: Record<string, string> = {
  functional: "Funcional",
  non_functional: "No funcional",
  technical: "Técnico",
  security: "Seguridad",
  integration: "Integración",
  performance: "Rendimiento",
  operational: "Operativo",
};
export const REQ_STATUS_LABEL: Record<string, string> = {
  draft: "Borrador",
  confirmed: "Confirmado",
  rejected: "Rechazado",
  duplicate: "Duplicado",
  suggested: "Sugerido",
};
export const REQ_STATUS_TONE: Record<string, string> = { draft: "", confirmed: "success", rejected: "danger", duplicate: "warning", suggested: "info" };
export const PROJECT_STATUS_LABEL: Record<string, string> = { draft: "Borrador", active: "Activo", archived: "Archivado" };
export const SCENARIO_STATUS_LABEL: Record<string, string> = {
  draft: "Borrador",
  simulated: "Simulación",
  applied: "Aplicado",
  stale: "Desactualizado",
  error: "Error",
};
export const TASK_CATEGORY_LABEL: Record<string, string> = {
  analysis: "Análisis técnico",
  design: "Diseño",
  frontend: "Frontend",
  backend: "Backend",
  integration: "Integración",
  database: "Base de datos",
  security: "Seguridad",
  unit_tests: "Pruebas unitarias",
  integration_tests: "Pruebas de integración",
  qa: "QA funcional",
  documentation: "Documentación",
  deployment: "Despliegue",
};
export const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
export const CHART_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];

export function chartColor(index: number): string {
  return CHART_COLORS[index] ?? "var(--chart-other)";
}

export function slugKey(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
}

/** Devuelve un Set NUEVO con `id` agregado o quitado. Nunca muta el original (React puede llamar dos veces
 * a las funciones de actualización de estado en modo desarrollo). */
export function toggled<T>(set: Set<T>, id: T): Set<T> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}
