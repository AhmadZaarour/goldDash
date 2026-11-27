import { useQuery } from "@tanstack/react-query";
import Decimal from "decimal.js";
import { get, type Row } from "./api";
import { gramPrice, type GoldQuote } from "./gold-price";
import { useLanguage } from "./i18n";
import { Busy, ErrorBox, money, text } from "./ui";

export function ItemCostLabel({
  item,
  liveBaseCost,
}: {
  item: Row;
  liveBaseCost?: string;
}) {
  const { t } = useLanguage();
  return (
    <section
      className="piece-cost-label"
      aria-label={t("Piece cost reference")}
    >
      <div>
        <span>{t("Total weight (g)")}</span>
        <strong dir="ltr">{text(item.weight)} g</strong>
      </div>
      <div>
        <span>{t("Base cost (USD)")}</span>
        <strong dir="ltr">
          {liveBaseCost ?? `$${money(item.base_cost_usd)}`}
        </strong>
      </div>
      {item.gold_charge_24k != null && (
        <div>
          <span>{t("Gold charge (24K equivalent g)")}</span>
          <strong dir="ltr">{text(item.gold_charge_24k)} g</strong>
        </div>
      )}
      <small>
        {t(
          liveBaseCost === undefined
            ? "Cash equivalent at purchase gold price, including gold charge and supplier making charge."
            : "Gold value at the current selling quote plus the piece’s making charge.",
        )}
      </small>
    </section>
  );
}

export function ReadOnlyGoldPrice({ price }: { price: string }) {
  const { t } = useLanguage();
  return (
    <p>
      {t("Gold price / gram")}{" "}
      <output aria-label={t("Calculated gold price / gram")} dir="ltr">
        {price}
      </output>{" "}
      USD
    </p>
  );
}

export function SaleItemCost({
  itemId,
  quote,
  purities,
}: {
  itemId: string;
  quote: GoldQuote | undefined;
  purities: Row[];
}) {
  const query = useQuery({
    queryKey: ["list", "item-cost", itemId],
    queryFn: () => get<Row>(`/inventory/items/${itemId}/sale-cost`),
  });
  const item = query.data;
  const purity = purities.find((p) => p.id === item?.purity_id);
  const price = gramPrice(quote, purity);
  let liveBaseCost = "—";
  if (item?.base_making_usd != null && quote) {
    const exactWeight = item.base_gold_24k;
    if (exactWeight != null || price !== "—") {
      const weight = String(exactWeight ?? item.weight);
      const rate = exactWeight != null ? quote.gram_24k_usd : price;
      const total = new Decimal(weight)
        .times(rate)
        .plus(String(item.base_making_usd))
        .toFixed(2, Decimal.ROUND_HALF_UP);
      liveBaseCost = `$${money(total)}`;
    }
  }
  return (
    <>
      <ReadOnlyGoldPrice price={price} />
      {query.isFetching && <Busy />}
      <ErrorBox error={query.error} />
      {item && (
        <>
          <p>
            {text(item.product_name)} ·{" "}
            <bdi className="mono">{text(item.barcode)}</bdi>
          </p>
          <ItemCostLabel item={item} liveBaseCost={liveBaseCost} />
        </>
      )}
    </>
  );
}
