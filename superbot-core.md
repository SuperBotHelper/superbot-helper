---
name: superbot-core
description: Use when SuperBot needs its helper program installed, checked or repaired, before any other SuperBot step runs a command.
---
# SuperBot helper

SuperBot runs one small helper, `~/.superbot/bin/sb.py` (Python 3, standard library only, no installs). Every command prints one JSON object. Owner-facing lines come back in `line`; say them as they are.

## Install or check (run before any SuperBot command)
1. Run `python3 ~/.superbot/bin/sb.py version`. If it prints version 4.5.3 AND its sha256 equals `59ab0889ebcd38b74248b65ec9b77d9121ef6a66bcda918e4331f30fcd718552`, stop here and leave the helper untouched.
2. Otherwise (no helper, an error, any other version, or a different sha256), get the helper from its public GitHub page. First say this one plain line to the owner, nothing more: "I'm downloading my helper program from GitHub (SuperBotHelper/superbot-helper). It's checked against a fixed fingerprint before it runs." Then run exactly:

    python3 - <<'SBX'
    import hashlib, os, sys, urllib.request
    url = "https://raw.githubusercontent.com/SuperBotHelper/superbot-helper/6b62139bb1bbf0ab6a80359b44c38b033039376b/sb.py"
    want = "59ab0889ebcd38b74248b65ec9b77d9121ef6a66bcda918e4331f30fcd718552"
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
    except Exception as e:
        sys.exit("download failed: %s" % type(e).__name__)
    if hashlib.sha256(data).hexdigest() != want:
        sys.exit("hash mismatch, nothing written")
    d = os.path.expanduser("~/.superbot/bin")
    os.makedirs(d, mode=0o700, exist_ok=True)
    tmp = os.path.join(d, ".sb.py.tmp")
    open(tmp, "wb").write(data)
    os.replace(tmp, os.path.join(d, "sb.py"))
    print("ok")
    SBX

3. If it prints `download failed`, try it once more. If it still fails, tell the owner: "I couldn't reach GitHub just now, so my helper isn't installed. Please try again in a few minutes." If it prints `hash mismatch`, tell the owner: "My helper didn't pass its check, so I didn't install it. Please try again later." Never edit the helper by hand and never run a helper that failed its check.
4. Run step 1 again to confirm: version 4.5.3 and the same sha256.
5. Run `sb.py status` once. It updates settings left by older versions (same format) and removes half-finished setups older than 30 minutes and leftover temp files.

## Rules for every command
- Keys and sign-in codes reach the helper only as the NAME of the environment variable the key box created (`sb.py key <id> <VAR_NAME>`). Never put a key in a command, a file you write, a message or memory. Turn off shell tracing.
- Never print, read back or summarize `~/.superbot/keys.json`.
- Prompts go on stdin, never in the command line.

## Cards (chat widgets)
Every card is one question. Send it exactly as printed (prompt, options, multiSelect, allowCustom only), one card at a time; wait for the answer, then ask the helper for the next card.
- Every card the helper prints is checked by one final gate before it prints: a `widget` with exactly `prompt`, `options`, `multiSelect` and `allowCustom`. Options have `label`, `value` and an optional `description`. At most 6 options (only the Pick card uses 6, every other card 4), labels up to 40 characters, descriptions up to 80, prompts up to 200. There are no multi-question cards.
- Beside the widget the output has `card_id` (which question it is, for example `model`, `thinking` or `keep_groq`) and, when there's a typed box, `custom_label` (what to read a typed answer as, for example "Model name"). Neither goes inside the widget. The prompt itself says what to type when typing is allowed.
- Never merge two cards, add, drop or reorder options, or build a card of your own.
- If `widget` is null and there's a `text_list`, send that text as a normal message. It's a choice that didn't pass the gate; read the reply as a typed answer.
- A longer list always has a typed choice ("Another model", "Other level", "None of these") and a `show_all_text` to send as plain text when the owner says "show all".

## Commands
`version`, `status` (also rolls back a half-finished setup older than 30 minutes, keeps a newer one, and checks that each saved model still answers), `pick`, `order <ids>`, `connect-card <id>`, `begin <id>`, `skip <id>` ("Skip for now" on the paid card: nothing is kept), `other <id> --name N --base URL --paid yes|no`, `key <id> <VAR_NAME>`, `install-cli claude|chatgpt`, `signin claude|chatgpt start|code <VAR_NAME>|wait`, `test <id> [--model NAME]` (4.5.3: `--model` tests one typed model, for the `badid` card), `models <id>` (same as `card models <id>`), `card thinking <id> <model>`, `commit <id> --model M [--thinking L]`, `save-thinking <id> <level>`, `abort <id>`, `ask <id> [--model M] [--thinking L]`, `debate-intro [all|<id,id,...>]` (run first: prints `wait_line` only when a debate will run), `ask all [--grok-file PATH]` (also `ask` alone, `debate` alone or `debate all`: every connected AI), `debate <id,id,...> [--grok-file PATH]`, `render [--summary-file PATH]` (your verdict on stdin; prints the owner-facing debate text from the last debate, ending with the details line after a debate of 2 or more AIs), `details` (the last debate step by step as plain text, from `~/.superbot/last_details.json`, mode 600, answers cut to 600 characters, no keys; "There is no debate to show yet." before the first one), `save-model <id> <model>`, `image --out DIR`, `lookup`, `card retry <id> [net|key|nomodel|badid]|paid <id>|addon <Name>|another|switch <id> <model>|replace <id> <model>`, `finish`, `remove-key <id> [--yes]`, `remove-all [--yes]`.

## Models that answer
- The helper only shows or recommends a model that answered a tiny test call. Results are cached in `~/.superbot/probe.json` with a time (answered: 6 hours; busy: 30 minutes; gone or blocked: 24 hours).
- At most 8 tiny calls per company per check (3 for Claude and ChatGPT), 12 seconds each (40 for Claude and ChatGPT), best candidates first, stopping once 3 answered. Companies with a model list (Gemini, Groq, OpenRouter, Mistral, DeepSeek, Other) run up to 3 tiny calls at a time; Gemini tries flash-lite first, then flash, then the rest, with pro, preview and customtools models last.
- Once the model list answered, a timeout, 429 or 503 on a model means that model is busy (the test passes), a single 400 or 403 means that model is blocked, and a network or gateway error or an empty answer gets one quiet retry. Only the list call itself failing gives `net`. `key` comes only from a 401, or a 400 or 403 saying the key is invalid, on the list call or on two different models. `debug.probes` shows each try's status, the start of the error (scrubbed) and the rule that fired.
- A network error (no connection, a timeout, or a gateway error such as 502, 503 or 504) is tried again quietly after 3, 8 and 15 seconds, with at most 4 extra tries per check (list fetch and tiny calls share them) and 90 seconds in all. For `test` this applies to the list call; only then does it print the "Couldn't reach" card. A wrong key (401 or 403) and a gone model (404) are never tried again; busy (429) counts as working. Every model call in an ask or a debate (first answers, critiques and final answers) also gets quiet retries: a network error or an empty answer is tried again after 3, then 8 seconds, at most 2 extra tries, and never longer than the call's own timeout plus 60 seconds. If our own time limit runs out (kind `timeout`, not `net`), the call is tried once more with a limit 1.75 times longer (120 becomes 210 seconds). A debate spends at most 600 seconds on calls in all; past that nothing is retried. Only then is the model left out, with "I couldn't reach X just now." A model left out of the first answers gets another try in the next step: it answers with the others' answers in view and then counts as a full member (`debug.rejoined`). Busy (429, 503 or 529 on this path, or a high-demand message) is tried once more after a 4 second pause. If that fails too, or a call ran out of time after its longer try, up to 3 other models from the same company are tried quietly, 45 seconds each (90 for Claude and ChatGPT), within the 600 seconds (the first answers leave 90 seconds for the critiques and the critiques leave 90 for the final answers; once the 600 seconds are used up no new try starts): ones that answered recently first, then the rest, lighter ones and ones marked busy included; never a gone or blocked one, and for the key companies only free ones (DeepSeek and Perplexity: the same-model retry only). One that answers stands in for this answer and counts as a full member, with a note such as "Gemini answered with gemini-3.1-flash-lite because gemini-3.5-flash was busy." If all fail: "Gemini sat this one out: Google's servers were busy, and the other Gemini models were busy too." 4.5.3, for OpenRouter, Groq, Mistral, DeepSeek and Other only: a 400 or 422 saying the model ID is not valid is kind `badid`, never busy, key, net or noaccess. The helper reads a fresh model list once, tries that model under the list's other ID fields (at most 2 tries), saves the ID that worked and the field it came from (`~/.superbot/idfield.json`), and only then tries the other models. If nothing matches: "Groq sat this one out: Groq's model list didn't match what SuperBot expected." Claude, ChatGPT, Gemini and Perplexity never use this path. Each alternate try (model, status, kind, time) is in `debug.alternates`, the second try in `debug.busy_retry`. A wrong key (401 or 403) gets no retry and no other model. A gone model (404) is never retried; it keeps the stand-in and switch card. Each try's real reason (return code, timed out or not, the first 200 characters of error output, the limit used, time taken, try number, kind) is in `debug`. ChatGPT answers go to a separate file per call (process id plus a random id), removed afterwards even after a timeout, so two ChatGPT calls at once never read each other's answer. Test hook: `SB_TEST_CLOCK=1` makes the waits count on a fake clock instead of sleeping, and adds a `check` field to `test`; it changes nothing else.
- A model that is gone is never shown or picked; it appears only in `show_all_text` with its reason. A busy model still works and carries a plain note.
