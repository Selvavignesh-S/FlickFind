import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { api, Me } from "../api";
import { useAuth } from "../auth";
import { Button, Card, Chip, Field, T } from "../components/ui";
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
    <ScrollView contentContainerStyle={s.page}>
      <View style={{ gap: space(1) }}>
        <T v="eyebrow">Preferences</T>
        <T v="heading">Preferred</T>
        <T v="small">These shape every recommendation, alongside what you watch and rate.</T>
      </View>
      <Card style={{ gap: space(2) }}>
        <T v="subheading">Genres</T>
        <T v="eyebrow" style={{ color: colors.smoke }}>Tap once to favour · twice to avoid · again to clear</T>
        <View style={s.chips}>
          {genres.map((g) => (
            <Chip key={g} label={g} state={picks[g] ?? "off"} icon={picks[g] === "on" ? "heart" : undefined}
              onPress={() => setPicks({ ...picks, [g]: NEXT[picks[g] ?? "off"] })} />
          ))}
        </View>
      </Card>
      <Card style={{ gap: space(2) }}>
        <T v="subheading">About me</T>
        <T v="small">Anything that helps: films you love, who you watch with, what you can't stand.</T>
        <Field value={about} onChangeText={setAbout} multiline maxLength={2000}
          style={{ minHeight: 140, textAlignVertical: "top" }}
          placeholder="e.g. I love slow Japanese dramas and anything by Wong Kar-wai. No horror please." />
        <T v="mono" style={{ alignSelf: "flex-end" }}>{about.length} / 2000</T>
      </Card>
      <View style={{ flexDirection: "row", gap: space(2), alignItems: "center" }}>
        <Button kind="primary" icon="checkmark" label="Save preferences" onPress={save} />
        {status && <T v="eyebrow" style={{ color: status === "Saved" ? colors.mist : colors.white }}>{status}</T>}
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: space(2), paddingTop: space(4), gap: space(3), maxWidth: 760, width: "100%", alignSelf: "center" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space(1) },
});
