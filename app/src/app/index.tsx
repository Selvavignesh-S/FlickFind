import { useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, ScrollViewInstance, StyleSheet, Text, View } from "react-native";

import { api, Film } from "../api";
import { useAuth } from "../auth";
import { FilmGrid, MAX_WIDTH } from "../components/FilmGrid";
import { Button, Chip, Field } from "../components/ui";
import { colors, space } from "../theme";

interface Turn {
  message: string; films: Film[]; busy: boolean; error?: string; done?: boolean;
  understood?: string[]; // the hard rules and reference films the request was read as, e.g. "Indian thrillers"
  notes?: string[]; // e.g. a director who isn't in the catalog
}
interface Answer { films: Film[]; understood: string[]; notes: string[] }

const EXAMPLES = ["I'm sad and want to laugh", "Something tense, not gory", "A cosy film for a rainy evening",
  "I want a good cry", "Mind-bending but not slow"];
const newSession = () => Math.random().toString(36).slice(2, 12);

export default function Discover() {
  const { me } = useAuth();
  const [session, setSession] = useState(newSession);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const scroll = useRef<ScrollViewInstance>(null);

  const update = (i: number, patch: Partial<Turn>) =>
    setTurns((ts) => ts.map((t, n) => (n === i ? { ...t, ...patch } : t)));

  // "Find more" sends the same message in the same session: the server never repeats a film within a session
  const fetchFilms = async (i: number, message: string) => {
    update(i, { busy: true, error: undefined });
    try {
      const { films, understood, notes } = await api<Answer>("/recommend", "POST", { message, session });
      setTurns((ts) => ts.map((t, n) => (n === i ? { ...t, busy: false, films: [...t.films, ...films],
        done: films.length === 0, understood, notes } : t)));
    } catch (e) {
      update(i, { busy: false, error: (e as Error).message });
    }
  };

  const send = (message: string) => {
    const m = message.trim();
    if (!m) return;
    setText("");
    const i = turns.length;
    setTurns((ts) => [...ts, { message: m, films: [], busy: true }]);
    fetchFilms(i, m);
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView ref={scroll} contentContainerStyle={s.page}
        onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}>
        {turns.length === 0 && (
          <View style={{ gap: space(2), paddingVertical: space(6) }}>
            <Text style={s.hello}>How are you feeling{me ? `, ${me.name}` : ""}?</Text>
            <Text style={{ color: colors.muted }}>Tell me your mood and what you want from tonight's film.</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {EXAMPLES.map((e) => <Chip key={e} label={e} onPress={() => send(e)} />)}
            </View>
          </View>
        )}
        {turns.length > 0 && (
          <View style={{ alignSelf: "flex-start" }}>
            <Button small label="New chat" onPress={() => { setTurns([]); setSession(newSession()); }} />
          </View>
        )}
        {turns.map((t, i) => (
          <View key={i} style={{ gap: space(1.5) }}>
            <Text style={s.you}>{t.message}</Text>
            {t.understood && t.understood.length > 0 && (
              <Text style={s.understood}>Searching: {t.understood.join(" · ")}</Text>
            )}
            {t.notes?.map((note) => <Text key={note} style={s.note}>{note}</Text>)}
            {t.films.length > 0 && (
              <FilmGrid films={t.films} onChange={(film) =>
                update(i, { films: t.films.map((f) => (f.tmdb_id === film.tmdb_id ? film : f)) })} />
            )}
            {t.busy && <Text style={{ color: colors.muted }}>Finding films…</Text>}
            {t.error && <Text style={{ color: colors.danger }}>{t.error}</Text>}
            {t.done && !(t.films.length === 0 && t.notes?.length) && (
              <Text style={{ color: colors.muted }}>
                {t.films.length ? "That's every film that fits this request." : "Nothing fits this request. Try describing it differently."}
              </Text>
            )}
            {!t.busy && !t.done && i === turns.length - 1 && t.films.length > 0 && (
              <View style={{ alignSelf: "flex-start" }}>
                <Button label="Find more" onPress={() => fetchFilms(i, t.message)} />
              </View>
            )}
          </View>
        ))}
      </ScrollView>
      <View style={s.inputBar}>
        <View style={s.inputRow}>
          <Field style={{ flex: 1 }} placeholder="What are you in the mood for?" value={text} onChangeText={setText}
            onSubmitEditing={() => send(text)} returnKeyType="send" accessibilityLabel="Your mood" />
          <Button kind="primary" label="Send" onPress={() => send(text)} disabled={!text.trim()} />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  page: { padding: space(2), gap: space(4), maxWidth: MAX_WIDTH, width: "100%", alignSelf: "center" },
  hello: { color: colors.text, fontSize: 28, fontWeight: "700" },
  understood: { color: colors.muted, fontSize: 13, alignSelf: "flex-end" },
  note: { color: colors.accent, fontSize: 14 },
  you: { color: colors.text, fontSize: 17, fontWeight: "600", alignSelf: "flex-end", backgroundColor: colors.glass,
    borderColor: colors.border, borderWidth: 1, borderRadius: 12, paddingVertical: 8, paddingHorizontal: 12, maxWidth: "85%" },
  inputBar: { borderTopWidth: 1, borderTopColor: colors.border, padding: space(1.5) },
  inputRow: { flexDirection: "row", gap: space(1), maxWidth: MAX_WIDTH, width: "100%", alignSelf: "center" },
});
