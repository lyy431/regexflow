interface Props {
  error: Error;
  onDismiss?: () => void;
  action?: { label: string; onClick: () => void };
}

export function ErrorBanner({ error, onDismiss, action }: Props) {
  return (
    <div className="banner banner--error" role="alert">
      <span className="banner__body">{error.message}</span>
      {action && (
        <button type="button" className="button button--small" onClick={action.onClick}>
          {action.label}
        </button>
      )}
      {onDismiss && (
        <button type="button" className="banner__close" aria-label="Dismiss" onClick={onDismiss}>
          ×
        </button>
      )}
    </div>
  );
}
