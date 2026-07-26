import type { ReactNode } from "react";

export function StatusBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded border border-[#c8d3cc] px-2 py-1 text-xs font-semibold">
      {children}
    </span>
  );
}
