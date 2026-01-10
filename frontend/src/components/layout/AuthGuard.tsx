import { Navigate, Outlet, useLocation } from "react-router-dom";

import { UI_COPY } from "../../lib/uiCopy";
import { useAuth } from "../../contexts/auth";

export function AuthGuard() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "loading") {
    return (
      <div className="min-h-screen bg-canvas text-ink">
        <div className="mx-auto max-w-screen-sm px-4 py-16">
          <div className="text-sm text-subtext">{UI_COPY.common.loading}</div>
        </div>
      </div>
    );
  }

  if (auth.status === "unauthenticated") {
    const next = `${location.pathname}${location.search}`;
    const nextParam = encodeURIComponent(next);
    return <Navigate to={`/login?next=${nextParam}`} replace />;
  }

  return <Outlet />;
}
