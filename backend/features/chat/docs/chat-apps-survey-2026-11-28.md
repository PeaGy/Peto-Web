# Open-source chat apps survey (2026-11-28)

The owner asked for direction 2 of the outside-repo list: what the large open-source chat apps have that Peto Web does
not. Direction 1 (streamdown-style block rendering) shipped the same day.

**Sources read.** READMEs and feature docs; no code was copied.
- Open WebUI (`open-webui/open-webui`, docs in `open-webui/docs`): chat features, data controls, sharing, message
  queue, follow-ups and shortcuts.
- LobeChat / LobeHub (`lobehub/lobe-chat`, `docs/usage`): message actions, topics, chat and pages.
- LibreChat (`danny-avila/LibreChat`, MIT): the README feature list and the v0.8.9 notes.

**What Peto already has, so it is left out below.**
- **Conversations:** projects with instructions, pinning, archive, Ctrl+K search with preview, past-chat search as a
  tool, edit/regenerate with version arrows, quoting a reply into the next question.
- **Reliability:** recovery and detached turns, live sync across tabs and devices.
- **Answers:** web search with a sources panel and citations, Mermaid, generated Word/Excel/slides, editing uploaded
  files, code execution through xAI.
- **People and providers:** memory and profile instructions, a GitHub connector, model and effort choice, dictation,
  Imagine, and per-reply "Lưu Markdown" and "In / lưu PDF".

## Candidates

Effort is S (a day or less), M (a few days) or L (a week or more). Value is my estimate for Peto's users.

| # | Feature | Seen in | Peto today | Value | Effort | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Read-only share link for a conversation | all three | none | high | M | **Do** |
| 2 | Export a whole conversation (Markdown, print/PDF) | all three | per reply only | medium | S | **Do** |
| 3 | Copy a reply as rich text (pastes formatted into Word/email) | LibreChat | Markdown text only | medium | S | **Do** |
| 4 | Message queue: type and send while Peto is answering | Open WebUI | composer shows Stop | medium | M | Maybe, after 1–3 |
| 5 | Read aloud in Chat (reuse Giọng Peto) | LibreChat, Open WebUI, LobeChat | Companion only | medium | S–M | Maybe; counts against the monthly TTS allowance |
| 6 | Temporary chat (not saved, no memory) | Open WebUI | none | medium | M | Maybe |
| 7 | Reply feedback (👍/👎) visible in `/admin` | LobeChat reactions, Open WebUI ratings | none | medium for the owner | S–M | Maybe; useful once usage grows |
| 8 | Follow-up suggestion chips after each reply | Open WebUI | none | low–medium | M | Skip for now: one extra model call per turn, against the planned weekly pool |
| 9 | Import ChatGPT exports | Open WebUI, LibreChat | none | low–medium | M | Skip until someone asks |
| 10 | Export all my data (JSON) from Settings | Open WebUI | none | medium (data rights, backups) | M | Pair with account deletion later |
| 11 | Side-by-side multi-model answers | Open WebUI | version arrows | low | M | Skip: doubles cost |
| 12 | Notes/Pages, channels, agent marketplaces, RAG knowledge bases, scheduled prompts | Open WebUI, LobeChat | — | — | L | Out of scope for Peto Web |

## Recommended items in more detail

### 1. Read-only share link

All three apps let a user publish a conversation as a link. Open WebUI's design is the most careful:
- private, signed-in users, or **open** (no sign-in, off by default);
- open links are read-only and apply to chats only;
- a "Shared chats" list in Data Controls revokes any link.

A sketch for Peto:
- **Snapshot, not a live view.** `POST /api/conversations/{id}/share` copies the current messages (text, sources,
  generated-document cards; images only if the owner ticks "kèm ảnh") into a `shared_chats` row with a random
  unguessable id. Later messages do not leak into the link.
- **Public read-only page** `/s/{id}`, served by the existing static catch-all with its own small page. It carries
  `noindex`, shows no Composer, and shows the sharer only by display name.
- **Revoke and safety.** Settings → Hội thoại gets "Link đã chia sẻ" with revoke. Deleting the conversation or the
  account deletes its links. Rate-limit creation.
- **Isolation.** The snapshot never includes memory, profile instructions or Discord-gateway context. Only rendered
  messages are copied.
- **Owner decisions needed:**
  - whether links are open to anyone or require a Peto login;
  - whether images and attachments are included.

### 2. Export the whole conversation

The conversation's `⋯` menu (sidebar row and chat header) gets "Tải Markdown" and "In / lưu PDF".
- Markdown is built in the browser from loaded messages, with sources listed per reply. The per-reply
  `saveResponseMarkdown` already does this.
- PDF reuses `printResponse` over the whole message list.
- No backend change.

### 3. Copy as rich text

The copy button writes both `text/plain` (Markdown, as today) and `text/html` (the rendered answer, with KaTeX as
MathML or plain text and tables as tables) through `ClipboardItem`, so pasting into Word, Google Docs or Gmail keeps
the formatting. Clipboard support differs across browsers and needs a fallback; the browser tests can cover Chromium.

## Not adopted, with reasons

- **Agents, marketplaces, MCP, channels, scheduled automations.** These belong to Peto Agent / Peto Harness, or are
  beyond a personal assistant web app.
- **RAG knowledge bases with vector stores.** Peto reads attachments in full and searches past chats; a vector store
  is heavy to run on the VPS for little gain at this scale.
- **Multi-model compare and follow-up chips.** They add model calls per turn while per-account usage is being measured
  for a weekly pool.
