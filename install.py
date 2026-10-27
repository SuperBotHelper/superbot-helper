# SuperBot skill installer. Saves the four SuperBot skills if missing, after checking each file's sha256.
import hashlib, os, sys, urllib.request
C = "3d44fab021137c3cc5976fe2f468b27beef1d81a"
B = "https://raw.githubusercontent.com/SuperBotHelper/superbot-helper/" + C + "/"
S = {
 "superbot-core": "cd5b126d9f5f7ff831fc4cd7e28ff4e3ca5b8ed48deaf73d14df8085ef652755",
 "superbot-connect": "fa48bfdcecb6921f2c2537ea49fd6bdaf887b3cf0f607218b64e1b27ddb7918a",
 "superbot-use": "10e92bc58dd90a58283a338b9e6020c4d45d2028bccd75096d82e33fc9fc1b1a",
 "superbot-manage": "59acf94541c68ac19ab4da8f623dd4b015b51681b9355266cdac1b2583ad88e5",
}
root = os.path.expanduser("~/agent-data/workflows")
got = {}
for n, h in S.items():
    d = os.path.join(root, n, "SKILL.md")
    if os.path.isfile(d) and hashlib.sha256(open(d, "rb").read()).hexdigest() == h:
        continue
    try:
        data = urllib.request.urlopen(B + n + ".md", timeout=60).read()
    except Exception as e:
        sys.exit("download failed: %s" % type(e).__name__)
    if hashlib.sha256(data).hexdigest() != h:
        sys.exit("hash mismatch, nothing written for " + n)
    got[n] = data
for n, data in got.items():
    os.makedirs(os.path.join(root, n), exist_ok=True)
    t = os.path.join(root, n, ".tmp")
    open(t, "wb").write(data)
    os.replace(t, os.path.join(root, n, "SKILL.md"))
print("ok", sorted(got) or "already installed")
