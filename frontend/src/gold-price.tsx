import { useState, useRef, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js";
import { get, Operation, type Row } from "./api";
import { useLanguage } from "./i18n";
import { useCan } from "./session";
import { Busy, ErrorBox, money, date, Modal, Form } from "./ui";

const quoteRefreshInterval = 30_000;

export interface GoldQuote {
  ounce_usd: string;
  gram_24k_usd: string;
  gram_21k_usd: string;
  gram_18k_usd: string;
  fetched_at: string;
  stale: boolean;
  quote_mode?: "live" | "manual";
  market_ounce_usd?: string;
  ounce_adjustment_usd?: string;
  applied_ounce_usd?: string;
  customer_buy?: GoldQuote & { available: boolean; error?: string };
  customer_sell?: GoldQuote & { available: boolean; error?: string };
}

type GoldPriceSettings = {
  buy_adjustment_usd: string;
  sell_adjustment_usd: string;
  manual_ounce_usd?: string | null;
};

function useGoldPriceSettings() {
  return useQuery({
    queryKey: ["gold-price-settings"],
    queryFn: () => get<GoldPriceSettings>("/gold-price/settings"),
  });
}

export function useGoldQuote(enabled = true) {
  return useQuery({
    queryKey: ["gold-price"],
    queryFn: () => get<GoldQuote>("/gold-price"),
    enabled,
    staleTime: quoteRefreshInterval,
    refetchInterval: quoteRefreshInterval,
  });
}

export function isFreshQuote(quote: GoldQuote | undefined): quote is GoldQuote {
  return (
    !!quote &&
    !quote.stale &&
    (quote.quote_mode === "manual" ||
      Date.now() - Date.parse(quote.fetched_at) < quoteRefreshInterval)
  );
}

export function GoldPrice() {
  const { t } = useLanguage();
  const can = useCan();
  const [editing, setEditing] = useState(false);
  const [editingQuoteMode, setEditingQuoteMode] = useState(false);
  const [saved, setSaved] = useState(false);
  const quote = useGoldQuote();
  const manual = !quote.isError && quote.data?.quote_mode === "manual";
  const stale = quote.isError || !isFreshQuote(quote.data);
  return (
    <section className="panel">
      <h2>{t(manual ? "Manual gold price" : "Live gold price")}</h2>
      {can.admin && (
        <div className="actions">
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setSaved(false);
              setEditing(true);
            }}
          >
            {t("Customer price adjustments")}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => setEditingQuoteMode(true)}
          >
            {t("Gold quote settings")}
          </button>
        </div>
      )}
      {saved && <p role="status">{t("Customer price adjustments saved")}</p>}
      {editing && (
        <Modal
          title="Customer price adjustments"
          close={() => setEditing(false)}
        >
          <PriceSettingsForm
            done={() => {
              setEditing(false);
              setSaved(true);
            }}
          />
        </Modal>
      )}
      {editingQuoteMode && (
        <Modal
          title="Gold quote settings"
          close={() => setEditingQuoteMode(false)}
        >
          <QuoteModeSettings done={() => setEditingQuoteMode(false)} />
        </Modal>
      )}
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
          <div className="table-wrap">
            <table aria-label={t("Customer gold prices")}>
              <thead>
                <tr>
                  {[
                    "Customer price",
                    "Ounce adjustment (USD)",
                    "Adjusted ounce (USD)",
                    "24K gram (USD)",
                    "21K gram (USD)",
                    "18K gram (USD)",
                  ].map((label) => (
                    <th key={label}>{t(label)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(["buy", "sell"] as const).map((direction) => {
                  const profile = customerQuote(quote.data, direction);
                  const offset =
                    (direction === "buy"
                      ? quote.data?.customer_buy
                      : quote.data?.customer_sell
                    )?.ounce_adjustment_usd || "0";
                  return (
                    <tr key={direction}>
                      <td data-label={t("Customer price")}>
                        {t(
                          direction === "buy"
                            ? "Customer buying"
                            : "Customer selling",
                        )}
                      </td>
                      <td dir="ltr" data-label={t("Ounce adjustment (USD)")}>
                        {money(offset)}
                      </td>
                      {profile ? (
                        <>
                          <td dir="ltr" data-label={t("Adjusted ounce (USD)")}>
                            {money(profile.ounce_usd)}
                          </td>
                          {(
                            [
                              ["gram_24k_usd", "24K gram (USD)"],
                              ["gram_21k_usd", "21K gram (USD)"],
                              ["gram_18k_usd", "18K gram (USD)"],
                            ] as const
                          ).map(([key, label]) => (
                            <td dir="ltr" key={key} data-label={t(label)}>
                              {new Decimal(profile[key]).toFixed(4)}
                            </td>
                          ))}
                        </>
                      ) : (
                        <td colSpan={4}>
                          {t(
                            "Customer price unavailable. Review the ounce adjustment.",
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p role="status">
            {t(
              manual
                ? "Manual gold quote"
                : stale
                  ? "Stale quote"
                  : "Latest quote",
            )}{" "}
            · {date(quote.data.fetched_at)}
          </p>
        </>
      )}
    </section>
  );
}

export function gramPrice(
  quote: GoldQuote | undefined,
  purity: Row | undefined,
) {
  if (!quote || !purity) return "—";
  const factor =
    Number(purity.karat) === 24
      ? new Decimal(1)
      : new Decimal(String(purity.purity)).div("99.5");
  return new Decimal(quote.gram_24k_usd)
    .times(factor)
    .toFixed(4, Decimal.ROUND_HALF_UP);
}

export function customerQuote(
  quote: GoldQuote | undefined,
  direction: "buy" | "sell",
): GoldQuote | undefined {
  if (!quote) return undefined;
  const profile =
    direction === "buy" ? quote.customer_buy : quote.customer_sell;
  return profile?.available === false ? undefined : profile || quote;
}

function QuoteModeSettings({ done }: { done: () => void }) {
  const settings = useGoldPriceSettings();
  return (
    <>
      <ErrorBox error={settings.error} />
      {settings.isLoading && <Busy />}
      {settings.data && (
        <QuoteModeForm
          initialOunce={settings.data.manual_ounce_usd}
          done={done}
        />
      )}
    </>
  );
}

function QuoteModeForm({
  initialOunce,
  done,
}: {
  initialOunce: string | null | undefined;
  done: () => void;
}) {
  const { t } = useLanguage();
  const q = useQueryClient();
  const op = useRef(new Operation());
  const [manual, setManual] = useState(!!initialOunce);
  const [ounce, setOunce] = useState(initialOunce ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const settings = await op.current.send<GoldPriceSettings>(
        "/gold-price/quote-mode",
        { manual_ounce_usd: manual ? ounce : null },
        "PUT",
      );
      q.setQueryData(["gold-price-settings"], settings);
      void q.resetQueries({ queryKey: ["gold-price"] });
      done();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <div className="form-grid">
          <label>
            {t("Quote source")}
            <select
              value={manual ? "manual" : "live"}
              onChange={(event) => setManual(event.target.value === "manual")}
            >
              <option value="live">{t("Refresh live quote")}</option>
              <option value="manual">{t("Use a manual quote")}</option>
            </select>
          </label>
          {manual && (
            <label>
              {t("Manual 24K ounce (USD)")}
              <input
                type="number"
                min="0.000001"
                step="0.000001"
                required
                value={ounce}
                onChange={(event) => setOunce(event.target.value)}
              />
            </label>
          )}
        </div>
      </fieldset>
      <ErrorBox error={error} />
      <footer>
        <button type="submit" disabled={busy}>
          {t(busy ? "Working…" : "Save")}
        </button>
      </footer>
    </form>
  );
}

function PriceSettingsForm({ done }: { done: () => void }) {
  const { t } = useLanguage();
  const q = useQueryClient();
  const settings = useGoldPriceSettings();
  const op = useRef(new Operation());
  return (
    <>
      <p>
        {t(
          "These adjustments apply to customer prices in this workspace. Enter a negative number to subtract from the market ounce price.",
        )}
      </p>
      <ErrorBox error={settings.error} />
      {settings.isLoading && <Busy />}
      {settings.data && (
        <Form
          fields={[
            {
              key: "buy_adjustment_usd",
              label: "Buying ounce adjustment (USD)",
              type: "number",
              step: "0.01",
              required: true,
            },
            {
              key: "sell_adjustment_usd",
              label: "Selling ounce adjustment (USD)",
              type: "number",
              step: "0.01",
              required: true,
            },
          ]}
          initial={{
            buy_adjustment_usd: settings.data.buy_adjustment_usd,
            sell_adjustment_usd: settings.data.sell_adjustment_usd,
          }}
          submit={(v) => op.current.send("/gold-price/settings", v, "PUT")}
          done={() => {
            void q.invalidateQueries();
            done();
          }}
        />
      )}
    </>
  );
}
