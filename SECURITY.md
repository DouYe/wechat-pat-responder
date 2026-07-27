# Security and platform notice

This project is an experimental desktop UI automation tool. It is not an
official WeChat/Weixin API and is not affiliated with Tencent.

- It does not inject DLLs, modify WeChat, decrypt databases, simulate private
  protocols, read payment passwords, or send payments.
- The "red packet" action is text-only. It never sends money.
- Automatic sending can select the wrong conversation if WeChat changes its
  layout or OCR makes a mistake. Test with a secondary account first.
- The app clears unsent text in the target input box before replying.
- UI automation may conflict with WeChat's terms or account policies. You are
  responsible for deciding whether to use it.

Do not report sensitive chat screenshots publicly. For security issues, open a
private GitHub security advisory instead of a public issue.
