import { useEffect } from "react";

/** Lleva al elemento del #hash cuando el contenido (cargado de forma asíncrona) ya está en pantalla. */
export function useHashScroll(ready: boolean) {
  useEffect(() => {
    if (!ready) return;
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id) return;
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("anchor-flash");
    const t = window.setTimeout(() => el.classList.remove("anchor-flash"), 2200);
    return () => window.clearTimeout(t);
  }, [ready]);
}
