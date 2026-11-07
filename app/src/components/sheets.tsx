import { useState } from "react";
import { View } from "react-native";

import { BlockReason, Film } from "../api";
import { useAuth } from "../auth";
import { space } from "../theme";
import { Button, Chip, Field, IconName, Sheet, Stars, T } from "./ui";

export interface WatchedAnswers { rating: number; comment?: string; mood_match?: number; mindset?: string }

/** After "Watched": stars + comment; niche users also say how well it matched their mood and the right mindset. */
export function WatchedSheet({ film, onSave, onClose }: {
  film: Film | null; onSave: (a: WatchedAnswers) => void; onClose: () => void;
}) {
  const { me } = useAuth();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [moodMatch, setMoodMatch] = useState(0);
  const [mindset, setMindset] = useState("");
  const close = () => { setRating(0); setComment(""); setMoodMatch(0); setMindset(""); onClose(); };
  return (
    <Sheet visible={!!film} title={`How was ${film?.title}?`} onClose={close}>
      <T v="eyebrow">Your rating</T>
      <Stars value={rating} onChange={setRating} label="Your rating" />
      <Field placeholder="Anything you'd like to remember? (optional)" value={comment} onChangeText={setComment} multiline />
      {me?.niche_questions && (
        <>
          <T v="eyebrow" style={{ marginTop: space(1) }}>How well did it match your mood?</T>
          <Stars value={moodMatch} onChange={setMoodMatch} label="Mood match" />
          <T v="eyebrow" style={{ marginTop: space(1) }}>What mindset should someone be in to watch this?</T>
          <Field placeholder="e.g. a quiet evening, ready for something heavy" value={mindset} onChangeText={setMindset} />
        </>
      )}
      <Button kind="primary" icon="checkmark" label="Save" disabled={!rating} onPress={() => {
        onSave({ rating, comment: comment.trim() || undefined, mood_match: moodMatch || undefined,
          mindset: mindset.trim() || undefined });
        close();
      }} />
    </Sheet>
  );
}

const REASONS: { key: BlockReason; label: string; icon: IconName }[] = [
  { key: "watched", label: "Already watched it", icon: "eye-outline" },
  { key: "language", label: "Not this language", icon: "language-outline" },
  { key: "actor", label: "Not this actor", icon: "person-outline" },
  { key: "theme", label: "Not this kind of story", icon: "book-outline" },
  { key: "mainstream", label: "Too mainstream", icon: "trending-up-outline" },
  { key: "other", label: "Something else", icon: "ellipsis-horizontal" },
];

/** "Reject": the reason changes future picks (language and actor are avoided, theme feeds the disliked profile). */
export function RejectSheet({ film, onSave, onClose }: {
  film: Film | null; onSave: (reason: BlockReason, detail?: string) => void; onClose: () => void;
}) {
  const [reason, setReason] = useState<BlockReason | null>(null);
  const [actor, setActor] = useState<string | null>(null);
  const close = () => { setReason(null); setActor(null); onClose(); };
  const ready = reason && (reason !== "actor" || actor);
  return (
    <Sheet visible={!!film} title={`Why not ${film?.title}?`} onClose={close}>
      <T v="eyebrow">Your reason shapes what you see next</T>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space(1) }}>
        {REASONS.map((r) => (
          <Chip key={r.key} icon={r.icon} label={r.label} state={reason === r.key ? "on" : "off"} onPress={() => setReason(r.key)} />
        ))}
      </View>
      {reason === "actor" && (
        <>
          <T v="eyebrow">Which actor?</T>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space(1) }}>
            {(film?.cast ?? []).map((name) => (
              <Chip key={name} label={name} state={actor === name ? "on" : "off"} onPress={() => setActor(name)} />
            ))}
          </View>
        </>
      )}
      <T v="caption">
        {reason === "watched" ? "It moves to your Watched list." : "It won't be suggested again unless you unblock it."}
      </T>
      <Button kind="primary" icon="close" label="Reject" disabled={!ready} onPress={() => {
        onSave(reason!, reason === "actor" ? actor! : undefined);
        close();
      }} />
    </Sheet>
  );
}
