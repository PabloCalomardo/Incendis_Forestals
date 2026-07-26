import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Wildfire Intelligence Platform",
  description: "Portals Civil i Bomber per informacio d'incendis forestals.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ca">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
