"use client";

import {
  BarChart3,
  BookOpen,
  CalendarRange,
  Calculator,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderKanban,
  GitBranch,
  HelpCircle,
  History,
  LayoutDashboard,
  ListChecks,
  ListTree,
  Menu,
  Plug,
  Settings,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { HelpPanel } from "./HelpPanel";
import { ToastProvider } from "./ui";

const LAST_PROJECT_KEY = "pm_agent_last_project";

const PROJECT_NAV = [
  { slug: "", label: "Resumen del proyecto", icon: BarChart3 },
  { slug: "requirements", label: "Requisitos/Requerimientos", icon: BookOpen },
  { slug: "stories", label: "Épicas e historias", icon: ListTree },
  { slug: "backlog", label: "Backlog", icon: ListChecks },
  { slug: "estimates", label: "Estimaciones", icon: Calculator },
  { slug: "planning", label: "Planificación", icon: CalendarRange },
  { slug: "team", label: "Equipo y capacidad", icon: Users },
  { slug: "optimization", label: "Optimización de escenarios", icon: SlidersHorizontal },
  { slug: "versions", label: "Versiones", icon: History },
  { slug: "reports", label: "Informes y exportaciones", icon: FileText },
  { slug: "integrations", label: "Integraciones", icon: Plug },
  { slug: "settings", label: "Configuración del proyecto", icon: GitBranch },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  // Las opciones del proyecto activo arrancan colapsadas
  const [projectNavOpen, setProjectNavOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const closeHelp = useCallback(() => setHelpOpen(false), []);
  const [lastProject, setLastProject] = useState<string | null>(null);
  const match = pathname.match(/^\/projects\/(\d+)(?:\/([\w-]+))?/);
  const projectId = match?.[1] ?? null;
  const section = match?.[2] ?? "";

  useEffect(() => {
    try {
      if (projectId) localStorage.setItem(LAST_PROJECT_KEY, projectId);
      setLastProject(projectId ?? localStorage.getItem(LAST_PROJECT_KEY));
    } catch {
      setLastProject(projectId);
    }
    setOpen(false);
  }, [projectId, pathname]);

  // en pantallas chicas el menú lateral se cierra con Esc
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const ctxProject = projectId ?? lastProject;
  const item = (href: string, label: string, Icon: typeof LayoutDashboard, active: boolean, disabled = false) => (
    <Link key={href + label} href={href} className={`nav-item ${active ? "active" : ""} ${disabled ? "disabled" : ""}`} aria-current={active ? "page" : undefined} aria-disabled={disabled || undefined} tabIndex={disabled ? -1 : undefined}>
      <Icon size={18} aria-hidden />
      <span>{label}</span>
    </Link>
  );

  return (
    <ToastProvider>
      <a href="#main" className="skip-link">
        Saltar al contenido
      </a>
      <div className="shell">
        <header className="header">
          <button className="menu-btn" aria-label="Abrir navegación" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            <Menu size={22} />
          </button>
          <Link href="/dashboard" className="brand" aria-label="Flock Planner, ir al dashboard">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/flock-logo.png" alt="Flock" width={94} height={24} className="brand-logo" />
            <span className="brand-sep" aria-hidden />
            <span className="brand-product">Planner</span>
          </Link>
          <div id="header-project" className="project-name" />
          <span className="spacer" />
          <span className="env" title="Entorno">
            {process.env.NEXT_PUBLIC_APP_ENV ?? "local"}
          </span>
          <button
            type="button"
            className="help-btn"
            aria-label={helpOpen ? "Cerrar ayuda" : "Abrir ayuda"}
            title="Ayuda"
            aria-expanded={helpOpen}
            aria-controls="help-panel"
            onClick={() => setHelpOpen((v) => !v)}
          >
            <HelpCircle size={20} aria-hidden />
          </button>
        </header>
        <HelpPanel open={helpOpen} onClose={closeHelp} projectId={ctxProject} />
        {open && <div className="sidebar-backdrop" aria-hidden onClick={() => setOpen(false)} />}
        <nav className={`sidebar ${open ? "open" : ""}`} aria-label="Navegación principal">
          {item("/dashboard", "Dashboard", LayoutDashboard, pathname === "/dashboard")}
          {item("/projects", "Proyectos", FolderKanban, pathname === "/projects" || pathname === "/projects/new")}
          <button
            type="button"
            className="nav-section nav-toggle"
            aria-expanded={projectNavOpen}
            aria-controls="project-nav"
            onClick={() => setProjectNavOpen((v) => !v)}
          >
            {projectNavOpen ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
            <span>{ctxProject ? "Proyecto activo" : "Proyecto (elegí uno)"}</span>
            {!projectNavOpen && projectId && (
              <span className="nav-current">{PROJECT_NAV.find((n) => n.slug === section)?.label}</span>
            )}
          </button>
          <div id="project-nav" hidden={!projectNavOpen}>
            {PROJECT_NAV.map((n) =>
              item(
                ctxProject ? `/projects/${ctxProject}${n.slug ? `/${n.slug}` : ""}` : "/projects",
                n.label,
                n.icon,
                !!projectId && section === n.slug,
                !ctxProject,
              ),
            )}
          </div>
          <div className="nav-section">Sistema</div>
          {item("/settings", "Configuración", Settings, pathname === "/settings")}
        </nav>
        <main id="main" className="main" tabIndex={-1}>
          <div className="main-inner">{children}</div>
          <div className="footer">Flock Planner · Las estimaciones son proyecciones calculadas, no garantías.</div>
        </main>
      </div>
    </ToastProvider>
  );
}
