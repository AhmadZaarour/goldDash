import { useState, type FormEvent } from "react";
import {
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { get, raw, request } from "./api";
import { useLanguage } from "./i18n";
import { PageHead } from "./pages";
import { Busy, ErrorBox, Modal } from "./ui";

const root = "/admin/data";
const pageSize = 25;

type DataColumn = {
  name: string;
  type:
    "string" | "integer" | "decimal" | "boolean" | "datetime" | "date" | "json";
  nullable: boolean;
  editable: boolean;
  primary_key: boolean;
};
type DataTable = {
  name: string;
  columns: DataColumn[];
};
type DataRecord = {
  key: Record<string, unknown>;
  values: Record<string, unknown>;
};
type RecordPage = { items: DataRecord[]; total: number };
type Draft = Record<string, string | null>;

const tablePath = (table: DataTable) =>
  `${root}/${encodeURIComponent(table.name)}`;

function displayValue(value: unknown): string {
  if (value == null) return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function displayKey(record: DataRecord) {
  return Object.entries(record.key)
    .map(([name, value]) => `${name} ${displayValue(value)}`)
    .join(" · ");
}

function draftValue(column: DataColumn, value: unknown): string | null {
  if (value == null) return null;
  return column.type === "json"
    ? JSON.stringify(value, null, 2)
    : String(value);
}

function RecordEditor({
  table,
  record,
  close,
  saved,
}: {
  table: DataTable;
  record: DataRecord;
  close: () => void;
  saved: () => void;
}) {
  const { t } = useLanguage();
  const columns = table.columns;
  const [draft, setDraft] = useState<Draft>(() =>
    Object.fromEntries(
      columns.map((column) => [
        column.name,
        draftValue(column, record.values[column.name]),
      ]),
    ),
  );
  const [validationError, setValidationError] = useState<Error>();
  const mutation = useMutation({
    mutationFn: (changes: Record<string, unknown>) =>
      request<DataRecord>(tablePath(table), {
        method: "PATCH",
        body: JSON.stringify({ key: record.key, changes }),
      }),
    onSuccess: saved,
  });
  const changed = columns.filter(
    (column) =>
      column.editable &&
      draft[column.name] !== draftValue(column, record.values[column.name]),
  );

  function change(name: string, value: string | null) {
    setDraft((previous) => ({ ...previous, [name]: value }));
    setValidationError(undefined);
    mutation.reset();
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!changed.length || mutation.isPending) return;

    const entries: [string, unknown][] = [];
    for (const column of changed) {
      const value = draft[column.name];
      let parsed: unknown = value;
      if (value !== null) {
        if (column.type === "json") {
          try {
            parsed = JSON.parse(value);
          } catch {
            setValidationError(
              new Error(`${column.name} · ${t("Enter valid JSON")}`),
            );
            return;
          }
        } else if (column.type === "integer") {
          parsed = Number(value);
          if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(parsed)) {
            setValidationError(
              new Error(`${column.name} · ${t("Enter a whole number")}`),
            );
            return;
          }
        } else if (column.type === "boolean") {
          parsed = value === "true";
        }
      }
      entries.push([column.name, parsed]);
    }

    mutation.mutate(Object.fromEntries(entries));
  }

  return (
    <Modal title="Record details" close={() => !mutation.isPending && close()}>
      <form onSubmit={submit}>
        <div className="form-grid">
          {columns.map((column) => (
            <div
              key={column.name}
              className={column.type === "json" ? "wide" : undefined}
            >
              <label>
                <span dir="ltr">{column.name}</span>
                {column.type === "boolean" ? (
                  <select
                    value={draft[column.name] ?? ""}
                    disabled={
                      !column.editable ||
                      mutation.isPending ||
                      draft[column.name] === null
                    }
                    onChange={(event) =>
                      change(column.name, event.target.value)
                    }
                  >
                    {draft[column.name] === null && <option value="">—</option>}
                    <option value="true">{t("Yes")}</option>
                    <option value="false">{t("No")}</option>
                  </select>
                ) : column.type === "json" ? (
                  <textarea
                    dir="ltr"
                    value={draft[column.name] ?? ""}
                    placeholder={draft[column.name] === null ? "—" : undefined}
                    readOnly={
                      !column.editable ||
                      mutation.isPending ||
                      draft[column.name] === null
                    }
                    onChange={(event) =>
                      change(column.name, event.target.value)
                    }
                  />
                ) : (
                  <input
                    dir={column.type === "string" ? "auto" : "ltr"}
                    type={
                      column.type === "date" && draft[column.name] !== null
                        ? "date"
                        : "text"
                    }
                    inputMode={
                      column.type === "decimal" || column.type === "integer"
                        ? "decimal"
                        : undefined
                    }
                    value={draft[column.name] ?? ""}
                    placeholder={draft[column.name] === null ? "—" : undefined}
                    readOnly={
                      !column.editable ||
                      mutation.isPending ||
                      draft[column.name] === null
                    }
                    onChange={(event) =>
                      change(column.name, event.target.value)
                    }
                  />
                )}
              </label>
              {column.editable && column.nullable && (
                <label className="data-null-toggle">
                  <input
                    type="checkbox"
                    checked={draft[column.name] === null}
                    disabled={mutation.isPending}
                    onChange={(event) =>
                      change(
                        column.name,
                        event.target.checked
                          ? null
                          : (draftValue(column, record.values[column.name]) ??
                              (column.type === "boolean" ? "false" : "")),
                      )
                    }
                  />
                  {t("No value")}
                </label>
              )}
            </div>
          ))}
        </div>
        <ErrorBox error={validationError || mutation.error} />
        <footer>
          <button
            type="button"
            className="secondary"
            disabled={mutation.isPending}
            onClick={close}
          >
            {t("Cancel")}
          </button>
          <button
            type="submit"
            disabled={!changed.length || mutation.isPending}
          >
            {t(mutation.isPending ? "Working…" : "Save")}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

function DeleteRecord({
  table,
  record,
  close,
  deleted,
}: {
  table: DataTable;
  record: DataRecord;
  close: () => void;
  deleted: () => void;
}) {
  const { t } = useLanguage();
  const mutation = useMutation({
    mutationFn: () =>
      raw(tablePath(table), {
        method: "DELETE",
        body: JSON.stringify({ key: record.key }),
      }),
    onSuccess: deleted,
  });

  return (
    <Modal title="Delete record" close={() => !mutation.isPending && close()}>
      <p>{t("Permanently delete this record?")}</p>
      <p>
        <bdi>
          {table.name} · {displayKey(record)}
        </bdi>
      </p>
      <ErrorBox error={mutation.error} />
      <footer>
        <button
          className="secondary"
          disabled={mutation.isPending}
          onClick={close}
        >
          {t("Cancel")}
        </button>
        <button
          className="secondary danger"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {t(mutation.isPending ? "Working…" : "Delete")}
        </button>
      </footer>
    </Modal>
  );
}

export function AdminData() {
  const { t } = useLanguage();
  const client = useQueryClient();
  const [tableName, setTableName] = useState("");
  const [lookup, setLookup] = useState("");
  const [recordKey, setRecordKey] = useState("");
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<DataRecord>();
  const [deleting, setDeleting] = useState<DataRecord>();
  const catalog = useQuery({
    queryKey: ["admin-data-tables"],
    queryFn: () => get<{ tables: DataTable[] }>(root),
  });
  const tables = catalog.data?.tables ?? [];
  const table = tables.find((value) => value.name === tableName) ?? tables[0];
  const primaryKeys = table?.columns.filter((column) => column.primary_key);
  const page = useQuery({
    queryKey: ["admin-data-records", table?.name, offset, recordKey],
    queryFn: table
      ? () => {
          const params = new URLSearchParams({
            limit: String(pageSize),
            offset: String(offset),
          });
          if (recordKey) params.set("key", recordKey);
          return get<RecordPage>(`${tablePath(table)}?${params}`);
        }
      : skipToken,
  });
  const previewColumns =
    table?.columns
      .filter((column) => !column.primary_key && column.type !== "json")
      .slice(0, 4) ?? [];
  const items = page.data?.items ?? [];
  const total = page.data?.total ?? 0;

  function complete(message: string) {
    setNotice(message);
    setEditing(undefined);
    setDeleting(undefined);
    void client.invalidateQueries();
  }

  function applyLookup(value: string) {
    setRecordKey(value);
    setOffset(0);
    setNotice("");
  }

  return (
    <>
      <PageHead
        title="Data management"
        description="Edit or delete stored records across workspaces. Corrections may require matching changes to linked records."
      />
      <section className="panel">
        {notice && (
          <div className="notice success" role="status">
            {t(notice)}
          </div>
        )}
        <ErrorBox error={catalog.error || page.error} />
        {catalog.isLoading && <Busy />}
        {table && (
          <>
            <div className="table-tools data-tools">
              <label>
                <span>{t("Database table")}</span>
                <select
                  dir="ltr"
                  value={table.name}
                  onChange={(event) => {
                    setTableName(event.target.value);
                    setLookup("");
                    applyLookup("");
                  }}
                >
                  {tables.map(({ name }) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </label>
              {primaryKeys?.length === 1 && (
                <form
                  className="data-record-lookup"
                  onSubmit={(event) => {
                    event.preventDefault();
                    applyLookup(
                      primaryKeys[0].type === "integer"
                        ? lookup.trim()
                        : lookup,
                    );
                  }}
                >
                  <label>
                    <span>
                      {t("Find by primary key")}{" "}
                      <bdi>({primaryKeys[0].name})</bdi>
                    </span>
                    <input
                      dir="ltr"
                      inputMode={
                        primaryKeys[0].type === "integer"
                          ? "numeric"
                          : undefined
                      }
                      value={lookup}
                      onChange={(event) => setLookup(event.target.value)}
                    />
                  </label>
                  <button type="submit" className="secondary">
                    {t("Search")}
                  </button>
                  {(lookup || recordKey) && (
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => {
                        setLookup("");
                        applyLookup("");
                      }}
                    >
                      {t("Clear")}
                    </button>
                  )}
                </form>
              )}
            </div>
            {page.isLoading ? (
              <Busy />
            ) : (
              page.data && (
                <>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t("Database record")}</th>
                          {previewColumns.map(({ name }) => (
                            <th key={name}>{name}</th>
                          ))}
                          <th>
                            <span className="sr-only">{t("Details")}</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((record) => (
                          <tr key={JSON.stringify(record.key)}>
                            <td data-label={t("Database record")}>
                              <bdi>{displayKey(record)}</bdi>
                            </td>
                            {previewColumns.map(({ name }) => {
                              const value = displayValue(record.values[name]);
                              return (
                                <td key={name} data-label={name}>
                                  <bdi>
                                    {value.length > 40
                                      ? `${value.slice(0, 40)}…`
                                      : value}
                                  </bdi>
                                </td>
                              );
                            })}
                            <td className="row-actions">
                              <button
                                className="ghost"
                                onClick={() => setEditing(record)}
                              >
                                {t("View / edit")}
                              </button>
                              <button
                                className="ghost danger"
                                onClick={() => setDeleting(record)}
                              >
                                {t("Delete")}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!items.length && (
                      <div className="empty">{t("No matching records")}</div>
                    )}
                  </div>
                  <div className="pagination">
                    <span>
                      {t("Showing")} {items.length ? offset + 1 : 0}–
                      {items.length ? offset + items.length : 0} {t("of")}{" "}
                      {total}
                    </span>
                    <div>
                      <button
                        className="icon"
                        aria-label={t("Previous")}
                        disabled={offset === 0}
                        onClick={() => setOffset(offset - pageSize)}
                      >
                        <ChevronLeft size={18} />
                      </button>
                      <button
                        className="icon"
                        aria-label={t("Next")}
                        disabled={offset + pageSize >= total}
                        onClick={() => setOffset(offset + pageSize)}
                      >
                        <ChevronRight size={18} />
                      </button>
                    </div>
                  </div>
                </>
              )
            )}
          </>
        )}
      </section>
      {table && editing && (
        <RecordEditor
          table={table}
          record={editing}
          close={() => setEditing(undefined)}
          saved={() => complete("Record updated")}
        />
      )}
      {table && deleting && (
        <DeleteRecord
          table={table}
          record={deleting}
          close={() => setDeleting(undefined)}
          deleted={() => {
            if (offset > 0 && items.length === 1) setOffset(offset - pageSize);
            complete("Record deleted");
          }}
        />
      )}
    </>
  );
}
