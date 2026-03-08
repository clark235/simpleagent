"""
Azure AI Foundry Agent with Azure AI Search (Responses API)

Creates a Foundry agent with the AI Search tool and queries it using the
OpenAI Responses API. Returns grounded answers with URL citations.

New Foundry (2025) pattern using azure-ai-projects >= 2.0.0:
  - AIProjectClient.agents.create_version()   ← registers named agent
  - AIProjectClient.get_openai_client()        ← authenticated OpenAI client
  - openai_client.responses.create()          ← Responses API invocation

Requires:
  pip install "azure-ai-projects>=2.0.0" azure-identity python-dotenv

Environment Variables:
  FOUNDRY_PROJECT_ENDPOINT     — e.g. https://clark-simpleagent-vnet.services.ai.azure.com/api/projects/<name>
  FOUNDRY_MODEL_DEPLOYMENT_NAME — e.g. gpt-4o
  AZURE_AI_SEARCH_CONNECTION_NAME — connection name in Foundry project
  AI_SEARCH_INDEX_NAME         — e.g. simpleagent-repo-index
"""

import os
import sys

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AzureAISearchTool,
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

    credential = DefaultAzureCredential()
    client = AIProjectClient(endpoint=endpoint, credential=credential)

    # ── Create / update agent version ─────────────────────────────────────────
    search_tool = AzureAISearchTool(
        index_connection_name=search_conn_name,
        index_name=search_index,
        query_type=AzureAISearchQueryType.SEMANTIC,
        semantic_configuration_name="default",
        top_k=5,
    )

    agent_def = client.agents.create_version(
        name="simpleagent-search-bot",
        model=model,
        instructions=(
            "You are a helpful assistant for the simpleagent Azure AI Foundry demo. "
            "Use the Azure AI Search tool to answer questions about the simpleagent "
            "repository contents, including its architecture, deployment steps, and code. "
            "Always cite the source filename when you use information from the search results."
        ),
        tools=search_tool.definitions,
        tool_resources=AzureAISearchToolResource(
            indexes=[AISearchIndexResource(
                index_connection_id=search_conn_name,
                index_name=search_index,
            )]
        ),
    )
    print(f"Agent version registered: {agent_def.id}")

    # ── Run via Responses API ──────────────────────────────────────────────────
    openai_client = client.get_openai_client()

    question = (
        "What does the simpleagent project do, and what Azure services does it use?"
    )
    print(f"\nQuestion: {question}\n")

    response = openai_client.responses.create(
        model=model,
        input=question,
        tools=search_tool.definitions,
        tool_resources=AzureAISearchToolResource(
            indexes=[AISearchIndexResource(
                index_connection_id=search_conn_name,
                index_name=search_index,
            )]
        ),
    )

    print("Answer:")
    for item in response.output:
        if hasattr(item, "content"):
            for block in item.content:
                if hasattr(block, "text"):
                    print(block.text)

    # Print any URL citations
    annotations = []
    for item in response.output:
        if hasattr(item, "content"):
            for block in item.content:
                if hasattr(block, "annotations"):
                    annotations.extend(block.annotations)

    if annotations:
        print("\nSources:")
        for ann in annotations:
            if hasattr(ann, "url"):
                print(f"  - {ann.url}")
            elif hasattr(ann, "file_citation"):
                print(f"  - {ann.file_citation}")


if __name__ == "__main__":
    main()
