import { ScrollView, Text, View } from "react-native";

import { useAuth } from "../auth";
import { Button, Muted } from "../components/ui";
import { colors, space } from "../theme";

export default function Profile() {
  const { me, signOut } = useAuth();
  if (!me) return null;
  const pct = Math.round(me.niche * 100);
  return (
    <ScrollView contentContainerStyle={{ padding: space(2), gap: space(2), maxWidth: 720, width: "100%", alignSelf: "center" }}>
      <Text style={{ color: colors.text, fontSize: 24, fontWeight: "700" }}>{me.name}</Text>
      <Muted>{me.email}</Muted>
      <View style={{ gap: space(1), marginTop: space(2) }}>
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: "600" }}>Your taste: {me.taste}</Text>
        <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: pct }}
          accessibilityLabel="Mainstream to niche"
          style={{ height: 8, borderRadius: 4, backgroundColor: colors.glass, borderWidth: 1, borderColor: colors.border }}>
          <View style={{ width: `${pct}%`, height: "100%", borderRadius: 4, backgroundColor: colors.accent }} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Muted>Mainstream</Muted>
          <Muted>Niche</Muted>
        </View>
        <Muted>
          Everyone starts in the middle, with no lean: films are picked on how well they fit your mood. Loving
          well-known films moves this toward mainstream; loving lesser-known ones, or rejecting films as too mainstream,
          moves it toward niche.
        </Muted>
      </View>
      <View style={{ alignSelf: "flex-start", marginTop: space(2) }}>
        <Button kind="danger" label="Log out" onPress={signOut} />
      </View>
    </ScrollView>
  );
}
