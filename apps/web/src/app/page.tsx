import Link from "next/link";
import { getApiStatus } from "@/lib/api/client";

export default async function HomePage() {
  const status = await getApiStatus();

  return (
    <main className="min-h-screen bg-[#f7f7f4] px-6 py-10 text-[#17201b]">
      <section className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-5xl flex-col justify-center gap-8">
        <div className="max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-canopy">
            Wildfire Intelligence Platform
          </p>
          <h1 className="mt-4 text-4xl font-bold leading-tight sm:text-6xl">
            Informacio d'incendis amb procedencia, temps i confiança visibles.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-[#4b534f]">
            Base inicial del projecte amb portals separats, API de salut i estructura preparada per
            a dades oficials, observades i estimades.
          </p>
        </div>

        <nav className="grid gap-4 sm:grid-cols-2" aria-label="Entrades principals">
          <Link
            href="/civil"
            className="rounded-lg border border-[#c8d3cc] bg-white p-6 shadow-sm transition hover:border-canopy"
          >
            <span className="text-sm font-semibold uppercase text-canopy">Portal Civil</span>
            <span className="mt-3 block text-2xl font-bold">Informacio publica</span>
            <span className="mt-2 block text-[#53605a]">
              Vista clara per incidents, avisos i estat de dades.
            </span>
          </Link>
          <Link
            href="/bomber"
            className="rounded-lg border border-[#d5cbc7] bg-white p-6 shadow-sm transition hover:border-ember"
          >
            <span className="text-sm font-semibold uppercase text-ember">Portal Bomber</span>
            <span className="mt-3 block text-2xl font-bold">Operativa protegida</span>
            <span className="mt-2 block text-[#53605a]">
              Espai preparat per autenticacio, fonts i decisions operatives.
            </span>
          </Link>
        </nav>

        <div className="rounded-lg border border-[#d7ddd8] bg-white p-4 text-sm text-[#4b534f]">
          API:{" "}
          <strong className="text-[#17201b]">{status.ok ? "connectada" : "no disponible"}</strong>
          <span className="ml-2">Version: {status.version ?? "desconeguda"}</span>
        </div>
      </section>
    </main>
  );
}
