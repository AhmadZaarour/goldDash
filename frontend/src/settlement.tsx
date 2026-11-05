import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import Decimal from "decimal.js";
import { all, get, Operation } from "./api";
import { useWorkspace } from "./session";
import { useLanguage } from "./i18n";
import { useGoldQuote } from "./gold-price";
import {
  Fields,
  ErrorBox,
  money,
  date,
  locationField,
  type Values,
} from "./ui";

export type SupplierBalance = {
  making_usd: string;
  gold_24k: string;
  gold_grams_by_purity: Record<string, string>;
  is_settled: boolean;
};
export function SupplierSettlement({
  supplierId,
  balance,
  done,
}: {
  supplierId: number;
  balance: SupplierBalance;
  done: () => void;
}) {
  const { t } = useLanguage();
  const workspace = useWorkspace();
  const [values, set] = useState<Values>({
    direction: "sent",
    gold_grams: "0",
    making_usd: "0",
    cash_gold_usd: "0",
    placement: workspace === "showroom" ? "showroom" : "factory",
  });
  const [closeAccount, setCloseAccount] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const quote = useGoldQuote();
  const suggested = useRef(false);
  const purities = useQuery({
    queryKey: ["list", "settlement-purities"],
    queryFn: () => all("/goldpurities"),
  });
  const available = useQuery({
    queryKey: [
      "list",
      "settlement-available",
      supplierId,
      values.location_id,
      values.placement,
    ],
    queryFn: () =>
      get<{ cash_usd: string; gold_grams_by_purity: Record<string, string> }>(
        `/suppliers/${supplierId}/availability?location_id=${values.location_id}&placement=${values.placement}`,
      ),
    enabled: !!values.location_id,
  });
  useEffect(() => {
    if (quote.data && !quote.data.stale && !suggested.current) {
      suggested.current = true;
      set((current) =>
        current.gold_price_usd
          ? current
          : {
              ...current,
              gold_price_usd: new Decimal(quote.data.gram_24k_usd).toFixed(4),
            },
      );
    }
  }, [quote.data]);
  let valid = false,
    full = false,
    insufficient = false;
  let gold = new Decimal(0),
    cashGold = new Decimal(0),
    usd = new Decimal(0),
    afterGold = new Decimal(balance.gold_24k),
    afterUsd = new Decimal(balance.making_usd);
  const selected = purities.data?.find(
    (p) => String(p.id) === String(values.purity_id),
  );
  try {
    gold = new Decimal(String(values.gold_grams || 0));
    usd = new Decimal(String(values.making_usd || 0));
    cashGold = new Decimal(String(values.cash_gold_usd || 0));
    const rate = new Decimal(String(values.gold_price_usd || 0));
    const cleared = gold
      .times(String(selected?.repayment_factor || 0))
      .plus(cashGold.gt(0) && rate.gt(0) ? cashGold.div(rate) : 0)
      .toDecimalPlaces(3, Decimal.ROUND_HALF_UP);
    const sign = values.direction === "sent" ? -1 : 1;
    afterGold = afterGold.plus(cleared.times(sign));
    afterUsd = afterUsd.plus(usd.times(sign));
    valid =
      gold.gte(0) &&
      usd.gte(0) &&
      cashGold.gte(0) &&
      (cleared.gt(0) || usd.gt(0)) &&
      (!gold.gt(0) || !!selected) &&
      (!cashGold.gt(0) || rate.gt(0));
    full = afterGold.isZero() && afterUsd.isZero();
    insufficient =
      values.direction === "sent" &&
      !!available.data &&
      (usd.plus(cashGold).gt(available.data.cash_usd) ||
        gold.gt(
          available.data.gold_grams_by_purity[String(values.purity_id)] || 0,
        ));
  } catch {
    valid = false;
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        `/suppliers/${supplierId}/settlements`,
        {
          direction: values.direction,
          location_id: Number(values.location_id),
          placement: values.placement,
          purity_id: values.purity_id ? Number(values.purity_id) : null,
          gold_grams: gold.toString(),
          making_usd: usd.toString(),
          cash_gold_usd: cashGold.toString(),
          gold_price_usd: values.gold_price_usd || null,
          close_account: closeAccount,
        },
        "POST",
        false,
        true,
      );
      done();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <Fields
          fields={[
            {
              key: "direction",
              label: "Direction",
              type: "select",
              options: ["sent", "received"],
              required: true,
            },
            locationField,
            {
              key: "placement",
              label: "Placement",
              type: "select",
              options: ["factory", "showroom"],
              required: true,
            },
            {
              key: "purity_id",
              label: "Payment purity",
              type: "select",
              resource: "goldpurities",
              required: gold.gt(0),
              optional: true,
            },
            ...[
              ["gold_grams", "Physical gold (g)"],
              ["making_usd", "Making charge (USD)"],
              ["cash_gold_usd", "Cash for gold (USD)"],
            ].map(([key, label]) => ({
              key,
              label,
              type: "money" as const,
              required: true,
            })),
            {
              key: "gold_price_usd",
              label: "USD per 24K-equivalent gram",
              type: "money",
              required: cashGold.gt(0),
            },
          ]}
          values={values}
          set={(next) => {
            set(next);
            setCloseAccount(false);
          }}
        />
        {quote.data && (
          <p>
            {t(
              quote.data.stale || quote.isError
                ? "Stale quote"
                : "Latest quote",
            )}
            : ${money(quote.data.gram_24k_usd)} · {date(quote.data.fetched_at)}
          </p>
        )}
        <section className="panel">
          <h3>{t("Settlement preview")}</h3>
          <p>
            {t("Available cash")}: ${money(available.data?.cash_usd)}
          </p>
          <p>
            {t("Available bulk gold")}:{" "}
            {available.data?.gold_grams_by_purity[String(values.purity_id)] ||
              "0.000"}{" "}
            g
          </p>
          <p>
            {t("Repayment factor")}: {String(selected?.repayment_factor || "—")}
          </p>
          <p>
            {t("Gold debt (24K equivalent g)")}:{" "}
            <bdi>
              {balance.gold_24k} → {afterGold.toFixed(3)}
            </bdi>
          </p>
          <p>
            {t("USD balance before / after")}:{" "}
            <bdi>
              {balance.making_usd} → {afterUsd.toFixed(2)}
            </bdi>
          </p>
          <p>
            {t("Total cash payment (USD)")}: $
            {money(usd.plus(cashGold).toString())}
          </p>
          <p>
            {t(
              full
                ? "This payment fully settles the account."
                : "The account will remain outstanding.",
            )}
          </p>
          {insufficient && (
            <p role="alert">
              {t("Not enough cash or bulk gold at this location.")}
            </p>
          )}
          <label>
            <input
              type="checkbox"
              checked={closeAccount}
              disabled={!valid || !full || insufficient}
              onChange={(e) => setCloseAccount(e.target.checked)}
            />
            {t("Settle account in full")}
          </label>
        </section>
      </fieldset>
      <ErrorBox error={error || available.error || purities.error} />
      <footer>
        <button
          disabled={
            busy ||
            !valid ||
            !available.data ||
            available.isFetching ||
            insufficient ||
            (closeAccount && !full)
          }
        >
          {t(busy ? "Working…" : "Record settlement")}
        </button>
      </footer>
    </form>
  );
}
