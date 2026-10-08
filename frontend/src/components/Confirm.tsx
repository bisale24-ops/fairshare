import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type Ask = (message: string, options?: { confirmLabel?: string; danger?: boolean; info?: boolean }) => Promise<boolean>;
const Ctx = createContext<Ask>(async () => false);

/** In-app dialogs instead of the browser's confirm()/alert(): readable, themed, keyboard-friendly (Escape cancels). */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [req, setReq] = useState<{ message: string; confirmLabel: string; danger: boolean; info: boolean; resolve: (v: boolean) => void } | null>(null);
  const ref = useRef<HTMLDialogElement>(null);

  const ask: Ask = useCallback(
    (message, options) => new Promise((resolve) => setReq({ message, confirmLabel: options?.confirmLabel ?? "Да", danger: !!options?.danger, info: !!options?.info, resolve })),
    [],
  );
  useEffect(() => {
    if (req && ref.current && !ref.current.open) ref.current.showModal();
  }, [req]);

  const finish = (v: boolean) => {
    ref.current?.close();
    req?.resolve(v);
    setReq(null);
  };

  return (
    <Ctx.Provider value={ask}>
      {children}
      {req && (
        <dialog ref={ref} role="alertdialog" aria-modal="true" aria-label={req.message} className="dialog" onCancel={(e) => { e.preventDefault(); finish(false); }}>
          <p>{req.message}</p>
          <div className="row">
            <button className={req.danger ? "danger-btn" : "primary"} autoFocus onClick={() => finish(true)}>{req.info ? "Понятно" : req.confirmLabel}</button>
            {!req.info && <button className="ghost" onClick={() => finish(false)}>Отмена</button>}
          </div>
        </dialog>
      )}
    </Ctx.Provider>
  );
}

export const useConfirm = () => useContext(Ctx);
