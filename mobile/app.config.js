// Dynamic Expo config. Its only extra job over app.json is loading `.env.dev`
// into process.env at startup, so Expo inlines EXPO_PUBLIC_* vars from it.
//
// Why this file exists: Expo's built-in dotenv only reads `.env`,
// `.env.local`, `.env.development`, etc. — NOT `.env.dev`. The repo uses
// `.env.dev` as the single env-file convention (backend + mobile), so we load
// it ourselves here before Metro transforms any code.
const fs = require("fs");
const path = require("path");

const envPath = path.resolve(__dirname, ".env.dev");
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    if (!(key in process.env)) process.env[key] = value; // real env wins
  }
}

// `config` is the resolved static config from app.json — pass it through.
module.exports = ({ config }) => config;
