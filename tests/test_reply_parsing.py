import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from WeChatPatResponder import (
    DOC_REPLY_ACTIONS,
    choose_unused_reply,
    dispatch_reply_action,
    load_tickle_state,
    parse_reply_actions,
    parse_reply_blocks,
    record_reply_sent,
    reply_action_key,
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

    def test_consecutive_message_separator_creates_one_action(self):
        text = "第一条\n>>>\n第二条\n---\n另一个行为"
        self.assertEqual(
            parse_reply_actions(text),
            [("第一条", "第二条"), ("另一个行为",)],
        )

    def test_normal_newline_remains_inside_one_message(self):
        text = "同一条消息第一行\n同一条消息第二行\n>>>\n下一条消息"
        self.assertEqual(
            parse_reply_actions(text),
            [
                (
                    "同一条消息第一行\n同一条消息第二行",
                    "下一条消息",
                )
            ],
        )


class GoogleDocReplyTests(unittest.TestCase):
    def test_current_document_has_25_top_level_actions(self):
        self.assertEqual(len(DOC_REPLY_ACTIONS), 25)

    def test_einstein_nested_item_is_a_second_message(self):
        self.assertIn(
            (
                "“疯狂是不断的尝试一件事情 并期待不同的结果” - 爱因斯坦",
                "而你我的朋友 非常疯狂",
            ),
            DOC_REPLY_ACTIONS,
        )

    def test_three_part_nested_action_stays_together(self):
        self.assertIn(
            (
                "这个人好烦 要不把他杀了把。",
                "不好意思刚刚自动回复",
                "你家地址在哪",
            ),
            DOC_REPLY_ACTIONS,
        )


class DispatchTests(unittest.TestCase):
    def test_messages_are_sent_separately_in_order(self):
        sent = []
        pauses = []
        dispatch_reply_action(
            ("第一条", "第二条"),
            sent.append,
            pauses.append,
        )
        self.assertEqual(sent, ["第一条", "第二条"])
        self.assertEqual(pauses, [0.6])


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
                record_reply_sent(
                    "alice",
                    "随机回复",
                    ("第一条\n第二行", "第二条独立消息"),
                )

            logged = history_path.read_text(encoding="utf-8")
            self.assertIn("[2026-07-29 12:34:56]", logged)
            self.assertIn("会话 ID: alice", logged)
            self.assertIn("类型: 随机回复", logged)
            self.assertIn("消息 1/2:\n第一条\n第二行", logged)
            self.assertIn("消息 2/2:\n第二条独立消息", logged)

    def test_v13_reply_history_migrates_to_action_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "tickle_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "counts": {"alice": 1},
                        "streaks": {},
                        "last_seen": {},
                        "used_library_replies": {"alice": ["旧回复"]},
                        "sent_replies": {"alice": ["旧回复"]},
                        "last_replies": {"alice": "旧回复"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("WeChatPatResponder.STATE_PATH", state_path):
                state = load_tickle_state()

            expected_key = reply_action_key(("旧回复",))
            self.assertEqual(state["schema_version"], 2)
            self.assertEqual(
                state["used_library_replies"]["alice"],
                [expected_key],
            )
            self.assertEqual(state["sent_replies"]["alice"], [expected_key])
            self.assertEqual(state["last_replies"]["alice"], expected_key)


if __name__ == "__main__":
    unittest.main()
