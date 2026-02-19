"""
Azure AI Foundry Agent with Azure AI Search (Responses API)

Creates an agent that queries an Azure AI Search index and returns
grounded answers with URL citations.

Requires: azure-ai-projects >= 2.0.0b3 (install with: pip install --pre azure-ai-projects)
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
    PromptAgentDefinition,
)


def main():
    load_dotenv()

    # Load configuration
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    search_connection = os.environ.get("AZURE_AI_SEARCH_CONNECTION_NAME")
    search_index = os.environ.get("AI_SEARCH_INDEX_NAME")

    # Validate required environment variables
    missing = []
    if not endpoint:
        missing.append("FOUNDRY_PROJECT_ENDPOINT")
    if not search_connection:
        missing.append("AZURE_AI_SEARCH_CONNECTION_NAME")
    if not search_index:
        missing.append("AI_SEARCH_INDEX_NAME")
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    # Initialize client
    credential = DefaultAzureCredential()
    client = AIProjectClient(endpoint=endpoint, credential=credential)

    # Verify the AI Search connection exists
    print(f"Verifying connection '{search_connection}'...")
    try:
        connection = client.connections.get(connection_name=search_connection)
        print(f"  Connection found: {connection.name} (type: {connection.type})")
    except Exception as e:
        print(f"Error: Could not find connection '{search_connection}'.")
        print(f"  Detail: {e}")
        print("\nAvailable connections:")
        try:
            for conn in client.connections.list():
                print(f"  - {conn.name} (type: {conn.type})")
        except Exception:
            print("  (Could not list connections)")
        sys.exit(1)

    # Configure the AI Search tool
    ai_search_tool = AzureAISearchAgentTool(
        search_resources=AzureAISearchToolResource(
            index_resources=[
                AISearchIndexResource(
                    index_connection_id=connection.id,
                    index_name=search_index,
                )
            ]
        )
    )

    # Create the agent
    print(f"Creating agent with model '{model}' and AI Search index '{search_index}'...")
    agent = client.agents.create_version(
        model=model,
        name="search-agent",
        instructions="You are a helpful assistant. Use the Azure AI Search tool to find relevant information and provide grounded answers with citations.",
        tools=ai_search_tool.definitions,
        tool_resources=ai_search_tool.resources,
    )
    print(f"  Agent created: {agent.id}")

    try:
        # Interactive query loop
        while True:
            print()
            query = input("Enter your question (or 'quit' to exit): ").strip()
            if not query or query.lower() in ("quit", "exit", "q"):
                break

            print("\nAgent response:\n")

            # Stream the response
            with client.agents.run(
                agent_id=agent.id,
                model=model,
                input=query,
                tools=ai_search_tool.definitions,
                tool_resources=ai_search_tool.resources,
                stream=True,
            ) as stream:
                citations = []
                for event in stream:
                    # Handle text output events
                    if hasattr(event, "type"):
                        if event.type == "response.output_text.delta":
                            print(event.delta, end="", flush=True)
                        elif event.type == "response.output_text.annotation.added":
                            annotation = event.annotation
                            if hasattr(annotation, "url_citation"):
                                citations.append({
                                    "title": annotation.url_citation.title,
                                    "url": annotation.url_citation.url,
                                })

            print("\n")

            # Display citations
            if citations:
                print("Citations:")
                seen = set()
                for i, cite in enumerate(citations, 1):
                    key = cite["url"]
                    if key not in seen:
                        seen.add(key)
                        title = cite.get("title", "Untitled")
                        print(f"  [{i}] {title}")
                        print(f"      {cite['url']}")

    except KeyboardInterrupt:
        print("\n\nInterrupted.")

    finally:
        # Clean up the agent
        print(f"\nDeleting agent {agent.id}...")
        try:
            client.agents.delete_version(agent.id)
            print("  Agent deleted.")
        except Exception as e:
            print(f"  Warning: Could not delete agent: {e}")


if __name__ == "__main__":
    main()
