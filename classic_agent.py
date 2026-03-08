"""
Azure AI Foundry Classic Agent (Assistants API)

Creates an agent via the classic Assistants API that appears in the
Classic Foundry portal (ml.azure.com) under Agents.

Classic Foundry (Azure ML Hub/Project) pattern using azure-ai-agents >= 1.0.0:
  - AgentsClient(endpoint, credential)        ← classic hub endpoint
  - client.agents.create(model, instructions) ← creates persistent agent
  - client.threads.create() → messages.create() → runs.create_and_process()

The agent is PERSISTENT and VISIBLE in ml.azure.com → your project → Agents.

Requires:
  pip install "azure-ai-agents>=1.0.0" azure-identity python-dotenv

Environment Variables:
  CLASSIC_PROJECT_ENDPOINT — e.g. https://<hub>.api.azureml.ms
  FOUNDRY_MODEL_DEPLOYMENT_NAME — e.g. gpt-4o
  CLASSIC_PROJECT_NAME — e.g. clark-simpleagent-project (optional, for display)
"""

import os
import sys

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    ListSortOrder,
    MessageRole,
)


def main():
    load_dotenv()

    # ── Config ────────────────────────────────────────────────────────────────
    endpoint = os.environ.get("CLASSIC_PROJECT_ENDPOINT")
    model    = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    project  = os.environ.get("CLASSIC_PROJECT_NAME", "clark-simpleagent-project")

    if not endpoint:
        print("Error: CLASSIC_PROJECT_ENDPOINT is required.")
        print("Set it to the classic hub endpoint, e.g.:")
        print("  https://<hub-name>.api.azureml.ms")
        print("\nFind it in Azure ML Studio → your Hub/Project → Settings → Project endpoint")
        sys.exit(1)

    credential = DefaultAzureCredential()

    # Classic AgentsClient uses the hub/project endpoint
    client = AgentsClient(endpoint=endpoint, credential=credential)

    # ── Create agent (persistent — visible in classic portal) ─────────────────
    agent = client.agents.create(
        model=model,
        name="simpleagent-classic-demo",
        instructions=(
            "You are a helpful assistant for the simpleagent Azure AI Foundry demo. "
            "Answer questions about the project architecture, deployment steps, and "
            "best practices for Azure AI Foundry with VNet injection."
        ),
    )
    print(f"Classic agent created: {agent.id}")
    print(f"  Visible in ml.azure.com → {project} → Agents")

    # ── Create thread and run ──────────────────────────────────────────────────
    thread = client.threads.create()
    print(f"Thread created: {thread.id}")

    question = (
        "Explain Azure AI Foundry's VNet injection pattern and why it matters for "
        "enterprise security."
    )
    print(f"\nQuestion: {question}\n")

    client.messages.create(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=question,
    )

    run = client.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id,
    )
    print(f"Run completed: {run.status}")

    # ── Print response ─────────────────────────────────────────────────────────
    messages = client.messages.list(
        thread_id=thread.id,
        order=ListSortOrder.DESCENDING,
    )

    print("Answer:")
    for msg in messages:
        if msg.role == MessageRole.AGENT:
            for content_block in msg.content:
                if hasattr(content_block, "text") and hasattr(content_block.text, "value"):
                    print(content_block.text.value)
            break  # Only first assistant message


if __name__ == "__main__":
    main()
