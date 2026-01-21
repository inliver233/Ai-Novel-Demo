import { Link } from "react-router-dom";

import { UI_COPY } from "../lib/uiCopy";

export function NotFoundPage() {
  return (
    <div className="panel p-6">
      <div className="font-content text-2xl">页面不存在</div>
      <Link className="ui-transition-fast mt-3 inline-block text-accent hover:underline" to="/">
        {UI_COPY.nav.backToHome}
      </Link>
    </div>
  );
}
