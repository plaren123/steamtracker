import os
import json
import urllib.request

GIST_TOKEN = os.environ["GIST_TOKEN"]
GIST_ID = os.environ["GIST_ID"]
GIST_FILENAME = "data.json"


def load_data():
    url = f"https://api.github.com/gists/{GIST_ID}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        gist = json.load(resp)
    content = gist["files"][GIST_FILENAME]["content"]
    return json.loads(content)


def save_data(data):
    url = f"https://api.github.com/gists/{GIST_ID}"
    body = json.dumps({
        "files": {GIST_FILENAME: {"content": json.dumps(data)}}
    }).encode()
    req = urllib.request.Request(url, data=body, method="PATCH", headers={
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()
