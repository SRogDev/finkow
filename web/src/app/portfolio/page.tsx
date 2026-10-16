import type { Metadata } from "next";
import { DashboardClient } from "@/components/dashboard";

export const metadata: Metadata = {
  title: "Portfolio — Finkow",
  description:
    "Your portfolio at a glance: total value, performance, allocation, positions, and transaction history. Virtual capital while you learn.",
};

export default function PortfolioPage() {
  return <DashboardClient />;
}
