import { NavLink, Outlet } from "react-router";
import { cn } from "cn";

const navItems = [
  { to: "/servers", label: "Servers" },
  { to: "/runs", label: "Runs" },
];

export function Layout() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-8 px-6">
          <span className="font-semibold">Load Balancer Simulation</span>
          <nav className="flex gap-1" aria-label="Main">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted",
                    isActive ? "bg-muted text-foreground" : "text-muted-foreground",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
