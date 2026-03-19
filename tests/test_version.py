import json
import tomllib

import httpx
import jsonschema
import pytest

import futuresearch


def test_version_consistency(pytestconfig: pytest.Config):
    """Check that version is consistent across pyproject.toml, plugin.json, gemini-extension.json, marketplace.json, futuresearch-mcp/pyproject.toml, and futuresearch-mcp/server.json."""
    root = pytestconfig.rootpath

    pyproject_path = root / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)
    pyproject_version = pyproject["project"]["version"]

    plugin_json_path = root / ".claude-plugin" / "plugin.json"
    with open(plugin_json_path) as f:
        plugin_json = json.load(f)
    plugin_version = plugin_json["version"]

    gemini_json_path = root / "gemini-extension.json"
    with open(gemini_json_path) as f:
        gemini_json = json.load(f)
    gemini_version = gemini_json["version"]

    marketplace_json_path = root / ".claude-plugin" / "marketplace.json"
    with open(marketplace_json_path) as f:
        marketplace_json = json.load(f)
    marketplace_version = marketplace_json["plugins"][0]["version"]

    mcp_pyproject_path = root / "futuresearch-mcp" / "pyproject.toml"
    with open(mcp_pyproject_path, "rb") as f:
        mcp_pyproject = tomllib.load(f)
    mcp_version = mcp_pyproject["project"]["version"]

    server_json_path = root / "futuresearch-mcp" / "server.json"
    with open(server_json_path) as f:
        server_json = json.load(f)
    server_json_version = server_json["version"]
    server_json_package_version = server_json["packages"][0]["version"]

    manifest_json_path = root / "futuresearch-mcp" / "manifest.json"
    with open(manifest_json_path) as f:
        manifest_json = json.load(f)
    manifest_version = manifest_json["version"]

    assert pyproject_version == plugin_version, (
        f"pyproject.toml version ({pyproject_version}) != plugin.json version ({plugin_version})"
    )
    assert pyproject_version == gemini_version, (
        f"pyproject.toml version ({pyproject_version}) != gemini-extension.json version ({gemini_version})"
    )
    assert pyproject_version == marketplace_version, (
        f"pyproject.toml version ({pyproject_version}) != marketplace.json version ({marketplace_version})"
    )
    assert pyproject_version == mcp_version, (
        f"pyproject.toml version ({pyproject_version}) != futuresearch-mcp/pyproject.toml version ({mcp_version})"
    )
    assert pyproject_version == server_json_version, (
        f"pyproject.toml version ({pyproject_version}) != futuresearch-mcp/server.json version ({server_json_version})"
    )
    assert pyproject_version == server_json_package_version, (
        f"pyproject.toml version ({pyproject_version}) != futuresearch-mcp/server.json packages[0].version ({server_json_package_version})"
    )
    assert pyproject_version == manifest_version, (
        f"pyproject.toml version ({pyproject_version}) != futuresearch-mcp/manifest.json version ({manifest_version})"
    )
    assert pyproject_version == futuresearch.__version__, (
        f"pyproject.toml version ({pyproject_version}) != futuresearch.__version__ ({futuresearch.__version__})"
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
