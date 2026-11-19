#!/usr/bin/env node

const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const packageRoot = path.resolve(__dirname, "..");
const venvPython = path.join(packageRoot, ".venv-npm", process.platform === "win32" ? "Scripts\\python.exe" : "bin/python");
const python = fs.existsSync(venvPython)
  ? venvPython
  : (process.platform === "win32" ? "py -3.12" : "python3");

const command = python.includes(" ") ? python.split(" ")[0] : python;
const args = python.includes(" ")
  ? [...python.split(" ").slice(1), "-m", "backend.main"]
  : ["-m", "backend.main"];

const child = spawn(command, args, {
  cwd: packageRoot,
  stdio: "inherit",
  env: process.env,
});

child.on("error", (error) => {
  console.error("Unable to start Universal Converter:", error.message);
  console.error("Install Python 3.12 or newer, then run npm install again.");
  process.exit(1);
});

child.on("exit", (code) => process.exit(code ?? 0));
