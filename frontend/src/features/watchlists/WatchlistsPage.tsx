import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Field } from "../../components/Form";
import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import {
  useAddToWatchlist,
  useCreateWatchlist,
  useDeleteWatchlist,
  useRemoveFromWatchlist,
  useRenameWatchlist,
  useWatchlists,
  type WatchlistOut,
} from "./api";

function WatchlistCard({ watchlist }: { watchlist: WatchlistOut }) {
  const [ticker, setTicker] = useState("");
  const [name, setName] = useState(watchlist.name);
  const add = useAddToWatchlist();
  const remove = useRemoveFromWatchlist();
  const rename = useRenameWatchlist();
  const del = useDeleteWatchlist();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (ticker.trim()) add.mutate({ id: watchlist.id, ticker: ticker.trim() }, { onSuccess: () => setTicker("") });
  }

  return (
    <Panel
      title={watchlist.name}
      actions={
        <button
          type="button"
          onClick={() => del.mutate(watchlist.id)}
          className="text-xs text-rose-700 underline"
          aria-label={`Delete watchlist ${watchlist.name}`}
        >
          Delete
        </button>
      }
    >
      {watchlist.companies.length === 0 ? (
        <Unavailable>No companies yet.</Unavailable>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {watchlist.companies.map((c) => (
            <li key={`${c.market}:${c.ticker}`} className="flex items-center justify-between py-1">
              <Link to={`/companies/${encodeURIComponent(c.ticker)}`} className="text-sky-700 underline">
                {c.name} ({c.ticker})
              </Link>
              <button
                type="button"
                onClick={() => remove.mutate({ id: watchlist.id, ticker: c.ticker })}
                className="text-xs text-slate-600 underline"
                aria-label={`Remove ${c.ticker} from ${watchlist.name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Add by ticker or ISIN" value={ticker} onChange={setTicker} />
        <button type="submit" className="rounded border border-slate-300 px-2 py-1 text-sm">
          Add
        </button>
      </form>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && name.trim() !== watchlist.name) rename.mutate({ id: watchlist.id, name: name.trim() });
        }}
        className="flex flex-wrap items-end gap-2"
      >
        <Field label="Rename" value={name} onChange={setName} />
        <button type="submit" className="rounded border border-slate-300 px-2 py-1 text-sm">
          Rename
        </button>
      </form>
      {[add, remove, rename, del].map((m, i) => (m.isError ? <ErrorState key={i} error={m.error} /> : null))}
    </Panel>
  );
}

export function WatchlistsPage() {
  const watchlists = useWatchlists();
  const create = useCreateWatchlist();
  const [name, setName] = useState("");

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Watchlists</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate(name.trim(), { onSuccess: () => setName("") });
        }}
        className="flex flex-wrap items-end gap-2"
      >
        <Field label="New watchlist" value={name} onChange={setName} />
        <button type="submit" className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white">
          Create
        </button>
      </form>
      {create.isError ? <ErrorState error={create.error} /> : null}
      {watchlists.isPending ? (
        <Loading />
      ) : watchlists.isError ? (
        <ErrorState error={watchlists.error} />
      ) : watchlists.data.length === 0 ? (
        <Unavailable>You have no watchlists yet.</Unavailable>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {watchlists.data.map((w) => (
            <WatchlistCard key={w.id} watchlist={w} />
          ))}
        </div>
      )}
    </div>
  );
}
