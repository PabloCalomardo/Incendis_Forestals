import type { ReactNode } from "react";

export default function CivilLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-[#f7f7f4] text-[#17201b]">{children}</div>;
}
