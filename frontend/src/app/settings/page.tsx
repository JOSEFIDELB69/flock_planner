"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, Button, Card, ErrorState, Field, Loading, PageHeader, useToast } from "@/components/ui";
import { getUserName, setUserName } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { SystemStatus } from "@/lib/types";

function Check({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <li className="row" style={{ alignItems: "flex-start" }}>
      {ok ? <CheckCircle2 size={18} color="var(--success)" aria-hidden /> : <XCircle size={18} color="var(--danger)" aria-hidden />}
      <div>
        <strong>{label}</strong>: {ok ? "sí" : "no"}
        {detail && <div className="subtle">{detail}</div>}
      </div>
    </li>
  );
}

export default function SettingsPage() {
  const { data, error, loading, reload } = useApi<SystemStatus>("/system/status");
  const [name, setName] = useState("");
  const toast = useToast();
  useEffect(() => setName(getUserName()), []);

  return (
    <>
      <PageHeader title="Configuración" description="Estado del sistema y preferencias de este navegador." />
      <div className="grid c2">
        <Card title="Usuario responsable" sub="Se registra en la auditoría y en las versiones del plan">
          <Alert tone="info">La versión actual no tiene autenticación multiusuario: el nombre se guarda en este navegador y se envía como responsable de los cambios.</Alert>
          <div className="mt">
            <Field label="Tu nombre">{(id) => <input id={id} className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />}</Field>
            <Button
              className="mt"
              onClick={() => {
                setUserName(name.trim());
                toast("success", "Guardamos tu nombre en este navegador.");
              }}
            >
              Guardar nombre
            </Button>
          </div>
        </Card>
        <Card title="Estado del sistema">
          {loading && <Loading />}
          {error && <ErrorState message={error} onRetry={reload} />}
          {data && (
            <ul className="list-plain">
              <Check ok={data.database_ok} label={`Base de datos (${data.database})`} detail={data.database === "sqlite" ? "SQLite es solo para desarrollo local. En producción usá PostgreSQL." : undefined} />
              <Check
                ok={data.ai_available}
                label={`IA disponible (${data.ai_provider === "claude_code" ? "Claude Code" : data.ai_provider === "demo" ? "demostración simulada" : "sin proveedor"})`}
                detail={
                  data.ai_provider === "claude_code"
                    ? `Modelo: ${data.ai_model}. La CLI corre sin herramientas habilitadas y necesita una sesión iniciada (claude → /login).`
                    : data.ai_provider
                      ? `Modelo: ${data.ai_model}. Se cambia con AI_PROVIDER en el backend.`
                      : "Configurá AI_PROVIDER=claude_code en el backend."
                }
              />
              <Check ok={data.ai_demo_mode} label="Modo demostración de IA" detail="Con AI_PROVIDER=demo los resultados de IA son heurísticos y se marcan como simulados." />
              <Check ok={data.secrets_encryption_configured} label="Cifrado de credenciales de integraciones" detail="Necesario solo para guardar el token de JIRA." />
              <li className="subtle">
                Entorno: {data.app_env} · Versión de la API: {data.version}
              </li>
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
