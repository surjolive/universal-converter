const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const packageRoot = path.resolve(__dirname, "..");
const venvDirectory = path.join(packageRoot, ".venv-npm");
const venvPython = path.join(venvDirectory, process.platform === "win32" ? "Scripts\\python.exe" : "bin/python");

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: packageRoot,
    stdio: "inherit",
  });
  return result.status === 0;
}

const pythonCandidates = process.platform === "win32"
  ? [
      ["py", ["-3.12"]],
      ["py", ["-3"]],
      ["python", []],
    ]
  : [["python3", []], ["python", []]];

if (!fs.existsSync(venvPython)) {
  let created = false;
  for (const [command, prefix] of pythonCandidates) {
    if (run(command, [...prefix, "-m", "venv", venvDirectory])) {
      created = true;
      break;
    }
  }
  if (!created) {
    console.error("Universal Converter requires Python 3.12 or newer.");
    process.exit(1);
  }
}

if (!run(venvPython, ["-m", "pip", "install", "-r", "requirements.txt"])) {
  console.error("Failed to install the Universal Converter Python dependencies.");
  process.exit(1);
}
