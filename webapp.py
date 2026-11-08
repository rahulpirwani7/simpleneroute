#!/usr/bin/env python3
"""Run: sudo python3 webapp.py   then open http://127.0.0.1:8080"""
import http.server, json, os, subprocess, urllib.parse as up
D = os.path.dirname(os.path.abspath(__file__)); NS = ["client", "r1", "r2", "server"]; P = []
COND = {"baseline": ("0ms", "0%", "10mbit"), "moderate": ("20ms", "2%", "5mbit"), "higher": ("100ms", "5%", "1mbit")}
HOSTS = ("127.0.0.1:8080", "localhost:8080")

def sh(c):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=300); return (r.stdout + r.stderr).strip()
def ex(n, c): return sh(f"ip netns exec {n} sh -c '{c}'")

def stop():
    for p in P: p.terminate()
    P.clear()
def start(q):
    stop()
    for n, a in (("r1", "router r1"), ("r2", "router r2"), ("server", "server")):
        P.append(subprocess.Popen(["ip", "netns", "exec", n, "python3", "-u", f"{D}/snr.py", *a.split()],
                                  stdout=open(f"/tmp/snr_{n}.log", "w"), stderr=subprocess.STDOUT))
    return "Routers and server started"
def netem(q):
    d, l, r = COND[q["c"]]
    return "\n".join(ex(n, f"tc qdisc replace dev {i} root netem delay {d} loss {l} rate {r}") or f"{n}/{i}: delay {d}, loss {l}, rate {r}"
                     for n, i in (("r1", "r1r2"), ("r2", "r2r1")))
ACTIONS = {
    "setup": lambda q: sh(f"bash {D}/setup.sh up") or "Topology created",
    "teardown": lambda q: (stop(), sh(f"bash {D}/setup.sh down"))[1] or "Topology removed",
    "start": start, "stop": lambda q: (stop(), "Stopped")[1], "netem": netem,
    "send": lambda q: ex("client", f"python3 {D}/snr.py client {int(q['ttl'])} {min(int(q.get('count', 1)), 50)}"),
    "ping": lambda q: ex("client", "ping -c 3 -W 2 10.10.3.2"),
    "traceroute": lambda q: ex("client", "traceroute -n 10.10.3.2"),
}

def state():
    return {"topo": "client" in sh("ip netns list"), "running": bool(P) and all(p.poll() is None for p in P),
            "routes": {n: ex(n, "ip -br -4 addr; ip route") for n in NS},
            "logs": {n: sh(f"tail -n 8 /tmp/snr_{n}.log 2>/dev/null") for n in ("r1", "r2", "server")}}

class H(http.server.BaseHTTPRequestHandler):
    def send(self, body, ct="application/json", code=200):
        b = body.encode(); self.send_response(code); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.headers.get("Host") not in HOSTS: return self.send("forbidden", "text/plain", 403)
        if self.path == "/api/state": return self.send(json.dumps(state()))
        self.send(open(f"{D}/dashboard.html", encoding="utf-8").read(), "text/html")
    def do_POST(self):
        if self.headers.get("Host") not in HOSTS or self.headers.get("Origin") not in (None, *("http://" + h for h in HOSTS)):
            return self.send("forbidden", "text/plain", 403)
        u = up.urlparse(self.path)
        try: out = ACTIONS[u.path.rsplit("/", 1)[-1]](dict(up.parse_qsl(u.query)))
        except Exception as e: out = f"Error: {e}"
        self.send(json.dumps({"out": out}))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print("SimpleNetRoute dashboard: http://127.0.0.1:8080")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8080), H).serve_forever()
