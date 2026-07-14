import httpx

BASE = "http://localhost:8000"

tests = [
    ("GET", "/",            None),
    ("GET", "/snapshot",    None),
    ("GET", "/health",      None),
    ("POST","/chat",        {"question": "what is wrong with my cluster?"}),
    ("GET", "/cost",        None),
    ("GET", "/reliability", None),
    ("GET", "/performance", None),
    ("GET", "/storage",     None),
    ("GET", "/security",    None),
    ("GET", "/drift",       None),
    ("POST","/refresh",     None),
]

for method, path, body in tests:
    try:
        if method == "GET":
            r = httpx.get(BASE + path, timeout=30)
        else:
            r = httpx.post(BASE + path, json=body, timeout=30)
        status = "PASS" if r.status_code == 200 else f"FAIL ({r.status_code})"
    except Exception as e:
        status = f"FAIL ({e})"
    print(f"{method} {path:<20} → {status}")
