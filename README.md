# flashcard-qa

Chats + Cursor answers → Anki. Needs [read_chat_gui](https://github.com/MaxGonzalezSaez-Diez/read_chat_gui).

1. Install [Anki](https://apps.ankiweb.net)
2. Anki → Tools → Add-ons → Get Add-ons → `2100166052` (Better Markdown). Restart Anki.
3. Clone [read_chat_gui](https://github.com/MaxGonzalezSaez-Diez/read_chat_gui) and this repo. `cd read_chat_gui && ./install.sh`
4. Chrome → `chrome://extensions` → Load unpacked → the `read_chat_gui` folder
5. Copy `.env.example` → `.env` and put your [OpenRouter](https://openrouter.ai) key in it
6. Edit `settings.yaml` (times, models, prompt, deck, `log_root`)
7. `./install.sh`
8. GitHub → this repo → Settings → Secrets: `OPENROUTER_API_KEY`, `QA_FLASHCARDS_REPO_TOKEN` (PAT that can push the cards repo in `data_repo`)

`install.sh` copies Cursor skills, Hammerspoon shortcuts (`cmd+shift+space` then `f`/`p`/`q`/`l`/`e`/`c`/`s`/`r`), and the morning/extract jobs.

`log_root` here and in `read_chat_gui/settings.yaml` must be the same path.
