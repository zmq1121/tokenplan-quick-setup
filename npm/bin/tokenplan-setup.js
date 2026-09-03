#!/usr/bin/env node
/**
 * tokenplan-setup — npx entry for the Tencent Cloud TokenHub installer.
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

async function main(argv = process.argv.slice(2), options = {}) {
  const script = options.script || SCRIPT;
  const findPython = options.detectPython || detectPython;
  const spawnProcess = options.spawn || spawn;

  if (!fileExists(script)) {
    console.error("tokenplan-setup: bundled TokenHub installer missing: " + script);
    return 1;
  }

  const python = await findPython();
  if (!python) {
    console.error("tokenplan-setup: 未找到 Python 3，请先安装：");
    console.error("  macOS:   brew install python3  或 https://www.python.org/downloads");
    console.error("  Windows: winget install Python.Python.3.12");
    return 1;
  }

  const child = spawnProcess(python.cmd, [...python.args, script, ...argv], {
    stdio: "inherit",
  });

  return new Promise((resolve) => {
    child.on("error", (err) => {
      console.error("tokenplan-setup: 无法启动 TokenHub 安装器: " + err.message);
      resolve(1);
    });
    child.on("close", (code) => {
      resolve(code === null ? 1 : code);
    });
  });
}

module.exports = {
  SCRIPT,
  fileExists,
  tryPython,
  detectPython,
  main,
};

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  }).catch((err) => {
    console.error("tokenplan-setup: 未处理的启动错误: " + err.message);
    process.exitCode = 1;
  });
}
