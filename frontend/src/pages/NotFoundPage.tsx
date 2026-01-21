import { Link } from "react-router-dom";

import { UI_COPY } from "../lib/uiCopy";

export function NotFoundPage() {
  return (
    <div className="panel p-6">
      <div className="font-content text-2xl">页面不存在</div>
      <Link className="btn btn-secondary mt-4" to="/" aria-label="返回首页 (notfound_back_home)">
        {UI_COPY.nav.backToHome}
      </Link>
    </div>
  );
}
