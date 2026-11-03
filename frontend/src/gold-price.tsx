import { useQuery } from "@tanstack/react-query";
import { get } from "./api";
import { useLanguage } from "./i18n";
import { Busy, ErrorBox, money, date } from "./ui";

export interface GoldQuote {
  ounce_usd: string;
  gram_24k_usd: string;
  gram_21k_usd: string;
  gram_18k_usd: string;
  fetched_at: string;
  stale: boolean;
}
export function useGoldQuote(enabled = true) {
  return useQuery({
    queryKey: ["gold-price"],
    queryFn: () => get<GoldQuote>("/gold-price"),
    enabled,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}
export function GoldPrice() {
  const { t } = useLanguage();
  const quote = useGoldQuote();
  const stale =
    quote.data?.stale ||
    quote.isError ||
    (quote.data && Date.now() - Date.parse(quote.data.fetched_at) >= 30_000);
  return (
    <section className="panel">
      <h2>{t("Live gold price")}</h2>
      {quote.isLoading && <Busy />}
      <ErrorBox error={quote.error} />
      {quote.data && (
        <>
          <div className="stats">
            {(
              [
                ["24K ounce (USD)", "ounce_usd"],
                ["24K gram (USD)", "gram_24k_usd"],
                ["21K gram (USD)", "gram_21k_usd"],
                ["18K gram (USD)", "gram_18k_usd"],
              ] as const
            ).map(([label, key]) => (
              <div className="stat compact" key={key}>
                <span>{t(label)}</span>
                <strong dir="ltr">${money(quote.data[key])}</strong>
              </div>
            ))}
          </div>
          <p role="status">
            {t(stale ? "Stale quote" : "Latest quote")} ·{" "}
            {date(quote.data.fetched_at)}
          </p>
        </>
      )}
    </section>
  );
}
