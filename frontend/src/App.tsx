import { useEffect, useState } from "react";
import { api, getToken, setToken, type User } from "./api";
import { useHash } from "./hooks";
import { ConfirmProvider } from "./components/Confirm";
import { LiveProvider } from "./live";
import { AuthPage } from "./pages/AuthPage";
import { GroupPage } from "./pages/GroupPage";
import { GroupsPage } from "./pages/GroupsPage";
import { JoinPage } from "./pages/JoinPage";
import { Header } from "./components/Header";

export default function App() {
  const hash = useHash();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(!getToken());

  useEffect(() => {
    if (!getToken()) return;
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setChecked(true));
  }, []);

  useEffect(() => {
    const expired = () => setUser(null);
    window.addEventListener("auth-expired", expired);
    return () => window.removeEventListener("auth-expired", expired);
  }, []);

  if (!checked) return <div className="center muted">Загрузка…</div>;
  if (!user) {
    return <AuthPage onAuth={(u) => { setUser(u); if (!location.hash) location.hash = "/"; }} next={hash} />;
  }

  const logout = async () => {
    try { await api.logout(); } catch { /* the token is dropped locally either way */ }
    setToken(null);
    setUser(null);
    location.hash = "/";
  };
  const join = hash.match(/^\/join\/(.+)$/);
  const group = hash.match(/^\/groups\/(\d+)$/);

  return (
    <LiveProvider>
      <ConfirmProvider>
        <Header user={user} onLogout={logout} />
        <main className="container">
          {join ? <JoinPage token={join[1]} /> : group ? <GroupPage key={group[1]} id={Number(group[1])} user={user} /> : <GroupsPage />}
        </main>
      </ConfirmProvider>
    </LiveProvider>
  );
}
