"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage } from "./api";

/** Carga datos de la API con estados explícitos de carga y error. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const seq = useRef(0);

  const reload = useCallback(async () => {
    if (!path) return;
    const n = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const result = await api<T>(path);
      if (n === seq.current) setData(result);
    } catch (e) {
      if (n === seq.current) setError(errorMessage(e));
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

/** Pide confirmación al abandonar la página con cambios sin guardar. */
export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
}

/** Ejecuta una acción con estado de carga y notifica éxito/error. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, onError?: (msg: string) => void): Promise<T | undefined> => {
    setBusy(key);
    try {
      return await fn();
    } catch (e) {
      onError?.(errorMessage(e));
      return undefined;
    } finally {
      setBusy(null);
    }
  }, []);
  return { busy, run };
}
