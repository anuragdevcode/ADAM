import type { Config } from "tailwindcss";

/**
 * Colours are exposed as semantic names backed by the CSS custom properties in
 * `globals.css`, so components never hardcode a hex value and the dark theme
 * needs no parallel set of classes.
 */
const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: {
          DEFAULT: "var(--surface)",
          subtle: "var(--surface-subtle)",
          sunken: "var(--surface-sunken)",
          inverted: "var(--surface-inverted)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
          inverted: "var(--border-inverted)",
        },
        ink: {
          DEFAULT: "var(--text)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
          faint: "var(--text-faint)",
          onBrand: "var(--text-on-brand)",
        },
        brand: {
          DEFAULT: "var(--brand)",
          hover: "var(--brand-hover)",
          active: "var(--brand-active)",
          soft: "var(--brand-soft)",
          softHover: "var(--brand-soft-hover)",
          border: "var(--brand-border)",
        },
        seal: {
          DEFAULT: "var(--accent)",
          soft: "var(--accent-soft)",
          border: "var(--accent-border)",
        },
        ok: { DEFAULT: "var(--success)", soft: "var(--success-soft)" },
        warn: { DEFAULT: "var(--warning)", soft: "var(--warning-soft)" },
        danger: { DEFAULT: "var(--danger)", soft: "var(--danger-soft)" },
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
      },
      borderRadius: {
        card: "14px",
        panel: "18px",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      maxWidth: {
        thread: "52rem",
      },
    },
  },
  plugins: [],
};
export default config;
