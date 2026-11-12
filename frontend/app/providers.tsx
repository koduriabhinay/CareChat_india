"use client";

import { AppProvider } from "@/lib/app";
import { I18nProvider } from "@/lib/i18n";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <AppProvider>{children}</AppProvider>
    </I18nProvider>
  );
}
