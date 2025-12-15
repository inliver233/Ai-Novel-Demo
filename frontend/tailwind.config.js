/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        surface: "var(--color-surface)",
        ink: "var(--color-ink)",
        subtext: "var(--color-subtext)",
        accent: "var(--color-accent)",
        success: "var(--color-success)",
        border: "var(--color-border)",
      },
      fontFamily: {
        ui: ["var(--font-ui)"],
        content: ["var(--font-content)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        atelier: "var(--radius-base)",
      },
    },
  },
  plugins: [],
}
