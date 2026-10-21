"use client";

import { useEffect, useState } from "react";
import { api, type Profile } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import Chat from "@/components/Chat";
import { card, input, PageTitle, Shell, Spinner } from "@/components/ui";

export default function Ask() {
  const { t } = useI18n();
  const { me, allowed } = useGuard();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");

  useEffect(() => {
    if (allowed) api<Profile[]>("/api/profiles").then(setProfiles).catch(() => {});
  }, [allowed]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;
  return (
    <Shell>
      <PageTitle sub={t("ask_sub")}>{t("nav_ask")}</PageTitle>
      {profiles.length > 0 && (
        <div className="mb-3">
          <label className="mb-1 block text-sm font-medium" htmlFor="who">{t("asking_for")}</label>
          <select id="who" className={input} value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            <option value="">{t("no_one_in_particular")}</option>
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
          </select>
        </div>
      )}
      <div className={card}>
        <Chat key={profileId} profileId={profileId || null} historyEnabled={false}
              suggestions={[t("suggest_hba1c"), t("suggest_thyroid"), t("suggest_vitd")]} />
      </div>
    </Shell>
  );
}
