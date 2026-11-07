import Ionicons from "@expo/vector-icons/Ionicons";
import { useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, ScrollViewInstance, StyleSheet,
  useWindowDimensions, View } from "react-native";

import { api, Film } from "../api";
import { useAuth } from "../auth";
import { FilmGrid } from "../components/FilmGrid";
import { AIBadge, Button, Card, Chip, Field, IconName, T } from "../components/ui";
import { atmosphere, colors, glass, MAX_WIDTH, radius, shadow, space } from "../theme";

interface Turn {
  message: string; films: Film[]; busy: boolean; error?: string; done?: boolean;
  understood?: string[]; // the hard rules and reference films the request was read as, e.g. "Indian thrillers"
  notes?: string[]; // e.g. a director who isn't in the catalog
  question?: string | null; options?: string[]; // a clarifying question, when the request was too vague
  noQuestions?: boolean; // "Just show me something": search with the best guess, ask nothing
  beyond?: "busy" | "done"; // the search past the catalog (TMDB + the web), run on request
}
interface Answer {
  films: Film[]; understood: string[]; notes: string[]; more: boolean; question: string | null; options: string[];
}
const JUST_SHOW = "Just show me something";

const EXAMPLES: { label: string; icon: IconName }[] = [
  { label: "I'm sad and want to laugh", icon: "happy-outline" },
  { label: "Something tense, not gory", icon: "pulse-outline" },
  { label: "A cosy film for a rainy evening", icon: "rainy-outline" },
  { label: "I want a good cry", icon: "water-outline" },
  { label: "Mind-bending but not slow", icon: "planet-outline" },
  { label: "Films like Spirited Away", icon: "sparkles-outline" },
];
const newSession = () => Math.random().toString(36).slice(2, 12);

export default function Discover() {
  const { me } = useAuth();
  const { width } = useWindowDimensions();
  const [session, setSession] = useState(newSession);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const scroll = useRef<ScrollViewInstance>(null);
  const compact = width < 640;

  const update = (i: number, patch: Partial<Turn>) =>
    setTurns((ts) => ts.map((t, n) => (n === i ? { ...t, ...patch } : t)));

  // "Find more" sends the same message in the same session: the server never repeats a film within a session
  const fetchFilms = async (i: number, message: string, noQuestions = false) => {
    update(i, { busy: true, error: undefined, question: null, noQuestions });
    try {
      const a = await api<Answer>("/recommend", "POST", { message, session, clarify: !noQuestions });
      setTurns((ts) => ts.map((t, n) => (n === i ? { ...t, busy: false, films: [...t.films, ...a.films],
        done: !a.question && !a.more, understood: a.understood, notes: a.notes, question: a.question,
        options: a.options } : t)));
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

  // past the catalog: TMDB and a web search, only when the user asks (it takes ~10 s and uses a web search credit)
  const searchBeyond = async (i: number, message: string) => {
    update(i, { beyond: "busy", error: undefined });
    try {
      const a = await api<Answer>("/beyond", "POST", { message, session });
      setTurns((ts) => ts.map((t, n) => (n === i ? { ...t, beyond: "done", films: [...t.films, ...a.films],
        notes: [...(t.notes ?? []), ...a.notes] } : t)));
    } catch (e) {
      update(i, { beyond: undefined, error: (e as Error).message });
    }
  };

  // an answer to a clarifying question becomes a fuller request: "I'm sad. A good cry"
  const answer = (t: Turn, i: number, option: string) =>
    option === JUST_SHOW ? fetchFilms(i, t.message, true) : send(`${t.message}. ${option}`);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView ref={scroll} contentContainerStyle={{ flexGrow: 1 }}
        onContentSizeChange={() => { if (turns.length) scroll.current?.scrollToEnd({ animated: true }); }}>
        {turns.length === 0 ? (
          <View style={s.hero}>
            <View style={[StyleSheet.absoluteFill, atmosphere]} pointerEvents="none" />
            <View style={s.heroInner}>
              <T v="eyebrow" style={{ textAlign: "center" }}>Mood-first film discovery</T>
              <T v="display" style={[{ textAlign: "center" }, compact && { fontSize: 34, lineHeight: 40 }]}>
                How are you feeling{me ? `, ${me.name}` : ""}?
              </T>
              <T v="body" style={{ color: colors.ash, textAlign: "center", maxWidth: 480 }}>
                Tell me your mood and what you want from tonight's film. I'll find the ones that fit, and say why.
              </T>
              <View style={s.examples}>
                {EXAMPLES.map((e) => <Chip key={e.label} icon={e.icon} label={e.label} onPress={() => send(e.label)} />)}
              </View>
              <T v="mono" style={{ textAlign: "center" }}>143K FILMS  |  TMDB · IMDb · OMDb · JUSTWATCH</T>
            </View>
          </View>
        ) : (
          <View style={s.page}>
            <View style={{ alignSelf: "flex-start" }}>
              <Button small kind="quiet" icon="add" label="New chat"
                onPress={() => { setTurns([]); setSession(newSession()); }} />
            </View>
            {turns.map((t, i) => (
              <View key={i} style={{ gap: space(2) }}>
                <View style={s.you}><T v="body">{t.message}</T></View>
                {t.understood && t.understood.length > 0 && (
                  <T v="eyebrow" style={{ alignSelf: "flex-end" }}>Searching · {t.understood.join(" · ")}</T>
                )}
                {t.notes?.map((note) => (
                  <View key={note} style={s.note}>
                    <Ionicons name="information-circle-outline" size={16} color={colors.mist} />
                    <T v="caption" style={{ color: colors.white, flexShrink: 1 }}>{note}</T>
                  </View>
                ))}
                {t.question && (
                  <Card style={{ gap: space(2), maxWidth: 640 }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: space(1) }}>
                      <AIBadge /><T v="eyebrow">A quick question</T>
                    </View>
                    <T v="subheading">{t.question}</T>
                    <View style={[s.examples, { justifyContent: "flex-start" }]}>
                      {[...(t.options ?? []), JUST_SHOW].map((o) => (
                        <Chip key={o} label={o} icon={o === JUST_SHOW ? "shuffle" : undefined}
                          onPress={() => answer(t, i, o)} />
                      ))}
                    </View>
                  </Card>
                )}
                {t.films.length > 0 && (
                  <FilmGrid films={t.films} onChange={(film) =>
                    update(i, { films: t.films.map((f) => (f.tmdb_id === film.tmdb_id ? film : f)) })} />
                )}
                {(t.busy || t.beyond === "busy") && (
                  <View style={s.busy}>
                    <ActivityIndicator size="small" color={colors.mist} />
                    <T v="eyebrow">{t.beyond === "busy" ? "Searching TMDB and the web · checking every film"
                      : "Reading your mood · checking every film"}</T>
                  </View>
                )}
                {t.error && <View style={s.note}><T v="caption" style={{ color: colors.white }}>{t.error}</T></View>}
                {t.done && !t.question && !t.beyond && !(t.films.length === 0 && t.notes?.length) && (
                  <T v="caption">
                    {t.films.length ? "That's every film in the catalog that fits this request."
                      : "Nothing in the catalog fits this request."}
                  </T>
                )}
                {t.done && !t.busy && !t.question && !t.beyond && (
                  <View style={{ alignSelf: "flex-start" }}>
                    <Button icon="globe-outline" label="Search beyond the catalog" onPress={() => searchBeyond(i, t.message)} />
                  </View>
                )}
                {!t.busy && !t.done && !t.question && i === turns.length - 1 && (
                  <View style={{ alignSelf: "flex-start" }}>
                    <Button icon="refresh" label="Find more" onPress={() => fetchFilms(i, t.message, t.noQuestions)} />
                  </View>
                )}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
      <View style={s.inputWrap}>
        <View style={[s.inputBar, glass]}>
          <Ionicons name="sparkles-outline" size={18} color={colors.smoke} style={{ marginLeft: space(1) }} />
          <Field style={s.input} placeholder="What are you in the mood for?" value={text} onChangeText={setText}
            onSubmitEditing={() => send(text)} returnKeyType="send" accessibilityLabel="Your mood" />
          <Button kind="primary" icon="arrow-up" label="Send" onPress={() => send(text)} disabled={!text.trim()}
            iconOnly={compact} />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  hero: { flexGrow: 1, justifyContent: "center", paddingVertical: space(8), paddingHorizontal: space(2), overflow: "hidden" },
  heroInner: { gap: space(3), alignItems: "center", maxWidth: 760, width: "100%", alignSelf: "center" },
  examples: { flexDirection: "row", flexWrap: "wrap", gap: space(1), justifyContent: "center" },
  page: { padding: space(2), paddingTop: space(3), gap: space(5), maxWidth: MAX_WIDTH, width: "100%", alignSelf: "center" },
  you: { alignSelf: "flex-end", backgroundColor: colors.recessed, borderRadius: radius.card, paddingVertical: space(1.25),
    paddingHorizontal: space(2), maxWidth: "85%", boxShadow: shadow.edge },
  note: { flexDirection: "row", alignItems: "center", gap: space(1), backgroundColor: colors.ember,
    borderRadius: radius.button, paddingVertical: space(1), paddingHorizontal: space(1.5), alignSelf: "flex-start" },
  busy: { flexDirection: "row", alignItems: "center", gap: space(1.5) },
  inputWrap: { paddingHorizontal: space(2), paddingBottom: space(2), paddingTop: space(1) },
  inputBar: { flexDirection: "row", alignItems: "center", gap: space(1), padding: space(1), borderRadius: radius.card,
    borderWidth: 1, borderColor: colors.border, backgroundColor: "rgba(7,8,10,0.8)", maxWidth: 840, width: "100%",
    alignSelf: "center", boxShadow: shadow.edge },
  input: { flex: 1, minWidth: 0, backgroundColor: "transparent", boxShadow: "none", paddingHorizontal: space(0.5) },
});
