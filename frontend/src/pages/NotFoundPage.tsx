import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="text-sky-700 underline">
        Back to home
      </Link>
    </div>
  );
}
