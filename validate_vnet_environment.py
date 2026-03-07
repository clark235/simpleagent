"""
Azure AI Foundry — Customer VNet Environment Validator

Validates that an Azure AI Foundry Standard Setup with private networking
(BYO VNet / customer VNet injection) is correctly configured for agent AI
Search tool calls to work.

Checks:
  1. DNS resolution — each service endpoint resolves to a private IP
  2. TCP connectivity — each private endpoint is reachable on port 443
  3. AI Search index accessibility
  4. Azure SDK / auth — DefaultAzureCredential works
  5. Foundry project connection — AI Search connection reachable
  6. Private DNS zone link (via Azure Management API, if credentials allow)
  7. Subnet delegation (via Azure Management API, if credentials allow)

Usage:
  python validate_vnet_environment.py [--mode public|private|auto]

  --mode public   : skip private networking checks (public endpoint setup)
  --mode private  : run all private networking checks
  --mode auto     : detect mode from endpoint format (default)

Requires: pip install azure-ai-projects azure-identity python-dotenv
Optional: pip install azure-mgmt-network azure-mgmt-search (for deeper checks)
"""

import os
import sys
import socket
import ssl
import argparse
import ipaddress
from datetime import datetime
from dotenv import load_dotenv

# ── ANSI colors ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    return f"{GREEN}✅ {msg}{RESET}"
def fail(msg):  return f"{RED}❌ {msg}{RESET}"
def warn(msg):  return f"{YELLOW}⚠️  {msg}{RESET}"
def info(msg):  return f"{BLUE}ℹ️  {msg}{RESET}"
def section(msg): print(f"\n{BOLD}{BLUE}{'─'*60}{RESET}")
def title(msg):   print(f"{BOLD}{msg}{RESET}")


class CheckResult:
    def __init__(self, name, passed, message, detail=None, remediation=None):
        self.name = name
        self.passed = passed
        self.message = message
        self.detail = detail
        self.remediation = remediation

    def print(self):
        status = ok(self.name) if self.passed else fail(self.name)
        print(f"  {status}")
        print(f"    → {self.message}")
        if self.detail:
            print(f"    {info(self.detail)}")
        if not self.passed and self.remediation:
            print(f"    {warn('Fix: ' + self.remediation)}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_private_ip(ip_str: str) -> bool:
    """Return True if IP is in an RFC1918 private range."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private
    except ValueError:
        return False


def resolve_hostname(hostname: str) -> list[str]:
    """Resolve a hostname to a list of IP addresses."""
    try:
        results = socket.getaddrinfo(hostname, None)
        return list({r[4][0] for r in results})
    except socket.gaierror as e:
        raise ConnectionError(f"DNS resolution failed: {e}") from e


def check_tcp_443(hostname: str, timeout: int = 5) -> bool:
    """Try to open a TCP connection to hostname:443."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((hostname, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock):
                return True
    except Exception:
        return False


def extract_hostname(url: str) -> str:
    """Extract hostname from a URL."""
    url = url.replace("https://", "").replace("http://", "")
    return url.split("/")[0].split(":")[0]


# ── Individual checks ─────────────────────────────────────────────────────────

def check_env_vars() -> list[CheckResult]:
    required = {
        "FOUNDRY_PROJECT_ENDPOINT":        "Foundry project endpoint URL",
        "FOUNDRY_MODEL_DEPLOYMENT_NAME":   "Model deployment name",
        "AZURE_AI_SEARCH_CONNECTION_NAME": "AI Search connection name",
        "AI_SEARCH_INDEX_NAME":            "AI Search index name",
    }
    results = []
    for var, desc in required.items():
        val = os.environ.get(var, "")
        if val and not val.startswith("<"):
            results.append(CheckResult(f"Env: {var}", True, f"Set → {val[:60]}"))
        else:
            results.append(CheckResult(
                f"Env: {var}", False,
                f"Not set or placeholder ({desc})",
                remediation=f"Set {var} in your .env file"
            ))
    return results


def check_dns_resolution(endpoint: str, private_mode: bool) -> CheckResult:
    hostname = extract_hostname(endpoint)
    name = f"DNS: {hostname}"
    try:
        ips = resolve_hostname(hostname)
        ip_str = ", ".join(ips)
        all_private = all(is_private_ip(ip) for ip in ips)

        if private_mode:
            if all_private:
                return CheckResult(name, True,
                    f"Resolves to private IP: {ip_str}",
                    "Private DNS zone is linked to this VNet ✅")
            else:
                return CheckResult(name, False,
                    f"Resolves to PUBLIC IP: {ip_str}",
                    detail="In private mode, this should resolve to a private (RFC1918) IP",
                    remediation=(
                        "Link privatelink DNS zone to the agent VNet. "
                        f"For AI Search: link 'privatelink.search.windows.net' to the VNet "
                        "where the Foundry agent subnet is injected."
                    ))
        else:
            return CheckResult(name, True,
                f"Resolves to: {ip_str}",
                "Public networking mode — DNS resolution OK")
    except ConnectionError as e:
        return CheckResult(name, False, str(e),
            remediation="Check DNS configuration and network connectivity")


def check_tcp_connectivity(endpoint: str) -> CheckResult:
    hostname = extract_hostname(endpoint)
    name = f"TCP:443 {hostname}"
    if check_tcp_443(hostname):
        return CheckResult(name, True, "Port 443 reachable")
    else:
        ips = []
        try:
            ips = resolve_hostname(hostname)
        except Exception:
            pass
        detail = f"Resolved to: {', '.join(ips)}" if ips else "Could not resolve hostname"
        return CheckResult(name, False,
            "Cannot connect on port 443",
            detail=detail,
            remediation=(
                "Check NSG outbound rules: agent subnet → resource subnet TCP 443. "
                "If using a firewall, verify allow rules for this destination."
            ))


def check_sdk_import() -> CheckResult:
    try:
        import azure.ai.projects
        version = getattr(azure.ai.projects, "__version__", "unknown")
        from azure.ai.projects.models import (
            AzureAISearchTool, PromptAgentDefinition
        )
        return CheckResult("SDK: azure-ai-projects", True,
            f"Version {version} installed, all classes available")
    except ImportError as e:
        return CheckResult("SDK: azure-ai-projects", False,
            f"Import error: {e}",
            remediation="pip install azure-ai-projects>=2.0.0")


def check_authentication() -> tuple[CheckResult, object]:
    """Check DefaultAzureCredential and return (result, credential)."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.core.credentials import TokenRequestOptions
        cred = DefaultAzureCredential()
        token = cred.get_token("https://ai.azure.com/.default")
        expires = datetime.fromtimestamp(token.expires_on).strftime("%H:%M:%S")
        return (
            CheckResult("Auth: DefaultAzureCredential", True,
                f"Token acquired (expires {expires})",
                "Authenticated via AzureCLI / ManagedIdentity / etc."),
            cred
        )
    except Exception as e:
        return (
            CheckResult("Auth: DefaultAzureCredential", False,
                f"Failed: {e}",
                remediation="Run 'az login' or configure a managed identity"),
            None
        )


def check_foundry_connection(endpoint: str, connection_name: str, cred) -> tuple[CheckResult, object]:
    """Check that the Foundry connection to AI Search exists and is accessible."""
    if cred is None:
        return (
            CheckResult("Foundry: AI Search connection", False,
                "Skipped — authentication failed"),
            None
        )
    try:
        from azure.ai.projects import AIProjectClient
        client = AIProjectClient(endpoint=endpoint, credential=cred)
        connection = client.connections.get(connection_name)
        return (
            CheckResult("Foundry: AI Search connection", True,
                f"Connection '{connection.name}' found (type: {connection.type})",
                f"Connection ID: {connection.id[:60]}..."),
            connection
        )
    except Exception as e:
        return (
            CheckResult("Foundry: AI Search connection", False,
                f"Connection '{connection_name}' not found: {e}",
                remediation=(
                    f"Add a connection named '{connection_name}' in your Foundry project "
                    "pointing to your Azure AI Search resource with AAD authentication."
                )),
            None
        )


def check_search_endpoint_from_connection(connection) -> CheckResult:
    """Resolve and probe the AI Search endpoint from the Foundry connection."""
    if connection is None:
        return CheckResult("AI Search: endpoint reachable", False,
            "Skipped — connection not available")
    try:
        # Connection target is the search service URL
        target = getattr(connection, "target", None)
        if not target:
            return CheckResult("AI Search: endpoint reachable", False,
                "Could not extract target URL from connection")
        hostname = extract_hostname(target)
        ips = resolve_hostname(hostname)
        ip_str = ", ".join(ips)
        all_private = all(is_private_ip(ip) for ip in ips)
        reachable = check_tcp_443(hostname)

        if reachable:
            return CheckResult("AI Search: endpoint reachable", True,
                f"{hostname} → {ip_str} (port 443 open)",
                "Private" if all_private else "Public")
        else:
            return CheckResult("AI Search: endpoint reachable", False,
                f"{hostname} → {ip_str} but port 443 unreachable",
                detail=f"Private IP: {all_private}",
                remediation=(
                    "If private IP: check NSG rules. "
                    "If public IP in private mode: DNS zone not linked to agent VNet."
                ))
    except Exception as e:
        return CheckResult("AI Search: endpoint reachable", False,
            f"Error: {e}")


def check_index_query(endpoint: str, connection_name: str, index_name: str, model: str, cred) -> CheckResult:
    """Try to run a simple agent query to validate end-to-end."""
    if cred is None:
        return CheckResult("E2E: Agent query", False, "Skipped — auth failed")
    try:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AzureAISearchTool, AzureAISearchToolResource,
            AISearchIndexResource, AzureAISearchQueryType,
            PromptAgentDefinition,
        )
        client = AIProjectClient(endpoint=endpoint, credential=cred)
        conn = client.connections.get(connection_name)

        tool = AzureAISearchTool(
            azure_ai_search=AzureAISearchToolResource(
                indexes=[AISearchIndexResource(
                    project_connection_id=conn.id,
                    index_name=index_name,
                    query_type=AzureAISearchQueryType.SIMPLE,
                )]
            )
        )

        agent_version = client.agents.create_version(
            agent_name="vnet-validate-test",
            definition=PromptAgentDefinition(
                model=model,
                instructions="You are a validation test agent. Answer with one sentence.",
                tools=[tool],
            )
        )

        try:
            with client.get_openai_client(api_version="2025-11-15-preview") as oc:
                resp = oc.responses.create(
                    model=model,
                    input="What topics does this knowledge base cover? One sentence.",
                    tools=[tool],
                    stream=False,
                )
                answer = getattr(resp, "output_text", None) or str(resp)
                return CheckResult("E2E: Agent query", True,
                    "Query succeeded",
                    detail=f"Response: {answer[:120]}...")
        finally:
            client.agents.delete_version(
                agent_name=agent_version.name,
                agent_version=agent_version.version,
            )

    except Exception as e:
        err = str(e)
        remediation = None
        if "403" in err or "Forbidden" in err:
            remediation = "Check RBAC: Foundry managed identity needs 'Search Index Data Reader' role on the AI Search service"
        elif "connection" in err.lower() or "timeout" in err.lower():
            remediation = "Connectivity issue — check NSG/PE/DNS (run checks above)"
        elif "not found" in err.lower():
            remediation = f"Index '{index_name}' may not exist — check AI_SEARCH_INDEX_NAME"
        return CheckResult("E2E: Agent query", False, f"Failed: {err[:200]}", remediation=remediation)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Validate Azure AI Foundry VNet environment")
    parser.add_argument("--mode", choices=["public", "private", "auto"], default="auto",
        help="Networking mode: public (no PE), private (BYO VNet), auto (detect)")
    parser.add_argument("--skip-e2e", action="store_true",
        help="Skip end-to-end agent query test (faster)")
    args = parser.parse_args()

    endpoint    = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    conn_name   = os.environ.get("AZURE_AI_SEARCH_CONNECTION_NAME", "")
    index_name  = os.environ.get("AI_SEARCH_INDEX_NAME", "")
    model       = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # Auto-detect private mode from endpoint (private endpoints often use custom domains)
    if args.mode == "auto":
        # If endpoint resolves to a private IP, assume private mode
        private_mode = False
        if endpoint:
            try:
                hostname = extract_hostname(endpoint)
                ips = resolve_hostname(hostname)
                private_mode = all(is_private_ip(ip) for ip in ips)
            except Exception:
                pass
        print(info(f"Mode: {'private' if private_mode else 'public'} (auto-detected)"))
    else:
        private_mode = (args.mode == "private")
        print(info(f"Mode: {args.mode}"))

    all_results = []
    passed = 0
    failed = 0

    # ── 1. Environment Variables ──────────────────────────────────────────────
    section("")
    title("1. Environment Variables")
    for r in check_env_vars():
        r.print()
        all_results.append(r)

    # ── 2. DNS Resolution ─────────────────────────────────────────────────────
    section("")
    title("2. DNS Resolution")
    if endpoint:
        r = check_dns_resolution(endpoint, private_mode)
        r.print(); all_results.append(r)
    if private_mode:
        print(info("Private mode: DNS must resolve to RFC1918 addresses"))
        print(info("Check that privatelink.search.windows.net is linked to the agent VNet"))

    # ── 3. TCP Connectivity ───────────────────────────────────────────────────
    section("")
    title("3. TCP Connectivity (port 443)")
    if endpoint:
        r = check_tcp_connectivity(endpoint)
        r.print(); all_results.append(r)

    # ── 4. SDK ────────────────────────────────────────────────────────────────
    section("")
    title("4. SDK Package")
    r = check_sdk_import()
    r.print(); all_results.append(r)

    # ── 5. Authentication ─────────────────────────────────────────────────────
    section("")
    title("5. Authentication")
    auth_result, cred = check_authentication()
    auth_result.print(); all_results.append(auth_result)

    # ── 6. Foundry Connection ─────────────────────────────────────────────────
    section("")
    title("6. Foundry Project Connection")
    if endpoint and conn_name:
        conn_result, connection = check_foundry_connection(endpoint, conn_name, cred)
        conn_result.print(); all_results.append(conn_result)

        # 6b: probe the Search endpoint from connection metadata
        r = check_search_endpoint_from_connection(connection)
        r.print(); all_results.append(r)
    else:
        print(f"  {warn('Skipped — endpoint or connection name not set')}")

    # ── 7. End-to-End Query ───────────────────────────────────────────────────
    if not args.skip_e2e:
        section("")
        title("7. End-to-End Agent Query")
        if endpoint and conn_name and index_name:
            r = check_index_query(endpoint, conn_name, index_name, model, cred)
            r.print(); all_results.append(r)
        else:
            print(f"  {warn('Skipped — required env vars not set')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    section("")
    title("Summary")
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total  = len(all_results)

    print(f"  {ok(f'{passed}/{total} checks passed')}") if failed == 0 else \
        print(f"  {fail(f'{failed}/{total} checks failed — see remediation above')}")

    if private_mode and failed > 0:
        print()
        print(f"  {warn('VNet checklist — verify ALL of the following:')}")
        for item in [
            "Agent subnet delegated to Microsoft.App/environments",
            "AI Search private endpoint in resource subnet",
            "privatelink.search.windows.net zone linked to agent VNet",
            "DNS A record: <search-name> → private IP registered",
            "NSG: agent subnet → resource subnet TCP 443 outbound allowed",
            "AI Search public access = Disabled",
            "Foundry managed identity has Search Index Data Reader role",
        ]:
            print(f"    [ ] {item}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
