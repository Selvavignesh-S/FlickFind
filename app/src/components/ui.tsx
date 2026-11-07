import Ionicons from "@expo/vector-icons/Ionicons";
import { ComponentProps, ReactNode } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, TextInputProps, TextProps, View, ViewStyle } from "react-native";

import { colors, fonts, glass, radius, shadow, space, type } from "../theme";

export type IconName = ComponentProps<typeof Ionicons>["name"];

/** Text in one of the type scale's styles (theme.type). */
export function T({ v = "body", style, ...props }: TextProps & { v?: keyof typeof type }) {
  return <Text {...props} style={[type[v], style]} />;
}

/** Actions: "primary" is the neutral light-gray fill (the only filled action), "ghost" a hairline button, "quiet" text only. */
export function Button({ label, onPress, kind = "ghost", disabled, small, icon, grow, iconOnly }: {
  label: string; onPress: () => void; kind?: "primary" | "ghost" | "quiet"; disabled?: boolean; small?: boolean;
  icon?: IconName; grow?: boolean; iconOnly?: boolean; // iconOnly: narrow spaces; the label stays for screen readers
}) {
  const fg = kind === "primary" ? colors.iron : kind === "quiet" ? colors.ash : colors.white;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed, hovered }: { pressed: boolean; hovered?: boolean }) => [
        s.button, small && s.small, grow && { flexGrow: 1, flexBasis: 0 },
        kind === "primary" && s.primary, kind === "ghost" && s.ghost, kind === "quiet" && s.quiet,
        hovered && !disabled && (kind === "primary" ? { backgroundColor: colors.white } : { backgroundColor: colors.well }),
        (pressed || disabled) && { opacity: disabled ? 0.4 : 0.75 }]}>
      {icon && <Ionicons name={icon} size={small ? 14 : 16} color={fg} />}
      {!(iconOnly && icon) && <Text style={[type.label, small && { fontSize: 12 }, { color: fg }]} numberOfLines={1}>{label}</Text>}
    </Pressable>
  );
}

/** A round icon-only button. */
export function IconButton({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} hitSlop={8}
      style={({ pressed }) => [s.iconButton, pressed && { opacity: 0.7 }]}>
      <Ionicons name={icon} size={18} color={colors.mist} />
    </Pressable>
  );
}

/** A pill to pick: "on" is filled light gray, "avoid" sits on the warm tint, struck through. */
export function Chip({ label, state = "off", onPress, icon }: {
  label: string; state?: "off" | "on" | "avoid"; onPress?: () => void; icon?: IconName;
}) {
  const fg = state === "on" ? colors.iron : state === "avoid" ? colors.ash : colors.mist;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={state === "avoid" ? `${label} (avoided)` : label}
      accessibilityState={{ selected: state !== "off" }} onPress={onPress}
      style={({ pressed, hovered }: { pressed: boolean; hovered?: boolean }) => [s.chip,
        state === "on" && { backgroundColor: colors.mist, borderColor: colors.mist },
        state === "avoid" && { backgroundColor: colors.ember, borderColor: colors.ember },
        hovered && state === "off" && { borderColor: colors.border, backgroundColor: "rgba(255,255,255,0.08)" },
        pressed && { opacity: 0.75 }]}>
      {icon && <Ionicons name={icon} size={13} color={fg} />}
      <Text style={[type.label, { color: fg }, state === "avoid" && { textDecorationLine: "line-through" }]}>{label}</Text>
    </Pressable>
  );
}

/** A small quiet tag for metadata: ratings, years, statuses. */
export function Badge({ label, icon, tone = "plain" }: { label: string; icon?: IconName; tone?: "plain" | "glass" }) {
  return (
    <View style={[s.badge, tone === "glass" && s.badgeGlass]}>
      {icon && <Ionicons name={icon} size={11} color={colors.mist} />}
      <Text style={s.badgeText}>{label}</Text>
    </View>
  );
}

/** The coral AI mark: the one functional use of the brand colour, on things the AI says. */
export const AIBadge = () => (
  <View style={s.ai}><Text style={[s.badgeText, { color: colors.white }]}>AI</Text></View>
);

/** FlickFind's mark: a coral key with a play glyph. */
export const Logo = ({ size = 22 }: { size?: number }) => (
  <View style={[s.logo, { width: size, height: size, borderRadius: size * 0.3 }]}>
    <Ionicons name="play" size={size * 0.5} color={colors.white} style={{ marginLeft: size * 0.06 }} />
  </View>
);

export function Stars({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
  return (
    <View style={{ flexDirection: "row", gap: space(1) }} accessibilityLabel={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable key={n} onPress={() => onChange(n)} accessibilityRole="button" accessibilityLabel={`${n} of 5`} hitSlop={6}>
          <Ionicons name={n <= value ? "star" : "star-outline"} size={28} color={n <= value ? colors.mist : colors.iron} />
        </Pressable>
      ))}
    </View>
  );
}

/** An inset field: a slightly lighter well you type into. */
export function Field(props: TextInputProps) {
  return <TextInput placeholderTextColor={colors.smoke} {...props} style={[s.field, props.style]} />;
}

/** A card: "key" is the pressed keycap surface, "edge" a hairline outline on the canvas. */
export function Card({ children, style, variant = "key" }: { children: ReactNode; style?: ViewStyle; variant?: "key" | "edge" }) {
  return <View style={[variant === "key" ? s.keyCard : s.edgeCard, style]}>{children}</View>;
}

/** Small mono uppercase label above a heading. */
export const Eyebrow = ({ children }: { children: ReactNode }) => <T v="eyebrow">{children}</T>;

export function Sheet({ visible, title, onClose, children }: {
  visible: boolean; title: string; onClose: () => void; children: ReactNode;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={[s.backdrop, glass]} onPress={onClose} accessibilityLabel="Close">
        <Pressable style={s.sheet} onPress={() => {}}>
          <ScrollView contentContainerStyle={{ gap: space(2) }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: space(1) }}>
              <T v="subheading" style={{ flex: 1 }}>{title}</T>
              <IconButton icon="close" label="Close" onPress={onClose} />
            </View>
            {children}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export const Muted = ({ children }: { children: ReactNode }) => <T v="small">{children}</T>;

const s = StyleSheet.create({
  button: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 10,
    paddingHorizontal: 14, borderRadius: radius.button },
  small: { paddingVertical: 7, paddingHorizontal: 10, gap: 5 },
  primary: { backgroundColor: colors.mist, boxShadow: shadow.lift },
  ghost: { borderWidth: 1, borderColor: colors.slate, backgroundColor: "transparent" },
  quiet: { backgroundColor: "transparent", paddingHorizontal: 6 },
  iconButton: { width: 32, height: 32, borderRadius: radius.pill, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.well },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8, paddingHorizontal: 14,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.slate, backgroundColor: colors.well },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 6, paddingVertical: 3,
    borderRadius: radius.badge, backgroundColor: colors.badge },
  badgeGlass: { backgroundColor: "rgba(4,5,6,0.72)", boxShadow: shadow.edge },
  badgeText: { fontFamily: fonts.monoMedium, fontSize: 10, lineHeight: 12, letterSpacing: 0.5, color: colors.mist,
    textTransform: "uppercase" },
  ai: { paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.badge, backgroundColor: colors.coral,
    alignSelf: "flex-start" },
  logo: { backgroundColor: colors.coral, alignItems: "center", justifyContent: "center", boxShadow: shadow.edge },
  field: { borderRadius: radius.input, paddingVertical: 12, paddingHorizontal: 14, color: colors.white,
    backgroundColor: colors.well, fontFamily: fonts.regular, fontSize: 16, boxShadow: shadow.edge },
  keyCard: { backgroundColor: colors.card, borderRadius: radius.card, padding: space(3), boxShadow: shadow.key },
  edgeCard: { borderRadius: radius.card, padding: space(3), borderWidth: 1, borderColor: colors.border },
  backdrop: { flex: 1, backgroundColor: "rgba(4,5,6,0.72)", justifyContent: "center", padding: space(2) },
  sheet: { backgroundColor: colors.card, borderRadius: radius.large, padding: space(3), maxWidth: 480, width: "100%",
    alignSelf: "center", maxHeight: "90%", boxShadow: shadow.window },
});
