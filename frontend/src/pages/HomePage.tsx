import { SystemStatus } from "../features/health/SystemStatus";

export function HomePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">FinSight</h1>
        <p className="text-slate-600">AI-powered financial intelligence platform.</p>
      </div>
      <SystemStatus />
    </div>
  );
}
