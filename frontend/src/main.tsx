import "@fontsource/dm-sans/latin-400.css";
import "@fontsource/dm-sans/latin-600.css";
import "@fontsource/noto-sans-arabic/arabic-400.css";
import "@fontsource/noto-sans-arabic/arabic-600.css";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  Gem,
  LayoutDashboard,
  Package,
  ShoppingBag,
  Truck,
  Users,
  Wallet,
  Layers,
  Wrench,
  UserPlus,
  LogOut,
  Languages,
  Menu,
  X,
} from "lucide-react";
import { login, logout, get, renew, onExpired, type User } from "./api";
import { Language, useLanguage } from "./i18n";
import { SessionProvider } from "./session";
import {
  Dashboard,
  Inventory,
  Trades,
  Suppliers,
  Cash,
  Catalog,
  Servicing,
  Staff,
} from "./pages";
import { Busy, Form } from "./ui";
import "./styles.css";
const client = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
function App() {
  const { t, toggle, lang } = useLanguage();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  useEffect(() => setMenu(false), [location.pathname]);
  useEffect(() => {
    onExpired(() => {
      setUser(null);
      client.clear();
    });
    renew()
      .then(async (ok) => {
        if (ok) setUser(await get<User>("/auth/me"));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  async function signout() {
    try {
      await logout();
    } finally {
      client.clear();
      setUser(null);
    }
  }
  if (loading)
    return (
      <main className="boot">
        <Gem size={32} />
        <Busy />
      </main>
    );
  if (!user)
    return (
      <div className="login-layout">
        <aside className="login-art">
          <div className="brand">
            <Gem />
            GoldDash
          </div>
          <div>
            <span className="eyebrow">{t("Shop workspace")}</span>
            <h1>{t("Your shop, in balance.")}</h1>
            <p>
              {t("Manage your pieces, people and daily trade in one place.")}
            </p>
          </div>
          <span>GOLDDASH · 24K</span>
        </aside>
        <main className="login-main">
          <button className="language ghost" onClick={toggle}>
            <Languages size={17} />
            {lang === "en" ? "العربية" : "English"}
          </button>
          <div className="login-card">
            <Gem className="login-gem" size={30} />
            <h2>{t("Welcome back")}</h2>
            <p>{t("Sign in to your workspace")}</p>
            <Form
              fields={[
                { key: "email", label: "Email", required: true },
                {
                  key: "password",
                  label: "Password",
                  type: "password",
                  required: true,
                },
              ]}
              submit={async (v) => {
                const me = await login(String(v.email), String(v.password));
                client.clear();
                setUser(me);
              }}
              done={() => {}}
              button="Sign in"
            />
            <small>
              {t(
                "Public signup is disabled. Ask your administrator for an account.",
              )}
            </small>
          </div>
        </main>
      </div>
    );
  const nav = [
    { to: "/", label: "Overview", icon: LayoutDashboard, allow: true },
    { to: "/inventory", label: "Inventory", icon: Package, allow: true },
    { to: "/sales", label: "Sales", icon: ShoppingBag, allow: true },
    { to: "/purchases", label: "Purchases", icon: Truck, allow: true },
    { to: "/suppliers", label: "Suppliers", icon: Users, allow: true },
    {
      to: "/cash",
      label: "Cash drawer",
      icon: Wallet,
      allow: user.role !== "employee",
    },
    { to: "/catalog", label: "Catalog", icon: Layers, allow: true },
    {
      to: "/servicing",
      label: "Servicing",
      icon: Wrench,
      allow: user.role !== "cashier",
    },
    {
      to: "/staff",
      label: "Staff accounts",
      icon: UserPlus,
      allow: user.role === "admin",
    },
  ];
  return (
    <SessionProvider user={user}>
      <div className="workspace">
        <aside className={"sidebar " + (menu ? "open" : "")}>
          <div className="brand">
            <Gem size={28} />
            <span>
              GoldDash<small>{t("Shop workspace")}</small>
            </span>
            <button
              className="icon mobile"
              aria-label={t("Close")}
              onClick={() => setMenu(false)}
            >
              <X />
            </button>
          </div>
          <nav>
            {nav
              .filter((n) => n.allow)
              .map((n) => (
                <NavLink to={n.to} end={n.to === "/"} key={n.to}>
                  <n.icon size={19} />
                  {t(n.label)}
                </NavLink>
              ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="avatar">{user.username[0]?.toUpperCase()}</div>
            <div>
              <strong>{user.username}</strong>
              <small>{t(user.role)}</small>
            </div>
            <button
              className="icon"
              aria-label={t("Sign out")}
              onClick={() => void signout()}
            >
              <LogOut size={17} />
            </button>
          </div>
        </aside>
        {menu && (
          <div className="nav-backdrop" onClick={() => setMenu(false)} />
        )}
        <div className="main-column">
          <header className="topbar">
            <button
              className="icon mobile"
              aria-label="Menu"
              onClick={() => setMenu(true)}
            >
              <Menu />
            </button>
            <span className="breadcrumb">
              {t(
                nav.find((n) => n.to === location.pathname)?.label ||
                  "Overview",
              )}
            </span>
            <div className="topbar-right">
              <span className="today">
                {new Intl.DateTimeFormat(lang === "ar" ? "ar-LB" : "en-GB", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                }).format(new Date())}
              </span>
              <button className="ghost" onClick={toggle}>
                <Languages size={17} />
                {lang === "en" ? "العربية" : "English"}
              </button>
            </div>
          </header>
          <main className="content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/inventory" element={<Inventory />} />
              <Route path="/sales" element={<Trades />} />
              <Route path="/purchases" element={<Trades purchase />} />
              <Route path="/suppliers" element={<Suppliers />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route
                path="/cash"
                element={
                  user.role !== "employee" ? (
                    <Cash />
                  ) : (
                    <Navigate to="/" replace />
                  )
                }
              />
              <Route
                path="/servicing"
                element={
                  user.role !== "cashier" ? (
                    <Servicing />
                  ) : (
                    <Navigate to="/" replace />
                  )
                }
              />
              <Route
                path="/staff"
                element={
                  user.role === "admin" ? (
                    <Staff />
                  ) : (
                    <Navigate to="/" replace />
                  )
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <footer className="app-footer">
            GoldDash <span>•</span>{" "}
            {t("Amounts are in USD; weights are in grams.")}
          </footer>
        </div>
      </div>
    </SessionProvider>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <Language>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </Language>
    </QueryClientProvider>
  </StrictMode>,
);
