from meeting_notes_ai.services.governance.policies import evaluate_provider


def test_us_009_ac_1_allowed_provider():
    assert evaluate_provider({"allowed_providers": ["local"]}, "local")["outcome"] == "allowed"


def test_us_009_ac_2_unapproved_provider_is_blocked():
    assert evaluate_provider({"allowed_providers": ["local"]}, "openai")["outcome"] == "blocked"


def test_us_009_ac_3_outage_pauses_without_fallback():
    assert (
        evaluate_provider({"allowed_providers": ["openai", "local"]}, "openai", False)["outcome"]
        == "paused"
    )
