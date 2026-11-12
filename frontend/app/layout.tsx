import type { Metadata, Viewport } from "next";
import "./globals.css";
import Providers from "./providers";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "CareChat",
  description: "Understand your lab reports in plain language, in your own language.",
  manifest: `${base}/manifest.webmanifest`,
  icons: { icon: `${base}/icon.svg` },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0f766e" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
