import { useEffect, useState } from "react";
import { api, type User } from "../api";
import { useResource } from "../hooks";

export function Header({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const [mailOpen, setMailOpen] = useState(false);
  const notes = useResource(() => api.notifications(), []);
  const mail = useResource(() => api.outbox(), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); setMailOpen(false); } };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);
  const unread = (notes.data ?? []).filter((n) => !n.read).length;

  async function toggle() {
    setOpen(!open);
    if (!open && unread) {
      await api.readNotifications();
      setTimeout(notes.reload, 1500);
    }
  }

  return (
    <header className="topbar">
      <a className="brand" href="#/">Fairshare</a>
      <div className="spacer" />
      <div className="menu">
        <button className="ghost" onClick={() => setMailOpen(!mailOpen)} aria-label="Письма (заглушка)" aria-expanded={mailOpen}>✉ Письма</button>
        {mailOpen && (
          <div className="popover wide">
            <div className="muted small">Почта — заглушка: здесь письма, «отправленные» на ваш адрес.</div>
            {(mail.data ?? []).length === 0 && <div className="muted">Писем нет</div>}
            {(mail.data ?? []).map((m) => (
              <details key={m.id}><summary>{m.subject}</summary><pre>{m.body}</pre></details>
            ))}
          </div>
        )}
      </div>
      <div className="menu">
        <button className="ghost" onClick={toggle} aria-label="Уведомления" aria-expanded={open}>
          🔔{unread > 0 && <span className="badge" data-testid="unread">{unread}</span>}
        </button>
        {open && (
          <div className="popover">
            {(notes.data ?? []).length === 0 && <div className="muted">Пока тихо</div>}
            {(notes.data ?? []).slice(0, 20).map((n) => (
              <a key={n.id} href={n.group_id ? `#/groups/${n.group_id}` : "#/"} onClick={() => setOpen(false)} className={`note ${n.read ? "" : "unread"}`}>
                {n.text}
              </a>
            ))}
          </div>
        )}
      </div>
      <span className="muted small">{user.name}</span>
      <button className="ghost" onClick={onLogout}>Выйти</button>
    </header>
  );
}
