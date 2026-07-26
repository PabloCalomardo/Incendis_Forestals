import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
let args = process.argv.slice(2);
let cwd = root;

if (args[0] === "--cwd") {
  cwd = path.resolve(root, args[1]);
  args = args.slice(2);
}

const pythonExecutable =
  process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");

const python = existsSync(pythonExecutable) ? pythonExecutable : "python";
const env = {
  ...process.env,
  PYTHONPATH: [path.join(root, "apps", "api"), path.join(root, "workers")]
    .concat(process.env.PYTHONPATH ? [process.env.PYTHONPATH] : [])
    .join(path.delimiter),
};

const result = spawnSync(python, args, {
  cwd,
  env,
  stdio: "inherit",
  shell: false,
});

process.exit(result.status ?? 1);
