import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ember: "#b42318",
        canopy: "#1f6f50",
        ash: "#3f454d",
        skywatch: "#1d5fd0",
      },
    },
  },
  plugins: [],
};

export default config;
