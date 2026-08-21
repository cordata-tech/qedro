"""A stand-in for a Marquez-compatible lineage API.

The API tests run against a real HTTP server on a loopback port rather than a
patched `urlopen`. A stub agrees with whatever the client already does; a socket
does not, and URL construction, paging and the choice of verb are exactly the
parts worth being disagreed with about.
"""

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


def event(job="j", when="2026-08-21T10:00:00Z"):
    return {
        "eventType": "COMPLETE",
        "eventTime": when,
        "run": {"runId": "r"},
        "job": {"namespace": "ns", "name": job},
    }


@dataclass
class Backend:
    """A stand-in for the raw-event endpoint, and a log of what was asked of it.

    It deliberately ignores `after` and `before`. Every real backend the client
    will meet is entitled to, and the window has to survive that.
    """

    events: list = field(default_factory=list)
    envelope: bool = True
    status: int | None = None
    body: str | None = None
    requests: list = field(default_factory=list)

    @property
    def methods(self):
        return {method for method, _, _ in self.requests}


def handler(backend):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass  # the test output is not a place for an access log

        def _record(self):
            url = urlsplit(self.path)
            backend.requests.append((self.command, url.path, parse_qs(url.query)))
            return url, parse_qs(url.query)

        def do_GET(self):
            url, query = self._record()
            if backend.status:
                self.send_error(backend.status)
                return
            if url.path != "/api/v1/events/lineage":
                self.send_error(404)
                return
            if backend.body is not None:
                payload = backend.body
            else:
                limit = int(query.get("limit", ["100"])[0])
                offset = int(query.get("offset", ["0"])[0])
                page = backend.events[offset : offset + limit]
                payload = json.dumps(
                    {"events": page, "totalCount": len(backend.events)}
                    if backend.envelope
                    else page
                )
            data = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            # Nothing in the client can reach this. It exists so that if
            # something ever does, a test says so rather than a 501 in a log.
            self._record()
            self.send_error(405)

    return Handler
