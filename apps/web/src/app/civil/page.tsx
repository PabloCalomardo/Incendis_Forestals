import { MapShell } from "@/components/map-shell";

export default function CivilPage() {
  return (
    <main className="grid min-h-screen grid-rows-[auto_1fr]">
      <header className="border-b border-[#d7ddd8] bg-white px-5 py-4">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-canopy">
          Portal Civil
        </p>
        <h1 className="mt-1 text-2xl font-bold">Incendis i avisos publics</h1>
      </header>
      <section className="grid gap-4 p-4 lg:grid-cols-[360px_1fr]">
        <aside className="rounded-lg border border-[#d7ddd8] bg-white p-4">
          <h2 className="text-lg font-semibold">Estat de dades</h2>
          <p className="mt-2 text-sm text-[#53605a]">
            Sense fonts externes configurades en Fase 1. La vista queda preparada per consumir l'API
            Civil quan s'implementi.
          </p>
        </aside>
        <MapShell portal="civil" />
      </section>
    </main>
  );
}
