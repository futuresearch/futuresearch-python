"""Integration tests for the MCP server.

These tests make real API calls to everyrow and require EVERYROW_API_KEY to be set.
Run with: pytest tests/test_integration.py -v -s

Note: These tests take time and cost money (on the order of 1 minute and $0.10 per test
case), so they are skipped by default. Set RUN_INTEGRATION_TESTS=1 to run them.
"""

import os
import re
from pathlib import Path

import pandas as pd
import pytest
from everyrow.generated.client import AuthenticatedClient

from everyrow_mcp.server import (
    AgentInput,
    DedupeInput,
    MergeInput,
    ProgressInput,
    RankInput,
    ResultsInput,
    ScreenInput,
    SingleAgentInput,
    everyrow_agent,
    everyrow_dedupe,
    everyrow_merge,
    everyrow_progress,
    everyrow_rank,
    everyrow_results,
    everyrow_screen,
    everyrow_single_agent,
)

# Skip all tests in this module unless environment variable is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests are skipped by default. Set RUN_INTEGRATION_TESTS=1 to run.",
)

# CSV fixtures are defined in conftest.py


async def poll_until_complete(task_id: str, max_polls: int = 30) -> str:
    """Poll everyrow_progress until task completes or fails.

    Returns the final status text from everyrow_progress.
    """
    for _ in range(max_polls):
        result = await everyrow_progress(ProgressInput(task_id=task_id))
        text = result[0].text
        print(f"  Progress: {text.splitlines()[0]}")

        if "Completed:" in text or "everyrow_results" in text:
            return text
        if "failed" in text.lower() or "revoked" in text.lower():
            raise RuntimeError(f"Task failed: {text}")
        # Continue polling

    raise TimeoutError(f"Task {task_id} did not complete within {max_polls} polls")


def extract_task_id(submit_text: str) -> str:
    """Extract task_id from submit tool response."""
    match = re.search(r"Task ID: ([a-f0-9-]+)", submit_text)
    if not match:
        raise ValueError(f"Could not extract task_id from: {submit_text}")
    return match.group(1)


class TestScreenIntegration:
    """Integration tests for the screen tool."""

    @pytest.mark.asyncio
    async def test_screen_jobs(
        self,
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
        jobs_csv: Path,
        tmp_path: Path,
    ):
        """Test screening jobs for remote senior roles."""
        # 1. Submit the task
        params = ScreenInput(
            task="""
                Filter for positions that meet ALL criteria:
                1. Remote-friendly (location says Remote)
                2. Senior-level (title includes Senior, Staff, Principal, or Lead)
                3. Salary disclosed (specific dollar amount, not "Competitive")
            """,
            input_csv=str(jobs_csv),
        )

        result = await everyrow_screen(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "screened_jobs.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print(f"\nScreen result: {len(output_df)} rows")
        print(output_df)

        # We expect Airtable and Descript to pass (remote, senior, salary disclosed)
        # Vercel fails (salary not disclosed), Notion fails (not remote), Linear fails (not senior)
        assert len(output_df) <= 3  # At most 3 should pass


class TestRankIntegration:
    """Integration tests for the rank tool."""

    @pytest.mark.asyncio
    async def test_rank_companies(
        self,
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
        companies_csv: Path,
        tmp_path: Path,
    ):
        """Test ranking companies by AI/ML maturity."""
        # 1. Submit the task
        params = RankInput(
            task="Score 0-10 by AI/ML adoption maturity and innovation focus. Higher score = more AI focused.",
            input_csv=str(companies_csv),
            field_name="ai_score",
            field_type="float",
            ascending_order=False,  # Highest first
        )

        result = await everyrow_rank(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "ranked_companies.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
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
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
        contacts_csv: Path,
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
            input_csv=str(contacts_csv),
        )

        result = await everyrow_dedupe(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "deduped_contacts.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
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
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
        products_csv: Path,
        suppliers_csv: Path,
        tmp_path: Path,
    ):
        """Test merging products with suppliers."""
        # 1. Submit the task
        params = MergeInput(
            task="""
                Match each product to its parent company in the suppliers list.
                Photoshop is made by Adobe, VSCode by Microsoft, Slack by Salesforce.
            """,
            left_csv=str(products_csv),
            right_csv=str(suppliers_csv),
        )

        result = await everyrow_merge(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "merged_products.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
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
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
        tmp_path: Path,
    ):
        """Test agent researching companies."""
        # Create input CSV with 2 companies to minimize cost
        df = pd.DataFrame(
            [
                {"name": "Anthropic"},
                {"name": "OpenAI"},
            ]
        )
        input_csv = tmp_path / "companies_to_research.csv"
        df.to_csv(input_csv, index=False)

        # 1. Submit the task
        params = AgentInput(
            task="Find the company's headquarters city and approximate employee count.",
            input_csv=str(input_csv),
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

        result = await everyrow_agent(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "agent_companies.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
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
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
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

        result = await everyrow_single_agent(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "single_agent_result.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
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
        everyrow_client: AuthenticatedClient,  # noqa: ARG002
        tmp_path: Path,
    ):
        """Test single agent with no input_data (pure question)."""
        params = SingleAgentInput(
            task="What is the current market cap of Apple Inc?",
        )

        result = await everyrow_single_agent(params)
        submit_text = result[0].text
        print(f"\nSubmit result: {submit_text}")

        task_id = extract_task_id(submit_text)

        # 2. Poll until complete
        await poll_until_complete(task_id)

        # 3. Retrieve results
        output_file = tmp_path / "single_agent_no_input.csv"
        results = await everyrow_results(
            ResultsInput(task_id=task_id, output_path=str(output_file))
        )
        print(f"Results: {results[0].text}")

        # 4. Verify output
        assert output_file.exists()
        output_df = pd.read_csv(output_file)
        print("\nSingle agent (no input) result:")
        print(output_df)

        assert len(output_df) == 1
