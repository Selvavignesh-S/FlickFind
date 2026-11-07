import Ionicons from "@expo/vector-icons/Ionicons";
import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, View } from "react-native";

import { api, Film, Status } from "../api";
import { colors, MAX_WIDTH, radius, space } from "../theme";
import { FilmGrid } from "./FilmGrid";
import { Card, IconName, T } from "./ui";

const COPY: Record<Status, { title: string; icon: IconName; empty: string }> = {
  watchlist: { title: "Watchlist", icon: "bookmark-outline",
    empty: "Films you tap \"Gonna watch\" on land here. They never change your recommendations." },
  watched: { title: "Watched", icon: "checkmark-done-outline",
    empty: "Films you've watched and rated. Your ratings shape what you're shown next." },
  blocked: { title: "Blocked", icon: "ban-outline", empty: "Nothing blocked. Rejected films stay here until you unblock them." },
};

export function LibraryScreen({ status }: { status: Status }) {
  const [films, setFilms] = useState<Film[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const copy = COPY[status];

  useFocusEffect(useCallback(() => {
    api<Film[]>(`/library?status=${status}`).then(setFilms, (e) => setError(e.message));
  }, [status]));

  return (
    <ScrollView contentContainerStyle={s.page}>
      <View style={{ gap: space(1) }}>
        <T v="eyebrow">Your library{films ? ` · ${films.length} film${films.length === 1 ? "" : "s"}` : ""}</T>
        <T v="heading">{copy.title}</T>
      </View>
      {error && <T v="caption" style={{ color: colors.white }}>{error}</T>}
      {!films && !error && <ActivityIndicator color={colors.mist} style={{ alignSelf: "flex-start" }} />}
      {films?.length === 0 && (
        <Card variant="edge" style={s.empty}>
          <View style={s.iconWell}><Ionicons name={copy.icon} size={24} color={colors.mist} /></View>
          <T v="small" style={{ flex: 1 }}>{copy.empty}</T>
        </Card>
      )}
      {films && films.length > 0 && (
        <FilmGrid films={films} onChange={(film, removed) =>
          // a film that moved to another list (e.g. watchlist -> watched) leaves this one
          setFilms(films.flatMap((f) => (f.tmdb_id !== film.tmdb_id ? [f]
            : removed || film.library?.status !== status ? [] : [film])))} />
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: space(2), paddingTop: space(4), gap: space(3), maxWidth: MAX_WIDTH, width: "100%", alignSelf: "center" },
  empty: { flexDirection: "row", alignItems: "center", gap: space(2), maxWidth: 640 },
  iconWell: { width: 56, height: 56, borderRadius: radius.pill, backgroundColor: colors.recessed, alignItems: "center",
    justifyContent: "center" },
});
