import Ionicons from "@expo/vector-icons/Ionicons";
import { Link, usePathname } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";

import { useAuth } from "../auth";
import { colors, glass, MAX_WIDTH, radius, shadow, space, type } from "../theme";
import { Badge, Logo, T } from "./ui";

const LINKS = [
  { href: "/", label: "Discover" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/watched", label: "Watched" },
  { href: "/preferred", label: "Preferred" },
  { href: "/blocked", label: "Blocked" },
  { href: "/profile", label: "Profile" },
] as const;

/** A floating glass bar: the mark and the user's taste on the left, page links on the right
 *  (folded into a menu on narrow screens). */
export function Header() {
  const { me } = useAuth();
  const path = usePathname();
  const { width } = useWindowDimensions();
  const [menu, setMenu] = useState(false);
  const narrow = width < 760;
  const links = LINKS.map((l) => {
    const active = path === l.href;
    return (
      <Link key={l.href} href={l.href} onPress={() => setMenu(false)}
        style={[type.label, { color: active ? colors.white : colors.ash }, narrow && s.menuLink]}>{l.label}</Link>
    );
  });
  return (
    <View style={s.wrap}>
      <View style={[s.bar, glass]}>
        <Link href="/" asChild>
          <Pressable accessibilityRole="link" accessibilityLabel="FlickFind, discover" style={s.brand}>
            <Logo />
            <T v="label" style={{ fontSize: 14 }}>FlickFind</T>
          </Pressable>
        </Link>
        {me && <Badge label={me.taste} />}
        <View style={{ flex: 1 }} />
        {narrow
          ? <Pressable onPress={() => setMenu(!menu)} accessibilityRole="button" accessibilityLabel="Menu" hitSlop={8}>
              <Ionicons name={menu ? "close" : "menu"} size={22} color={colors.mist} />
            </Pressable>
          : <View style={s.links}>{links}</View>}
      </View>
      {narrow && menu && <View style={[s.menu, glass]}>{links}</View>}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { paddingHorizontal: space(2), paddingTop: space(1.5), maxWidth: MAX_WIDTH + space(4), width: "100%",
    alignSelf: "center", zIndex: 10 },
  bar: { flexDirection: "row", alignItems: "center", gap: space(1.5), paddingVertical: space(1), paddingHorizontal: space(2),
    borderRadius: radius.button + 4, borderWidth: 1, borderColor: colors.border, backgroundColor: "rgba(7,8,10,0.72)",
    boxShadow: shadow.edge },
  brand: { flexDirection: "row", alignItems: "center", gap: space(1) },
  links: { flexDirection: "row", alignItems: "center", gap: space(3) },
  menu: { marginTop: space(1), padding: space(1), borderRadius: radius.card, borderWidth: 1, borderColor: colors.border,
    backgroundColor: "rgba(7,8,10,0.92)" },
  menuLink: { paddingVertical: space(1.25), paddingHorizontal: space(1.5), fontSize: 15 },
});
