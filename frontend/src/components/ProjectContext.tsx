"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { useApi } from "@/lib/hooks";
import { PROJECT_STATUS_LABEL } from "@/lib/format";
import type { Project, SystemStatus } from "@/lib/types";

import { Badge, ErrorState, Loading } from "./ui";

type Ctx = { project: Project; reload: () => Promise<void>; system: SystemStatus | null };
const ProjectCtx = createContext<Ctx | null>(null);

export function ProjectProvider({ id, children }: { id: string; children: ReactNode }) {
  const { data, error, loading, reload } = useApi<Project>(`/projects/${id}`);
  const { data: system } = useApi<SystemStatus>("/system/status");
  if (loading && !data) return <Loading label="Cargando proyecto…" />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <ProjectCtx.Provider value={{ project: data, reload, system }}>
      <HeaderProject project={data} />
      {children}
    </ProjectCtx.Provider>
  );
}

function HeaderProject({ project }: { project: Project }) {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setTarget(document.getElementById("header-project"));
  }, []);
  useEffect(() => {
    document.title = `${project.name} · Flock Planner`;
  }, [project.name]);
  if (!target) return null;
  return createPortal(
    <span className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{project.name}</span>
      <Badge tone={project.status === "active" ? "success" : ""}>{PROJECT_STATUS_LABEL[project.status]}</Badge>
      {project.active_version_number && <Badge tone="primary">Versión activa v{project.active_version_number}</Badge>}
      <Badge tone="outline">{project.mode === "jira" ? "Modo integrado (JIRA)" : "Modo autónomo"}</Badge>
    </span>,
    target,
  );
}

export function useProject(): Ctx {
  const ctx = useContext(ProjectCtx);
  if (!ctx) throw new Error("useProject fuera de ProjectProvider");
  return ctx;
}
