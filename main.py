"""
simpleagent — Azure AI Foundry VNet Demo

Entry point that redirects to the appropriate demo script.

Available scripts:
  - responses_agent.py  — New Foundry (Responses API, ai.azure.com)
  - classic_agent.py    — Classic Foundry (Assistants API, ml.azure.com)
  - index_repo.py       — Index this repo into Azure AI Search

Usage:
  python responses_agent.py    # New Foundry (Responses API)
  python classic_agent.py      # Classic Foundry (Assistants API)
  python index_repo.py         # Re-index repo files into AI Search

See VNET-DEPLOYMENT.md for full deployment details.
See README.md for setup instructions.
"""

import sys
import subprocess


def main():
    print("simpleagent — Azure AI Foundry VNet Demo")
    print("=========================================")
    print()
    print("Available demos:")
    print("  1. responses_agent.py  — New Foundry portal (Responses API)")
    print("  2. classic_agent.py    — Classic Foundry portal (Assistants API)")
    print("  3. index_repo.py       — Re-index repo files into AI Search")
    print()
    print("Run one of the above scripts directly, e.g.:")
    print("  python responses_agent.py")
    print()
    print("See VNET-DEPLOYMENT.md for full resource details and credentials.")


if __name__ == "__main__":
    main()
