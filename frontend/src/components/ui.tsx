"use client";

import { AlertTriangle, CheckCircle2, Info, Inbox, X, XCircle, FlaskConical } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";

// ------------------------------------------------------------------ botones

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "brand";
  size?: "md" | "sm";
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({ variant = "primary", size = "md", loading, icon, children, disabled, className = "", ...rest }: BtnProps) {
  return (
    <button
      type="button"
      className={`btn ${variant !== "primary" ? variant : ""} ${size === "sm" ? "sm" : ""} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="spinner" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function IconButton({ label, children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" className="icon-btn" aria-label={label} title={label} {...rest}>
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ estructura

export function PageHeader({ title, description, actions, crumbs }: { title: string; description?: ReactNode; actions?: ReactNode; crumbs?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        {crumbs && <nav className="breadcrumbs" aria-label="Ubicación">{crumbs}</nav>}
        <h1>{title}</h1>
        {description && <div className="desc">{description}</div>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function Card({ title, sub, actions, children, className = "" }: { title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {actions && <div className="actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, icon, brand, delta }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; brand?: boolean; delta?: ReactNode }) {
  return (
    <div className={`card stat ${brand ? "brand" : ""}`}>
      <span className="label">
        {icon}
        {label}
      </span>
      <span className="value">{value}</span>
      {delta}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Badge({ tone = "", children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${tone}`} title={title}>
      {children}
    </span>
  );
}

const ALERT_ICON = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle };

export function Alert({ tone = "info", title, children, action }: { tone?: "info" | "success" | "warning" | "danger"; title?: string; children?: ReactNode; action?: ReactNode }) {
  const Icon = ALERT_ICON[tone];
  return (
    <div className={`alert ${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={18} aria-hidden />
      <div style={{ flex: 1 }}>
        {title && <div className="title">{title}</div>}
        {children}
      </div>
      {action}
    </div>
  );
}

/** Aviso obligatorio para resultados del modo demostración (no provienen de un modelo de IA). */
export function SimulatedNotice({ what = "Estos resultados" }: { what?: string }) {
  return (
    <div className="alert warning sim-banner" role="status">
      <FlaskConical size={18} aria-hidden />
      <div>
        <div className="title">Resultado simulado (modo demostración)</div>
        {what} se generaron con heurísticas locales, no con IA. Revisalos antes de usarlos en una propuesta.
      </div>
    </div>
  );
}

export function EmptyState({ title, children, action, icon }: { title: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty">
      <div className="icon">{icon ?? <Inbox size={26} aria-hidden />}</div>
      <h3>{title}</h3>
      {children && <div style={{ maxWidth: 520 }}>{children}</div>}
      {action}
    </div>
  );
}

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="loading-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden /> {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert tone="danger" title="No pudimos cargar los datos" action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Reintentar</Button>}>
      {message}
    </Alert>
  );
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const tone = value > 1 ? "over" : value >= 0.9 ? "warn" : "";
  return (
    <div className={`progress ${tone}`} role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

// ------------------------------------------------------------------ formularios

export function Field({ label, help, error, required, children, className = "" }: { label: string; help?: ReactNode; error?: string; required?: boolean; children: (id: string) => ReactNode; className?: string }) {
  const id = useId();
  return (
    <div className={`field ${className}`}>
      <label htmlFor={id} className={required ? "req" : ""}>
        {label}
      </label>
      {children(id)}
      {help && !error && <span className="help">{help}</span>}
      {error && (
        <span className="error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" className="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ ventanas

export function Modal({ title, onClose, children, footer, wide }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("input, select, textarea, button:not(.icon-btn)");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && ref.current) {
        const items = Array.from(ref.current.querySelectorAll<HTMLElement>("a, button, input, select, textarea")).filter((el) => !el.hasAttribute("disabled"));
        if (!items.length) return;
        const [a, b] = [items[0], items[items.length - 1]];
        if (e.shiftKey && document.activeElement === a) {
          e.preventDefault();
          b.focus();
        } else if (!e.shiftKey && document.activeElement === b) {
          e.preventDefault();
          a.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <IconButton label="Cerrar" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  danger,
  loading,
  confirmDisabled,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
  loading?: boolean;
  confirmDisabled?: boolean;
}) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancelar
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading} disabled={confirmDisabled}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}

// ------------------------------------------------------------------ toasts

type Toast = { id: number; tone: "success" | "danger" | "info" | "warning"; text: string };
const ToastCtx = createContext<(tone: Toast["tone"], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, tone, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === "danger" ? 9000 : 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => {
          const Icon = ALERT_ICON[t.tone];
          return (
            <div key={t.id} className={`toast ${t.tone}`} role={t.tone === "danger" ? "alert" : "status"}>
              <Icon size={18} aria-hidden />
              <div style={{ flex: 1 }}>{t.text}</div>
              <IconButton label="Cerrar aviso" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}>
                <X size={14} />
              </IconButton>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
