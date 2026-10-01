"""Sơ đồ Mermaid trong Trò chuyện: Peto tự viết khối ```mermaid thay vì đẩy sang tab Tạo ảnh, và chỉ nhận hướng dẫn chi
tiết khi tin nhắn nói tới sơ đồ."""
import pytest

import main
from ai.mock import DIAGRAM_SAMPLE
from conftest import TEST_OWNER, read_events
from persona import COMPANION_SYSTEM_PROMPT, DIAGRAM_PROMPT, SYSTEM_PROMPT, build_diagram_guide


@pytest.mark.parametrize("question", [
    "Vẽ sơ đồ lớp cho hệ thống thư viện",
    "vẽ sequence diagram lúc đăng nhập",
    "activity diagram quy trình mượn sách",
    "vẽ lưu đồ thuật toán tìm số lớn nhất",
    "ERD cho ba bảng users, orders, products",
    "sơ đồ use case cho hệ thống bán hàng",
    "mở bằng draw.io được không",
])
def test_diagram_questions_get_the_mermaid_guide(question):
    assert build_diagram_guide(question).strip() == DIAGRAM_PROMPT


@pytest.mark.parametrize("question", [
    "Vẽ giúp con mèo đang uống trà",
    "giải thích asyncio cho mình",
    "mình đúng là một nerd chính hiệu",
    "tóm tắt chương 3 giúp mình",
])
def test_other_questions_do_not_pay_for_the_guide(question):
    assert build_diagram_guide(question) == ""


def test_prompts_send_diagrams_to_mermaid_not_to_the_image_tab():
    assert "```mermaid" in SYSTEM_PROMPT
    assert "Không bảo người dùng\n  sang tab Tạo ảnh để vẽ sơ đồ" in SYSTEM_PROMPT
    # Lỗi đã gặp khi thử thật: <<choice>> khai báo sau lần dùng đầu thì nút rẽ nhánh thành hình chữ nhật.
    assert "ở ĐẦU sơ đồ, trước dòng đầu tiên dùng tới chúng" in DIAGRAM_PROMPT
    # Làn thật bằng swimlane-beta; nút ngoài mọi làn sinh ra một làn trống không tên (cũng đã thử thật).
    assert "dùng swimlane-beta" in DIAGRAM_PROMPT
    assert "Mọi nút khai báo bên trong làn của nó" in DIAGRAM_PROMPT
    assert "mermaid" not in COMPANION_SYSTEM_PROMPT.lower()


async def test_guide_is_added_only_to_assistant_chat_turns(client):
    question = "vẽ sơ đồ lớp cho thư viện"
    chat = await main._build_system_prompt(TEST_OWNER, "chat", agent_question=question)
    assert DIAGRAM_PROMPT in chat
    assert DIAGRAM_PROMPT not in await main._build_system_prompt(TEST_OWNER, "chat", agent_question="chào bạn")
    assert DIAGRAM_PROMPT not in await main._build_system_prompt(TEST_OWNER, "companion", agent_question=question)
    assert DIAGRAM_PROMPT not in await main._build_system_prompt(TEST_OWNER, "chat", persona="roleplay", agent_question=question)


async def test_mock_diagram_reply_streams_four_mermaid_blocks(client):
    response = await client.post("/api/chat", json={"message": "__sodo__"})
    events = await read_events(response)
    text = "".join(event.get("text", "") for event in events if event["type"] == "delta")
    assert events[-1]["type"] == "done"
    assert text == DIAGRAM_SAMPLE
    assert text.count("```mermaid") == 4
    assert "swimlane-beta" in text
    assert "state KiemTra <<choice>>" in text.split("stateDiagram-v2", 1)[1].splitlines()[1]
