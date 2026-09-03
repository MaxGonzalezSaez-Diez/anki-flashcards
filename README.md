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

`install.sh` copies Cursor skills, Hammerspoon shortcuts (`cmd+shift+space` then `f`/`p`/`q`/`l`/`e`/`c`/`s`/`r`), and the morning/extract jobs.

Chats and Anki snapshots live in `~/projects/anki-cards/Ai-Convo-QA`.
