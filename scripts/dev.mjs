import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const venvPython =
  process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : "python";
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const children = [];

function start(name, command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: root,
    env: {
      ...process.env,
      API_INTERNAL_BASE_URL: "http://localhost:8000",
      NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
      PYTHONPATH: [path.join(root, "apps", "api"), path.join(root, "workers")]
        .concat(process.env.PYTHONPATH ? [process.env.PYTHONPATH] : [])
        .join(path.delimiter),
      ...options.env,
    },
    stdio: "inherit",
    shell: false,
  });

  child.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`${name} stopped with exit code ${code}`);
      stopAll(code);
    }
  });

  children.push(child);
}

function stopAll(code = 0) {
  for (const child of children) {
    if (!child.killed) {
      child.kill();
    }
  }
  process.exit(code);
}

process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));

start("api", python, [
  "-m",
  "uvicorn",
  "app.main:app",
  "--host",
  "0.0.0.0",
  "--port",
  "8000",
  "--app-dir",
  "apps/api",
]);
start("web", npm, ["run", "dev", "--workspace", "@wip/web"]);
