#!/usr/bin/env node
/**
 * Cardano Governance Sync — CLI (Commander + Inquirer + Chalk)
 *
 * Subcommands:
 *   sync [step]      Run sync pipeline (all or specific step)
 *   verify           Check DB row counts
 *   backup           Backup DB to .sql file
 *   ai               Generate AI summaries + budget extraction
 *   logs             View recent log files
 *   status           Quick DB connection + row count check
 *   interactive      Interactive menu (default if no args)
 *
 * Usage:
 *   node cli.js sync                    # full sync
 *   node cli.js sync proposals          # only proposals step
 *   node cli.js sync --skip-delegators  # skip slow delegators
 *   node cli.js verify                  # verify DB
 *   node cli.js backup --no-data        # logic only backup
 *   node cli.js ai --apply              # write AI summaries to DB
 *   node cli.js logs --tail             # tail latest log
 *   node cli.js status                  # quick DB status
 *   node cli.js                         # interactive menu
 */

const { Command } = require('commander');
const inquirer = require('inquirer');
const chalk = require('chalk');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { info, error, warn } = require('./helpers');

const program = new Command();
const SCRIPT_DIR = __dirname;
const LOG_DIR = path.join(SCRIPT_DIR, '..', 'Python', 'logs');

// ── Helpers ────────────────────────────────────────────────────────

function printHeader(title) {
  const line = '='.repeat(60);
  console.log(chalk.cyan(line));
  console.log(chalk.cyan.bold(`  ${title}`));
  console.log(chalk.cyan(line));
}

function runScript(scriptName, extraArgs = []) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(SCRIPT_DIR, scriptName);
    if (!fs.existsSync(scriptPath)) {
      error(`Script not found: ${scriptPath}`);
      return reject(new Error('Script not found'));
    }
    const cmd = process.execPath;
    const args = [scriptPath, ...extraArgs];
    const proc = spawn(cmd, args, { stdio: 'inherit', cwd: SCRIPT_DIR });
    proc.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Exit code ${code}`));
    });
    proc.on('error', reject);
  });
}

const SYNC_STEPS = [
  'epoch',
  'proposals',
  'drep_list',
  'drep_info',
  'voting_summary',
  'vote_activities',
  'drep_delegators',
];

// ── Subcommands ────────────────────────────────────────────────────

// sync
program
  .command('sync [step]')
  .description('Run sync pipeline (all or specific step)')
  .option('--skip-delegators', 'Skip drep_delegators (slow)')
  .action(async (step, opts) => {
    if (step && !SYNC_STEPS.includes(step)) {
      error(`Unknown step '${step}'. Valid: ${SYNC_STEPS.join(', ')}`);
      process.exit(1);
    }
    try {
      if (step) {
        printHeader(`Sync: ${step}`);
        await runScript('sync_all.js', [`--only=${step}`]);
      } else {
        const extra = [];
        if (opts.skipDelegators) extra.push('--skip-delegators');
        printHeader('Full Sync Pipeline');
        await runScript('sync_all.js', extra);
      }
    } catch (e) {
      process.exit(1);
    }
  });

// verify
program
  .command('verify')
  .description('Verify DB row counts')
  .action(async () => {
    printHeader('DB Verification');
    try {
      await runScript('verify.js');
    } catch (e) {
      process.exit(1);
    }
  });

// backup
program
  .command('backup')
  .description('Backup DB to .sql file')
  .option('--no-data', 'Logic only (skip data)')
  .option('--tables <tables>', 'Comma-separated table list')
  .option('--out <path>', 'Output file path')
  .action(async (opts) => {
    printHeader('DB Backup');
    const extra = [];
    if (opts.noData) extra.push('--no-data');
    if (opts.tables) extra.push('--tables', opts.tables);
    if (opts.out) extra.push('--out', opts.out);
    // JS doesn't have backup_db.js — use Python version
    const pyScript = path.join(SCRIPT_DIR, '..', 'Python', 'backup_db.py');
    if (fs.existsSync(pyScript)) {
      const proc = spawn('python', [pyScript, ...extra], { stdio: 'inherit' });
      proc.on('close', (code) => process.exit(code || 0));
    } else {
      error('backup_db.py not found. Backup is Python-only.');
      process.exit(1);
    }
  });

// ai
program
  .command('ai')
  .description('Generate AI summaries + budget extraction')
  .option('--apply', 'Write to DB (default: dry-run)')
  .option('--skip-existing', 'Only process rows with NULL fields')
  .action(async (opts) => {
    printHeader('AI Summary + Budget Generation');
    const extra = [];
    if (opts.apply) extra.push('--apply');
    else extra.push('--dry-run');
    if (opts.skipExisting) extra.push('--skip-existing');
    // JS doesn't have generate_ai_summaries.js — use Python version
    const pyScript = path.join(SCRIPT_DIR, '..', 'Python', 'generate_ai_summaries.py');
    if (fs.existsSync(pyScript)) {
      const proc = spawn('python', [pyScript, ...extra], { stdio: 'inherit' });
      proc.on('close', (code) => process.exit(code || 0));
    } else {
      error('generate_ai_summaries.py not found. AI summaries are Python-only.');
      process.exit(1);
    }
  });

// logs
program
  .command('logs')
  .description('View recent log files')
  .option('--tail', 'Tail latest log file')
  .action(async (opts) => {
    if (!fs.existsSync(LOG_DIR)) {
      console.log('No logs directory found.');
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
      console.log('No log files found.');
      return;
    }

    if (opts.tail) {
      const latest = files[0];
      console.log(chalk.cyan(`--- ${latest.name} (latest) ---\n`));
      const content = fs.readFileSync(latest.path, 'utf-8');
      const lines = content.split('\n');
      const last50 = lines.slice(-50);
      last50.forEach(l => console.log(l));
    } else {
      console.log(`Log files in ${LOG_DIR} (${files.length} total):\n`);
      console.log(`${'#'.padEnd(4)} ${'File'.padEnd(40)} ${'Size'.padStart(10)} ${'Modified'.padStart(20)}`);
      console.log('-'.repeat(78));
      files.slice(0, 20).forEach((f, i) => {
        const sizeStr = f.size < 1024 * 1024
          ? `${(f.size / 1024).toFixed(1)} KB`
          : `${(f.size / (1024 * 1024)).toFixed(1)} MB`;
        const modStr = new Date(f.mtime).toISOString().slice(0, 16).replace('T', ' ');
        console.log(`${String(i + 1).padEnd(4)} ${f.name.padEnd(40)} ${sizeStr.padStart(10)} ${modStr.padStart(20)}`);
      });
      if (files.length > 20) {
        console.log(`\n  ... and ${files.length - 20} more files`);
      }
      console.log(`\nUse: node cli.js logs --tail  to view latest log`);
    }
  });

// status
program
  .command('status')
  .description('Quick DB connection + row count check')
  .action(async () => {
    printHeader('DB Status');
    try {
      const { pgConnect } = require('./helpers');
      const { TABLE_COLUMNS } = require('./config');
      const client = await pgConnect();
      console.log(chalk.green('  Connected to PostgreSQL OK\n'));
      console.log(`  ${'Table'.padEnd(35)} ${'Rows'.padStart(10)}`);
      console.log(`  ${'-'.repeat(47)}`);
      for (const table of Object.keys(TABLE_COLUMNS).sort()) {
        try {
          const res = await client.query(`SELECT count(*)::int as cnt FROM "${table}"`);
          const cnt = res.rows[0].cnt;
          console.log(`  ${table.padEnd(35)} ${String(cnt).padStart(10)}`);
        } catch (e) {
          console.log(`  ${table.padEnd(35)} ${'N/A'.padStart(10)}`);
        }
      }
      // ga_* count
      try {
        const gaRes = await client.query(
          `SELECT count(*)::int as cnt FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'ga_%'`
        );
        console.log(`\n  ga_* tables: ${gaRes.rows[0].cnt}`);
      } catch (e) {
        // ignore
      }
      await client.end();
    } catch (e) {
      error(`DB connection failed: ${e.message}`);
      process.exit(1);
    }
  });

// interactive (default when no command)
program
  .command('interactive')
  .description('Interactive menu (default if no args)')
  .action(async () => {
    printHeader('Cardano Governance Sync — Interactive');
    const { action } = await inquirer.prompt([
      {
        type: 'list',
        name: 'action',
        message: 'What do you want to do?',
        choices: [
          { name: 'Full sync (all steps)', value: 'sync_all' },
          { name: 'Sync specific step', value: 'sync_step' },
          { name: 'Verify DB (row counts)', value: 'verify' },
          { name: 'Quick DB status', value: 'status' },
          { name: 'Backup DB', value: 'backup' },
          { name: 'Generate AI summaries', value: 'ai' },
          { name: 'View logs', value: 'logs' },
          { name: 'Exit', value: 'exit' },
        ],
      },
    ]);

    try {
      switch (action) {
        case 'sync_all': {
          const { skip } = await inquirer.prompt([
            {
              type: 'confirm',
              name: 'skip',
              message: 'Skip drep_delegators? (slow step)',
              default: false,
            },
          ]);
          const extra = skip ? ['--skip-delegators'] : [];
          printHeader('Full Sync Pipeline');
          await runScript('sync_all.js', extra);
          break;
        }
        case 'sync_step': {
          const { step } = await inquirer.prompt([
            {
              type: 'list',
              name: 'step',
              message: 'Which step?',
              choices: SYNC_STEPS,
            },
          ]);
          printHeader(`Sync: ${step}`);
          await runScript('sync_all.js', [`--only=${step}`]);
          break;
        }
        case 'verify':
          printHeader('DB Verification');
          await runScript('verify.js');
          break;
        case 'status':
          printHeader('DB Status');
          const { pgConnect } = require('./helpers');
          const { TABLE_COLUMNS } = require('./config');
          const client = await pgConnect();
          console.log(chalk.green('  Connected to PostgreSQL OK\n'));
          console.log(`  ${'Table'.padEnd(35)} ${'Rows'.padStart(10)}`);
          console.log(`  ${'-'.repeat(47)}`);
          for (const table of Object.keys(TABLE_COLUMNS).sort()) {
            try {
              const res = await client.query(`SELECT count(*)::int as cnt FROM "${table}"`);
              console.log(`  ${table.padEnd(35)} ${String(res.rows[0].cnt).padStart(10)}`);
            } catch (e) {
              console.log(`  ${table.padEnd(35)} ${'N/A'.padStart(10)}`);
            }
          }
          await client.end();
          break;
        case 'backup': {
          const { noData } = await inquirer.prompt([
            {
              type: 'confirm',
              name: 'noData',
              message: 'Logic only (skip data)?',
              default: false,
            },
          ]);
          printHeader('DB Backup');
          const pyScript = path.join(SCRIPT_DIR, '..', 'Python', 'backup_db.py');
          const extra = noData ? ['--no-data'] : [];
          const proc = spawn('python', [pyScript, ...extra], { stdio: 'inherit' });
          proc.on('close', (code) => process.exit(code || 0));
          break;
        }
        case 'ai': {
          const { apply } = await inquirer.prompt([
            {
              type: 'confirm',
              name: 'apply',
              message: 'Write to DB? (no = dry-run preview)',
              default: false,
            },
          ]);
          printHeader('AI Summary + Budget Generation');
          const pyScript = path.join(SCRIPT_DIR, '..', 'Python', 'generate_ai_summaries.py');
          const extra = apply ? ['--apply'] : ['--dry-run'];
          const proc = spawn('python', [pyScript, ...extra], { stdio: 'inherit' });
          proc.on('close', (code) => process.exit(code || 0));
          break;
        }
        case 'logs': {
          if (!fs.existsSync(LOG_DIR)) {
            console.log('No logs directory found.');
            break;
          }
          const files = fs.readdirSync(LOG_DIR)
            .filter(f => f.startsWith('sync_') && f.endsWith('.log'))
            .map(f => ({ name: f, path: path.join(LOG_DIR, f), mtime: fs.statSync(path.join(LOG_DIR, f)).mtime }))
            .sort((a, b) => b.mtime - a.mtime);
          if (files.length === 0) {
            console.log('No log files found.');
            break;
          }
          const { file } = await inquirer.prompt([
            {
              type: 'list',
              name: 'file',
              message: 'Which log file?',
              choices: files.slice(0, 20).map(f => ({ name: f.name, value: f })),
            },
          ]);
          const content = fs.readFileSync(file.path, 'utf-8');
          const lines = content.split('\n');
          const last50 = lines.slice(-50);
          last50.forEach(l => console.log(l));
          break;
        }
        case 'exit':
          console.log('Bye!');
          break;
      }
    } catch (e) {
      if (e.isTtyError) {
        error('Interactive prompt not supported in this environment.');
      } else {
        error(e.message);
      }
      process.exit(1);
    }
  });

// ── Main ───────────────────────────────────────────────────────────

program
  .name('cli.js')
  .description('Cardano Governance Sync — CLI tool')
  .version('1.0.0');

// If no args, run interactive mode
const args = process.argv.slice(2);
if (args.length === 0) {
  // Default to interactive
  program.parse(['interactive', ...args]);
} else {
  program.parse();
}
