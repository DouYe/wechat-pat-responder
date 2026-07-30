# Changelog

## 1.4.0

- Synchronized 25 random actions from the configured Google Doc.
- Added `>>>` syntax for sending nested entries as consecutive messages.
- Kept multiline text inside each individual message.
- Migrated reply history to action-level keys without losing v1.3 state.

## 1.3.0

- Raised the main reply library probability from 55% to 90%.
- Added persistent no-replacement selection per conversation.
- Prevented immediate repeats across reply cycles and dynamic actions.
- Added a readable `reply_history.txt` sent-message log.

## 1.2.0

- Added multiline replies separated by a standalone `---` line.
- Added absurd multiline copypasta and serious life quotes.
- Preserved ordinary line breaks and blank paragraphs when sending.

## 1.1.0

- Replaced the default reply library with longer, more absurd responses.
- Removed the 12-character reply limit.
- Made counter, combo, fake-system, and red-packet responses stranger too.

## 1.0.0

- First public Windows release.
