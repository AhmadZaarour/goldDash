import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js";
import { all, get, raw, Operation, type Row } from "./api";
import { useCan } from "./session";
import { useLanguage } from "./i18n";
import { useGoldQuote } from "./gold-price";
import { ServiceSaleButton } from "./servicing";
import { resizePhoto } from "./item-photo";
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

const number = (key: string, label: string, min = "0"): Field => ({
  key,
  label,
  type: "number",
  required: true,
  min,
  step: "0.001",
});
const usd = (key: string, label: string): Field => ({
  key,
  label,
  type: "money",
  required: true,
  min: "0",
});
const note: Field = {
  key: "note",
  label: "Reason / notes",
  type: "textarea",
  maxLength: 500,
};
const purity: Field = {
  key: "purity_id",
  label: "Purity",
  type: "select",
  resource: "goldpurities",
  required: true,
};
const product: Field = {
  key: "product_id",
  label: "Product",
  type: "select",
  resource: "products",
  required: true,
  filter: (r) => r.inventory_type === "item",
};
const weight = number("weight", "Weight (g)", "0.001");
const rowsPayload = (rows: Values[]) =>
  rows.map((r) => ({
    purity_id: Number(r.purity_id),
    weight: String(r.weight),
  }));
function useDone(close: () => void) {
  const q = useQueryClient();
  return () => {
    void q.invalidateQueries();
    close();
  };
}
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
        {description && <p>{t(description)}</p>}
      </div>
    </div>
  );
}
function GoldRows({
  rows,
  set,
  making = false,
  valued = false,
}: {
  rows: Values[];
  set: (rows: Values[]) => void;
  making?: boolean;
  valued?: boolean;
}) {
  const { t } = useLanguage();
  return (
    <>
      {rows.map((row, i) => (
        <section className="line-item" key={i}>
          <Fields
            fields={[
              purity,
              weight,
              ...(making
                ? [usd("making_per_gram", "Making charge / gram (USD)")]
                : []),
              ...(valued
                ? [usd("value_usd", "Recorded gold value (USD)")]
                : []),
            ]}
            values={row}
            set={(next) => set(rows.map((r, j) => (i === j ? next : r)))}
          />
          <button
            type="button"
            className="ghost danger"
            onClick={() => set(rows.filter((_, j) => i !== j))}
          >
            {t("Remove")}
          </button>
        </section>
      ))}
      <button
        type="button"
        className="secondary"
        onClick={() => set([...rows, making ? { making_per_gram: "0" } : {}])}
      >
        {t("Add purity")}
      </button>
    </>
  );
}
function GoldAudit({ rows }: { rows: Row[] }) {
  const { t } = useLanguage();
  return (
    <div className="detail-grid">
      {rows.map((row, i) => (
        <div key={i}>
          <ReferenceName resource="goldpurities" value={row.purity_id} />
          <strong>
            <bdi>{text(row.weight)} g</bdi>
          </strong>
          {row.gold_24k != null && (
            <small>
              {t("Gold (24K equivalent g)")}: <bdi>{text(row.gold_24k)}</bdi>
            </small>
          )}
        </div>
      ))}
    </div>
  );
}

export function Production() {
  const { t } = useLanguage();
  const can = useCan();
  const q = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Row>();
  const [head, setHead] = useState<Values>({ direct_cost_usd: "0" });
  const [inputs, setInputs] = useState<Values[]>([{}]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const detail = useQuery({
    queryKey: ["list", "production-detail", selected?.id],
    queryFn: () => get<Row>(`/operations/production/${selected!.id}`),
    enabled: !!selected,
  });
  const done = useDone(() => {
    setSelected(undefined);
    setError(undefined);
  });
  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const result = await op.current.send(
        "/operations/weight-production",
        {
          location_id: Number(head.location_id),
          reference: head.reference || null,
          note: head.note || null,
          direct_cost_usd: head.direct_cost_usd || "0",
          inputs: rowsPayload(inputs),
        },
        "POST",
        true,
      );
      setOpen(false);
      setSelected(result);
      setHead({ direct_cost_usd: "0" });
      setInputs([{}]);
      void q.invalidateQueries();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        title="Production"
        description="Track raw gold through production steps, then release finished weight by purity."
      />
      {can.employee && (
        <button
          onClick={() => {
            setError(undefined);
            setOpen(true);
          }}
        >
          {t("Start production")}
        </button>
      )}
      <section className="panel">
        <DataList
          path="/operations/production"
          searchable={false}
          columns={[
            { key: "reference", label: "Reference" },
            {
              key: "status",
              label: "Status",
              render: (r) =>
                t(r.status === "active" ? "Finished" : String(r.status)),
            },
            { key: "input_gold_24k", label: "Input gold (24K g)" },
            { key: "output_gold_24k", label: "Output gold (24K g)" },
            { key: "loss_gold_24k", label: "Loss (24K g)" },
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
          <form onSubmit={start}>
            <fieldset disabled={busy}>
              <Fields
                fields={[
                  locationField,
                  { key: "reference", label: "Reference", maxLength: 100 },
                  usd("direct_cost_usd", "Production costs paid (USD)"),
                  note,
                ]}
                values={head}
                set={setHead}
              />
              <h3>{t("Raw gold input")}</h3>
              <GoldRows rows={inputs} set={setInputs} />
              <p>
                {t(
                  "Starting a batch reserves its raw gold. Finished stock becomes available only after completion.",
                )}
              </p>
            </fieldset>
            <ErrorBox error={error} />
            <footer>
              <button disabled={busy || !inputs.length}>
                {t(busy ? "Working…" : "Start production")}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title="Production batch" close={() => setSelected(undefined)}>
          <ErrorBox error={detail.error} />
          {detail.isLoading ? (
            <Busy />
          ) : (
            detail.data && (
              <>
                <p>
                  {text(detail.data.reference)} ·{" "}
                  {t(
                    detail.data.status === "active"
                      ? "Finished"
                      : String(detail.data.status),
                  )}
                </p>
                <p>
                  {t("Production cost (USD)")}: $
                  {money(detail.data.total_cost_usd)} · {t("Loss (24K g)")}:{" "}
                  <bdi>{text(detail.data.loss_gold_24k)}</bdi>
                </p>
                <h3>{t("Raw gold input")}</h3>
                <GoldAudit
                  rows={
                    (detail.data.details as { inputs?: Row[] })?.inputs || []
                  }
                />
                {((detail.data.details as { steps?: Row[] })?.steps || []).map(
                  (step, i) => (
                    <section className="panel" key={i}>
                      <h3>
                        {i + 1}. {text(step.name)}
                      </h3>
                      <GoldAudit rows={step.outputs as Row[]} />
                      <p>
                        {t("Input gold (24K g)")}:{" "}
                        <bdi>{text(step.input_gold_24k)}</bdi> ·{" "}
                        {t("Output gold (24K g)")}:{" "}
                        <bdi>{text(step.output_gold_24k)}</bdi> ·{" "}
                        {t("Loss (24K g)")}:{" "}
                        <bdi>{text(step.loss_gold_24k)}</bdi>
                      </p>
                      <h4>{t("Newly recovered scrap")}</h4>
                      <GoldAudit rows={step.scrap as Row[]} />
                      {!!step.note && <p>{text(step.note)}</p>}
                    </section>
                  ),
                )}
                {detail.data.tracking_mode === "weight" &&
                  detail.data.status === "in_progress" &&
                  can.employee && (
                    <StepForm
                      batch={detail.data}
                      changed={() => void q.invalidateQueries()}
                    />
                  )}
                {detail.data.tracking_mode !== "weight" && (
                  <>
                    <h3>{t("Historical pieces")}</h3>
                    {((detail.data.pieces as Row[]) || []).map((piece) => (
                      <p key={piece.id}>
                        {text(piece.barcode)} · {text(piece.weight)} g
                      </p>
                    ))}
                  </>
                )}
                {can.admin &&
                  ["active", "in_progress"].includes(
                    String(detail.data.status),
                  ) && (
                    <Form
                      fields={[{ ...note, required: true }]}
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
            )
          )}
        </Modal>
      )}
    </>
  );
}

function StepForm({ batch, changed }: { batch: Row; changed: () => void }) {
  const { t } = useLanguage();
  const [head, setHead] = useState<Values>({ direct_cost_usd: "0" });
  const [outputs, setOutputs] = useState<Values[]>([{}]);
  const [scrap, setScrap] = useState<Values[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const count = ((batch.details as { steps: Row[] }).steps || []).length;
  async function send(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        `/operations/weight-production/${batch.id}/${e ? "steps" : "finish"}`,
        e
          ? {
              name: head.name,
              note: head.note || null,
              direct_cost_usd: head.direct_cost_usd || "0",
              expected_step: count,
              outputs: rowsPayload(outputs),
              scrap: rowsPayload(scrap),
            }
          : { expected_step: count },
        "POST",
        true,
      );
      setHead({ direct_cost_usd: "0" });
      setOutputs([{}]);
      setScrap([]);
      changed();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h3>{t("Record production step")}</h3>
      <form onSubmit={send}>
        <fieldset disabled={busy}>
          <Fields
            fields={[
              {
                key: "name",
                label: "Step name",
                required: true,
                maxLength: 100,
              },
              usd("direct_cost_usd", "Production costs paid (USD)"),
              note,
            ]}
            values={head}
            set={setHead}
          />
          <h4>{t("Output after this step")}</h4>
          <GoldRows rows={outputs} set={setOutputs} />
          <p>
            {t(
              "Weigh all gold remaining in the batch by purity, including work still in progress. Do not include scrap recovered in earlier steps.",
            )}
          </p>
          <h4>{t("Newly recovered scrap")}</h4>
          <GoldRows rows={scrap} set={setScrap} />
          <p>
            {t(
              "Loss is calculated automatically in 24K equivalent. Explain any loss in the step notes.",
            )}
          </p>
        </fieldset>
        <ErrorBox error={error} />
        <footer>
          <button disabled={busy || !outputs.length}>
            {t(busy ? "Working…" : "Save step")}
          </button>
        </footer>
      </form>
      {count > 0 && (
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => void send()}
        >
          {t("Finish production")}
        </button>
      )}
    </section>
  );
}

export function WeightTradeForm({
  done,
  external = false,
}: {
  done: () => void;
  external?: boolean;
}) {
  const { t } = useLanguage();
  const quote = useGoldQuote();
  const purities = useQuery({
    queryKey: ["options", "factory-purities"],
    queryFn: () => all("/goldpurities"),
  });
  const [head, setHead] = useState<Values>({});
  const [rows, setRows] = useState<Values[]>([{ making_per_gram: "0" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const suggested = useRef(false);
  useEffect(() => {
    if (quote.data && !quote.data.stale && !suggested.current) {
      suggested.current = true;
      setHead((v) => ({
        ...v,
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
          ? "/operations/supplier-weight-sales"
          : "/operations/weight-internal-invoices",
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
          note: head.note || null,
          lines: rowsPayload(rows).map((r, i) => ({
            ...r,
            making_per_gram: String(rows[i].making_per_gram || "0"),
          })),
        },
        "POST",
        true,
      );
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
                    filter: (r: Row) => r.is_active !== false,
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
                  usd("gold_price_usd", "Agreed USD per 24K gram"),
                ]),
            note,
          ]}
          values={head}
          set={setHead}
        />
        <GoldRows rows={rows} set={setRows} making />
        {rows.map((row, i) => {
          const purity = purities.data?.find(
            (p) => p.id === Number(row.purity_id),
          );
          let price = "—";
          try {
            if (purity) {
              const factor =
                Number(purity.karat) === 24
                  ? new Decimal(1)
                  : new Decimal(String(purity.purity)).div("99.5");
              price = new Decimal(
                String(
                  external ? quote.data?.gram_24k_usd : head.gold_price_usd,
                ),
              )
                .mul(factor)
                .toFixed(4);
            }
          } catch {
            /* Wait for a usable quote or agreed price. */
          }
          return (
            <p key={i}>
              <ReferenceName resource="goldpurities" value={row.purity_id} /> ·{" "}
              {t("Gold price / gram")}: <output dir="ltr">{price}</output> USD
            </p>
          );
        })}
        <p>
          {t(
            "Making charge is USD per physical gram. Gold receivables use 24K equivalent; settlement factors remain unchanged.",
          )}
        </p>
        <h3>{t("Available finished gold")}</h3>
        <DataList
          path={
            "/operations/finished-stock" +
            (head.location_id ? `?location_id=${head.location_id}` : "")
          }
          local
          searchable={false}
          columns={stockColumns()}
        />
      </fieldset>
      <ErrorBox error={error} />
      <footer>
        <button disabled={busy || !rows.length}>
          {t(busy ? "Working…" : "Confirm")}
        </button>
      </footer>
    </form>
  );
}
function stockColumns() {
  return [
    {
      key: "purity_id",
      label: "Purity",
      render: (r: Row) => (
        <ReferenceName resource="goldpurities" value={r.purity_id} />
      ),
    },
    {
      key: "location_id",
      label: "Location",
      render: (r: Row) => (
        <ReferenceName resource="locations" value={r.location_id} />
      ),
    },
    { key: "weight", label: "Weight (g)" },
  ];
}

export function FactorySales() {
  const { t } = useLanguage();
  const can = useCan();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Row>();
  const done = useDone(() => setOpen(false));
  const details = useQuery({
    queryKey: ["list", "factory-sale-detail", selected?.id],
    queryFn: () =>
      get<Row[]>(`/operations/supplier-weight-sales/${selected!.id}`),
    enabled: !!selected,
  });
  return (
    <>
      <Heading
        title="Supplier sales"
        description="Sell finished gold by purity and weight. Gold and making charges are recorded as receivables."
      />
      {can.admin && (
        <button onClick={() => setOpen(true)}>{t("Sell to supplier")}</button>
      )}
      {can.cashier && <ServiceSaleButton />}
      <section className="panel">
        <DataList
          path="/sales"
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
          view={setSelected}
        />
      </section>
      {open && (
        <Modal title="Sell to supplier" close={() => setOpen(false)}>
          <WeightTradeForm external done={done} />
        </Modal>
      )}
      {selected && (
        <Modal title="Supplier sale" close={() => setSelected(undefined)}>
          <ErrorBox error={details.error} />
          {details.isLoading ? (
            <Busy />
          ) : (
            <>
              {(details.data || []).map((r) => (
                <section className="line-item" key={r.id}>
                  <ReferenceName resource="goldpurities" value={r.purity_id} />
                  <p>
                    <bdi>{text(r.weight)} g</bdi> ·{" "}
                    {t("Making charge / gram (USD)")}: $
                    {money(r.making_per_gram)} · {t("Making charge (USD)")}: $
                    {money(r.making_usd)}
                  </p>
                  <p>
                    {t("Gold debt (24K equivalent g)")}:{" "}
                    <bdi>{text(r.gold_24k)}</bdi>
                  </p>
                </section>
              ))}
              {details.data?.length === 0 && (
                <DataList
                  path={`/sales/item/${selected.id}`}
                  columns={[
                    { key: "inventory_item_id", label: "Historical pieces" },
                    { key: "making_usd", label: "Making charge (USD)" },
                  ]}
                />
              )}
            </>
          )}
        </Modal>
      )}
    </>
  );
}

export function FactoryInventory() {
  const { t } = useLanguage();
  const can = useCan();
  const [open, setOpen] = useState(false);
  const [moving, setMoving] = useState(false);
  const [head, setHead] = useState<Values>({});
  const [rows, setRows] = useState<Values[]>([{}]);
  const op = useRef(new Operation());
  const done = useDone(() => {
    setOpen(false);
    setMoving(false);
    setHead({});
    setRows([{}]);
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function seed(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        "/operations/finished-opening",
        {
          location_id: Number(head.location_id),
          note: head.note,
          gold: rowsPayload(rows).map((r, i) => ({
            ...r,
            value_usd: String(rows[i].value_usd),
          })),
        },
        "POST",
        true,
      );
      done();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        title="Factory gold inventory"
        description="Raw gold and finished gold are tracked separately by purity and weight."
      />
      {can.employee && (
        <button onClick={() => setMoving(true)}>
          {t("Raw gold transfer")}
        </button>
      )}
      {moving && (
        <Modal title="Raw gold transfer" close={() => setMoving(false)}>
          <Form
            fields={[
              purity,
              {
                ...locationField,
                key: "source_location_id",
                label: "Source location",
              },
              {
                ...locationField,
                key: "destination_location_id",
                label: "Destination location",
              },
              weight,
            ]}
            submit={(v) =>
              op.current.send(
                "/inventory/stocks/transfer",
                {
                  purity_id: Number(v.purity_id),
                  source_location_id: Number(v.source_location_id),
                  destination_location_id: Number(v.destination_location_id),
                  weight: v.weight,
                  source_placement: "factory",
                  destination_placement: "factory",
                },
                "POST",
                true,
              )
            }
            done={done}
          />
        </Modal>
      )}
      <section className="panel">
        <h2>{t("Raw bulk gold")}</h2>
        <DataList
          path="/balance"
          columns={[
            {
              key: "purity_id",
              label: "Purity",
              render: (r) => (
                <ReferenceName resource="goldpurities" value={r.purity_id} />
              ),
            },
            { key: "location_id", label: "Location" },
            { key: "placement", label: "Stock bucket" },
            { key: "total_weight", label: "Weight (g)" },
          ]}
        />
      </section>
      <section className="panel">
        <h2>{t("Finished gold")}</h2>
        {can.admin && (
          <button onClick={() => setOpen(true)}>
            {t("Seed finished gold")}
          </button>
        )}
        <DataList
          path="/operations/finished-stock"
          local
          columns={stockColumns()}
        />
      </section>
      <section className="panel">
        <h2>{t("Production batches")}</h2>
        <DataList
          path="/operations/production"
          columns={[
            { key: "reference", label: "Reference" },
            {
              key: "status",
              label: "Status",
              render: (r) =>
                t(r.status === "active" ? "Finished" : String(r.status)),
            },
            { key: "input_gold_24k", label: "Input gold (24K g)" },
            { key: "output_gold_24k", label: "Output gold (24K g)" },
            { key: "loss_gold_24k", label: "Loss (24K g)" },
          ]}
          searchable={false}
        />
      </section>
      {open && (
        <Modal title="Seed finished gold" close={() => setOpen(false)}>
          <form onSubmit={seed}>
            <fieldset disabled={busy}>
              <Fields
                fields={[locationField, { ...note, required: true }]}
                values={head}
                set={setHead}
              />
              <GoldRows rows={rows} set={setRows} valued />
            </fieldset>
            <ErrorBox error={error} />
            <footer>
              <button disabled={busy || !rows.length}>{t("Save")}</button>
            </footer>
          </form>
        </Modal>
      )}
    </>
  );
}

function ReceiptPhoto({
  invoiceId,
  value,
  change,
  busy,
}: {
  invoiceId: number;
  value: Values;
  change: (next: Values) => void;
  busy: (value: boolean) => void;
}) {
  const { t } = useLanguage();
  const [error, setError] = useState<unknown>();
  return (
    <>
      <label>
        {t("Take / choose photo")}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            busy(true);
            setError(undefined);
            try {
              const response = await (
                await raw(
                  `/operations/weight-internal-invoices/${invoiceId}/photos`,
                  {
                    method: "POST",
                    body: await resizePhoto(file),
                    headers: { "Content-Type": "image/jpeg" },
                  },
                )
              ).json();
              change({ ...value, photo_token: response.token });
            } catch (err) {
              setError(err);
            } finally {
              busy(false);
            }
          }}
        />
      </label>
      {value.photo_token && <p>{t("Photo attached")}</p>}
      <ErrorBox error={error} />
    </>
  );
}
export function ShowroomReceipts() {
  const { t } = useLanguage();
  const can = useCan();
  const [selected, setSelected] = useState<Row>();
  const [rows, setRows] = useState<Values[]>([{ _key: crypto.randomUUID() }]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>();
  const op = useRef(new Operation());
  const pending = useQuery({
    queryKey: ["list", "pending-receipts"],
    queryFn: () => get<Row[]>("/operations/pending-receipts"),
  });
  const done = useDone(() => {
    setSelected(undefined);
    setRows([{ _key: crypto.randomUUID() }]);
  });
  if (!pending.data?.length && !pending.error) return null;
  async function receive(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await op.current.send(
        `/operations/weight-internal-invoices/${selected!.invoice_id}/receive`,
        {
          pieces: rows.map((r) => ({
            product_id: Number(r.product_id),
            weight: String(r.weight),
            ...(r.photo_token ? { photo_token: r.photo_token } : {}),
          })),
        },
        "POST",
        true,
      );
      done();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t("Factory stock awaiting piece registration")}</h2>
      <ErrorBox error={pending.error} />
      {(pending.data || []).map((row) => (
        <div className="line-item" key={row.id}>
          <p>
            {t("Invoice")}: {text(row.invoice_id)} ·{" "}
            <ReferenceName resource="goldpurities" value={row.purity_id} /> ·{" "}
            <bdi>{text(row.remaining_weight)} g</bdi>
          </p>
          {can.employee && (
            <button
              onClick={() => {
                setSelected(row);
                setError(undefined);
              }}
            >
              {t("Register received pieces")}
            </button>
          )}
        </div>
      ))}
      {selected && (
        <Modal
          title="Register received pieces"
          close={() => setSelected(undefined)}
        >
          <form onSubmit={receive}>
            <fieldset disabled={busy || uploading}>
              <p>
                {t(
                  "Enter pieces from this invoice. Their total weight cannot exceed the remaining weight for each purity.",
                )}
              </p>
              {rows.map((row, i) => (
                <section className="line-item" key={String(row._key)}>
                  <Fields
                    fields={[product, weight]}
                    values={row}
                    set={(next) =>
                      setRows(rows.map((r, j) => (i === j ? next : r)))
                    }
                  />
                  <ReceiptPhoto
                    invoiceId={Number(selected.invoice_id)}
                    value={row}
                    change={(next) =>
                      setRows((current) =>
                        current.map((r) => (r._key === row._key ? next : r)),
                      )
                    }
                    busy={setUploading}
                  />
                  {rows.length > 1 && (
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => setRows(rows.filter((_, j) => i !== j))}
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
                  setRows([...rows, { _key: crypto.randomUUID() }])
                }
              >
                {t("Add piece")}
              </button>
            </fieldset>
            <ErrorBox error={error} />
            <footer>
              <button disabled={busy || uploading}>
                {t(busy ? "Working…" : "Register received pieces")}
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </section>
  );
}
