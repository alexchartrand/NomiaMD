type SpinnerProps = {
  label?: string;
};

export function Spinner({ label }: SpinnerProps) {
  return (
    <span className="spinner" role="status">
      <span className="spinner-dot" />
      <span className="spinner-dot" />
      <span className="spinner-dot" />
      {label && <span className="spinner-label">{label}</span>}
    </span>
  );
}
