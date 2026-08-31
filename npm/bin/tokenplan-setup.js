#!/usr/bin/env node
/**
 * tokenplan-setup — npx entry for the Tencent Cloud Token Plan installer.
 *
 * The installer core is a single self-contained Python script
 * (lib/setup.command, polyglot bash/python). This Node wrapper only:
 *   1. locates a usable Python 3 (python3 / python / py -3),
 *   2. spawns it with the bundled core script,
 *   3. forwards all CLI args and propagates the exit code.
 *
 * Zero dependencies; works on macOS, Linux and Windows.
 */
"use strict";

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const SCRIPT = path.join(__dirname, "..", "lib", "setup.command");

function fileExists(p) {
  try {
    fs.accessSync(p, fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

function tryPython(candidates) {
  return new Promise((resolve) => {
    if (candidates.length === 0) {
      resolve(null);
      return;
    }
    const [cmd, ...rest] = candidates[0];
    const child = spawn(cmd, [...rest, "--version"], { stdio: "ignore" });
    child.on("error", () => resolve(tryPython(candidates.slice(1))));
    child.on("close", (code) => {
      if (code === 0) resolve({ cmd, args: rest });
      else resolve(tryPython(candidates.slice(1)));
    });
  });
}

function detectPython() {
  const isWindows = process.platform === "win32";
  const candidates = isWindows
    ? [["py", "-3"], ["python"], ["python3"]]
    : [["python3"], ["python"]];
  return tryPython(candidates);
}

async function main() {
  if (!fileExists(SCRIPT)) {
    console.error("tokenplan-setup: bundled installer script missing: " + SCRIPT);
    process.exit(1);
  }

  const python = await detectPython();
  if (!python) {
    console.error("tokenplan-setup: 未找到 Python 3，请先安装：");
    console.error("  macOS:   brew install python3  或 https://www.python.org/downloads");
    console.error("  Windows: winget install Python.Python.3.12");
    process.exit(1);
  }

  const child = spawn(python.cmd, [...python.args, SCRIPT, ...process.argv.slice(2)], {
    stdio: "inherit",
  });

  child.on("error", (err) => {
    console.error("tokenplan-setup: failed to start installer: " + err.message);
    process.exit(1);
  });

  child.on("close", (code) => {
    process.exit(code === null ? 1 : code);
  });
}

main();
