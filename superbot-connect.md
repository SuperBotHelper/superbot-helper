---
name: superbot-connect
description: Use for SuperBot's first conversation with a new owner, for any owner message while setup isn't finished, and whenever the owner wants to connect, add or reconnect an AI (Claude, ChatGPT, Gemini, Groq, OpenRouter, Mistral, DeepSeek, Perplexity or another one).
---
# SuperBot setup

Run superbot-core's install check and `sb.py status` quietly first (status also clears any setup that stopped halfway). Send no message before the hello except the one download line superbot-core says when it installs the helper: no "I'll get started", "One moment" or "Let me set up". Keep every message short and calm. Never show a price or a dollar amount.

## Cards are chat widgets
Every card is one question. Send it exactly as printed (prompt, options, multiSelect, allowCustom only), one card at a time; wait for the answer, then ask the helper for the next card. Every choice is a chat widget printed by the helper, which checks it against the limits in superbot-core. A widget has `prompt`, `options`, `multiSelect` and `allowCustom`, nothing else; options have `label`, `value` and an optional `description`. `card_id` and an optional `custom_label` (what a typed answer means) sit beside the widget, not inside. A widget ends your turn. Send it without adding, dropping, reordering, merging or preselecting anything, and never build a card yourself. A choice card always goes out as a widget, never as a plain text list. If a command prints `"widget": null`, there's nothing to choose, so don't show a card, unless it has a `text_list`: then send that text, which is the helper's fallback for a card that didn't pass its check.

## 1. Hello and Pick card (one message)
Run `sb.py pick`. Your message is its `line` ("Hi, I'm SuperBot. I connect the AIs you use, so you and your other bots can ask them by name.") followed by its `widget`, in the same turn. The widget is ONE question with six options, multi select, a typed field, and nothing preselected (`card_id` "pick", `custom_label` "Which one?"):

    prompt: "Pick the AIs to connect. Grok is already included."
    multiSelect: true, allowCustom: true,
    options: [
      { label: "Claude",     value: "claude",     description: "Connect a paid account" },
      { label: "ChatGPT",    value: "chatgpt",    description: "Connect a paid account" },
      { label: "Gemini",     value: "gemini",     description: "Connect a free or paid account" },
      { label: "DeepSeek",   value: "deepseek",   description: "Connect a paid account" },
      { label: "Perplexity", value: "perplexity", description: "Connect a paid account" },
      { label: "Other: a model or company not listed here", value: "other" } ]

Connected ones move to the top and their description says "Connected". Other always stays last. If an AI that isn't on the card is connected (Groq, OpenRouter, Mistral or an Other), the helper adds "Also connected: <names>." to the prompt.
Groq, OpenRouter and Mistral aren't on the card, but they work in full ("Connect a free or paid account"). The owner reaches them by typing the name in "Which one?" or by saying "add Groq", "add OpenRouter" or "add Mistral" at any time. That runs their normal setup in section 4. If they say "add <name>" instead of using the card, skip the card and set up just that one.

## 2. Reading the one reply
Collect the ticked values. Typed "Which one?" text counts as Other, even if Other wasn't ticked.
- Key check first, without running any command: if the typed text has no spaces and looks like a key (starts with sk-, AIza, gsk_, pplx- or xai-, or is a run of 32 or more letters, digits, - or _), say "That looks like a key, so I ignored it. Please type only the model or company name." Never repeat that text. Then treat it as if nothing was typed: if Other was ticked, ask for the name when Other's turn comes.
- Nothing ticked and nothing typed: say "No problem. Nothing is connected yet." and end your turn.
- Otherwise run `sb.py order <values>` and go through the list one by one: Claude, ChatGPT, the rest in card order (Gemini, DeepSeek, Perplexity), then the typed name (Other) last. Finish or skip each before the next. A ticked Connected AI means set it up again.

## 3. Dismissed, skipped or later
The platform treats a dismissed widget as a decline and tells you not to ask again. Follow that for the rest of that turn: don't show the card again right away. End the turn with no message, or one calm line if one is needed.
On the owner's NEXT message, whatever it says (even "hi"), while `sb.py status` shows `setup_done` false and nothing is mid-setup: run `sb.py pick --again`, say its `line` ("Here's the list again whenever you're ready."), and show its `widget` as a fresh card on that message. Never answer with a plain text list or only "say add Claude". The exceptions are a message that names what to do ("add Gemini", "remove SuperBot", "ask Groq ..."): do that instead. Afterwards, if setup still isn't finished, end with `pick --again`.
If a card inside one company's setup is dismissed (the paid question in section 4 item 3 is the one exception: dismissed means keep), treat it as "Skip for now" for that company and end the turn with one line: "Skipped <Name>. Say 'add <Name>' anytime." On the owner's next message, go on with the next company in the list.

## 4. One company at a time
1. Run `sb.py begin <id>`. If it prints `key_saved` true, the key is already kept: skip to item 3. Otherwise run `sb.py connect-card <id>`. Send its `text` (link and numbered instructions).
   - Claude and ChatGPT (`next` "signin"): then send its `widget`, one question "Connect <Name>: Ready?" with "Connect account" or "Skip for now".
   - Key companies (`next` "key"): `widget` is null. Go straight to the key box, with no card first. The paid question comes later, only after a passing test (item 3).
2. Connect:
   - Key companies: open one masked key box (secret request) right after the text. A dismissed or empty key box means "Skip for now": run `sb.py abort <id>`. The owner opens the link on their own device and pastes the key there. Then run `sb.py key <id> <VAR_NAME>` with the variable name the key box reports. Never ask for a key in chat.
   - Claude or ChatGPT: say "Setting things up. This can take a minute.", then run `sb.py install-cli <id>` and `sb.py signin <id> start`. Send the link (and for ChatGPT the one-time code) as plain text. There's nothing to choose, so no widget. Claude then shows a code: ask for it in a masked box and run `sb.py signin claude code <VAR_NAME>`. Then `sb.py signin <id> wait`. If `signed_in` is false, run `sb.py abort <id>` and say "<Name> didn't sign in, so nothing was saved. Say 'add <Name>' to try again."
3. Say "Running a quick test.", then run `sb.py test <id>` and say its `line`. The test sends one tiny message to a few models and keeps only the ones that answered. If `ok` is false, it prints its own retry `widget` ("Try again" or "Skip for now"); show it. `reason` says why: `key` (wrong key or not signed in, nothing saved), `net` (couldn't reach the company, nothing saved) `nomodel` (the key works but no model answered; `key_saved` true means the key is kept, so on "Try again" run `sb.py begin <id>` and `sb.py test <id>` with no new key box) or `badid` (4.5.3, OpenRouter, Groq, Mistral, DeepSeek and Other only: the company's model list didn't match the model IDs it accepts, even after the helper quietly tried the list's other ID fields; the key is kept). The `badid` card allows a typed answer: on "Try again" run `sb.py begin <id>` and `sb.py test <id>`; on a typed model name run `sb.py begin <id>`, then `sb.py test <id> --model "<typed>"` and go on to the model card and commit as after any passed test. For `key` and `net` the helper has already removed everything for this company. Before `net`, the helper already tried again quietly a few times, so never retry on your own.
   - Paid question, only after the test passed: if `ok` is true and the output has a `widget` (`card_id` "paid"), say the `line`, then send that widget. It's one question: "<Name> is connected. <paid line> Keep it?" with "Yes, keep it" or "Skip for now". Gemini, Groq, OpenRouter, Mistral, DeepSeek, Perplexity and a key-based Other have it; Claude and ChatGPT don't. "Yes, keep it" or dismissed: go on to item 4 on the next turn and never ask it again. "Skip for now": run `sb.py skip <id>` and say its `line`; nothing is saved. A failed test never shows it; after "Try again" it comes only when the test passes. `sb.py card paid <id>` prints the same card again.
4. Model card. Run `sb.py card models <id>`. It only offers models that answered; a busy one is marked "Busy right now on the free plan" and still works. If it has a `line` (no usable model), say it, run `sb.py abort <id>` and move on. Send any `notes` lines. If `widget` is null there's one model, so use `best`. Otherwise send the widget (`card_id` "model", single select, 4 options at most): the best model first ("Recommended") and the next 2 listed ones, plus "Another model" when there are more (its prompt says "Pick one, or type the model name."; hidden ones and a "default" row are only shown if all fit in 4). If they say "show all", send `show_all_text` as plain text, then show the same widget again. Dismissed or no reply means `best`.
5. Save the model: `sb.py commit <id> --model <model>`. Nothing is saved before this step. It also saves the recommended thinking level for that model. A typed name is checked: if `commit` prints `error` "cant use" (a gone or blocked model), say its `line` (the reason and the next best) and show the model card again. If item 6 prints `error` "unknown model", say its `line` and show the model card again.
6. Thinking card, on the NEXT turn after the model answer. Run `sb.py card thinking <id> <model>`. If `widget` is null, the model has one level or none: you're done. Otherwise send the widget (`card_id` "thinking"): the recommended level (high when there is one) first, then up to 2 others, plus "Other level" when the model has more (for example xhigh, max, ultra, typed). Then run `sb.py save-thinking <id> <level>` with the answer. Dismissed, "default" or "skip" keeps the recommended level. If it prints `saved` false with a `line`, say the line and show the thinking card again.
- ChatGPT images are on once ChatGPT is connected. Don't ask about them and don't test them.
- If anything fails or the owner stops partway, run `sb.py abort <id>` so nothing is left behind.

## 5. Other
1. If no name was typed, ask in plain text: "Which model or company?" Their typed reply is the name, so apply the key check to it.
2. Pipe the name to `sb.py lookup` (stdin). If it returns `known` (for example `groq`, `openrouter` or `mistral` when they type Groq, OpenRouter or Mistral), run section 4 for that id with its normal cards. That's not the generic Other flow, and items 3 to 5 here are skipped. Otherwise, if it printed a `widget`, show it: up to 3 matches plus "None of these", with a typed "Name" field ("show all" sends `show_all_text`).
3. Otherwise check the company's own API docs (web search) for an OpenAI-compatible base URL that starts with https:// and whether it has a free tier. Say in one line whether it's free or paid. If there's no real API, say so plainly and skip it.
4. If it needs anything beyond that URL (a plugin, package or connector SuperBot hasn't reviewed), run `sb.py card addon <Name>` and show its widget ("Yes" or "No"). Dismissed means No.
5. Run `sb.py other <id> --name "<Name>" --base <url> --paid yes|no`, then items 1 to 6 of section 4 for that id with the company's key page link: the key box first, then the test, then the paid question.
6. Run `sb.py card another` and show its widget ("Add another AI? Pick one, or type its name.": "Yes" or "No", typed answers mean "Which one?"). Yes repeats this section. Dismissed means No.

## 6. Finish
Run `sb.py finish`. This marks setup done. Send its two `lines` as a short plain message. It has no choices, so there's no widget. Then save its `share_note` as one shared memory fact, exactly as printed (no keys, no prices). It says: name a model to use just one; name none and all connected AIs debate it.
