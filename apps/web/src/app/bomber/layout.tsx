import type { ReactNode } from "react";

export default function BomberLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-[#101418] text-white">{children}</div>;
}
