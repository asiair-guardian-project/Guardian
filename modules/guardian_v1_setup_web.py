"""Guardian 1.0 first-run setup wizard: the local-only web page (step one).

A SEPARATE program, started on demand and stopped with Ctrl-C. It is not part of the monitor and never
talks to it: no ARM, no DISARM, no power switching, no operator-socket command of any kind.

Safety rules:
  * listens on 127.0.0.1 only (never Tailscale, a LAN address or 0.0.0.0);
  * the Host header must be this server's own loopback name and port (blocks DNS rebinding);
  * every POST needs a random per-run token (sent in a header, so another web page cannot forge it)
    and a JSON content type; request bodies are size-capped;
  * the output folder is fixed when the program starts; the page cannot choose where a file is written;
  * the only file it can create is one NEW candidate configuration, never overwriting anything.
"""
from __future__ import annotations

import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from modules import guardian_v1_setup_wizard as wizard

DEFAULT_PORT = 8766
MAX_BODY_BYTES = 4096
CHECKS = ("asiair", "roof", "strip")


def _page(token: str) -> bytes:
    return (_PAGE.replace("__TOKEN__", token).replace("__HOST__", wizard.DEFAULT_ALPACA_HOST)
            .replace("__PORT__", str(wizard.DEFAULT_ALPACA_PORT))).encode("utf-8")


def make_server(folder, *, port=DEFAULT_PORT, token=None, checks=None):
    """Build the server. `checks` lets tests replace the three equipment checks; real use passes none."""
    token = token or secrets.token_urlsafe(24)
    runners = {
        "asiair": lambda body: wizard.check_asiair(str(body.get("asiair_ip", ""))),
        "roof": lambda body: wizard.check_roof(str(body.get("roof_host", "")), body.get("roof_port"),
                                               body.get("roof_device")),
        "strip": lambda body: wizard.check_strip(str(body.get("strip_ip", ""))),
    }
    runners.update(checks or {})

    class Handler(BaseHTTPRequestHandler):
        server_version = "GuardianSetup"
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):   # keep the Terminal quiet
            pass

        # -- helpers
        def _allowed_host(self):
            actual_port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{actual_port}", f"localhost:{actual_port}")

        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if "text" in content_type else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                             "connect-src 'self'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        # -- routes
        def do_GET(self):
            if not self._allowed_host():
                return self._send(400, {"ok": False, "message": "Unexpected Host header"})
            if self.path.split("?", 1)[0] == "/":
                return self._send(200, _page(token), "text/html")
            return self._send(404, {"ok": False, "message": "Not found"})

        def do_POST(self):
            if not self._allowed_host():
                return self._send(400, {"ok": False, "message": "Unexpected Host header"})
            if not hmac.compare_digest(self.headers.get("X-Wizard-Token", ""), token):
                return self._send(403, {"ok": False, "message": "Missing or wrong token"})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._send(415, {"ok": False, "message": "JSON required"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._send(411, {"ok": False, "message": "Content-Length required"})
            if not 0 < length <= MAX_BODY_BYTES:
                return self._send(413, {"ok": False, "message": "Request too large"})
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeError):
                return self._send(400, {"ok": False, "message": "Malformed JSON"})
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "message": "A JSON object is required"})

            path = self.path.split("?", 1)[0]
            if path == "/api/check":
                which = body.get("which")
                if which not in CHECKS:
                    return self._send(400, {"ok": False, "message": "Unknown check"})
                try:
                    return self._send(200, runners[which](body))
                except Exception as error:     # a failing check is a report, never a crash
                    return self._send(200, {"ok": False, "detail": f"The check failed: {error}"})
            if path == "/api/write":
                try:
                    installation = wizard.build_installation(body.get("form"))
                    result = wizard.write_candidate(folder, installation)
                except wizard.WizardError as error:
                    return self._send(200, {"ok": False, "message": str(error)})
                except OSError as error:
                    return self._send(200, {"ok": False, "message": f"Could not write the file: {error}"})
                result.update(ok=True, next_steps=wizard.next_steps(result["path"], installation))
                return self._send(200, result)
            return self._send(404, {"ok": False, "message": "Not found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.guardian_token = token
    return server


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Guardian 1.0 setup</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font:16px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1d1d1f}
 h1{margin:.2rem 0}.sub{color:#6b6b70;margin-top:0}
 .banner{background:#eef3ff;border:1px solid #c9d7ff;border-radius:8px;padding:.6rem .9rem;margin:1rem 0}
 .step{display:none;border:1px solid #d9d9de;border-radius:10px;padding:1rem 1.2rem;margin:1rem 0}.step.on{display:block}
 label{display:block;margin:.7rem 0 .2rem;font-weight:600}
 input{font:inherit;padding:.4rem .5rem;width:100%;box-sizing:border-box;border:1px solid #b8b8bf;border-radius:6px}
 button{font:inherit;padding:.45rem .9rem;border-radius:7px;border:1px solid #8e8e93;background:#f2f2f7;cursor:pointer;margin:.6rem .4rem 0 0}
 button.primary{background:#0a6cff;border-color:#0a6cff;color:#fff}button:disabled{opacity:.5;cursor:default}
 .res{margin-top:.6rem;padding:.5rem .7rem;border-radius:6px;display:none}.ok{background:#e7f6ea;display:block}.bad{background:#fdeaea;display:block}.wait{background:#f2f2f7;display:block}
 .hint{color:#6b6b70;font-size:.9rem}code{background:#f2f2f7;padding:.1rem .3rem;border-radius:4px}
 table{border-collapse:collapse}td{padding:.2rem .8rem .2rem 0}
</style></head><body>
<h1>Guardian 1.0 setup</h1><p class="sub">First-run setup &middot; step one</p>
<div class="banner"><b>This page only looks, and writes one new file.</b> It never switches power, never ARMs or DISARMs, and never
activates anything. It runs only on this computer.</div>

<div class="step on" id="s0"><h2>1. Before you start</h2>
<p>You will enter four addresses and say which power-strip outlet is which. The address screens have a <b>Check</b> button that
reads from your equipment (read-only) so you know the address is right. At the end the page creates a candidate configuration
file for you to review.</p>
<p class="hint">Not in this step: activating the file, and commissioning (the equipment checks you verify yourself).</p>
<button class="primary" onclick="go(1)">Start</button></div>

<div class="step" id="s1"><h2>2. ASIAIR</h2>
<label for="asiair_ip">ASIAIR address (the wired address, if it is connected by Ethernet)</label>
<input id="asiair_ip" placeholder="for example 192.168.1.20" autocomplete="off">
<button onclick="check('asiair')">Check (ping)</button><div class="res" id="r_asiair"></div>
<div><button onclick="go(0)">Back</button><button class="primary" onclick="go(2)">Next</button></div></div>

<div class="step" id="s2"><h2>3. Roof status</h2>
<p class="hint">Starfront's roof status is the same service for every operator; the device number is yours.</p>
<label for="roof_host">Alpaca host</label><input id="roof_host" value="__HOST__" autocomplete="off">
<label for="roof_port">Port</label><input id="roof_port" value="__PORT__" inputmode="numeric">
<label for="roof_device">Your safety monitor device number</label><input id="roof_device" inputmode="numeric" autocomplete="off">
<button onclick="check('roof')">Check (read once)</button><div class="res" id="r_roof"></div>
<div><button onclick="go(1)">Back</button><button class="primary" onclick="go(3)">Next</button></div></div>

<div class="step" id="s3"><h2>4. Power strip</h2>
<label for="controller">Kind of power controller</label>
<select id="controller"><option value="kasa_hs300">Kasa HS300 power strip</option>
<option value="digital_loggers_rest">Digital Loggers (newer models with the REST API) - not yet tested on real hardware</option></select>
<label for="strip_ip">Power controller address</label><input id="strip_ip" placeholder="for example 192.168.1.31" autocomplete="off">
<button onclick="check('strip')">Check (ping)</button><div class="res" id="r_strip"></div>
<p class="hint">The check is a ping. It opens no session with the strip and sends it no command, so no outlet can change. Your sign-in is not asked for here.</p>
<div><button onclick="go(2)">Back</button><button class="primary" onclick="go(4)">Next</button></div></div>

<div class="step" id="s4"><h2>5. Outlets</h2>
<p>Look at the outlet names in the Kasa app (or on the Digital Loggers web page) and type each <b>exactly</b> as it appears there. Guardian refuses to switch an
outlet whose name on the strip no longer matches what you enter here.</p>
<p class="hint">The computer running Guardian is never switched: say which outlet powers it so Guardian can protect it.
When protecting the rig Guardian switches off the ASIAIR first, then the mount, then the accessories.</p>
<table>
<tr><td></td><td><b>Outlet number</b></td><td><b>Outlet name</b></td></tr>
<tr><td>This computer (never switched)</td><td><input id="host_outlet_number" inputmode="numeric" size="3"></td><td><input id="host_outlet_alias" autocomplete="off"></td></tr>
<tr><td>ASIAIR</td><td><input id="asiair_outlet_number" inputmode="numeric" size="3"></td><td><input id="asiair_outlet_alias" autocomplete="off"></td></tr>
<tr><td>Mount</td><td><input id="mount_outlet_number" inputmode="numeric" size="3"></td><td><input id="mount_outlet_alias" autocomplete="off"></td></tr>
<tr><td>Accessories (for example dew heaters)</td><td><input id="accessories_outlet_number" inputmode="numeric" size="3"></td><td><input id="accessories_outlet_alias" autocomplete="off"></td></tr>
</table>
<div><button onclick="go(3)">Back</button><button class="primary" onclick="review()">Next</button></div></div>

<div class="step" id="s5"><h2>6. Review</h2><table id="rv"></table>
<p class="hint">Checks you have not run are not required, but a check that failed means that address may be wrong.</p>
<button onclick="go(4)">Back</button><button class="primary" id="wr" onclick="createCandidate()">Create candidate file</button>
<div class="res" id="r_write"></div><ul id="nx"></ul></div>

<script>
const TOKEN="__TOKEN__";
const F=["controller","asiair_ip","roof_host","roof_port","roof_device","strip_ip","host_outlet_number","host_outlet_alias","asiair_outlet_number","asiair_outlet_alias","mount_outlet_number","mount_outlet_alias","accessories_outlet_number","accessories_outlet_alias"];
function val(i){return document.getElementById(i).value.trim()}
function go(n){document.querySelectorAll('.step').forEach((e,i)=>e.classList.toggle('on',i===n))}
function show(id,ok,text){const e=document.getElementById(id);e.className='res '+(ok===null?'wait':(ok?'ok':'bad'));e.textContent=text}
async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Wizard-Token':TOKEN},body:JSON.stringify(body)});
  return r.json();
}
async function check(which){
  const body={which};F.forEach(f=>body[f]=val(f));
  show('r_'+which,null,'Checking...');
  try{const r=await post('/api/check',body);show('r_'+which,r.ok,r.detail||r.message||'')}
  catch(e){show('r_'+which,false,'Could not run the check: '+e)}
}
function form(){const o={};F.forEach(f=>o[f]=val(f));return o}
function review(){
  const t=document.getElementById('rv');t.innerHTML='';
  [["Power controller","controller"],["ASIAIR address","asiair_ip"],["Roof host","roof_host"],["Roof port","roof_port"],["Safety monitor device","roof_device"],["Strip address","strip_ip"],
    ["This computer (never switched)","host_outlet_number"],["  its name","host_outlet_alias"],
    ["ASIAIR outlet","asiair_outlet_number"],["  its name","asiair_outlet_alias"],
    ["Mount outlet","mount_outlet_number"],["  its name","mount_outlet_alias"],
    ["Accessories outlet","accessories_outlet_number"],["  its name","accessories_outlet_alias"]]
   .forEach(([l,k])=>{const r=t.insertRow();r.insertCell().textContent=l;r.insertCell().textContent=val(k)||'(empty)'});
  go(5);
}
async function createCandidate(){
  document.getElementById('wr').disabled=true;
  try{
    const r=await post('/api/write',{form:form()});
    if(r.ok){show('r_write',true,'Created '+r.path+' (nothing activated)');
      const u=document.getElementById('nx');u.innerHTML='';r.next_steps.forEach(s=>{const li=document.createElement('li');li.textContent=s;u.appendChild(li)})}
    else{show('r_write',false,r.message);document.getElementById('wr').disabled=false}
  }catch(e){show('r_write',false,'Could not write: '+e);document.getElementById('wr').disabled=false}
}
</script></body></html>
"""
