---
name: superbot-use
description: Use when the owner or another bot asks SuperBot a question, asks a named AI, runs a debate, or has ChatGPT make an image.
---
# Using the connected AIs

Run superbot-core's install check first.

## Which models run
- A question that names no model goes to every connected AI as a debate. Grok is always in it.
- A named model runs alone. Several named models debate among themselves.
- A statement gets a short normal reply from you, with no models and no debate.
- With one connected AI, a question gets a plain answer from it and from you, with no debate and no card.
- Never add a model that isn't connected. Never pick one by guessing.

Examples:
| Message | What happens |
|---|---|
| "I like blue" | statement: short reply, no debate |
| "thanks" | statement: short reply, no debate |
| "ok" | statement: short reply, no debate |
| "Claude is connected now" | statement: short reply, no debate |
| "What's the best way to learn Spanish?" | question, no model named: `ask all` (a debate) |
| "Should I rent or buy?" | question, no model named: `ask all` (a debate) |
| "Create a logo for my bakery using Claude" | named: `ask claude` only |
| "Just ask Gemini what it thinks" | named: `ask gemini` only |
| "Skip the debate. Is 17 prime?" | no debate asked: you answer alone |
| "Use ChatGPT to write a haiku" | named: `ask chatgpt` only |
| "Have Claude and Gemini debate tabs vs spaces" | named: `debate claude,gemini` |
| "details" | after a debate: `details`, send its `text` as is |

## The wait line
When a debate will run, first send exactly: "These debates can become heated, so answers may take a couple minutes.", then run it.
- Run `sb.py debate-intro` (or `sb.py debate-intro <id,id,...>` for named models) before `ask all` or `debate`. If it prints `wait_line`, send that line as its own message first, then run the debate. If it prints `debate` false, send nothing extra.
- It goes out every time a debate runs, right after the question and before any waiting.
- Never for a statement, a single named model, "skip the debate", or 0 or 1 connected AI (no debate). Never inside the debate reply or `render` text. No other waiting message.

## Rules
- Grok is you. When Grok is named, answer yourself.
- Prompts go on stdin. Show answers as they came back, with each model's name.
- Never show prices or dollar amounts.

## Ask one
`sb.py ask <id> [--model M] [--thinking L]` with the prompt on stdin. Say the `answer`. If there is a `line`, say it once.

## Ask all (the default for a question)
Run `sb.py debate-intro` and send its `wait_line` first if it printed one. Write your own short answer to a file, then run `sb.py ask all --grok-file <that file>` with the question on stdin. The helper decides who is in it and prints `included` (always starts with Grok) and `mode`:
- `grok_only`: no AI is connected. Answer yourself.
- `single`: one AI. Show its answer and yours, one or two lines each. No debate words and no debate layout.
- `debate`: two or more. Reply in the debate layout below.

## Debate
`sb.py debate <id,id,...> [--grok-file F]` with the question on stdin, for named models only. Run `sb.py debate-intro <id,id,...>` first and send its `wait_line`. `ask all` works the same way. The models answer, read each other's answers, and say whether they agree; the helper does the back and forth.

The reply to the owner, in this order and nothing else:
1. The verdict, always the very first line, in bold: `**Verdict:** ` then one clear answer in one to three sentences, written by you from all the answers including yours (`summary.verdict_instruction`).
2. Only when `summary.disagreed_at_some_point` is true: a blank line, the quiet italic label `_How the debate went_`, then at most 4 short lines (about 500 characters): who agreed on what, who differed and why, with names, each position in one short sentence, and a brief "In the end they all agreed." when they did. No line about who changed their mind: that is only in `details`.
3. The notes, one short line each: a carried-forward note and any `lines` (a stand-in or a model that sat out).
4. Last, exactly: `_Reply "details" to see how each model answered and how the debate ran._` (only when `summary.details_line` is true).

The easy way: run `sb.py render` with your verdict on stdin and send its `text` exactly. It builds this layout from the last debate, `lines` and details line included, so don't send them again (`report_template` shows the same layout with a {verdict} slot).
Never mention rounds or the steps of the debate, never paste each model's full answer, and never list each model's final answer. No heading anywhere: nothing is bigger than the verdict. `debug` is not for display.

## Details
The details line goes out only after a debate. Never after a statement, a single named model, "skip the debate", or the plain answer with 0 or 1 AI.
When the owner replies "details" (also "show details", "breakdown", "how did that go" and the like), run `sb.py details` and send its `text` as is. It shows the last debate step by step, who changed their mind, retries, stand-ins and sit-outs, and the verdict. If it says there is no debate to show yet, say that.

## A model isn't available
The helper handles this. A busy model is tried again after a short pause, then up to 3 other models from the same company quietly answer for it, with a plain `line` and no card; if they are busy too, it sits this one out with a plain `line`. If a company's model list didn't match the IDs it accepts (OpenRouter, Groq, Mistral, DeepSeek or Other only), the helper quietly finds the right ID itself; if it can't, the line says the model list didn't match, never that it was busy. Send that line as printed. A gone model gets a stand-in from the same company for this answer, a `line` and a `widget`. Every card is one question. Send it exactly as printed (prompt, options, multiSelect, allowCustom only), one card at a time; wait for the answer, then ask the helper for the next card. There is one card per switched model, 2 options each ("Yes, keep it" or "No, just this once"), `card_id` `keep_<id>`. `ask` prints that card. `debate` prints the first one and lists the rest in `switches_left`; after each answer, run `sb.py card switch <id> <model>` for the next entry and send that card. Only for a question answered "Yes, keep it", run `sb.py save-model <id> <new model>`. Dismissed or unanswered means no. Never save a switch without that yes. A request from another bot gets the line in its reply, not a widget, and nothing is saved.

## Images
Only when ChatGPT is named for an image: `sb.py image` with the prompt on stdin (optionally `--out <new folder>`). Send the files back. If it fails, say its `line`.

## Requests from other bots
Same rules: a named model runs alone; a question with no model named runs `ask all`. Reply with the answers or the report.
