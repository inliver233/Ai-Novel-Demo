/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--color-canvas) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        "surface-hover": "rgb(var(--color-surface-hover) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        subtext: "rgb(var(--color-subtext) / <alpha-value>)",
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        success: "rgb(var(--color-success) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        info: "rgb(var(--color-info) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
      },
      fontFamily: {
        ui: ["var(--font-ui)"],
        content: ["var(--font-content)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        atelier: "var(--radius-base)",
      },
      transitionTimingFunction: {
        atelier: "var(--motion-ease-standard)",
      },
      transitionDuration: {
        "atelier-fast": "var(--motion-duration-fast)",
        atelier: "var(--motion-duration-base)",
        "atelier-slow": "var(--motion-duration-slow)",
      },
    },
  },
  plugins: [],
};
