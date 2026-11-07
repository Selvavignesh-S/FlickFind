import { ReactNode } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, TextInputProps, View } from "react-native";

import { colors, space } from "../theme";

export function Button({ label, onPress, kind = "plain", disabled, small }: {
  label: string; onPress: () => void; kind?: "primary" | "plain" | "danger"; disabled?: boolean; small?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [s.button, small && s.small, kind === "primary" && s.primary, kind === "danger" && s.danger,
        (pressed || disabled) && { opacity: 0.6 }]}>
      <Text style={[s.buttonText, small && { fontSize: 12 }, kind === "primary" && { color: colors.bg }]}>{label}</Text>
    </Pressable>
  );
}

export function Chip({ label, state = "off", onPress }: { label: string; state?: "off" | "on" | "avoid"; onPress?: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={state === "avoid" ? `${label} (avoided)` : label}
      accessibilityState={{ selected: state !== "off" }} onPress={onPress}
      style={[s.chip, state === "on" && { borderColor: colors.accent, backgroundColor: "rgba(232,176,75,0.15)" },
        state === "avoid" && { borderColor: colors.danger, backgroundColor: "rgba(229,103,107,0.15)" }]}>
      <Text style={[s.chipText, state === "avoid" && { textDecorationLine: "line-through" }]}>{label}</Text>
    </Pressable>
  );
}

export function Stars({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
  return (
    <View style={{ flexDirection: "row", gap: space(0.5) }} accessibilityLabel={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable key={n} onPress={() => onChange(n)} accessibilityRole="button" accessibilityLabel={`${n} of 5`}
          hitSlop={6}>
          <Text style={{ fontSize: 28, color: n <= value ? colors.accent : colors.border }}>★</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function Field(props: TextInputProps) {
  return <TextInput placeholderTextColor={colors.muted} {...props} style={[s.field, props.style]} />;
}

export function Sheet({ visible, title, onClose, children }: {
  visible: boolean; title: string; onClose: () => void; children: ReactNode;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.backdrop} onPress={onClose} accessibilityLabel="Close">
        <Pressable style={s.sheet} onPress={() => {}}>
          <ScrollView contentContainerStyle={{ gap: space(2) }}>
            <Text style={s.sheetTitle}>{title}</Text>
            {children}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export const Muted = ({ children }: { children: ReactNode }) => <Text style={{ color: colors.muted }}>{children}</Text>;

const s = StyleSheet.create({
  button: { paddingVertical: space(1), paddingHorizontal: space(2), borderRadius: 8, borderWidth: 1,
    borderColor: colors.border, backgroundColor: colors.glass, alignItems: "center" },
  small: { paddingVertical: 6, paddingHorizontal: 10 },
  primary: { backgroundColor: colors.accent, borderColor: colors.accent },
  danger: { borderColor: colors.danger },
  buttonText: { color: colors.text, fontWeight: "600", fontSize: 14 },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border },
  chipText: { color: colors.text, fontSize: 13 },
  field: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: space(1.5), color: colors.text,
    backgroundColor: colors.glass, fontSize: 15 },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", padding: space(2) },
  sheet: { backgroundColor: colors.glassStrong, borderColor: colors.border, borderWidth: 1, borderRadius: 16,
    padding: space(3), maxWidth: 480, width: "100%", alignSelf: "center", maxHeight: "90%" },
  sheetTitle: { color: colors.text, fontSize: 18, fontWeight: "700" },
});
