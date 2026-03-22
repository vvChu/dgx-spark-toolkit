export function LoadingButton({ loading, children, disabled, className = "", ...props }) {
  return (
    <button disabled={loading || disabled} className={className} {...props}>
      {loading ? <span className="animate-spin">⏳</span> : children}
    </button>
  );
}
