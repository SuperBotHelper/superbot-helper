#!/usr/bin/env python3
# SuperBot helper v4.5.3. Python 3 stdlib only. Output is one JSON object on stdout.
# Keys are never printed, logged, put in argv or in state files other than keys.json (mode 600).
import difflib, hashlib, json, os, re, select, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.request, uuid

VERSION = "4.5.3"
HOME = os.path.expanduser("~")
SB = os.path.join(HOME, ".superbot")
PEND = os.path.join(SB, "pending")
CFG = os.path.join(SB, "config.json")
KEYS = os.path.join(SB, "keys.json")
PROBE = os.path.join(SB, "probe.json")   # which models answered a tiny call, with a timestamp
NPM = os.path.join(SB, "npm")
PINS = {"claude": ("@anthropic-ai/claude-code", "2.1.300", "claude"),
        "chatgpt": ("@openai/codex", "0.162.1", "codex")}
PAID, FREE, SUB = "Connect a paid account", "Connect a free or paid account", "sub"
P = {
 "claude": {"name": "Claude", "kind": "cli", "label": PAID, "pay": SUB},
 "chatgpt": {"name": "ChatGPT", "kind": "cli", "label": PAID, "pay": SUB},
 "gemini": {"name": "Gemini", "kind": "gemini", "label": FREE, "pay": "maybe",
            "base": "https://generativelanguage.googleapis.com/v1beta", "page": "https://aistudio.google.com/apikey",
            "instructions": ["Sign in with your Google account.", "Tap Create API key. If it asks for a project, choose Create project.", "Copy the key and paste it in the key box."]},
 "groq": {"name": "Groq", "kind": "openai", "label": FREE, "pay": "maybe",
          "base": "https://api.groq.com/openai/v1", "page": "https://console.groq.com/keys",
          "instructions": ["Sign up or sign in.", "Tap Create API Key and copy it.", "Paste it in the key box."]},
 "openrouter": {"name": "OpenRouter", "kind": "openai", "label": FREE, "pay": "maybe",
                "base": "https://openrouter.ai/api/v1", "page": "https://openrouter.ai/keys",
                "instructions": ["Sign up or sign in.", "Tap Create Key and copy it.", "Paste it in the key box."]},
 "mistral": {"name": "Mistral", "kind": "openai", "label": FREE, "pay": "maybe",
             "base": "https://api.mistral.ai/v1", "page": "https://console.mistral.ai/api-keys",
             "instructions": ["Sign up or sign in. Pick the free plan if asked.", "Create a new key and copy it.", "Paste it in the key box."]},
 "deepseek": {"name": "DeepSeek", "kind": "openai", "label": PAID, "pay": "yes",
              "base": "https://api.deepseek.com", "page": "https://platform.deepseek.com/api_keys",
              "instructions": ["Sign up or sign in.", "Create a new API key and copy it.", "Paste it in the key box."]},
 "perplexity": {"name": "Perplexity", "kind": "openai", "label": PAID, "pay": "yes",
                "base": "https://api.perplexity.ai", "page": "https://www.perplexity.ai/account/api/keys",
                "instructions": ["Sign in and open API keys.", "Create a key and copy it.", "Paste it in the key box."],
                "static": ["sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-deep-research"]},
}
ORDER = ["claude", "chatgpt", "gemini", "deepseek", "perplexity", "groq", "openrouter", "mistral"]
CARD = ORDER[:5]   # on the Pick card; Groq, OpenRouter and Mistral are reached by name ("add Groq" or the Other box)
OTHER_ROW = "Other: a model or company not listed here"
BEST = {"gemini": [],   # Gemini is ranked by gemini_rank (newest version first); probes decide what is shown
        "groq": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"], "openrouter": [":free"],
        "mistral": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
        "deepseek": ["deepseek-reasoner", "deepseek-chat"], "perplexity": ["sonar-pro"],
        "claude": ["opus"], "chatgpt": []}   # ChatGPT: first listed model in the cache; "default" comes last
CLAUDE_MODELS = [("opus", "Claude Opus"), ("sonnet", "Claude Sonnet"), ("haiku", "Claude Haiku")]
NOT_CHAT = re.compile(r"(embed|whisper|tts|audio|guard|moderation|image|imagen|veo|aqa|transcribe|ocr|realtime|lyria|robotics)", re.I)
KEYPRE = r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|gsk_[A-Za-z0-9]{10,}|pplx-[A-Za-z0-9]{10,}|xai-[A-Za-z0-9]{10,}"
KEYLIKE = re.compile(KEYPRE + r"|[A-Za-z0-9_\-]{32,})")
KEYSURE = re.compile(KEYPRE + ")")
URL = re.compile(r"(https://\S+)")
DEAD = re.compile(r"(not.found|does not exist|no longer|not available to new (users|accounts)|deprecated|decommissioned|not supported|unknown model|invalid model|retired)", re.I)
LEVELS = ["low", "medium", "high"]
BUSY = re.compile(r"(rate.?limit|too many requests|quota|resource.?exhausted|overloaded|busy|try again later|usage limit|high.demand)", re.I)
KEYBAD = re.compile(r"(api.?key.{0,20}(invalid|not valid|expired|incorrect)|invalid.{0,20}(api.?key|key|token|credentials)|incorrect api key|"
                    r"unauthori[sz]ed|authentication|permission.denied(?!.{0,40}model)|not logged in|not signed in|please (log|sign) ?in)", re.I)
# 4.5.1: only these words mean the key itself is bad. The wider KEYBAD also matched Google's 403 PERMISSION_DENIED
# for one model ("The caller does not have permission") and 400s like "invalid ... token", which read a valid key as wrong.
KEYSAYS = re.compile(r"(api.?key.{0,20}(invalid|not valid|expired|incorrect|revoked|leaked)|invalid.{0,20}api.?key|incorrect api key|"
                     r"api_key_invalid|unauthenticated|invalid.{0,20}(authentication|credentials))", re.I)
NOACCESS = re.compile(r"(do(es)? not have access|no access|not available (on|for|to) (this|your) (key|account|plan|tier|project)|not allowed to use|"
                      r"permission.{0,40}model|model.{0,40}permission)", re.I)
NETERR = re.compile(r"(ENOTFOUND|ECONNREFUSED|ECONNRESET|ETIMEDOUT|EAI_AGAIN|network error|connection error|could not resolve host|stream disconnected)", re.I)
GATEWAY = re.compile(r"(\b50[0234]\b|internal server error|bad gateway|service unavailable|gateway time-?out)", re.I)
# One place for the plain reasons shown beside a model that can't be used (or is busy).
REASONS = {
    "dead": "No longer available to new accounts",
    "busy": "Busy right now on the free plan",
    "noaccess": "Not available on this key",
    "badid": "Its model list didn't match what SuperBot expected",
    "noanswer": "Did not answer",
    "unchecked": "Not checked yet. Type its name to try it",
    "notchat": "Not a chat model",
    "off": "Turned off by %s",
    "paid": "Paid models aren't in this version",
    "hidden": "Hidden in %s's list. Type the name to use it",
}
# Probe bounds: a tiny call per model, best candidates first, stop once PROBE_WANT answered.
PROBE_WANT = 3            # the model card shows 3
PROBE_MAX_CALLS = 8       # never more tiny calls than this per company per check (HTTP companies)
PROBE_MAX_CLI = 3         # Claude and ChatGPT calls are slower, so fewer
PROBE_TIMEOUT = 12        # seconds per HTTP call in a check (probe and list fetch)
PROBE_CLI_TIMEOUT = 40    # seconds per CLI probe
# 4.5: quiet retries in a check (setup test, model card, status). A wrong key, a gone model or busy never retries.
NET_WAITS = (3, 8, 15)    # seconds before try 2, 3 and 4 of one call after a network error
NET_RETRIES = 4           # extra tries per check, shared by the list fetch and every probe
NET_CAP = 90              # hard cap in seconds for one check, calls and waits together
TRANSIENT = (408, 500, 502, 503, 504, 520, 521, 522, 523, 524, 529)   # gateway and server errors count as network
PROBE_PAR = 3             # 4.5.1: HTTP companies probe up to 3 models at a time once their list call worked
PEND_FRESH = 30 * 60      # 4.5.1: status leaves a half-finished setup alone while it is younger than this
GATE_RETRY = (0, 500, 502, 504, 520, 521, 522, 523, 524)   # one model's network or gateway error: one quiet retry
PROBE_TTL = {"ok": 6 * 3600, "busy": 30 * 60, "dead": 24 * 3600, "noaccess": 24 * 3600, "noanswer": 30 * 60}
PROBE_PROMPT = "Reply with the word OK."
ROUND_TIMEOUT = {1: 120, 2: 90, 3: 90}   # seconds per call in each debate round
ASK_WAITS = (3, 8)        # an ask or debate call that hit a network error or came back empty: tried again after 3, then 8 seconds
ASK_EXTRA = 60            # cap: one call with its retries never runs longer than its own timeout plus this
TIMEOUT_GROW = 1.75       # a call that ran out of time gets one more try with 1.75 times its limit (120s becomes 210s)
BUSY_PAUSE = 4            # 4.5.2: a busy model (429, 503, 529, high demand) is tried once more after this pause
ALT_MAX = 3               # 4.5.2: then at most this many other models from the same company, one call each
ALT_TIMEOUT = 45          # 4.5.2: seconds per call for those other models (HTTP)
ALT_TIMEOUT_CLI = 90      # 4.5.2: the same for Claude and ChatGPT
SERVERS = {"gemini": "Google", "claude": "Anthropic", "chatgpt": "OpenAI"}   # whose servers were busy; others: the company name
BUSY503 = re.compile(r"\b(503|529)\b")
# 4.5.3: model IDs. Only key companies with a standard model list (OpenRouter, Groq, Mistral, DeepSeek, Other) use this;
# Claude, ChatGPT, Gemini and Perplexity's fixed list work exactly as in 4.5.2 and never reach it (see idfix).
ID_FIELDS = ("id", "model_id", "model", "slug", "model_slug", "canonical_slug", "name")   # the real ID: "id" first, "name" last
ID_EXTRA = re.compile(r"(^|_)(id|slug)$")   # other fields that may hold an ID, tried after ID_FIELDS
DISPLAY_FIELDS = ("name", "display_name", "displayName", "title")   # shown to the owner, never sent
IDLIKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/:@+]{0,199}$")   # no spaces: "NVIDIA: Nemotron 3.5 (free)" is a display name
BADID = re.compile(r"(not a valid model|invalid model|unknown model|model[_ ]not[_ ]found|no such model|"
                   r"model\W.{0,120}(does not exist|doesn't exist|not found|is not supported|unsupported))", re.I)
ID_TRY_FIELDS = 2         # 4.5.3: after every probe said "not a valid model ID", at most 2 other ID fields are tried
ID_TRY_CALLS = 4          # and at most 4 extra tiny calls in all (2 models per field), sequential, inside the check's 90 s
ID_ASK_TRIES = 2          # an ask whose saved model got "not a valid model ID": at most 2 other IDs from a fresh list
IDF = os.path.join(SB, "idfield.json")   # 4.5.3: {company: field} when an ID field other than the first one worked
DEBATE_CAP = 600          # seconds for one debate's model calls, round by round; no longer try starts past it
_secrets = []


def scrub(s):
    s = str(s)
    for k in _secrets:
        if k:
            s = s.replace(k, "[hidden]")
    return "".join(KEYSURE.sub("[hidden]", x) if URL.fullmatch(x) else KEYLIKE.sub("[hidden]", x) for x in URL.split(s))


def gate(x):
    """The one final card gate. Every dict holding a widget, at any depth, is checked here."""
    if isinstance(x, dict):
        if "widget" in x:
            safe_card(x)
        for v in x.values():
            gate(v)
    elif isinstance(x, list):
        for v in x:
            gate(v)
    return x


def out(obj, rc=0):
    # scrub first, then gate exactly the text that gets printed
    sys.stdout.write(json.dumps(gate(json.loads(scrub(json.dumps(obj))))) + "\n")
    sys.exit(rc)


def rj(path, default):
    try:
        with open(path) as f:
            v = json.load(f)
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def wj(path, obj, mode=0o600):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())   # unique, so parallel asks never collide
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def cfg():
    return rj(CFG, {"version": VERSION, "connected": {}})


def migrate():
    # State from an older helper (4.0): same config and journal format. 4.0 had no "finished" flag,
    # so a config with connections counts as set up and an empty one shows the Pick card again.
    if not os.path.exists(CFG):
        return []
    c = rj(CFG, {})
    if not c:
        if os.path.exists(CFG):
            os.remove(CFG)   # unreadable leftover; nothing is connected without it
            return ["config"]
        return []
    if c.get("version") == VERSION and isinstance(c.get("connected"), dict):
        return []
    if not isinstance(c.get("connected"), dict):
        c["connected"] = {}
    c.setdefault("finished", bool(c["connected"]))
    c["version"] = VERSION
    wj(CFG, c, 0o644)
    return ["config"]


def info(p):
    if p in P:
        return P[p]
    c = cfg()
    o = c.get("connected", {}).get(p) or c.get("parked", {}).get(p) or rj(os.path.join(PEND, p + ".json"), {}).get("other")
    if o:
        return {"name": o["name"], "kind": "openai", "label": PAID if o.get("paid") else FREE,
                "pay": "yes" if o.get("paid") else "maybe", "base": o["base"], "other": True}
    out({"error": "unknown", "line": "I don't know that one yet. You can add it with Other."}, 2)


def base(p):
    t = os.environ.get("SB_TEST_BASE", "")
    if t.startswith("http://127.0.0.1"):
        return t.rstrip("/") + "/" + p
    return info(p)["base"]


def key(p):
    k = rj(os.path.join(PEND, p + ".key"), {}).get("k") or rj(KEYS, {}).get(p)
    if k:
        _secrets.append(k)
    return k


def tscale(t):
    """Test hook: with SB_TEST_CLOCK=1, SB_TEST_TIMEOUT_SCALE shrinks real time limits so a timeout can be tested fast."""
    sc = os.environ.get("SB_TEST_TIMEOUT_SCALE") if os.environ.get("SB_TEST_CLOCK") else None
    return t * float(sc) if sc else t


def is_timeout(e):
    return isinstance(e, (socket.timeout, TimeoutError)) or isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError))


def http(method, url, hdr=None, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(hdr or {}, **{"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=tscale(timeout)) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode()[:400]
        except Exception:
            msg = ""
        return e.code, {"error": scrub(msg)}
    except Exception as e:
        if is_timeout(e):   # our own time limit ran out: told apart from a real network error for asks and debates
            NETSEEN.timed_out = True
            return 0, {"error": "timed out after %ss" % timeout}
        return 0, {"error": scrub(type(e).__name__)}


CHECK = {"t0": None, "left": NET_RETRIES, "retries": 0, "waited": 0, "fake": 0.0}
NETSEEN = threading.local()   # NETSEEN.transient: the last call() failed like a network error


def fake_clock():
    """Test hook: SB_TEST_CLOCK=1 makes waits move a counter instead of sleeping, and counts each
    network failure as a full timeout. Nothing else changes."""
    return bool(os.environ.get("SB_TEST_CLOCK"))


def now():
    return CHECK["fake"] if fake_clock() else time.monotonic()


def nap(s):
    CHECK["waited"] += s
    if fake_clock():
        CHECK["fake"] += s
    else:
        time.sleep(s)


def seen():
    """With the test clock on, how the check went (retries and waited seconds), for the tests. Empty otherwise."""
    return {"check": {"retries": CHECK["retries"], "waited": CHECK["waited"], "elapsed": round(now() - (now() if CHECK["t0"] is None else CHECK["t0"]), 1)}} if fake_clock() else {}


def time_left():
    if CHECK["t0"] is None:
        CHECK["t0"] = now()
    return NET_CAP - (now() - CHECK["t0"])


def retrying(fn, tmo, none):
    """fn(timeout) -> (result, transient). A network-type failure is tried again quietly after NET_WAITS,
    while the check has retries and time left. Returns (result, still_failing); `none` when no time is left."""
    n = 0
    while True:
        left = time_left()
        if left < 1:
            return none, True
        t = max(1, min(tmo, int(left)))
        res, bad = fn(t)
        if not bad:
            return res, False
        if fake_clock():
            CHECK["fake"] += t
        if n >= len(NET_WAITS) or CHECK["left"] <= 0 or time_left() - NET_WAITS[n] < 5:
            return res, True
        nap(NET_WAITS[n])
        CHECK["left"] -= 1; CHECK["retries"] += 1; n += 1


def auth(p):
    k = key(p)
    if info(p)["kind"] == "gemini":
        return {"x-goog-api-key": k or ""}
    return {"Authorization": "Bearer " + (k or "")}


def child_env(p):
    env = {k: v for k, v in os.environ.items() if not (k.startswith("SUPERBOT_SECRET") or k.endswith("_API_KEY") or k.endswith("_TOKEN"))}
    env["CLAUDE_CONFIG_DIR"] = os.path.join(SB, "claude")
    env["CODEX_HOME"] = os.path.join(SB, "codex")
    env["PATH"] = os.path.join(NPM, "node_modules", ".bin") + os.pathsep + env.get("PATH", "")
    return env


NOT_IN = re.compile(r"\bnot\s+(logged|signed)\s+in\b|\blogged\s+out\b|\"loggedIn\"\s*:\s*false", re.I)
YES_IN = re.compile(r"\"loggedIn\"\s*:\s*true|\b(logged|signed)\s+in\b", re.I)


def signed_in(rc, o, e):
    """CLIs print status on stdout or stderr (codex uses stderr), so read both, plus the return code."""
    t = (o or "") + "\n" + (e or "")
    return rc == 0 and not NOT_IN.search(t) and bool(YES_IN.search(t))


def tail_of(*texts, n=200):
    """The last few hundred characters of a call's output, for the debug block only."""
    t = re.sub(r"\s+", " ", " | ".join(x.strip() for x in texts if x and x.strip()))
    return scrub(t[-n:])


def run_cli(p, args, stdin=None, timeout=300):
    try:
        r = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=tscale(timeout), env=child_env(p), cwd=SB)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as x:
        NETSEEN.timed_out = True   # rc 124 is our own limit, not the network; call() reports it as "timeout"
        dec = lambda b: (b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or ""))
        return 124, dec(x.stdout), dec(x.stderr) + "\ntimeout"
    except OSError as e:
        return 127, "", type(e).__name__


# ---------------------------------------------------------------- models
def thinking_for(p, m, meta):
    if p == "gemini" and meta.get("thinking"):
        return ["low", "high"] if m.startswith("gemini-3") else LEVELS
    if p == "openrouter" and "reasoning" in (meta.get("supported_parameters") or []):
        return LEVELS
    if p == "groq" and m.startswith("openai/gpt-oss"):
        return LEVELS
    if p == "chatgpt":
        return [x.get("effort", x) if isinstance(x, dict) else x for x in meta.get("supported_reasoning_levels", [])] or LEVELS
    return []


def free_model(p, m, meta):
    if p == "openrouter":
        pr = meta.get("pricing") or {}
        return m.endswith(":free") or (str(pr.get("prompt")) in ("0", "0.0") and str(pr.get("completion")) in ("0", "0.0"))
    if p == "gemini":
        return "flash" in m
    return p in ("groq", "mistral")


LIST = {"code": None, "error": "", "raw": [], "noid": False}


def list_models(p):
    """Live list: [{id,label,usable,reason,thinking,free}] or None when the list can't be read (LIST says why)."""
    i, rows = info(p), []
    if p == "claude":
        return [{"id": m, "label": l, "usable": True, "reason": "", "thinking": [], "free": False} for m, l in CLAUDE_MODELS]
    if p == "chatgpt":
        cache = rj(os.path.join(SB, "codex", "models_cache.json"), {}).get("models", [])
        for m in cache:
            if m.get("slug") and m["slug"] != "default":
                hid = m.get("visibility", "list") != "list"
                rows.append({"id": m["slug"], "label": m.get("display_name", m["slug"]), "usable": True, "reason": "",
                             "thinking": thinking_for(p, m["slug"], m), "free": False, "hidden": hid})
        rows.append({"id": "default", "label": "ChatGPT default", "usable": True, "reason": "", "thinking": LEVELS, "free": False})
        return rows
    if i.get("static"):
        return [{"id": m, "label": m, "usable": True, "reason": "", "free": False,
                 "thinking": LEVELS if m == "sonar-deep-research" else []} for m in i["static"]]
    url = base(p) + ("/models?pageSize=1000" if i["kind"] == "gemini" else "/models")
    (code, js), _ = retrying(lambda t: (lambda r: (r, r[0] == 0 or r[0] in TRANSIENT))(http("GET", url, auth(p), timeout=t)),
                             PROBE_TIMEOUT, (0, {"error": "timeout"}))
    LIST.update(code=code, error=json.dumps(js.get("error", "")) if isinstance(js, dict) else "")
    if code != 200:
        return None
    if idfix(p):   # 4.5.3: the real ID, read per list format; the display name kept apart
        ents = [m for m in (js.get("data") if isinstance(js.get("data"), list) else []) if isinstance(m, dict)]
        LIST["raw"] = ents
        rows = rows_from(p, ents, id_field(p))
        LIST["noid"] = bool(ents) and not rows and not any(entry_ids(m) for m in ents)
        return rows
    for m in js.get("models" if i["kind"] == "gemini" else "data", []):
        mid = (m.get("name") or m.get("id") or "").replace("models/", "")
        if not mid:
            continue
        rows.append(row_for(p, m, mid, m.get("displayName") or mid))
    return rows


def row_for(p, m, mid, label):
    i, reason = info(p), ""
    if i["kind"] == "gemini" and "generateContent" not in m.get("supportedGenerationMethods", ["generateContent"]):
        reason = REASONS["notchat"]
    elif NOT_CHAT.search(mid):
        reason = REASONS["notchat"]
    elif m.get("active") is False:
        reason = REASONS["off"] % i["name"]
    elif p == "mistral" and (m.get("capabilities") or {}).get("completion_chat") is False:
        reason = REASONS["notchat"]
    elif p == "openrouter" and not free_model(p, mid, m):
        reason = REASONS["paid"]
    return {"id": mid, "label": label, "usable": not reason, "reason": reason, "thinking": thinking_for(p, mid, m), "free": free_model(p, mid, m)}


def idfix(p):
    """4.5.3: True only for key companies with a standard model list: OpenRouter, Groq, Mistral, DeepSeek and Other.
    Claude, ChatGPT, Gemini and Perplexity (a fixed list) never use the ID fixes and work exactly as in 4.5.2."""
    if p in ("claude", "chatgpt", "gemini", "perplexity"):
        return False
    i = info(p)
    return i["kind"] == "openai" and not i.get("static")


def entry_ids(m):
    """Every ID-like value in one list entry, best field first: [(field, value)]. Display names (spaces) never count."""
    keys = list(ID_FIELDS) + sorted(k for k in m if k not in ID_FIELDS and ID_EXTRA.search(k))
    res, seen_ = [], set()
    for k in keys:
        v = m.get(k)
        if isinstance(v, str) and IDLIKE.match(v.strip()) and v.strip() not in seen_:
            seen_.add(v.strip())
            res.append((k, v.strip()))
    return res


def display_of(m, mid):
    for k in DISPLAY_FIELDS:
        v = m.get(k)
        if isinstance(v, str) and v.strip() and v.strip() != mid:
            return v.strip()[:120]
    return mid


def rows_from(p, ents, field=None):
    """4.5.3: one row per list entry. The ID comes from `field` when the entry has it (a field that worked before),
    else the first ID-like field in ID_FIELDS order. Each row keeps its other ID-like values for the quiet fallback."""
    rows = []
    for m in ents:
        ids = entry_ids(m)
        if field:
            ids.sort(key=lambda x: x[0] != field)
        if not ids:
            continue
        r = row_for(p, m, ids[0][1], display_of(m, ids[0][1]))
        r["id_field"], r["alt_ids"] = ids[0][0], [list(x) for x in ids[1:]]
        rows.append(r)
    return rows


def id_field(p):
    f = rj(IDF, {}).get(p) if idfix(p) else None
    return f if f in ID_FIELDS or (isinstance(f, str) and ID_EXTRA.search(f)) else None


def save_id_field(p, field):
    if not idfix(p):
        return
    d = rj(IDF, {})
    if field == ID_FIELDS[0]:
        d.pop(p, None)
    else:
        d[p] = field
    wj(IDF, d) if d else (os.path.exists(IDF) and os.remove(IDF))


def as_id(p, model, rows=None):
    """4.5.3: a saved or typed model that is a display name ("NVIDIA: Nemotron (free)") becomes that entry's real ID.
    Only for idfix companies; anything else comes back as it was."""
    if not idfix(p) or not model or model == "default" or (IDLIKE.match(model) and rows is None):
        return model
    rows = list_models(p) if rows is None else rows
    for r in rows or []:
        if r["id"] == model:
            return model
    for r in rows or []:
        if r["label"].lower() == model.lower() or any(v == model for _, v in r.get("alt_ids", [])):
            return r["id"]
    return model


def pick_best(p, rows):
    """Only a model that answered (or, failing that, a busy one) is ever the pick. Never a dead one."""
    g = good_models(p, annotate(p, rows))
    if g:
        return g[0]["id"]
    if p == "chatgpt" and any(r["id"] == "default" for r in rows):
        return "default"
    return None


def closest_free(p, dead, rows, skip=()):
    """A stand-in from the same company: answered models first, free ones when the company has free ones. Never a known-bad one."""
    annotate(p, rows)
    ok = [r for r in rows if r["usable"] and r["id"] != dead and r["id"] not in skip and r.get("status") in ("ok", "unchecked")
          and not r.get("hidden") and r["id"] != "default"]
    pool = [r for r in ok if r["free"]]   # stand-ins stay on free models, so a stand-in never costs extra
    answered = [r for r in pool if r.get("status") == "ok"]
    cands = [r["id"] for r in (answered or pool)]
    if not cands:
        return None
    fam = re.split(r"[-/:.]", dead)[0]
    return max(cands, key=lambda c: (c.split("/")[0] == dead.split("/")[0], c.startswith(fam), difflib.SequenceMatcher(None, dead, c).ratio()))


# ---------------------------------------------------------------- calls
def classify(code, text, p=None):
    """One word for how a call went: ok, dead, busy, key, noaccess, net, noanswer or (4.5.3, idfix companies only) badid."""
    t = str(text or "")
    if code == 0:
        return "net"
    if p and code in (400, 422) and BADID.search(t) and idfix(p):   # 4.5.3: the company didn't know this ID; never busy, key or net
        return "badid"
    if code == 429 or (code in (503, 529) and BUSY.search(t)) or (code in (400, 403) and BUSY.search(t) and not KEYBAD.search(t)):
        return "busy"
    if code in (404, 410) or (code in (400, 403, 422) and DEAD.search(t) and "model" in t.lower()):
        return "dead"
    if code == 403 and NOACCESS.search(t):
        return "noaccess"
    if code in (401, 403) or (code == 400 and KEYBAD.search(t)):
        return "key"
    return "noanswer"


def cli_kind(rc, o, e, ok):
    t = (o or "") + "\n" + (e or "")
    if ok:
        return "ok"
    if rc == 124 or NETERR.search(t):
        return "net"
    if DEAD.search(t) and "model" in t.lower():
        return "dead"
    if BUSY.search(t):
        return "busy"
    if NOT_IN.search(t) or KEYBAD.search(t):
        return "key"
    if NOACCESS.search(t):
        return "noaccess"
    return "noanswer"


def cli_seen(rc, o, e, ok):
    k = cli_kind(rc, o, e, ok)
    NETSEEN.transient = k == "net" or (k == "noanswer" and bool(GATEWAY.search((o or "") + "\n" + (e or ""))))
    return k


def call(p, model, prompt, thinking=None, timeout=120):
    """Returns (ok, text, kind). kind is ok, dead, busy, key, noaccess, net, timeout or noanswer.
    "timeout" means our own time limit ran out; "net" means the network failed. Setup checks treat both as net."""
    i = info(p)
    NETSEEN.timed_out = False
    t0 = time.monotonic()
    if p == "claude":
        a = ["claude", "-p", "--output-format", "text", "--tools", ""] + ([] if model in (None, "default") else ["--model", model])
        rc, o, e = run_cli(p, a, prompt, timeout)
        ok = rc == 0 and bool(o.strip())
        k = cli_seen(rc, o, e, ok)
        return cli_done(ok, o.strip() if ok else "", k, rc, o, e, timeout, t0)
    if p == "chatgpt":
        # One answer file per call: a fixed name let two codex runs at once (a debate and another ask) read or
        # delete each other's answer, which came back as an empty answer.
        os.makedirs(os.path.join(SB, "codex"), mode=0o700, exist_ok=True)
        last = os.path.join(SB, "codex", "last.%d.%s.txt" % (os.getpid(), uuid.uuid4().hex))
        a = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", last]
        if model not in (None, "default"):
            a += ["-m", model]
        if thinking:
            a += ["-c", 'model_reasoning_effort="%s"' % thinking]
        try:
            rc, o, e = run_cli(p, a + ["-"], prompt, timeout)
            try:
                with open(last) as f:
                    txt = f.read().strip()
            except OSError:
                txt = ""
        finally:   # never left behind, even after a timeout
            try:
                os.remove(last)
            except OSError:
                pass
        ok = rc == 0 and bool(txt)
        k = cli_seen(rc, o, e, ok)
        if rc == 0 and not txt:   # it finished but left no answer: empty, whatever its log lines said on the way
            k, NETSEEN.transient = "noanswer", False
        return cli_done(ok, txt if ok else "", k, rc, o, e, timeout, t0)
    if i["kind"] == "gemini":
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        if thinking:
            body["generationConfig"] = {"thinkingConfig": {"thinkingLevel": thinking} if model.startswith("gemini-3")
                                        else {"thinkingBudget": {"low": 1024, "medium": 4096, "high": 16384}[thinking]}}
        code, js = http("POST", base(p) + "/models/%s:generateContent" % model, auth(p), body, timeout)
        try:
            txt = "".join(x.get("text", "") for x in js["candidates"][0]["content"]["parts"] if not x.get("thought"))
        except (KeyError, IndexError, TypeError):
            txt = ""
    else:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if thinking:
            if p == "openrouter":
                body["reasoning"] = {"effort": thinking}
            else:
                body["reasoning_effort"] = thinking
        code, js = http("POST", base(p) + "/chat/completions", auth(p), body, timeout)
        try:
            txt = js["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            txt = ""
    NETSEEN.transient = False
    err = json.dumps(js.get("error", "")) if isinstance(js, dict) else ""
    NETSEEN.body = err
    timed = bool(getattr(NETSEEN, "timed_out", False))
    NETSEEN.detail = {"code": code, "timed_out": timed, "limit": timeout, "took": round(time.monotonic() - t0, 1),
                      "stderr": "" if code == 200 and txt.strip() else scrub(err[:200]),
                      "tail": "" if code == 200 and txt.strip() else tail_of(err), "empty": code == 200 and not txt.strip()}
    if code == 200 and txt.strip():
        return True, txt.strip(), "ok"
    if timed:
        return False, "", "timeout"
    kind = "noanswer" if code == 200 else classify(code, err, p)
    NETSEEN.transient = kind == "net" or (kind == "noanswer" and code in TRANSIENT)
    return False, "", kind


def cli_done(ok, txt, k, rc, o, e, timeout, t0):
    """The real reason for a CLI call, kept for the debug block: rc, timeout or not, the start of stderr, time, limit."""
    timed = bool(getattr(NETSEEN, "timed_out", False))
    err = re.sub(r"\s*\btimeout$", "", e or "").strip() if timed else (e or "").strip()
    NETSEEN.detail = {"rc": rc, "timed_out": timed, "limit": timeout, "took": round(time.monotonic() - t0, 1),
                      "stderr": scrub(err[:200]), "tail": tail_of(e, o), "empty": not ok and not timed and (rc == 0 or not (o + e).strip())}
    if timed and not ok:
        NETSEEN.transient = False
        return False, "", "timeout"
    return ok, txt, k


# ---------------------------------------------------------------- probes (which models really answer)
def probes():
    return rj(PROBE, {})


def cached(p, m, now=None):
    e = probes().get(p, {}).get(m)
    now = now or time.time()
    if isinstance(e, dict) and now - e.get("at", 0) <= PROBE_TTL.get(e.get("status"), 0):
        return e["status"]
    return None


PROBE_LOCK = threading.Lock()


def remember(p, m, kind):
    if kind not in PROBE_TTL or not m or m == "default":
        return
    with PROBE_LOCK:
        d = probes()
        d.setdefault(p, {})[m] = {"status": kind, "at": int(time.time())}
        wj(PROBE, d)


def forget(p):
    with PROBE_LOCK:
        d = probes()
        if d.pop(p, None) is not None:
            wj(PROBE, d) if d else os.remove(PROBE)
    if os.path.exists(IDF):   # 4.5.3: the ID field that worked goes with the company's other results
        d = rj(IDF, {})
        if d.pop(p, None) is not None:
            wj(IDF, d) if d else os.remove(IDF)


def probe_one(p, m, fresh=False):
    """One tiny call, unless a fresh result is cached. Returns (kind, called)."""
    k = cached(p, m) if not fresh else None
    if k:
        return k, False
    kind = check_call(p, m)
    remember(p, m, kind)
    return kind, True


def check_call(p, m):
    """The tiny test call, with quiet retries. A network failure that survived its retries reads as net."""
    tmo = PROBE_CLI_TIMEOUT if info(p)["kind"] == "cli" else PROBE_TIMEOUT
    kind, bad = retrying(lambda t: (lambda k: ("net", True) if k == "timeout" else (k, getattr(NETSEEN, "transient", False)))(call(p, m, PROBE_PROMPT, None, t)[2]), tmo, "net")
    return "net" if bad else kind


def gemini_rank(m):
    """Which Gemini model to recommend (unchanged from 4.5): newest version first, then pro, flash, lite."""
    v = re.match(r"gemini-(\d+(?:\.\d+)?)", m)
    tier = 0 if "-pro" in m else (2 if "lite" in m else (1 if "flash" in m else 3))
    return (0 if v else 1, -float(v.group(1)) if v else 0, "preview" in m or "exp" in m, tier, m)


def gemini_probe_rank(m):
    """4.5.1, probe order only: cheap fast ones first (flash-lite, then flash, then the rest, then pro), newest first inside each;
    preview, experimental and customtools variants after all of those. Unversioned names come last."""
    v = re.match(r"gemini-(\d+(?:\.\d+)?)", m)
    tier = 0 if "lite" in m else (1 if "flash" in m else (3 if "-pro" in m else 2))
    side = bool(re.search(r"preview|exp|customtools", m))
    return (0 if v else 1, side, tier, -float(v.group(1)) if v else 0, m)


def ranked(p, rows):
    """Best candidates first. Only rows that could be used, never hidden ones or ChatGPT's default."""
    use = [r for r in rows if r["usable"] and not r.get("hidden") and r["id"] != "default"]
    if p == "gemini":
        return sorted(use, key=lambda r: gemini_rank(r["id"]))
    def score(r):
        for n, pat in enumerate(BEST.get(p, [])):
            if r["id"] == pat or (pat.startswith(":") and r["id"].endswith(pat)) or r["id"].startswith(pat):
                return n
        return len(BEST.get(p, []))
    return sorted(use, key=score)   # stable: list order inside each score


def list_ok(p):
    """True when this company's models came from a list call that answered 200 (not Claude, ChatGPT or a fixed list)."""
    return info(p)["kind"] != "cli" and not info(p).get("static")


def model_kind(code, body, timed, p=None):
    """4.5.1: one model's tiny call after the list call worked. Returns (kind, rule). A timeout, 429 or 503 is that
    model being busy, never the network or the key. "keybad" counts toward a key verdict only on two different models."""
    t = str(body or "")
    if timed:
        return "busy", "timeout"
    if code == 200:
        return "noanswer", "200 with no text"
    if code == 0:
        return "noanswer", "network error on this model"
    if code == 429:
        return "busy", "429"
    if p and code in (400, 422) and BADID.search(t) and idfix(p):   # 4.5.3: before busy, gone, key and no-access
        return "badid", "%d not a valid model ID" % code
    if code in (503, 529):
        return "busy", "%d" % code
    if code in (400, 403) and BUSY.search(t) and not KEYSAYS.search(t):
        return "busy", "%d with busy words" % code
    if code in (404, 410):
        return "dead", "%d" % code
    if code in (400, 403, 422) and DEAD.search(t) and "model" in t.lower():
        return "dead", "%d with gone-model words" % code
    if code == 401:
        return "keybad", "401"
    if code in (400, 403) and KEYSAYS.search(t):
        return "keybad", "%d with bad-key words" % code
    if code in (400, 403):
        return "noaccess", "%d on this model only" % code
    return "noanswer", "%d other" % code


def sim_took(t0, tmo, failed):
    """Seconds one probe call took. With the test clock a timeout or network failure counts as its full limit,
    and SB_TEST_TIMEOUT_SCALE turns scaled real time back into model time."""
    real = time.monotonic() - t0
    if not fake_clock():
        return real
    if failed:
        return float(tmo)
    sc = os.environ.get("SB_TEST_TIMEOUT_SCALE")
    return real / float(sc) if sc else real


def probe_model(p, m, left):
    """One model, list OK: a tiny call; a network or gateway error is retried after 3, 8, 15 s and an empty answer once
    (from the check's shared retry budget of 4; 429, 503 and timeouts never use it). Returns (kind, rule, spent, tries)."""
    spent, tries = 0.0, []
    while True:
        tmo = max(1, min(PROBE_TIMEOUT, int(left - spent)))
        NETSEEN.detail, NETSEEN.body = {}, ""
        t0 = time.monotonic()
        ok, _, k = call(p, m, PROBE_PROMPT, None, tmo)
        d = dict(getattr(NETSEEN, "detail", {}) or {})
        code, timed = d.get("code"), k == "timeout"
        kind, rule = ("ok", "200 with an answer") if ok else model_kind(code, getattr(NETSEEN, "body", ""), timed, p)
        took = sim_took(t0, tmo, timed or code == 0)
        spent += took
        tries.append({"model": m, "attempt": len(tries) + 1, "status": code, "timed_out": timed, "limit": tmo,
                      "took": round(took, 1), "kind": kind, "rule": rule, "body": "" if ok else scrub(str(getattr(NETSEEN, "body", ""))[:200])})
        n = len(tries)   # a dropped connection or gateway error: quiet retries as in 4.5; an empty answer: one
        again = not ok and not timed and ((code in GATE_RETRY and n <= len(NET_WAITS)) or (code == 200 and n == 1))
        wait = NET_WAITS[min(n, len(NET_WAITS)) - 1]
        if again:
            with PROBE_LOCK:
                again = CHECK["left"] > 0 and left - spent - wait >= 5
                if again:
                    CHECK["left"] -= 1; CHECK["retries"] += 1; CHECK["waited"] += wait
        if not again:
            return kind, rule, spent, tries
        if not fake_clock():
            time.sleep(wait)
        spent += wait


PROBE_DEBUG = []   # 4.5.1: every probe try of the last check (status, scrubbed body, the rule that fired), for `debug`


def probe_par(p, rows, want, fresh):
    """4.5.1, list OK: up to PROBE_PAR tiny calls at a time, best first. A new call starts only while the answers so far
    plus the calls in flight are short of `want`, so the same answers always give the same calls. At most
    PROBE_MAX_CALLS calls. "key" only when two different models say the key is bad; one is that model's problem."""
    cands = ranked(p, rows)
    if p == "gemini":
        cands = sorted(cands, key=lambda r: gemini_probe_rank(r["id"]))
    lk = threading.Lock()
    st = {"i": 0, "calls": 0, "good": 0, "flying": 0, "keybad": [], "kinds": []}
    lanes = [0.0] * PROBE_PAR
    start_left = time_left()

    def take(w):
        with lk:
            while st["i"] < len(cands):
                if st["good"] >= want or len(st["keybad"]) >= 2 or st["good"] + st["flying"] >= want:
                    return None
                r = cands[st["i"]]
                k = None if fresh else cached(p, r["id"])
                if k:
                    st["i"] += 1; st["good"] += k == "ok"
                    continue
                if st["calls"] >= PROBE_MAX_CALLS or start_left - lanes[w] < 1:
                    return None
                st["i"] += 1; st["calls"] += 1; st["flying"] += 1
                return r
            return None

    def work(w):
        while True:
            r = take(w)
            if r is None:
                return
            kind, rule, spent, tries = probe_model(p, r["id"], start_left - lanes[w])
            lanes[w] += spent
            with lk:
                st["flying"] -= 1
                st["good"] += kind == "ok"
                st["kinds"].append((kind, rule))
                if kind == "keybad":
                    st["keybad"].append(r["id"])
                PROBE_DEBUG.extend(tries)
            remember(p, r["id"], "noaccess" if kind == "keybad" else kind)

    ts = [threading.Thread(target=work, args=(w,)) for w in range(PROBE_PAR)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    if fake_clock():
        CHECK["fake"] += max(lanes)
    PROBE_DEBUG.sort(key=lambda x: ([r["id"] for r in cands].index(x["model"]), x["attempt"]))
    if len(st["keybad"]) >= 2:
        forget(p)
        return {"calls": st["calls"], "stop": "key"}
    return {"calls": st["calls"], "stop": None, "kinds": st["kinds"]}


ID_DEBUG = {}   # 4.5.3: the quiet ID-field fallback of the last check, for `debug`


def id_problem(kinds):
    """4.5.3: every probe failed the same way: "not a valid model ID", or a 404 for models the list just showed."""
    if not kinds:
        return None
    if all(k == "badid" for k, _ in kinds):
        return "every probe said not a valid model ID"
    if len(kinds) >= 2 and all(k == "dead" and r == "404" for k, r in kinds):
        return "every probe got 404 for models the list just showed"
    return None


def id_fallback(p, rows, rule):
    """4.5.3, idfix companies only, quiet: the list's other ID-like fields, best field first, at most ID_TRY_FIELDS
    fields and ID_TRY_CALLS tiny calls (2 models per field), one at a time inside the check's time cap.
    A field that works is remembered (idfield.json) and `rows` is rebuilt with it. Returns the field or None."""
    ID_DEBUG.clear()
    ID_DEBUG.update({"rule": rule, "first_field": (rows[0].get("id_field") if rows else None), "tried": [], "result": None})
    cands = {}
    for r in ranked(p, rows):
        for fld, v in r.get("alt_ids", []):
            if v != r["id"]:
                cands.setdefault(fld, []).append(v)
    order = [f for f in list(ID_FIELDS) + sorted(cands) if f in cands]
    order = list(dict.fromkeys(order))[:ID_TRY_FIELDS]
    calls = 0
    for fld in order:
        for v in cands[fld][:2]:
            if calls >= ID_TRY_CALLS or time_left() < 5:
                break
            kind, why_, spent, tries = probe_model(p, v, min(time_left(), PROBE_TIMEOUT * 2))
            calls += 1
            PROBE_DEBUG.extend(dict(t, field=fld) for t in tries)
            ID_DEBUG["tried"].append({"field": fld, "model": v, "status": tries[-1]["status"], "kind": kind, "rule": why_,
                                      "body": tries[-1]["body"]})
            if kind in ("ok", "busy"):
                save_id_field(p, fld)
                with PROBE_LOCK:   # the old IDs' 404 marks belonged to the wrong field
                    d = probes()
                    for r in rows:
                        d.get(p, {}).pop(r["id"], None)
                    wj(PROBE, d) if d else (os.path.exists(PROBE) and os.remove(PROBE))
                rows[:] = rows_from(p, LIST.get("raw") or [], fld)
                remember(p, v, kind)
                ID_DEBUG["result"] = "field %s worked" % fld
                return fld
            if kind == "keybad":
                break
    ID_DEBUG["result"] = "no other ID field worked" if order else "the list has no other ID field"
    ID_DEBUG["calls"] = calls
    return None


def probe(p, rows, want=PROBE_WANT, fresh=False):
    """Tiny calls, best first, until `want` models answered or the call cap is hit.
    fresh=True (the setup test and its "Try again") ignores cached results.
    Returns {"calls": n, "stop": None|"key"|"net"}. Companies whose list call worked use probe_par (never "net")."""
    if list_ok(p):
        r = probe_par(p, rows, want, fresh)
        rule = idfix(p) and not r["stop"] and id_problem(r.get("kinds"))
        if rule:   # 4.5.3: quietly, the other ID fields; a different field that works is used from now on
            fld = id_fallback(p, rows, rule)
            if fld is None and rule.startswith("every probe said"):
                r["stop"] = "badid"
            r["id_field"] = fld
        r.pop("kinds", None)
        return r
    cap = PROBE_MAX_CLI if info(p)["kind"] == "cli" else PROBE_MAX_CALLS
    calls, good, nets = 0, 0, 0
    for r in ranked(p, rows):
        if good >= want:
            break
        k = None if fresh else cached(p, r["id"])
        if not k:
            if calls >= cap:
                break
            if time_left() < 1:   # the check's time cap is used up
                return {"calls": calls, "stop": "net" if nets else None}
            k, _ = probe_one(p, r["id"], fresh)
            calls += 1
        if k == "key":
            return {"calls": calls, "stop": "key"}
        nets = nets + 1 if k == "net" else 0
        if nets >= 2:
            return {"calls": calls, "stop": "net"}
        good += k == "ok"
    return {"calls": calls, "stop": None}


def annotate(p, rows):
    """Mark each row with what the probes found. Dead, no-access and silent models can't be used."""
    for r in rows:
        if not r["usable"] or r["id"] == "default":
            continue
        k = cached(p, r["id"])
        r["status"] = k or "unchecked"
        if k in ("dead", "noaccess", "noanswer"):
            r["usable"], r["reason"] = False, REASONS[k]
    return rows


def good_models(p, rows):
    """Answered first (best first), then busy ones. Only these are ever shown or recommended."""
    rk = ranked(p, rows)
    return [r for r in rk if r.get("status") == "ok"] + [r for r in rk if r.get("status") == "busy"]


def ask_wait(s):
    """Test hook: with SB_TEST_CLOCK=1 the wait only counts, it doesn't sleep."""
    if not fake_clock():
        time.sleep(s)


def call_retry(p, model, prompt, thinking, timeout, budget=None):
    """call() with quiet retries for an ask or a debate. A network-type error or an empty answer is tried again
    after ASK_WAITS, within the call's timeout plus ASK_EXTRA. A call that ran out of time gets one more try with
    TIMEOUT_GROW times the limit, within `budget` (what is left of the debate's DEBATE_CAP). At most 3 tries.
    A wrong key, a busy model and a gone model are not retried here (ask_one gives a busy one its own second try).
    4.5.2: a 503 or 529 counts as busy on this path. Returns (ok, text, kind, debug)."""
    budget = DEBATE_CAP if budget is None else budget
    if budget < 10:   # 4.5.2: the debate's time is used up: no new try starts
        return False, "", "timeout", {"attempts": [{"kind": "timeout", "attempt": 0, "limit": 0, "elapsed": 0, "skipped": "no time left"}],
                                      "succeeded_on": None, "elapsed": 0}
    spent, tries, tmo, waits, grown = 0.0, [], int(min(timeout, budget)), list(ASK_WAITS), False
    while True:
        NETSEEN.detail, NETSEEN.transient = {}, False
        t0 = time.monotonic()
        ok, txt, kind = call(p, model, prompt, thinking, tmo)
        took = time.monotonic() - t0
        d = dict(getattr(NETSEEN, "detail", {}) or {})
        d.pop("took", None)
        kind = busy_kind(ok, kind, d)
        timed = kind == "timeout"
        again = not ok and not timed and kind != "busy" and (kind == "net" or getattr(NETSEEN, "transient", False) or bool(d.get("empty")))
        if fake_clock() and (again or timed):
            took = tmo   # the test clock counts each such failure as a full timeout
        spent += took
        tries.append(dict(d, kind=kind, attempt=len(tries) + 1, limit=tmo, elapsed=round(took, 1)))
        if ok or len(tries) > len(ASK_WAITS):
            break
        if timed:   # once, with a longer limit; never past the debate's budget
            left = budget - spent
            if grown or left < timeout:
                break
            grown, tmo = True, int(min(timeout * TIMEOUT_GROW, left))
            continue
        if not again or not waits:
            break
        w = waits.pop(0)
        left = min(timeout + ASK_EXTRA, budget) - spent - w
        if left < 10:
            break
        ask_wait(w); spent += w
        tmo = max(5, min(timeout, int(left)))
    return ok, txt, kind, {"attempts": tries, "succeeded_on": len(tries) if ok else None, "elapsed": round(spent, 1)}


def busy_kind(ok, kind, d):
    """4.5.2, asks and debates only: a 503 or 529 means the company's servers are busy, not a network failure."""
    if not ok and kind in ("noanswer", "net") and (d.get("code") in (503, 529) or (d.get("rc") not in (None, 0) and BUSY503.search(d.get("stderr") or ""))):
        return "busy"
    return kind


def one_try(p, model, prompt, thinking, tmo):
    """One plain call for the busy fallback. Returns (ok, text, kind, seconds, debug entry). The test clock counts a timeout in full."""
    NETSEEN.detail, NETSEEN.transient = {}, False
    t0 = time.monotonic()
    ok, txt, kind = call(p, model, prompt, thinking, tmo)
    took = time.monotonic() - t0
    d = dict(getattr(NETSEEN, "detail", {}) or {})
    kind = busy_kind(ok, kind, d)
    if fake_clock() and kind == "timeout":
        took = tmo
    if kind in ("ok", "dead", "busy", "noaccess"):
        remember(p, model, kind)
    return ok, txt, kind, took, {"model": model, "status": d.get("code", d.get("rc")), "kind": kind, "took": round(took, 1), "limit": tmo}


def alternates(p, model):
    """4.5.2: other models from the same company for a busy one. Ones that answered recently come first (best first), then
    the rest: not checked yet, then busy ones (busy comes and goes), lighter ones first for Gemini. Never a gone, blocked
    or silent one, never a hidden one or ChatGPT's default. HTTP companies stay on their free models, as stand-ins always
    did, so a company with only paid models gets no alternates. Claude and ChatGPT use the other models of the plan.
    Returns [(model, cache status, thinking levels)]."""
    cli = info(p)["kind"] == "cli"
    rows = list_models(p)
    if rows is None:   # the list can't be read: what the probes saw
        rows = [{"id": m, "label": m, "usable": True, "reason": "", "thinking": [], "free": free_model(p, m, {})} for m in probes().get(p, {})]
    annotate(p, rows)
    use = [r for r in ranked(p, rows) if r["id"] != model]
    if not cli:
        use = [r for r in use if r.get("free")]
    good = [r for r in use if r.get("status") == "ok"]
    rest = [r for r in use if r.get("status") != "ok"]
    if p == "gemini":
        rest.sort(key=lambda r: gemini_probe_rank(r["id"]))
    rest.sort(key=lambda r: r.get("status") == "busy")   # stable: unchecked ones before busy ones
    return [(r["id"], r.get("status") or "unchecked", r.get("thinking") or []) for r in good + rest]


def servers(p):
    return "%s's servers were busy" % SERVERS.get(p, info(p)["name"])


def sit_out_line(p, model, kind, tried):
    """The plain note when a busy model and the other models tried for it all failed."""
    name = info(p)["name"]
    first = servers(p) if kind == "busy" else "%s didn't answer in time" % model
    if not tried and kind != "badid":
        return "%s sat this one out: %s." % (name, first)
    ks = {t["kind"] for t in tried}
    other = "the other %s model%s" % (name, "s" if len(tried) > 1 else "")
    if kind == "badid":   # 4.5.3: never "busy": the ID wasn't one the company knows
        first = "%s's model list didn't match what SuperBot expected" % name
        if not tried:
            return "%s sat this one out: %s." % (name, first)
    if ks <= {"badid"}:
        rest = "%s I tried didn't match either" % other
    elif ks <= {"busy"}:
        rest = "%s %s busy too" % (other, "were" if len(tried) > 1 else "was")
    elif ks <= {"busy", "timeout"}:
        rest = "%s %s busy or too slow too" % (other, "were" if len(tried) > 1 else "was")
    else:
        rest = "%s I tried didn't answer either" % other
    return "%s sat this one out: %s, and %s." % (name, first, rest)


def save_model(p, model, was):
    """4.5.3: the saved model `was` becomes the ID the company accepts (idfix companies only)."""
    c = cfg()
    if idfix(p) and c.get("connected", {}).get(p, {}).get("model") == was:
        c["connected"][p]["model"] = model
        wj(CFG, c, 0o644)


def re_resolve(p, model, prompt, thinking, timeout, left, dbg):
    """4.5.3: the company said "not a valid model ID" for the saved model. A fresh list, once: the same entry's other
    ID-like values, at most ID_ASK_TRIES calls. A model gone from the list is treated as gone (4.5.2 stand-ins).
    Returns (ok, text, kind, model, seconds)."""
    rows = list_models(p) or []
    r = next((r for r in rows if r["id"] == model or r["label"].lower() == model.lower() or
              any(v == model for _, v in r.get("alt_ids", []))), None)
    info_ = {"from": model, "listed": bool(r), "tries": []}
    dbg["remap"] = info_
    if not r:
        return False, "", ("dead" if rows else "badid"), model, 0
    cands = [(r.get("id_field"), r["id"])] + [tuple(x) for x in r.get("alt_ids", [])]
    cands = [x for x in cands if x[1] != model][:ID_ASK_TRIES]
    spent = 0
    for fld, mid in cands:
        tmo = int(min(ALT_TIMEOUT, timeout, left - spent))
        if tmo < 10:
            break
        ok, txt, k, took, d = one_try(p, mid, prompt, thinking, tmo)
        spent += took
        info_["tries"].append(dict(d, field=fld))
        if k != "badid":   # the company knows this ID: keep it, even if it is busy right now
            save_id_field(p, fld)
            save_model(p, mid, model)
            dbg["remapped"] = {"from": model, "to": mid, "field": fld, "kind": k}
            return ok, txt, k, mid, spent
    return False, "", "badid", model, spent


def ask_one(p, prompt, model=None, thinking=None, timeout=120, budget=None, keep=0):
    c = cfg()["connected"].get(p)
    name = info(p)["name"]
    if not c:
        return {"provider": p, "ok": False, "line": "%s isn't connected. Say 'add %s' to set it up." % (name, name)}
    model = model or c.get("model")
    thinking = thinking or c.get("thinking")
    budget = DEBATE_CAP if budget is None else budget
    shown = None
    if idfix(p) and model and not IDLIKE.match(model):   # 4.5.3: a saved display name is sent as its real ID
        m2 = as_id(p, model)
        if m2 != model:
            shown, model = model, m2
            save_model(p, model, shown)
    ok, txt, kind, dbg = call_retry(p, model, prompt, thinking, timeout, budget)
    extra = budget - keep   # 4.5.2: the busy retry and the other models leave `keep` seconds for the debate's later steps
    if shown:
        dbg["display_name_mapped"] = {"from": shown, "to": model}
    if kind in ("ok", "dead", "busy", "noaccess"):
        remember(p, model, kind)
    spent = dbg["elapsed"]
    if kind == "badid":   # 4.5.3 (idfix companies only): re-read the list once and try this model's other IDs
        ok, txt, kind, model, took = re_resolve(p, model, prompt, thinking, timeout, extra - spent, dbg)
        spent += took
    if kind == "busy":   # 4.5.2: busy comes and goes: the same model once more after a short pause
        tmo = int(min(timeout, extra - spent - BUSY_PAUSE))
        if tmo >= 10:
            ask_wait(BUSY_PAUSE)
            ok, txt, k2, took, d = one_try(p, model, prompt, thinking, tmo)
            spent += BUSY_PAUSE + took
            dbg["busy_retry"] = dict(d, pause=BUSY_PAUSE)
            kind = k2 if k2 in ("ok", "key") else "busy"
    res = {"provider": p, "model": model, "ok": ok, "answer": txt if ok else "", "kind": kind,
           "debug": dict(dbg, not_for_display=True)}   # the real reason for each try; never shown
    if ok:
        res["debug"]["elapsed"] = round(spent, 1)
        return res
    if kind in ("busy", "timeout", "badid"):   # 4.5.2: other models from the same company, quietly, within bounds
        tried = []
        for m, st, levels in alternates(p, model):
            if len(tried) >= ALT_MAX:
                break
            tmo = int(min(ALT_TIMEOUT_CLI if info(p)["kind"] == "cli" else ALT_TIMEOUT, timeout, extra - spent))
            if tmo < 10:
                break
            ok2, txt2, k2, took, d = one_try(p, m, prompt, thinking if thinking in levels else None, tmo)
            spent += took
            tried.append(dict(d, cache=st))
            if ok2:
                res.update({"ok": True, "answer": txt2, "standin": {"from": model, "to": m, "why": kind}})
                res["line"] = "%s answered with %s because %s %s." % (name, m, model, "was busy" if kind == "busy" else "didn't answer in time"
                                                                     if kind != "badid" else "didn't match %s's model list" % name)
                break
            if k2 == "key":   # a key problem is not busy: stop
                break
        res["debug"]["alternates"] = tried
        res["debug"]["elapsed"] = round(spent, 1)
        if not res["ok"]:
            res["line"] = sit_out_line(p, model, kind, tried)
        return res
    if kind == "key":
        res["line"] = "%s didn't accept its key or sign-in. Say 'add %s' to connect it again." % (name, name)
        return res
    if kind == "net":
        res["line"] = "I couldn't reach %s just now." % name
        return res
    if kind not in ("dead", "noaccess"):
        res["line"] = "%s didn't answer this time." % name
        return res
    # a gone or blocked model (never retried): as in 4.5.1, up to two free stand-ins and the switch card
    rows = list_models(p) or []
    tried = []
    for _ in range(2):
        sub = closest_free(p, model, rows, tried)
        if not sub:
            break
        th = thinking if thinking in next((r["thinking"] for r in rows if r["id"] == sub), []) else None
        ok2, txt2, k2 = call(p, sub, prompt, th, timeout)
        remember(p, sub, k2)
        if ok2:
            res.update({"ok": True, "answer": txt2, "standin": {"from": model, "to": sub, "why": kind}})
            res["switch"] = {"id": p, "to": sub}
            res["line"] = "%s isn't available right now, so I used %s from %s instead. Want me to keep using %s?" % (model, sub, name, sub)
            return res
        tried.append(sub)
    res["line"] = "%s isn't available right now, so %s sat this one out." % (model, name)
    return res


# ---------------------------------------------------------------- setup journal
def journal(p):
    return rj(os.path.join(PEND, p + ".json"), {})


def begin(p, other=None):
    j = {"provider": p, "started": time.time(), "added": []}
    if other:
        j["other"] = other
    wj(os.path.join(PEND, p + ".json"), j)
    return j


def jadd(p, path):
    j = journal(p)
    j.setdefault("added", []).append(path)
    wj(os.path.join(PEND, p + ".json"), j)


def abort(p):
    j = journal(p)
    c = rj(CFG, {})
    if p not in c.get("connected", {}) and p not in c.get("parked", {}):
        forget(p)   # probe results for a company that never connected don't stay behind
    for path in reversed(j.get("added", [])):
        if path.startswith(SB + os.sep):
            shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else (os.path.exists(path) and os.remove(path))
    for suf in (".key", ".json", ".log", ".in", ".rc"):
        f = os.path.join(PEND, p + suf)
        if os.path.exists(f):
            os.remove(f)
    if os.path.isdir(PEND) and not os.listdir(PEND):
        os.rmdir(PEND)
    if os.path.isdir(SB) and not os.listdir(SB):
        os.rmdir(SB)


def pend_age(f):
    """Seconds since a half-finished setup began (its journal's start time, else the file's time)."""
    j = rj(f, {})
    t = j.get("started") if isinstance(j, dict) else None
    try:
        t = float(t) if t else os.path.getmtime(f)
    except (TypeError, ValueError, OSError):
        t = 0
    return time.time() - t


def cleanup():
    """Run by `status`: rolls back half-finished setups. 4.5.1: one younger than PEND_FRESH (30 minutes) is still
    in progress (the owner may be fetching a key), so it and its files are kept."""
    done, keep = [], set()
    if os.path.isdir(PEND):
        for f in sorted(os.listdir(PEND)):
            if f.endswith(".json"):
                if pend_age(os.path.join(PEND, f)) < PEND_FRESH:
                    keep.add(f[:-5])
                    continue
                abort(f[:-5])
                done.append(f[:-5])
        for f in sorted(os.listdir(PEND)) if os.path.isdir(PEND) else []:
            if f.split(".")[0] in keep:
                continue
            fp = os.path.join(PEND, f)   # orphans (a key, log or temp file whose journal is gone)
            shutil.rmtree(fp, ignore_errors=True) if os.path.isdir(fp) else os.remove(fp)
            done.append(f)
        if os.path.isdir(PEND) and not os.listdir(PEND):
            os.rmdir(PEND)
    for d in (SB, os.path.join(SB, "bin")):
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.endswith(".tmp"):
                os.remove(os.path.join(d, f))
                done.append(f)
    return done


def park(p):
    """The key was accepted but no model answered: keep the key so the owner doesn't paste it again."""
    j = journal(p)
    k = rj(os.path.join(PEND, p + ".key"), {}).get("k")
    if k:
        ks = rj(KEYS, {})
        ks[p] = k
        wj(KEYS, ks)
    c = cfg()
    e = {"name": info(p)["name"], "since": time.strftime("%Y-%m-%d")}
    e.update(j.get("other") or {})
    c.setdefault("parked", {})[p] = e
    wj(CFG, c, 0o644)


def commit(p, model, thinking=None):
    j = journal(p)
    if not j:
        out({"error": "no setup open"}, 4)
    c = cfg()
    entry = {"model": model, "thinking": thinking, "name": info(p)["name"], "since": time.strftime("%Y-%m-%d")}
    if j.get("other"):
        entry.update(j["other"])
    if p == "chatgpt":
        entry["images"] = True
    k = rj(os.path.join(PEND, p + ".key"), {}).get("k")
    if k:
        ks = rj(KEYS, {})
        ks[p] = k
        wj(KEYS, ks)
    c["connected"][p] = entry
    c.get("parked", {}).pop(p, None)
    c.setdefault("added", {})[p] = j.get("added", [])
    wj(CFG, c, 0o644)
    for suf in (".key", ".json", ".log", ".in", ".rc"):
        f = os.path.join(PEND, p + suf)
        if os.path.exists(f):
            os.remove(f)
    return entry


# ---------------------------------------------------------------- sign-in (Claude, ChatGPT)
SIGNIN = {"claude": (["claude", "auth", "login", "--claudeai"], ["claude", "auth", "status", "--json"]),
          "chatgpt": (["codex", "login", "--device-auth"], ["codex", "login", "status"])}


def pty_child(p):
    import pty
    log, fifo = os.path.join(PEND, p + ".log"), os.path.join(PEND, p + ".in")
    pid, fd = pty.fork()
    if pid == 0:
        env = child_env(p)
        os.execvpe(SIGNIN[p][0][0], SIGNIN[p][0], env)
    import termios
    try:
        t = termios.tcgetattr(fd)
        t[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, t)
    except termios.error:
        pass
    inp = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    end = time.time() + 900
    with open(log, "a") as L:
        while time.time() < end:
            r, _, _ = select.select([fd, inp], [], [], 1)
            if fd in r:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                L.write(scrub(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", data.decode(errors="replace"))))
                L.flush()
            if inp in r:
                d = os.read(inp, 4096)
                if d:
                    os.write(fd, d)
        try:
            if time.time() >= end:
                os.kill(pid, 9)
            _, st = os.waitpid(pid, 0)
        except (ChildProcessError, OSError):
            st = 0
    rc = os.waitstatus_to_exitcode(st) if st else 0
    with open(os.path.join(PEND, p + ".rc"), "w") as f:
        f.write(str(rc))


def signin(p, step, env_name=None):
    log, fifo = os.path.join(PEND, p + ".log"), os.path.join(PEND, p + ".in")
    if step == "start":
        home = os.path.join(SB, "claude" if p == "claude" else "codex")
        if not os.path.exists(home):
            os.makedirs(home, mode=0o700)
            jadd(p, home)
        if not os.path.exists(fifo):
            os.mkfifo(fifo, 0o600)
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "_pty", p], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        end = time.time() + 30
        while time.time() < end:
            t = open(log).read() if os.path.exists(log) else ""
            url = re.search(r"https://\S+", t)
            code = re.search(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b", t)
            if url and (p == "claude" or code):
                return {"url": url.group(0), "code": code.group(0) if (code and p == "chatgpt") else None}
            time.sleep(0.3)
        return {"error": "no link", "line": "%s didn't give me a sign-in link. Try again or skip for now." % P[p]["name"]}
    if step == "code":
        v = os.environ.get(env_name or "", "")
        if not v:
            return {"error": "no code"}
        _secrets.append(v)
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, (v.strip() + "\r").encode())
        os.close(fd)
        return {"sent": True}
    if step == "wait":
        end = time.time() + 900
        while time.time() < end and not os.path.exists(os.path.join(PEND, p + ".rc")):
            time.sleep(0.5)
        good = False
        for n in range(3):   # the status can lag a moment behind the sign-in
            good = signed_in(*run_cli(p, SIGNIN[p][1], timeout=30))
            if good or os.environ.get("SB_TEST_FAST"):
                break
            time.sleep(2)
        return {"signed_in": good}
    return {"error": "bad step"}


def install_cli(p):
    pkg, ver, binname = PINS[p]
    if os.path.exists(os.path.join(NPM, "node_modules", ".bin", binname)):
        return {"installed": True, "new": False}
    new = not os.path.exists(NPM)
    os.makedirs(SB, mode=0o700, exist_ok=True)
    if new:
        jadd(p, NPM)
    r = subprocess.run(["npm", "install", "--prefix", NPM, "--no-audit", "--no-fund", "%s@%s" % (pkg, ver)],
                       capture_output=True, text=True, env=child_env(p))
    return {"installed": r.returncode == 0, "new": new}


# ---------------------------------------------------------------- cards
# Chat widget: one question per card, at most 6 options. A dismissed card counts as a decline.
# There are no multi-step cards: the widget tool rejected one live, so the helper never prints "steps".
HELLO = "Hi, I'm SuperBot. I connect the AIs you use, so you and your other bots can ask them by name."
AGAIN = "Here's the list again whenever you're ready."

SINGLE_MAX = 6    # the six-row Pick card is proven live
SINGLE_PREF = 4   # every other card stays at 4 options or fewer
LABEL_MAX, DESC_MAX, PROMPT_MAX = 40, 80, 200
MODEL_SHOW = 3
PROVEN_LABELS = {OTHER_ROW}   # 41 characters, shown live on the Pick card
WIDGET_KEYS = ("prompt", "options", "multiSelect", "allowCustom")   # the only widget keys the helper prints
OPT_KEYS = {"label", "description", "value", "style"}
STYLES = {"default", "primary", "danger"}
CUSTOM_HINT = "custom_label"   # beside the widget, never in it: the widget has no typed-box label


def short(label, alt=""):
    for x in (label, alt):
        if x and len(x) <= LABEL_MAX:
            return x
    x = label or alt
    return x[:LABEL_MAX - 3] + "..."


def opt(label, value, desc=None):
    o = {"label": label, "value": value}
    if desc:
        o["description"] = desc
    return o


def card(cid, prompt, options, multi=False, custom=None):
    """One question. Prints {prompt, options, multiSelect, allowCustom}; card_id and custom_label ride beside it."""
    d = {"widget": {"prompt": prompt, "options": options, "multiSelect": multi, "allowCustom": bool(custom)}, "card_id": cid}
    if custom:
        d[CUSTOM_HINT] = custom
    return d


def yes_no(cid, prompt, yes, no, custom=None):
    return card(cid, prompt, [opt(yes, "yes"), opt(no, "no")], False, custom)


def card_problems(w, hint=None, cid=None):
    if not isinstance(w, dict):
        return ["not a card"]
    bad = []
    if "steps" in w:
        bad.append("steps are not allowed")
    extra = sorted(set(w) - set(WIDGET_KEYS))
    if extra:
        bad.append("unknown keys: %s" % ", ".join(extra))
    pr = w.get("prompt")
    if not isinstance(pr, str) or not pr.strip() or len(pr) > PROMPT_MAX:
        bad.append("prompt length")
    if not isinstance(w.get("multiSelect"), bool) or not isinstance(w.get("allowCustom"), bool):
        bad.append("multiSelect and allowCustom must be true or false")
    if w.get("allowCustom") and not (isinstance(hint, str) and 0 < len(hint) <= LABEL_MAX):
        bad.append("typed box needs a short hint")
    o = w.get("options")
    most = SINGLE_MAX if cid == "pick" else SINGLE_PREF
    if not isinstance(o, list) or not 1 <= len(o) <= most:
        return bad + ["%s options (most %d)" % (len(o) if isinstance(o, list) else "no", most)]
    vals = []
    for x in o:
        if not isinstance(x, dict):
            bad.append("option is not an object")
            continue
        if set(x) - OPT_KEYS:
            bad.append("unknown option keys: %s" % ", ".join(sorted(set(x) - OPT_KEYS)))
        lab = x.get("label")
        if not isinstance(lab, str) or not lab or (len(lab) > LABEL_MAX and lab not in PROVEN_LABELS):
            bad.append("label length")
        if "description" in x and (not isinstance(x["description"], str) or len(x["description"]) > DESC_MAX):
            bad.append("description length")
        if "style" in x and x["style"] not in STYLES:
            bad.append("style %r" % x["style"])
        vals.append(x.get("value", lab))
    if len(set(map(str, vals))) != len(vals):
        bad.append("repeated option")
    return bad


def as_text(w):
    lines = [w.get("prompt") or "Choose one:"] if isinstance(w, dict) else ["Choose one:"]
    for n, x in enumerate((w.get("options") if isinstance(w, dict) else None) or []):
        if isinstance(x, dict):
            lines.append("%d. %s%s" % (n + 1, x.get("label", ""), (" (%s)" % x["description"]) if x.get("description") else ""))
    return "\n".join(lines)


def safe_card(obj):
    """Final check on exactly what gets printed. A card that fails becomes a numbered text list."""
    w = obj.get("widget")
    if w is None:
        return obj
    bad = card_problems(w, obj.get(CUSTOM_HINT), obj.get("card_id"))
    if bad:
        obj["widget"], obj["text_list"], obj["card_fallback"] = None, as_text(w), bad
        obj.pop(CUSTOM_HINT, None)
    return obj


def pick_card(again=False):
    conn = cfg()["connected"]
    rows = [opt(P[p]["name"], p, "Connected") for p in CARD if p in conn]
    rows += [opt(P[p]["name"], p, P[p]["label"]) for p in CARD if p not in conn]
    rows.append(opt(OTHER_ROW, "other"))
    prompt = "Pick the AIs to connect. Grok is already included."
    extra = [c["name"] for p, c in conn.items() if p not in CARD]
    if extra:
        more = prompt + " Also connected: %s." % ", ".join(extra)
        prompt = more if len(more) <= PROMPT_MAX else prompt + " Also connected: %d more." % len(extra)
    return dict(card("pick", prompt, rows, True, "Which one?"), line=AGAIN if again else HELLO)


def setup_order(ticked):
    known = [p for p in ORDER if p in ticked]
    return known + [p for p in ticked if p not in ORDER and p != "other"] + (["other"] if "other" in ticked else [])


def paid_line(p):
    i = info(p)
    if i["pay"] == SUB:
        return None
    if i["pay"] == "yes":
        return "You pay %s for what you use with this account." % i["name"]
    return "If this is a paid account, you pay %s for what you use." % i["name"]


def connect_card(p):
    i = info(p)
    pl = paid_line(p)
    if i["kind"] == "cli":
        ins = ["Sign in with your %s account." % i["name"]]
    else:
        ins = i.get("instructions", ["Create an API key and copy it.", "Paste it in the key box."])
    text = "\n".join([i.get("page") or ""] + ["%d. %s" % (n + 1, x) for n, x in enumerate(ins)]).strip()
    # 4.5: key companies go straight to the key box; the paid question comes after a passing test (card paid)
    w = yes_no("connect", "Connect %s: Ready?" % i["name"], "Connect account", "Skip for now") if i["kind"] == "cli" else {"widget": None}
    return dict(w, title="Connect %s" % i["name"], link=i.get("page"), instructions=ins, text=text,
                next="signin" if i["kind"] == "cli" else "key", paid_after_test=bool(pl))


def paid_card(p):
    """Asked once, after the test passed. Yes keeps going; Skip for now saves nothing; dismissed means yes."""
    pl = paid_line(p)
    if not pl:
        return {"widget": None}
    n = info(p)["name"]
    return yes_no("paid", "%s is connected. %s Keep it?" % (n, pl), "Yes, keep it", "Skip for now")


def default_level(levels):
    return ("high" if "high" in levels else levels[-1]) if levels else None


def model_row(p, model, rows=None):
    rows = list_models(p) if rows is None else rows
    if rows is None:
        return None, None
    return rows, next((r for r in rows if r["id"] == model or r["label"].lower() == (model or "").lower()), None)


def thinking_card(p, model):
    """Second card, asked only after the model is chosen. No card when the model has 0 or 1 levels."""
    name = info(p)["name"]
    rows, r = model_row(p, model)
    if rows is None:
        return {"widget": None, "model": model, "thinking": None, "levels": [], "line": "I couldn't read %s's model list just now." % name}
    if r is None:
        return {"widget": None, "model": model, "thinking": None, "levels": [], "error": "unknown model",
                "line": "I couldn't find %s on %s. Type the name again, or say 'show all'." % (model, name)}
    bad = cant_use(p, r, rows)
    if bad:
        return dict(bad, widget=None, model=r["id"], thinking=None, levels=[])
    levels = r["thinking"]
    tdef = default_level(levels)
    res = {"widget": None, "model": r["id"], "thinking": tdef, "levels": levels}
    if len(levels) <= 1:
        return res
    if len(levels) <= MODEL_SHOW:
        lv, more = [tdef] + [x for x in levels if x != tdef], []
    else:
        others = [x for x in LEVELS if x in levels and x != tdef] + [x for x in levels if x not in LEVELS and x != tdef]
        lv = [tdef] + others[:2]
        more = [x for x in levels if x not in lv]
    opts = [opt(x.capitalize(), x, "Recommended" if x == tdef else None) for x in lv]
    prompt = "How much thinking for %s?" % short(r["label"], r["id"])
    if more:
        opts.append(opt("Other level", "other_level", short("Type it: " + ", ".join(more), "Type the level name")))
        prompt += " Pick one, or type a level."
    res.update(card("thinking", prompt, opts, False, "Level" if more else None))
    return res


def why(p, r):
    if not r["usable"]:
        return r["reason"]
    if r.get("status") == "busy":
        return REASONS["busy"]
    if r.get("hidden"):
        return REASONS["hidden"] % info(p)["name"]
    if r.get("status") == "unchecked":
        return REASONS["unchecked"]
    return "Usable"


def cant_use(p, r, rows):
    """None when the model can be used. Otherwise the plain reason and the next best model."""
    if r is None or r["id"] == "default":
        return None
    annotate(p, rows)
    if r["usable"] and r.get("status") == "unchecked" and not r.get("hidden"):
        probe_one(p, r["id"])
        annotate(p, rows)
    if r["usable"]:
        return None
    g = [x for x in good_models(p, rows) if x["id"] != r["id"]]
    if not g:
        probe(p, rows, 1)
        g = [x for x in good_models(p, annotate(p, rows)) if x["id"] != r["id"]]
    nb = g[0]["id"] if g else None
    line = "%s can't be used: %s." % (r["id"], r["reason"].lower())
    line += (" The next best is %s." % nb) if nb else " No other %s model answered just now." % info(p)["name"]
    return {"error": "cant use", "reason": r["reason"], "next_best": nb, "line": line}


def models_card(p):
    """First card: the model only. Only models that answered a tiny call (or are busy) are shown or recommended.
    The thinking card comes on the next turn (card thinking <id> <model>)."""
    name = info(p)["name"]
    rows = list_models(p)
    if rows is None:
        return {"card": None, "widget": None, "error": "list", "line": "I couldn't read %s's model list just now." % name}
    annotate(p, rows)
    if not good_models(p, rows):
        probe(p, rows)
        annotate(p, rows)
    good = good_models(p, rows)
    best = pick_best(p, rows)
    use = [r for r in rows if r["usable"]]
    bt = next((r["thinking"] for r in use if r["id"] == best), [])
    hidden = {}
    for r in rows:
        if not r["usable"]:
            hidden[r["reason"]] = hidden.get(r["reason"], 0) + 1
    tdef = default_level(bt)
    res = {"widget": None, "card": None}
    gid = {r["id"] for r in good}
    dflt = [r for r in use if r["id"] == "default"]
    fits = len(use) <= SINGLE_PREF and all(r["id"] in gid or r["id"] == "default" for r in use)
    shown = (good + dflt) if fits else good[:MODEL_SHOW]
    if len(use) > 1 and shown:
        def desc(r):
            if r.get("status") == "busy":
                return REASONS["busy"]
            return "Recommended" if r["id"] == best else None
        opts = [opt(short(r["label"], r["id"]), r["id"], desc(r)) for r in shown]
        more = len(use) - len(shown)
        prompt = "Which %s model?" % name
        if more:
            opts.append(opt("Another model", "more", "%d more. Type its name, or say 'show all'." % more))
            prompt += " Pick one, or type the model name."
        res.update(card("model", prompt, opts, False, "Model name" if more else None))
        res["card"] = {"title": "%s models" % name, "best": best, "models": [{"id": r["id"], "label": r["label"], "thinking": r["thinking"]} for r in use],
                       "cant_use": [{"count": n, "reason": w} for w, n in hidden.items()], "thinking_default": tdef}
    notes = ["%d more can't be used here: %s." % (n, w) for w, n in hidden.items()]
    busy = [r["id"] for r in good if r.get("status") == "busy"]
    if busy:
        notes.append("Busy right now on the free plan: %s. They still work, just slower for a bit." % ", ".join(busy))
    line = None
    if not use:
        line = "I couldn't find a model SuperBot can use on %s." % name
    elif not best:
        line = "No %s model answered just now. Try again in a little while." % name
        res["error"] = "noanswer"
    text = ["Models on %s:" % name] + ["- %s (%s): %s." % (r["id"], r["label"], why(p, r)) if r["label"] != r["id"] else "- %s: %s." % (r["id"], why(p, r)) for r in rows]
    if bt:
        text.append("Thinking levels for %s: %s." % (best, ", ".join(bt)))
    res.update({"notes": notes, "best": best, "thinking": tdef, "usable": len(use), "answered": [r["id"] for r in good if r.get("status") == "ok"],
                "busy": busy, "line": line, "next": "thinking" if best else None,
                "show_all": [{"id": r["id"], "reason": why(p, r), "thinking": r["thinking"]} for r in rows], "show_all_text": "\n".join(text)})
    return res


def switch_card(p, sub):
    return yes_no("keep_" + p, "Keep using %s for %s?" % (short(sub), info(p)["name"]), "Yes, keep it", "No, just this once")


def replace_card(p, sub):
    """Offered when a saved model can't be used any more (found by status)."""
    e = cfg()["connected"].get(p) or {}
    k = cached(p, e.get("model")) or "dead"
    return yes_no("fix_" + p, "%s on %s can't be used now: %s. Switch to %s?" % (short(e.get("model") or "Its model"), info(p)["name"],
                  REASONS.get(k, REASONS["dead"]).lower(), short(sub)), "Yes, switch", "Not now")


RETRY = {"badid": "%s's model list didn't match. Type a model name to try?", "net": "Couldn't reach %s. Try again?", "nomodel": "No %s model answered. Try again?", "key": "%s didn't accept the key. Try again?"}


def extra_card(kind, arg=None, why_=None):
    """Small one-question cards. Two options each."""
    if kind == "retry":
        n = info(arg)["name"]
        return yes_no("retry", RETRY.get(why_, "%s didn't connect. Try again?") % n, "Try again", "Skip for now",
                      "Model name" if why_ == "badid" else None)   # 4.5.3: a typed model name is tested with test <id> --model
    if kind == "paid":
        return paid_card(arg)
    if kind == "addon":
        n = short((arg or "This one").strip())
        return yes_no("addon", "%s needs an add-on that SuperBot hasn't checked. Add it anyway?" % n, "Yes", "No")
    if kind == "another":
        return yes_no("another", "Add another AI? Pick one, or type its name.", "Yes", "No", "Which one?")
    return {"error": "unknown card", "widget": None}


SHARE_NOTE = ("SuperBot is set up on this computer. Connected: %s. Name a model to use just one: "
              "python3 ~/.superbot/bin/sb.py ask <id> with the prompt on stdin. Name none and all connected AIs debate it: "
              "python3 ~/.superbot/bin/sb.py ask all with the question on stdin. Never add an AI that isn't connected.")


def finish_lines(names):
    """The two lines said when setup is done, built from the real connected list (Grok first)."""
    lst = ", ".join(["Grok"] + names)
    if not names:
        return ["Connected: Grok.", "Ask me anything. To connect another AI, say 'add' and its name."]
    if len(names) == 1:
        return ["Connected: %s." % lst, "Ask me a question and I'll answer with both. To use just one, name it."]
    return ["Connected: %s." % lst,
            "Ask me a question and I'll have all of them debate it. To use just one, name it, like 'make a logo using %s'." % names[0]]


def finish_card():
    c = cfg()
    c["finished"] = True
    wj(CFG, c, 0o644)
    names = [x["name"] for x in c["connected"].values()]
    return {"title": "SuperBot is ready.", "lines": finish_lines(names), "connected_names": ["Grok"] + names,
            "share_note": SHARE_NOTE % ", ".join(["Grok"] + names), "widget": None}


# ---------------------------------------------------------------- debate
STANCE = re.compile(r"STANCE:\W*(AGREE|DIFFER)", re.I)
REVISE = re.compile(r"REVISE:\W*(YES|NO)", re.I)
CHANGED = re.compile(r"CHANGED:\W*(YES|NO)", re.I)


def tag(rx, t):
    m = rx.search(t or "")
    return m.group(1).upper() if m else None


def together(fn, names):
    res = {}
    def run(n):
        try:
            res[n] = fn(n)
        except Exception as e:   # one model failing never sinks the others
            res[n] = {"ok": False, "kind": "noanswer", "answer": "", "line": "%s didn't answer this time." % info(n)["name"], "error": scrub(type(e).__name__)}
    th = [threading.Thread(target=run, args=(n,)) for n in names]
    [t.start() for t in th]
    [t.join() for t in th]
    return res


POSITION = re.compile(r"^\W*POSITION:\s*(.+)$", re.I | re.M)
TAGS = re.compile(r"^\W*(STANCE|REVISE|CHANGED|POSITION):.*$\n?", re.I | re.M)
LAST = os.path.join(SB, "last_debate.json")   # the last debate's summary, for `render`
VERDICT_HOW = ("Write the verdict yourself: one clear answer to the question in one to three sentences, weighing every answer "
               "including yours. Then run `sb.py render` with it on stdin and send the printed text exactly.")
TAIL = "\n\nEnd with 'STANCE: AGREE' if you agree with the others' main conclusion or 'STANCE: DIFFER' if not, and 'POSITION: ' plus your answer in one short sentence."


def brief(t, n=110):
    """One short line: the first sentence, cut at a word."""
    t = re.sub(r"\s+", " ", (t or "").strip())
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    if len(t) > n:
        t = t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return t


def plain(t):
    """An answer without the helper's tags."""
    return TAGS.sub("", t or "").strip()


def position_of(*texts):
    """The latest POSITION line, or else the first line of the latest answer that came back."""
    for t in texts:
        m = POSITION.search(t or "")
        if m:
            return brief(m.group(1))
    for t in texts:
        if plain(t):
            return brief(plain(t).splitlines()[0])
    return ""


def join_names(ns):
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]


VERDICT_LEAD = "**Verdict:** "    # the verdict is always the first line, bold lead-in, so the eye lands on it first
RECAP_LABEL = "_How the debate went_"   # quieter: italics, no heading
RECAP_LINES, RECAP_CHARS = 4, 500


def recap_lines(summary):
    """A short recap built from the data: who agreed, who differed and why, and who came around. 4.5.2: no changed-mind
    lines here; who changed their mind is only in `sb.py details`."""
    def pos(t):   # one short sentence, never one that talks about rounds
        keep = [x for x in re.split(r"(?<=[.!?])\s+", (t or "").strip()) if not re.search(r"(?i)\brounds?\b", x)]
        b = brief(" ".join(keep) or re.sub(r"(?i)\brounds?\b", "step", t or ""), 90)
        b = b[:1].upper() + b[1:]
        return b if b.endswith("...") else b.rstrip(".")
    dot = lambda x: x if x.endswith(("...", "?", "!", '"')) else x + "."
    ls, still = [], [x["name"] for x in summary.get("still_differ", [])]
    if not summary.get("fully_agreed"):
        for d in summary.get("differences", []):
            how = "differed" if d["name"] in still else ("agreed" if " and " in d["name"] else "said")
            ls.append(dot("%s %s: %s" % (d["name"], how, pos(d["position"]))))
    for d in summary.get("differed_first", []):
        if d["name"] not in still:
            ls.append('%s differed at first ("%s"), then agreed.' % (d["name"], pos(d["position"])))
    refined = [x["name"] for x in summary.get("refined_first", [])]
    if refined and summary.get("fully_agreed"):
        ls.append("%s asked to refine the answer, then agreed." % join_names(refined))
    end = ["In the end they all agreed."] if summary.get("fully_agreed") else []
    out_, n = [], len(RECAP_LABEL) + sum(len(x) + 1 for x in end)
    for l in ls:
        if len(out_) + len(end) >= RECAP_LINES or n + len(l) + 1 > RECAP_CHARS:
            break
        out_.append(l); n += len(l) + 1
    return out_ + end


def render(summary, verdict):
    """Owner-facing text. Verdict first, in bold; a short recap below it only if they disagreed at some point; the notes;
    4.5.2: the details line last, only after a debate that ran with two or more AIs."""
    v = re.sub(r"\s+", " ", (verdict or "").replace("**", "").strip()) or "They didn't reach one answer."
    out_ = [VERDICT_LEAD + v]
    if summary.get("disagreed_at_some_point"):
        ls = recap_lines(summary)
        if ls:
            out_.append(RECAP_LABEL + "\n" + "\n".join(ls))
    notes = [c["note"] for c in summary.get("carried_forward", [])] + [x for x in summary.get("notes", []) if x]
    if notes:
        out_.append("\n".join(notes))
    if summary.get("details_line"):
        out_.append(DETAILS_LINE)
    return "\n\n".join(out_)


DETAILS = os.path.join(SB, "last_details.json")   # 4.5.2: the last debate, step by step, for `sb.py details` (mode 600, no keys)
DETAILS_LINE = '_Reply "details" to see how each model answered and how the debate ran._'
DETAILS_CHARS = 600
NO_DETAILS = "There is no debate to show yet."
KIND_WORDS = {"net": "a network error", "timeout": "no answer in time", "noanswer": "an empty answer", "busy": "busy servers",
              "dead": "the model is gone", "noaccess": "no access to that model", "key": "the key or sign-in was not accepted",
              "ok": "an answer", "badid": "a model ID the company didn't recognize"}


def clip(t, n=DETAILS_CHARS):
    """Plain text for the details record: no tags, no keys, no long dashes, at most n characters."""
    t = re.sub(r"[ \t]+", " ", scrub(plain(t))).replace("\u2014", " - ").replace("\u2013", "-").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def how_it_ran(step, n, r):
    """Plain sentences about the retries, stand-ins and sit-outs of one model in one step."""
    name, d, ev = info(n)["name"], r.get("debug") or {}, []
    at = d.get("attempts") or []
    if len(at) > 1:
        why = list(dict.fromkeys(KIND_WORDS.get(a.get("kind"), "no answer") for a in at[:-1]))
        ev.append("%s: %s was tried %d times (first %s)%s." % (step, name, len(at), ", then ".join(why),
                                                              ", then it answered" if at[-1].get("kind") == "ok" else ""))
    b = d.get("busy_retry")
    if b:
        ev.append("%s: %s was busy, so I tried it again after a short pause, and %s." % (
            step, b["model"], "it answered" if b["kind"] == "ok" else "it was still busy" if b["kind"] == "busy" else "it got " + KIND_WORDS.get(b["kind"], "no answer")))
    m = d.get("remapped")
    if m:   # 4.5.3, OpenRouter, Groq, Mistral, DeepSeek and Other only
        ev.append("%s: %s's model list didn't match %s, so I used the model ID %s%s." % (
            step, name, m["from"], m["to"], "" if m.get("kind") == "ok" else ", and " + KIND_WORDS.get(m.get("kind"), "no answer") + " came back"))
    for t in d.get("alternates") or []:
        ev.append("%s: %s tried %s instead, and %s." % (step, name, t["model"], "it answered" if t["kind"] == "ok" else "it was busy too" if t["kind"] == "busy" else "it got " + KIND_WORDS.get(t["kind"], "no answer")))
    if r.get("line"):
        ev.append("%s: %s" % (step, re.sub(r"\s*Want me to keep using .*\?$", "", r["line"])))
    elif not r.get("ok"):
        ev.append("%s: %s didn't answer (%s)." % (step, name, KIND_WORDS.get(r.get("kind"), "no answer")))
    return ev


def details_record(q, names, grok, r1, r2, r3, rounds, decision, rejoined, changed, pos, fully, differ):
    """4.5.2: what `sb.py details` shows. Answers trimmed, keys scrubbed, nothing secret."""
    nm = lambda n: info(n)["name"]
    word = {"AGREE": "agrees", "DIFFER": "differs"}
    one = {nm(n): clip(r1[n]["answer"]) for n in names if r1[n].get("ok")}
    if grok and grok.strip():
        one["Grok"] = clip(grok)
    two = []
    for n in names:
        r = r2.get(n)
        if not r or not r.get("ok"):
            continue
        late = rejoined.get(nm(n)) == 2
        two.append({"name": nm(n), "late": late, "text": clip(r["answer"]), "stance": word.get(tag(STANCE, r["answer"]) or "", "gave no stance"),
                    "revise": "" if late else ("wants to revise" if tag(REVISE, r["answer"]) == "YES" else "keeps its answer")})
    three = None
    if decision.get("run"):
        three = []
        for n in names:
            r = r3.get(n)
            if r and r.get("ok"):
                three.append({"name": nm(n), "late": rejoined.get(nm(n)) == 3, "changed": nm(n) in changed, "text": clip(r["answer"])})
    ev = []
    for step, rs in (("Round 1", r1), ("Round 2", r2), ("Round 3", r3)):
        for n in names:
            if n in rs:
                ev += how_it_ran(step, n, rs[n])
    for k, v in rejoined.items():
        ev.append("Round %d: %s missed the first answers and joined with a late answer." % (v, k))
    return {"version": VERSION, "question": clip(q, 300), "names": [nm(n) for n in names], "round1": one,
            "missing1": [nm(n) for n in names if not r1[n].get("ok")], "round2": two if len(rounds) >= 2 else None,
            "round2_skipped": "" if len(rounds) >= 2 else decision.get("reason", ""), "round3": three,
            "round3_why": decision.get("reason", ""), "changed_minds": list(changed), "events": ev,
            "ended": {k: clip(v, 200) for k, v in pos.items()}, "fully_agreed": fully, "still_differ": list(differ), "verdict": ""}


def details_text(rec):
    """The plain-text breakdown. It may talk about rounds; the normal answer never does."""
    if not rec.get("round1") and not rec.get("events"):
        return NO_DETAILS
    out_ = ["Question: %s" % rec.get("question", ""), "", "Round 1, first answers:"]
    out_ += ["- %s: %s" % kv for kv in rec.get("round1", {}).items()]
    out_ += ["- %s: no answer in this round." % k for k in rec.get("missing1", [])]
    out_.append("")
    if rec.get("round2") is None:
        out_.append("Round 2 didn't run: %s" % rec.get("round2_skipped", ""))
    else:
        out_.append("Round 2, critiques:")
        for c in rec["round2"]:
            how = "late answer, " + c["stance"] if c["late"] else "%s, %s" % (c["stance"], c["revise"])
            out_.append("- %s (%s): %s" % (c["name"], how, c["text"]))
        if not rec["round2"]:
            out_.append("- No critiques came back.")
        out_.append("Next: %s" % rec.get("round3_why", ""))
    if rec.get("round3") is not None:
        out_ += ["", "Round 3, final answers:"]
        for c in rec["round3"]:
            how = "answered late" if c["late"] else ("changed its mind" if c["changed"] else "kept its answer")
            out_.append("- %s %s: %s" % (c["name"], how, c["text"]))
        ch = rec.get("changed_minds") or []
        out_.append("Changed their minds: %s." % join_names(ch) if ch else "Nobody changed their mind.")
    out_ += ["", "Retries, stand-ins and sit-outs:"]
    out_ += ["- " + e for e in rec.get("events", [])] or ["- None. Every model answered the first time."]
    out_ += ["", "Final verdict: %s" % (rec.get("verdict") or "not written yet.")]
    if rec.get("fully_agreed"):
        out_.append("They all agreed in the end.")
    elif rec.get("still_differ"):
        out_.append("Still differ: %s." % "; ".join("%s (%s)" % (k, (rec.get("ended", {}).get(k) or "").rstrip(".")) for k in rec["still_differ"]))
    return "\n".join(out_).replace("\u2014", " - ")


def run_debate(names, q, grok=None):
    """Answers, critiques, then a final pass only if someone differs or wants to revise. A later failure keeps
    the earlier answer. `summary` and `report_template` are for the owner; `debug` is not for display."""
    nm = lambda n: info(n)["name"]
    used = [0.0]   # seconds of DEBATE_CAP used so far: the slowest call of each round
    def spend(rs):
        used[0] += max([(r.get("debug") or {}).get("elapsed", 0) for r in rs.values()] or [0])
    left = lambda: max(0.0, DEBATE_CAP - used[0])
    r1 = together(lambda n: ask_one(n, q, timeout=ROUND_TIMEOUT[1], budget=left(), keep=ROUND_TIMEOUT[2]), names)
    spend(r1)
    lines = [r["line"] for r in r1.values() if r.get("line")]
    good = [n for n in names if r1[n]["ok"]]
    # A model that dropped in the first answers for a network error, a timeout or an empty answer gets another
    # try in the later steps. It sees the others' answers, so it answers and says where it stands.
    late = [n for n in names if not r1[n]["ok"] and r1[n].get("kind") in ("net", "timeout", "noanswer", "busy")]
    rejoined, first = {}, {n: r1[n]["answer"] for n in good}

    def rejoin(n, step, r):
        rejoined[nm(n)] = step
        good.append(n); late.remove(n)
        first[n] = plain(r["answer"])
        if r1[n].get("line") in lines:
            lines.remove(r1[n]["line"])
    stand = {n: r1[n].get("standin", {}).get("to") for n in names}
    use = lambda n: stand.get(n)   # a stand-in keeps answering for the rest of the debate
    def took_over(rs):   # 4.5.2: a stand-in in a later step keeps answering too, and its note is shown once
        for n, r in rs.items():
            if r.get("ok") and r.get("standin"):
                stand[n] = r["standin"]["to"]
                if r.get("line") and r["standin"].get("why") in ("busy", "timeout") and r["line"] not in lines:
                    lines.append(r["line"])
    answers = {nm(n): r1[n]["answer"] for n in good}
    if grok and grok.strip():
        answers["Grok"] = grok.strip()
    rounds = [{"round": 1, "kind": "answer", "answers": dict(answers)}]
    final = {nm(n): r1[n]["answer"] for n in good}
    texts = {nm(n): [r1[n]["answer"]] for n in good}   # newest first, for each model's short position
    r2, r3, stance, revise, changed, carried, first_differ, wants = {}, {}, {}, {}, [], [], {}, []
    decision = {"run": False, "reason": ""}
    if len(answers) < 2:
        decision["reason"] = "Only one answer came back, so there was nothing to compare."
    else:
        def critique(n):
            others = "\n\n".join("%s said:\n%s" % (k, v) for k, v in answers.items() if k != nm(n))
            return ask_one(n, "Round 2. Question:\n%s\n\nYour answer:\n%s\n\nThe other answers:\n%s\n\n"
                              "Briefly critique the other answers. Then end with three lines: 'STANCE: AGREE' if you agree with the others' "
                              "main conclusion, or 'STANCE: DIFFER' if not; 'REVISE: YES' if you want to change your own answer, or 'REVISE: NO'; "
                              "and 'POSITION: ' plus your answer in one short sentence."
                           % (q, r1[n]["answer"], others), use(n), timeout=ROUND_TIMEOUT[2], budget=left(), keep=ROUND_TIMEOUT[3])

        def late2(n):
            return ask_one(n, "Round 2, late answer. Question:\n%s\n\nThe answers so far:\n%s\n\nGive your own answer in a few lines, "
                              "then briefly say where you agree or differ with the others. Then end with three lines: 'STANCE: AGREE' if you "
                              "agree with the others' main conclusion, or 'STANCE: DIFFER' if not; 'REVISE: NO'; and 'POSITION: ' plus your "
                              "answer in one short sentence." % (q, "\n\n".join("%s said:\n%s" % kv for kv in answers.items())),
                           timeout=ROUND_TIMEOUT[2], budget=left(), keep=ROUND_TIMEOUT[3])
        was_good = list(good)
        r2 = together(lambda n: critique(n) if n in was_good else late2(n), was_good + late)
        spend(r2)
        took_over(r2)
        for n in list(late):
            if r2[n]["ok"]:
                rejoin(n, 2, r2[n])
                answers[nm(n)] = final[nm(n)] = first[n]
                texts[nm(n)] = [r2[n]["answer"]]
                stance[nm(n)], revise[nm(n)] = tag(STANCE, r2[n]["answer"]), "NO"
        for n in was_good:
            r2[n].pop("switch", None)
            if r2[n]["ok"]:
                stance[nm(n)], revise[nm(n)] = tag(STANCE, r2[n]["answer"]), tag(REVISE, r2[n]["answer"])
                if POSITION.search(r2[n]["answer"]):
                    texts[nm(n)].insert(0, r2[n]["answer"])
            else:
                carried.append(nm(n))
        rounds.append({"round": 2, "kind": "critique", "critiques": {nm(n): plain(r2[n]["answer"]) for n in was_good if r2[n]["ok"]},
                       "late_answers": {k: final[k] for k, v in rejoined.items() if v == 2}, "stance": dict(stance), "revise": revise})
        differ = [k for k, v in stance.items() if v == "DIFFER"]
        wants = [k for k, v in revise.items() if v == "YES"]
        first_differ = {k: position_of(*texts[k]) for k in differ}   # positions at the critique, before any change
        if differ or wants:
            why_ = []
            if differ:
                why_.append("Still disagree: %s." % ", ".join(differ))
            if wants:
                why_.append("Want to revise: %s." % ", ".join(wants))
            decision = {"run": True, "reason": " ".join(why_)}
        elif stance and all(v == "AGREE" for v in stance.values()):
            decision["reason"] = "They agree after the critiques and nobody wants to revise."
        else:
            decision["reason"] = "Nobody said they disagree or want to revise."
        if decision["run"]:
            crits = "\n\n".join("%s's critique:\n%s" % (k, v) for k, v in rounds[1]["critiques"].items())
            def final3(n):
                if n in late:   # still missing: it answers once, seeing the answers and the critiques
                    return ask_one(n, "Round 3, late answer. Question:\n%s\n\nThe answers so far:\n%s\n\nThe critiques:\n%s\n\n"
                                      "Give your answer in a few lines. Start with 'CHANGED: NO'." % (q, "\n\n".join("%s said:\n%s" % kv for kv in answers.items()), crits)
                                   + TAIL, timeout=ROUND_TIMEOUT[3], budget=left())
                return ask_one(n, "Round 3. Question:\n%s\n\nYour first answer:\n%s\n\nThe critiques:\n%s\n\n"
                                  "Give your final answer in a few lines. Start with 'CHANGED: YES' if it differs from your first answer, "
                                  "or 'CHANGED: NO'." % (q, first[n], crits) + TAIL, use(n), timeout=ROUND_TIMEOUT[3], budget=left())
            in3 = [n for n in good if nm(n) not in carried] + list(late)
            r3 = together(final3, in3)
            spend(r3)
            took_over(r3)
            ch = {}
            for n in list(late):
                if r3[n]["ok"]:
                    rejoin(n, 3, r3[n])
                    final[nm(n)] = plain(r3[n]["answer"]); texts[nm(n)] = [r3[n]["answer"]]
                    stance[nm(n)] = tag(STANCE, r3[n]["answer"])
            for n in [x for x in in3 if x not in late and rejoined.get(nm(x)) != 3]:   # still missing: its note stands
                r3[n].pop("switch", None)
                if r3[n]["ok"]:
                    final[nm(n)] = plain(r3[n]["answer"])
                    texts[nm(n)].insert(0, r3[n]["answer"])
                    ch[nm(n)] = tag(CHANGED, r3[n]["answer"])
                    stance[nm(n)] = tag(STANCE, r3[n]["answer"]) or stance.get(nm(n))   # the latest stance counts
                    if ch[nm(n)] == "YES":
                        changed.append(nm(n))
                else:
                    carried.append(nm(n))
            rounds.append({"round": 3, "kind": "final", "answers": {nm(n): final[nm(n)] for n in good}, "changed": ch})
    if grok and grok.strip():
        final["Grok"] = grok.strip()
    pos = {k: position_of(*v) for k, v in texts.items()}
    # Sides: everyone who still differs stands alone; everyone else is one side. Grok's view goes into the verdict.
    differ = [k for k in final if k != "Grok" and stance.get(k) == "DIFFER"]
    rest = [k for k in final if k != "Grok" and k not in differ]
    fully = len(answers) >= 2 and not differ
    diffs = [] if fully else ([{"name": join_names(rest), "position": pos[rest[0]]}] if rest else []) + [{"name": k, "position": pos[k]} for k in differ]
    # Disagreed at some point: anyone said DIFFER in the critiques, wanted to revise, changed, or still differs.
    some = bool(first_differ or wants or changed or differ)
    summary = {"verdict": None, "verdict_instruction": VERDICT_HOW, "fully_agreed": fully, "differences": diffs,
               "disagreed_at_some_point": some, "still_differ": [{"name": k} for k in differ],
               "differed_first": [{"name": k, "position": v} for k, v in first_differ.items()],
               "refined_first": [{"name": k} for k in wants if k not in first_differ],
               "carried_forward": [{"name": k, "note": "%s didn't answer the follow-up, so its first answer stands." % k} for k in carried],
               "grok_included": "Grok" in answers, "notes": list(lines), "details_line": len(rounds) >= 2}
    try:
        wj(LAST, summary)
        wj(DETAILS, details_record(q, names, grok, r1, r2, r3, rounds, decision, rejoined, changed, pos, fully, differ))
    except OSError:
        pass
    sw = [r1[n]["switch"] for n in names if r1[n].get("switch")]
    res = {"summary": summary, "report_template": render(summary, "{verdict}"),
           "debug": {"not_for_display": True, "note": "For debugging only. Never show this to the owner.",
                     "round1": r1, "round2": r2, "round3": r3, "rounds": rounds, "round_count": len(rounds),
                     "round3_decision": decision, "stance": stance, "final": final,
                     "changed_minds": [{"name": k, "change": pos[k]} for k in changed],
                     "rejoined": rejoined, "seconds_used": round(used[0], 1), "cap": DEBATE_CAP},
           "lines": lines, "switches": sw, "widget": None}
    if sw:   # one card now; the bot asks for the next with: card switch <id> <model>
        res.update(switch_card(sw[0]["id"], sw[0]["to"]))
        res["switches_left"] = sw[1:]
    return res


# Sent once, before the models run, whenever a debate will run (sb.py debate-intro prints it).
WAIT_LINE = "These debates can become heated, so answers may take a couple minutes."


def debate_intro(target):
    """Run before `ask all` / `debate`, so the bot can send the wait line first. Only a real debate
    (two or more connected AIs, or two or more named) gets it; 0 or 1 AI and a single named model don't."""
    t = (target or "all").strip().lower()
    names = list(cfg()["connected"]) if t in ("", "all", "auto", "any", "grok") else [x for x in t.split(",") if x and x != "grok"]
    names = [x for x in names if x in cfg()["connected"]]
    if len(names) >= 2:
        return {"debate": True, "wait_line": WAIT_LINE, "send_first": True}
    return {"debate": False}


def ask_all(q, grok=None):
    """No model named: every connected AI, plus Grok's own view. One AI: a plain answer, no debate."""
    names = list(cfg()["connected"])
    incl = ["Grok"] + [info(n)["name"] for n in names]
    base_ = {"included": incl, "included_ids": names, "widget": None}
    if not names:
        return dict(base_, mode="grok_only", line="Only Grok is connected, so I'll answer myself. Say 'add' and a name to connect another AI.")
    if len(names) == 1:
        r = ask_one(names[0], q)
        res = dict(base_, mode="single", answers={incl[1]: r}, line="Answering with %s." % " and ".join(incl),
                   lines=[r["line"]] if r.get("line") else [])
        if r.get("switch"):
            res.update(switch_card(names[0], r["switch"]["to"]))
        return res
    res = run_debate(names, q, grok)
    res.update(mode="debate", included=incl, included_ids=names, line="Asking %s." % (", ".join(incl[:-1]) + " and " + incl[-1]))
    return res


# ---------------------------------------------------------------- lookup for Other
def lookup(name):
    name = name.strip()
    if KEYLIKE.search(name):
        return {"keylike": True, "line": "That looks like a key, so I ignored it. Please type only the model or company name."}
    n = name.lower()
    hits = [{"id": p, "name": P[p]["name"], "known": True, "setup": p} for p in ORDER if n in p or n in P[p]["name"].lower()]
    if hits and any(n in (h["id"], h["name"].lower()) for h in hits):
        return {"keylike": False, "known": hits[0]["setup"], "matches": hits[:1], "count": 1, "list_read": False}
    t = os.environ.get("SB_TEST_BASE", "")
    url = (t.rstrip("/") + "/catalog" if t.startswith("http://127.0.0.1") else "https://openrouter.ai/api/v1") + "/models"
    code, js = http("GET", url, timeout=30)
    for m in js.get("data", []) if code == 200 else []:
        mid = m.get("id", "")
        if n in mid.lower() or n in (m.get("name") or "").lower():
            hits.append({"id": mid, "company": mid.split("/")[0], "free_on_openrouter": free_model("openrouter", mid, m)})
    res = {"keylike": False, "matches": hits[:12], "count": len(hits), "list_read": code == 200, "widget": None}
    if hits:
        opts = [opt(short(h.get("name") or h["id"], h["id"]), h["id"]) for h in hits[:MODEL_SHOW]] + [opt("None of these", "none")]
        res.update(card("match", "Matches for %s. Which one did you mean? Or type the name." % short(name), opts, False, "Name"))
        res["show_all_text"] = "\n".join(["Matches for %s:" % name] + ["- " + h["id"] for h in hits])
    return res


# ---------------------------------------------------------------- remove
def remove_key(p, yes):
    c = cfg()
    if p in c.get("parked", {}) and p not in c["connected"]:
        name = c["parked"][p]["name"]
        if not yes:
            q = "Remove your saved %s key from SuperBot?" % name
            return {"ask": q, "removed": False, **yes_no("remove", q, "Yes, remove", "No, keep it")}
        ks = rj(KEYS, {})
        ks.pop(p, None)
        wj(KEYS, ks)
        del c["parked"][p]
        wj(CFG, c, 0o644)
        forget(p)
        return {"removed": True, "line": "%s's saved key is removed from SuperBot." % name}
    if p not in c["connected"]:
        return {"removed": False, "line": "%s isn't connected." % info(p)["name"]}
    name = c["connected"][p]["name"]
    if not yes:
        q = "Remove your %s connection from SuperBot?" % name
        return {"ask": q, "buttons": ["Yes, remove", "No, keep it"], "removed": False,
                **yes_no("remove", q, "Yes, remove", "No, keep it")}
    ks = rj(KEYS, {})
    ks.pop(p, None)
    wj(KEYS, ks)
    still_cli = any(x in c["connected"] for x in ("claude", "chatgpt") if x != p)
    for path in c.get("added", {}).pop(p, []):
        if path == NPM and still_cli:
            continue
        if path.startswith(SB + os.sep):
            shutil.rmtree(path, ignore_errors=True)
    if p == "claude":
        shutil.rmtree(os.path.join(SB, "claude"), ignore_errors=True)
    if p == "chatgpt":
        shutil.rmtree(os.path.join(SB, "codex"), ignore_errors=True)
    del c["connected"][p]
    wj(CFG, c, 0o644)
    forget(p)
    line = "%s is removed from SuperBot." % name
    if p not in ("claude", "chatgpt"):
        line += " To turn the key off everywhere, delete it on %s's site too." % name
    return {"removed": True, "line": line}


def remove_all(yes):
    names = [c["name"] for c in cfg()["connected"].values()] + [c["name"] for c in cfg().get("parked", {}).values()]
    ins = ["I delete the saved keys and sign-ins for: %s." % (", ".join(names) or "none"),
             "I delete SuperBot's setup and the tools it added on this computer.",
             "You turn off each key on the company's own site.",
             "You delete SuperBot from the sidebar: right-click it and choose Delete."]
    if not yes:
        return dict(yes_no("remove_all", "Remove SuperBot?", "Yes, remove", "No, keep it"),
                    ask="Remove SuperBot?", instructions=ins, buttons=["Yes, remove", "No, keep it"], removed=False)
    shutil.rmtree(SB, ignore_errors=True)
    return {"removed": True, "line": "Your keys and the setup are deleted from this computer.", "instructions": ins[2:]}


# ---------------------------------------------------------------- main
def stdin_text():
    return sys.stdin.read()


def main(a):
    if not a:
        out({"error": "usage"}, 2)
    cmd = a[0]
    if cmd == "_pty":
        return pty_child(a[1])
    if cmd == "version":
        # printed without scrub: the sha256 of this public file is not a secret, but it looks like one
        sys.stdout.write(json.dumps({"version": VERSION, "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}) + "\n")
        sys.exit(0)
    if cmd == "status":
        cleaned = migrate() + cleanup()
        c = cfg()
        dead = []
        for p, e in c["connected"].items():
            m = e.get("model")
            if not m or m == "default":
                continue
            if idfix(p) and not IDLIKE.match(m):   # 4.5.3: a saved display name becomes its real ID
                m2 = as_id(p, m)
                if m2 != m:
                    save_model(p, m2, m)
                    e["model"] = m = m2
            k = cached(p, m)
            if k is None and info(p)["kind"] != "cli":
                k, _ = probe_one(p, m)   # one tiny call per saved model, at most every few hours (cached)
            if k in ("dead", "noaccess"):
                rows = list_models(p) or []
                annotate(p, rows)
                g = [x for x in good_models(p, rows) if x["id"] != m]
                if not g:
                    probe(p, rows, 1)
                    g = [x for x in good_models(p, annotate(p, rows)) if x["id"] != m]
                dead.append({"id": p, "model": m, "reason": REASONS[k], "to": g[0]["id"] if g else None})
        res = {"connected": {p: {k: v for k, v in e.items() if k != "base"} for p, e in c["connected"].items()},
               "parked": sorted(c.get("parked", {})), "setup_done": bool(c.get("finished")), "cleaned": cleaned,
               "dead_saved": dead, "widget": None}
        res["lines"] = ["%s's model %s can't be used now: %s. No other %s model answered just now." % (info(d["id"])["name"], d["model"], d["reason"].lower(), info(d["id"])["name"])
                        for d in dead if not d["to"]]
        fix = [d for d in dead if d["to"]]
        if fix:   # one card now; the next with: card replace <id> <model>
            res.update(replace_card(fix[0]["id"], fix[0]["to"]))
            res["switches_left"] = [{"id": d["id"], "to": d["to"]} for d in fix[1:]]
        out(res)
    if cmd == "pick":
        out(pick_card("--again" in a))
    if cmd == "order":
        out({"order": setup_order(a[1:])})
    if cmd == "connect-card":
        out(connect_card(a[1]))
    if cmd == "skip":   # "Skip for now" on the paid card: nothing for this company is kept
        c, n = cfg(), info(a[1])["name"]
        if a[1] in c.get("parked", {}) and a[1] not in c["connected"]:
            del c["parked"][a[1]]; wj(CFG, c, 0o644)
            ks = rj(KEYS, {}); ks.pop(a[1], None); wj(KEYS, ks)
        abort(a[1])
        out({"skipped": True, "line": "Skipped %s. Say 'add %s' anytime." % (n, n)})
    if cmd == "begin":
        other = journal(a[1]).get("other")
        abort(a[1])
        out({"begun": bool(begin(a[1], other)), "key_saved": a[1] in cfg().get("parked", {}) and a[1] in rj(KEYS, {})})
    if cmd == "other":
        o = dict(zip(a[2::2], a[3::2]))
        oid = re.sub(r"[^a-z0-9]", "", a[1].lower())[:30]
        if not oid or oid in P or not o.get("--base", "").startswith("https://"):
            out({"error": "bad other"}, 2)
        begin(oid, {"name": o.get("--name", a[1])[:40], "base": o["--base"].rstrip("/"), "paid": o.get("--paid") == "yes"})
        out({"begun": True, "id": oid, "paid": o.get("--paid") == "yes"})
    if cmd == "key":
        p, env_name = a[1], a[2]
        if not journal(p):
            out({"error": "no setup open"}, 4)
        v = os.environ.get(env_name, "").strip()
        if not v:
            out({"stored": False, "line": "I didn't get a key. Try the key box again."}, 3)
        wj(os.path.join(PEND, p + ".key"), {"k": v})
        out({"stored": True})
    if cmd == "install-cli":
        out(install_cli(a[1]))
    if cmd == "signin":
        out(signin(a[1], a[2], a[3] if len(a) > 3 else None))
    if cmd == "test":
        # A valid key connects when at least one model answers or is only busy. The model list alone never decides.
        p = a[1]
        name, cli = info(p)["name"], info(p)["kind"] == "cli"
        del PROBE_DEBUG[:]
        dbg = {"not_for_display": True, "list": {}, "probes": PROBE_DEBUG}

        def fail(why_, line, **kw):
            if why_ == "key" and p in cfg().get("parked", {}):   # a kept key that stopped working is dropped
                c = cfg(); c["parked"].pop(p, None); wj(CFG, c, 0o644)
                ks = rj(KEYS, {}); ks.pop(p, None); wj(KEYS, ks)
            card = extra_card("retry", p, why_)
            other = journal(p).get("other")
            abort(p)
            if other:   # an added-by-hand AI keeps its name and address, so "Try again" only needs the key
                begin(p, other)
            r = {"ok": False, "reason": why_, "line": line}
            r.update(kw)
            r.update(card)
            out(dict(r, debug=dbg, **seen()))

        def passed(r):   # the paid question, if this company has one, comes only now
            r.update(paid_card(p))
            if not r.get("widget"):
                r.pop("widget", None); r.pop("card_id", None)
            out(dict(r, debug=dbg, **seen()))
        rows = list_models(p)
        if rows is None:
            code, body = LIST["code"], str(LIST["error"] or "")
            dbg["list"] = {"status": code, "body": scrub(body[:200])}
            if code == 0 or code in TRANSIENT:   # the list call itself failed after its retries: the only "net"
                dbg["list"]["rule"] = "list unreachable"
                fail("net", "I couldn't reach %s just now, so nothing was saved. Try again in a minute." % name)
            if code == 401 or (code in (400, 403) and KEYSAYS.search(body)):   # 4.5.1: a 403 alone isn't a bad key
                dbg["list"]["rule"] = "list %s bad key" % code
                fail("key", "%s didn't accept that key, so nothing was saved. Check the key and try again." % name)
            dbg["list"]["rule"] = "list %s other" % code
            fail("other", "%s couldn't connect, so nothing was saved. Try again or skip for now." % name)
        dbg["list"] = {"status": 200 if list_ok(p) else None, "rule": "list ok" if list_ok(p) else "no list call"}
        badid_line = ("%s's model list didn't match what SuperBot expected, so I couldn't test a model. Your key looks fine and is saved. "
                      "Want to try another model name by typing it?" % name)
        if idfix(p):   # 4.5.3
            dbg["list"].update(entries=len(LIST.get("raw") or []), with_id=len(rows), id_field=(rows[0].get("id_field") if rows else None))
            typed = dict(zip(a[2::2], a[3::2])).get("--model")
            if typed:   # the owner typed a model name after the "didn't match" card: test just that one
                mid = as_id(p, typed.strip(), rows)
                kind, rule, _, tries = probe_model(p, mid, time_left())
                PROBE_DEBUG.extend(tries)
                dbg["typed"] = {"model": mid, "kind": kind, "rule": rule}
                if kind in ("ok", "busy"):
                    remember(p, mid, kind)
                    passed({"ok": True, "line": "%s connected. The test passed." % name, "answered": [mid] if kind == "ok" else [],
                            "best": mid, "busy": [] if kind == "ok" else [mid], "calls": len(tries)})
                if kind == "keybad":
                    fail("key", "%s didn't accept that key, so nothing was saved. Check the key and try again." % name)
                park(p)
                fail("badid" if kind == "badid" else "nomodel", badid_line if kind == "badid" else
                     "%s didn't answer with %s, so I couldn't test it. Your key looks fine and is saved." % (name, mid), key_saved=True, calls=len(tries))
            if LIST.get("noid"):   # the list loaded, but no entry has a field SuperBot can send as a model ID
                dbg["idcheck"] = {"rule": "no entry in the list has an ID-like field", "tried": [], "result": "nothing to try"}
                park(p)
                fail("badid", badid_line, key_saved=True, calls=0)
        pr = probe(p, rows, fresh=True)
        if pr.get("id_field") is not None or ID_DEBUG.get("rule"):
            dbg["idcheck"] = dict(ID_DEBUG)
        if p == "chatgpt" and not ranked(p, rows):   # no model list yet: the default model answers the test
            k = check_call(p, "default")
            pr = {"calls": 1, "stop": k if k in ("key", "net") else None}
            if k in ("ok", "busy"):
                passed({"ok": True, "line": "%s connected. The test passed." % name, "answered": ["default"] if k == "ok" else [],
                        "busy": [] if k == "ok" else ["default"], "calls": 1})
        if pr["stop"] == "key":
            fail("key", ("%s isn't signed in, so nothing was saved. Try again or skip for now." if cli else
                         "%s didn't accept that key, so nothing was saved. Check the key and try again.") % name)
        if pr["stop"] == "badid":   # 4.5.3: the key is fine (list 200): keep it; never "no model answered"
            park(p)
            fail("badid", badid_line, key_saved=True, calls=pr["calls"])
        if pr["stop"] == "net":
            fail("net", "I couldn't reach %s just now, so nothing was saved. Try again in a minute." % name)
        annotate(p, rows)
        good = good_models(p, rows)
        ok_ = [r["id"] for r in good if r["status"] == "ok"]
        busy = [r["id"] for r in good if r["status"] == "busy"]
        if ok_:
            line = "%s connected. The test passed." % name
            if busy:
                line += " Some models are busy right now on the free plan, but they still work."
            passed({"ok": True, "line": line, "answered": ok_, "best": ok_[0], "busy": busy, "calls": pr["calls"]})
        if busy:
            passed({"ok": True, "line": "%s connected. Its models are busy right now on the free plan, so answers may be slow for a bit." % name,
                 "answered": [], "busy": busy, "calls": pr["calls"]})
        if cli:
            fail("nomodel", "%s didn't answer right now, so nothing was saved. Try again in a little while." % name, calls=pr["calls"])
        park(p)
        fail("nomodel", "Your %s key works, but no model answered right now. I saved the key, so you won't need to paste it again." % name,
             key_saved=True, calls=pr["calls"])
    if cmd == "models":
        out(models_card(a[1]))
    if cmd == "card":
        k = a[1] if len(a) > 1 else ""
        if k == "models":
            out(models_card(a[2]))
        if k == "thinking":
            out(thinking_card(a[2], " ".join(a[3:])))
        if k == "switch":
            out(switch_card(a[2], " ".join(a[3:])))
        if k == "replace":
            out(replace_card(a[2], " ".join(a[3:])))
        if k == "retry":
            out(extra_card(k, a[2], a[3] if len(a) > 3 else None))
        out(extra_card(k, " ".join(a[2:]) or None))
    if cmd == "commit":
        o = dict(zip(a[2::2], a[3::2]))
        m = o.get("--model") or "default"
        th = o.get("--thinking")
        if m != "default" and journal(a[1]):
            rows = list_models(a[1])
            r = model_row(a[1], m, rows)[1] if rows else None
            bad = cant_use(a[1], r, rows) if r else None
            if bad:   # a typed dead or blocked name: say why and offer the next best
                out(dict(bad, saved=False), 3)
            if r and idfix(a[1]):   # 4.5.3: a display name typed or picked is saved as the real ID
                m = r["id"]
        if th is None:
            th = default_level((model_row(a[1], m)[1] or {}).get("thinking", []))   # thinking card skipped or not asked yet
        out({"saved": commit(a[1], m, th)})
    if cmd == "save-thinking":
        c = cfg()
        if a[1] not in c["connected"]:
            out({"error": "not connected"}, 4)
        e = c["connected"][a[1]]
        lv = (a[2] if len(a) > 2 else "default").strip().lower()
        if lv in ("default", "skip", ""):
            out({"saved": False, "thinking": e.get("thinking"), "line": "Kept %s's thinking level." % e["name"]})
        _, r = model_row(a[1], e.get("model"))
        if r is not None and lv not in r["thinking"]:
            out({"saved": False, "line": "%s doesn't have a %s level. Pick one of: %s." % (e.get("model"), lv, ", ".join(r["thinking"]) or "none")}, 3)
        e["thinking"] = lv
        wj(CFG, c, 0o644)
        out({"saved": True, "thinking": lv, "line": "Saved. %s now uses %s thinking." % (e["name"], lv)})
    if cmd == "abort":
        abort(a[1])
        out({"aborted": True})
    if cmd == "debate-intro":
        out(debate_intro(a[1] if len(a) > 1 else "all"))
    if cmd in ("ask", "debate"):
        o = dict(zip(a[2::2], a[3::2]))
        target = a[1].strip().lower() if len(a) > 1 and not a[1].startswith("--") else "all"
        if len(a) > 1 and a[1].startswith("--"):
            o = dict(zip(a[1::2], a[2::2]))
        grok = None
        if o.get("--grok-file"):
            try:
                with open(o["--grok-file"]) as f:
                    grok = f.read()[:20000]
            except OSError:
                grok = None
        if target in ("", "all", "auto", "any", "grok"):
            out(ask_all(stdin_text(), grok))   # no model named: everyone connected (one AI: a plain answer)
        if cmd == "ask" and "," not in target:
            r = ask_one(target, stdin_text(), o.get("--model"), o.get("--thinking"))
            if r.get("switch"):
                r.update(switch_card(p=target, sub=r["switch"]["to"]))
            out(r)
        names = [x for x in target.split(",") if x and x != "grok"]
        missing = [x for x in names if x not in cfg()["connected"]]
        if missing:
            out({"error": "not connected", "missing": missing, "line": "Not connected yet: %s. Say 'add' and the name to set it up." % ", ".join(missing)}, 4)
        q = stdin_text()
        if len(names) == 1:
            out(ask_one(names[0], q))
        res = run_debate(names, q, grok)
        res.update(mode="debate", included=["Grok"] + [info(n)["name"] for n in names], included_ids=names)
        out(res)
    if cmd == "render":   # the verdict on stdin; prints the owner-facing debate text
        o = dict(zip(a[1::2], a[2::2]))
        summ = rj(o.get("--summary-file", LAST), {})
        if "fully_agreed" not in summ:
            out({"error": "no debate", "line": "There's no debate to report yet."}, 4)
        v = stdin_text()
        if "--summary-file" not in o:   # 4.5.2: the details view shows the same verdict
            rec = rj(DETAILS, {})
            if rec:
                rec["verdict"] = clip(re.sub(r"\s+", " ", (v or "").replace("**", "")))
                try:
                    wj(DETAILS, rec)
                except OSError:
                    pass
        out({"text": render(summ, v)})
    if cmd == "details":   # 4.5.2: how the last debate ran, step by step, as plain text
        out({"text": details_text(rj(DETAILS, {}))})
    if cmd == "save-model":
        c = cfg()
        if a[1] not in c["connected"]:
            out({"error": "not connected"}, 4)
        a[2] = as_id(a[1], a[2])   # 4.5.3: OpenRouter, Groq, Mistral, DeepSeek and Other save the real ID, never a display name
        c["connected"][a[1]]["model"] = a[2]
        wj(CFG, c, 0o644)
        out({"saved": True, "line": "Saved. %s now uses %s." % (c["connected"][a[1]]["name"], a[2])})
    if cmd == "image":
        if "chatgpt" not in cfg()["connected"]:
            out({"ok": False, "line": "ChatGPT isn't connected."})
        o = dict(zip(a[1::2], a[2::2]))
        dest = o.get("--out") or os.path.join(HOME, "superbot-images", time.strftime("%Y%m%d-%H%M%S"))
        gen = os.path.join(SB, "codex", "generated_images")
        before = {os.path.join(d, f) for d, _, fs in os.walk(gen) for f in fs}
        rc, _, _ = run_cli("chatgpt", ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-"],
                           "Make an image: " + stdin_text(), 300)
        new = sorted({os.path.join(d, f) for d, _, fs in os.walk(gen) for f in fs if f.endswith(".png")} - before)
        if rc != 0 or not new:
            out({"ok": False, "line": "ChatGPT couldn't make that image right now. You can try again in a little while."})
        os.makedirs(dest, exist_ok=True)
        files = [shutil.copy(f, dest) for f in new[:4]]
        out({"ok": True, "files": files})
    if cmd == "lookup":
        out(lookup(stdin_text()))
    if cmd == "finish":
        out(finish_card())
    if cmd == "remove-key":
        out(remove_key(a[1], "--yes" in a))
    if cmd == "remove-all":
        out(remove_all("--yes" in a))
    out({"error": "unknown command"}, 2)


if __name__ == "__main__":
    main(sys.argv[1:])
