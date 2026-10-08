import { useState } from "react";
import { api, setToken, type User } from "../api";

export function AuthPage({ onAuth, next }: { onAuth: (u: User) => void; next: string }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = mode === "login" ? await api.login(email, password) : await api.register(email, name, password);
      setToken(res.token);
      onAuth(res.user);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card auth" onSubmit={submit}>
        <h1>Fairshare</h1>
        <p className="muted">
          {next.startsWith("/join/") ? "Войдите, чтобы присоединиться к группе." : "Общие расходы без споров о копейках."}
        </p>
        {mode === "register" && (
          <label>Имя<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} /></label>
        )}
        <label>E-mail<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Пароль<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} /></label>
        {error && <div className="error" role="alert">{error}</div>}
        <button className="primary" disabled={busy}>{mode === "login" ? "Войти" : "Создать аккаунт"}</button>
        <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
        </button>
      </form>
    </div>
  );
}
