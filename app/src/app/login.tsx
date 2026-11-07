import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { useAuth } from "../auth";
import { Button, Field } from "../components/ui";
import { colors, space } from "../theme";

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
      <View style={s.box}>
        <Text style={s.logo}>FlickFind</Text>
        <Text style={{ color: colors.muted, marginBottom: space(1) }}>Films for the mood you're in.</Text>
        {mode === "up" && <Field placeholder="Your name" value={name} onChangeText={setName} autoComplete="name" />}
        <Field placeholder="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address"
          autoComplete="email" />
        <Field placeholder={mode === "up" ? "Password (8+ characters)" : "Password"} value={password}
          onChangeText={setPassword} secureTextEntry autoComplete={mode === "up" ? "new-password" : "current-password"}
          onSubmitEditing={submit} />
        {error && <Text style={{ color: colors.danger }} accessibilityLiveRegion="polite">{error}</Text>}
        <Button kind="primary" label={mode === "in" ? "Log in" : "Create account"} onPress={submit}
          disabled={busy || !email || !password || (mode === "up" && !name)} />
        <Pressable onPress={() => { setMode(mode === "in" ? "up" : "in"); setError(null); }} accessibilityRole="button">
          <Text style={{ color: colors.accent, textAlign: "center" }}>
            {mode === "in" ? "New here? Create an account" : "Have an account? Log in"}
          </Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, justifyContent: "center", padding: space(2) },
  box: { gap: space(1.5), maxWidth: 380, width: "100%", alignSelf: "center" },
  logo: { color: colors.accent, fontSize: 36, fontWeight: "800" },
});
