"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useProject } from "./ProjectContext";

/** En las solapas del proyecto (Requisitos, Historias, Planificación…) muestra el botón para volver a su resumen. */
export function ProjectBackLink() {
  const { project } = useProject();
  const pathname = usePathname();
  const home = `/projects/${project.id}`;
  if (pathname === home || pathname === `${home}/`) return null;
  return (
    <Link href={home} className="btn ghost sm back-link">
      <ArrowLeft size={16} aria-hidden /> Volver al proyecto <span className="back-link-name">{project.name}</span>
    </Link>
  );
}
