import type { ReactNode } from "react";

import { ProjectBackLink } from "@/components/ProjectBackLink";
import { ProjectProvider } from "@/components/ProjectContext";

export default async function ProjectLayout({ children, params }: { children: ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <ProjectProvider id={id}>
      <ProjectBackLink />
      {children}
    </ProjectProvider>
  );
}
