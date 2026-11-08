#!/usr/bin/env python3
"""python3 snr.py router r1|r2 | server | client TTL [COUNT] [SIZE] | load TTL RATE SECS [SIZE] | send TTL DST | selftest"""
import sys, socket, json, time, ipaddress, statistics, uuid, threading, os
C, S = "10.10.1.2", "10.10.3.2"
ROUTES = {  # (prefix, next hop, UDP port)
    "r1": [("10.10.3.0/24", "10.10.2.2", 5000), ("10.10.1.0/24", C, 5002)],
    "r2": [("10.10.3.0/24", S, 5001), ("10.10.1.0/24", "10.10.2.1", 5000)],
}

def lpm(routes, dst):
    t = time.perf_counter_ns(); a = ipaddress.ip_address(dst); best = None
    for p, h, port in routes:
        n = ipaddress.ip_network(p)
        if a in n and (best is None or n.prefixlen > best[0].prefixlen):
            best = (n, h, port)
    return best, time.perf_counter_ns() - t

def udp(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((ip, port)); return s

def log(*a): print(f"{time.time():.6f}", *a, flush=True)

def extra():  # optional test route for Router 1, e.g. SNR_EXTRA="10.10.0.0/16,10.10.1.2,5002"
    e = os.environ.get("SNR_EXTRA")
    if not e: return []
    p, h, port = e.split(","); return [(p, h, int(port))]

def router(name):
    routes, s = ROUTES[name] + extra(), udp("0.0.0.0", 5000)
    while True:
        raw, _ = s.recvfrom(65535)
        try:
            p = json.loads(raw); p["ttl"] = int(p["ttl"]) - 1; mid, dst = p["id"], p["dst"]
        except (ValueError, KeyError, TypeError):
            log(name, "DROP bad-packet"); continue
        if p["ttl"] <= 0:
            log(name, mid, "DROP ttl-expired"); continue
        r, ns = lpm(routes, dst)
        if not r:
            log(name, mid, "DROP no-route", dst); continue
        s.sendto(json.dumps(p).encode(), (r[1], r[2]))
        log(name, mid, "FWD", f"{r[0]}->{r[1]}:{r[2]}", f"ttl={p['ttl']}", f"lookup_ns={ns}")

def server():
    s = udp(S, 5001)
    while True:
        p = json.loads(s.recvfrom(65535)[0])
        log("server", p["id"], "RX", f"ttl={p['ttl']}", f"bytes={len(p['data'])}")
        rep = {"id": p["id"], "src": S, "dst": p["src"], "ttl": 8, "data": p["data"]}
        s.sendto(json.dumps(rep).encode(), ("10.10.3.1", 5000))

def client(ttl, count=1, size=1000):
    s = udp(C, 5002); rtts, bad = [], 0
    for _ in range(count):
        mid, data = uuid.uuid4().hex[:8], "x" * size
        msg = {"id": mid, "src": C, "dst": S, "ttl": ttl, "data": data}
        t = time.perf_counter(); s.sendto(json.dumps(msg).encode(), ("10.10.1.1", 5000))
        try:
            while True:
                s.settimeout(max(0.01, 2 - (time.perf_counter() - t)))
                r = json.loads(s.recvfrom(65535)[0])
                if r["id"] == mid: break
            rtts.append((time.perf_counter() - t) * 1000); bad += r["data"] != data
        except socket.timeout:
            pass
    out = {"ttl": ttl, "sent": count, "replies": len(rtts), "timeouts": count - len(rtts), "corrupted": bad}
    if rtts:
        r = sorted(rtts)
        out |= {"rtt_median_ms": round(statistics.median(r), 2), "rtt_p95_ms": round(r[min(len(r) - 1, int(.95 * len(r)))], 2)}
    print(json.dumps(out))

def load(ttl, rate, secs, size=1000):
    """Send rate packets/s for secs seconds without waiting for replies, then drain 3 s."""
    s = udp(C, 5002); s.settimeout(0.2); got = set(); done = threading.Event()
    def rx():
        while not done.is_set():
            try: got.add(json.loads(s.recvfrom(65535)[0])["id"])
            except socket.timeout: pass
    th = threading.Thread(target=rx); th.start()
    n, data, t0, wall = int(rate * secs), "x" * size, time.perf_counter(), time.time()
    for i in range(n):
        while time.perf_counter() < t0 + i / rate: time.sleep(0.0005)
        s.sendto(json.dumps({"id": f"{i:06d}", "src": C, "dst": S, "ttl": ttl, "data": data}).encode(), ("10.10.1.1", 5000))
    time.sleep(3); done.set(); th.join()
    print(json.dumps({"sent": n, "replies": len(got), "seconds": secs, "t0": wall}))

def send(ttl, dst):
    s = udp(C, 5002); mid = uuid.uuid4().hex[:8]
    s.sendto(json.dumps({"id": mid, "src": C, "dst": dst, "ttl": ttl, "data": "probe"}).encode(), ("10.10.1.1", 5000)); print(mid)

def selftest():
    t = [("10.10.0.0/16", "A", 1), ("10.10.3.0/24", "B", 2)]
    assert lpm(t, "10.10.3.2")[0][1] == "B" and lpm(t, "10.10.9.9")[0][1] == "A" and lpm(t, "192.168.1.1")[0] is None
    print("LPM ok")

if __name__ == "__main__":
    a = sys.argv[1:]; m = a[0] if a else ""
    if m == "router": router(a[1])
    elif m == "server": server()
    elif m == "client": client(*map(int, a[1:]))
    elif m == "load": load(*map(int, a[1:]))
    elif m == "send": send(int(a[1]), a[2])
    elif m == "selftest": selftest()
    else: print(__doc__)
