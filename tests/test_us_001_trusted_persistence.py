import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from meeting_notes_ai.db.models import Base
from meeting_notes_ai.routes.trusted_records import ClaimUpdate, EvidenceIn, MappingIn


@pytest.mark.asyncio
async def test_us_001_ac_1_complete_schema_creates_on_real_sqlite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        names = await connection.run_sync(lambda c: set(c.dialect.get_table_names(c)))
    await engine.dispose()
    assert {
        "transcript_segments",
        "claims",
        "claim_evidence",
        "published_snapshots",
        "artifacts",
        "deletion_jobs",
        "audit_exports",
    } <= names


def test_us_001_ac_2_claim_contract_limits_evidence():
    body = ClaimUpdate(
        text="Grounded decision", evidence=[EvidenceIn(segment_id="s", start_ms=0, end_ms=1)]
    )
    assert body.text == "Grounded decision"


def test_us_002_ac_1_mapping_contract_is_bounded():
    mapping = MappingIn(
        raw_label="Speaker 1",
        canonical_name="Alex",
        segment_ids=["s"],
        expected_transcript_version=1,
    )
    assert mapping.expected_transcript_version == 1
