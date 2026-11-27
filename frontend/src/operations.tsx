import { WeightTradeForm } from "./factory";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import Decimal from "decimal.js";
import { all, get, Operation, type Row } from "./api";
import { useLanguage } from "./i18n";
import { useCan, useUser, useWorkspace } from "./session";
import { useGoldQuote } from "./gold-price";
import { useLocationValues } from "./location-settings";
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
const operationLabels: Record<string, string> = {
  opening: "Opening balance",
  capital_in: "Capital addition",
  adjustment: "Balance adjustment",
  cash_transfer: "Cash transfer",
  gold_transfer: "Gold transfer",
  valuation: "Stock valuation",
  production: "Production",
  finished_opening: "Seed finished gold",
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
      get<{
        cash_usd: string;
        available_pieces: number;
        bulk: Row[];
        finished?: Row[];
      }>("/operations/overview"),
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
        {showPieces && unit !== "factory" && (
          <div className="stat compact">
            <span>{t("Available pieces")}</span>
            <strong>{query.data?.available_pieces ?? "—"}</strong>
          </div>
        )}
        {unit === "factory" && (
          <div className="stat compact">
            <span>{t("Finished gold (g)")}</span>
            <strong>
              {(query.data?.finished || [])
                .reduce(
                  (sum, row) => sum.plus(String(row.weight || 0)),
                  new Decimal(0),
                )
                .toFixed(3)}
            </strong>
          </div>
        )}
        <div className="stat compact">
          <span>
            {t(unit === "factory" ? "Raw gold (g)" : "Bulk gold (g)")}
          </span>
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
  const [head, setHead] = useLocationValues({ cash_usd: "0" });
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
            "finished_opening",
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
            <WeightTradeForm done={done} />
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
