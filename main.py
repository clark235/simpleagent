"""
Azure AI Foundry Agent with Azure AI Search (Responses API)

Creates a Foundry agent with the AI Search tool and queries it using the
OpenAI Responses API via get_openai_client(). Returns grounded answers
with URL citations.

New Foundry (2025) pattern:
  - AIProjectClient.agents.create_version()  ← creates the agent definition
  - AIProjectClient.get_openai_client()       ← gets an authenticated OpenAI client
  - openai_client.responses.create()         ← runs the agent via Responses API

Requires: pip install --pre azure-ai-projects azure-identity python-dotenv
"""

import os
import sys

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
    PromptAgentDefinition,
)


def main():
    load_dotenv()

    # ── Config ────────────────────────────────────────────────────────────────
    endpoint         = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model            = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    search_conn_name = os.environ.get("AZURE_AI_SEARCH_CONNECTION_NAME")
    search_index     = os.environ.get("AI_SEARCH_INDEX_NAME")

    missing = [v for v, val in [
        ("FOUNDRY_PROJECT_ENDPOINT",        endpoint),
        ("AZURE_AI_SEARCH_CONNECTION_NAME", search_conn_name),
        ("AI_SEARCH_INDEX_NAME",            search_index),
    ] if not val]

    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    # ── Clients ───────────────────────────────────────────────────────────────
    credential     = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)

    # ── Resolve AI Search connection ──────────────────────────────────────────
    print(f"Verifying connection '{search_conn_name}'...")
    try:
        connection = project_client.connections.get(search_conn_name)
        print(f"  ✅ Connection found: {connection.name} (type: {connection.type})")
    except Exception as e:
        print(f"  ❌ Could not find connection '{search_conn_name}': {e}")
        print("\nAvailable connections:")
        try:
            for conn in project_client.connections.list():
                print(f"  - {conn.name} (type: {conn.type})")
        except Exception:
            pass
        sys.exit(1)

    # ── Configure AI Search tool ──────────────────────────────────────────────
    ai_search_tool = AzureAISearchAgentTool(
        search_resources=AzureAISearchToolResource(
            index_resources=[
                AISearchIndexResource(
                    index_connection_id=connection.id,
                    index_name=search_index,
                    query_type=AzureAISearchQueryType.SIMPLE,
                )
            ]
        )
    )

    # ── Create agent version (new Foundry pattern) ────────────────────────────
    # create_version() registers a named, versioned agent definition.
    # This uses the new Foundry Agents API (visible in Foundry portal → Agents).
    AGENT_NAME = "simpleagent-search"
    print(f"Creating agent version '{AGENT_NAME}'...")
    try:
        agent_version = project_client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model=model,
                instructions=(
                    "You are a helpful assistant with access to an Azure AI Search knowledge base. "
                    "Always search for relevant information before answering. "
                    "Provide grounded answers with inline citations. "
                    "If the search results don't contain the answer, say so clearly."
                ),
                tools=ai_search_tool.definitions,
                tool_resources=ai_search_tool.resources,
            ),
        )
        print(f"  ✅ Agent created: name={agent_version.name}, version={agent_version.version}")
    except Exception as e:
        print(f"  ❌ Failed to create agent: {e}")
        sys.exit(1)

    # ── Get OpenAI client and run via Responses API ───────────────────────────
    # get_openai_client() returns an authenticated openai.OpenAI client
    # pointing at this project's endpoint with Entra ID auth.
    # The Responses API (client.responses.create) is the new Foundry invocation path.
    print("\nStarting interactive session. Type 'quit' to exit.\n")

    try:
        with project_client.get_openai_client(api_version="2025-11-15-preview") as openai_client:

            while True:
                print()
                query = input("Your question: ").strip()
                if not query or query.lower() in ("quit", "exit", "q"):
                    break

                print("\nAgent:\n")

                try:
                    response = openai_client.responses.create(
                        model=model,
                        input=query,
                        tools=ai_search_tool.definitions,
                        tool_resources=ai_search_tool.resources,
                        stream=True,
                    )

                    citations = []
                    for event in response:
                        event_type = getattr(event, "type", None)
                        if event_type == "response.output_text.delta":
                            delta = getattr(event, "delta", "")
                            print(delta, end="", flush=True)
                        elif event_type == "response.output_text.annotation.added":
                            ann = getattr(event, "annotation", None)
                            if ann and hasattr(ann, "url_citation"):
                                uc = ann.url_citation
                                citations.append({
                                    "title": getattr(uc, "title", "Untitled"),
                                    "url":   getattr(uc, "url",   ""),
                                })

                    print("\n")

                    if citations:
                        print("Citations:")
                        seen = set()
                        idx = 1
                        for cite in citations:
                            if cite["url"] not in seen:
                                seen.add(cite["url"])
                                print(f"  [{idx}] {cite['title']}")
                                print(f"       {cite['url']}")
                                idx += 1

                except KeyboardInterrupt:
                    print("\n\nInterrupted.")
                    break
                except Exception as e:
                    print(f"\n  ❌ Error running agent: {e}")

    finally:
        # ── Clean up agent version ────────────────────────────────────────────
        print(f"\nCleaning up agent '{AGENT_NAME}' version {agent_version.version}...")
        try:
            project_client.agents.delete_version(
                agent_name=agent_version.name,
                agent_version=agent_version.version,
            )
            print("  ✅ Agent version deleted.")
        except Exception as e:
            print(f"  ⚠️  Could not delete agent version: {e}")


if __name__ == "__main__":
    main()
