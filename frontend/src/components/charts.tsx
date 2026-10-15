"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtNum } from "@/lib/format";

const VARS = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-other", "--border", "--ink-subtle", "--ink", "--surface-raised", "--accent"];

/** Resuelve los tokens CSS a colores concretos (los atributos SVG no admiten var()). */
function useTokens() {
  const [t, setT] = useState<Record<string, string>>({});
  useEffect(() => {
    const read = () => {
      const cs = getComputedStyle(document.documentElement);
      setT(Object.fromEntries(VARS.map((v) => [v, cs.getPropertyValue(v).trim()])));
    };
    read();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, []);
  return t;
}

function series(t: Record<string, string>, i: number) {
  return i < 4 ? t[`--chart-${i + 1}`] : t["--chart-other"];
}

/** Agrupa a partir de la quinta serie en "Otros" (regla de la paleta). */
function groupOthers<T extends { name: string; value: number }>(rows: T[]): { name: string; value: number }[] {
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  if (sorted.length <= 5) return sorted;
  const head = sorted.slice(0, 4);
  const rest = sorted.slice(4).reduce((s, r) => s + r.value, 0);
  return [...head, { name: "Otros", value: rest }];
}

const tooltipStyle = (t: Record<string, string>) => ({
  contentStyle: { background: t["--surface-raised"], border: `1px solid ${t["--border"]}`, borderRadius: 10, color: t["--ink"] },
  labelStyle: { color: t["--ink"] },
  itemStyle: { color: t["--ink"] },
});

export function HoursBarChart({ data, unit = "h", height = 240 }: { data: { name: string; value: number; secondary?: number }[]; unit?: string; height?: number }) {
  const t = useTokens();
  if (!data.length) return <p className="muted">Sin datos.</p>;
  return (
    <div role="img" aria-label={`Gráfico de barras: ${data.map((d) => `${d.name} ${fmtNum(d.value)} ${unit}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 30, top: 5, bottom: 5 }}>
          <CartesianGrid horizontal={false} stroke={t["--border"]} />
          <XAxis type="number" tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} tickFormatter={(v) => fmtNum(v as number, 0)} />
          <YAxis type="category" dataKey="name" width={150} tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} />
          <Tooltip formatter={(v) => `${fmtNum(v as number)} ${unit}`} {...tooltipStyle(t)} cursor={{ fill: t["--border"], opacity: 0.3 }} />
          <Bar dataKey="value" name="Horas" radius={[0, 8, 8, 0]} isAnimationActive={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={series(t, i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DonutChart({ data, unit = "h", height = 240 }: { data: { name: string; value: number }[]; unit?: string; height?: number }) {
  const t = useTokens();
  const rows = groupOthers(data.filter((d) => d.value > 0));
  if (!rows.length) return <p className="muted">Sin datos.</p>;
  return (
    <div role="img" aria-label={`Distribución: ${rows.map((d) => `${d.name} ${fmtNum(d.value)} ${unit}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" innerRadius="55%" outerRadius="85%" paddingAngle={2} isAnimationActive={false}>
            {rows.map((r, i) => (
              <Cell key={r.name} fill={r.name === "Otros" ? t["--chart-other"] : series(t, i)} />
            ))}
          </Pie>
          <Tooltip formatter={(v) => `${fmtNum(v as number)} ${unit}`} {...tooltipStyle(t)} />
          <Legend wrapperStyle={{ fontSize: 12, color: t["--ink-subtle"] }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function GroupedBarChart({
  data,
  keys,
  unit = "",
  height = 260,
}: {
  data: Record<string, string | number>[];
  keys: { key: string; label: string }[];
  unit?: string;
  height?: number;
}) {
  const t = useTokens();
  if (!data.length) return <p className="muted">Sin datos.</p>;
  return (
    <div role="img" aria-label={`Comparación de ${keys.map((k) => k.label).join(" y ")}`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
          <CartesianGrid vertical={false} stroke={t["--border"]} />
          <XAxis dataKey="name" tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} interval={0} />
          <YAxis tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} tickFormatter={(v) => fmtNum(v as number, 0)} />
          <Tooltip formatter={(v) => `${fmtNum(v as number)}${unit}`} {...tooltipStyle(t)} cursor={{ fill: t["--border"], opacity: 0.3 }} />
          {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {keys.map((k, i) => (
            <Bar key={k.key} dataKey={k.key} name={k.label} fill={series(t, i)} radius={[6, 6, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Probabilidad acumulada de terminar el trabajo en N días laborables (simulación Monte Carlo). */
export function ForecastChart({ data, marks, height = 230 }: { data: { working_days: number; date: string; probability: number }[]; marks: { days: number; label: string }[]; height?: number }) {
  const t = useTokens();
  if (data.length < 2) return null;
  const rows = data.map((d) => ({ ...d, pct: Math.round(d.probability * 100) }));
  return (
    <div role="img" aria-label={`Probabilidad acumulada de terminar: ${rows.filter((_, i) => i % Math.ceil(rows.length / 6) === 0).map((d) => `${d.working_days} días ${d.pct} %`).join(", ")}`}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={rows} margin={{ left: 0, right: 20, top: 10, bottom: 18 }}>
          <CartesianGrid vertical={false} stroke={t["--border"]} />
          <XAxis dataKey="working_days" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} label={{ value: "días laborables de trabajo", position: "insideBottom", offset: -10, fill: t["--ink-subtle"], fontSize: 11 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v} %`} tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} width={48} />
          <Tooltip
            formatter={(v) => [`${v} %`, "Probabilidad de terminar"]}
            labelFormatter={(l, p) => `${l} días · ${p?.[0]?.payload?.date ? new Date(p[0].payload.date + "T00:00:00").toLocaleDateString("es-AR") : ""}`}
            {...tooltipStyle(t)}
          />
          {marks.map((m) => (
            <ReferenceLine key={m.label} x={m.days} stroke={t["--ink-subtle"]} strokeDasharray="4 3" label={{ value: m.label, position: "top", fill: t["--ink"], fontSize: 11 }} />
          ))}
          <Line type="stepAfter" dataKey="pct" name="Probabilidad" stroke={t["--chart-1"]} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({ data, height = 220 }: { data: { name: string; value: number }[]; height?: number }) {
  const t = useTokens();
  if (data.length < 2) return <p className="muted">Se necesitan al menos dos versiones para ver la evolución.</p>;
  return (
    <div role="img" aria-label={`Evolución de la duración: ${data.map((d) => `${d.name} ${d.value} días`).join(", ")}`}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ left: 0, right: 20, top: 10, bottom: 5 }}>
          <CartesianGrid vertical={false} stroke={t["--border"]} />
          <XAxis dataKey="name" tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} />
          <YAxis tick={{ fill: t["--ink-subtle"], fontSize: 12 }} stroke={t["--border"]} allowDecimals={false} />
          <Tooltip formatter={(v) => `${v} días laborables`} {...tooltipStyle(t)} />
          <Line type="monotone" dataKey="value" name="Duración" stroke={t["--chart-1"]} strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
