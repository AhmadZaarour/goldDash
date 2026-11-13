import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { all, Operation, request, type Row } from "./api";
import { useCan } from "./session";
import { useLanguage } from "./i18n";
import { BarcodeScanButton } from "./barcode-scanner";
import { normalizeBarcode } from "./barcode-camera";
import {
  Badge,
  DataList,
  ErrorBox,
  Form,
  Modal,
  Select,
  date,
  locationField,
  money,
  text,
  type Field,
} from "./ui";

type Service = Row & { sale?: Row | null };
const fields: Field[] = [
  {
    key: "status",
    label: "Status",
    type: "select",
    options: ["in_progress", "finished"],
    required: true,
  },
  { key: "notes", label: "Notes", type: "textarea", maxLength: 200 },
];

function ServiceLookup({
  found,
  disabled = false,
  changed,
  onBusy,
}: {
  found: (service: Service) => void;
  disabled?: boolean;
  changed?: () => void;
  onBusy?: (busy: boolean) => void;
}) {
  const { t } = useLanguage();
  const [barcode, setBarcode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const lookup = useRef<AbortController | null>(null);
  useEffect(() => () => lookup.current?.abort(), []);
  useEffect(() => {
    onBusy?.(busy);
  }, [busy, onBusy]);
  async function find(value = barcode) {
    if (lookup.current || disabled) return;
    const code = normalizeBarcode(value);
    changed?.();
    setError(undefined);
    if (!code) {
      setError(new Error(t("Enter a barcode of 1 to 50 characters.")));
      return;
    }
    setBarcode(code);
    const controller = new AbortController();
    lookup.current = controller;
    setBusy(true);
    try {
      const rows = await request<Service[]>(
        `/servicing?${new URLSearchParams({ barcode: code })}`,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      if (!rows.length) throw new Error(t("Service not found"));
      found(rows[0]);
    } catch (err) {
      if (!controller.signal.aborted) setError(err);
    } finally {
      if (lookup.current === controller) {
        lookup.current = null;
        setBusy(false);
      }
    }
  }
  return (
    <>
      <div className="scan">
        <input
          aria-label={t("Service barcode")}
          placeholder={t("Service barcode")}
          value={barcode}
          maxLength={50}
          disabled={busy || disabled}
          onChange={(e) => {
            setBarcode(e.target.value);
            changed?.();
            setError(undefined);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void find();
            }
          }}
        />
        <button
          type="button"
          className="secondary"
          disabled={busy || disabled}
          onClick={() => void find()}
        >
          {t("Find service")}
        </button>
        <BarcodeScanButton
          disabled={busy || disabled}
          onScan={(code) => void find(code)}
        />
      </div>
      <ErrorBox error={error} />
    </>
  );
}

function ServiceCheckout({
  initial,
  done,
}: {
  initial?: Service;
  done: (sale: Row) => void;
}) {
  const { t } = useLanguage();
  const [service, setService] = useState<Service | undefined>(initial);
  const [location, setLocation] = useState("");
  const [cost, setCost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const submitting = useRef(false);
  const op = useRef(new Operation());
  const locations = useQuery({
    queryKey: ["list", "service-locations"],
    queryFn: () => all("/locations"),
  });
  useEffect(() => {
    const active = locations.data?.filter((r) => r.is_active !== false);
    if (active?.length === 1) setLocation(String(active[0].id));
  }, [locations.data]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      !service ||
      service.sale ||
      service.status !== "finished" ||
      submitting.current
    )
      return;
    submitting.current = true;
    setBusy(true);
    setError(undefined);
    try {
      done(
        await op.current.send(
          "/servicing/sales",
          { barcode: service.barcode, location_id: Number(location), cost },
          "POST",
          true,
        ),
      );
    } catch (err) {
      setError(err);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <ServiceLookup
        disabled={busy}
        found={setService}
        changed={() => setService(undefined)}
      />
      {service && (
        <section aria-label={t("Service details")}>
          <p>
            {t("Barcode")}: <bdi>{text(service.barcode)}</bdi> ·{" "}
            <Badge value={service.status} />
          </p>
          {!!service.notes && <p>{text(service.notes)}</p>}
          {service.sale ? (
            <p role="status">{t("This service has already been paid")}</p>
          ) : (
            service.status !== "finished" && (
              <p role="status">
                {t("Finish the service before collecting payment")}
              </p>
            )
          )}
        </section>
      )}
      <label>
        {t("Location")}
        <Select field={locationField} value={location} change={setLocation} />
      </label>
      <label>
        {t("Cost (USD)")}
        <input
          aria-label={t("Cost (USD)")}
          type="number"
          min="0"
          step="0.01"
          required
          value={cost}
          disabled={busy}
          onChange={(e) => setCost(e.target.value)}
        />
      </label>
      <small>{t("Enter the amount collected for this service.")}</small>
      <ErrorBox error={error || locations.error} />
      <footer>
        <button
          type="submit"
          disabled={
            busy ||
            !location ||
            !service ||
            !!service.sale ||
            service.status !== "finished"
          }
        >
          {t(busy ? "Working…" : "Submit payment")}
        </button>
      </footer>
    </form>
  );
}

export function ServiceSaleButton({
  initial,
  onPaid,
  disabled = false,
}: {
  initial?: Service;
  onPaid?: () => void;
  disabled?: boolean;
}) {
  const { t } = useLanguage();
  const q = useQueryClient();
  const [open, setOpen] = useState(false);
  const [receipt, setReceipt] = useState<Row>();
  return (
    <>
      <button
        type="button"
        disabled={disabled}
        className="secondary"
        onClick={() => {
          setReceipt(undefined);
          setOpen(true);
        }}
      >
        {t("Service sale")}
      </button>
      {receipt && (
        <p role="status">
          {t("Service payment recorded")}:{" "}
          <bdi>
            {text(receipt.barcode)} · ${money(receipt.amount_usd)}
          </bdi>
        </p>
      )}
      {open && (
        <Modal title="Service sale" close={() => setOpen(false)}>
          <ServiceCheckout
            initial={initial}
            done={(sale) => {
              setReceipt(sale);
              setOpen(false);
              void q.invalidateQueries();
              onPaid?.();
            }}
          />
        </Modal>
      )}
    </>
  );
}

export function Servicing() {
  const { t } = useLanguage();
  const can = useCan();
  const q = useQueryClient();
  const [editing, setEditing] = useState<Service | null | undefined>();
  const [looking, setLooking] = useState(false);
  const op = useRef(new Operation());
  return (
    <>
      <div className="page-head">
        <h1>{t("Servicing")}</h1>
        <div className="actions">
          {can.employee && (
            <button disabled={looking} onClick={() => setEditing(null)}>
              {t("New service")}
            </button>
          )}
          {can.cashier && <ServiceSaleButton disabled={looking} />}
        </div>
      </div>
      {editing === undefined && (
        <ServiceLookup found={setEditing} onBusy={setLooking} />
      )}
      <section className="panel">
        <DataList
          path="/servicing"
          local
          columns={[
            { key: "barcode", label: "Barcode" },
            {
              key: "status",
              label: "Status",
              render: (r) => <Badge value={r.status} />,
            },
            {
              key: "payment",
              label: "Payment",
              render: (r) => t(r.sale ? "Paid" : "Unpaid"),
            },
            {
              key: "amount",
              label: "Collected (USD)",
              render: (r) =>
                (r as Service).sale
                  ? money((r as Service).sale!.amount_usd)
                  : "—",
            },
            { key: "notes", label: "Notes" },
          ]}
          view={(r) => setEditing(r)}
        />
      </section>
      {editing !== undefined && (
        <Modal
          key={editing?.id ?? "new"}
          title={editing ? "Service details" : "New service"}
          close={() => setEditing(undefined)}
        >
          {editing && (
            <>
              <p>
                {t("Barcode")}:{" "}
                <strong>
                  <bdi>{text(editing.barcode)}</bdi>
                </strong>
              </p>
              <p>
                <Badge value={editing.status} /> ·{" "}
                {t(editing.sale ? "Paid" : "Unpaid")}
              </p>
              {editing.sale && (
                <p>
                  {t("Collected (USD)")}: ${money(editing.sale.amount_usd)} ·{" "}
                  {date(editing.sale.created_at)}
                </p>
              )}
              {!!Number(editing.cost) && !editing.sale && (
                <p>
                  {t("Legacy estimate (USD)")}: ${money(editing.cost)}
                </p>
              )}
            </>
          )}
          {can.employee && !editing?.sale ? (
            <Form
              fields={fields}
              initial={
                editing
                  ? {
                      status: String(editing.status),
                      notes: String(editing.notes || ""),
                    }
                  : { status: "in_progress", notes: "" }
              }
              submit={async (v) => {
                const result = await op.current.send<Service>(
                  "/servicing" + (editing ? `/${editing.id}` : ""),
                  { status: v.status, notes: v.notes || null },
                  editing ? "PATCH" : "POST",
                  !editing,
                );
                setEditing(result);
              }}
              done={() => {
                void q.invalidateQueries();
              }}
            />
          ) : (
            <p>{text(editing?.notes)}</p>
          )}
          {can.cashier &&
            editing &&
            !editing.sale &&
            editing.status === "finished" && (
              <ServiceSaleButton
                initial={editing}
                onPaid={() => setEditing(undefined)}
              />
            )}
        </Modal>
      )}
    </>
  );
}
