import { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";

import { api, Me } from "../api";
import { useAuth } from "../auth";
import { MAX_WIDTH } from "../components/FilmGrid";
import { Button, Chip, Field, Muted } from "../components/ui";
import { colors, space } from "../theme";

type Pick = "off" | "on" | "avoid";
const NEXT: Record<Pick, Pick> = { off: "on", on: "avoid", avoid: "off" };

export default function Preferred() {
  const { me, setMe } = useAuth();
  const [genres, setGenres] = useState<string[]>([]);
  const [picks, setPicks] = useState<Record<string, Pick>>({});
  const [about, setAbout] = useState(me?.about ?? "");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api<string[]>("/genres").then(setGenres, (e) => setStatus(e.message));
    if (me) {
      setPicks(Object.fromEntries([...me.genres_like.map((g) => [g, "on"]), ...me.genres_avoid.map((g) => [g, "avoid"])]));
    }
  }, [me]);

  const save = async () => {
    setStatus(null);
    try {
      const pick = (p: Pick) => Object.keys(picks).filter((g) => picks[g] === p);
      setMe(await api<Me>("/me/preferences", "PUT", { about, genres_like: pick("on"), genres_avoid: pick("avoid") }));
      setStatus("Saved");
    } catch (e) {
      setStatus((e as Error).message);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: space(2), gap: space(2), maxWidth: 720, width: "100%", alignSelf: "center" }}>
      <Text style={{ color: colors.text, fontSize: 24, fontWeight: "700" }}>Preferred</Text>
      <Muted>Tap a genre once to favour it, twice to avoid it, a third time to clear it.</Muted>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, maxWidth: MAX_WIDTH }}>
        {genres.map((g) => (
          <Chip key={g} label={g} state={picks[g] ?? "off"}
            onPress={() => setPicks({ ...picks, [g]: NEXT[picks[g] ?? "off"] })} />
        ))}
      </View>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "600", marginTop: space(1) }}>About me</Text>
      <Muted>Anything that helps: films you love, what you watch with, what you can't stand.</Muted>
      <Field value={about} onChangeText={setAbout} multiline maxLength={2000} style={{ minHeight: 120, textAlignVertical: "top" }}
        placeholder="e.g. I love slow Japanese dramas and anything by Wong Kar-wai. No horror please." />
      <View style={{ flexDirection: "row", gap: space(2), alignItems: "center" }}>
        <Button kind="primary" label="Save" onPress={save} />
        {status && <Text style={{ color: status === "Saved" ? colors.good : colors.danger }}>{status}</Text>}
      </View>
    </ScrollView>
  );
}
