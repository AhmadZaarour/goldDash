import { useQuery } from "@tanstack/react-query";
import { get, type Row } from "./api";
import { useLanguage } from "./i18n";
import { Busy, ErrorBox, money, text } from "./ui";

export function ItemCostLabel({ item }: { item: Row }) {
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
        <strong dir="ltr">${money(item.base_cost_usd)}</strong>
      </div>
      <small>
        {t(
          "Cash equivalent at purchase gold price, including gold charge and supplier making charge.",
        )}
      </small>
    </section>
  );
}

export function SaleItemCost({ itemId }: { itemId: string }) {
  const query = useQuery({
    queryKey: ["list", "item-cost", itemId],
    queryFn: () => get<Row>(`/inventory/items/${itemId}`),
  });
  return (
    <>
      {query.isFetching && <Busy />}
      <ErrorBox error={query.error} />
      {query.data && (
        <>
          <p>
            {text(query.data.product_name)} ·{" "}
            <bdi className="mono">{text(query.data.barcode)}</bdi>
          </p>
          <ItemCostLabel item={query.data} />
        </>
      )}
    </>
  );
}
