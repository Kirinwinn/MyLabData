import { useState } from "react";

interface CopyButtonProps {
  label: string;
  value: string;
  compact?: boolean;
}

export function CopyButton({ label, value, compact = false }: CopyButtonProps) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
      window.setTimeout(() => setState("idle"), 1500);
    } catch {
      setState("failed");
    }
  }

  const text =
    state === "copied" ? `Copied ${label}` : state === "failed" ? "Copy failed" : `Copy ${label}`;

  return (
    <button
      aria-label={`Copy ${label}`}
      className={`copy-button${compact ? " copy-button--compact" : ""}`}
      type="button"
      onClick={copy}
    >
      {text}
    </button>
  );
}
