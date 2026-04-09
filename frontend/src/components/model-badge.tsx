interface ModelBadgeProps {
  model: string;
  provider: string;
  thinking?: boolean;
}

export default function ModelBadge({ model, provider, thinking }: ModelBadgeProps) {
  return (
    <>
      <span className="font-medium">{model}</span>
      <span className="ml-1 text-xs text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">
        {provider}
      </span>
      {thinking && (
        <span className="ml-1 text-xs text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">思考</span>
      )}
    </>
  );
}
