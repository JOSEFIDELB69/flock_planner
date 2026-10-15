/** Cliente de la API. Todas las llamadas pasan por el proxy de Next.js (/api/v1 → backend). */

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const USER_KEY = "pm_agent_user";

export function getUserName(): string {
  try {
    return localStorage.getItem(USER_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setUserName(name: string): void {
  try {
    localStorage.setItem(USER_KEY, name);
  } catch {
    /* almacenamiento no disponible */
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const user = getUserName();
  if (user) headers["X-PM-User"] = user;
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method: options.method ?? (body ? "POST" : "GET"), headers, body, cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", "No pudimos conectar con el servidor. Revisá que el backend esté en ejecución y probá de nuevo.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data as { error?: { code: string; message: string; details?: Record<string, unknown> } } | null)?.error;
    if (err) throw new ApiError(res.status, err.code, err.message, err.details ?? {});
    const proxyDown = res.status === 500 || res.status === 502 || res.status === 503 || res.status === 504;
    throw new ApiError(
      res.status,
      "http_error",
      proxyDown ? "El backend no responde. Revisá que la API esté en ejecución." : `Error ${res.status} en la solicitud.`,
    );
  }
  return data as T;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const errors = (e.details?.errors as { field: string; message: string }[] | undefined) ?? [];
    if (errors.length) return `${e.message} ${errors.map((x) => `${x.field}: ${x.message}`).join("; ")}`;
    return e.message;
  }
  return e instanceof Error ? e.message : "Ocurrió un error inesperado.";
}
