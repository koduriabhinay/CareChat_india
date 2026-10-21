"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type Profile } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { LANGUAGES, useI18n, type TKey } from "@/lib/i18n";
import { btnDanger, btnPrimary, card, ErrorBox, input, PageTitle, Shell, Spinner } from "@/components/ui";

const DIETS = ["vegetarian", "eggetarian", "non_vegetarian", "vegan", "jain"] as const;
const RELATIONS = ["mother", "father", "spouse", "son", "daughter", "grandparent", "sibling", "other"] as const;

interface Form {
  display_name: string;
  relation: string;
  language: string;
  name_on_reports: string;
  birth_year: string;
  sex: string;
  height_cm: string;
  weight_kg: string;
  conditions: string;
  medicines: string;
  pregnant: boolean;
  diet_type: string;
  diet_notes: string;
  family_consent: boolean;
}

const EMPTY: Form = {
  display_name: "", relation: "self", language: "", name_on_reports: "", birth_year: "", sex: "", height_cm: "",
  weight_kg: "", conditions: "", medicines: "", pregnant: false, diet_type: "", diet_notes: "", family_consent: false,
};

function fromProfile(p: Profile): Form {
  return {
    display_name: p.display_name, relation: p.is_self ? "self" : p.relation, language: p.language ?? "",
    name_on_reports: p.name_on_reports ?? "", birth_year: p.birth_year?.toString() ?? "", sex: p.sex ?? "",
    height_cm: p.height_cm?.toString() ?? "", weight_kg: p.weight_kg?.toString() ?? "",
    conditions: p.conditions.join(", "), medicines: p.medicines.join(", "), pregnant: p.pregnant,
    diet_type: p.diet_type ?? "", diet_notes: p.diet_notes ?? "", family_consent: true,
  };
}

function ProfileForm() {
  const { t, lang } = useI18n();
  const { allowed } = useGuard();
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const [form, setForm] = useState<Form>({ ...EMPTY, relation: params.get("relation") === "self" ? "self" : "mother" });
  const [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed || !id) return;
    api<Profile>(`/api/profiles/${id}`).then((p) => { setProfile(p); setForm(fromProfile(p)); }).catch((e) => setError(e.message));
  }, [allowed, id]);

  if (!allowed || (id && !profile && !error)) return <Shell><Spinner /></Shell>;

  const isSelf = form.relation === "self";
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const list = (v: string) => v.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      display_name: form.display_name.trim(), relation: form.relation, language: form.language || lang,
      name_on_reports: form.name_on_reports.trim() || null, birth_year: num(form.birth_year), sex: form.sex || null,
      height_cm: num(form.height_cm), weight_kg: num(form.weight_kg), conditions: list(form.conditions),
      medicines: list(form.medicines), pregnant: form.sex === "female" && form.pregnant, diet_type: form.diet_type || null,
      diet_notes: form.diet_notes.trim() || null, family_consent: form.family_consent,
    };
    try {
      await api(id ? `/api/profiles/${id}` : "/api/profiles", id ? "PUT" : "POST", body);
      router.push("/home/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  async function remove() {
    if (!id || !confirm(t("confirm_delete_profile", { name: form.display_name }))) return;
    setBusy(true);
    try {
      await api(`/api/profiles/${id}`, "DELETE");
      router.push("/home/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const label = "mb-1 block text-sm font-medium";
  return (
    <Shell>
      <PageTitle sub={t("profile_sub")}>{id ? t("health_details") : isSelf ? t("add_my_details") : t("add_family_member")}</PageTitle>
      <form onSubmit={save} className="space-y-4">
        <section className={`${card} space-y-3`}>
          <div>
            <label className={label} htmlFor="dn">{t("display_name")}</label>
            <input id="dn" required maxLength={60} className={input} value={form.display_name} onChange={set("display_name")} />
          </div>
          {!isSelf && (
            <div>
              <label className={label} htmlFor="rel">{t("relation")}</label>
              <select id="rel" className={input} value={form.relation} onChange={set("relation")}>
                {RELATIONS.map((r) => <option key={r} value={r}>{t(`relation_${r}` as TKey)}</option>)}
              </select>
            </div>
          )}
          <div>
            <label className={label} htmlFor="nor">{t("name_on_reports")}</label>
            <input id="nor" maxLength={100} className={input} value={form.name_on_reports} onChange={set("name_on_reports")} />
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{t("name_on_reports_help")}</p>
          </div>
          <div>
            <label className={label} htmlFor="lang">{t("their_language")}</label>
            <select id="lang" className={input} value={form.language || lang} onChange={set("language")}>
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
            </select>
          </div>
        </section>

        <section className={`${card} space-y-3`}>
          <h2 className="font-semibold">{t("health_form_title")}</h2>
          <p className="text-xs text-slate-600 dark:text-slate-400">{t("health_form_help")}</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={label} htmlFor="by">{t("birth_year")}</label>
              <input id="by" inputMode="numeric" min={1900} max={2100} type="number" className={input} value={form.birth_year} onChange={set("birth_year")} />
            </div>
            <div>
              <label className={label} htmlFor="sex">{t("sex")}</label>
              <select id="sex" className={input} value={form.sex} onChange={set("sex")}>
                <option value="">{t("not_given")}</option>
                <option value="female">{t("sex_female")}</option>
                <option value="male">{t("sex_male")}</option>
                <option value="other">{t("sex_other")}</option>
              </select>
            </div>
            <div>
              <label className={label} htmlFor="h">{t("height_cm")}</label>
              <input id="h" type="number" step="0.1" min={30} max={250} className={input} value={form.height_cm} onChange={set("height_cm")} />
            </div>
            <div>
              <label className={label} htmlFor="w">{t("weight_kg")}</label>
              <input id="w" type="number" step="0.1" min={1} max={400} className={input} value={form.weight_kg} onChange={set("weight_kg")} />
            </div>
          </div>
          {profile?.bmi && (
            <p className="text-sm">
              {t("bmi_line", { value: profile.bmi.value, band: t(`bmi_${profile.bmi.band}` as TKey) })}{" "}
              <span className="text-xs text-slate-600 dark:text-slate-400">{t("bmi_asian_note")}</span>
            </p>
          )}
          {profile && profile.weights.length > 1 && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              {t("weight_trend")}: {profile.weights.slice(-5).map((w) => `${w.kg} kg (${w.date})`).join(" → ")}
            </p>
          )}
          {form.sex === "female" && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-5 w-5 accent-teal-700" checked={form.pregnant} onChange={set("pregnant")} />
              {t("pregnant")}
            </label>
          )}
          <div>
            <label className={label} htmlFor="cond">{t("conditions")}</label>
            <textarea id="cond" rows={2} className={input} value={form.conditions} onChange={set("conditions")} placeholder={t("conditions_placeholder")} />
          </div>
          <div>
            <label className={label} htmlFor="med">{t("medicines")}</label>
            <textarea id="med" rows={2} className={input} value={form.medicines} onChange={set("medicines")} placeholder={t("medicines_placeholder")} />
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{t("medicines_help")}</p>
          </div>
          <div>
            <label className={label} htmlFor="diet">{t("diet_type")}</label>
            <select id="diet" className={input} value={form.diet_type} onChange={set("diet_type")}>
              <option value="">{t("not_given")}</option>
              {DIETS.map((d) => <option key={d} value={d}>{t(`diet_${d}` as TKey)}</option>)}
            </select>
          </div>
          <div>
            <label className={label} htmlFor="dnotes">{t("diet_notes")}</label>
            <textarea id="dnotes" rows={2} maxLength={500} className={input} value={form.diet_notes} onChange={set("diet_notes")} placeholder={t("diet_notes_placeholder")} />
          </div>
        </section>

        {!isSelf && !id && (
          <label className={`${card} flex items-start gap-3`}>
            <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-teal-700" checked={form.family_consent} onChange={set("family_consent")} />
            <span className="text-sm">{t("family_consent")}</span>
          </label>
        )}
        <ErrorBox message={error} />
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={busy}>{t("save")}</button>
          {id && <button type="button" className={btnDanger} onClick={remove} disabled={busy}>{t("delete_profile")}</button>}
        </div>
      </form>
    </Shell>
  );
}

export default function Page() {
  return <Suspense><ProfileForm /></Suspense>;
}
