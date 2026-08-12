#!/usr/bin/env node
/**
 * Cardano Governance Sync — TUI (full-screen, blessed)
 *
 * Arrow keys to navigate, Enter to select, q/Esc to quit.
 *
 * Usage:
 *   node tui.js
 */

const blessed = require('blessed');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const SCRIPT_DIR = __dirname;
const LOG_DIR = path.join(SCRIPT_DIR, '..', 'Python', 'logs');

const SYNC_STEPS = [
  ['epoch',           'Update current epoch from Koios tip'],
  ['proposals',       'Fetch proposal list from Koios'],
  ['drep_list',       'Fetch DRep registry from Blockfrost'],
  ['drep_info',       'Fetch DRep metadata + stake from Blockfrost'],
  ['voting_summary',  'Fetch voting summary from Koios'],
  ['vote_activities', 'Fetch votes + IPFS comments → ga_* tables'],
  ['drep_delegators', 'Fetch delegators from Koios (slow)'],
];

// ── Helpers ────────────────────────────────────────────────────────

function runScript(screen, scriptName, extraArgs = []) {
  return new Promise((resolve) => {
    // Hide TUI, show terminal output
    screen.leave();

    const scriptPath = path.join(SCRIPT_DIR, scriptName);
    if (!fs.existsSync(scriptPath)) {
      console.log(`\x1b[31mERROR: ${scriptPath} not found\x1b[0m`);
    } else {
      const cmd = process.execPath;
      const args = [scriptPath, ...extraArgs];
      try {
        spawnSync(cmd, args, { stdio: 'inherit', cwd: SCRIPT_DIR });
      } catch (e) {
        console.log(`\x1b[31mError: ${e.message}\x1b[0m`);
      }
    }

    console.log('\n\x1b[90mPress Enter to return to TUI...\x1b[0m');
    // Wait for Enter
    process.stdin.resume();
    process.stdin.once('data', () => {
      process.stdin.pause();
      screen.enter();
      screen.alloc();
      screen.render();
      resolve();
    });
  });
}

function spawnSync(cmd, args, opts) {
  const { spawnSync: ss } = require('child_process');
  ss(cmd, args, opts);
}

function runPythonScript(screen, scriptName, extraArgs = []) {
  return new Promise((resolve) => {
    screen.leave();

    const pyScript = path.join(SCRIPT_DIR, '..', 'Python', scriptName);
    if (!fs.existsSync(pyScript)) {
      console.log(`\x1b[31mERROR: ${pyScript} not found\x1b[0m`);
    } else {
      try {
        spawnSync('python', [pyScript, ...extraArgs], { stdio: 'inherit' });
      } catch (e) {
        console.log(`\x1b[31mError: ${e.message}\x1b[0m`);
      }
    }

    console.log('\n\x1b[90mPress Enter to return to TUI...\x1b[0m');
    process.stdin.resume();
    process.stdin.once('data', () => {
      process.stdin.pause();
      screen.enter();
      screen.alloc();
      screen.render();
      resolve();
    });
  });
}

// ── TUI Screens ────────────────────────────────────────────────────

function createScreen() {
  const screen = blessed.screen({
    smartCSR: true,
    title: 'Cardano Governance Sync',
    fullUnicode: true,
  });

  // Quit handlers
  screen.key(['q', 'C-c', 'escape'], () => process.exit(0));

  return screen;
}

function createList(screen, items, label, top = 3) {
  const list = blessed.list({
    parent: screen,
    label,
    top,
    left: 'center',
    width: '70%',
    height: items.length + 4,
    keys: true,
    vi: true,
    mouse: true,
    border: { type: 'line' },
    style: {
      selected: { bg: 'cyan', fg: 'black', bold: true },
      item: { fg: 'white' },
      border: { fg: 'cyan' },
      label: { fg: 'cyan', bold: true },
    },
    items: items.map(i => i[0]),
  });

  // Description box
  const descBox = blessed.box({
    parent: screen,
    top: top + items.length + 4,
    left: 'center',
    width: '70%',
    height: 3,
    border: { type: 'line' },
    style: { border: { fg: 'gray' } },
    content: '',
  });

  list.on('select item', (item, idx) => {
    if (items[idx] && items[idx][1]) {
      descBox.setContent(` ${items[idx][1]}`);
      screen.render();
    }
  });

  return list;
}

function createHeader(screen) {
  blessed.box({
    parent: screen,
    top: 0,
    left: 'center',
    width: '100%',
    height: 3,
    content: '{center}{bold}{cyan-fg}◆ Cardano Governance Sync{/cyan-fg}{/bold}{/center}\n{center}{gray-fg} PostgreSQL · Koios · Blockfrost · IPFS {/gray-fg}{/center}',
    tags: true,
    style: {},
  });
}

function createFooter(screen) {
  blessed.box({
    parent: screen,
    bottom: 0,
    left: 'center',
    width: '100%',
    height: 1,
    content: '{center}{gray-fg} ↑↓ Navigate · ENTER Select · q Quit {/gray-fg}{/center}',
    tags: true,
  });
}

// ── Main Menu ──────────────────────────────────────────────────────

async function showMainMenu(screen) {
  const items = [
    ['Full Sync',             'Run all 7 sync steps + verify'],
    ['Sync: Step',            'Choose a specific sync step'],
    ['Verify DB',             'Check row counts across all tables'],
    ['DB Status',             'Quick connection + row count check'],
    ['Backup DB',             'Export DB to .sql file'],
    ['AI Summaries',          'Generate AI summaries + budget extract'],
    ['View Logs',             'Browse sync log files'],
    ['Quit',                  'Exit'],
  ];

  return new Promise((resolve) => {
    createHeader(screen);
    const list = createList(screen, items, ' Main Menu ');
    createFooter(screen);
    list.focus();
    screen.render();

    list.on('action', async (item, idx) => {
      const action = items[idx][0];
      if (action === 'Quit') {
        process.exit(0);
      }
      // Remove old widgets
      screen.children.forEach(c => c.detach());
      screen.render();

      switch (action) {
        case 'Full Sync':
          await runScript(screen, 'sync_all.js');
          break;
        case 'Sync: Step':
          await showSyncStepMenu(screen);
          break;
        case 'Verify DB':
          await runScript(screen, 'verify.js');
          break;
        case 'DB Status':
          await showDBStatus(screen);
          break;
        case 'Backup DB':
          await showBackupMenu(screen);
          break;
        case 'AI Summaries':
          await showAIMenu(screen);
          break;
        case 'View Logs':
          await showLogs(screen);
          break;
      }
      resolve();
    });
  });
}

// ── Sync Step Menu ─────────────────────────────────────────────────

async function showSyncStepMenu(screen) {
  const items = [...SYNC_STEPS, ['Back', 'Return to main menu']];

  return new Promise((resolve) => {
    createHeader(screen);
    const list = createList(screen, items, ' Sync Step ');
    createFooter(screen);
    list.focus();
    screen.render();

    list.on('action', async (item, idx) => {
      screen.children.forEach(c => c.detach());
      screen.render();

      if (idx < SYNC_STEPS.length) {
        const step = SYNC_STEPS[idx][0];
        await runScript(screen, 'sync_all.js', [`--only=${step}`]);
      }
      resolve();
    });
  });
}

// ── Backup Menu ────────────────────────────────────────────────────

async function showBackupMenu(screen) {
  const items = [
    ['Full Backup',           'Data + SQL logic (functions, triggers)'],
    ['Logic Only',            'Skip data, export DDL only'],
    ['Back',                  'Return to main menu'],
  ];

  return new Promise((resolve) => {
    createHeader(screen);
    const list = createList(screen, items, ' Backup DB ');
    createFooter(screen);
    list.focus();
    screen.render();

    list.on('action', async (item, idx) => {
      screen.children.forEach(c => c.detach());
      screen.render();

      if (idx === 0) {
        await runPythonScript(screen, 'backup_db.py');
      } else if (idx === 1) {
        await runPythonScript(screen, 'backup_db.py', ['--no-data']);
      }
      resolve();
    });
  });
}

// ── AI Menu ────────────────────────────────────────────────────────

async function showAIMenu(screen) {
  const items = [
    ['Dry Run (preview)',     'Preview without writing to DB'],
    ['Apply (write to DB)',   'Write summaries + budget to DB'],
    ['Apply + Skip Existing', 'Only process rows with NULL fields'],
    ['Back',                  'Return to main menu'],
  ];

  return new Promise((resolve) => {
    createHeader(screen);
    const list = createList(screen, items, ' AI Summaries ');
    createFooter(screen);
    list.focus();
    screen.render();

    list.on('action', async (item, idx) => {
      screen.children.forEach(c => c.detach());
      screen.render();

      if (idx === 0) {
        await runPythonScript(screen, 'generate_ai_summaries.py', ['--dry-run']);
      } else if (idx === 1) {
        await runPythonScript(screen, 'generate_ai_summaries.py', ['--apply']);
      } else if (idx === 2) {
        await runPythonScript(screen, 'generate_ai_summaries.py', ['--apply', '--skip-existing']);
      }
      resolve();
    });
  });
}

// ── DB Status ──────────────────────────────────────────────────────

async function showDBStatus(screen) {
  return new Promise((resolve) => {
    createHeader(screen);

    const box = blessed.box({
      parent: screen,
      label: ' DB Status ',
      top: 3,
      left: 'center',
      width: '80%',
      height: '80%',
      scrollable: true,
      alwaysScroll: true,
      keys: true,
      vi: true,
      border: { type: 'line' },
      style: { border: { fg: 'cyan' }, label: { fg: 'cyan', bold: true } },
      content: ' Connecting to PostgreSQL...',
    });

    createFooter(screen);
    box.focus();
    screen.render();

    // Run DB status query
    (async () => {
      try {
        const { pgConnect } = require('./helpers');
        const { TABLE_COLUMNS } = require('./config');
        const client = await pgConnect();

        let output = ' {green-fg}✓ Connected to PostgreSQL{/}\n\n';
        output += ` ${'Table'.padEnd(35)} ${'Rows'.padStart(10)}\n`;
        output += ` ${'-'.repeat(47)}\n`;

        for (const table of Object.keys(TABLE_COLUMNS).sort()) {
          try {
            const res = await client.query(`SELECT count(*)::int as cnt FROM "${table}"`);
            const cnt = res.rows[0].cnt;
            const color = cnt > 0 ? '{green-fg}' : '{yellow-fg}';
            output += ` ${table.padEnd(35)} ${color}${String(cnt).padStart(10)}{/}\n`;
          } catch (e) {
            output += ` ${table.padEnd(35)} {red-fg}${'N/A'.padStart(10)}{/}\n`;
          }
        }

        // ga_* count
        try {
          const gaRes = await client.query(
            `SELECT count(*)::int as cnt FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'ga_%'`
          );
          output += `\n {cyan-fg}ga_* tables: ${gaRes.rows[0].cnt}{/}\n`;
        } catch (e) {}

        await client.end();
        box.setContent(output);
        box.setContent(output + '\n\n {gray-fg}Press ENTER to return to main menu...{/}');
        screen.render();
      } catch (e) {
        box.setContent(` {red-fg}✗ DB connection failed: ${e.message}{/}\n\n {gray-fg}Press ENTER to return...{/}`);
        screen.render();
      }
    })();

    box.key(['enter', 'escape', 'q'], () => {
      screen.children.forEach(c => c.detach());
      screen.render();
      resolve();
    });
  });
}

// ── View Logs ──────────────────────────────────────────────────────

async function showLogs(screen) {
  return new Promise((resolve) => {
    createHeader(screen);

    if (!fs.existsSync(LOG_DIR)) {
      const box = blessed.box({
        parent: screen,
        top: 3, left: 'center', width: '70%', height: 5,
        border: { type: 'line' },
        style: { border: { fg: 'gray' } },
        content: ' {yellow-fg}No logs directory found.{/}\n\n {gray-fg}Press ENTER to return...{/}',
        tags: true,
      });
      box.key(['enter', 'escape', 'q'], () => {
        screen.children.forEach(c => c.detach());
        screen.render();
        resolve();
      });
      box.focus();
      screen.render();
      return;
    }

    const files = fs.readdirSync(LOG_DIR)
      .filter(f => f.startsWith('sync_') && f.endsWith('.log'))
      .map(f => {
        const fp = path.join(LOG_DIR, f);
        const stat = fs.statSync(fp);
        return { name: f, path: fp, size: stat.size, mtime: stat.mtime };
      })
      .sort((a, b) => b.mtime - a.mtime);

    if (files.length === 0) {
      const box = blessed.box({
        parent: screen,
        top: 3, left: 'center', width: '70%', height: 5,
        border: { type: 'line' },
        style: { border: { fg: 'gray' } },
        content: ' {yellow-fg}No log files found.{/}\n\n {gray-fg}Press ENTER to return...{/}',
        tags: true,
      });
      box.key(['enter', 'escape', 'q'], () => {
        screen.children.forEach(c => c.detach());
        screen.render();
        resolve();
      });
      box.focus();
      screen.render();
      return;
    }

    const items = files.slice(0, 30).map(f => {
      const sizeStr = f.size < 1024 * 1024
        ? `${(f.size / 1024).toFixed(1)} KB`
        : `${(f.size / (1024 * 1024)).toFixed(1)} MB`;
      const modStr = new Date(f.mtime).toISOString().slice(0, 16).replace('T', ' ');
      return [f.name, `${sizeStr} · ${modStr}`];
    });
    items.push(['Back', 'Return to main menu']);

    const list = createList(screen, items, ' Log Files ');
    createFooter(screen);
    list.focus();
    screen.render();

    list.on('action', async (item, idx) => {
      screen.children.forEach(c => c.detach());
      screen.render();

      if (idx < files.length) {
        // Show log content
        const content = fs.readFileSync(files[idx].path, 'utf-8');
        const lines = content.split('\n').slice(-100);

        const box = blessed.box({
          parent: screen,
          label: ` ${files[idx].name} (last 100 lines) `,
          top: 3, left: 'center', width: '90%', height: '85%',
          scrollable: true,
          alwaysScroll: true,
          keys: true,
          vi: true,
          border: { type: 'line' },
          style: { border: { fg: 'cyan' }, label: { fg: 'cyan', bold: true } },
          content: lines.join('\n') + '\n\n {gray-fg}Press ENTER or q to return...{/}',
          tags: true,
        });
        createFooter(screen);
        box.focus();
        screen.render();

        box.key(['enter', 'escape', 'q'], () => {
          screen.children.forEach(c => c.detach());
          screen.render();
          resolve();
        });
      } else {
        resolve();
      }
    });
  });
}

// ── Main ───────────────────────────────────────────────────────────

async function main() {
  const screen = createScreen();

  // Main loop — keep returning to main menu
  while (true) {
    await showMainMenu(screen);
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
