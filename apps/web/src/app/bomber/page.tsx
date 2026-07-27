import { MapShell } from "@/components/map-shell";

export default function BomberPage() {
  return (
    <main className="grid min-h-screen grid-rows-[auto_1fr]">
      <header className="border-b border-[#2a333c] bg-[#151b20] px-5 py-4">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#ffb199]">
          Portal Bomber
        </p>
        <h1 className="mt-1 text-2xl font-bold">Base operativa protegida</h1>
      </header>
      <section className="grid gap-4 p-4 lg:grid-cols-[380px_1fr]">
        <aside className="rounded-lg border border-[#2a333c] bg-[#151b20] p-4">
          <h2 className="text-lg font-semibold">Fonts i readiness</h2>
          <p className="mt-2 text-sm text-[#b8c0c7]">
            La ingesta ja prepara fonts operatives. Autenticacio, permisos i capes professionals
            arribaran a la fase del portal Bomber.
          </p>
        </aside>
        <MapShell portal="bomber" />
      </section>
    </main>
  );
}
