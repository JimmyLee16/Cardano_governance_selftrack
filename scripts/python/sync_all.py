"""Orchestrator: run all sync steps from Cardano on-chain → Neon + Supabase (dual-write).

Usage:
    python sync_all.py                  # Full sync
    python sync_all.py --skip-delegators  # Skip drep_delegators (slow)
    python sync_all.py --only=proposals   # Run specific step
    python sync_all.py --verify           # Only verify
"""

import sys
import time

from helpers import get_logger, check_env


def main():
    check_env()
    logger = get_logger()

    args = sys.argv[1:]
    skip_delegators = "--skip-delegators" in args
    verify_only = "--verify" in args
    only_step = None
    for arg in args:
        if arg.startswith("--only="):
            only_step = arg.split("=")[1]

    if verify_only:
        from verify import main as verify_main
        verify_main()
        return

    logger.info("=" * 60)
    logger.info("  Cardano On-Chain → Neon + Supabase Full Sync")
    logger.info("=" * 60)

    steps = [
        ("epoch", "sync_epoch"),
        ("proposals", "sync_proposals"),
        ("drep_list", "sync_drep_list"),
        ("drep_info", "sync_drep_info"),
        ("voting_summary", "sync_voting_summary"),
        ("vote_activities", "sync_vote_activities"),
        ("drep_delegators", "sync_drep_delegators"),
    ]

    for name, module_name in steps:
        if only_step and only_step != name:
            continue
        if skip_delegators and name == "drep_delegators":
            logger.info(f"\n⏭️  Skipping {name} (--skip-delegators)")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f">>> Step: {name}")
        logger.info(f"{'='*60}")

        try:
            mod = __import__(module_name)
            func = getattr(mod, f"sync_{name}")
            if name == "vote_activities":
                result = func(logger=logger, only_active=True)
            else:
                result = func(logger=logger)
            logger.info(f"✅ {name} completed: {result}")
        except Exception as e:
            logger.error(f"❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()

    # Final verification
    logger.info(f"\n{'='*60}")
    logger.info(">>> Final Verification")
    logger.info(f"{'='*60}")
    from verify import main as verify_main
    verify_main()

    logger.info("\n" + "=" * 60)
    logger.info("  Sync Complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
