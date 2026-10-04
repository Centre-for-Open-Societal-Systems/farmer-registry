interface Props {
  enabled: boolean;
  paused: boolean;
}

export default function StatusBadge({ enabled, paused }: Props) {
  if (!enabled)
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-200 text-gray-700">
        Disabled
      </span>
    );
  if (paused)
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
        Paused
      </span>
    );
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
      Active
    </span>
  );
}
