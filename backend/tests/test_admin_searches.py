# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.api.v1.admin import _is_test_email


def test_test_email_classification():
    assert _is_test_email("smoke-1781504778@example.com")  # smoke-test accounts
    assert _is_test_email("anyone@xcape.test")
    assert _is_test_email("APPLYTEST+1@EXAMPLE.COM")  # case-insensitive
    assert not _is_test_email("harley@athenadecisions.com")  # real users kept
    assert not _is_test_email(None)
