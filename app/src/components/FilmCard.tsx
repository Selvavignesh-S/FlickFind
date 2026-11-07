import { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import { Film } from "../api";
import { colors, space } from "../theme";
import { Button } from "./ui";

export interface CardActions {
  onWatchlist: () => void;
  onWatched: () => void;
  onReject: () => void;
  onRemove: () => void;
}

const STATUS_LABEL = { watchlist: "On your watchlist", watched: "Watched", blocked: "Blocked" } as const;

function Ratings({ film }: { film: Film }) {
  const r = film.ratings;
  if (!r) return null;
  const parts = [
    r.imdb != null && `IMDb ${r.imdb.toFixed(1)}`,
    r.rotten_tomatoes != null && `RT ${r.rotten_tomatoes}%`,
    r.flickfind != null && `FlickFind ${r.flickfind.toFixed(1)}★`,
  ].filter(Boolean);
  return <Text style={s.meta}>{parts.join("  ·  ")}</Text>;
}

/** Poster card; tap (or hover on web) opens a glass panel with the synopsis and why it was picked. */
export function FilmCard({ film, width, actions }: { film: Film; width: number; actions: CardActions }) {
  const [open, setOpen] = useState(false);
  const status = film.library?.status;
  return (
    <View style={[s.card, { width }]}>
      <Pressable onPress={() => setOpen(!open)} onHoverIn={() => setOpen(true)} onHoverOut={() => setOpen(false)}
        accessibilityRole="button" accessibilityLabel={`${film.title}, ${open ? "hide" : "show"} details`}>
        <View style={{ width, aspectRatio: 2 / 3, backgroundColor: colors.glass, overflow: "hidden" }}>
          {film.poster ? <Image source={{ uri: film.poster }} style={StyleSheet.absoluteFill} accessibilityIgnoresInvertColors />
            : <Text style={[s.meta, { margin: space(1) }]}>{film.title}</Text>}
          {open && !film.missing && (
            <View style={s.panel}>
              {film.watch_when ? <Text style={s.why}>Watch this when {film.watch_when}</Text> : null}
              <Text style={s.overview} numberOfLines={9}>{film.overview}</Text>
              {film.director?.length ? <Text style={s.meta}>Dir. {film.director.join(", ")}</Text> : null}
              {film.cast?.length ? <Text style={s.meta} numberOfLines={2}>{film.cast.slice(0, 3).join(", ")}</Text> : null}
              {film.providers_in?.length ? <Text style={s.meta}>Stream: {film.providers_in.slice(0, 3).join(", ")}</Text> : null}
            </View>
          )}
        </View>
      </Pressable>
      <View style={s.body}>
        <Text style={s.title} numberOfLines={2}>{film.title}{film.year ? ` (${film.year})` : ""}</Text>
        <Ratings film={film} />
        {film.why ? <Text style={s.reason} numberOfLines={3}>{film.why}</Text> : null}
        {film.mood_tags?.length ? <Text style={s.tags} numberOfLines={1}>{film.mood_tags.slice(0, 3).join(" · ")}</Text> : null}
        {status && (
          <Text style={[s.meta, { color: status === "blocked" ? colors.danger : colors.good }]}>
            {STATUS_LABEL[status]}{film.library?.rating ? `  ${"★".repeat(film.library.rating)}` : ""}
          </Text>
        )}
        <View style={s.actions}>
          {!status && <Button small kind="primary" label="Gonna watch" onPress={actions.onWatchlist} />}
          {status !== "watched" && status !== "blocked" && <Button small label="Watched" onPress={actions.onWatched} />}
          {!status && <Button small kind="danger" label="Reject" onPress={actions.onReject} />}
          {status === "watched" && <Button small label="Re-rate" onPress={actions.onWatched} />}
          {status && <Button small label={status === "blocked" ? "Unblock" : "Remove"} onPress={actions.onRemove} />}
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  card: { borderRadius: 12, overflow: "hidden", backgroundColor: colors.glass, borderWidth: 1, borderColor: colors.border },
  panel: { ...StyleSheet.absoluteFill, backgroundColor: colors.glassStrong, padding: space(1.5), gap: space(1) },
  why: { color: colors.accent, fontSize: 13, fontStyle: "italic" },
  overview: { color: colors.text, fontSize: 13, lineHeight: 18 },
  body: { padding: space(1.5), gap: 4 },
  title: { color: colors.text, fontWeight: "700", fontSize: 15 },
  meta: { color: colors.muted, fontSize: 12 },
  tags: { color: colors.accent, fontSize: 12 },
  reason: { color: colors.text, fontSize: 13, fontStyle: "italic", lineHeight: 18 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: space(1) },
});
