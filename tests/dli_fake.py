"""Simulated Digital Loggers REST controller for tests (loopback only). Mirrors the documented API: Digest auth,
X-CSRF on state changes, zero-based indices, `=N` selectors answering JSON lists, form-encoded PUT value=true|false.
Fault switches let tests make it misbehave."""
import hashlib
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REALM = "protected"


class FakeDli:
    def __init__(self, names, user="admin", password="secret"):
        self.names = list(names)
        self.on = [True] * len(names)
        self.user, self.password = user, password
        self.log = []                 # (method, path, form)
        self.stuck = set()            # indices whose relay ignores OFF
        self.fail_put = set()         # indices answering 500 to PUT
        self.two_values = False      # replies hold two values instead of one
        self.garbage_state = False    # physical_state answers a string
        self.require_csrf = True
        self.nonce = "n0nce"
        self.server = None
        self.connections = 0

    def start(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                outer.connections += 1
                super().setup()

            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", headers=None):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _auth_ok(self, method):
                header = self.headers.get("Authorization", "")
                if not header.startswith("Digest "):
                    return False
                f = {k: q or u for k, q, u in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]*))', header[7:])}
                ha1 = hashlib.md5(f"{f.get('username')}:{REALM}:{outer.password}".encode()).hexdigest()
                if f.get("username") != outer.user or f.get("nonce") != outer.nonce:
                    return False
                ha2 = hashlib.md5(f"{method}:{f.get('uri')}".encode()).hexdigest()
                want = hashlib.md5(
                    f"{ha1}:{f['nonce']}:{f.get('nc')}:{f.get('cnonce')}:auth:{ha2}".encode()).hexdigest()
                return f.get("response") == want and f.get("uri") == self.path

            def _handle(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                form = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode())) if length else {}
                if not self._auth_ok(method):
                    return self._send(401, b"", {"WWW-Authenticate":
                        f'Digest realm="{REALM}", qop="auth", nonce="{outer.nonce}", opaque="o", algorithm=MD5'})
                outer.log.append((method, self.path, form))
                m = re.fullmatch(r"/restapi/relay/outlets/=(\d+)/(name|physical_state|state)/", self.path)
                if not m or int(m.group(1)) >= len(outer.names):
                    return self._send(404)
                i, leaf = int(m.group(1)), m.group(2)
                if method == "PUT":
                    if outer.require_csrf and self.headers.get("X-CSRF") != "x":
                        return self._send(403)
                    if leaf != "state" or form.get("value") not in ("true", "false") or i in outer.fail_put:
                        return self._send(500 if i in outer.fail_put else 400)
                    if form["value"] == "false" and i not in outer.stuck:
                        outer.on[i] = False
                    elif form["value"] == "true":
                        outer.on[i] = True
                    return self._send(204)
                if leaf == "name":
                    body = [outer.names[i]]
                elif leaf == "physical_state":
                    body = ["yes"] if outer.garbage_state else [outer.on[i]]
                else:
                    body = [outer.on[i]]
                if outer.two_values:
                    body = body * 2
                self._send(200, json.dumps(body).encode(), {"Content-Type": "application/json"})

            def do_GET(self):
                self._handle("GET")

            def do_PUT(self):
                self._handle("PUT")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
