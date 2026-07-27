import { Suspense } from "react";
import { CivilPortal } from "@/components/civil/civil-portal";

export default function CivilPage() {
  return (
    <Suspense fallback={<main className="p-4">Carregant portal civil...</main>}>
      <CivilPortal />
    </Suspense>
  );
}
