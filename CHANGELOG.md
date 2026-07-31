# Changelog

## 1.7.1

- Materialize text replies with the native Windows Unicode clipboard instead
  of Tk clipboard ownership, preventing a later message from replacing an
  earlier queued paste on slower VMs.
- Wait for WeChat to process each paste and Send click before preparing the
  next message in a multi-message reply.

## 1.7.0

- Move startup and manual Google Doc reloads to a background worker so OCR,
  monitoring, and the UI remain responsive during large downloads.
- Raise the socket timeout from 4 to 90 seconds and stream the HTML export in
  512 KB chunks instead of retaining the full document and every Base64 image
  in memory at once.
- Show downloaded megabytes on the Reload button while a refresh is running.
- Add a persistent source-image index so unchanged cached images skip Base64
  decoding and image validation on later reloads.
- Keep the last successful reply snapshot active if a large refresh still
  fails.

## 1.6.0

- Import image-only numbered Google Doc entries as random actions.
- Cache each imported image locally under a stable content hash.
- Send image actions through the Windows bitmap clipboard and WeChat paste
  flow.
- Show `[图片]` in the library preview and readable reply history while using
  the image hash for per-conversation no-repeat tracking.

## 1.5.0

- Read the public Google Doc once at startup and on the new **Reload 文档**
  button, without network requests during pat-triggered replies.
- Preserve top-level action order and nested consecutive-message order.
- Convert visible `↵` markers in a Doc item into message-internal newlines.
- Cache the latest successful ordered Doc snapshot for offline fallback.
- Keep per-conversation no-repeat history stable when existing Doc text remains
  unchanged, while appended actions become available automatically.

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
