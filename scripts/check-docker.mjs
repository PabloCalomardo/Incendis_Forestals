import { spawnSync } from "node:child_process";
import process from "node:process";

const docker = process.platform === "win32" ? "docker.exe" : "docker";
const composeResult = spawnSync(docker, ["compose", "version"], {
  stdio: "ignore",
  shell: false,
});

if (composeResult.status !== 0) {
  console.error("");
  console.error("Docker no trobat o Docker Compose no disponible.");
  console.error("");
  console.error("Per usar `npm run dev:docker` o `npm run reset-db`, instal·la Docker Desktop");
  console.error("i torna a obrir la terminal perquè `docker` quedi al PATH.");
  console.error("");
  console.error("Mentrestant pots usar:");
  console.error("  npm run dev");
  console.error("");
  process.exit(1);
}

const daemonResult = spawnSync(docker, ["info"], {
  stdio: "ignore",
  shell: false,
});

if (daemonResult.status !== 0) {
  console.error("");
  console.error("Docker instal·lat, però el dimoni Docker no està arrencat.");
  console.error("");
  console.error("Obre Docker Desktop, espera que indiqui que està running,");
  console.error("i comprova després:");
  console.error("  docker info");
  console.error("");
  console.error("Quan això funcioni, torna a executar:");
  console.error("  npm run dev:docker");
  console.error("");
  process.exit(1);
}
