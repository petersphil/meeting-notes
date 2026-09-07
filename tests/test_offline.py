import pytest
from meeting_notes.offline import OfflinePolicyError, assert_local_url
def test_local_url_allowed():
    assert_local_url("http://localhost:11434"); assert_local_url("http://127.0.0.1:11434")
def test_remote_url_rejected():
    with pytest.raises(OfflinePolicyError): assert_local_url("https://example.com")
