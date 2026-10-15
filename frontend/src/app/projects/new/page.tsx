"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ProjectForm, type ProjectInput } from "@/components/ProjectForm";
import { Card, PageHeader, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function NewProjectPage() {
  const router = useRouter();
  const toast = useToast();
  const [saving, setSaving] = useState(false);

  const create = async (data: ProjectInput) => {
    setSaving(true);
    try {
      const p = await api<Project>("/projects", { body: { ...data, status: data.status ?? "active" } });
      toast("success", "Proyecto creado con el equipo inicial (1 Frontend, 1 Backend, 1 QA). Ahora cargá los requisitos.");
      router.push(`/projects/${p.id}/requirements`);
      return true;
    } catch (e) {
      toast("danger", `No pudimos crear el proyecto. ${errorMessage(e)}`);
      return false;
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader title="Nuevo proyecto" crumbs={<><Link href="/projects">Proyectos</Link> / Nuevo</>} description="El proyecto se guarda como borrador y arranca con un equipo editable de 1 Frontend, 1 Backend y 1 QA." />
      <Card className="pad-lg">
        <ProjectForm onSubmit={create} submitLabel="Crear proyecto" saving={saving} />
      </Card>
    </>
  );
}
