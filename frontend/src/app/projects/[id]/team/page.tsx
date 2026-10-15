"use client";

import { useEffect, useState } from "react";

import { useProject } from "@/components/ProjectContext";
import { cleanTeam, TeamEditor } from "@/components/TeamEditor";
import { Alert, Button, Card, ErrorState, Loading, PageHeader, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { useApi, useUnsavedChanges } from "@/lib/hooks";
import type { Backlog, TeamProfile } from "@/lib/types";

export default function TeamPage() {
  const { project } = useProject();
  const toast = useToast();
  const remote = useApi<TeamProfile[]>(`/projects/${project.id}/team`);
  const backlog = useApi<Backlog>(`/projects/${project.id}/backlog`);
  const [team, setTeam] = useState<TeamProfile[]>([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (remote.data) setTeam(remote.data);
  }, [remote.data]);
  const dirty = !!remote.data && JSON.stringify(cleanTeam(team)) !== JSON.stringify(cleanTeam(remote.data));
  useUnsavedChanges(dirty);

  const used = Object.keys(backlog.data?.hours_by_profile ?? {});
  const missing = used.filter((k) => !team.some((p) => p.profile_key === k));
  const empty = team.filter((p) => used.includes(p.profile_key) && p.quantity === 0);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await api<TeamProfile[]>(`/projects/${project.id}/team`, { method: "PUT", body: { profiles: cleanTeam(team) } });
      remote.setData(saved);
      toast("success", "Equipo guardado. Las versiones de plan existentes no cambian; recalculá o simulá escenarios para ver el efecto.");
    } catch (e) {
      toast("danger", errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Equipo y capacidad"
        description="Perfiles, cantidades, horas productivas y dedicación. Los valores iniciales son configurables: no asumimos 8 horas productivas por día."
        actions={
          <>
            <Button variant="secondary" disabled={!dirty} onClick={() => remote.data && setTeam(remote.data)}>
              Descartar cambios
            </Button>
            <Button onClick={save} loading={saving} disabled={!dirty}>
              Guardar equipo
            </Button>
          </>
        }
      />
      {remote.loading && !remote.data && <Loading />}
      {remote.error && <ErrorState message={remote.error} onRetry={remote.reload} />}
      {remote.data && (
        <div className="stack">
          {missing.length > 0 && <Alert tone="warning" title="Faltan perfiles">El backlog tiene tareas para perfiles que no están en el equipo: {missing.join(", ")}. Agregalos para poder planificar.</Alert>}
          {empty.length > 0 && <Alert tone="warning">Hay perfiles con tareas y cantidad 0: {empty.map((p) => p.profile_name).join(", ")}.</Alert>}
          <Card title="Perfiles del equipo" sub="Expandí un perfil para configurar la disponibilidad individual, vacaciones y ausencias">
            <TeamEditor team={team} onChange={setTeam} />
            <p className="subtle mt">
              Capacidad nominal total: {fmtNum(team.reduce((s, p) => s + p.quantity * p.available_hours_per_day * (p.dedication_percentage / 100), 0))} h/día. El motor descuenta además un 5 % de eficiencia por cada persona adicional en un mismo perfil (coordinación) y aplica el calendario laboral.
            </p>
          </Card>
          <Card title="Cómo usa el motor estos datos">
            <ul className="ac-list" style={{ color: "var(--ink)" }}>
              <li>Capacidad diaria por persona = horas productivas × dedicación × disponibilidad individual × eficiencia de coordinación.</li>
              <li>Cada tarea la realiza una sola persona del perfil asignado; nadie recibe más trabajo simultáneo del que puede hacer.</li>
              <li>Los perfiles marcados como QA prueban cada historia después de su desarrollo.</li>
              <li>Seniority (perfiles de desarrollo y QA): indicá cuántas personas son SR, SSR y JR. El tiempo de cada tarea se ajusta según quién la hace, con los porcentajes de Planificación (por defecto SR −15 %, SSR sin ajuste, JR +30 %). El motor asigna cada tarea a la persona que la termina antes.</li>
              <li>La tarifa por hora es opcional y habilita los costes estimados de planes y escenarios.</li>
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}
