import { Coins } from "lucide-react";
import type { Metadata } from "next";
import { HeaderAuth } from "@/components/HeaderAuth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finkow — AI agents that invest for you",
  description:
    "Finkow democratizes investing: AI agents that grow your money, detect opportunities, and explain everything in plain language. No brokerage apps, no jargon. Paper money while you learn.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        <header className="border-b border-border bg-background/95">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
            <a
              href="/"
              className="inline-flex cursor-pointer items-center gap-2.5 transition-opacity duration-200 hover:opacity-80"
              aria-label="Finkow home"
            >
              <span className="btn-sheen flex h-9 w-9 items-center justify-center rounded-lg gold-bg shadow-[0_6px_20px_-6px_rgba(245,158,11,0.5)]">
                <Coins className="h-5 w-5 text-on-accent" aria-hidden />
              </span>
              <span className="font-display text-xl font-semibold tracking-tight">Finkow</span>
            </a>
            <div className="flex items-center gap-3">
              <span className="rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent">
                Paper money
              </span>
              <HeaderAuth />
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">{children}</main>

        <footer className="border-t border-border">
          <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>Finkow — AI investing agents for everyone.</p>
            <p>All money is paper money. Not financial advice.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
