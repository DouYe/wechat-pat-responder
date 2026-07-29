import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from WeChatPatResponder import (
    choose_unused_reply,
    parse_reply_blocks,
    record_reply_sent,
)


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


class NoRepeatTests(unittest.TestCase):
    def test_chooses_only_from_unused_replies(self):
        reply, reset_cycle = choose_unused_reply(
            ["甲", "乙", "丙"],
            ["甲"],
            choice_fn=lambda items: items[0],
        )
        self.assertEqual(reply, "乙")
        self.assertFalse(reset_cycle)

    def test_new_cycle_does_not_immediately_repeat_last_reply(self):
        reply, reset_cycle = choose_unused_reply(
            ["甲", "乙", "丙"],
            ["甲", "乙", "丙"],
            last_reply="甲",
            choice_fn=lambda items: items[0],
        )
        self.assertEqual(reply, "乙")
        self.assertTrue(reset_cycle)

    def test_duplicate_library_entries_are_deduplicated(self):
        reply, reset_cycle = choose_unused_reply(
            ["甲", "甲", "乙"],
            ["甲"],
            choice_fn=lambda items: items[0],
        )
        self.assertEqual(reply, "乙")
        self.assertFalse(reset_cycle)

    def test_entire_library_is_used_before_a_new_cycle(self):
        candidates = [f"回复 {index}" for index in range(110)]
        used = []
        for _ in candidates:
            reply, reset_cycle = choose_unused_reply(
                candidates,
                used,
                choice_fn=lambda items: items[0],
            )
            self.assertNotIn(reply, used)
            self.assertFalse(reset_cycle)
            used.append(reply)

        reply, reset_cycle = choose_unused_reply(
            candidates,
            used,
            last_reply=used[-1],
            choice_fn=lambda items: items[0],
        )
        self.assertTrue(reset_cycle)
        self.assertNotEqual(reply, used[-1])


class ReplyHistoryTests(unittest.TestCase):
    def test_log_contains_id_action_and_full_multiline_reply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "reply_history.txt"
            with (
                patch(
                    "WeChatPatResponder.REPLY_HISTORY_PATH",
                    history_path,
                ),
                patch(
                    "WeChatPatResponder.time.strftime",
                    return_value="2026-07-29 12:34:56",
                ),
            ):
                record_reply_sent("alice", "随机回复", "第一行\n第二行")

            logged = history_path.read_text(encoding="utf-8")
            self.assertIn("[2026-07-29 12:34:56]", logged)
            self.assertIn("会话 ID: alice", logged)
            self.assertIn("类型: 随机回复", logged)
            self.assertIn("第一行\n第二行", logged)


if __name__ == "__main__":
    unittest.main()
