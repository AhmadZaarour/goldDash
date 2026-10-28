import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  Search,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import Decimal from "decimal.js";
import { all, list, get, type Row, ApiError } from "./api";
import { useLanguage } from "./i18n";
export const text = (x: unknown) => (x == null ? "—" : String(x));
export const money = (x: unknown) => {
  try {
    return new Decimal(String(x ?? 0)).toFixed(2);
  } catch {
    return "—";
  }
};
export const date = (x: unknown) =>
  x
    ? new Date(String(x)).toLocaleString(
        document.documentElement.lang === "ar" ? "ar-LB" : "en-GB",
      )
    : "—";
export function ErrorBox({ error }: { error: unknown }) {
  const { t } = useLanguage();
  return error ? (
    <div className="notice error" role="alert">
      {t("Something went wrong")} ·{" "}
      {error instanceof ApiError && error.status === 401
        ? t("Session expired")
        : error instanceof Error
          ? error.message
          : t("Try again")}
    </div>
  ) : null;
}
export function Busy() {
  const { t } = useLanguage();
  return (
    <div className="busy">
      <LoaderCircle className="spin" size={18} />
      {t("Loading…")}
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useLanguage();
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <header>
        <h2>{t(title)}</h2>
        <button
          className="icon"
          type="button"
          aria-label={t("Close")}
          onClick={close}
        >
          <X />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export interface Field {
  key: string;
  label: string;
  type?:
    | "text"
    | "number"
    | "money"
    | "select"
    | "textarea"
    | "password"
    | "datetime-local"
    | "checkbox";
  required?: boolean;
  resource?: string;
  options?: string[];
  filter?: (r: Row) => boolean;
  min?: string;
  maxLength?: number;
  step?: string;
  optional?: boolean;
}
export type Values = Record<string, string | boolean>;
export function Select({
  field,
  value,
  change,
}: {
  field: Field;
  value: string;
  change: (v: string) => void;
}) {
  const { t } = useLanguage();
  const q = useQuery({
    queryKey: ["options", field.resource],
    queryFn: () => all("/" + field.resource),
    enabled: !!field.resource,
  });
  return (
    <select
      aria-label={t(field.label)}
      required={field.required}
      value={value}
      onChange={(e) => change(e.target.value)}
      disabled={q.isLoading}
    >
      <option value="">{t(field.optional ? "All" : "Choose…")}</option>
      {field.options?.map((v) => (
        <option key={v} value={v}>
          {t(v)}
        </option>
      ))}
      {q.data?.filter(field.filter || (() => true)).map((r) => (
        <option key={r.id} value={r.id}>
          {text(
            r.product_name ??
              r.name ??
              r.barcode ??
              r.username ??
              r.code ??
              r.id,
          )}
          {r.sku ? ` · ${text(r.sku)}` : ""}
        </option>
      ))}
    </select>
  );
}
export function Fields({
  fields,
  values,
  set,
}: {
  fields: Field[];
  values: Values;
  set: (v: Values) => void;
}) {
  const { t } = useLanguage();
  return (
    <div className="form-grid">
      {fields.map((f) => (
        <label key={f.key} className={f.type === "textarea" ? "wide" : ""}>
          <span>
            {t(f.label)}
            {f.required && (
              <b className="required" aria-hidden="true">
                {" "}
                *
              </b>
            )}
          </span>
          {f.type === "select" ? (
            <Select
              field={f}
              value={String(values[f.key] ?? "")}
              change={(v) => set({ ...values, [f.key]: v })}
            />
          ) : f.type === "checkbox" ? (
            <input
              aria-label={t(f.label)}
              type="checkbox"
              checked={values[f.key] !== false}
              onChange={(e) => set({ ...values, [f.key]: e.target.checked })}
            />
          ) : f.type === "textarea" ? (
            <textarea
              aria-label={t(f.label)}
              maxLength={f.maxLength ?? 200}
              value={String(values[f.key] ?? "")}
              onChange={(e) => set({ ...values, [f.key]: e.target.value })}
            />
          ) : (
            <input
              aria-label={t(f.label)}
              type={f.type === "money" ? "text" : f.type || "text"}
              inputMode={f.type === "money" ? "decimal" : undefined}
              pattern={f.type === "money" ? "[0-9]+([.][0-9]+)?" : undefined}
              required={f.required}
              value={String(values[f.key] ?? "")}
              min={f.min}
              step={f.step || "any"}
              maxLength={f.maxLength ?? (f.type === "password" ? 128 : 500)}
              onChange={(e) =>
                set({
                  ...values,
                  [f.key]:
                    f.type === "money" || f.type === "number"
                      ? e.target.value
                          .replace(/[٠-٩]/g, (c) =>
                            String("٠١٢٣٤٥٦٧٨٩".indexOf(c)),
                          )
                          .replace(/٫/g, ".")
                          .replace(/٬/g, "")
                      : e.target.value,
                })
              }
            />
          )}
        </label>
      ))}
    </div>
  );
}
export function toPayload(fields: Field[], values: Values) {
  const data: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.key];
    if (v === "" || v === undefined) {
      if (!f.required) data[f.key] = null;
      continue;
    }
    data[f.key] =
      f.type === "number" || (f.type === "select" && f.resource)
        ? Number(v)
        : v;
  }
  return data;
}
export function Form({
  fields,
  initial = {},
  submit,
  done,
  children,
  button = "Save",
}: {
  fields: Field[];
  initial?: Values;
  submit: (v: Values) => Promise<unknown>;
  done: () => void;
  children?: ReactNode;
  button?: string;
}) {
  const [v, set] = useState<Values>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const { t } = useLanguage();
  async function send(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await submit(v);
      done();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={send}>
      <Fields fields={fields} values={v} set={set} />
      {children}
      <ErrorBox error={error} />
      <footer>
        <button type="submit" disabled={busy}>
          {t(busy ? "Working…" : button)}
        </button>
      </footer>
    </form>
  );
}
export interface Column {
  key: string;
  label: string;
  render?: (r: Row) => ReactNode;
}
export function DataList({
  path,
  columns,
  params = {},
  view,
  edit,
  searchable = true,
  local = false,
}: {
  path: string;
  columns: Column[];
  params?: Record<string, string | number>;
  view?: (r: Row) => void;
  edit?: (r: Row) => void;
  searchable?: boolean;
  local?: boolean;
}) {
  const { t } = useLanguage();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(search);
      setOffset(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => setOffset(0), [JSON.stringify(params), path]);
  const page = useQuery({
    queryKey: ["list", path, params, q, offset],
    queryFn: async () => {
      if (local) {
        const rows = (await get<Row[]>(path)).filter((r) =>
          Object.values(r).some((v) =>
            text(v).toLowerCase().includes(q.toLowerCase()),
          ),
        );
        return { rows: rows.slice(offset, offset + 20), total: rows.length };
      }
      return list(path, { ...params, limit: 20, offset, ...(q ? { q } : {}) });
    },
  });
  return (
    <>
      <div className="table-tools">
        {searchable && (
          <label className="search">
            <Search size={17} />
            <input
              aria-label={t("Search")}
              placeholder={t("Search")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        )}
        <span className="muted">
          {page.data?.total ?? "—"} {t("Items")}
        </span>
      </div>
      <ErrorBox error={page.error} />
      {page.isLoading ? (
        <Busy />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.key}>{t(c.label)}</th>
                ))}
                {(view || edit) && (
                  <th>
                    <span className="sr-only">{t("Details")}</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {page.data?.rows.map((r) => (
                <tr key={r.id}>
                  {columns.map((c) => (
                    <td key={c.key} data-label={t(c.label)}>
                      {c.render ? (
                        c.render(r)
                      ) : referenceResources[c.key] ? (
                        <ReferenceName
                          resource={referenceResources[c.key]}
                          value={r[c.key]}
                        />
                      ) : (
                        text(r[c.key])
                      )}
                    </td>
                  ))}
                  {(view || edit) && (
                    <td className="row-actions">
                      {view && (
                        <button className="ghost" onClick={() => view(r)}>
                          {t("View")}
                        </button>
                      )}
                      {edit && (
                        <button className="ghost" onClick={() => edit(r)}>
                          {t("Edit")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {page.data?.rows.length === 0 && (
            <div className="empty">{t("No matching records")}</div>
          )}
        </div>
      )}
      <div className="pagination">
        <span>
          {t("Showing")} {page.data?.rows.length ? offset + 1 : 0}–
          {offset + (page.data?.rows.length ?? 0)} {t("of")}{" "}
          {page.data?.total ?? 0}
        </span>
        <div>
          <button
            className="icon"
            aria-label={t("Previous")}
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            <ChevronLeft size={18} />
          </button>
          <button
            className="icon"
            aria-label={t("Next")}
            disabled={offset + 20 >= (page.data?.total ?? 0)}
            onClick={() => setOffset(offset + 20)}
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
    </>
  );
}
export function Badge({ value }: { value: unknown }) {
  const { t } = useLanguage();
  return (
    <span
      className={"badge " + (value === "sold" || value === false ? "dim" : "")}
    >
      {t(
        value === true ? "Active" : value === false ? "Inactive" : text(value),
      )}
    </span>
  );
}
export const active = (r: Row) => r.is_active !== false;
export const locationField: Field = {
  key: "location_id",
  label: "Location",
  type: "select",
  resource: "locations",
  required: true,
  filter: active,
};
export const supplierField: Field = {
  key: "supplier_id",
  label: "Supplier",
  type: "select",
  resource: "suppliers",
  required: true,
  filter: active,
};

const referenceResources: Record<string, string> = {
  product_id: "products",
  category_id: "categories",
  purity_id: "goldpurities",
  gold_purity_id: "goldpurities",
  supplier_id: "suppliers",
  customer_id: "customers",
  location_id: "locations",
  from_location_id: "locations",
  to_location_id: "locations",
  source_location_id: "locations",
  destination_location_id: "locations",
};
export function ReferenceName({
  resource,
  value,
}: {
  resource: string;
  value: unknown;
}) {
  const q = useQuery({
    queryKey: ["options", resource],
    queryFn: () => all("/" + resource),
    enabled: value != null,
  });
  const record = q.data?.find((r) => String(r.id) === String(value));
  return (
    <>
      {record
        ? text(record.name ?? record.code)
        : value == null
          ? "—"
          : "#" + text(value)}
    </>
  );
}
