import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from WeChatPatResponder import (
    App,
    DOC_REPLY_ACTIONS,
    choose_unused_reply,
    dispatch_reply_action,
    fetch_google_doc_reply_actions,
    format_message_preview,
    format_reply_actions_for_editor,
    image_message_path,
    image_to_dib_bytes,
    is_image_message,
    load_google_doc_cache,
    load_tickle_state,
    materialize_google_doc_image,
    parse_google_doc_reply_actions,
    parse_reply_actions,
    parse_reply_blocks,
    record_reply_sent,
    reply_action_key,
    save_google_doc_cache,
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
    def test_bundled_emergency_snapshot_has_25_top_level_actions(self):
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

    def test_html_export_preserves_order_nesting_and_visible_newlines(self):
        html = """
        <html><body>
          <ol class="x lst-kix_demo-0 start">
            <li><span>第一项</span></li>
          </ol>
          <ol class="x lst-kix_demo-1 start">
            <li><span>第二条消息</span><br><span>第二行</span></li>
          </ol>
          <ol class="x lst-kix_demo-0">
            <li><span>甲 ↵ 乙 ↵ ↵ 丙</span></li>
            <li><span>最后一项</span></li>
          </ol>
        </body></html>
        """
        self.assertEqual(
            parse_google_doc_reply_actions(html),
            [
                ("第一项", "第二条消息\n第二行"),
                ("甲\n乙\n\n丙",),
                ("最后一项",),
            ],
        )

    def test_image_only_numbered_item_is_cached_as_an_action(self):
        image_buffer = io.BytesIO()
        Image.new("RGB", (3, 2), (12, 34, 56)).save(
            image_buffer,
            "PNG",
        )
        source = (
            "data:image/png;base64,"
            + base64.b64encode(image_buffer.getvalue()).decode("ascii")
        )
        html = (
            '<ol class="lst-kix_demo-0">'
            "<li>文字条目</li>"
            f'<li><img src="{source}"></li>'
            "</ol>"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir)
            actions = parse_google_doc_reply_actions(
                html,
                image_resolver=lambda value: materialize_google_doc_image(
                    value,
                    media_dir,
                ),
            )

            self.assertEqual(actions[0], ("文字条目",))
            self.assertEqual(len(actions), 2)
            image_message = actions[1][0]
            self.assertTrue(is_image_message(image_message))
            self.assertTrue(image_message_path(image_message, media_dir).is_file())
            self.assertEqual(format_message_preview(image_message), "[图片]")

    def test_image_is_converted_to_windows_dib_without_bitmap_file_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.png"
            Image.new("RGBA", (2, 2), (255, 0, 0, 128)).save(image_path)

            dib = image_to_dib_bytes(image_path)

        self.assertNotEqual(dib[:2], b"BM")
        self.assertEqual(int.from_bytes(dib[:4], "little"), 40)
        self.assertGreater(len(dib), 40)

    def test_library_preview_hides_internal_image_token(self):
        token = f"[[WECHAT_IMAGE:{'a' * 64}.jpg]]"
        preview = format_reply_actions_for_editor(
            [("文字", token)]
        )
        self.assertEqual(preview, "文字\n>>>\n[图片]")

    def test_live_fetch_is_cache_busted(self):
        html = (
            '<ol class="lst-kix_demo-0">'
            "<li>实时第一条</li><li>实时第二条</li></ol>"
        )
        captured = {}

        class Headers:
            @staticmethod
            def get_content_charset():
                return "utf-8"

        class Response:
            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            @staticmethod
            def read():
                return html.encode("utf-8")

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return Response()

        actions = fetch_google_doc_reply_actions(
            export_url="https://example.test/export?format=html",
            timeout=2.5,
            opener=opener,
            now_fn=lambda: 123.456,
        )
        self.assertEqual(actions, [("实时第一条",), ("实时第二条",)])
        self.assertIn("cache_bust=123456", captured["url"])
        self.assertEqual(captured["timeout"], 2.5)

    def test_cache_round_trip_keeps_action_and_message_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "doc-cache.json"
            actions = [
                ("第一行为", "第二条消息"),
                ("第二行为",),
            ]
            save_google_doc_cache(actions, cache_path)
            self.assertEqual(load_google_doc_cache(cache_path), actions)

    def test_pat_selection_uses_loaded_snapshot_without_network(self):
        app = App.__new__(App)
        app.reply_actions_cache = [("已载入的第一条",), ("已载入的第二条",)]
        with patch(
            "WeChatPatResponder.fetch_google_doc_reply_actions"
        ) as fetch:
            self.assertEqual(
                app.get_reply_actions(),
                app.reply_actions_cache,
            )
        fetch.assert_not_called()

    def test_reload_replaces_cache_and_visible_library_preview(self):
        app = App.__new__(App)
        old_actions = [("旧词条",)]
        new_actions = [("新词条一",), ("新词条二", "连续消息")]
        app.reply_actions_cache = old_actions
        app.reply_actions_digest = "old-digest"
        app.doc_refresh_succeeded = True
        app.doc_last_error = ""
        app.set_reply_library_preview = Mock()
        app.log = Mock()

        with (
            patch(
                "WeChatPatResponder.fetch_google_doc_reply_actions",
                return_value=new_actions,
            ),
            patch("WeChatPatResponder.save_google_doc_cache"),
        ):
            loaded = app.refresh_reply_library()

        self.assertEqual(loaded, new_actions)
        self.assertEqual(app.reply_actions_cache, new_actions)
        app.set_reply_library_preview.assert_called_once_with(new_actions)


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
