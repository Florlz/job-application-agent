"""Offline boundary check for the local n8n adapter."""
import io
from unittest.mock import patch
from n8n_fetch import fetch

for kind, body in (("bodies", {"message_ids": []}), ("bodies", {"message_ids": ["x"] * 21}),
                   ("metadata", {"queries": "not a list"}), ("other", {})):
    try:
        fetch(kind, body)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid request accepted")
with patch("urllib.request.urlopen", return_value=io.BytesIO(b'[{"message_id":"test"}]')) as request:
    assert fetch("metadata", {"queries": ["subject:sample"]}) == [{"message_id": "test"}]
    assert request.call_args.args[0].full_url == "http://localhost:5678/webhook/jobagent-backfill-fetch"
print("n8n adapter checks passed")
