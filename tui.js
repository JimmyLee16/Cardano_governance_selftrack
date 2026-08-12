#!/usr/bin/env node
/**
 * Root entry point — launches the TUI from src/JavaScript/tui.js.
 *
 * Run from repo root:
 *   node tui.js
 */

const path = require('path');
const fs = require('fs');

const tuiScript = path.join(__dirname, 'src', 'JavaScript', 'tui.js');

if (!fs.existsSync(tuiScript)) {
  console.error(`ERROR: TUI script not found at ${tuiScript}`);
  process.exit(1);
}

// Change to src/JavaScript so relative requires work
process.chdir(path.join(__dirname, 'src', 'JavaScript'));

// Load and execute tui.js
require(tuiScript);
