import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Playfair Display", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      colors: {
        // Luxury/Editorial Design System Palette
        lux: {
          alabaster: "#F9F8F6",
          charcoal:  "#1A1A1A",
          taupe:     "#EBE5DE",
          warmgrey:  "#6C6863",
          gold:      "#D4AF37",
          "gold-light": "#E8C94A",
        },
        // Theme-responsive colors mapping to CSS variables
        themeBg: "var(--bg-primary)",
        themeBgSecondary: "var(--bg-secondary)",
        themeCard: "var(--bg-card)",
        themeCardAlt: "var(--bg-card-alt)",
        themeText: "var(--text-primary)",
        themeTextMuted: "var(--text-muted)",
        themeBorder: "var(--border-primary)",
        themeBorderStrong: "var(--border-strong)",
        themeSurfaceInput: "var(--surface-input)",
        themeSurfaceHover: "var(--surface-hover)",
        themeDarkSection: "var(--bg-dark-section)",
        themeTextInverted: "var(--text-inverted)",

        // Keep JetBrains Mono code colours for compiler output
        brand: {
          300: "#a5b9fd",
          400: "#8191f9",
          500: "#6366f1",
        },
        surface: {
          0: "#0a0a0f",
          1: "#111118",
          2: "#18181f",
          3: "#1f1f2e",
          4: "#26263a",
        },
      },
      animation: {
        "fade-in":      "fadeIn 0.7s ease-out forwards",
        "slide-up":     "slideUp 0.8s ease-out forwards",
        "slide-up-slow":"slideUp 1.2s ease-out forwards",
        "pulse-slow":   "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "spin-slow":    "spin 2s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      transitionDuration: {
        "400":  "400ms",
        "600":  "600ms",
        "700":  "700ms",
        "1500": "1500ms",
        "2000": "2000ms",
      },
      transitionTimingFunction: {
        luxury: "cubic-bezier(0.25, 0.46, 0.45, 0.94)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
      },
      borderWidth: {
        "0.5": "0.5px",
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem",
        "26": "6.5rem",
        "30": "7.5rem",
      },
      maxWidth: {
        "8xl": "88rem",
        "9xl": "96rem",
      },
    },
  },
  plugins: [],
};

export default config;
