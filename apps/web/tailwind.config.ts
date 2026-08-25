import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-mode="dark"]'],
  theme: {
    extend: {
      borderRadius: {
        card: "12px",
        control: "8px",
      },
      spacing: {
        1: "4px",
      },
    },
  },
  plugins: [],
};
export default config;
