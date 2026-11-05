import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import Decimal from "decimal.js";
import { all, get, raw, Operation, type Row } from "./api";
import { useLanguage } from "./i18n";
import { useCan, useUser, useWorkspace } from "./session";
import { useGoldQuote } from "./gold-price";
import {
  Busy,
  DataList,
  ErrorBox,
  Fields,
  Form,
  Modal,
  ReferenceName,
  date,
  locationField,
  money,
  text,
  type Field,
  type Values,
} from "./ui";

const amount = (key: string, label: string, required = true): Field => ({
  key,
  label,
  type: "money",
  required,
});
const note: Field = {
  key: "note",
  label: "Reason / notes",
  type: "textarea",
  required: true,
  maxLength: 500,
};
const purity: Field = {
  key: "purity_id",
  label: "Purity",
  type: "select",
  resource: "goldpurities",
  required: true,
};
const itemProduct: Field = {
  key: "product_id",
  label: "Product",
  type: "select",
  resource: "products",
  required: true,
  filter: (row) => row.inventory_type === "item",
};
const piece: Field = {
  key: "inventory_item_id",
  label: "Piece",
  type: "select",
  resource: "inventory/items",
  required: true,
  filter: (row) => row.status === "in_stock",
};
const operationLabels: Record<string, string> = {
  opening: "Opening balance",
  capital_in: "Capital addition",
  adjustment: "Balance adjustment",
  cash_transfer: "Cash transfer",
  gold_transfer: "Gold transfer",
  valuation: "Stock valuation",
  production: "Production",
  production_reversal: "Production reversal",
  reversal: "Operation reversal",
  legacy_assignment: "Ownership assignment",
  internal_payment: "Record payment",
};
function Heading({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  const { t } = useLanguage();
  return (
    <div className="page-head">
      <div>
        <h1>{t(title)}</h1>
        {description && <p className="operations-note">{t(description)}</p>}
      </div>
    </div>
  );
}
function GoldAudit({ rows }: { rows: Row[] }) {
  const { t } = useLanguage();
  return (
    <div className="detail-grid">
      {rows.map((row, i) => (
        <div key={i}>
          <span>
            <ReferenceName resource="goldpurities" value={row.purity_id} />
          </span>
          <strong dir="ltr">{text(row.weight)} g</strong>
          {row.value_usd != null && (
            <small>
              {t("Recorded gold value (USD)")}: ${money(row.value_usd)}
            </small>
          )}
        </div>
      ))}
    </div>
  );
}

function useDone(close: () => void) {
  const query = useQueryClient();
  return () => {
    void query.invalidateQueries();
    close();
  };
}
function ids(rows: Values[]) {
  return rows.map((row) => ({
    inventory_item_id: Number(row.inventory_item_id),
    making_usd: String(row.making_usd || "0"),
  }));
}
function gold(rows: Values[]) {
  return rows.map((row) => ({
    purity_id: Number(row.purity_id),
    weight: String(row.weight),
    ...(row.value_usd !== "" && row.value_usd != null
      ? { value_usd: String(row.value_usd) }
      : {}),
  }));
}
function GoldRows({
  rows,
  change,
  valued,
  signed = false,
}: {
  rows: Values[];
  change: (rows: Values[]) => void;
  valued?: boolean;
  signed?: boolean;
}) {
  const { t } = useLanguage();
  return (
    <>
      {rows.map((row, i) => (
        <section className="line-item" key={i}>
          <Fields
            fields={[
              purity,
              {
                ...amount("weight", "Weight (g)"),
                ...(signed ? { type: "number" as const } : {}),
              },
              ...(valued
                ? [amount("value_usd", "Recorded gold value (USD)", !signed)]
                : []),
            ]}
            values={row}
            set={(next) => change(rows.map((r, j) => (i === j ? next : r)))}
          />
          <button
            type="button"
            className="ghost danger"
            onClick={() => change(rows.filter((_, j) => i !== j))}
          >
            {t("Remove")}
          </button>
        </section>
      ))}
      <button
        type="button"
        className="secondary"
        onClick={() => change([...rows, {}])}
      >
        {t("Add gold line")}
      </button>
    </>
  );
}

export function WorkspaceSummary({
  showPieces = true,
}: {
  showPieces?: boolean;
}) {
  const { t } = useLanguage();
  const unit = useWorkspace();
  const can = useCan();
  const query = useQuery({
    queryKey: ["list", "workspace-overview"],
    queryFn: () =>
      get<{ cash_usd: string; available_pieces: number; bulk: Row[] }>(
        "/operations/overview",
      ),
  });
  if (unit === "legacy") return null;
  return (
    <section className="panel">
      <h2>
        {t(unit === "factory" ? "Factory balances" : "Showroom balances")}
      </h2>
      <ErrorBox error={query.error} />
      {query.isLoading && <Busy />}
      <div className="stats">
        {can.cashier && (
          <div className="stat compact">
            <span>{t("Cash drawer")}</span>
            <strong dir="ltr">${money(query.data?.cash_usd)}</strong>
          </div>
        )}
        {showPieces && (
          <div className="stat compact">
            <span>{t("Available pieces")}</span>
            <strong>{query.data?.available_pieces ?? "—"}</strong>
          </div>
        )}
        <div className="stat compact">
          <span>{t("Bulk gold (g)")}</span>
          <strong>
            {(query.data?.bulk || [])
              .reduce(
                (sum, row) => sum.plus(String(row.total_weight || 0)),
                new Decimal(0),
              )
              .toFixed(3)}
          </strong>
        </div>
      </div>
      {can.admin && (
        <div className="operations-actions">
          <Link className="button secondary" to="/balances">
            {t("Set opening balances")}
          </Link>
          <Link className="button secondary" to="/reports">
            {t("Workspace reports")}
          </Link>
        </div>
      )}
    </section>
  );
}

export function BalanceSetup() {
  const { t } = useLanguage();
  const unit = useWorkspace();
  const [action, setAction] = useState("");
  const [rows, setRows] = useState<Values[]>([]);
  const [head, setHead] = useState<Values>({ cash_usd: "0" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [reverse, setReverse] = useState<Row>();
  const op = useRef(new Operation());
  const done = useDone(() => {
    setAction("");
    setReverse(undefined);
    setRows([]);
    setHead({ cash_usd: "0" });
  });
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        `/operations/${action}`,
        {
          location_id: Number(head.location_id),
          cash_usd: String(head.cash_usd || 0),
          ...(head.effective_at
            ? {
                effective_at: new Date(String(head.effective_at)).toISOString(),
              }
            : {}),
          gold: gold(rows),
          note: head.note,
        },
        "POST",
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
    <>
      <Heading
        title="Opening balances"
        description="Record this workspace's starting cash and bulk gold. Additions and corrections keep a permanent history."
      />
      <WorkspaceSummary />
      <div className="operations-actions">
        {[
          ["opening", "Set opening balances"],
          ["capital", "Add cash / gold"],
          ["adjustments", "Record adjustment"],
          ["cash-transfers", "Transfer cash"],
          ["gold-transfers", "Transfer gold"],
          ["stock-value", "Record stock value"],
        ].map(([key, label]) => (
          <button
            key={key}
            className="secondary"
            onClick={() => {
              setAction(key);
              setError(undefined);
              setRows([]);
              setHead({
                cash_usd: "0",
                to_unit: unit === "factory" ? "showroom" : "factory",
              });
            }}
          >
            {t(label)}
          </button>
        ))}
      </div>
      <section className="panel">
        <h2>{t("Balance history")}</h2>
        <DataList
          path="/operations/history"
          searchable={false}
          columns={[
            {
              key: "kind",
              label: "Type",
              render: (r) =>
                t(operationLabels[String(r.kind)] || String(r.kind)),
            },
            { key: "amount_usd", label: "Amount (USD)" },
            { key: "note", label: "Reason / notes" },
            {
              key: "created_at",
              label: "Date",
              render: (r) => date(r.created_at),
            },
          ]}
          view={setReverse}
        />
      </section>
      {action && (
        <Modal
          title={
            (
              {
                opening: "Set opening balances",
                capital: "Add cash / gold",
                adjustments: "Record adjustment",
                "cash-transfers": "Transfer cash",
                "gold-transfers": "Transfer gold",
                "stock-value": "Record stock value",
              } as Record<string, string>
            )[action]
          }
          close={() => setAction("")}
        >
          {["opening", "capital", "adjustments"].includes(action) ? (
            <form onSubmit={submit}>
              <fieldset disabled={busy}>
                <Fields
                  fields={[
                    locationField,
                    {
                      key: "effective_at",
                      label: "As of",
                      type: "datetime-local",
                    },
                    {
                      ...amount("cash_usd", "Cash (USD)"),
                      ...(action === "adjustments"
                        ? { type: "number" as const }
                        : {}),
                    },
                    note,
                  ]}
                  values={head}
                  set={setHead}
                />
                <p>
                  {t(
                    "Gold value is the recorded cost of stock already owned; it does not spend drawer cash.",
                  )}
                </p>
                <GoldRows
                  rows={rows}
                  change={setRows}
                  valued
                  signed={action === "adjustments"}
                />
                <p>
                  {t(
                    "Use a negative amount only when correcting a balance downward.",
                  )}
                </p>
              </fieldset>
              <ErrorBox error={error} />
              <footer>
                <button disabled={busy}>
                  {t(busy ? "Working…" : "Confirm")}
                </button>
              </footer>
            </form>
          ) : (
            <Form
              fields={
                action === "stock-value"
                  ? [
                      locationField,
                      purity,
                      amount("value_usd", "Recorded gold value (USD)"),
                      note,
                    ]
                  : [
                      locationField,
                      {
                        key: "to_unit",
                        label: "Destination workspace",
                        type: "select",
                        options: [unit === "factory" ? "showroom" : "factory"],
                        required: true,
                      },
                      {
                        ...locationField,
                        key: "to_location_id",
                        label: "Destination",
                      },
                      ...(action === "cash-transfers"
                        ? [amount("amount_usd", "Amount (USD)")]
                        : [purity, amount("weight", "Weight (g)")]),
                      note,
                    ]
              }
              initial={{ to_unit: unit === "factory" ? "showroom" : "factory" }}
              submit={(v) =>
                op.current.send(
                  `/operations/${action}`,
                  {
                    ...v,
                    location_id: Number(v.location_id),
                    ...(v.to_location_id
                      ? { to_location_id: Number(v.to_location_id) }
                      : {}),
                    ...(v.purity_id ? { purity_id: Number(v.purity_id) } : {}),
                  },
                  "POST",
                  true,
                )
              }
              done={done}
            />
          )}
        </Modal>
      )}
      {reverse && (
        <Modal title="Details" close={() => setReverse(undefined)}>
          <p>
            {text(reverse.kind)} · {date(reverse.created_at)}
          </p>
          <p>{text(reverse.note)}</p>
          <GoldAudit rows={(reverse.details as { gold?: Row[] })?.gold || []} />
          {!!reverse.other_unit && (
            <p>
              {t("Destination workspace")}: {t(String(reverse.other_unit))}
            </p>
          )}
          {[
            "opening",
            "capital_in",
            "adjustment",
            "cash_transfer",
            "gold_transfer",
          ].includes(String(reverse.kind)) && (
            <Form
              fields={[note]}
              button="Reverse"
              submit={(v) =>
                op.current.send(
                  `/operations/history/${reverse.id}/reverse`,
                  v,
                  "POST",
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

function StagePhoto({
  value,
  change,
  onBusy,
}: {
  value: Values;
  change: (value: Values) => void;
  onBusy: (busy: boolean) => void;
}) {
  const { t } = useLanguage();
  const [error, setError] = useState<unknown>();
  const [preview, setPreview] = useState("");
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  return (
    <div>
      {preview && (
        <img src={preview} alt={t("Photo")} className="piece-photo" />
      )}
      <label>
        {t("Take / choose photo")}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            onBusy(true);
            setError(undefined);
            try {
              const result = await (
                await raw("/purchases/photos", { method: "POST", body: file })
              ).json();
              setPreview(URL.createObjectURL(file));
              change({ ...value, photo_token: result.token });
            } catch (e) {
              setError(e);
            } finally {
              onBusy(false);
            }
          }}
        />
      </label>
      <ErrorBox error={error} />
    </div>
  );
}

export function Production() {
  const { t } = useLanguage();
  const can = useCan();
  const [open, setOpen] = useState(false);
  const [head, setHead] = useState<Values>({
    direct_cost_usd: "0",
    loss_gold_24k: "0",
  });
  const [inputs, setInputs] = useState<Values[]>([{}]);
  const [scrap, setScrap] = useState<Values[]>([]);
  const [pieces, setPieces] = useState<Values[]>([
    { _key: crypto.randomUUID() },
  ]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<Row>();
  const op = useRef(new Operation());
  const done = useDone(() => {
    setOpen(false);
    setSelected(undefined);
    setInputs([{}]);
    setScrap([]);
    setPieces([{ _key: crypto.randomUUID() }]);
  });
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        "/operations/production",
        {
          location_id: Number(head.location_id),
          reference: head.reference || null,
          note: head.note || null,
          direct_cost_usd: String(head.direct_cost_usd || 0),
          loss_gold_24k: String(head.loss_gold_24k || 0),
          inputs: gold(inputs),
          scrap: gold(scrap),
          pieces: pieces.map((p) => ({
            product_id: Number(p.product_id),
            weight: String(p.weight),
            ...(p.image_url ? { image_url: p.image_url } : {}),
            ...(p.photo_token ? { photo_token: p.photo_token } : {}),
          })),
        },
        "POST",
        true,
      );
      done();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const detail = useQuery({
    queryKey: ["list", "production-detail", selected?.id],
    queryFn: () => get<Row>(`/operations/production/${selected!.id}`),
    enabled: !!selected,
  });
  return (
    <>
      <Heading
        title="Production"
        description="Turn factory bulk gold into finished pieces, keeping scrap, loss and production costs accounted for."
      />
      {can.employee && (
        <button onClick={() => setOpen(true)}>{t("Start production")}</button>
      )}
      <section className="panel">
        <DataList
          path="/operations/production"
          searchable={false}
          columns={[
            { key: "reference", label: "Reference" },
            { key: "status", label: "Status" },
            { key: "input_gold_24k", label: "Input gold (24K g)" },
            { key: "output_gold_24k", label: "Finished gold (24K g)" },
            { key: "total_cost_usd", label: "Production cost (USD)" },
            {
              key: "created_at",
              label: "Date",
              render: (r) => date(r.created_at),
            },
          ]}
          view={setSelected}
        />
      </section>
      {open && (
        <Modal title="Start production" close={() => setOpen(false)}>
          <form onSubmit={submit}>
            <fieldset disabled={busy || uploading}>
              <Fields
                fields={[
                  locationField,
                  { key: "reference", label: "Reference", maxLength: 100 },
                  amount("direct_cost_usd", "Production costs paid (USD)"),
                  amount("loss_gold_24k", "Unrecoverable loss (24K g)"),
                  { ...note, required: false },
                ]}
                values={head}
                set={setHead}
              />
              <p>
                {t(
                  "Production costs are paid from the factory drawer and included in the pieces' cost.",
                )}
              </p>
              <h3>{t("Bulk gold consumed")}</h3>
              <GoldRows rows={inputs} change={setInputs} />
              <h3>{t("Finished pieces")}</h3>
              {pieces.map((p, i) => (
                <section className="line-item" key={String(p._key)}>
                  <Fields
                    fields={[itemProduct, amount("weight", "Weight (g)")]}
                    values={p}
                    set={(next) =>
                      setPieces(pieces.map((row, j) => (i === j ? next : row)))
                    }
                  />
                  <StagePhoto
                    value={p}
                    change={(next) =>
                      setPieces((current) =>
                        current.map((row) =>
                          row._key === p._key ? next : row,
                        ),
                      )
                    }
                    onBusy={setUploading}
                  />
                  {pieces.length > 1 && (
                    <button
                      type="button"
                      className="ghost danger"
                      onClick={() =>
                        setPieces(pieces.filter((_, j) => i !== j))
                      }
                    >
                      {t("Remove")}
                    </button>
                  )}
                </section>
              ))}
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setPieces([...pieces, { _key: crypto.randomUUID() }])
                }
              >
                {t("Add piece")}
              </button>
              <h3>{t("Recoverable scrap")}</h3>
              <GoldRows rows={scrap} change={setScrap} />
              <p>
                {t(
                  "Gold inputs must equal finished pieces, scrap and declared loss in 24K equivalent.",
                )}
              </p>
            </fieldset>
            <ErrorBox error={error} />
            <footer>
              <button disabled={busy || uploading}>
                {t(busy ? "Working…" : "Confirm")}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title="Details" close={() => setSelected(undefined)}>
          <ErrorBox error={detail.error} />
          {detail.isLoading ? (
            <Busy />
          ) : (
            <>
              <p>
                {text(detail.data?.reference)} · {text(detail.data?.status)}
              </p>
              <p>
                {t("Production cost (USD)")}: $
                {money(detail.data?.total_cost_usd)}
              </p>
              <h3>{t("Bulk gold consumed")}</h3>
              <GoldAudit
                rows={
                  (detail.data?.details as { inputs?: Row[] })?.inputs || []
                }
              />
              <h3>{t("Recoverable scrap")}</h3>
              <GoldAudit
                rows={(detail.data?.details as { scrap?: Row[] })?.scrap || []}
              />
              <h3>{t("Finished pieces")}</h3>
              {((detail.data?.pieces as Row[]) || []).map((piece) => (
                <div className="line-item" key={piece.id}>
                  <ReferenceName resource="products" value={piece.product_id} />
                  <p>
                    {text(piece.barcode)} · {text(piece.weight)} g · $
                    {money(piece.total_cost_usd)}
                  </p>
                </div>
              ))}
              {can.admin && detail.data?.status === "active" && (
                <Form
                  fields={[note]}
                  button="Reverse"
                  submit={(v) =>
                    op.current.send(
                      `/operations/production/${selected.id}/reverse`,
                      v,
                      "POST",
                      true,
                    )
                  }
                  done={done}
                />
              )}
            </>
          )}
        </Modal>
      )}
    </>
  );
}

function PieceLines({
  rows,
  change,
}: {
  rows: Values[];
  change: (rows: Values[]) => void;
}) {
  const { t } = useLanguage();
  return (
    <>
      {rows.map((row, i) => (
        <section className="line-item" key={i}>
          <Fields
            fields={[piece, amount("making_usd", "Making charge (USD)")]}
            values={row}
            set={(next) => change(rows.map((r, j) => (i === j ? next : r)))}
          />
          {rows.length > 1 && (
            <button
              type="button"
              className="ghost danger"
              onClick={() => change(rows.filter((_, j) => i !== j))}
            >
              {t("Remove")}
            </button>
          )}
        </section>
      ))}
      <button
        type="button"
        className="secondary"
        onClick={() => change([...rows, {}])}
      >
        {t("Add piece")}
      </button>
    </>
  );
}

function SupplyForm({
  done,
  external = false,
}: {
  done: () => void;
  external?: boolean;
}) {
  const { t } = useLanguage();
  const quote = useGoldQuote();
  const [head, setHead] = useState<Values>({});
  const [rows, setRows] = useState<Values[]>([{}]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const suggested = useRef(false);
  useEffect(() => {
    if (quote.data && !quote.data.stale && !suggested.current) {
      suggested.current = true;
      setHead((current) => ({
        ...current,
        gold_price_usd: new Decimal(quote.data.gram_24k_usd).toFixed(4),
      }));
    }
  }, [quote.data]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        external
          ? "/operations/supplier-item-sales"
          : "/operations/internal-invoices",
        {
          location_id: Number(head.location_id),
          ...(external
            ? {
                supplier_id: Number(head.supplier_id),
                invoice_number: head.invoice_number || null,
              }
            : {
                showroom_location_id: Number(head.showroom_location_id),
                gold_price_usd: String(head.gold_price_usd),
              }),
          pieces: ids(rows),
          note: head.note || null,
        },
        "POST",
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
            locationField,
            ...(external
              ? [
                  {
                    key: "supplier_id",
                    label: "Supplier",
                    type: "select" as const,
                    resource: "suppliers",
                    required: true,
                  },
                  {
                    key: "invoice_number",
                    label: "Invoice number",
                    maxLength: 50,
                  },
                ]
              : [
                  {
                    ...locationField,
                    key: "showroom_location_id",
                    label: "Showroom location",
                  },
                  amount("gold_price_usd", "Agreed USD per 24K gram"),
                ]),
            { ...note, required: false },
          ]}
          values={head}
          set={setHead}
        />
        <PieceLines rows={rows} change={setRows} />
        <p>
          {t(
            "Gold is recorded as 24K-equivalent debt. Making charges remain separate in USD.",
          )}
        </p>
      </fieldset>
      <ErrorBox error={error} />
      <footer>
        <button disabled={busy}>{t(busy ? "Working…" : "Confirm")}</button>
      </footer>
    </form>
  );
}

function InternalPaymentForm({
  balance,
  done,
}: {
  balance: { gold_24k: string; making_usd: string };
  done: () => void;
}) {
  const { t } = useLanguage();
  const unit = useWorkspace();
  const quote = useGoldQuote();
  const [head, setHead] = useState<Values>({
    direction: "showroom_to_factory",
    gold_grams: "0",
    making_usd: "0",
    cash_gold_usd: "0",
  });
  const [close, setClose] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const suggested = useRef(false);
  const purities = useQuery({
    queryKey: ["list", "internal-purities"],
    queryFn: () => all("/goldpurities"),
  });
  useEffect(() => {
    if (quote.data && !quote.data.stale && !suggested.current) {
      suggested.current = true;
      setHead((current) => ({
        ...current,
        gold_price_usd: new Decimal(quote.data.gram_24k_usd).toFixed(4),
      }));
    }
  }, [quote.data]);
  const source =
    head.direction === "showroom_to_factory" ? "showroom" : "factory";
  const loc = head[`${source}_location_id`];
  const resources = useQuery({
    queryKey: ["list", "internal-resources", source, loc],
    queryFn: () =>
      get<{ cash_usd: string; bulk: Row[] }>(
        `/operations/internal-resources?unit=${source}&location_id=${loc}`,
      ),
    enabled: !!loc,
  });
  let afterGold = "—",
    afterUsd = "—",
    cash = "—";
  try {
    const factor = String(
      purities.data?.find((p) => String(p.id) === String(head.purity_id))
        ?.repayment_factor || 0,
    );
    const gold = new Decimal(String(head.gold_grams || 0)).times(factor);
    const usd = new Decimal(String(head.making_usd || 0));
    const substitution = new Decimal(String(head.cash_gold_usd || 0));
    const rate = new Decimal(String(head.gold_price_usd || 0));
    const credit = gold
      .plus(substitution.gt(0) && rate.gt(0) ? substitution.div(rate) : 0)
      .toDecimalPlaces(3, Decimal.ROUND_HALF_UP);
    const sign = head.direction === "showroom_to_factory" ? 1 : -1;
    afterGold = new Decimal(balance.gold_24k)
      .minus(credit.times(sign))
      .toFixed(3);
    afterUsd = new Decimal(balance.making_usd)
      .minus(usd.times(sign))
      .toFixed(2);
    cash = usd.plus(substitution).toFixed(2);
  } catch {
    /* incomplete input */
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        "/operations/internal-payments",
        {
          ...head,
          showroom_location_id: Number(head.showroom_location_id),
          factory_location_id: Number(head.factory_location_id),
          purity_id: head.purity_id ? Number(head.purity_id) : null,
          gold_price_usd: head.gold_price_usd || null,
          close_account: close,
        },
        "POST",
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
              label: "Payment direction",
              type: "select",
              options: ["showroom_to_factory", "factory_to_showroom"],
              required: true,
            },
            {
              ...locationField,
              key: "showroom_location_id",
              label: "Showroom location",
            },
            {
              ...locationField,
              key: "factory_location_id",
              label: "Factory location",
            },
            { ...purity, required: false, optional: true },
            amount("gold_grams", "Physical gold (g)"),
            amount("making_usd", "Making charge (USD)"),
            amount("cash_gold_usd", "Cash for gold (USD)"),
            amount("gold_price_usd", "USD per 24K-equivalent gram", false),
            note,
          ]}
          values={head}
          set={(next) => {
            setHead(next);
            setClose(false);
          }}
        />
        <section className="panel">
          <h3>{t("Settlement preview")}</h3>
          <p>
            {t("Available cash")}: ${money(resources.data?.cash_usd)}
          </p>
          <p>
            {t("Available bulk gold")}:{" "}
            {(resources.data?.bulk || [])
              .filter(
                (r) =>
                  String(r.purity_id) === String(head.purity_id) &&
                  r.placement === source,
              )
              .map((r) => text(r.total_weight))
              .join(" + ") || "0.000"}{" "}
            g
          </p>
          <p>
            {t("Gold debt (24K equivalent g)")}: {balance.gold_24k} →{" "}
            {afterGold}
          </p>
          <p>
            {t("Making charge (USD)")}: {balance.making_usd} → {afterUsd}
          </p>
          <p>
            {t("Total cash payment (USD)")}: ${cash}
          </p>
          <label>
            <input
              type="checkbox"
              checked={close}
              disabled={afterGold !== "0.000" || afterUsd !== "0.00"}
              onChange={(e) => setClose(e.target.checked)}
            />
            {t("Settle account in full")}
          </label>
        </section>
      </fieldset>
      <ErrorBox error={error || resources.error} />
      <footer>
        <button disabled={busy}>
          {t(
            busy
              ? "Working…"
              : unit === "showroom"
                ? "Pay Factory"
                : "Record payment",
          )}
        </button>
      </footer>
    </form>
  );
}

export function InternalTrade() {
  const { t } = useLanguage();
  const unit = useWorkspace();
  const can = useCan();
  const [action, setAction] = useState("");
  const [reverse, setReverse] = useState<{ row: Row; type: string }>();
  const op = useRef(new Operation());
  const done = useDone(() => {
    setAction("");
    setReverse(undefined);
  });
  const balance = useQuery({
    queryKey: ["list", "internal-balance"],
    queryFn: () =>
      get<{ gold_24k: string; making_usd: string; is_settled: boolean }>(
        "/operations/internal-balance",
      ),
  });
  return (
    <>
      <Heading
        title="Factory / Showroom account"
        description="Positive balances mean Showroom owes Factory. Gold and making charges remain separate."
      />
      <ErrorBox error={balance.error} />
      <div className="stats">
        <div className="stat">
          <span>{t("Gold debt (24K equivalent g)")}</span>
          <strong>{balance.data?.gold_24k ?? "—"}</strong>
        </div>
        <div className="stat">
          <span>{t("Making charge (USD)")}</span>
          <strong>${money(balance.data?.making_usd)}</strong>
        </div>
      </div>
      {can.admin && (
        <div className="operations-actions">
          {unit === "factory" && (
            <button onClick={() => setAction("supply")}>
              {t("Supply Showroom")}
            </button>
          )}
          <button className="secondary" onClick={() => setAction("payment")}>
            {t(unit === "showroom" ? "Pay Factory" : "Receive from Showroom")}
          </button>
        </div>
      )}
      <section className="panel">
        <h2>{t("Internal invoices")}</h2>
        <DataList
          path="/operations/internal-invoices"
          searchable={false}
          columns={[
            { key: "id", label: "ID" },
            { key: "gold_24k", label: "Gold debt (24K equivalent g)" },
            { key: "making_usd", label: "Making charge (USD)" },
            { key: "total_value_usd", label: "Agreed value (USD)" },
            { key: "reversal_of_id", label: "Reversal of" },
            {
              key: "created_at",
              label: "Date",
              render: (r) => date(r.created_at),
            },
          ]}
          view={(row) => setReverse({ row, type: "internal-invoices" })}
        />
      </section>
      <section className="panel">
        <h2>{t("Internal payments")}</h2>
        <DataList
          path="/operations/internal-payments"
          searchable={false}
          columns={[
            { key: "direction", label: "Payment direction" },
            { key: "gold_24k", label: "Gold debt (24K equivalent g)" },
            { key: "making_usd", label: "Making charge (USD)" },
            { key: "physical_gold_grams", label: "Physical gold (g)" },
            { key: "cash_gold_usd", label: "Cash for gold (USD)" },
            { key: "reversal_of_id", label: "Reversal of" },
          ]}
          view={(row) => setReverse({ row, type: "internal-payments" })}
        />
      </section>
      {action && (
        <Modal
          title={action === "supply" ? "Supply Showroom" : "Record payment"}
          close={() => setAction("")}
        >
          {action === "supply" ? (
            <SupplyForm done={done} />
          ) : (
            balance.data && (
              <InternalPaymentForm balance={balance.data} done={done} />
            )
          )}
        </Modal>
      )}
      {reverse && (
        <Modal title="Details" close={() => setReverse(undefined)}>
          <p>{text(reverse.row.note)}</p>
          <p>
            {t("Gold debt (24K equivalent g)")}: {text(reverse.row.gold_24k)}
          </p>
          <p>
            {t("Making charge (USD)")}: ${money(reverse.row.making_usd)}
          </p>
          {can.admin && !reverse.row.reversal_of_id && (
            <Form
              fields={[note]}
              button="Reverse"
              submit={(v) =>
                op.current.send(
                  `/operations/${reverse.type}/${reverse.row.id}/reverse`,
                  v,
                  "POST",
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

function FactorySaleDetail({ sale }: { sale: Row }) {
  const { t } = useLanguage();
  return (
    <>
      <p>
        {t("Invoice number")}: {text(sale.invoice_number)}
      </p>
      <DataList
        path={`/sales/item/${sale.id}`}
        columns={[
          { key: "inventory_item_id", label: "Piece" },
          { key: "gold_24k", label: "Gold debt (24K equivalent g)" },
          { key: "making_usd", label: "Making charge (USD)" },
          { key: "sell_price", label: "Recorded value (USD)" },
        ]}
      />
    </>
  );
}

export function FactorySales() {
  const [selected, setSelected] = useState<Row>();
  const { t } = useLanguage();
  const can = useCan();
  const [open, setOpen] = useState(false);
  const done = useDone(() => setOpen(false));
  return (
    <>
      {selected && (
        <Modal title="Supplier sale" close={() => setSelected(undefined)}>
          <FactorySaleDetail sale={selected} />
        </Modal>
      )}
      <Heading
        title="Supplier sales"
        description="Sell finished factory pieces to suppliers. Gold and making charges are recorded as receivables."
      />
      {can.admin && (
        <button onClick={() => setOpen(true)}>{t("Sell to supplier")}</button>
      )}
      <section className="panel">
        <DataList
          path="/sales"
          view={setSelected}
          columns={[
            { key: "id", label: "ID" },
            { key: "invoice_number", label: "Invoice number" },
            { key: "supplier_id", label: "Supplier" },
            {
              key: "created_at",
              label: "Date",
              render: (r) => date(r.created_at),
            },
          ]}
        />
      </section>
      {open && (
        <Modal title="Sell to supplier" close={() => setOpen(false)}>
          <SupplyForm external done={done} />
        </Modal>
      )}
    </>
  );
}

export function WorkspaceReports() {
  const { t } = useLanguage();
  const unit = useWorkspace();
  const now = new Date();
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );
  const [company, setCompany] = useState(false);
  const report = useQuery({
    queryKey: ["list", "workspace-profit", month, company],
    queryFn: () =>
      get<Row>(`/operations/profit?month=${month}&company=${company}`),
    enabled: /^\d{4}-(0[1-9]|1[0-2])$/.test(month),
  });
  return (
    <>
      <Heading
        title="Workspace reports"
        description="Profit uses recorded purchase and production costs. Company results exclude internal trade."
      />
      <div className="filters">
        <label>
          {t("Month")}
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
        </label>
        <label>
          {t("Report")}
          <select
            value={company ? "company" : unit}
            onChange={(e) => setCompany(e.target.value === "company")}
          >
            <option value={unit}>
              {t(unit === "factory" ? "Factory" : "Showroom")}
            </option>
            <option value="company">{t("Combined business")}</option>
          </select>
        </label>
      </div>
      <ErrorBox error={report.error} />
      {report.isLoading && <Busy />}
      <div className="stats">
        {[
          ["Revenue (USD)", "revenue_usd"],
          ["Cost of goods sold (USD)", "cost_of_sales_usd"],
          ["Expenses", "expenses_usd"],
          ["Profit (USD)", "profit_usd"],
        ].map(([label, key]) => (
          <div className="stat" key={key}>
            <span>{t(label)}</span>
            <strong dir="ltr">
              {report.data?.[key] == null ? "—" : `$${money(report.data[key])}`}
            </strong>
          </div>
        ))}
      </div>
      {Number(report.data?.uncosted_trades || 0) > 0 && (
        <p role="alert">
          {t(
            "Some trades are missing recorded stock costs. Profit is unavailable until those costs are recorded.",
          )}
        </p>
      )}
      <WorkspaceSummary />
    </>
  );
}

export function LegacyHistory() {
  const { t } = useLanguage();
  const user = useUser();
  const [kind, setKind] = useState("purchase");
  const [selected, setSelected] = useState<Row>();
  const op = useRef(new Operation());
  const done = useDone(() => setSelected(undefined));
  if (user.role !== "admin") return null;
  return (
    <>
      <Heading
        title="Unassigned history"
        description="Existing records have no assumed owner. Review each record before assigning it to Factory or Showroom."
      />
      <label>
        {t("Record type")}
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setSelected(undefined);
          }}
        >
          {[
            ["purchase", "Purchases"],
            ["sale", "Sales"],
            ["cash", "Cash drawer"],
            ["stock", "Bulk gold"],
            ["item", "Inventory"],
            ["supplier_entry", "Supplier ledger"],
            ["reconciliation", "Reconciliation"],
            ["return", "Returns"],
            ["movement", "Movements"],
            ["service", "Servicing"],
            ["transfer", "Bulk transfers"],
            ["photo", "Photo"],
          ].map(([key, label]) => (
            <option key={key} value={key}>
              {t(label)}
            </option>
          ))}
        </select>
      </label>
      <section className="panel">
        <DataList
          key={kind}
          path="/operations/legacy"
          params={{ kind }}
          searchable={false}
          columns={[
            { key: "id", label: "ID" },
            { key: "location_id", label: "Location" },
            { key: "invoice_number", label: "Invoice number" },
            { key: "kind", label: "Type" },
            { key: "amount_usd", label: "Amount (USD)" },
            { key: "total_weight", label: "Weight (g)" },
          ]}
          view={setSelected}
        />
      </section>
      {selected && (
        <Modal title="Assign ownership" close={() => setSelected(undefined)}>
          <p>
            {t(
              "Assign this record and its linked financial records only after reviewing their ownership.",
            )}
          </p>
          <Form
            fields={[
              {
                key: "unit",
                label: "Workspace",
                type: "select",
                options: ["factory", "showroom"],
                required: true,
              },
              locationField,
              note,
            ]}
            initial={{
              location_id: selected.location_id
                ? String(selected.location_id)
                : "",
            }}
            submit={(v) =>
              op.current.send(
                "/operations/legacy/assign",
                {
                  kind,
                  id: selected.id,
                  unit: v.unit,
                  location_id: Number(v.location_id),
                  note: v.note,
                },
                "POST",
                true,
              )
            }
            done={done}
          />
        </Modal>
      )}
    </>
  );
}
