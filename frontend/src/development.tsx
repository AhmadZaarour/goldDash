import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, request } from "./api";
import { useLanguage } from "./i18n";
import { ErrorBox, Modal } from "./ui";

const confirmationText = "CLEAR DEVELOPMENT DATA";

export function DevelopmentReset() {
  const { t } = useLanguage();
  const queries = useQueryClient();
  const status = useQuery({
    queryKey: ["development-reset-status"],
    queryFn: () => get<{ enabled: boolean }>("/development/reset-status"),
    retry: false,
  });
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [result, setResult] = useState<string>();
  async function reset(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const response = await request<{ photo_cleanup_complete: boolean }>(
        "/development/reset",
        {
          method: "POST",
          body: JSON.stringify({ confirmation }),
        },
      );
      setOpen(false);
      setConfirmation("");
      setResult(
        response.photo_cleanup_complete
          ? "Development data cleared. Staff accounts are preserved."
          : "Business data cleared. Some uploaded photos could not be removed; check development storage.",
      );
      await queries.resetQueries({
        predicate: (q) => q.queryKey[0] !== "development-reset-status",
      });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  if (!status.data?.enabled) return null;
  return (
    <section className="panel">
      <h2>{t("Development tools")}</h2>
      <p>
        {t(
          "Clear business data from this disposable development database. Staff accounts and login access are preserved.",
        )}
      </p>
      <button
        className="secondary danger"
        onClick={() => {
          setError(undefined);
          setConfirmation("");
          setResult(undefined);
          setOpen(true);
        }}
      >
        {t("Clear all development data")}
      </button>
      {result && <p role="status">{t(result)}</p>}
      {open && (
        <Modal
          title="Clear all development data"
          close={() => {
            if (!busy) setOpen(false);
          }}
        >
          <form onSubmit={reset}>
            <p>
              {t(
                "This permanently deletes catalog, suppliers, customers, inventory, purchases, sales, returns, payments, cash history and uploaded item photos. It cannot be undone.",
              )}
            </p>
            <p>
              {t(
                "Use this only when nobody else is working in the development system.",
              )}
            </p>
            <p>
              {t("Type the exact phrase to confirm")}:{" "}
              <bdi>
                <strong>{confirmationText}</strong>
              </bdi>
            </p>
            <label>
              {t("Confirmation phrase")}
              <input
                aria-label={t("Confirmation phrase")}
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                dir="ltr"
                disabled={busy}
              />
            </label>
            <ErrorBox error={error} />
            <footer>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setOpen(false)}
              >
                {t("Cancel")}
              </button>
              <button
                type="submit"
                className="secondary danger"
                disabled={busy || confirmation !== confirmationText}
              >
                {t(busy ? "Working…" : "Delete development data")}
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </section>
  );
}
