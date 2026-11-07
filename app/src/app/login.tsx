import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, View } from "react-native";

import { useAuth } from "../auth";
import { Button, Field, Logo, T } from "../components/ui";
import { atmosphere, colors, radius, shadow, space } from "../theme";

export default function Login() {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await (mode === "in" ? signIn(email, password) : signUp(email, password, name));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.screen}>
      <View style={[StyleSheet.absoluteFill, atmosphere]} pointerEvents="none" />
      <View style={s.head}>
        <Logo size={44} />
        <T v="display" style={{ textAlign: "center", fontSize: 40, lineHeight: 46 }}>FlickFind</T>
        <T v="body" style={{ color: colors.ash, textAlign: "center" }}>Films for the mood you're in.</T>
      </View>
      <View style={s.box}>
        <T v="eyebrow">{mode === "in" ? "Welcome back" : "Create your account"}</T>
        {mode === "up" && <Field placeholder="Your name" value={name} onChangeText={setName} autoComplete="name" />}
        <Field placeholder="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address"
          autoComplete="email" />
        <Field placeholder={mode === "up" ? "Password (8+ characters)" : "Password"} value={password}
          onChangeText={setPassword} secureTextEntry autoComplete={mode === "up" ? "new-password" : "current-password"}
          onSubmitEditing={submit} />
        {error && <T v="caption" style={{ color: colors.white }} accessibilityLiveRegion="polite">{error}</T>}
        <Button kind="primary" icon="arrow-forward" label={mode === "in" ? "Log in" : "Create account"} onPress={submit}
          disabled={busy || !email || !password || (mode === "up" && !name)} />
        <Pressable onPress={() => { setMode(mode === "in" ? "up" : "in"); setError(null); }} accessibilityRole="button">
          <T v="caption" style={{ textAlign: "center" }}>
            {mode === "in" ? "New here? " : "Have an account? "}
            <T v="caption" style={{ color: colors.white }}>{mode === "in" ? "Create an account" : "Log in"}</T>
          </T>
        </Pressable>
      </View>
      <T v="mono" style={{ textAlign: "center" }}>NON-COMMERCIAL  |  TMDB · IMDb · OMDb · JUSTWATCH</T>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, justifyContent: "center", padding: space(2), gap: space(4), overflow: "hidden" },
  head: { alignItems: "center", gap: space(1.5) },
  box: { gap: space(1.5), maxWidth: 400, width: "100%", alignSelf: "center", padding: space(3), borderRadius: radius.large,
    backgroundColor: colors.card, boxShadow: shadow.key },
});
