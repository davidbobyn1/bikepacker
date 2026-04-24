/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#2563eb", foreground: "#ffffff" },
        secondary: { DEFAULT: "#f1f5f9", foreground: "#0f172a" },
        background: "#f8fafc",
        foreground: "#0f172a",
        card: "#ffffff",
        border: "#e2e8f0",
        muted: { DEFAULT: "#f1f5f9", foreground: "#64748b" },
        accent: "#f59e0b",
        destructive: { DEFAULT: "#ef4444", foreground: "#ffffff" },
        trail: "#16a34a",
        camp: "#f59e0b",
        hotel: "#3b82f6",
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", "serif"],
      },
    },
  },
  plugins: [],
}

