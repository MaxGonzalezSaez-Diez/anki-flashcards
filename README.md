# anki-flashcards

Chats + Cursor answers → Anki. Needs [chat-logger](https://github.com/MaxGonzalezSaez-Diez/chat-logger).

1. Install [Anki](https://apps.ankiweb.net)
2. Anki → Tools → Add-ons → Get Add-ons → `2100166052` (Better Markdown). Restart Anki.
3. Clone [chat-logger](https://github.com/MaxGonzalezSaez-Diez/chat-logger) and this repo into `~/projects/`. `cd ~/projects/chat-logger && ./install.sh`
4. Chrome → `chrome://extensions` → Load unpacked → the `chat-logger` folder
5. Copy `.env.example` → `.env` and put your [OpenRouter](https://openrouter.ai) key in it
6. Edit `settings.yaml` (times, models, prompt, deck, `log_root`)
7. `./install.sh`
8. GitHub → this repo → Settings → Secrets: `OPENROUTER_API_KEY`, `QA_FLASHCARDS_REPO_TOKEN` (PAT that can push [anki-cards](https://github.com/MaxGonzalezSaez-Diez/anki-cards))

`install.sh` copies Cursor skills, optional Hammerspoon shortcuts, and the morning/extract jobs.

Chats and Anki snapshots live in `~/projects/anki-cards/Ai-Convo-QA`.

# Important
This app was written end to end by AI. There are NO WARRANTIES WHATSOEVER. You are responsible. Read the licence, keep backups of your folder.

## Hammerspoon shortcuts (optional)

Not required for chat logging, nightly cleanup, or Anki merge. Skip this if you only want the pipeline.

The shortcuts exist so you do not retype long flashcard prompts. In any focused text box (Claude, ChatGPT, Cursor, …) they paste a canned prompt and hit Return. That is separate from the Chrome logger: the logger records what you already typed; these hotkeys inject a request for QQQ/AAA cards (or explain / cleanup / …) into the chat you are in.

1. Install [Hammerspoon](https://www.hammerspoon.org) (Homebrew: `brew install --cask hammerspoon`)
2. Open Hammerspoon once → grant Accessibility when asked (System Settings → Privacy & Security → Accessibility)
3. Run `./install.sh` (copies `hammerspoon/flashcard.lua` → `~/.hammerspoon/flashcard.lua` and `dofile`s it from `init.lua`)
4. Hammerspoon menu bar icon → Reload Config (or `hs -c 'hs.reload()'` if the `hs` CLI is enabled)

**Use:** click the chat composer, then `cmd+shift+space`, then within 2 seconds one letter:

| Key | What it pastes |
| --- | --- |
| `f` | Full flashcard prompt over the conversation (QQQ/AAA) |
| `p` | One paper card: title, authors, venue, takeaways |
| `q` | A few new cards on recent concepts (skip papers / duplicates) |
| `l` | “Also give a copy-pasteable LaTeX block” |
| `e` | Explain simply, step by step, with an example |
| `c` | Clean up the selected / preceding text (grammar, no em dashes) |
| `s` | Summarize a long text with quotes + LaTeX |
| `r` | Random history/econ/etc. tidbit as a QQQ/AAA card |

If nothing happens: composer not focused, Hammerspoon not running, Accessibility off, or another app already owns `cmd+shift+space`. Edit bindings in `hammerspoon/flashcard.lua` and re-run `./install.sh` (or copy the file and Reload Config).
