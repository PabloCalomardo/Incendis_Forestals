import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const venvPython =
  process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");

function run(command, args) {
  console.log(`> ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    shell: false,
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (!existsSync(venvPython)) {
  console.log("Creating Python virtual environment in .venv");
  run("python", ["-m", "venv", ".venv"]);
}

console.log("Installing Python dependencies for API and workers");
run(venvPython, [
  "-m",
  "pip",
  "install",
  "-r",
  "apps/api/requirements-dev.txt",
  "-r",
  "workers/requirements-dev.txt",
]);
