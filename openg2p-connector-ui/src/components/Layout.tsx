import { Link, Outlet, useLocation } from "react-router-dom";
import { Cable, LayoutDashboard, AlertTriangle, Activity } from "lucide-react";
import ApiConnectionBar from "./ApiConnectionBar";

const NAV = [
  { to: "/", label: "Pipelines", icon: Cable },
  { to: "/runs", label: "Runs", icon: Activity },
  { to: "/dlq", label: "Dead Letter Queue", icon: AlertTriangle },
];

export default function Layout() {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-[#d9d5c5] shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center h-14 gap-6">
          <Link to="/" className="flex items-center gap-2 font-semibold text-lg text-gray-900 shrink-0">
            <LayoutDashboard className="w-5 h-5 text-amber-700" />
            Connector Admin
          </Link>
          <nav className="flex gap-1 ml-4">
            {NAV.map(({ to, label, icon: Icon }) => {
              const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? "bg-amber-100 text-amber-900"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <ApiConnectionBar />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}
