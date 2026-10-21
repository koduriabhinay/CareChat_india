"use client";

import { useI18n, type TKey } from "@/lib/i18n";
import { PageTitle, Shell } from "@/components/ui";

export default function LegalPage({ prefix, count, title }: { prefix: string; count: number; title: TKey }) {
  const { t } = useI18n();
  return (
    <Shell>
      <PageTitle sub={t("legal_draft_note")}>{t(title)}</PageTitle>
      <div className="space-y-5">
        {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
          <section key={n}>
            <h2 className="font-semibold">{t(`${prefix}${n}_title` as TKey)}</h2>
            <p className="mt-1 whitespace-pre-line text-sm leading-relaxed">{t(`${prefix}${n}_body` as TKey)}</p>
          </section>
        ))}
      </div>
    </Shell>
  );
}
