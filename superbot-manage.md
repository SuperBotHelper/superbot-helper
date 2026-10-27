---
name: superbot-manage
description: Use when the owner asks what SuperBot has connected, wants to remove one AI's key or sign-in, asks whether its models still work, or says "Remove SuperBot".
---
# Managing SuperBot

Run superbot-core's install check first.

Every card is one question. Send it exactly as printed (prompt, options, multiSelect, allowCustom only), one card at a time; wait for the answer, then ask the helper for the next card.

## What's connected
`sb.py status`. List each connected AI with its model and thinking level, plus Grok. Never show keys. Say any `lines` once.
- `parked` lists companies whose key works but where no model answered yet. Say "Try again" there runs `sb.py test <id>` with the saved key.
- `dead_saved` lists saved models that no longer answer. Show its `widget` (`card_id` `fix_<id>`: "Yes, switch" or "Not now"). Only after "Yes, switch", run `sb.py save-model <id> <to>`. For the rest in `switches_left`, run `sb.py card replace <id> <model>` one at a time.

## Remove one
1. `sb.py remove-key <id>` (without --yes). Show its `widget` exactly as printed (one question, 2 options: "Yes, remove" or "No, keep it"). Dismissed means keep it.
2. Only after "Yes, remove": `sb.py remove-key <id> --yes`, then say its `line`.
SuperBot only removes keys and sign-ins it added itself.

## Remove SuperBot
1. `sb.py remove-all` (without --yes). Send its numbered `instructions` as plain text, then its `widget` exactly as printed (one question "Remove SuperBot?", 2 options: "Yes, remove" or "No, keep it"). Dismissed means keep it.
2. Only after "Yes, remove": `sb.py remove-all --yes`. Also forget the shared memory fact about SuperBot.
3. Say its `line`, then the remaining `instructions` as a short numbered list, with each company's key page so the owner can turn the key off there.
