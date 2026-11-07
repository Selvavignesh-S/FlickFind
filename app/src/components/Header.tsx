import { Link, usePathname } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from "react-native";

import { useAuth } from "../auth";
import { colors, space } from "../theme";
import { MAX_WIDTH } from "./FilmGrid";

const LINKS = [
  { href: "/watchlist", label: "Watchlist" },
  { href: "/watched", label: "Watched" },
  { href: "/preferred", label: "Preferred" },
  { href: "/blocked", label: "Blocked" },
  { href: "/profile", label: "Profile" },
] as const;

/** Logo, the user's Normal/Niche label and the page links; the links fold into a menu on narrow screens. */
export function Header() {
  const { me } = useAuth();
  const path = usePathname();
  const { width } = useWindowDimensions();
  const [menu, setMenu] = useState(false);
  const narrow = width < 720;
  const links = LINKS.map((l) => (
    <Link key={l.href} href={l.href} onPress={() => setMenu(false)}
      style={[s.link, path === l.href && { color: colors.accent }]}>{l.label}</Link>
  ));
  return (
    <View style={s.wrap}>
      <View style={s.bar}>
        <Link href="/" style={s.logo} accessibilityLabel="FlickFind, discover">FlickFind</Link>
        {me && <Text style={s.badge}>{me.taste}</Text>}
        <View style={{ flex: 1 }} />
        {narrow
          ? <Pressable onPress={() => setMenu(!menu)} accessibilityRole="button" accessibilityLabel="Menu" hitSlop={8}>
              <Text style={s.link}>{menu ? "Close" : "Menu"}</Text>
            </Pressable>
          : <View style={{ flexDirection: "row", gap: space(2.5) }}>{links}</View>}
      </View>
      {narrow && menu && <View style={s.menu}>{links}</View>}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { borderBottomWidth: 1, borderBottomColor: colors.border },
  bar: { flexDirection: "row", alignItems: "center", gap: space(1.5), paddingHorizontal: space(2), paddingVertical: space(1.5),
    maxWidth: MAX_WIDTH, width: "100%", alignSelf: "center" },
  logo: { color: colors.accent, fontSize: 20, fontWeight: "800", letterSpacing: 0.5 },
  badge: { color: colors.text, fontSize: 12, borderWidth: 1, borderColor: colors.border, borderRadius: 10,
    paddingHorizontal: 8, paddingVertical: 2 },
  link: { color: colors.text, fontSize: 15, fontWeight: "500" },
  menu: { paddingHorizontal: space(2), paddingBottom: space(2), gap: space(1.5) },
});
