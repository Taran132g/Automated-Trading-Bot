#!/usr/bin/env python3
"""
CLI entry point for all trading agents.
Usage: python run_agent.py <agent_name>

Agents:
  post_market      — Daily post-market analyst (run at 4:15 PM ET weekdays)
  alert_quality    — Weekly alert quality analyst (run Sunday 6 PM ET)
  risk_monitor     — Live risk watchdog (run every 5 min during market hours)
  optimizer        — Weekly strategy optimizer (run Sunday 7 PM ET)
  pattern_analyst  — Daily pattern trade report + intraday Claude filter (run at 4:30 PM ET weekdays)
"""

import sys
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

AGENTS = {
    "post_market":     "agents.post_market",
    "alert_quality":   "agents.alert_quality",
    "risk_monitor":    "agents.risk_monitor",
    "optimizer":       "agents.optimizer",
    "pattern_analyst": "agents.pattern_analyst",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in AGENTS:
        print(f"Usage: python run_agent.py [{' | '.join(AGENTS)}]")
        sys.exit(1)

    agent_name = sys.argv[1]
    module_path = AGENTS[agent_name]

    # Ensure working directory is the project root (important when called from cron)
    os.chdir(Path(__file__).parent)

    import importlib
    module = importlib.import_module(module_path)
    module.run()


if __name__ == "__main__":
    main()
