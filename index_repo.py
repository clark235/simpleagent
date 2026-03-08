"""
Index simpleagent GitHub repo files into Azure AI Search.

Reads local repo files, chunks them, and uploads to the simpleagent-repo-index
Azure AI Search index using the REST API with an Azure CLI bearer token.

Approach:
  1. Read each file in the repo (markdown + Python)
  2. Chunk large files (>2000 chars) into overlapping 1500-char chunks
  3. Upload documents via Search REST API using api-key or bearer token
  4. Semantic config "default" is already on the index

Usage:
  # With API key (set AZURE_SEARCH_ADMIN_KEY env var):
  AZURE_SEARCH_ADMIN_KEY=<key> python index_repo.py

  # Or use az CLI credentials (RBAC must be assigned):
  python index_repo.py

Requires:
  pip install azure-identity python-dotenv
"""

import os
import sys
import json
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SEARCH_SERVICE = "clark-simpleagent-search-vnet"
INDEX_NAME = "simpleagent-repo-index"
API_VERSION = "2024-07-01"

REPO_PATH = Path(__file__).parent

FILES_TO_INDEX = [
    "DEMO.md",
    "README.md",
    "PROVISIONING.md",
    "VNET-DEPLOYMENT.md",
    "main.py",
    "responses_agent.py",
    "classic_agent.py",
    "index_repo.py",
    "validate_environment.py",
    "validate_vnet_environment.py",
    "requirements.txt",
]

MAX_CHARS = 1500
OVERLAP = 200


def get_auth_header():
    """Get auth header — prefer API key, fall back to az CLI token."""
    api_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
    if api_key:
        return {"api-key": api_key}

    # Try RBAC token
    try:
        import subprocess
        token = subprocess.check_output([
            "az", "account", "get-access-token",
            "--resource", "https://search.azure.com/",
            "--query", "accessToken", "-o", "tsv"
        ]).decode().strip()
        return {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"Warning: Could not get az CLI token: {e}")
        print("Set AZURE_SEARCH_ADMIN_KEY env var with the Search admin key.")
        sys.exit(1)


def get_file_type(filename):
    parts = filename.rsplit(".", 1)
    return parts[-1].lower() if len(parts) > 1 else "txt"


def chunk_content(content, max_chars=MAX_CHARS, overlap=OVERLAP):
    """Chunk content into overlapping segments."""
    if len(content) <= 2000:
        return [content]
    chunks = []
    start = 0
    while start < len(content):
        end = min(start + max_chars, len(content))
        chunks.append(content[start:end])
        if end == len(content):
            break
        start = end - overlap
    return chunks


def build_documents():
    documents = []
    for fname in FILES_TO_INDEX:
        fpath = REPO_PATH / fname
        if not fpath.exists():
            print(f"  Skipping (not found): {fname}")
            continue

        content = fpath.read_text(encoding="utf-8", errors="replace")
        file_type = get_file_type(fname)
        chunks = chunk_content(content)

        print(f"  {fname}: {len(content):,} chars → {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            doc_id = hashlib.md5(f"{fname}-{i}".encode()).hexdigest()
            documents.append({
                "id": doc_id,
                "filename": fname,
                "content": chunk,
                "file_type": file_type,
                "chunk_id": i,
            })

    return documents


def upload_documents(documents, auth_headers):
    batch_size = 100
    total_success = 0

    for batch_start in range(0, len(documents), batch_size):
        batch = documents[batch_start : batch_start + batch_size]
        payload = json.dumps({"value": batch}).encode()

        url = (
            f"https://{SEARCH_SERVICE}.search.windows.net"
            f"/indexes/{INDEX_NAME}/docs/index?api-version={API_VERSION}"
        )
        headers = {"Content-Type": "application/json", **auth_headers}

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
                success = sum(1 for v in result.get("value", []) if v.get("status"))
                total_success += success
                print(
                    f"  Batch {batch_start // batch_size + 1}: "
                    f"{success}/{len(batch)} documents indexed"
                )
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ERROR batch {batch_start // batch_size + 1}: {e.code} - {body[:300]}")

    return total_success


def main():
    print(f"Indexing repo files into: {SEARCH_SERVICE}/{INDEX_NAME}")
    print(f"Repo path: {REPO_PATH}\n")

    auth_headers = get_auth_header()

    print("Reading files:")
    documents = build_documents()
    print(f"\nTotal documents: {len(documents)}\n")

    print("Uploading to Azure AI Search:")
    total = upload_documents(documents, auth_headers)

    print(f"\nDone! {total}/{len(documents)} documents indexed successfully.")


if __name__ == "__main__":
    main()
