import tailwindcssAnimate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["PingFang SC", "Microsoft YaHei", "system-ui", "sans-serif"],
      },
      colors: {
        // 全部走 CSS 变量（RGB 三元组），:root=深色，html.light=浅色，见 index.css
        brand: {
          DEFAULT: "rgb(var(--brand) / <alpha-value>)",
          dark: "rgb(var(--brand-dark) / <alpha-value>)",
          light: "rgb(var(--brand-light) / <alpha-value>)",
        },
        ink: "#0F172A",
        muted: "#475569",
        surface: "#F8FAFC",
        theme: {
          bg: "rgb(var(--theme-bg) / <alpha-value>)",
          deep: "rgb(var(--theme-deep) / <alpha-value>)",
          card: "rgb(var(--theme-card) / <alpha-value>)",
          input: "rgb(var(--theme-input) / <alpha-value>)",
          line: "rgb(var(--theme-line) / <alpha-value>)",
          text: "rgb(var(--theme-text) / <alpha-value>)",
          sub: "rgb(var(--theme-sub) / <alpha-value>)",
        },
      },
      boxShadow: {
        soft: "0 1px 2px rgba(15,23,42,0.04), 0 1px 3px rgba(15,23,42,0.05)",
        card: "0 1px 3px rgba(15,23,42,0.05), 0 6px 16px rgba(15,23,42,0.05)",
        pop: "0 6px 28px rgba(15,23,42,0.12)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "caret-blink": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        shake: {
          "0%, 100%": { transform: "translateX(0)" },
          "25%": { transform: "translateX(-6px)" },
          "75%": { transform: "translateX(6px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        "caret-blink": "caret-blink 1s step-end infinite",
        shake: "shake 0.3s ease-in-out",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
