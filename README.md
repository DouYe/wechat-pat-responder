# WeChat Pat Responder

Experimental Windows automation that watches the visible WeChat/Weixin
conversation list for `tickled m` (`tickled me` or `tickled my`), opens the
matching conversation, and sends a weighted random response.

[Download the latest Windows ZIP](https://github.com/DouYe/wechat-pat-responder/releases/latest/download/WeChatPatResponder-Windows-x64.zip)
· [中文说明](README.zh-CN.md)

## Features

- Watches the visible left conversation list, not only the active chat.
- Uses Windows OCR and window capture; no DLL injection or protocol emulation.
- Avoids clicking an already-selected conversation.
- Tracks displayed WeChat time and local detection time.
- Handles repeated pats with per-conversation state and a short deduplication
  interval.
- Weighted actions:
  - 90% reply read directly from the live Google Doc
  - 4% persistent counter
  - 3% combo/streak response
  - 2% playful fake-system text
  - 1% text-only red-packet easter egg
- Reads the public
  [Google Doc reply source](https://docs.google.com/document/d/1zaxLelnWjSDkGEm1SFQnPh643NF7KGJXdcfjVFv7QdM/edit?tab=t.0).
  once at startup. Click **Reload 文档** whenever you want to import newly
  appended entries; pat-triggered replies do not make network requests.
- Runs startup/Reload downloads in the background with a 90-second socket
  timeout. Large exports are parsed in 512 KB chunks and the button displays
  downloaded megabytes, so OCR monitoring and the UI remain responsive.
- Preserves the document's action order. A top-level numbered item is one
  random action; its nested items are sent as additional, separate messages in
  order.
- Imports an image-only numbered item as an image reply. Images are downloaded
  only during startup/Reload, cached by content hash, and pasted into WeChat
  from the Windows image clipboard when selected.
- Keeps a source-image index inside `google_doc_media`, allowing unchanged
  images to reuse their validated local files without Base64 decoding on every
  later Reload.
- Saves every successful read as an ordered local cache. If Google Docs is
  temporarily unavailable, the last successful cache is used instead.
- Draws library replies without replacement for each detected conversation.
  A new cycle begins only after that conversation has received the entire
  current library, and the first reply of a new cycle cannot immediately repeat
  the previous reply.

## Google Doc reply format

- Each top-level numbered item is one random action.
- Nested numbered items belong to the preceding top-level action and are sent
  as separate messages in their displayed order.
- Put `↵` inside one numbered item to create a newline inside that same WeChat
  message. Two markers (`↵ ↵`) create a blank line.
- Put an image in its own top-level numbered item to make it one random image
  action. PNG, JPEG, GIF, and WebP source images are accepted; animated images
  are pasted as their first frame.

```text
1. “Doing the same thing and expecting different results is madness.”
   a. And you, my friend, are very mad.
2. First line ↵ Second line ↵ ↵ Final paragraph.
```

The app does not truncate replies, although WeChat may still enforce its own
message-length limit. Existing entries keep stable per-conversation history as
long as their text is not edited; newly appended entries automatically join the
unused pool.

Google's public HTML export still transfers the complete document on each
Reload; it does not provide an unauthenticated incremental feed. Compressing
very large source images before inserting them will therefore reduce every
Reload time, even though cached images no longer need to be decoded again.

## Supported systems

The packaged application supports **64-bit Windows 10 and Windows 11**.

It does not run natively on macOS, Linux, or ChromeOS because it depends on the
Windows WeChat client, `PrintWindow`, Windows OCR, and Windows input APIs. Those
systems can use a Windows VM or an always-on Windows PC through Chrome Remote
Desktop.

## Fastest installation: portable release

1. Install and sign in to the official Windows WeChat/Weixin client.
2. Install English OCR:
   - Windows Settings → Time & language → Language & region.
   - Add **English (United States)** and its language features.
   - Or download the source ZIP and run `Install-OCR.cmd` as administrator.
3. Download and extract
   [WeChatPatResponder-Windows-x64.zip](https://github.com/DouYe/wechat-pat-responder/releases/latest/download/WeChatPatResponder-Windows-x64.zip).
4. Keep the WeChat main window open and not minimized.
5. Double-click `Run.cmd`.
6. Click **开始监控**. Existing visible entries become the baseline; ask someone
   to pat you again to test.

The executable is not code-signed, so Windows SmartScreen may show a warning.
Review the source and build it yourself if you are not comfortable proceeding.

## Run from source

Requirements:

- Windows 10/11 x64
- Python 3.10 or newer, 64-bit
- Windows WeChat/Weixin desktop client
- English (United States) Windows OCR capability

Clone or download the repository, then run:

```bat
Setup.cmd
```

`Setup.cmd` creates an isolated `.venv`, installs `requirements.txt`, checks
OCR, and starts the app. Later launches can use `Run.cmd`.

If Python is missing and `winget` is available, setup offers to install Python
3.12. Run setup again afterward.

### Manual commands

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\check_environment.py
.\.venv\Scripts\python.exe WeChatPatResponder.py
```

## OCR troubleshooting

Run:

```bat
Install-OCR.cmd
```

Approve the administrator prompt, allow Windows to download English Basic and
OCR capabilities, and restart Windows. Alternatively, install English from
Windows Settings. Microsoft documents language installation in
[Language packs for Windows](https://support.microsoft.com/en-us/windows/language-packs-for-windows-a5094319-a92d-18de-5b53-1cfc697cfca8).

Use **单次 OCR 测试** in the application. The left-list preview should contain
`tickled m`. If it does not:

- enlarge the WeChat window and conversation list;
- make sure the matching row is visible;
- keep WeChat restored rather than minimized;
- verify English OCR with `tools\check_environment.py`.

## Important limitations

- Only visible conversation-list rows can be detected.
- OCR and click coordinates can break after a WeChat UI update.
- The app clears unsent text before sending a reply.
- The active WeChat window must not be minimized, although other windows may
  cover it.
- This is not an official WeChat API. Test with a secondary account and review
  [SECURITY.md](SECURITY.md).

## Build the standalone executable

```powershell
py -3 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.build-venv\Scripts\pyinstaller.exe --noconfirm --clean WeChatPatResponder.spec
```

The executable will be at `dist\WeChatPatResponder.exe`. GitHub Actions also
builds a portable ZIP on every push and publishes it when a `v*` tag is pushed.

## Data files

The app writes these beside the executable/source:

- `tickle_events.log`: detected event history
- `reply_history.txt`: readable per-conversation history of successfully sent
  replies
- `tickle_state.json`: persistent per-conversation counters, streaks, reply
  history, and no-repeat progress
- `google_doc_replies_cache.json`: latest ordered text/image reply snapshot
- `google_doc_media`: locally cached Google Doc images

These runtime files are ignored by Git.

## License

MIT. This project is not affiliated with Tencent, WeChat, or Weixin.
