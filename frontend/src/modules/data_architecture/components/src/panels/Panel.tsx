interface PanelProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

export function Panel({ title, subtitle, actions, className, children }: PanelProps) {
  return (
    <section className={`panel ${className || ''}`.trim()}>
      <header className="panel-header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

interface LoadingPanelProps {
  title: string;
  message: string;
}

export function LoadingPanel({ title, message }: LoadingPanelProps) {
  return (
    <Panel title={title}>
      <div className="loading-row">
        <span className="spinner" />
        <span>{message}</span>
      </div>
    </Panel>
  );
}
