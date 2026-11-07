import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, Text } from "react-native";

import { api, Film, Status } from "../api";
import { colors, space } from "../theme";
import { FilmGrid, MAX_WIDTH } from "./FilmGrid";

const COPY: Record<Status, { title: string; empty: string }> = {
  watchlist: { title: "Watchlist", empty: "Films you tap \"Gonna watch\" on land here. They never change your recommendations." },
  watched: { title: "Watched", empty: "Films you've watched and rated. Your ratings shape what you're shown next." },
  blocked: { title: "Blocked", empty: "Nothing blocked. Rejected films stay here until you unblock them." },
};

export function LibraryScreen({ status }: { status: Status }) {
  const [films, setFilms] = useState<Film[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    api<Film[]>(`/library?status=${status}`).then(setFilms, (e) => setError(e.message));
  }, [status]));

  return (
    <ScrollView contentContainerStyle={{ padding: space(2), gap: space(2), maxWidth: MAX_WIDTH, width: "100%", alignSelf: "center" }}>
      <Text style={{ color: colors.text, fontSize: 24, fontWeight: "700" }}>{COPY[status].title}</Text>
      {error && <Text style={{ color: colors.danger }}>{error}</Text>}
      {films?.length === 0 && <Text style={{ color: colors.muted }}>{COPY[status].empty}</Text>}
      {films && films.length > 0 && (
        <FilmGrid films={films} onChange={(film, removed) =>
          // a film that moved to another list (e.g. watchlist -> watched) leaves this one
          setFilms(films.flatMap((f) => (f.tmdb_id !== film.tmdb_id ? [f]
            : removed || film.library?.status !== status ? [] : [film])))} />
      )}
    </ScrollView>
  );
}
