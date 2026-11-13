import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Plus,
  ArrowUpRight,
  Camera,
  Package,
  Coins,
  Users,
} from "lucide-react";
import Decimal from "decimal.js";
import { WorkspaceSummary } from "./operations";
import { DevelopmentReset } from "./development";
import { ServiceSaleButton } from "./servicing";
import { BarcodeScanButton } from "./barcode-scanner";
import { normalizeBarcode } from "./barcode-camera";
import { ItemCostLabel, SaleItemCost } from "./item-cost";
import { SupplierSettlement, type SupplierBalance } from "./settlement";
import {
  GoldPrice,
  useGoldQuote,
  gramPrice,
  type GoldQuote,
} from "./gold-price";
import { MonthlyProfitView } from "./profit";
import { all, get, request, raw, list, Operation, type Row } from "./api";
import { useLanguage } from "./i18n";
import { useCan, useUser, useWorkspace } from "./session";
import {
  DataList,
  Modal,
  Form,
  Fields,
  Select,
  ReferenceName,
  ErrorBox,
  Busy,
  Badge,
  text,
  money,
  date,
  toPayload,
  locationField,
  supplierField,
  type Field,
  type Values,
  type Column,
} from "./ui";

const name: Field = {
  key: "name",
  label: "Name",
  required: true,
  maxLength: 50,
};
const phone: Field = { key: "phone", label: "Phone", maxLength: 20 };
const note: Field = { key: "notes", label: "Notes", type: "textarea" };
const product = (kind?: string): Field => ({
  key: "product_id",
  label: "Product",
  type: "select",
  resource: "products",
  required: true,
  filter: (r) => !kind || r.inventory_type === kind,
});
const purity: Field = {
  key: "purity_id",
  label: "Purity",
  type: "select",
  resource: "goldpurities",
  required: true,
};
const amount = (key: string, label: string, required = true): Field => ({
  key,
  label,
  type: "money",
  required,
});
const clean = (r: Row): Values =>
  Object.fromEntries(
    Object.entries(r).map(([k, v]) => [
      k,
      typeof v === "boolean" ? v : v == null ? "" : String(v),
    ]),
  );
function useDone(close: () => void) {
  const q = useQueryClient();
  return () => {
    void q.invalidateQueries();
    close();
  };
}
export function PageHead({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  const { t } = useLanguage();
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{t("Shop workspace")}</div>
        <h1>{t(title)}</h1>
        {description && <p>{t(description)}</p>}
      </div>
      {action}
    </div>
  );
}
export function Photo({ url }: { url: unknown }) {
  const [source, setSource] = useState("");
  useEffect(() => {
    let live = true;
    let object = "";
    const value = String(url || "");
    if (!value) return;
    const parsed = new URL(value, location.origin);
    if (parsed.pathname.startsWith("/api/v1/media/items/")) {
      raw(parsed.pathname.replace("/api/v1", ""))
        .then((r) => r.blob())
        .then((blob) => {
          object = URL.createObjectURL(blob);
          if (live) setSource(object);
        })
        .catch(() => {});
    } else if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      setSource(value);
    }
    return () => {
      live = false;
      if (object) URL.revokeObjectURL(object);
    };
  }, [url]);
  const { t } = useLanguage();
  return source ? (
    <img
      className="piece-photo"
      src={source}
      alt={t("Photo")}
      referrerPolicy="no-referrer"
    />
  ) : (
    <div className="photo-placeholder">
      <Package size={26} />
      <span>{t("No image")}</span>
    </div>
  );
}

export function Dashboard() {
  const workspace = useWorkspace();
  const { t } = useLanguage();
  const u = useUser();
  const can = useCan();
  const [loc, setLoc] = useState("");
  const inv = useQuery({
    queryKey: ["list", "dashboard-inventory"],
    queryFn: () => list("/inventory/items", { status: "in_stock", limit: 1 }),
  });
  const suppliers = useQuery({
    queryKey: ["list", "dashboard-suppliers"],
    queryFn: () => list("/suppliers", { limit: 1 }),
  });
  const cash = useQuery({
    queryKey: ["list", "dashboard-cash", loc],
    queryFn: () => get<Row>("/cash/summary?location_id=" + loc),
    enabled: can.cashier && !!loc,
  });
  return (
    <>
      <PageHead title="Overview" description="A clear view of your shop" />
      <div className="hero">
        <div>
          <span className="eyebrow">GOLDDASH / {t("Daily operations")}</span>
          <h2>{t("Track every gram. Account for every dollar.")}</h2>
          <p>
            {u.username} · {t(u.role)}
          </p>
          <Link className="button light" to="/inventory">
            {t("Open")} {t("Inventory")}
            <ArrowUpRight size={17} />
          </Link>
        </div>
        <div className="hero-mark" aria-hidden="true">
          G<span>24</span>
        </div>
      </div>
      <div className="stats">
        <div className="stat">
          <Package />
          <span>{t("Available pieces")}</span>
          <strong>{inv.data?.total ?? "—"}</strong>
        </div>
        <div className="stat">
          <Users />
          <span>{t("Supplier accounts")}</span>
          <strong>{suppliers.data?.total ?? "—"}</strong>
        </div>
        <div className="stat">
          <Coins />
          <span>{t("Current location")}</span>
          <Select
            field={{ ...locationField, filter: undefined }}
            value={loc}
            change={setLoc}
          />
          {can.cashier && loc && (
            <strong dir="ltr">${money(cash.data?.net_usd)}</strong>
          )}
        </div>
      </div>
      <GoldPrice />
      {can.admin && workspace === "showroom" && <MonthlyProfitView />}
      <WorkspaceSummary showPieces={false} />
      <section className="panel">
        <h2>{t("Quick actions")}</h2>
        <div className="quick-links">
          {[
            ["/inventory", "Inventory"],
            ...(can.cashier
              ? [
                  ["/sales", "New sale"],
                  ["/cash", "Cash drawer"],
                ]
              : []),
            ...(can.admin
              ? [
                  ["/purchases", "New purchase"],
                  ["/suppliers", "Supplier balances"],
                ]
              : []),
          ].map(([to, label]) => (
            <Link key={to} to={to}>
              {t(label)}
              <ArrowUpRight size={18} />
            </Link>
          ))}
        </div>
      </section>
      {can.admin && <DevelopmentReset />}
      <ErrorBox error={inv.error || suppliers.error || cash.error} />
    </>
  );
}

const catalogs: Record<
  string,
  { title: string; fields: Field[]; columns: Column[] }
> = {
  products: {
    title: "Products",
    fields: [
      { key: "sku", label: "SKU", required: true, maxLength: 50 },
      name,
      { key: "description", label: "Description", type: "textarea" },
      {
        key: "category_id",
        label: "Category",
        type: "select",
        resource: "categories",
        required: true,
      },
      purity,
      {
        key: "inventory_type",
        label: "Type",
        type: "select",
        options: ["item", "bulk"],
        required: true,
      },
    ],
    columns: [
      { key: "sku", label: "SKU" },
      { key: "name", label: "Name" },
      {
        key: "inventory_type",
        label: "Type",
        render: (r) => <Badge value={r.inventory_type} />,
      },
    ],
  },
  categories: {
    title: "Categories",
    fields: [
      name,
      { key: "description", label: "Description", type: "textarea" },
    ],
    columns: [
      { key: "name", label: "Name" },
      { key: "description", label: "Description" },
    ],
  },
  goldpurities: {
    title: "Gold purities",
    fields: [
      name,
      {
        key: "karat",
        label: "Karat",
        type: "number",
        min: "1",
        required: true,
      },
      {
        key: "purity",
        label: "Purity (%)",
        type: "number",
        min: "0",
        required: true,
      },
      {
        key: "repayment_factor",
        label: "Repayment factor",
        type: "number",
        min: "0",
        step: "0.000001",
      },
    ],
    columns: [
      { key: "name", label: "Name" },
      { key: "karat", label: "Karat" },
      { key: "purity", label: "Purity (%)" },
      { key: "repayment_factor", label: "Repayment factor" },
    ],
  },
  locations: {
    title: "Locations",
    fields: [
      name,
      { key: "code", label: "Code", required: true, maxLength: 50 },
      { key: "address", label: "Address", maxLength: 200 },
      { key: "is_active", label: "Active", type: "checkbox" },
    ],
    columns: [
      { key: "name", label: "Name" },
      { key: "code", label: "Code" },
      {
        key: "is_active",
        label: "Status",
        render: (r) => <Badge value={r.is_active} />,
      },
    ],
  },
  customers: {
    title: "Customers",
    fields: [name, { ...phone, maxLength: 50 }],
    columns: [
      { key: "name", label: "Name" },
      { key: "phone", label: "Phone" },
    ],
  },
  suppliers: {
    title: "Suppliers",
    fields: [
      name,
      { ...phone, required: true },
      { key: "is_active", label: "Active", type: "checkbox" },
    ],
    columns: [
      { key: "name", label: "Name" },
      { key: "phone", label: "Phone" },
      {
        key: "is_active",
        label: "Status",
        render: (r) => <Badge value={r.is_active} />,
      },
    ],
  },
};
export function Catalog() {
  const { t } = useLanguage();
  const can = useCan();
  const [tab, setTab] = useState("products");
  const [editing, setEditing] = useState<Row | null | undefined>();
  const config = catalogs[tab];
  const op = useRef(new Operation());
  const done = useDone(() => setEditing(undefined));
  const editable = can.admin || tab === "customers";
  return (
    <>
      <PageHead
        title="Catalog"
        action={
          editable && (
            <button onClick={() => setEditing(null)}>
              <Plus size={17} />
              {t("Create")}
            </button>
          )
        }
      />
      <div className="tabs">
        {Object.entries(catalogs)
          .filter(([k]) => k !== "suppliers")
          .map(([k, c]) => (
            <button
              key={k}
              className={tab === k ? "selected" : ""}
              onClick={() => {
                setTab(k);
                setEditing(undefined);
              }}
            >
              {t(c.title)}
            </button>
          ))}
      </div>
      <section className="panel">
        <DataList
          key={tab}
          path={"/" + tab}
          columns={config.columns}
          edit={editable ? setEditing : undefined}
        />
      </section>
      {editing !== undefined && (
        <Modal
          title={editing ? "Edit" : "Create"}
          close={() => setEditing(undefined)}
        >
          <Form
            key={String(editing?.id ?? "new") + tab}
            fields={config.fields}
            initial={editing ? clean(editing) : { is_active: true }}
            submit={(v) =>
              op.current.send(
                "/" + tab + (editing ? "/" + editing.id : ""),
                toPayload(config.fields, v),
                editing ? "PATCH" : "POST",
              )
            }
            done={done}
          />
        </Modal>
      )}
    </>
  );
}

export function Inventory() {
  const { t } = useLanguage();
  const can = useCan();
  const [tab, setTab] = useState("Items");
  const [filters, setFilters] = useState<Values>({});
  const [item, setItem] = useState<Row>();
  const [action, setAction] = useState("");
  const op = useRef(new Operation());
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState<unknown>();
  const done = useDone(() => {
    setAction("");
    setItem(undefined);
  });
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== ""),
  ) as Record<string, string>;
  async function upload(file: File | undefined) {
    if (!file || !item) return;
    setPhotoBusy(true);
    setPhotoError(undefined);
    try {
      await request(`/inventory/items/${item.id}/photo`, {
        method: "POST",
        body: await resizePhoto(file),
        headers: { "Content-Type": "image/jpeg" },
      });
      done();
    } catch (e) {
      setPhotoError(e);
    } finally {
      setPhotoBusy(false);
    }
  }
  return (
    <>
      <PageHead
        title="Inventory"
        description="Amounts are in USD; weights are in grams."
        action={
          can.employee && (
            <button onClick={() => setAction("Bulk transfer")}>
              <ArrowUpRight size={17} />
              {t("Bulk transfer")}
            </button>
          )
        }
      />
      <div className="tabs">
        {["Items", "Bulk balances", "Returns", "Transfers"].map((v) => (
          <button
            key={v}
            className={v === tab ? "selected" : ""}
            onClick={() => {
              setTab(v);
              setFilters({});
            }}
          >
            {t(v)}
          </button>
        ))}
      </div>
      <div className="filters">
        <Fields
          fields={[
            {
              ...locationField,
              required: false,
              optional: true,
              filter: undefined,
            },
            ...(tab === "Items"
              ? [
                  {
                    key: "status",
                    label: "Status",
                    type: "select" as const,
                    options: ["in_stock", "sold"],
                    optional: true,
                  },
                ]
              : []),
          ]}
          values={filters}
          set={setFilters}
        />
      </div>
      <section className="panel">
        {tab === "Items" ? (
          <DataList
            path="/inventory/items"
            params={params}
            columns={[
              {
                key: "barcode",
                label: "Barcode",
                render: (r) => <span className="mono">{text(r.barcode)}</span>,
              },
              { key: "product_name", label: "Product" },
              { key: "weight", label: "Weight (g)" },
              {
                key: "base_cost_usd",
                label: "Base cost (USD)",
                render: (r) => <bdi>${money(r.base_cost_usd)}</bdi>,
              },
              {
                key: "status",
                label: "Status",
                render: (r) => <Badge value={r.status} />,
              },
            ]}
            view={setItem}
          />
        ) : tab === "Bulk balances" ? (
          <DataList
            path="/balance"
            params={params}
            searchable={false}
            columns={[
              { key: "purity_id", label: "Purity" },
              { key: "location_id", label: "Location" },
              {
                key: "placement",
                label: "Placement",
                render: (r) => <Badge value={r.placement} />,
              },
              { key: "total_weight", label: "Weight (g)" },
            ]}
          />
        ) : tab === "Returns" ? (
          <DataList
            path="/inventory/returns"
            params={params}
            searchable={false}
            columns={[
              { key: "id", label: "ID" },
              { key: "sale_id", label: "Sales" },
              { key: "inventory_item_id", label: "Items" },
              { key: "refund_usd", label: "Refund (USD)" },
              {
                key: "created_at",
                label: "Date",
                render: (r) => date(r.created_at),
              },
            ]}
          />
        ) : (
          <>
            <h3>{t("Item transfer")}</h3>
            <DataList
              path="/inventory/transfers/items"
              params={params}
              searchable={false}
              columns={[
                { key: "id", label: "ID" },
                { key: "inventory_item_id", label: "Items" },
                { key: "from_location_id", label: "Source" },
                { key: "to_location_id", label: "Destination" },
                {
                  key: "created_at",
                  label: "Date",
                  render: (r) => date(r.created_at),
                },
              ]}
            />
            <h3>{t("Bulk transfer")}</h3>
            <DataList
              path="/inventory/transfers/stocks"
              params={params}
              searchable={false}
              columns={[
                { key: "id", label: "ID" },
                { key: "purity_id", label: "Purity" },
                { key: "source_location_id", label: "Source" },
                { key: "destination_location_id", label: "Destination" },
                { key: "weight", label: "Weight (g)" },
              ]}
            />
          </>
        )}
      </section>
      {item && !action && (
        <Modal title="Piece details" close={() => setItem(undefined)}>
          <Photo url={item.image_url} />
          <ItemCostLabel item={item} />
          <div className="detail-grid">
            {[
              ["Barcode", "barcode"],
              ["Product", "product_name"],
              ["SKU", "sku"],
              ["Purity", "purity_id"],
              ["Location", "location_id"],
              ["Status", "status"],
            ].map(([label, key]) => (
              <div key={key}>
                <span>{t(label)}</span>
                <strong>
                  {key === "status" ? t(text(item[key])) : text(item[key])}
                </strong>
              </div>
            ))}
          </div>
          <ErrorBox error={photoError} />
          <footer>
            {(can.admin || can.cashier) && (
              <label className="button secondary">
                <Camera size={17} />
                {t(photoBusy ? "Working…" : "Take / choose photo")}
                <input
                  aria-label={t("Take / choose photo")}
                  className="sr-only"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  capture="environment"
                  disabled={photoBusy}
                  onChange={(e) => void upload(e.target.files?.[0])}
                />
              </label>
            )}
            {can.employee && (
              <button
                className="secondary"
                onClick={() => setAction("Update photo")}
              >
                {t("Image URL")}
              </button>
            )}
            {can.employee && item.status === "in_stock" && (
              <button onClick={() => setAction("Item transfer")}>
                {t("Transfer")}
              </button>
            )}
          </footer>
        </Modal>
      )}
      {action && (
        <Modal title={action} close={() => setAction("")}>
          <Form
            fields={
              action === "Update photo"
                ? [{ key: "image_url", label: "Image URL", maxLength: 2048 }]
                : action === "Item transfer"
                  ? [locationField]
                  : [
                      purity,
                      {
                        ...locationField,
                        key: "source_location_id",
                        label: "Source",
                      },
                      {
                        key: "source_placement",
                        label: "Placement",
                        type: "select",
                        options: ["factory", "showroom"],
                        required: true,
                      },
                      {
                        ...locationField,
                        key: "destination_location_id",
                        label: "Destination",
                      },
                      {
                        key: "destination_placement",
                        label: "Placement",
                        type: "select",
                        options: ["factory", "showroom"],
                        required: true,
                      },
                      amount("weight", "Weight (g)"),
                    ]
            }
            initial={
              action === "Update photo"
                ? {
                    image_url:
                      text(item?.image_url) === "—"
                        ? ""
                        : String(item?.image_url ?? ""),
                  }
                : {}
            }
            submit={(v) => {
              if (action === "Update photo")
                return op.current.send(
                  `/inventory/items/${item!.id}/image`,
                  { image_url: v.image_url || null },
                  "PATCH",
                );
              if (action === "Item transfer")
                return op.current.send(
                  `/inventory/items/${item!.id}/transfer`,
                  { location_id: Number(v.location_id) },
                );
              return op.current.send(
                "/inventory/stocks/transfer",
                {
                  purity_id: Number(v.purity_id),
                  source_location_id: Number(v.source_location_id),
                  destination_location_id: Number(v.destination_location_id),
                  source_placement: v.source_placement,
                  destination_placement: v.destination_placement,
                  weight: v.weight,
                },
                "POST",
                true,
              );
            }}
            done={done}
          />
        </Modal>
      )}
    </>
  );
}

function PurchasePhoto({
  value,
  change,
  disabled,
  onBusy,
}: {
  value: Values;
  change: (next: Values) => void;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
}) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    onBusy(true);
    setError(undefined);
    try {
      const result = await request<{ token: string; image_url: string }>(
        "/purchases/photos",
        { method: "POST", body: await resizePhoto(file) },
      );
      change({ photo_token: result.token, photo_preview: result.image_url });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <div>
      {value.photo_preview && <Photo url={value.photo_preview} />}
      <label>
        {t("Take / choose photo")}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          disabled={busy || disabled}
          onChange={(e) => {
            void upload(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
      {busy && <Busy />}
      {value.photo_token && (
        <button
          type="button"
          className="ghost"
          disabled={busy || disabled}
          onClick={() => change({ photo_token: "", photo_preview: "" })}
        >
          {t("Remove photo")}
        </button>
      )}
      <ErrorBox error={error} />
    </div>
  );
}

function ReadOnlyGoldPrice({ price }: { price: string }) {
  const { t } = useLanguage();
  return (
    <p>
      {t("Gold price / gram")}:{" "}
      <output aria-label={t("Calculated gold price / gram")} dir="ltr">
        {price}
      </output>{" "}
      USD
    </p>
  );
}
function SaleLivePrice({
  itemId,
  quote,
  purities,
}: {
  itemId: string;
  quote: GoldQuote | undefined;
  purities: Row[];
}) {
  const item = useQuery({
    queryKey: ["list", "item-cost", itemId],
    queryFn: () => get<Row>(`/inventory/items/${itemId}`),
  });
  return (
    <ReadOnlyGoldPrice
      price={gramPrice(
        quote,
        purities.find((p) => p.id === item.data?.purity_id),
      )}
    />
  );
}

function TradeForm({
  kind,
  done,
}: {
  kind: "itemPurchase" | "customerBulkPurchase" | "customerSale" | "bulkSale";
  done: () => void;
}) {
  const { t } = useLanguage();
  const purchase = kind.endsWith("Purchase");
  const workspace = useWorkspace();
  const customerBulk = kind === "customerBulkPurchase";
  const bulk = kind.startsWith("bulk") || customerBulk;
  const [head, setHead] = useState<Values>({});
  const [lines, setLines] = useState<Values[]>([{}]);
  const [scan, setScan] = useState("");
  const [barcodeLookup, setBarcodeLookup] = useState(false);
  const [barcodeMessage, setBarcodeMessage] = useState("");
  const lookupRequest = useRef<AbortController | null>(null);
  useEffect(() => () => lookupRequest.current?.abort(), []);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const op = useRef(new Operation());
  const quote = useGoldQuote();
  const pricing = useQuery({
    queryKey: ["list", "purchase-pricing"],
    queryFn: async () => {
      const [products, purities] = await Promise.all([
        all("/products"),
        all("/goldpurities"),
      ]);
      return { products, purities };
    },
  });
  const freshQuote =
    !!quote.data &&
    !quote.data.stale &&
    !quote.isError &&
    Date.now() - Date.parse(quote.data.fetched_at) < 30_000;
  function linePrice(productId: unknown) {
    const p = pricing.data?.products.find(
      (p) => String(p.id) === String(productId),
    );
    return gramPrice(
      quote.data,
      pricing.data?.purities.find((k) => k.id === p?.purity_id),
    );
  }

  function makingTotal(rows: Values[]) {
    try {
      return rows
        .reduce(
          (sum, row) =>
            sum.plus(
              new Decimal(String(row.weight || 0)).times(
                String(row.making_charge || 0),
              ),
            ),
          new Decimal(0),
        )
        .toFixed(2, Decimal.ROUND_HALF_UP);
    } catch {
      return "—";
    }
  }

  const headerFields: Field[] = [
    locationField,
    ...(customerBulk
      ? []
      : purchase || kind === "bulkSale"
        ? [supplierField]
        : [
            {
              key: "customer_id",
              label: "Customer",
              type: "select" as const,
              resource: "customers",
              optional: true,
            },
          ]),
    { key: "invoice_number", label: "Invoice number", maxLength: 50 },
    note,
  ];
  const lineFields: Field[] =
    kind === "itemPurchase"
      ? [
          product("item"),
          amount("weight", "Weight (g)"),
          amount("making_charge", "Making charge (USD/g)"),
          { key: "image_url", label: "Image URL", maxLength: 2048 },
        ]
      : customerBulk
        ? [
            product("bulk"),
            amount("weight", "Weight (g)"),
            amount("paid_usd", "Total paid (USD)"),
          ]
        : kind === "bulkSale"
          ? [
              { ...purity, key: "gold_purity_id" },
              amount("weight", "Weight (g)"),
              amount("gold_charge_in_grams", "Gold charge (g)"),
              amount("making_charge", "Making charge (USD)"),
            ]
          : [
              {
                key: "inventory_item_id",
                label: "Product",
                type: "select",
                resource: "inventory/items",
                required: true,
                filter: (r) =>
                  r.status === "in_stock" &&
                  String(r.location_id) === String(head.location_id),
              },
              amount("discount", "Discount (USD)"),
              amount("sell_price", "Final price (USD)"),
            ];
  async function addBarcode(value = scan) {
    if (lookupRequest.current) return;
    setError(undefined);
    setBarcodeMessage("");
    const code = normalizeBarcode(value);
    if (!code) {
      setError(new Error(t("Enter a barcode of 1 to 50 characters.")));
      return;
    }
    if (!head.location_id) {
      setError(new Error(t("Choose a location")));
      return;
    }
    const controller = new AbortController();
    lookupRequest.current = controller;
    setBarcodeLookup(true);
    try {
      const params = new URLSearchParams({
        barcode: code,
        status: "in_stock",
        location_id: String(head.location_id),
        limit: "1",
      });
      const rows = await request<Row[]>(`/inventory/items?${params}`, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!rows.length)
        throw new Error(t("The item was not found at this location."));
      const id = String(rows[0].id);
      setBarcodeMessage(
        t(
          lines.some((line) => String(line.inventory_item_id) === id)
            ? "This item is already in the sale."
            : "Item added to the sale. Enter its final price.",
        ),
      );
      setLines((current) => {
        if (current.some((line) => String(line.inventory_item_id) === id))
          return current;
        const next = { inventory_item_id: id, discount: "0", sell_price: "" };
        return current.length === 1 && !current[0].inventory_item_id
          ? [next]
          : [...current, next];
      });
      setScan("");
    } catch (error) {
      if (!controller.signal.aborted) setError(error);
    } finally {
      if (lookupRequest.current === controller) {
        lookupRequest.current = null;
        setBarcodeLookup(false);
      }
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const payload = toPayload(headerFields, head);
      const converted = lines.map((v) => {
        const row = toPayload(lineFields, v);
        if ((purchase && !bulk) || kind === "bulkSale")
          row.supplier_id = Number(head.supplier_id);
        return row;
      });
      if (kind === "itemPurchase") {
        payload.total_gold_charge_grams = lines
          .reduce(
            (sum, line) => sum.plus(String(line.weight || 0)),
            new Decimal(0),
          )
          .toString();
        converted.forEach((line, index) => {
          if (lines[index].photo_token)
            line.photo_token = lines[index].photo_token;
        });
      }
      if (customerBulk)
        Object.assign(payload, converted[0], { placement: workspace });
      if (kind === "bulkSale") delete payload.supplier_id;
      if (customerBulk) {
        /* flat request; no customer identity */
      } else if (bulk) payload.item = converted[0];
      else payload.items = converted;
      const path = customerBulk
        ? "/purchases/customer-stock"
        : purchase
          ? "/purchases/" + (bulk ? "stock" : "item")
          : "/sales/" + (bulk ? "stock" : "item");
      await op.current.send(path, payload, "POST", purchase);
      done();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  let total = "0.00";
  try {
    total = lines
      .reduce((n, l) => n.plus(String(l.sell_price || 0)), new Decimal(0))
      .toFixed(2);
  } catch {
    /* Incomplete decimal input is validated on submit. */
  }
  return (
    <form onSubmit={submit}>
      <Fields
        fields={headerFields}
        values={head}
        set={(v) => {
          if (v.location_id !== head.location_id && kind === "customerSale") {
            lookupRequest.current?.abort();
            lookupRequest.current = null;
            setBarcodeLookup(false);
            setBarcodeMessage("");
            setScan("");
            setLines([{}]);
          }
          setHead(v);
        }}
      />
      {
        <>
          <p>
            {t(
              "Gold prices are calculated from the live quote when the trade is confirmed.",
            )}
          </p>
          {quote.data && (
            <p>
              {t(freshQuote ? "Latest quote" : "Stale quote")} ·{" "}
              {date(quote.data.fetched_at)}
            </p>
          )}
          <ErrorBox error={quote.error || pricing.error} />
        </>
      }
      {customerBulk && (
        <p>
          {t(
            "Enter 0 USD for opening stock. No cash payment or supplier debt is recorded.",
          )}
        </p>
      )}
      {kind === "itemPurchase" && (
        <p>
          {t("Total gold charge (g)")}:{" "}
          <bdi>
            {lines
              .reduce((sum, line) => {
                try {
                  return sum.plus(String(line.weight || 0));
                } catch {
                  return sum;
                }
              }, new Decimal(0))
              .toFixed(3)}
          </bdi>{" "}
          · {t("Converted to 24K debt by item purity")}
        </p>
      )}
      {kind === "itemPurchase" && (
        <div className="making-total">
          <span>{t("Invoice making charge (USD)")}</span>
          <output aria-label={t("Invoice making charge (USD)")}>
            {makingTotal(lines)}
          </output>
        </div>
      )}
      {kind === "customerSale" && (
        <div className="scan">
          <input
            aria-label={t("Scan or enter barcode")}
            placeholder={t("Scan or enter barcode")}
            value={scan}
            maxLength={50}
            disabled={busy || barcodeLookup}
            onChange={(e) => setScan(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void addBarcode();
              }
            }}
          />
          <button
            type="button"
            className="secondary"
            onClick={() => void addBarcode()}
            disabled={busy || barcodeLookup}
          >
            {t(barcodeLookup ? "Loading…" : "Add")}
          </button>
          <BarcodeScanButton
            disabled={busy || barcodeLookup || !head.location_id}
            onScan={(barcode) => {
              setScan(barcode);
              void addBarcode(barcode);
            }}
          />
        </div>
      )}
      {barcodeMessage && (
        <p role="status" className="notice success">
          {barcodeMessage}
        </p>
      )}
      <fieldset disabled={busy || uploading || barcodeLookup}>
        {lines.map((v, i) => (
          <section className="line-item" key={i}>
            <div className="section-title">
              <h3>
                {t(bulk ? "Details" : "Items")} {bulk ? "" : i + 1}
              </h3>
              {!bulk && lines.length > 1 && (
                <button
                  type="button"
                  className="ghost danger"
                  onClick={() => setLines(lines.filter((_, j) => j !== i))}
                >
                  {t("Remove")}
                </button>
              )}
            </div>
            <Fields
              fields={lineFields}
              values={v}
              set={(next) =>
                setLines(lines.map((x, j) => (j === i ? next : x)))
              }
            />
            {(kind === "itemPurchase" || customerBulk) && (
              <ReadOnlyGoldPrice price={linePrice(v.product_id)} />
            )}
            {kind === "itemPurchase" && (
              <div className="making-total">
                <span>{t("Total making charge (USD)")}</span>
                <output aria-label={t("Total making charge (USD)")}>
                  {makingTotal([v])}
                </output>
              </div>
            )}
            {kind === "bulkSale" && (
              <ReadOnlyGoldPrice
                price={gramPrice(
                  quote.data,
                  pricing.data?.purities.find(
                    (p) => String(p.id) === String(v.gold_purity_id),
                  ),
                )}
              />
            )}
            {kind === "customerSale" && v.inventory_item_id && (
              <SaleLivePrice
                itemId={String(v.inventory_item_id)}
                quote={quote.data}
                purities={pricing.data?.purities || []}
              />
            )}
            {kind === "itemPurchase" && (
              <PurchasePhoto
                value={v}
                disabled={busy || uploading}
                onBusy={setUploading}
                change={(next) =>
                  setLines((current) =>
                    current.map((line, index) =>
                      index === i ? { ...line, ...next } : line,
                    ),
                  )
                }
              />
            )}
            {kind === "customerSale" && v.inventory_item_id && (
              <SaleItemCost itemId={String(v.inventory_item_id)} />
            )}
          </section>
        ))}
        {!bulk && (
          <button
            type="button"
            className="secondary"
            onClick={() => setLines([...lines, {}])}
          >
            <Plus size={16} />
            {t("Add piece")}
          </button>
        )}
      </fieldset>
      {kind === "customerSale" && (
        <div className="checkout-total">
          <span>{t("Cash collected")}</span>
          <strong dir="ltr">${total}</strong>
          <small>{t("Final prices already include the discount.")}</small>
        </div>
      )}
      <ErrorBox error={error} />
      <footer>
        <span className="muted small">
          {t("Keep this window open and retry after a connection failure.")}
        </span>
        <button
          disabled={
            busy || uploading || barcodeLookup || !freshQuote || !pricing.data
          }
        >
          {t(busy ? "Working…" : "Confirm")}
        </button>
      </footer>
    </form>
  );
}

function TradeDetail({
  record,
  purchase,
  close,
}: {
  record: Row;
  purchase: boolean;
  close: () => void;
}) {
  const { t } = useLanguage();
  const can = useCan();
  const [returnLine, setReturnLine] = useState<Row>();
  const op = useRef(new Operation());
  const done = useDone(() => setReturnLine(undefined));
  const q = useQuery<Row[]>({
    queryKey: ["list", "trade-detail", purchase, record.id],
    queryFn: async () => {
      const rows = await get<Row[]>(
        (purchase ? "/purchases/items/" : "/sales/item/") + record.id,
      );
      if (rows.length) {
        if (purchase) {
          const inv = await list("/inventory/items", {
            purchase_id: record.id,
            limit: 100,
          });
          return rows.map((r) => ({
            ...r,
            barcode: inv.rows.find((i) => i.purchase_item_id === r.id)?.barcode,
          }));
        }
        return rows;
      }
      return [
        await get<Row>(
          (purchase ? "/purchases/stock/" : "/sales/stock/") + record.id,
        ),
      ];
    },
  });
  return (
    <Modal title="Details" close={close}>
      <div className="detail-grid">
        <div>
          <span>{t("Invoice number")}</span>
          <strong>{text(record.invoice_number ?? record.id)}</strong>
        </div>
        <div>
          <span>{t("Location")}</span>
          <strong>{text(record.location_id)}</strong>
        </div>
        <div>
          <span>{t("Date")}</span>
          <strong>{date(record.created_at)}</strong>
        </div>
      </div>
      {purchase && ["customer", "opening"].includes(String(record.source)) && (
        <p>
          {t("Total paid (USD)")}: ${money(record.paid_usd)}
        </p>
      )}
      <ErrorBox error={q.error} />
      {q.isLoading ? (
        <Busy />
      ) : (
        q.data?.map((row) => (
          <div className="line-item" key={row.id}>
            <div className="detail-grid">
              {Object.entries(row)
                .filter(
                  ([key, value]) =>
                    value != null &&
                    !(
                      purchase &&
                      key === "gold_charge_in_grams" &&
                      row.gold_charge_24k != null
                    ) &&
                    [
                      "barcode",
                      "product_id",
                      "inventory_item_id",
                      "weight",
                      "gold_charge_in_grams",
                      "gold_charge_24k",
                      "gold_price_per_gram",
                      "cost_per_gram",
                      "making_charge",
                      "sell_price",
                      "refund_usd",
                    ].includes(key),
                )
                .map(([key, value]) => (
                  <div key={key}>
                    <span>
                      {t(
                        (
                          {
                            barcode: "Barcode",
                            product_id: "Product",
                            inventory_item_id: "Items",
                            weight: "Weight (g)",
                            gold_charge_in_grams: "Gold charge (g)",
                            gold_charge_24k: "Gold charge (24K equivalent g)",
                            gold_price_per_gram: "Gold price / gram",
                            cost_per_gram: "Cost / gram",
                            making_charge:
                              purchase && row.gold_charge_in_grams != null
                                ? "Making charge (USD/g)"
                                : "Making charge (USD)",
                            sell_price: "Final price (USD)",
                            refund_usd: "Refund (USD)",
                          } as Record<string, string>
                        )[key],
                      )}
                    </span>
                    <strong>{text(value)}</strong>
                  </div>
                ))}
            </div>
            {!purchase &&
              record.kind !== "supplier" &&
              row.inventory_item_id != null &&
              (row.returned ? (
                <Badge value="Returned" />
              ) : (
                can.cashier && (
                  <button
                    className="secondary"
                    onClick={() => setReturnLine(row)}
                  >
                    {t("Return item")}
                  </button>
                )
              ))}
          </div>
        ))
      )}
      {returnLine && (
        <div className="panel inset">
          <h3>{t("Return item")}</h3>
          <Form
            fields={[locationField, amount("refund_usd", "Refund (USD)")]}
            initial={{
              location_id: String(record.location_id),
              refund_usd: String(returnLine.sell_price),
            }}
            submit={(v) =>
              op.current.send("/inventory/returns", {
                sale_item_id: returnLine.id,
                location_id: Number(v.location_id),
                refund_usd: v.refund_usd,
              })
            }
            done={done}
          />
        </div>
      )}
    </Modal>
  );
}

export function Trades({ purchase = false }: { purchase?: boolean }) {
  const workspace = useWorkspace();
  const { t } = useLanguage();
  const can = useCan();
  const [action, setAction] = useState<
    "itemPurchase" | "customerBulkPurchase" | "customerSale" | "bulkSale"
  >();
  const [selected, setSelected] = useState<Row>();
  const [loc, setLoc] = useState("");
  const done = useDone(() => setAction(undefined));
  return (
    <>
      <PageHead
        title={purchase ? "Purchases" : "Sales"}
        action={
          <div className="actions">
            {purchase && can.cashier && (
              <button onClick={() => setAction("customerBulkPurchase")}>
                {t("Customer bulk purchase")}
              </button>
            )}
            {(purchase
              ? can.admin && workspace === "showroom"
              : can.cashier) && (
              <button
                onClick={() =>
                  setAction(purchase ? "itemPurchase" : "customerSale")
                }
              >
                <Plus size={17} />
                {t(purchase ? "Item purchase" : "Customer sale")}
              </button>
            )}
            {!purchase && can.cashier && <ServiceSaleButton />}
            {!purchase && workspace === "factory" && can.admin && (
              <button
                className="secondary"
                onClick={() => setAction("bulkSale")}
              >
                {t("Supplier bulk sale")}
              </button>
            )}
          </div>
        }
      />
      <div className="filters">
        <label>
          <span>{t("Location")}</span>
          <Select
            field={{
              ...locationField,
              required: false,
              optional: true,
              filter: undefined,
            }}
            value={loc}
            change={setLoc}
          />
        </label>
      </div>
      <section className="panel">
        <DataList
          path={purchase ? "/purchases" : "/sales"}
          params={loc ? { location_id: loc } : {}}
          columns={[
            { key: "id", label: "ID" },
            { key: "invoice_number", label: "Invoice number" },
            { key: "location_id", label: "Location" },
            {
              key: "created_at",
              label: "Date",
              render: (r) => date(r.created_at),
            },
          ]}
          view={setSelected}
        />
      </section>
      {!purchase && can.cashier && (
        <section className="panel">
          <h2>{t("Service sales")}</h2>
          <DataList
            path={"/servicing/sales" + (loc ? `?location_id=${loc}` : "")}
            local
            columns={[
              { key: "id", label: "ID" },
              { key: "barcode", label: "Barcode" },
              { key: "location_id", label: "Location" },
              {
                key: "amount_usd",
                label: "Collected (USD)",
                render: (r) => money(r.amount_usd),
              },
              {
                key: "created_at",
                label: "Date",
                render: (r) => date(r.created_at),
              },
            ]}
          />
        </section>
      )}
      {action && (
        <Modal
          title={
            action === "customerBulkPurchase"
              ? "Customer bulk purchase"
              : action === "itemPurchase"
                ? "Item purchase"
                : action === "customerSale"
                  ? "Customer sale"
                  : "Supplier bulk sale"
          }
          close={() => setAction(undefined)}
        >
          <TradeForm kind={action} done={done} />
        </Modal>
      )}
      {selected && (
        <TradeDetail
          purchase={purchase}
          record={selected}
          close={() => setSelected(undefined)}
        />
      )}
    </>
  );
}

export function Suppliers() {
  const { t } = useLanguage();
  const can = useCan();
  const [selected, setSelected] = useState<Row>();
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [action, setAction] = useState("");
  const [entry, setEntry] = useState<Row>();
  const op = useRef(new Operation());
  const done = useDone(() => {
    setEditing(undefined);
    setAction("");
  });
  const balance = useQuery({
    queryKey: ["list", "supplier-balance", selected?.id],
    queryFn: () =>
      get<SupplierBalance>("/suppliers/" + selected!.id + "/balance"),
    enabled: !!selected,
  });
  return (
    <>
      <PageHead
        title="Suppliers"
        action={
          can.admin && (
            <button onClick={() => setEditing(null)}>
              <Plus size={17} />
              {t("Create")}
            </button>
          )
        }
      />
      {selected ? (
        <>
          <button className="ghost" onClick={() => setSelected(undefined)}>
            {t("Back")}
          </button>
          <h2>{text(selected.name)}</h2>
          <ErrorBox error={balance.error} />
          <p role="status">
            <strong>
              {t(balance.data?.is_settled ? "Fully settled" : "Outstanding")}
            </strong>
          </p>
          <div className="stats">
            {[true, false].map((owe) => (
              <div className="stat" key={String(owe)}>
                <h3>
                  {t(owe ? "We owe the supplier" : "The supplier owes us")}
                </h3>
                <span>{t("Making charge (USD)")}</span>
                <strong dir="ltr">
                  $
                  {money(
                    balance.data &&
                      (owe
                        ? Decimal.max(balance.data.making_usd, 0)
                        : Decimal.max(
                            new Decimal(balance.data.making_usd).negated(),
                            0,
                          )
                      ).toString(),
                  )}
                </strong>
                <span>{t("Gold debt (24K equivalent g)")}</span>
                <strong dir="ltr">
                  {balance.data
                    ? (owe
                        ? Decimal.max(balance.data.gold_24k, 0)
                        : Decimal.max(
                            new Decimal(balance.data.gold_24k).negated(),
                            0,
                          )
                      ).toFixed(3)
                    : "—"}{" "}
                  g
                </strong>
              </div>
            ))}
          </div>
          <p>
            {t(
              "Gold debt is standardized to 24K equivalent. Making charges remain in USD.",
            )}
          </p>
          {can.admin && balance.data && (
            <button onClick={() => setAction("Settlement")}>
              {t("Record settlement")}
            </button>
          )}
          <section className="panel">
            <h2>{t("Ledger")}</h2>
            <p>{t("Positive: we owe supplier. Negative: supplier owes us.")}</p>
            <DataList
              path={`/suppliers/${selected.id}/ledger`}
              searchable={false}
              columns={[
                {
                  key: "kind",
                  label: "Type",
                  render: (r) => <Badge value={r.kind} />,
                },
                {
                  key: "purity_id",
                  label: "Purity",
                  render: (r) => (
                    <ReferenceName
                      resource="goldpurities"
                      value={r.purity_id}
                    />
                  ),
                },
                { key: "purchase_id", label: "Purchase" },
                { key: "sale_id", label: "Sale" },
                {
                  key: "location_id",
                  label: "Location",
                  render: (r) => (
                    <ReferenceName resource="locations" value={r.location_id} />
                  ),
                },
                { key: "gold_24k", label: "Gold debt (24K equivalent g)" },
                { key: "physical_gold_grams", label: "Physical gold (g)" },
                {
                  key: "physical_purity_id",
                  label: "Payment purity",
                  render: (r) => (
                    <ReferenceName
                      resource="goldpurities"
                      value={r.physical_purity_id}
                    />
                  ),
                },
                { key: "cash_gold_usd", label: "Cash for gold (USD)" },
                { key: "gold_price_usd", label: "USD per 24K-equivalent gram" },
                { key: "making_usd", label: "Making charge (USD)" },
                {
                  key: "created_at",
                  label: "Date",
                  render: (r) => date(r.created_at),
                },
                {
                  key: "reverse",
                  label: "Reverse",
                  render: (r) =>
                    can.admin && r.kind === "settlement" ? (
                      <button
                        className="ghost"
                        onClick={() => {
                          setEntry(r);
                          setAction("Reverse");
                        }}
                      >
                        {t("Reverse")}
                      </button>
                    ) : (
                      "—"
                    ),
                },
              ]}
            />
          </section>
        </>
      ) : (
        <section className="panel">
          <DataList
            path="/suppliers"
            columns={catalogs.suppliers.columns}
            view={setSelected}
            edit={can.admin ? setEditing : undefined}
          />
        </section>
      )}
      {editing !== undefined && (
        <Modal
          title={editing ? "Edit" : "Create"}
          close={() => setEditing(undefined)}
        >
          <Form
            fields={catalogs.suppliers.fields}
            initial={editing ? clean(editing) : { is_active: true }}
            submit={(v) =>
              op.current.send(
                "/suppliers" + (editing ? "/" + editing.id : ""),
                toPayload(catalogs.suppliers.fields, v),
                editing ? "PATCH" : "POST",
              )
            }
            done={done}
          />
        </Modal>
      )}
      {action && (
        <Modal title={action} close={() => setAction("")}>
          {action === "Settlement" && balance.data ? (
            <SupplierSettlement
              supplierId={Number(selected!.id)}
              balance={balance.data}
              done={done}
            />
          ) : (
            <Form
              fields={[
                {
                  key: "reason",
                  label: "Reason",
                  type: "textarea",
                  required: true,
                  maxLength: 500,
                },
              ]}
              submit={(v) =>
                op.current.send(
                  `/suppliers/${selected!.id}/ledger/${entry!.id}/reverse`,
                  { reason: v.reason },
                  "POST",
                  false,
                  true,
                )
              }
              done={done}
            />
          )}
        </Modal>
      )}
    </>
  );
}

export function Cash() {
  const { t } = useLanguage();
  const can = useCan();
  const [loc, setLoc] = useState("");
  const [tab, setTab] = useState("Entries");
  const [action, setAction] = useState("");
  const op = useRef(new Operation());
  const done = useDone(() => setAction(""));
  const summary = useQuery({
    queryKey: ["list", "cash-summary", loc],
    queryFn: () => get<Row>("/cash/summary?location_id=" + loc),
    enabled: !!loc,
  });
  const fields: Field[] =
    action === "Reconciliation"
      ? [
          locationField,
          {
            key: "from_at",
            label: "From",
            type: "datetime-local",
            required: true,
          },
          { key: "to_at", label: "To", type: "datetime-local", required: true },
          amount("opening_usd", "Opening cash"),
          amount("counted_usd", "Counted cash"),
        ]
      : [
          locationField,
          amount("amount_usd", "Amount (USD)"),
          {
            key: "description",
            label: "Description",
            type: "textarea",
            required: true,
            maxLength: 500,
          },
          { key: "category", label: "Category", maxLength: 50 },
        ];
  return (
    <>
      <PageHead
        title="Cash drawer"
        action={
          can.admin && (
            <div className="actions">
              <button onClick={() => setAction("Expense")}>
                <Plus size={17} />
                {t("Expense")}
              </button>
              <button
                className="secondary"
                onClick={() => setAction("Withdrawal")}
              >
                {t("Withdrawal")}
              </button>
            </div>
          )
        }
      />
      <div className="filters">
        <label>
          <span>{t("Location")}</span>
          <Select
            field={{ ...locationField, filter: undefined }}
            value={loc}
            change={setLoc}
          />
        </label>
      </div>
      {loc ? (
        <>
          <ErrorBox error={summary.error} />
          <div className="stats">
            {[
              ["Customer receipts", "received_usd"],
              ["Service receipts", "service_received_usd"],
              ["Customer refunds", "refunded_usd"],
              ["Expenses", "expenses_usd"],
              ["Withdrawals", "withdrawals_usd"],
              ["Customer bulk purchases", "customer_purchases_usd"],
              ["Supplier sent", "supplier_sent_usd"],
              ["Supplier received", "supplier_received_usd"],
              ["Capital", "capital_usd"],
              ["Adjustments", "adjustments_usd"],
              ["Cash transfers", "transfers_usd"],
              ["Internal payments", "internal_payments_usd"],
              ["Production costs", "production_costs_usd"],
              ["Net movement", "net_usd"],
            ].map(([label, key]) => (
              <div className="stat compact" key={key}>
                <span>{t(label)}</span>
                <strong dir="ltr">${money(summary.data?.[key])}</strong>
              </div>
            ))}
          </div>
          <div className="section-title">
            <div className="tabs">
              {["Entries", ...(can.admin ? ["Reconciliation"] : [])].map(
                (v) => (
                  <button
                    key={v}
                    className={tab === v ? "selected" : ""}
                    onClick={() => setTab(v)}
                  >
                    {t(v)}
                  </button>
                ),
              )}
            </div>
            {can.admin && (
              <button
                className="secondary"
                onClick={() => setAction("Reconciliation")}
              >
                {t("Record")} {t("Reconciliation")}
              </button>
            )}
          </div>
          <section className="panel">
            <DataList
              key={tab}
              path={
                tab === "Entries" ? "/cash/entries" : "/cash/reconciliations"
              }
              params={{ location_id: loc }}
              searchable={false}
              columns={
                tab === "Entries"
                  ? [
                      {
                        key: "kind",
                        label: "Type",
                        render: (r) => <Badge value={r.kind} />,
                      },
                      { key: "description", label: "Description" },
                      {
                        key: "amount_usd",
                        label: "Amount (USD)",
                        render: (r) => (
                          <span
                            className={
                              String(r.amount_usd).startsWith("-")
                                ? "negative"
                                : "positive"
                            }
                            dir="ltr"
                          >
                            ${money(r.amount_usd)}
                          </span>
                        ),
                      },
                      {
                        key: "created_at",
                        label: "Date",
                        render: (r) => date(r.created_at),
                      },
                    ]
                  : [
                      {
                        key: "from_at",
                        label: "From",
                        render: (r) => date(r.from_at),
                      },
                      {
                        key: "to_at",
                        label: "To",
                        render: (r) => date(r.to_at),
                      },
                      { key: "expected_usd", label: "Expected cash" },
                      { key: "counted_usd", label: "Counted cash" },
                      { key: "variance_usd", label: "Variance" },
                    ]
              }
            />
          </section>
        </>
      ) : (
        <div className="empty panel">{t("Choose a location")}</div>
      )}
      {action && (
        <Modal title={action} close={() => setAction("")}>
          <Form
            fields={fields}
            initial={{ location_id: loc }}
            submit={(v) => {
              if (action === "Reconciliation")
                return op.current.send(
                  "/cash/reconciliations",
                  {
                    location_id: Number(v.location_id),
                    from_at: new Date(String(v.from_at)).toISOString(),
                    to_at: new Date(String(v.to_at)).toISOString(),
                    opening_usd: v.opening_usd,
                    counted_usd: v.counted_usd,
                  },
                  "POST",
                  false,
                  true,
                );
              return op.current.send(
                "/cash/outflows",
                {
                  location_id: Number(v.location_id),
                  kind: action === "Expense" ? "expense" : "withdrawal",
                  amount_usd: v.amount_usd,
                  description: v.description,
                  category: v.category || null,
                },
                "POST",
                true,
              );
            }}
            done={done}
          >
            <p className="muted small">
              {t("This action records a real cash movement.")}
            </p>
          </Form>
        </Modal>
      )}
    </>
  );
}

export function Staff() {
  const { t } = useLanguage();
  const op = useRef(new Operation());
  const [saved, setSaved] = useState(false);
  const [editing, setEditing] = useState<Row>();
  const done = useDone(() => setEditing(undefined));
  return (
    <>
      <PageHead
        title="Staff accounts"
        description="Only admins can create staff accounts."
      />
      <section className="panel">
        <DataList
          path="/operations/staff"
          searchable={false}
          columns={[
            { key: "username", label: "Username" },
            { key: "role", label: "Role" },
            { key: "workspace_access", label: "Workspace access" },
          ]}
          edit={setEditing}
        />
      </section>
      {editing && (
        <Modal title="Workspace access" close={() => setEditing(undefined)}>
          <Form
            fields={[
              {
                key: "workspace_access",
                label: "Workspace access",
                type: "select",
                options: ["showroom", "factory", "both"],
                required: true,
              },
            ]}
            initial={{
              workspace_access: String(editing.workspace_access || "showroom"),
            }}
            submit={(v) =>
              op.current.send(`/operations/staff/${editing.id}`, v, "PATCH")
            }
            done={done}
          />
        </Modal>
      )}
      <section className="panel narrow">
        {saved && (
          <div className="notice success" role="status">
            {t("Account created")}
          </div>
        )}
        <Form
          key={String(saved)}
          fields={[
            {
              key: "workspace_access",
              label: "Workspace access",
              type: "select",
              options: ["showroom", "factory", "both"],
              required: true,
            },
            { key: "email", label: "Email", required: true, maxLength: 255 },
            {
              key: "username",
              label: "Username",
              required: true,
              maxLength: 50,
            },
            {
              key: "password",
              label: "Password",
              type: "password",
              required: true,
              maxLength: 128,
            },
            {
              key: "role",
              label: "Role",
              type: "select",
              options: ["cashier", "employee"],
              required: true,
            },
          ]}
          initial={{ role: "cashier", workspace_access: "showroom" }}
          submit={(v) => op.current.send("/auth/register", v)}
          done={() => {
            setSaved(true);
            setTimeout(() => setSaved(false), 5000);
          }}
          button="Create"
        />
      </section>
    </>
  );
}

async function resizePhoto(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image",
  });
  const ratio = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
  canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("Cannot prepare photo");
  }
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) =>
        blob ? resolve(blob) : reject(new Error("Cannot prepare photo")),
      "image/jpeg",
      0.85,
    ),
  );
}
