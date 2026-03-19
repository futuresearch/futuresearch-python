"""Integration tests for the MCP server.

These tests make real API calls to FutureSearch and require FUTURESEARCH_API_KEY to be set.
Run with: pytest tests/test_integration.py -v -s

Note: These tests take time and cost money (on the order of 1 minute and $0.10 per test
case), so they are skipped by default. Set RUN_INTEGRATION_TESTS=1 to run them.
"""

import json
import os
import re
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from futuresearch_mcp.models import (
    AgentInput,
    CancelInput,
    DedupeInput,
    MergeInput,
    ProgressInput,
    RankInput,
    SingleAgentInput,
    StdioResultsInput,
    UploadDataInput,
)
from futuresearch_mcp.tools import (
    futuresearch_agent,
    futuresearch_cancel,
    futuresearch_dedupe,
    futuresearch_merge,
    futuresearch_progress,
    futuresearch_rank,
    futuresearch_results_stdio,
    futuresearch_single_agent,
    futuresearch_upload_data,
)
from tests.conftest import make_test_context
from tests.test_stdio_content import assert_stdio_clean

# Skip all tests in this module unless environment variable is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests are skipped by default. Set RUN_INTEGRATION_TESTS=1 to run.",
)

# CSV fixtures are defined in conftest.py


@pytest.fixture
def real_ctx(futuresearch_client):
    """Create a test Context wrapping the real FutureSearch client."""
    return make_test_context(futuresearch_client)


async def poll_until_complete(task_id: str, ctx, max_polls: int = 60) -> str:
    """Poll futuresearch_progress until task completes or fails.

    Returns the final human-readable status text from futuresearch_progress.
    """
    for _ in range(max_polls):
        result = await futuresearch_progress(ProgressInput(task_id=task_id), ctx)
        assert_stdio_clean(result, tool_name="futuresearch_progress")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        text = result[0].text
        print(f"  Progress: {text.splitlines()[0]}")

        if "Completed:" in text or "futuresearch_results" in text:
            return text
        if "failed" in text.lower() or "revoked" in text.lower():
            raise RuntimeError(f"Task failed: {text}")
        # Continue polling

    raise TimeoutError(f"Task {task_id} did not complete within {max_polls} polls")


def extract_task_id(submit_text: str) -> str:
    """Extract task_id from submit tool response (human-readable TextContent)."""
    match = re.search(r"Task ID: ([a-f0-9-]+)", submit_text)
    if not match:
        raise ValueError(f"Could not extract task_id from: {submit_text}")
    return match.group(1)


# ── Inline data fixtures ──────────────────────────────────────

COMPANIES_DATA = [
    {"name": "TechStart", "industry": "Software", "size": 50},
    {"name": "AILabs", "industry": "AI/ML", "size": 30},
    {"name": "DataFlow", "industry": "Data", "size": 100},
    {"name": "CloudNine", "industry": "Cloud", "size": 75},
    {"name": "OldBank", "industry": "Finance", "size": 5000},
]

CONTACTS_DATA = [
    {"name": "John Smith", "email": "john.smith@acme.com", "company": "Acme Corp"},
    {"name": "J. Smith", "email": "jsmith@acme.com", "company": "Acme Corporation"},
    {"name": "Alexandra Butoi", "email": "a.butoi@tech.io", "company": "TechStart"},
    {"name": "A. Butoi", "email": "alexandra@techstart.io", "company": "TechStart Inc"},
    {"name": "Mike Johnson", "email": "mike@startup.co", "company": "StartupCo"},
]

PRODUCTS_DATA = [
    {"product_name": "Photoshop", "category": "Design", "vendor": "Adobe Systems"},
    {"product_name": "VSCode", "category": "Development", "vendor": "Microsoft"},
    {"product_name": "Slack", "category": "Communication", "vendor": "Salesforce"},
]

SUPPLIERS_DATA = [
    {"company_name": "Adobe Inc", "approved": True},
    {"company_name": "Microsoft Corporation", "approved": True},
    {"company_name": "Salesforce Inc", "approved": True},
]


class TestRankIntegration:
    """Integration tests for the rank tool."""

    @pytest.mark.asyncio
    async def test_rank_companies(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Test ranking companies by AI/ML maturity."""
        # 1. Submit the task
        params = RankInput(
            task="Score 0-10 by AI/ML adoption maturity and innovation focus. Higher score = more AI focused.",
            data=COMPANIES_DATA,
            field_name="ai_score",
            field_type="float",
            ascending_order=False,  # Highest first
        )

        result = await futuresearch_rank(params, real_ctx)
        assert_stdio_clean(result, tool_name="futuresearch_rank")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id, real_ctx)

        # 3. Retrieve results
        output_file = tmp_path / "ranked_companies.csv"
        results = await futuresearch_results_stdio(
            StdioResultsInput(task_id=task_id, output_path=str(output_file)), real_ctx
        )
        assert_stdio_clean(results, tool_name="futuresearch_results")
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print("\nRank result:")
        print(output_df)

        assert len(output_df) == 5
        assert "ai_score" in output_df.columns


class TestDedupeIntegration:
    """Integration tests for the dedupe tool."""

    @pytest.mark.asyncio
    async def test_dedupe_contacts(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Test deduplicating contacts."""
        # 1. Submit the task
        params = DedupeInput(
            equivalence_relation="""
                Two rows are duplicates if they represent the same person.
                Consider name abbreviations (J. Smith = John Smith),
                and company name variations (Acme Corp = Acme Corporation).
            """,
            data=CONTACTS_DATA,
        )

        result = await futuresearch_dedupe(params, real_ctx)
        assert_stdio_clean(result, tool_name="futuresearch_dedupe")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id, real_ctx)

        # 3. Retrieve results
        output_file = tmp_path / "deduped_contacts.csv"
        results = await futuresearch_results_stdio(
            StdioResultsInput(task_id=task_id, output_path=str(output_file)), real_ctx
        )
        assert_stdio_clean(results, tool_name="futuresearch_results")
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print(f"\nDedupe result: {len(output_df)} rows")
        print(output_df)

        # Dedupe returns all rows with a 'selected' column marking representatives
        if "selected" in output_df.columns:
            selected_df = output_df[output_df["selected"]]
            print(f"Selected representatives: {len(selected_df)}")
            # We expect 3 unique people (John/J. Smith, Alexandra/A. Butoi, Mike Johnson)
            assert len(selected_df) == 3
        else:
            # If no selected column, just verify output exists
            assert len(output_df) > 0


class TestMergeIntegration:
    """Integration tests for the merge tool."""

    @pytest.mark.asyncio
    async def test_merge_products_suppliers(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Test merging products with suppliers."""
        # 1. Submit the task
        params = MergeInput(
            task="""
                Match each product to its parent company in the suppliers list.
                Photoshop is made by Adobe, VSCode by Microsoft, Slack by Salesforce.
            """,
            left_data=PRODUCTS_DATA,
            right_data=SUPPLIERS_DATA,
        )

        result = await futuresearch_merge(params, real_ctx)
        assert_stdio_clean(result, tool_name="futuresearch_merge")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id, real_ctx)

        # 3. Retrieve results
        output_file = tmp_path / "merged_products.csv"
        results = await futuresearch_results_stdio(
            StdioResultsInput(task_id=task_id, output_path=str(output_file)), real_ctx
        )
        assert_stdio_clean(results, tool_name="futuresearch_results")
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print("\nMerge result:")
        print(output_df)

        # Should have merged data from both tables
        assert len(output_df) >= 1


class TestAgentIntegration:
    """Integration tests for the agent tool."""

    @pytest.mark.asyncio
    async def test_agent_company_research(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Test agent researching companies."""
        # 1. Submit the task
        params = AgentInput(
            task="Find the company's headquarters city and approximate employee count.",
            data=[
                {"name": "Anthropic"},
                {"name": "OpenAI"},
            ],
            response_schema={
                "properties": {
                    "headquarters": {
                        "type": "string",
                        "description": "City where HQ is located",
                    },
                    "employees": {
                        "type": "string",
                        "description": "Approximate employee count",
                    },
                },
                "required": ["headquarters"],
            },
        )

        result = await futuresearch_agent(params, real_ctx)
        assert_stdio_clean(result, tool_name="futuresearch_agent")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id, real_ctx)

        # 3. Retrieve results
        output_file = tmp_path / "agent_companies.csv"
        results = await futuresearch_results_stdio(
            StdioResultsInput(task_id=task_id, output_path=str(output_file)), real_ctx
        )
        assert_stdio_clean(results, tool_name="futuresearch_results")
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print("\nAgent result:")
        print(output_df)

        assert len(output_df) == 2
        # Should have research results
        assert "headquarters" in output_df.columns or "answer" in output_df.columns


class TestSingleAgentIntegration:
    """Integration tests for the single agent tool."""

    @pytest.mark.asyncio
    async def test_single_agent_basic(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Test single agent researching one question."""
        # 1. Submit the task
        params = SingleAgentInput(
            task="Find the current CEO and headquarters city of this company.",
            input_data={"company": "Anthropic"},
            response_schema={
                "properties": {
                    "ceo": {
                        "type": "string",
                        "description": "Name of the current CEO",
                    },
                    "headquarters": {
                        "type": "string",
                        "description": "City where HQ is located",
                    },
                },
                "required": ["ceo", "headquarters"],
            },
        )

        result = await futuresearch_single_agent(params, real_ctx)
        assert_stdio_clean(result, tool_name="futuresearch_single_agent")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id, real_ctx)

        # 3. Retrieve results
        output_file = tmp_path / "single_agent_result.csv"
        results = await futuresearch_results_stdio(
            StdioResultsInput(task_id=task_id, output_path=str(output_file)), real_ctx
        )
        assert_stdio_clean(results, tool_name="futuresearch_results")
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print("\nSingle agent result:")
        print(output_df)

        assert len(output_df) == 1
        assert "ceo" in output_df.columns or "answer" in output_df.columns

    @pytest.mark.asyncio
    async def test_single_agent_no_input_data(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Test single agent with no input_data (pure question)."""
        params = SingleAgentInput(
            task="What is the current market cap of Apple Inc?",
        )

        result = await futuresearch_single_agent(params, real_ctx)
        assert_stdio_clean(result, tool_name="futuresearch_single_agent")
        assert len(result) == 1, f"Stdio should return 1 item, got {len(result)}"
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id, real_ctx)

        # 3. Retrieve results
        output_file = tmp_path / "single_agent_no_input.csv"
        results = await futuresearch_results_stdio(
            StdioResultsInput(task_id=task_id, output_path=str(output_file)), real_ctx
        )
        assert_stdio_clean(results, tool_name="futuresearch_results")
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print("\nSingle agent (no input) result:")
        print(output_df)

        assert len(output_df) == 1


class TestArtifactReuseIntegration:
    """Test that artifact_id from upload_data can be reused by tools."""

    @pytest.mark.asyncio
    async def test_upload_then_rank_with_artifact(
        self,
        real_ctx,
        tmp_path: Path,
    ):
        """Upload data once, then use the artifact_id in rank."""
        # 1. Upload
        csv_file = tmp_path / "companies.csv"
        pd.DataFrame(COMPANIES_DATA).to_csv(csv_file, index=False)

        upload_result = await futuresearch_upload_data(
            UploadDataInput(source=str(csv_file)), real_ctx
        )
        artifact_id = json.loads(upload_result[0].text)["artifact_id"]
        print(f"\nUploaded artifact: {artifact_id}")

        # 2. Rank with the artifact
        rank_result = await futuresearch_rank(
            RankInput(
                task="Score 0-10 by AI/ML focus.",
                artifact_id=artifact_id,
                field_name="ai_score",
                field_type="float",
            ),
            real_ctx,
        )
        rank_task_id = extract_task_id(rank_result[0].text)
        await poll_until_complete(rank_task_id, real_ctx)

        rank_output = tmp_path / "ranked.csv"
        await futuresearch_results_stdio(
            StdioResultsInput(task_id=rank_task_id, output_path=str(rank_output)),
            real_ctx,
        )
        rank_df = pd.read_csv(rank_output)
        print(f"Rank result: {len(rank_df)} rows")
        assert len(rank_df) == 5
        assert "ai_score" in rank_df.columns


class TestUrlUploadIntegration:
    """Test uploading data from a public URL."""

    @pytest.mark.asyncio
    async def test_upload_from_url(
        self,
        real_ctx,
    ):
        """Upload a CSV from a public URL, then use the artifact_id."""
        # Use a small public CSV — GitHub raw content
        url = "https://raw.githubusercontent.com/datasets/country-list/master/data.csv"

        upload_result = await futuresearch_upload_data(
            UploadDataInput(source=url), real_ctx
        )
        assert_stdio_clean(upload_result, tool_name="futuresearch_upload_data")
        upload_response = json.loads(upload_result[0].text)
        print(f"\nURL upload result: {upload_response}")

        assert upload_response["rows"] > 0
        assert "artifact_id" in upload_response
        assert "Name" in upload_response["columns"] or "name" in [
            c.lower() for c in upload_response["columns"]
        ]


class TestCancelIntegration:
    """Test cancelling a running task."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(
        self,
        real_ctx,
    ):
        """Submit a task, immediately cancel it, verify cancellation."""
        # 1. Submit a slow task (agent with many rows)
        result = await futuresearch_agent(
            AgentInput(
                task="Find the headquarters city of this company.",
                data=[
                    {"name": "Anthropic"},
                    {"name": "OpenAI"},
                    {"name": "Google"},
                    {"name": "Meta"},
                    {"name": "Apple"},
                ],
            ),
            real_ctx,
        )
        task_id = extract_task_id(result[0].text)
        print(f"\nSubmitted task: {task_id}")

        # 2. Cancel immediately
        cancel_result = await futuresearch_cancel(
            CancelInput(task_id=task_id), real_ctx
        )
        cancel_text = cancel_result[0].text
        print(f"Cancel result: {cancel_text}")
        assert "cancelled" in cancel_text.lower() or "cancel" in cancel_text.lower()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(
        self,
        real_ctx,
    ):
        """Cancel a fake task_id — should get a graceful error, not a crash."""
        cancel_result = await futuresearch_cancel(
            CancelInput(task_id="00000000-0000-0000-0000-000000000000"), real_ctx
        )
        cancel_text = cancel_result[0].text
        print(f"Cancel nonexistent result: {cancel_text}")
        # Should return an error message, not crash
        assert len(cancel_result) == 1


class TestErrorPathsIntegration:
    """Test that invalid inputs produce clear errors, not 500s."""

    def test_merge_mismatched_inputs_rejected(self):
        """Merge with only one side provided is rejected."""
        with pytest.raises(ValidationError):
            MergeInput(
                task="test",
                left_data=[{"a": 1}],
                # right side missing
            )
