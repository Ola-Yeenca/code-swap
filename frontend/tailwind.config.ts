import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111013",
        paper: "#f5f3ef",
        brass: "#b26a2b",
        pine: "#1f4d3d",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'IBM Plex Sans'", "sans-serif"],
      },
      boxShadow: {
        panel: "0 16px 40px -20px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
