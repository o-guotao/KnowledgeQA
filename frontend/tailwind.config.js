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
        brand: {
          DEFAULT: "#2563EB",
          dark: "#1E40AF",
          light: "#3B82F6",
        },
        ink: "#0F172A",
        muted: "#475569",
        surface: "#F8FAFC",
        // 钢蓝灰主题（仿目标截图的中明度蓝灰）
        theme: {
          bg: "#14161b",
          deep: "#0f1114",
          card: "#1f232b",
          input: "#1b1f27",
          line: "rgba(255,255,255,0.10)",
          text: "#e9ecf1",
          sub: "#9aa3b2",
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
