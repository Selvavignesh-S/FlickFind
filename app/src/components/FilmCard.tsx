import { useState } from "react";
import { Image, Pressable, StyleSheet, View } from "react-native";

import { Film } from "../api";
import { colors, glass, gradient, radius, shadow, space } from "../theme";
import { Badge, Button, T } from "./ui";

export interface CardActions {
  onWatchlist: () => void;
  onWatched: () => void;
  onReject: () => void;
  onRemove: () => void;
}

const fade = gradient("linear-gradient(180deg, rgba(7,8,10,0) 45%, rgba(7,8,10,0.55) 72%, rgba(7,8,10,0.96) 100%)");
const runtime = (m?: number) => (m ? `${Math.floor(m / 60)}h ${m % 60}m` : null);

function ratingBadges(film: Film) {
  const r = film.ratings;
  if (!r) return [];
  return [
    r.imdb != null && `IMDb ${r.imdb.toFixed(1)}`,
    r.rotten_tomatoes != null && `RT ${r.rotten_tomatoes}%`,
    r.flickfind != null && `FF ${r.flickfind.toFixed(1)}`,
  ].filter(Boolean) as string[];
}

/** A film as a keycap: the poster inset at the top, facts and the AI's reason below, actions at the foot.
 *  Tap (or hover on the web) lays a glass panel over the poster with the synopsis, people and where to stream. */
export function FilmCard({ film, width, actions }: { film: Film; width: number; actions: CardActions }) {
  const [open, setOpen] = useState(false);
  const status = film.library?.status;
  const meta = [film.year, runtime(film.runtime), film.language?.toUpperCase()].filter(Boolean).join(" · ");
  const tags = film.mood_tags?.slice(0, 3).join(" · ");
  const badges = ratingBadges(film);
  const narrow = width < 220; // two-up on a phone: secondary actions become icon-only
  return (
    <View style={[s.card, { width }]}>
      <Pressable onPress={() => setOpen(!open)} onHoverIn={() => setOpen(true)} onHoverOut={() => setOpen(false)}
        accessibilityRole="button" accessibilityLabel={`${film.title}, ${open ? "hide" : "show"} details`}
        style={s.poster}>
        {film.poster
          ? <Image source={{ uri: film.poster }} style={StyleSheet.absoluteFill} accessibilityIgnoresInvertColors />
          : <View style={s.noPoster}><T v="title" style={{ textAlign: "center" }}>{film.title}</T></View>}
        <View style={[StyleSheet.absoluteFill, fade]} pointerEvents="none" />
        <View style={s.topRow} pointerEvents="none">
          {film.fit != null ? <Badge tone="glass" icon="sparkles" label={`${film.fit}/10 fit`} /> : <View />}
          {status ? <Badge tone="glass" icon={status === "watchlist" ? "bookmark" : status === "watched" ? "checkmark"
            : "ban"} label={status === "watched" && film.library?.rating ? `${film.library.rating}★` : status} />
            : film.beyond ? <Badge tone="glass" icon="globe-outline" label="New" /> : null}
        </View>
        {!!meta && <T v="mono" style={s.meta} pointerEvents="none">{meta}</T>}
        {open && !film.missing && (
          <View style={[s.panel, glass]}>
            {film.watch_when ? <T v="eyebrow" style={{ color: colors.mist }}>Watch this when</T> : null}
            {film.watch_when ? <T v="caption" style={{ color: colors.white }}>{film.watch_when}</T> : null}
            <T v="caption" numberOfLines={8} style={{ marginTop: space(0.5) }}>{film.overview}</T>
            <View style={{ flex: 1 }} />
            {film.director?.length ? <T v="mono">DIR · {film.director.join(", ")}</T> : null}
            {film.cast?.length ? <T v="mono" numberOfLines={2}>CAST · {film.cast.slice(0, 3).join(", ")}</T> : null}
            {film.providers_in?.length
              ? <T v="mono" style={{ color: colors.mist }}>STREAM · {film.providers_in.slice(0, 3).join(", ")}</T> : null}
          </View>
        )}
      </Pressable>

      <View style={s.body}>
        <T v="title" numberOfLines={2}>{film.title}</T>
        {badges.length > 0 && <View style={s.badges}>{badges.map((b) => <Badge key={b} label={b} />)}</View>}
        {film.why ? <T v="caption" numberOfLines={3}>{film.why}</T> : null}
        {!!tags && <T v="eyebrow" numberOfLines={1} style={{ color: colors.smoke, fontSize: 10 }}>{tags}</T>}
        <View style={{ flex: 1 }} />
        <View style={s.actions}>
          {!status && <Button small kind="primary" icon="bookmark-outline" label="Gonna watch" onPress={actions.onWatchlist} />}
          <View style={s.row}>
            {status !== "watched" && status !== "blocked" &&
              <Button small icon="checkmark" label="Watched" onPress={actions.onWatched} grow iconOnly={narrow && !status} />}
            {!status && <Button small icon="close" label="Reject" onPress={actions.onReject} grow iconOnly={narrow} />}
            {status === "watched" && <Button small icon="star-outline" label="Re-rate" onPress={actions.onWatched} grow />}
            {status && <Button small kind="quiet" icon={status === "blocked" ? "refresh" : "trash-outline"}
              label={status === "blocked" ? "Unblock" : "Remove"} onPress={actions.onRemove} grow />}
          </View>
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.card, padding: space(1), boxShadow: shadow.key, gap: space(1.5) },
  poster: { aspectRatio: 2 / 3, borderRadius: radius.poster, overflow: "hidden", backgroundColor: colors.recessed },
  noPoster: { flex: 1, alignItems: "center", justifyContent: "center", padding: space(2) },
  topRow: { position: "absolute", top: space(1), left: space(1), right: space(1), flexDirection: "row",
    justifyContent: "space-between", alignItems: "flex-start" },
  meta: { position: "absolute", left: space(1.5), bottom: space(1.25), color: colors.mist },
  panel: { ...StyleSheet.absoluteFill, backgroundColor: "rgba(7,8,10,0.86)", padding: space(1.5), gap: space(0.75) },
  body: { flex: 1, paddingHorizontal: space(0.75), paddingBottom: space(0.5), gap: space(1) },
  badges: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  actions: { gap: space(0.75), marginTop: space(0.5) },
  row: { flexDirection: "row", gap: space(0.75) },
});
