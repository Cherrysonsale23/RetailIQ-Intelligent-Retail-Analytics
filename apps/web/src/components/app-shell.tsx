
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bot,
  ChevronDown,
  Database,
  LayoutDashboard,
  LogOut,
  Moon,
  Settings2,
  Sun,
  UploadCloud,
} from "lucide-react";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

const groups = [
  {
    label: "WORKSPACE",
    items: [
      { href: "/overview", label: "Overview", icon: LayoutDashboard },
      { href: "/datasets", label: "Datasets", icon: Database },
      { href: "/datasets/upload", label: "Upload data", icon: UploadCloud },
    ],
  },
  {
    label: "ANALYZE",
    items: [
      { href: "/analytics", label: "Analytics", icon: Activity },
      { href: "/agent", label: "AI analyst", icon: Bot },
    ],
  },
];

export function AppShell({
  children,
  email,
}: {
  children: React.ReactNode;
  email: string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [dark, setDark] = useState(false);
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signOut();

      if (error) throw error;

      router.replace("/sign-in");
      router.refresh();
    } catch (error) {
      alert(
        error instanceof Error
          ? error.message
          : "Unable to sign out. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={dark ? "app-frame dark-mode" : "app-frame"}>
      <aside className="sidebar">
        <Link href="/overview" className="brand side-brand">
          <span className="brand-mark">M</span>
          <span>
            Meridian<span className="brand-dot">.</span>
          </span>
        </Link>

        <div className="workspace-switch">
          <div className="workspace-avatar">
            {email.slice(0, 1).toUpperCase() || "W"}
          </div>
          <div className="workspace-label">
            <b>My workspace</b>
            <small>Personal plan</small>
          </div>
          <ChevronDown size={15} />
        </div>

        <nav className="side-nav">
          {groups.map((group) => (
            <section key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active =
                  pathname === item.href ||
                  (item.href !== "/overview" &&
                    pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={active ? "nav-item active" : "nav-item"}
                  >
                    <Icon size={17} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </section>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <Link
            className={
              pathname.startsWith("/settings")
                ? "nav-item active"
                : "nav-item"
            }
            href="/settings"
          >
            <Settings2 size={17} />
            Settings
          </Link>

          <button
            className="nav-item"
            onClick={() => setDark(!dark)}
          >
            {dark ? <Sun size={17} /> : <Moon size={17} />}
            <span>Appearance</span>
            <span className="nav-trailing">
              {dark ? "Dark" : "Light"}
            </span>
          </button>

          <div className="account-row">
            <div className="account-avatar">
              {email.slice(0, 1).toUpperCase() || "U"}
            </div>

            <div className="account-email">
              <b>{email.split("@")[0] || "Account"}</b>
              <small>{email}</small>
            </div>

            <button
              aria-label="Sign out"
              title="Sign out"
              className="icon-button"
              disabled={busy}
              onClick={signOut}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            <b>
              {pathname
                .split("/")
                .filter(Boolean)
                .at(-1)
                ?.replaceAll("-", " ") || "Overview"}
            </b>
          </div>

          <div className="topbar-right">
            <div className="top-avatar">
              {email.slice(0, 1).toUpperCase() || "U"}
            </div>
          </div>
        </header>

        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
