"""Schema công cụ của Agent theo khả năng CLI khai báo.

Bản CLI đang cài nhận đúng từng chữ schema của bộ khả năng nó khai báo: đổi chữ là CLI cũ có thể vỡ (schema strict) và
mất prompt cache. Khả năng mới (GĐ 4, 2026-10-12: explore_v2, edit_v2) chỉ đổi schema khi CLI khai báo chúng.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from features.agent.tools import FEATURES, tool_schemas

BASE = ("cwd", "browser", "browser_act", "browser_outside", "skills", "mcp")

# Mã băm schema của các bộ khả năng đã phát hành, ghim ngày 2026-10-12 trước khi thêm khả năng mới.
SHIPPED = {
    (): "a30c0d446daada74d4b774a29a28f0b5d289df70a0ee5c7b731cc2f0c150c2ed",
    ("cwd",): "92c60750ebc1801f4b77cc6134109e3b57a155e2c7483f676a04dca608f6828d",
    ("cwd", "browser"): "3fe1e2c680136794bcd1485bd579dfcc13c06b8c3f0aec2cfcecb90ef62ba022",
    ("cwd", "browser", "browser_act"): "676c8b425ddc57ac7c0bc218cfe6895f8a61c99c83426af1d9a1cf67fd0d9313",
    ("cwd", "browser", "browser_act", "browser_outside"):
        "5c1d1cba99e10a6cad7058cc6e6154f4b4aa466e3dde4c02f406b7c93783d2ec",
    BASE[:5]: "f2667e6eb422077cf04f3d2cab07ab0eca13bd714008203ec58b5ce7642fa8d2",
    BASE: "9cbf0adbc6889295adaa79a729d43f244b6d3a08930bcdb4153b5e0551f15f36",
    # CLI 0.18–0.20 (ghim ngày 2026-10-12 trước khi thêm question, patch).
    BASE + ("explore_v2", "edit_v2"): "1934f1c23f55230fd65021385c8dcdf621820e752a7e069e0887f10373cbcd09",
}


def digest(features) -> str:
    data = json.dumps(tool_schemas(frozenset(features)), ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("features,expected", SHIPPED.items())
def test_shipped_feature_sets_keep_their_exact_schemas(features, expected):
    assert digest(features) == expected


def names(features) -> list[str]:
    return [tool["name"] for tool in tool_schemas(frozenset(features))]


def schema(features, name) -> dict:
    return next(tool for tool in tool_schemas(frozenset(features)) if tool["name"] == name)


def test_explore_v2_numbers_reads_groups_searches_and_appends_find_files_last():
    before, after = names(BASE), names(BASE + ("explore_v2",))
    assert after[:-1] == before and after[-1] == "find_files", "công cụ mới ở cuối để giữ phần đầu cho prompt cache"
    assert "số dòng" in schema(BASE + ("explore_v2",), "read_file")["description"]
    assert "gộp theo tệp" in schema(BASE + ("explore_v2",), "search_files")["description"]
    find = schema(BASE + ("explore_v2",), "find_files")["parameters"]
    assert find["required"] == ["pattern", "path"] and find["additionalProperties"] is False


def test_edit_v2_adds_replace_all_in_place():
    tools = tool_schemas(frozenset(BASE + ("edit_v2",)))
    assert [tool["name"] for tool in tools] == names(BASE)
    edit = schema(BASE + ("edit_v2",), "edit_file")
    assert list(edit["parameters"]["properties"]) == ["path", "old_text", "new_text", "replace_all"]
    assert edit["parameters"]["properties"]["replace_all"]["type"] == ["boolean", "null"]
    assert "gần đúng" in edit["description"]


def test_new_features_are_known_to_the_server():
    assert {"explore_v2", "edit_v2", "question", "patch", "title", "steer", "jobs_notify", "plan_mode",
            "btw"} <= FEATURES


def test_instructions_explain_the_new_tools_only_when_declared():
    from features.agent import api as agent_api

    plain = agent_api._instructions({"features": list(BASE)}, False)
    assert "find_files" not in plain and "replace_all" not in plain
    both = agent_api._instructions({"features": list(BASE) + ["explore_v2", "edit_v2"]}, False)
    assert "find_files" in both and "replace_all" in both and "path/to/file.py:42" in both
    assert "approximate match" in both


async def test_me_lists_the_features_the_server_understands(client, anon_client):
    from tests.test_agent_api import bearer, connect, login_as

    await login_as(client, "discord")
    token = await connect(anon_client, client)
    me = (await anon_client.get("/api/agent/me", headers=bearer(token))).json()
    assert me["agent_features"] == sorted(FEATURES) and "explore_v2" in me["agent_features"]


def _strict(node) -> None:
    """Schema strict: mọi object liệt kê đủ required và cấm thuộc tính lạ, ở mọi tầng."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False and node["required"] == list(node["properties"])
        for value in node.values():
            _strict(value)
    elif isinstance(node, list):
        for value in node:
            _strict(value)


def test_question_adds_ask_user_last_with_a_strict_schema():
    before, after = names(BASE + ("explore_v2", "edit_v2")), names(BASE + ("explore_v2", "edit_v2", "question"))
    assert after[:-1] == before and after[-1] == "ask_user", "công cụ mới ở cuối để giữ prompt cache"
    ask = schema(BASE + ("question",), "ask_user")
    _strict(ask["parameters"])
    assert "(nên chọn)" in ask["description"]


def test_patch_replaces_edit_and_write_only_for_gpt_models():
    features = frozenset(BASE + ("explore_v2", "edit_v2", "patch"))
    plain = [tool["name"] for tool in tool_schemas(features)]
    assert plain == names(BASE + ("explore_v2", "edit_v2")), "model không phải GPT thì khả năng patch không đổi gì"
    gpt = [tool["name"] for tool in tool_schemas(features, patch_model=True)]
    assert "edit_file" not in gpt and "write_file" not in gpt
    assert gpt.index("apply_patch") == plain.index("edit_file"), "apply_patch đứng đúng chỗ edit_file"
    assert {"delete_file", "move_file"} <= set(gpt)
    assert [tool["name"] for tool in tool_schemas(frozenset(BASE), patch_model=True)] == \
        [name for name in names(BASE) if name != "update_plan"], "CLI chưa khai báo patch thì GPT vẫn dùng edit_file"
    patch = next(tool for tool in tool_schemas(features, patch_model=True) if tool["name"] == "apply_patch")
    _strict(patch["parameters"])


def test_new_prompts_follow_the_declared_features_and_model():
    from features.agent import api as agent_api

    plain = agent_api._instructions({"features": list(BASE)}, False)
    assert "ask_user" not in plain and "[Người dùng nhắn thêm" not in plain and "[Tự động]" not in plain
    full = agent_api._instructions({"features": list(BASE) + ["question", "steer", "jobs_notify", "plan_mode",
                                                              "patch"]}, False)
    assert "ask_user" in full and "[Người dùng nhắn thêm" in full and "[Tự động]" in full and "[Peto Agent]" in full
    assert "apply_patch" not in full, "Peto (Grok) vẫn sửa bằng edit_file"
    luna = agent_api._instructions({"features": ["patch", "question", "steer"]}, False, model="luna")
    assert "*** Begin Patch" in luna and "ask_user" in luna and "adjustment to the current task" in luna
    haiku = agent_api._instructions({"features": ["patch"]}, False, model="haiku")
    assert "*** Begin Patch" not in haiku, "Claude vẫn sửa bằng edit_file"


def test_gpt_models_get_no_update_plan_tool_or_prompt():
    """Chủ web chọn ngày 2026-10-14: ở hai lượt thi, 6 Luna dành 29/96 rồi 29/90 lượt chỉ để gọi update_plan, và lời
    nhắc gửi chung lượt không đổi được. GPT mất công cụ đó; Peto (Grok) và Claude giữ nguyên."""
    from features.agent import api as agent_api

    for features in ((), BASE, BASE + ("explore_v2", "edit_v2", "question", "patch")):
        gpt = [tool["name"] for tool in tool_schemas(frozenset(features), patch_model=True)]
        assert "update_plan" not in gpt, features
        assert "update_plan" in names(features), "model không phải GPT vẫn có danh sách việc"
    context = {"features": list(BASE) + ["patch", "question"]}
    for model in ("luna", "terra", "sol"):
        assert "update_plan" not in agent_api._instructions(context, False, model=model), model
    for model in ("haiku", "sonnet"):
        assert "update_plan" in agent_api._instructions(context, False, model=model), model
    assert "update_plan" in agent_api._instructions(context, False), "Peto giữ lời nhắc tiếng Việt về danh sách việc"


# CLI 0.21–0.24 (ghim ngày 2026-10-15 trước khi thêm read_more, output_files, wrapup, user_guide). Model GPT có bộ
# riêng: apply_patch thay edit_file và không có update_plan.
SHIPPED_0_21 = BASE + ("explore_v2", "edit_v2", "question", "patch", "title", "steer", "jobs_notify", "plan_mode",
                       "btw")
SHIPPED_GPT = {
    SHIPPED_0_21: "c5063ed42e2df8753bfa089743dad5a2e9bf4c19e8f4141801e633477261a927",
}


def test_cli_0_21_to_0_24_keep_their_exact_schemas():
    assert digest(SHIPPED_0_21) == "91cab53d5c5de2d65761670a1e99ee339356c21da389b1894bc0bd82c9a64951"
    assert digest(SHIPPED_0_21[:-1]) == digest(SHIPPED_0_21), "btw không đổi schema"
    for features, expected in SHIPPED_GPT.items():
        data = json.dumps(tool_schemas(frozenset(features), patch_model=True), ensure_ascii=False, sort_keys=True)
        assert hashlib.sha256(data.encode()).hexdigest() == expected


def test_read_more_replaces_read_file_in_place_only_with_explore_v2():
    """CLI 0.25.0: nhật ký thật có 88/269 lần đọc bị cắt ở 160 dòng; đọc tới 1000 dòng mỗi lần."""
    v2, v3 = SHIPPED_0_21, SHIPPED_0_21 + ("read_more",)
    assert names(v3) == names(v2), "thay đúng chỗ, không thêm bớt công cụ"
    read = schema(v3, "read_file")
    assert "1000 dòng" in read["description"] and "số dòng" in read["description"]
    assert list(read["parameters"]["properties"]) == ["path", "start_line", "end_line"]
    assert "1000 dòng" in read["parameters"]["properties"]["end_line"]["description"]
    _strict(read["parameters"])
    assert "160" not in json.dumps(read, ensure_ascii=False)
    assert schema(BASE + ("read_more",), "read_file") == schema(BASE, "read_file"), "CLI chưa đánh số dòng: giữ bản cũ"


def test_output_files_appends_read_output_last():
    before, after = names(SHIPPED_0_21), names(SHIPPED_0_21 + ("output_files",))
    assert after[:-1] == before and after[-1] == "read_output"
    read_output = schema(SHIPPED_0_21 + ("output_files",), "read_output")
    _strict(read_output["parameters"])
    assert list(read_output["parameters"]["properties"]) == ["output_id", "pattern", "start_line", "end_line"]
    gpt = [tool["name"] for tool in tool_schemas(frozenset(SHIPPED_0_21 + ("output_files",)), patch_model=True)]
    assert gpt[-1] == "read_output"


def test_new_0_25_features_are_known_and_change_prompts_only_when_declared():
    from features.agent import api as agent_api
    from prompts import english as english_prompts

    assert {"read_more", "output_files", "wrapup", "user_guide"} <= FEATURES
    for model in ("peto", "luna", "haiku"):
        before = agent_api._instructions({"features": list(SHIPPED_0_21)}, False, model=model)
        after = agent_api._instructions({"features": list(SHIPPED_0_21) + ["read_more", "output_files"]}, False,
                                        model=model)
        assert "targeted read_file ranges" in before and "targeted read_file ranges" not in after, model
        assert "whole in one read_file call" in after and "read_output" in after, model
    assert english_prompts.agent_prompt(plan=False, read_more=True).count("update_plan") == 0


def test_old_feature_sets_get_the_english_instructions_without_new_parts():
    """Từ 2026-10-15 mọi CLI, kể cả bản cũ, nhận chỉ dẫn tiếng Anh; phần của khả năng chưa khai báo vẫn không có."""
    from features.agent import api as agent_api
    from prompts import english as english_prompts

    context = {"features": list(SHIPPED_0_21), "user_guidance": "Luôn dùng pnpm."}
    peto = agent_api._instructions(context, False)
    assert "Luôn dùng pnpm" not in peto, "chưa khai báo user_guide thì không gửi hướng dẫn chung"
    assert english_prompts.AGENT_PROMPT in peto and "\n\n\n\n" not in peto
    luna = agent_api._instructions(context, False, model="luna")
    assert english_prompts.AGENT_PROMPT_NO_PLAN in luna


def test_user_guidance_is_wrapped_apart_from_project_guidance_and_bounded():
    from features.agent import api as agent_api

    context = {"features": ["user_guide"], "user_guidance": "Luôn trả lời tiếng Việt, dùng pnpm.",
               "project_guidance": [{"path": "AGENTS.md", "scope": ".", "text": "Chạy npm test."}]}
    text = agent_api._instructions(context, False)
    assert "general guidance" in text and "dùng pnpm" in text
    assert text.index("dùng pnpm") < text.index("Chạy npm test."), "hướng dẫn dự án đứng sau, được ưu tiên"
    long = agent_api._instructions({**context, "user_guidance": "x" * 40001}, False)
    assert "too long" in long and "x" * 100 not in long
    assert "general guidance" not in agent_api._instructions({**context, "user_guidance": "   "}, False)


def test_subagent_appends_explore_last_and_its_tools_are_read_only():
    """CLI 0.27.0 (theo agent "explore" của opencode): công cụ explore ở cuối danh sách; agent con chỉ tìm và đọc."""
    from features.agent.tools import EXPLORE_DEPTHS, explore_schemas

    current = SHIPPED_0_21 + ("read_more", "output_files", "wrapup", "user_guide")
    before, after = names(current), names(current + ("subagent",))
    assert after[:-1] == before and after[-1] == "explore"
    explore = schema(current + ("subagent",), "explore")
    _strict(explore["parameters"])
    assert explore["parameters"]["properties"]["depth"]["enum"] == list(EXPLORE_DEPTHS) == ["quick", "medium", "thorough"]
    child = explore_schemas(frozenset(current + ("subagent",)))
    assert [tool["name"] for tool in child] == ["list_files", "read_file", "search_files", "find_files"]
    assert child[1] == schema(current, "read_file"), "agent con đọc đúng như Peto (số dòng, 1000 dòng)"
    assert [tool["name"] for tool in explore_schemas(frozenset())] == ["list_files", "read_file", "search_files"]


def test_subagent_prompt_only_when_declared():
    from features.agent import api as agent_api

    plain = agent_api._instructions({"features": list(SHIPPED_0_21)}, False)
    assert "Explore subagent" not in plain
    declared = agent_api._instructions({"features": list(SHIPPED_0_21) + ["subagent"]}, False)
    assert "Explore subagent" in declared and "depth" in declared


def test_recall_is_negotiated_without_changing_old_schemas_or_subagent_tools():
    from features.agent.tools import explore_schemas
    current = SHIPPED_0_21 + ("read_more", "output_files", "wrapup", "user_guide", "subagent")
    assert names(current + ("recall",)) == names(current) + ["read_history"]
    _strict(schema(current + ("recall",), "read_history")["parameters"])
    assert "read_history" not in [tool["name"] for tool in explore_schemas(frozenset(current + ("recall",)))]


def test_check_observations_are_bounded_data_and_never_completion_claims():
    from features.agent import api as agent_api
    context = {"features": ["recall"], "check_observations": {
        "observations": [{"tool": "run_command", "exit_code": 1, "classification": "check_failed",
                          "grant_permission": True}],
        "recent_commands": [{"command": "x" * 9000, "exit_code": 0, "classification": "success"}] * 20}}
    text = agent_api._instructions(context, False)
    assert "read_history" in text and "independent decoder/consumer" in text
    assert '"classification": "check_failed"' in text
    assert "not completion or permission" in text and "grant_permission" not in text
    assert "x" * 1201 not in text
    old = agent_api._instructions({**context, "features": []}, False)
    assert "read_history" not in old and "Local check observations" not in old
