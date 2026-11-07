import { GeistMono_400Regular, GeistMono_500Medium } from "@expo-google-fonts/geist-mono";
import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold, useFonts } from "@expo-google-fonts/inter";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "../auth";
import { Header } from "../components/Header";
import { colors } from "../theme";

function Screens() {
  const { me, ready } = useAuth();
  if (!ready) return <View style={{ flex: 1, backgroundColor: colors.canvas }} />;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }}>
      <StatusBar style="light" />
      {me && <Header />}
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.canvas }, animation: "fade" }}>
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
  const [fontsReady] = useFonts({ Inter_400Regular, Inter_500Medium, Inter_600SemiBold, GeistMono_400Regular,
    GeistMono_500Medium });
  if (!fontsReady) return <View style={{ flex: 1, backgroundColor: colors.canvas }} />;
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <Screens />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
