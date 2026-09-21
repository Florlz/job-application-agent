"""Read local n8n Gmail workflows: n8n_fetch.py metadata|bodies request.json."""
import argparse
import json
from pathlib import Path
import urllib.request


def fetch(kind, body):
    if kind == "metadata":
        values = body.get("queries")
    elif kind == "bodies":
        values = body.get("message_ids")
        if isinstance(values, list) and len(values) > 20:
            raise ValueError("At most 20 message ids")
    else:
        raise ValueError("Choose metadata or bodies")
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("Request must contain a nonempty list of strings")
    endpoint = "jobagent-backfill-fetch" if kind == "metadata" else "jobagent-fetch-bodies"
    req = urllib.request.Request("http://localhost:5678/webhook/" + endpoint,
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kind", choices=("metadata", "bodies"))
    p.add_argument("request", type=Path)
    args = p.parse_args()
    print(json.dumps(fetch(args.kind, json.loads(args.request.read_text(encoding="utf-8"))), ensure_ascii=False))
