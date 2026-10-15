"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ProjectForm, type ProjectInput } from "@/components/ProjectForm";
import { useProject } from "@/components/ProjectContext";
import { Alert, Button, Card, ConfirmDialog, Field, PageHeader, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export default function ProjectSettingsPage() {
  const { project, reload } = useProject();
  const router = useRouter();
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const [del, setDel] = useState<{ text: string } | null>(null);

  const save = async (data: ProjectInput) => {
    setSaving(true);
    try {
      await api(`/projects/${project.id}`, { method: "PATCH", body: data });
      toast("success", "Proyecto actualizado. Las versiones de plan guardadas conservan su calendario.");
      await reload();
      return true;
    } catch (e) {
      toast("danger", errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const archive = async () => {
    try {
      await api(`/projects/${project.id}`, { method: "PATCH", body: { status: project.status === "archived" ? "active" : "archived" } });
      toast("success", project.status === "archived" ? "Proyecto reactivado." : "Proyecto archivado.");
      await reload();
    } catch (e) {
      toast("danger", errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader title="Configuración del proyecto" description="Datos generales, calendario laboral, feriados y modo de funcionamiento." />
      <div className="stack">
        <Card className="pad-lg">
          <ProjectForm initial={project} onSubmit={save} submitLabel="Guardar cambios" saving={saving} />
        </Card>
        <Card title="Zona de riesgo">
          <div className="row">
            <Button variant="secondary" onClick={archive}>
              {project.status === "archived" ? "Reactivar proyecto" : "Archivar proyecto"}
            </Button>
            <Button variant="danger" onClick={() => setDel({ text: "" })}>
              Eliminar proyecto
            </Button>
          </div>
        </Card>
      </div>
      {del && (
        <ConfirmDialog
          title="Eliminar proyecto"
          danger
          confirmLabel="Eliminar definitivamente"
          confirmDisabled={del.text !== project.name}
          onCancel={() => setDel(null)}
          onConfirm={async () => {
            try {
              await api(`/projects/${project.id}?confirm=true`, { method: "DELETE" });
              toast("success", "Proyecto eliminado.");
              try {
                localStorage.removeItem("pm_agent_last_project");
              } catch {
                /* sin almacenamiento */
              }
              router.push("/projects");
            } catch (e) {
              toast("danger", errorMessage(e));
            }
          }}
        >
          <Alert tone="danger">Se eliminarán requisitos, backlog, versiones, escenarios y exportaciones. No se puede deshacer. Si querés conservar el historial, archivalo.</Alert>
          <Field label={`Escribí el nombre del proyecto (${project.name}) para confirmar`} className="mt">
            {(id) => <input id={id} className="input" value={del.text} onChange={(e) => setDel({ text: e.target.value })} autoComplete="off" />}
          </Field>
        </ConfirmDialog>
      )}
    </>
  );
}
