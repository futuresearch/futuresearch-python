import json
import re
import tomllib

import httpx
import jsonschema
import pytest

import futuresearch


def test_version_consistency(pytestconfig: pytest.Config):
    """Check that version is consistent across all files that contain the SDK version."""
    root = pytestconfig.rootpath

    pyproject_path = root / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)
    pyproject_version = pyproject["project"]["version"]

    # Collect all version sources with labels
    sources: dict[str, str] = {}

    with open(root / ".claude-plugin" / "plugin.json") as f:
        sources[".claude-plugin/plugin.json version"] = json.load(f)["version"]

    with open(root / ".claude-plugin" / "marketplace.json") as f:
        sources[".claude-plugin/marketplace.json plugins[0].version"] = json.load(f)[
            "plugins"
        ][0]["version"]

    with open(root / "gemini-extension.json") as f:
        sources["gemini-extension.json version"] = json.load(f)["version"]

    with open(root / "futuresearch-mcp" / "pyproject.toml", "rb") as f:
        sources["futuresearch-mcp/pyproject.toml version"] = tomllib.load(f)["project"][
            "version"
        ]

    with open(root / "futuresearch-mcp" / "server.json") as f:
        server_json = json.load(f)
    sources["futuresearch-mcp/server.json version"] = server_json["version"]
    sources["futuresearch-mcp/server.json packages[0].version"] = server_json[
        "packages"
    ][0]["version"]

    with open(root / "futuresearch-mcp" / "manifest.json") as f:
        sources["futuresearch-mcp/manifest.json version"] = json.load(f)["version"]

    citation_text = (root / "CITATION.cff").read_text()
    citation_match = re.search(r"^version:\s*(.+)$", citation_text, re.MULTILINE)
    assert citation_match, "Could not find version in CITATION.cff"
    sources["CITATION.cff version"] = citation_match.group(1).strip()

    readme_text = (root / "README.md").read_text()
    bibtex_match = re.search(
        r"@software\{futuresearch,.*?version\s*=\s*\{(.+?)\}", readme_text, re.DOTALL
    )
    assert bibtex_match, "Could not find BibTeX version in README.md"
    sources["README.md BibTeX version"] = bibtex_match.group(1)

    with open(root / "stubs" / "everyrow" / "pyproject.toml", "rb") as f:
        sources["stubs/everyrow/pyproject.toml version"] = tomllib.load(f)["project"][
            "version"
        ]

    with open(root / "stubs" / "everyrow-mcp" / "pyproject.toml", "rb") as f:
        sources["stubs/everyrow-mcp/pyproject.toml version"] = tomllib.load(f)[
            "project"
        ]["version"]

    sources["futuresearch.__version__"] = futuresearch.__version__

    mismatches = {label: v for label, v in sources.items() if v != pyproject_version}
    assert not mismatches, (
        f"pyproject.toml version is {pyproject_version}, but these differ: {mismatches}"
    )


def test_server_json_schema(pytestconfig: pytest.Config):
    """Validate futuresearch-mcp/server.json against its JSON schema."""
    root = pytestconfig.rootpath

    server_json_path = root / "futuresearch-mcp" / "server.json"
    with open(server_json_path) as f:
        server_json = json.load(f)

    schema_url = server_json.get("$schema")
    assert schema_url, "server.json must have a $schema field"

    response = httpx.get(schema_url)
    response.raise_for_status()
    schema = response.json()

    jsonschema.validate(instance=server_json, schema=schema)
