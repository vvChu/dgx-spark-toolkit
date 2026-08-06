import { ButtonHTMLAttributes, ReactNode } from 'react';

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  children: ReactNode;
}

export function LoadingButton({ loading, children, disabled, className = "", ...props }: LoadingButtonProps) {
  return (
    <button disabled={loading || disabled} className={className} {...props}>
      {loading ? <span className="animate-spin">&#9203;</span> : children}
    </button>
  );
}
