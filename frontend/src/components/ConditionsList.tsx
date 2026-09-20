function conditionValue(value: unknown): string {
  if (value === null) return "Unspecified";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(conditionValue).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${key}: ${conditionValue(nested)}`)
      .join("; ");
  }
  return String(value);
}

export function ConditionsList({ conditions }: { conditions: Record<string, unknown> }) {
  const items = Object.entries(conditions);
  if (!items.length) return <span className="conditions-empty">No additional conditions</span>;

  return (
    <dl className="conditions-list">
      {items.map(([key, value]) => (
        <div key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd>{conditionValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
