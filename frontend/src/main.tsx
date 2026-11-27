import { Production, FactorySales, FactoryInventory } from "./factory";
import { Servicing } from "./servicing";
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
  useNavigate,
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
import {
  getWorkspace,
  setWorkspace,
  type Workspace,
  login,
  logout,
  get,
  renew,
  onExpired,
  type User,
} from "./api";
import { Language, useLanguage } from "./i18n";
import { SessionProvider } from "./session";
import {
  Dashboard,
  Inventory,
  Trades,
  Suppliers,
  Cash,
  Catalog,
  Staff,
} from "./pages";
import {
  BalanceSetup,
  InternalTrade,
  WorkspaceReports,
  LegacyHistory,
} from "./operations";
import { Busy, Form } from "./ui";
import "./styles.css";
const client = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
const workspaceLabels = {
  showroom: "Showroom",
  factory: "Factory",
  legacy: "Unassigned history",
};
function App() {
  const { t, toggle, lang } = useLanguage();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const [workspace, changeWorkspace] = useState<Workspace>(getWorkspace());
  function enterWorkspace(unit: Workspace) {
    setWorkspace(unit);
    changeWorkspace(unit);
    client.clear();
    setMenu(false);
    navigate("/");
  }
  function signedIn(me: User) {
    const saved = getWorkspace();
    const unit =
      me.role === "employee"
        ? "factory"
        : me.role === "admin" && (saved === "factory" || saved === "legacy")
          ? saved
          : "showroom";
    setWorkspace(unit);
    changeWorkspace(unit);
    setUser(me);
  }
  useEffect(() => setMenu(false), [location.pathname]);
  useEffect(() => {
    onExpired(() => {
      setUser(null);
      client.clear();
    });
    renew()
      .then(async (ok) => {
        if (ok) signedIn(await get<User>("/auth/me"));
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
                {
                  key: "identifier",
                  label: "Username or email",
                  required: true,
                  maxLength: 255,
                  autoComplete: "username",
                },
                {
                  key: "password",
                  label: "Password",
                  type: "password",
                  required: true,
                  autoComplete: "current-password",
                },
              ]}
              submit={async (v) => {
                const me = await login(String(v.identifier), String(v.password));
                client.clear();
                signedIn(me);
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
  const admin = user.role === "admin";
  const employee = user.role === "employee";
  const isFactory = workspace === "factory";
  const isLegacy = workspace === "legacy";
  const home = employee ? "/production" : "/";
  const screens = [
    {
      to: "/",
      label: "Overview",
      icon: LayoutDashboard,
      allow: !employee,
      element: isLegacy ? <LegacyHistory /> : <Dashboard />,
    },
    {
      to: "/inventory",
      label: "Inventory",
      icon: Package,
      allow: !employee,
      element: isFactory ? <FactoryInventory /> : <Inventory />,
    },
    {
      to: "/sales",
      label: "Sales",
      icon: ShoppingBag,
      allow: !employee,
      element: isFactory ? (
        <FactorySales />
      ) : isLegacy ? (
        <LegacyHistory />
      ) : (
        <Trades />
      ),
    },
    {
      to: "/purchases",
      label: "Purchases",
      icon: Truck,
      allow: !employee,
      element: <Trades purchase />,
    },
    {
      to: "/suppliers",
      label: "Suppliers",
      icon: Users,
      allow: !employee,
      element: <Suppliers />,
    },
    {
      to: "/cash",
      label: "Cash drawer",
      icon: Wallet,
      allow: !employee,
      element: <Cash />,
    },
    {
      to: "/catalog",
      label: "Catalog",
      icon: Layers,
      allow: !employee,
      element: <Catalog />,
    },
    {
      to: "/servicing",
      label: "Servicing",
      icon: Wrench,
      allow: true,
      element: <Servicing />,
    },
    {
      to: "/staff",
      label: "Staff accounts",
      icon: UserPlus,
      allow: admin,
      element: <Staff />,
    },
    {
      to: "/balances",
      label: "Opening balances",
      icon: Wallet,
      allow: admin && !isLegacy,
      element: <BalanceSetup />,
    },
    {
      to: "/production",
      label: "Production",
      icon: Wrench,
      allow: isFactory && (admin || employee),
      element: <Production />,
    },
    {
      to: "/internal",
      label: "Factory / Showroom account",
      icon: Truck,
      allow: !isLegacy && !employee,
      element: <InternalTrade />,
    },
    {
      to: "/reports",
      label: "Workspace reports",
      icon: LayoutDashboard,
      allow: admin && !isLegacy,
      element: <WorkspaceReports />,
    },
    {
      to: "/legacy",
      label: "Unassigned history",
      icon: Layers,
      allow: admin,
      element: <LegacyHistory />,
    },
  ].filter((screen) => screen.allow);
  return (
    <SessionProvider user={user} workspace={workspace}>
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
            {screens.map(({ to, label, icon: Icon }) => (
              <NavLink to={to} end={to === "/"} key={to}>
                <Icon size={19} />
                {t(label)}
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
                screens.find((screen) => screen.to === location.pathname)
                  ?.label || (employee ? "Production" : "Overview"),
              )}
            </span>
            <div className="topbar-right">
              {admin && (
                <label className="workspace-picker">
                  <span>{t("Workspace")}</span>
                  <select
                    aria-label={t("Workspace")}
                    value={workspace}
                    onChange={(e) =>
                      enterWorkspace(e.target.value as Workspace)
                    }
                  >
                    {Object.entries(workspaceLabels).map(([unit, label]) => (
                      <option key={unit} value={unit}>
                        {t(label)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
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
          <main className="content" key={workspace}>
            <div className="workspace-banner">
              {t(workspaceLabels[workspace])}
            </div>
            <Routes>
              {screens.map(({ to, element }) => (
                <Route key={to} path={to} element={element} />
              ))}
              <Route path="*" element={<Navigate to={home} replace />} />
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
