import unittest

from WeChatPatResponder import parse_reply_blocks


class ReplyParsingTests(unittest.TestCase):
    def test_preserves_newlines_and_blank_paragraphs(self):
        text = "第一行\n第二行\n\n空白段落后\n---\n另一条"
        self.assertEqual(
            parse_reply_blocks(text),
            ["第一行\n第二行\n\n空白段落后", "另一条"],
        )

    def test_separator_must_be_on_its_own_line(self):
        text = "句子里的 --- 不会切开\n  ---  \n下一条"
        self.assertEqual(
            parse_reply_blocks(text),
            ["句子里的 --- 不会切开", "下一条"],
        )

    def test_accepts_windows_line_endings(self):
        text = "第一行\r\n第二行\r\n---\r\n第三行"
        self.assertEqual(
            parse_reply_blocks(text),
            ["第一行\n第二行", "第三行"],
        )


if __name__ == "__main__":
    unittest.main()
