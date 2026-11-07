import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "../auth";
import { Header } from "../components/Header";
import { colors } from "../theme";

function Screens() {
  const { me, ready } = useAuth();
  if (!ready) return <View style={{ flex: 1, backgroundColor: colors.bg }} />;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <StatusBar style="light" />
      {me && <Header />}
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg }, animation: "fade" }}>
        <Stack.Protected guard={!!me}>
          <Stack.Screen name="index" />
          <Stack.Screen name="watchlist" />
          <Stack.Screen name="watched" />
          <Stack.Screen name="blocked" />
          <Stack.Screen name="preferred" />
          <Stack.Screen name="profile" />
        </Stack.Protected>
        <Stack.Protected guard={!me}>
          <Stack.Screen name="login" />
        </Stack.Protected>
      </Stack>
    </SafeAreaView>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <Screens />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
