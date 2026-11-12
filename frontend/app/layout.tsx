import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CareChat",
  description: "Understand your medical reports in plain language.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
