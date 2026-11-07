import { ScrollView, StyleSheet, View } from "react-native";

import { useAuth } from "../auth";
import { Badge, Button, Card, T } from "../components/ui";
import { colors, radius, shadow, space } from "../theme";

export default function Profile() {
  const { me, signOut } = useAuth();
  if (!me) return null;
  const pct = Math.round(me.niche * 100);
  return (
    <ScrollView contentContainerStyle={s.page}>
      <View style={{ gap: space(1) }}>
        <T v="eyebrow">Profile</T>
        <T v="heading">{me.name}</T>
        <T v="small">{me.email}</T>
      </View>
      <Card style={{ gap: space(2) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: space(1.5) }}>
          <T v="subheading" style={{ flex: 1 }}>Your taste</T>
          <Badge label={me.taste} />
        </View>
        <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: pct }}
          accessibilityLabel="Mainstream to niche" style={s.track}>
          <View style={[s.marker, { left: `${pct}%` }]} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <T v="eyebrow">Mainstream</T>
          <T v="eyebrow">Balanced</T>
          <T v="eyebrow">Niche</T>
        </View>
        <T v="small">
          Everyone starts in the middle, with no lean: films are picked on how well they fit your mood. Loving
          well-known films moves this toward mainstream; loving lesser-known ones, or rejecting films as too mainstream,
          moves it toward niche.
        </T>
      </Card>
      <View style={{ alignSelf: "flex-start" }}>
        <Button icon="log-out-outline" label="Log out" onPress={signOut} />
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  page: { padding: space(2), paddingTop: space(4), gap: space(3), maxWidth: 760, width: "100%", alignSelf: "center" },
  track: { height: 8, borderRadius: radius.pill, backgroundColor: colors.recessed, boxShadow: shadow.edge, marginVertical: space(1) },
  marker: { position: "absolute", top: -6, width: 20, height: 20, marginLeft: -10, borderRadius: radius.pill,
    backgroundColor: colors.mist, boxShadow: shadow.lift },
});
