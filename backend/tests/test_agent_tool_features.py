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
    assert "find_files" in both and "replace_all" in both and "đường/dẫn.py:42" in both
    english = agent_api._instructions({"features": ["explore_v2", "edit_v2"]}, False, model="luna")
    assert "find_files" in english and "replace_all" in english and "approximate match" in english


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
