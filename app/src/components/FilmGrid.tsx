import { useState } from "react";
import { View } from "react-native";

import { api, BlockReason, Film } from "../api";
import { useAuth } from "../auth";
import { colors, space } from "../theme";
import { T } from "./ui";
import { FilmCard } from "./FilmCard";
import { RejectSheet, WatchedAnswers, WatchedSheet } from "./sheets";

/** A responsive grid of film cards that runs the card actions against the API and reports the updated film. */
export function FilmGrid({ films, onChange }: { films: Film[]; onChange: (film: Film, removed?: boolean) => void }) {
  const [inner, setInner] = useState(0); // measured, so scrollbars and padding are already taken out
  const { refresh } = useAuth();
  const [watching, setWatching] = useState<Film | null>(null);
  const [rejecting, setRejecting] = useState<Film | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cols = inner < 520 ? 2 : inner < 860 ? 3 : inner < 1060 ? 4 : 5;
  // -1: layout widths are fractional, and an exact fit can still wrap the last card by a sub-pixel
  const cardWidth = Math.floor((inner - space(2) * (cols - 1)) / cols) - 1;

  const run = async (film: Film, call: Promise<Film | unknown>, removed = false) => {
    setError(null);
    try {
      const result = await call;
      onChange(removed ? { ...film, library: null } : (result as Film), removed);
      refresh().catch(() => {}); // ratings and blocks can move the Normal -> Niche score
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const save = (film: Film, body: object) => run(film, api<Film>(`/library/${film.tmdb_id}`, "PUT", body));

  return (
    <View style={{ gap: space(1) }} onLayout={(e) => setInner(e.nativeEvent.layout.width)}>
      {error && <T v="caption" style={{ color: colors.white }}>{error}</T>}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space(2) }}>
        {inner > 0 && films.map((f) => (
          <FilmCard key={f.tmdb_id} film={f} width={cardWidth} actions={{
            onWatchlist: () => save(f, { status: "watchlist" }),
            onWatched: () => setWatching(f),
            onReject: () => setRejecting(f),
            onRemove: () => run(f, api(`/library/${f.tmdb_id}`, "DELETE"), true),
          }} />
        ))}
      </View>
      <WatchedSheet film={watching} onClose={() => setWatching(null)}
        onSave={(a: WatchedAnswers) => watching && save(watching, { status: "watched", ...a })} />
      <RejectSheet film={rejecting} onClose={() => setRejecting(null)}
        onSave={(reason: BlockReason, detail?: string) =>
          rejecting && save(rejecting, { status: "blocked", block_reason: reason, block_detail: detail })} />
    </View>
  );
}
