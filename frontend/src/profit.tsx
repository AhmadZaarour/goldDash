import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get } from "./api";
import { useLanguage } from "./i18n";
import {
  Busy,
  ErrorBox,
  money,
  ReferenceName,
  Select,
  locationField,
} from "./ui";

interface ProfitReport {
  month: string;
  timezone: string;
  customer_sales_count: number;
  returned_items_count: number;
  sales_usd: string;
  refunds_usd: string;
  net_sales_usd: string;
  gold_value_usd: string;
  making_cost_usd: string;
  restored_cost_usd: string;
  net_cost_usd: string;
  gross_profit_usd: string;
  expenses_usd: string;
  net_profit_usd: string;
  supplier_sales: {
    purity_id: number;
    weight_grams: string;
    settlement_grams: string;
    making_usd: string;
  }[];
  supplier_purchases: {
    purity_id: number;
    gold_grams: string;
    making_usd: string;
  }[];
}

export function MonthlyProfitView() {
  const { t } = useLanguage();
  const now = new Date();
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );
  const [location, setLocation] = useState("");
  const report = useQuery({
    queryKey: ["list", "monthly-profit", month, location],
    queryFn: () =>
      get<ProfitReport>(
        `/insights/monthly-profit?month=${month}${location ? `&location_id=${location}` : ""}`,
      ),
    enabled: /^\d{4}-(0[1-9]|1[0-2])$/.test(month),
  });
  const data = report.data;
  return (
    <section className="panel">
      <h2>{t("Monthly profit")}</h2>
      <p>
        {t(
          "Customer sales valued at the gold price recorded at sale, after making costs and shop expenses.",
        )}
      </p>
      <div className="filters">
        <label>
          {t("Month")}
          <input
            type="month"
            aria-label={t("Month")}
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
        </label>
        <label>
          {t("Location")}
          <Select
            field={{
              ...locationField,
              optional: true,
              filter: undefined,
              required: false,
            }}
            value={location}
            change={setLocation}
          />
        </label>
      </div>
      {!month && <p>{t("Choose a month to see profit.")}</p>}
      {report.isFetching && <Busy />}
      <ErrorBox error={report.error} />
      {data && (
        <>
          <small>
            {t("Reporting timezone")}: <bdi>{data.timezone}</bdi> ·{" "}
            {t("The current month includes transactions recorded so far.")}
          </small>
          <div className="stats">
            {(
              [
                ["Estimated net profit (USD)", data.net_profit_usd],
                ["Gross customer profit (USD)", data.gross_profit_usd],
                ["Shop expenses (USD)", data.expenses_usd],
              ] as const
            ).map(([label, value]) => (
              <div className="stat" key={label}>
                <span>{t(label)}</span>
                <strong dir="ltr">${money(value)}</strong>
              </div>
            ))}
          </div>
          <p>
            {t("Pieces sold")}: {data.customer_sales_count} ·{" "}
            {t("Pieces returned")}: {data.returned_items_count}
          </p>
          <dl className="profit-breakdown">
            {(
              [
                ["Customer sales collected", data.sales_usd],
                ["Less customer refunds", data.refunds_usd],
                ["Net customer sales", data.net_sales_usd],
                ["Gold value at sale", data.gold_value_usd],
                ["Supplier making cost on sold pieces", data.making_cost_usd],
                ["Less cost restored by returns", data.restored_cost_usd],
                ["Net cost of sold pieces", data.net_cost_usd],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{t(label)}</dt>
                <dd dir="ltr">${money(value)}</dd>
              </div>
            ))}
          </dl>
          <p>
            <small>
              {t(
                "Gold value uses the purchase gold-charge grams and the sale gold price. Discounts are already included in collected prices. Returns reverse their original sale valuation in the return month.",
              )}
            </small>
          </p>
          <p>
            <small>
              {t(
                "Supplier payments and owner withdrawals are balance movements, not profit expenses.",
              )}
            </small>
          </p>
          <h3>{t("Supplier trades — separate from profit")}</h3>
          <p>
            {t(
              "Gold stays in its own purity. Supplier USD making charges below are booked amounts, not supplier profit or cash received.",
            )}
          </p>
          <h4>{t("Supplier purchases (pieces and bulk)")}</h4>
          {data.supplier_purchases.length ? (
            data.supplier_purchases.map((row) => (
              <p key={row.purity_id}>
                <ReferenceName resource="goldpurities" value={row.purity_id} />{" "}
                · {t("Gold owed")}: <bdi>{row.gold_grams} g</bdi> ·{" "}
                {t("Making charge (USD)")}: <bdi>${money(row.making_usd)}</bdi>
              </p>
            ))
          ) : (
            <p>{t("No supplier purchases this month.")}</p>
          )}
          <h4>{t("Supplier bulk sales")}</h4>
          {data.supplier_sales.length ? (
            data.supplier_sales.map((row) => (
              <p key={row.purity_id}>
                <ReferenceName resource="goldpurities" value={row.purity_id} />{" "}
                · {t("Weight (g)")}: <bdi>{row.weight_grams}</bdi> ·{" "}
                {t("Gold receivable")}: <bdi>{row.settlement_grams} g</bdi> ·{" "}
                {t("Making charge (USD)")}: <bdi>${money(row.making_usd)}</bdi>
              </p>
            ))
          ) : (
            <p>{t("No supplier bulk sales this month.")}</p>
          )}
        </>
      )}
    </section>
  );
}
