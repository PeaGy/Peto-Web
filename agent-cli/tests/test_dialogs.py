"""Khung nổi kiểu OpenCode (tui/dialog.py, CLI 0.32.0) và /models, /connect (lộ trình nhiều nguồn, M4): khung giữa màn
hình trên nền tối, tìm, nhóm, yêu thích, đặt mặc định riêng, thêm khóa OpenAI (hiện thành chấm, kiểm bằng máy chủ OpenAI
giả trên 127.0.0.1), đổi tên, xóa hai lần."""

from __future__ import annotations

import threading

import pytest
from test_direct_source import KEY, OpenAIHandler, leaked, serve
from test_footer import settle
from test_mouse import click, find, mouse, rows
from test_screen import rich_glyphs, run  # noqa: F401 - fixture màn hình giả

from peto_agent import __main__ as cli
from peto_agent import config, connections, credentials, model_catalog as catalog, model_dialogs
from peto_agent.line_editor import Key
from peto_agent.loop import Session
from peto_agent.tui.dialog import Action, Option, PromptDialog, SelectDialog
from peto_agent.tui.theme import load as load_theme
from peto_agent.workspace import Workspace

PETO = {"key": "peto", "label": "Peto", "description": "Mặc định", "step_cost": 1}
SOL = {"key": "sol", "label": "6.1 Sol", "description": "Mạnh nhất", "step_cost": 4,
       "efforts": ["low", "medium", "high", "xhigh", "max"]}

needs_dpapi = pytest.mark.skipif(not credentials.available(), reason="Kho khóa DPAPI chỉ có trên Windows.")


def text_of(lines) -> list[str]:
    return ["".join(text for text, _ in line.spans) for line in lines]


def options():
    return [Option("Peto", value="a", category="Peto", current=True, footer="1 bước"),
            Option("6.1 Sol", value="b", category="Peto", description="Mạnh nhất", footer="4 bước"),
            Option("GPT-6 Luna", value="c", category="OpenAI", search_text="gpt-6-luna"),
            Option("GPT-6 Luna", value="c", category="Gần đây", searchable=False, description="OpenAI")]


def test_select_dialog_draws_like_opencode_and_finds_by_name_or_source():
    theme = load_theme()
    dialog = SelectDialog("Chọn model", options(), actions=[Action("Yêu thích", "ctrl+f", "favorite")])
    lines = dialog.render(theme, 100, 40)
    shown = text_of(lines)
    assert {line.width() for line in lines} == {60}, "khung rộng 60 ô như OpenCode"
    assert shown[1].strip().startswith("Chọn model") and shown[1].rstrip().endswith("esc")
    assert "Tìm" in shown[3] and dialog.chosen().value == "a", "dòng đang dùng được chọn sẵn"
    assert any(row.strip() == "OpenAI" for row in shown) and any("● Peto" in row for row in shown)
    assert shown[-2].strip() == "Yêu thích ctrl+f"
    active = next(line for line in lines if "● Peto" in "".join(text for text, _ in line.spans))
    assert any(style.get("bg") == theme.primary and style.get("b") for _, style in active.spans), "dòng chọn tô màu chính"

    for char in "luna":
        dialog.handle(Key("char", char))
    found = dialog.flat()
    assert [option.value for option in found] == ["c"], "bản trong Gần đây không lặp lại khi tìm"
    assert "OpenAI" in text_of(dialog.render(theme, 100, 40))[5], "khi tìm, tên nguồn đứng bên phải"
    for _ in "luna":
        dialog.handle(Key("backspace"))
    dialog.handle(Key("char", "z"))
    assert "Không tìm thấy kết quả" in "\n".join(text_of(dialog.render(theme, 100, 40)))


def test_select_dialog_keys_actions_and_confirming_twice():
    dialog = SelectDialog("Khóa", options(), actions=[Action("Xóa", "ctrl+d", "delete")])
    assert dialog.handle(Key("up")) is None and dialog.chosen().value == "c", "↑ ở dòng đầu quay vòng xuống cuối"
    assert dialog.handle(Key("ctrl", "d")) == "done" and dialog.result.action == "delete" and dialog.armed is None
    dialog.arm("c", "Bấm ctrl+d lần nữa để xóa")
    assert "Bấm ctrl+d lần nữa để xóa" in "\n".join(text_of(dialog.render(load_theme(), 80, 30)))
    dialog.handle(Key("ctrl", "d"))
    assert dialog.armed == "c", "bấm lần hai trên cùng dòng: nơi gọi thấy đã xác nhận"
    dialog.armed = None
    dialog.arm("c", "x")
    dialog.handle(Key("down"))
    assert dialog.armed is None, "đi chỗ khác là bỏ xác nhận"
    assert dialog.handle(Key("enter")) == "done" and dialog.result.kind == "select"
    assert dialog.handle(Key("escape")) == "done" and dialog.result.kind == "close"


def test_prompt_dialog_masks_secrets_and_never_takes_newlines():
    theme = load_theme()
    prompt = PromptDialog("Khóa API OpenAI", placeholder="sk-…", secret=True)
    assert prompt.handle(Key("enter")) is None, "trống thì không gửi"
    prompt.handle(Key("paste", "sk-abc\r\n123"))
    shown = "\n".join(text_of(prompt.render(theme, 80, 30)))
    assert "sk-abc" not in shown and "•" * 9 in shown and prompt.value == "sk-abc123"
    assert prompt.handle(Key("enter")) == "done" and prompt.result.text == "sk-abc123"
    prompt.busy = "Đang kiểm tra khóa…"
    assert prompt.handle(Key("escape")) is None, "đang kiểm thì bỏ qua phím"


def test_the_dialog_floats_centered_over_a_dimmed_screen_and_a_click_outside_closes_it(run):  # noqa: F811
    screen = run(100, 30)
    screen.ui.line("Câu trả lời trước của Peto.")
    answer = {}
    dialog = SelectDialog("Chọn model", options())
    thread = threading.Thread(target=lambda: answer.setdefault("value", screen.ui.dialog(dialog)), daemon=True)
    thread.start()
    assert settle(lambda: "Chọn model" in rows(screen))
    x, y = find(screen, "Chọn model")
    assert y == 30 // 4 + 1, "cách đỉnh một phần tư màn hình"
    assert x == (99 - 60) // 2 + 4, "canh giữa"
    assert "Câu trả lời trước của Peto." in rows(screen), "hội thoại vẫn thấy phía sau"
    behind = screen.ui.engine._hits[find(screen, "Câu trả lời trước")[1]]
    theme = screen.ui.theme
    assert all(style.get("fg") != theme.text for _, style in behind.spans), "phía sau tối đi"
    screen.press(Key("down"))
    assert dialog.chosen().value == "b"
    mouse(screen, "press", 2, 28)
    mouse(screen, "release", 2, 28)
    thread.join(timeout=3)
    assert answer["value"].kind == "close" and "Chọn model" not in rows(screen)


def session_with(screen, project, *, peto=(PETO, SOL)):
    work = Session(cli._offline_client({}), Workspace(project), screen.ui)
    cat = catalog.Catalog(list(peto), account="Bình", logged_in=True)
    work.model_catalog = cat
    work.supported_efforts = ["low", "medium", "high"]
    model_dialogs.refresh(work, cat)
    return work, cat


def in_thread(target):
    done = {}
    thread = threading.Thread(target=lambda: done.setdefault("value", target()), daemon=True)
    thread.start()
    return thread, done


def test_models_switch_this_conversation_favorite_and_default_are_separate(run, project):  # noqa: F811
    screen = run(100, 32)
    work, cat = session_with(screen, project)
    thread, done = in_thread(lambda: model_dialogs.models(screen.ui, work, cat))
    assert settle(lambda: "Chọn model" in rows(screen))
    assert "● Peto" in rows(screen) and "4 bước" in rows(screen)
    screen.press(Key("down"), Key("ctrl", "f"))
    assert settle(lambda: "Yêu thích" in rows(screen) and "Đã thêm 6.1 Sol vào Yêu thích." in rows(screen))
    assert catalog.favorites() == ["peto||sol"]
    screen.press(Key("ctrl", "d"))
    assert settle(lambda: "Từ lần mở peto sau, hội thoại mới dùng 6.1 Sol." in rows(screen))
    assert config.load()["model"] == "sol" and "mặc định" in rows(screen)
    screen.press(Key("enter"))
    # Mức "vừa" không còn hợp lệ? 6.1 Sol có medium nên không hỏi mức; đổi ngay.
    thread.join(timeout=3)
    assert done["value"] is True and work.model == "sol" and work.model_step_cost == 4
    assert "Hội thoại này giờ dùng 6.1 Sol" in rows(screen)
    assert catalog.recent() == ["peto||sol"]


def test_a_model_without_the_current_effort_asks_for_one(run, project):  # noqa: F811
    screen = run(100, 32)
    work, cat = session_with(screen, project, peto=(PETO, {**SOL, "efforts": ["xhigh", "max"]}))
    thread, done = in_thread(lambda: model_dialogs.models(screen.ui, work, cat))
    assert settle(lambda: "Chọn model" in rows(screen))
    screen.press(Key("down"), Key("enter"))
    assert settle(lambda: "Chọn mức suy nghĩ" in rows(screen) and "Model này không có mức vừa." in rows(screen))
    screen.press(Key("down"), Key("enter"))
    thread.join(timeout=3)
    assert work.effort == "max" and done["value"] is True


@needs_dpapi
def test_connect_adds_a_masked_key_checks_it_then_picks_a_model_renames_and_deletes(run, project,  # noqa: F811
                                                                                  agent_home):
    openai = serve(OpenAIHandler, reply=lambda body: (500, "không dùng"),
                   models=(200, {"data": [{"id": "gpt-6-luna"}, {"id": "gpt-6.1-sol"}]}))
    try:
        screen = run(100, 34)
        work, cat = session_with(screen, project)
        original = model_dialogs.add_key

        def add_key(ui, work, cat, *, endpoint=None):
            return original(ui, work, cat, endpoint=f"{openai.url}/v1")

        model_dialogs.add_key = add_key
        try:
            thread, done = in_thread(lambda: model_dialogs.sources(screen.ui, work, cat))
            assert settle(lambda: "Kết nối nguồn" in rows(screen))
            assert "Phổ biến" in rows(screen) and "✓ Peto" in rows(screen) and "Bình" in rows(screen)
            screen.press(Key("down"), Key("enter"))
            assert settle(lambda: "Khóa API OpenAI" in rows(screen))
            screen.press(Key("paste", "ngắn"), Key("enter"))
            assert settle(lambda: "Đây không giống một khóa API OpenAI." in rows(screen))
            screen.press(Key("paste", KEY))
            assert KEY not in rows(screen) and KEY[:8] not in rows(screen) and "•" * 20 in rows(screen)
            screen.press(Key("enter"))
            assert settle(lambda: "Chọn model · OpenAI" in rows(screen), timeout=6)
            assert [request["path"] for request in openai.requests] == ["/v1/models"]
            assert "GPT-6 Luna" in rows(screen) and "4 bước" not in rows(screen), "chỉ model của khóa vừa thêm"
            screen.press(Key("enter"))
            thread.join(timeout=3)
        finally:
            model_dialogs.add_key = original
        item = connections.load_all()[0]
        assert done["value"] is True and (work.source, work.model, work.connection) == ("openai-key", "gpt-6-luna",
                                                                                         item.id)
        assert "selection" not in config.load(), "kết nối xong chỉ đổi hội thoại này"
        assert credentials.load(item.id) == KEY and leaked(agent_home) == []

        # Đổi tên rồi xóa (bấm ctrl+d hai lần): hội thoại đang dùng khóa đó quay về Peto, có báo.
        thread, done = in_thread(lambda: model_dialogs.accounts(screen.ui, work, cat))
        assert settle(lambda: "Khóa đã kết nối" in rows(screen) and "Thêm khóa API" in rows(screen))
        assert "● OpenAI (khóa API riêng)" in rows(screen) and "2 model" in rows(screen)
        screen.press(Key("ctrl", "r"))  # dòng của khóa đang dùng được chọn sẵn
        assert settle(lambda: "Đổi tên khóa" in rows(screen))
        screen.press(*[Key("backspace")] * 30, Key("paste", "Khóa công ty"), Key("enter"))
        assert settle(lambda: "Đã đổi tên thành “Khóa công ty”." in rows(screen))
        assert connections.load_all()[0].label == "Khóa công ty"
        screen.press(Key("ctrl", "d"))
        assert settle(lambda: "Bấm ctrl+d lần nữa để xóa Khóa công ty" in rows(screen))
        assert connections.load_all(), "lần đầu chỉ hỏi lại"
        screen.press(Key("ctrl", "d"))
        thread.join(timeout=3)
        assert connections.load_all() == [] and done["value"] is False
        assert work.source == "peto" and "chuyển sang Peto" in rows(screen)
        assert not (agent_home / "credentials" / f"{item.id}.bin").exists()
    finally:
        openai.shutdown()
        openai.server_close()


def test_peto_row_without_a_login_explains_how_to_log_in(run, project):  # noqa: F811
    screen = run(100, 30)
    work = Session(cli._offline_client({}), Workspace(project), screen.ui)
    cat = catalog.Catalog([], logged_in=False)
    thread, done = in_thread(lambda: model_dialogs.sources(screen.ui, work, cat))
    assert settle(lambda: "Kết nối nguồn" in rows(screen))
    assert "chưa đăng nhập" in rows(screen)
    screen.press(Key("enter"))
    assert settle(lambda: "Máy này chưa đăng nhập Peto." in rows(screen))
    click(screen, "esc")
    thread.join(timeout=3)
    assert done["value"] is False


def test_resume_continues_with_the_conversations_own_model_when_it_is_still_available(project):
    from conftest import FakeUI
    from peto_agent import history

    first = Session(cli._offline_client({}), Workspace(project), FakeUI())
    first.select("peto", "sol", step_cost=4)
    first.items = [{"type": "message", "role": "user", "content": "sửa README"},
                   {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Xong"}]}]
    assert first.save()
    saved = history.load(project, first.client.server, first.session_id)

    second = Session(cli._offline_client({}), Workspace(project), FakeUI())
    second.model_catalog = catalog.Catalog([PETO, SOL], logged_in=True)
    second.supported_efforts = ["low", "medium", "high"]
    cli._open_session(second.ui, second, saved)
    assert (second.model, second.model_step_cost, second.model_label) == ("sol", 4, "6.1 Sol")
    assert "giờ tiếp tục" not in second.ui.text and "model" not in config.load(), "không đổi mặc định"

    third = Session(cli._offline_client({}), Workspace(project), FakeUI())
    third.model_catalog = catalog.Catalog([PETO], logged_in=True)
    cli._open_session(third.ui, third, saved)
    assert third.model == "peto", "model của hội thoại không còn: giữ model đang chọn"


def test_a_lost_default_key_is_reported_not_silently_replaced(project, monkeypatch):
    from conftest import FakeUI
    from test_loop_client import Handler

    peto = serve(Handler, reply=lambda path, body: (200, {"account": "Bình", "models": [PETO]}))
    try:
        config.save({"server": peto.url, "token": "peto_token_thu",
                     "selection": {"source": "openai-key", "connection": "openai-mat", "model": "gpt-6-luna"}})
        monkeypatch.chdir(project)
        ui = FakeUI(answers=["/exit"])
        assert cli.session(ui) == 0
        assert "Model mặc định gpt-6-luna (khóa riêng) không còn dùng được trên máy này nên peto dùng Peto." in ui.text
        assert "/models" in ui.text and "/connect" in ui.text
    finally:
        peto.shutdown()
        peto.server_close()
