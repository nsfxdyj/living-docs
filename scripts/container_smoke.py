"""Exercise database and attachment persistence across container recreation."""

import argparse
import base64
import json
import secrets
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
DOCUMENT_TITLE = "Container persistence smoke"
DOCUMENT_CONTENT = "The database and this document's attachment must survive recreation."


def request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
    expected_status: int = 200,
    timeout: int = 15,
) -> bytes:
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = content_type
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{method} {path} returned {exc.code}, expected {expected_status}: {detail}"
        ) from exc
    if status != expected_status:
        raise RuntimeError(
            f"{method} {path} returned {status}, expected {expected_status}: {body!r}"
        )
    return body


def json_request(base_url: str, path: str, **kwargs) -> dict | list:
    return json.loads(request(base_url, path, **kwargs))


def wait_for_health(base_url: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            health = json_request(
                base_url, "/api/health", expected_status=200, timeout=5
            )
            if health == {"status": "ok"}:
                return
            last_error = f"unexpected health response: {health!r}"
        except (OSError, RuntimeError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Service did not become healthy within {timeout}s: {last_error}")


def upload_png(base_url: str, token: str, document_id: int) -> str:
    boundary = f"living-docs-{uuid.uuid4().hex}"
    multipart = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="smoke.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("ascii") + PNG_BYTES + f"\r\n--{boundary}--\r\n".encode("ascii")
    result = json_request(
        base_url,
        f"/api/documents/{document_id}/attachments",
        method="POST",
        token=token,
        data=multipart,
        content_type=f"multipart/form-data; boundary={boundary}",
        expected_status=201,
    )
    url = result["url"]
    if not url.startswith("/api/attachments/") or not url.endswith(".png"):
        raise RuntimeError(f"Unexpected attachment URL: {url!r}")
    return url


def write_state(base_url: str, state_path: Path) -> None:
    wait_for_health(base_url)
    email = f"container-smoke-{uuid.uuid4().hex}@example.com"
    password = secrets.token_urlsafe(24)
    registration = json_request(
        base_url,
        "/api/auth/register",
        method="POST",
        payload={
            "email": email,
            "password": password,
            "display_name": "Container Smoke",
        },
        expected_status=201,
    )
    token = registration["token"]
    workspaces = json_request(base_url, "/api/workspaces", token=token)
    if not workspaces:
        raise RuntimeError("Registration did not create a default workspace")
    document = json_request(
        base_url,
        f"/api/workspaces/{workspaces[0]['id']}/documents",
        method="POST",
        token=token,
        payload={"title": DOCUMENT_TITLE, "content_md": DOCUMENT_CONTENT},
        expected_status=201,
    )
    attachment_url = upload_png(base_url, token, document["id"])
    downloaded = request(base_url, attachment_url, token=token)
    if downloaded != PNG_BYTES:
        raise RuntimeError("Uploaded attachment did not match the source bytes")

    state = {
        "email": email,
        "password": password,
        "document_id": document["id"],
        "attachment_url": attachment_url,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    print(f"Created document {document['id']} and uploaded {len(PNG_BYTES)} PNG bytes")


def verify_state(base_url: str, state_path: Path) -> None:
    wait_for_health(base_url)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    login = json_request(
        base_url,
        "/api/auth/login",
        method="POST",
        payload={"email": state["email"], "password": state["password"]},
    )
    token = login["token"]
    document = json_request(
        base_url,
        f"/api/documents/{state['document_id']}?track=false",
        token=token,
    )
    if document["title"] != DOCUMENT_TITLE or document["content_md"] != DOCUMENT_CONTENT:
        raise RuntimeError("Document contents did not survive container recreation")
    downloaded = request(base_url, state["attachment_url"], token=token)
    if downloaded != PNG_BYTES:
        raise RuntimeError(
            "Attachment bytes did not survive container recreation: "
            f"expected {len(PNG_BYTES)} bytes, received {len(downloaded)}"
        )
    print("Login, document and attachment bytes all survived container recreation")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("write", "verify"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state-file", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "write":
        write_state(args.base_url, args.state_file)
    else:
        verify_state(args.base_url, args.state_file)


if __name__ == "__main__":
    main()
