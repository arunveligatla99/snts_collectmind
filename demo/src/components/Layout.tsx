import { Outlet, NavLink } from "react-router-dom";
import { Header } from "./Header";
import { Footer } from "./Footer";
import { cn } from "@/lib/cn";

const NAV: Array<{ to: string; label: string; hint: string }> = [
  { to: "/", label: "Overview", hint: "Pitch + architecture" },
  { to: "/operator", label: "Operator", hint: "Submit finding → audit chain" },
  { to: "/audit", label: "Audit", hint: "FR-017a chain explorer" },
  { to: "/slo", label: "SLO", hint: "Measured + gated SLOs" },
  { to: "/tenants", label: "Tenants", hint: "Isolation + break-glass" },
  { to: "/docs", label: "Docs", hint: "Constitution + ADRs + reviews" },
];

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex">
        <aside className="hidden md:flex flex-col w-64 border-r border-zinc-800 bg-zinc-950/40">
          <nav className="p-3 space-y-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "block rounded-md px-3 py-2 text-sm transition",
                    isActive
                      ? "bg-accent-500/15 text-accent-200 border border-accent-500/30"
                      : "text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100",
                  )
                }
              >
                <div className="font-medium">{item.label}</div>
                <div className="text-[11px] text-zinc-500">{item.hint}</div>
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto p-3 border-t border-zinc-800 text-xs text-zinc-500 space-y-1">
            <div>Feature 002 shipped ✓</div>
            <div>Constitution v1.0.1</div>
            <div>OpenAPI v1.1.0</div>
          </div>
        </aside>
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  );
}
