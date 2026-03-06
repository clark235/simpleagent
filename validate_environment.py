"""
Environment Validation for Azure AI Foundry Agent with AI Search

Validates that the deployment environment is correctly configured by checking
environment variables, DNS resolution, network connectivity, authentication,
and project connections.

Usage: python validate_environment.py
"""

import os
import sys
import socket
import ssl
from urllib.parse import urlparse

from dotenv import load_dotenv


def check_mark():
    return "\u2705"  # green checkmark


def cross_mark():
    return "\u274C"  # red cross


def warn_mark():
    return "\u26A0\uFE0F"  # warning


class ValidationResult:
    def __init__(self, name, passed, message, remediation=None):
        self.name = name
        self.passed = passed
        self.message = message
        self.remediation = remediation

    def __str__(self):
        icon = check_mark() if self.passed else cross_mark()
        line = f"{icon} {self.name}: {self.message}"
        if not self.passed and self.remediation:
            line += f"\n   Remediation: {self.remediation}"
        return line


def check_env_vars():
    """Check that all required environment variables are set."""
    results = []
    required = {
        "FOUNDRY_PROJECT_ENDPOINT": "Azure AI Foundry project endpoint URL",
        "FOUNDRY_MODEL_DEPLOYMENT_NAME": "Model deployment name (e.g., gpt-4o)",
        "AZURE_AI_SEARCH_CONNECTION_NAME": "AI Search connection name in Foundry project",
        "AI_SEARCH_INDEX_NAME": "AI Search index name to query",
    }

    for var, description in required.items():
        value = os.environ.get(var)
        if value and not value.startswith("<"):
            results.append(ValidationResult(
                f"Env: {var}",
                True,
                f"Set ({description})",
            ))
        elif value and value.startswith("<"):
            results.append(ValidationResult(
                f"Env: {var}",
                False,
                f"Still has placeholder value",
                f"Update {var} in your .env file with your actual value. {description}.",
            ))
        else:
            results.append(ValidationResult(
                f"Env: {var}",
                False,
                f"Not set ({description})",
                f"Add {var}=<value> to your .env file. {description}.",
            ))

    return results


def check_dns(endpoint):
    """Resolve the AI Services hostname from the project endpoint."""
    try:
        parsed = urlparse(endpoint)
        hostname = parsed.hostname
        if not hostname:
            return ValidationResult(
                "DNS: AI Services endpoint",
                False,
                f"Could not parse hostname from endpoint: {endpoint}",
                "Verify FOUNDRY_PROJECT_ENDPOINT format: https://<account>.services.ai.azure.com/api/projects/<project>",
            )

        ip = socket.gethostbyname(hostname)
        is_private = ip.startswith("10.") or ip.startswith("172.") or ip.startswith("192.168.")
        extra = f" (private IP - private endpoint detected)" if is_private else ""
        return ValidationResult(
            "DNS: AI Services endpoint",
            True,
            f"{hostname} -> {ip}{extra}",
        )
    except socket.gaierror as e:
        return ValidationResult(
            "DNS: AI Services endpoint",
            False,
            f"Could not resolve {hostname}: {e}",
            "Check DNS configuration. For private endpoints, ensure your DNS can resolve "
            "*.services.ai.azure.com to the private IP. You may need a Private DNS Zone "
            "or conditional forwarder.",
        )


def check_network(endpoint):
    """Test HTTPS connectivity to the AI Services endpoint."""
    try:
        parsed = urlparse(endpoint)
        hostname = parsed.hostname
        if not hostname:
            return ValidationResult(
                "Network: HTTPS connectivity",
                False,
                "Could not parse hostname from endpoint",
            )

        # Try connecting on port 443
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                subject = dict(x[0] for x in cert.get("subject", []))
                cn = subject.get("commonName", "unknown")
                return ValidationResult(
                    "Network: HTTPS connectivity",
                    True,
                    f"Connected to {hostname}:443 (cert CN: {cn})",
                )
    except socket.timeout:
        return ValidationResult(
            "Network: HTTPS connectivity",
            False,
            f"Connection to {hostname}:443 timed out",
            "Check network connectivity. If using private endpoints, ensure you are "
            "connected to the VNet (e.g., via VPN or from a VM in the VNet).",
        )
    except ssl.SSLError as e:
        return ValidationResult(
            "Network: HTTPS connectivity",
            False,
            f"SSL error connecting to {hostname}: {e}",
            "Check TLS/SSL configuration. Ensure no proxy is intercepting HTTPS traffic.",
        )
    except Exception as e:
        return ValidationResult(
            "Network: HTTPS connectivity",
            False,
            f"Could not connect to {hostname}:443: {e}",
            "Check firewall rules and network security groups. Ensure outbound HTTPS "
            "(port 443) is allowed to Azure services.",
        )


def check_authentication():
    """Verify DefaultAzureCredential can acquire a token."""
    try:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        if token and token.token:
            return ValidationResult(
                "Auth: DefaultAzureCredential",
                True,
                "Successfully acquired token for cognitiveservices.azure.com",
            )
        else:
            return ValidationResult(
                "Auth: DefaultAzureCredential",
                False,
                "Token acquisition returned empty token",
                "Run 'az login' to authenticate, or ensure managed identity is configured.",
            )
    except ImportError:
        return ValidationResult(
            "Auth: DefaultAzureCredential",
            False,
            "azure-identity package not installed",
            "Run: pip install 'azure-ai-projects>=2.0.0' azure-identity python-dotenv",
        )
    except Exception as e:
        return ValidationResult(
            "Auth: DefaultAzureCredential",
            False,
            f"Authentication failed: {e}",
            "Run 'az login' to authenticate with Azure CLI, or ensure a managed identity "
            "is assigned. For local development, also try 'az account set -s <subscription-id>'.",
        )


def check_project_connection(endpoint, connection_name):
    """Verify the AI Search connection exists in the Foundry project."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        credential = DefaultAzureCredential()
        client = AIProjectClient(endpoint=endpoint, credential=credential)

        # Try to get the specific connection
        try:
            connection = client.connections.get(connection_name)
            return ValidationResult(
                "Project: AI Search connection",
                True,
                f"Connection '{connection.name}' found (type: {connection.type})",
            )
        except Exception as e:
            error_msg = str(e)
            result = ValidationResult(
                "Project: AI Search connection",
                False,
                f"Connection '{connection_name}' not found: {error_msg}",
                f"Verify the connection name in Azure AI Foundry portal > Project > "
                f"Settings > Connected resources. Check RBAC: you need at least "
                f"'Azure AI Developer' role on the project.",
            )
            return result

    except ImportError:
        return ValidationResult(
            "Project: AI Search connection",
            False,
            "azure-ai-projects package not installed or wrong version",
            "Run: pip install azure-ai-projects>=2.0.0 (stable -- no --pre needed)",
        )
    except Exception as e:
        return ValidationResult(
            "Project: AI Search connection",
            False,
            f"Could not connect to project: {e}",
            "Verify FOUNDRY_PROJECT_ENDPOINT and ensure you have 'Azure AI Developer' "
            "or 'Contributor' role on the AI Foundry project.",
        )


def list_connections(endpoint):
    """List all available connections in the project."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        credential = DefaultAzureCredential()
        client = AIProjectClient(endpoint=endpoint, credential=credential)

        connections = list(client.connections.list())
        if connections:
            print(f"\n{warn_mark()}  Available connections in project:")
            for conn in connections:
                print(f"   - {conn.name} (type: {conn.type})")
        else:
            print(f"\n{warn_mark()}  No connections found in project.")
        print()

    except Exception as e:
        print(f"\n{warn_mark()}  Could not list connections: {e}\n")


def check_package_version():
    """Check that azure-ai-projects is installed with the correct version."""
    try:
        import azure.ai.projects
        version = getattr(azure.ai.projects, "__version__", "unknown")

        # Check if Responses API classes are available (2.0.0 stable uses AzureAISearchTool)
        try:
            from azure.ai.projects.models import AzureAISearchTool, PromptAgentDefinition
            return ValidationResult(
                "Package: azure-ai-projects",
                True,
                f"Version {version} (Responses API classes available)",
            )
        except ImportError:
            return ValidationResult(
                "Package: azure-ai-projects",
                False,
                f"Version {version} installed, but Responses API classes not found",
                'Run: pip install azure-ai-projects>=2.0.0',
            )
    except ImportError:
        return ValidationResult(
            "Package: azure-ai-projects",
            False,
            "Package not installed",
            "Run: pip install azure-ai-projects>=2.0.0",
        )


def main():
    load_dotenv()

    print("=" * 60)
    print("Azure AI Foundry Agent - Environment Validation")
    print("=" * 60)
    print()

    all_results = []

    # 1. Check package version
    print("Checking package version...")
    result = check_package_version()
    all_results.append(result)
    print(f"  {result}")
    print()

    # 2. Check environment variables
    print("Checking environment variables...")
    env_results = check_env_vars()
    all_results.extend(env_results)
    for r in env_results:
        print(f"  {r}")
    print()

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    connection_name = os.environ.get("AZURE_AI_SEARCH_CONNECTION_NAME", "")

    # Only proceed with network checks if endpoint is set
    if endpoint and not endpoint.startswith("<"):
        # 3. DNS resolution
        print("Checking DNS resolution...")
        result = check_dns(endpoint)
        all_results.append(result)
        print(f"  {result}")
        print()

        # 4. Network connectivity
        print("Checking network connectivity...")
        result = check_network(endpoint)
        all_results.append(result)
        print(f"  {result}")
        print()

        # 5. Authentication
        print("Checking authentication...")
        result = check_authentication()
        all_results.append(result)
        print(f"  {result}")
        print()

        # 6. Project connection (only if auth and connection name are available)
        if connection_name and not connection_name.startswith("<"):
            print("Checking project connection...")
            result = check_project_connection(endpoint, connection_name)
            all_results.append(result)
            print(f"  {result}")

            # List all connections if the specific one wasn't found
            if not result.passed:
                list_connections(endpoint)
            else:
                print()
        else:
            print("Skipping project connection check (AZURE_AI_SEARCH_CONNECTION_NAME not set).\n")
    else:
        print("Skipping network/auth/connection checks (FOUNDRY_PROJECT_ENDPOINT not set).\n")

    # Summary
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total = len(all_results)

    print("=" * 60)
    print(f"Results: {passed}/{total} checks passed", end="")
    if failed > 0:
        print(f", {failed} failed")
    else:
        print()
    print("=" * 60)

    if failed > 0:
        print(f"\n{cross_mark()} Some checks failed. Review the remediation steps above.")
        sys.exit(1)
    else:
        print(f"\n{check_mark()} All checks passed! You are ready to run main.py.")
        sys.exit(0)


if __name__ == "__main__":
    main()
