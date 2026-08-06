interface MetricBadgeProps {
  label: string;
  value: number;
  threshold?: number;
}

export function MetricBadge({ label, value, threshold = 0.8 }: MetricBadgeProps) {
  const percentage = Math.round(value * 100);
  const colorClass = value > threshold ? 'text-green-500' : 'text-yellow-500';

  return (
    <div className="flex items-center space-x-2">
      <span className="text-[10px] uppercase font-bold text-gray-500">{label}:</span>
      <span className={`text-sm font-black ${colorClass}`}>
        {percentage}%
      </span>
    </div>
  );
}
