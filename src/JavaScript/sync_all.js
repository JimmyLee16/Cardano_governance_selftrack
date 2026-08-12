// sync_all.js
// Orchestrator: run all sync steps (PostgreSQL-only)
// Equivalent to sync_all.py
//
// Usage:
//   node sync_all.js              # Full sync
//   node sync_all.js --skip-delegators  # Skip drep_delegators (slow)
//   node sync_all.js --only=proposals   # Run specific step
//   node sync_all.js --verify         # Only verify

const { info, error } = require('./helpers');

async function runStep(name, moduleName, onlyActive = false) {
  info(`\n${'='.repeat(60)}`);
  info(`>>> Step: ${name}`);
  info(`${'='.repeat(60)}`);

  try {
    const mod = require(`./${moduleName}`);
    const func = mod[`sync${name.charAt(0).toUpperCase() + name.slice(1)}`];
    const result = onlyActive ? await func({ onlyActive: true }) : await func();
    info(`✅ ${name} completed: ${result}`);
    return true;
  } catch (e) {
    error(`❌ ${name} failed: ${e.message}`);
    console.error(e.stack);
    return false;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const skipDelegators = args.includes('--skip-delegators');
  const verifyOnly = args.includes('--verify');
  const onlyArg = args.find(a => a.startsWith('--only='));
  const onlyStep = onlyArg ? onlyArg.split('=')[1] : null;

  if (verifyOnly) {
    const { main: verifyMain } = require('./verify');
    await verifyMain();
    return;
  }

  info('='.repeat(60));
  info('  Cardano On-Chain → PostgreSQL Full Sync');
  info('='.repeat(60));

  const steps = [
    ['epoch', 'sync_epoch'],
    ['proposals', 'sync_proposals'],
    ['drep_list', 'sync_drep_list'],
    ['drep_info', 'sync_drep_info'],
    ['voting_summary', 'sync_voting_summary'],
    ['vote_activities', 'sync_vote_activities'],
    ['drep_delegators', 'sync_drep_delegators'],
  ];

  for (const [name, moduleName] of steps) {
    if (onlyStep && onlyStep !== name) continue;
    if (skipDelegators && name === 'drep_delegators') {
      info(`\n⏭️  Skipping ${name} (--skip-delegators)`);
      continue;
    }

    const onlyActive = name === 'vote_activities';
    await runStep(name, moduleName, onlyActive);
  }

  // Final verification
  info(`\n${'='.repeat(60)}`);
  info('>>> Final Verification');
  info(`${'='.repeat(60)}`);
  const { main: verifyMain } = require('./verify');
  await verifyMain();

  info('\n' + '='.repeat(60));
  info('  Sync Complete!');
  info('='.repeat(60));
}

if (require.main === module) {
  main().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { main };