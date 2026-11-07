import { Platform, TextStyle, ViewStyle } from "react-native";

// FlickFind's look ("midnight command center"): a near-black canvas, surfaces defined by hairline "key" edges rather
// than drop shadows, neutral light-gray actions, Inter type, Geist Mono for tiny technical labels, and a single coral
// accent kept for the brand mark and the AI badge. Spacing snaps to an 8px grid.
export const colors = {
  canvas: "#040506",   // page background, everywhere
  card: "#07080a",     // cards and panels
  recessed: "#111214", // input wells, user messages
  badge: "#1b1c1e",    // badge tags
  border: "#363739",   // hairlines
  slate: "#2f3031",    // ghost button borders
  white: "#ffffff",    // headings, high-emphasis text
  ash: "#9c9c9d",      // secondary text
  smoke: "#6a6b6c",    // muted labels
  mist: "#e6e6e6",     // the only filled action surface
  iron: "#454647",     // text on mist
  coral: "#ff6363",    // brand mark and AI badge only, never body text
  ember: "#452324",    // warm-tinted surface for notes
  well: "rgba(255,255,255,0.05)", // inset fields and pills
};

export const fonts = {
  regular: "Inter_400Regular",
  medium: "Inter_500Medium",
  semibold: "Inter_600SemiBold",
  mono: "GeistMono_400Regular",
  monoMedium: "GeistMono_500Medium",
};

export const space = (n: number) => n * 8;
export const radius = { badge: 6, button: 8, input: 8, poster: 10, card: 16, large: 20, pill: 9999 };
export const MAX_WIDTH = 1200;

export const shadow = {
  // the "keyboard key": inset top highlight, a faint outer ring, an inset bottom shade. Elevation without drop shadows.
  key: "rgba(255,255,255,0.05) 0px 1px 0px 0px inset, rgba(255,255,255,0.25) 0px 0px 0px 1px, rgba(0,0,0,0.2) 0px -1px 0px 0px inset",
  edge: "rgba(255,255,255,0.1) 0px 1px 0px 0px inset, rgba(255,255,255,0.06) 0px 0px 0px 1px inset",
  lift: "rgba(0,0,0,0.03) 0px 7px 3px 0px, rgba(0,0,0,0.25) 0px 4px 4px 0px",
  window: "rgba(0,0,0,0.4) 0px 4px 40px 8px, rgba(0,0,0,0.8) 0px 0px 0px 0.5px, rgba(255,255,255,0.3) 0px 0.5px 0px 0px inset",
};

// backdrop blur only exists on the web; native gets the same translucent fill without it
export const glass: ViewStyle = Platform.OS === "web"
  ? ({ backdropFilter: "blur(48px)", WebkitBackdropFilter: "blur(48px)" } as unknown as ViewStyle)
  : {};

// a CSS gradient as a background: the web takes backgroundImage, native the experimental_ prop
export const gradient = (css: string): ViewStyle =>
  (Platform.OS === "web" ? { backgroundImage: css } : { experimental_backgroundImage: css }) as unknown as ViewStyle;

// the hero atmosphere: a coral glow and a deep blue wash, the one place colour is turned up
export const atmosphere = gradient(
  "radial-gradient(ellipse 60% 55% at 22% 18%, rgba(255,99,99,0.28) 0%, rgba(255,99,99,0) 70%), " +
  "radial-gradient(ellipse 70% 60% at 82% 12%, rgba(4,63,150,0.55) 0%, rgba(6,18,37,0) 72%)");

export const type: Record<string, TextStyle> = {
  display: { fontFamily: fonts.regular, fontSize: 48, lineHeight: 56, letterSpacing: 0.2, color: colors.white },
  heading: { fontFamily: fonts.regular, fontSize: 32, lineHeight: 37, color: colors.white },
  subheading: { fontFamily: fonts.medium, fontSize: 20, lineHeight: 24, letterSpacing: 0.2, color: colors.white },
  title: { fontFamily: fonts.medium, fontSize: 15, lineHeight: 20, letterSpacing: 0.1, color: colors.white },
  body: { fontFamily: fonts.regular, fontSize: 16, lineHeight: 22, color: colors.white },
  small: { fontFamily: fonts.regular, fontSize: 14, lineHeight: 20, color: colors.ash },
  caption: { fontFamily: fonts.regular, fontSize: 13, lineHeight: 18, color: colors.ash },
  label: { fontFamily: fonts.medium, fontSize: 13, lineHeight: 16, letterSpacing: 0.1, color: colors.white },
  eyebrow: { fontFamily: fonts.monoMedium, fontSize: 11, lineHeight: 14, letterSpacing: 0.8, textTransform: "uppercase",
    color: colors.ash },
  mono: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 16, letterSpacing: 0.2, color: colors.smoke },
};
