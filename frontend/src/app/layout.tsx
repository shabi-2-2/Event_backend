import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppProviders } from "@/components/providers/app-providers";
import { isSupabaseConfigured } from "@/lib/env";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Event Management",
    template: "%s | Event Management",
  },
  description: "Event administration and check-in workspace",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppProviders supabaseConfigured={isSupabaseConfigured()}>{children}</AppProviders>
      </body>
    </html>
  );
}
