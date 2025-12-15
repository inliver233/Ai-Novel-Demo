import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="rounded-atelier border border-border bg-surface p-6">
      <div className="font-content text-2xl">页面不存在</div>
      <Link className="mt-3 inline-block text-accent hover:underline" to="/">
        返回 Dashboard
      </Link>
    </div>
  );
}

