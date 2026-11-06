"""Ảnh trong yêu cầu của Peto Agent bản desktop, chuẩn bị theo từng dịch vụ AI (features/agent/gateway_images.py)."""

from __future__ import annotations

import base64
import io

from PIL import Image

from features.agent import gateway_images

MIMES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}


def data_url(fmt: str = "PNG", size: tuple[int, int] = (4, 4), mode: str = "RGB") -> str:
    buffer = io.BytesIO()
    Image.new(mode, size, "red").save(buffer, fmt)
    return f"data:{MIMES[fmt]};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def picture(url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(url.partition(",")[2])))


def image(url: str) -> dict:
    return {"type": "input_image", "detail": "auto", "image_url": url}


def user_images(*urls: str) -> dict:
    return {"role": "user", "content": [{"type": "input_text", "text": "Xem ảnh"}, *map(image, urls)]}


def urls_of(items: list[dict]) -> list[str]:
    return [part["image_url"] for item in items if item.get("role") == "user" and isinstance(item.get("content"), list)
            for part in item["content"] if part.get("type") == "input_image"]


def test_tool_result_images_move_to_a_user_message_after_the_results():
    shot = data_url()
    items = [
        {"role": "user", "content": "Chụp màn hình giúp mình"},
        {"type": "function_call", "call_id": "c1", "name": "screenshot", "arguments": "{}"},
        {"type": "function_call", "call_id": "c2", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1",
         "output": [{"type": "input_text", "text": "Đã chụp."}, image(shot)]},
        {"type": "function_call_output", "call_id": "c2", "output": [image(shot)]},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Xong."}]},
    ]
    lifted = gateway_images.lift_tool_images(items)
    assert lifted[3] == {"type": "function_call_output", "call_id": "c1", "output": "Đã chụp."}
    assert lifted[4] == {"type": "function_call_output", "call_id": "c2", "output": gateway_images.IMAGE_ONLY_OUTPUT}
    assert lifted[5] == {"role": "user", "content": [
        {"type": "input_text", "text": gateway_images.TOOL_IMAGES_NOTE},
        {"type": "input_text", "text": "[screenshot]"}, image(shot),
        {"type": "input_text", "text": "[read]"}, image(shot),
    ]}
    assert lifted[6] == items[5]
    assert isinstance(items[3]["output"], list)


def test_text_only_tool_results_are_left_as_they_were():
    items = [{"type": "function_call", "call_id": "c1", "name": "read", "arguments": "{}"},
             {"type": "function_call_output", "call_id": "c1", "output": "nội dung"},
             {"type": "function_call_output", "call_id": "c2", "output": [{"type": "input_text", "text": "a"},
                                                                          {"type": "input_text", "text": "b"}]}]
    lifted = gateway_images.lift_tool_images(items)
    assert lifted[:2] == items[:2]
    assert lifted[2]["output"] == "a\nb"
    assert len(lifted) == 3


def test_webp_and_gif_become_png_for_xai_while_png_and_jpeg_stay_as_sent():
    webp, gif, png, jpeg = data_url("WEBP"), data_url("GIF", mode="P"), data_url(), data_url("JPEG")
    prepared = gateway_images.prepare([user_images(webp, gif, png, jpeg)], "xai")
    converted = urls_of(prepared)
    assert [url.split(";")[0] for url in converted] == ["data:image/png"] * 3 + ["data:image/jpeg"]
    assert converted[2] is png and converted[3] is jpeg
    assert picture(converted[0]).size == (4, 4)
    assert urls_of(gateway_images.prepare([user_images(webp)], "openai")) == [webp]


def test_claude_gets_large_images_shrunk_only_past_twenty_images():
    big, small = data_url("JPEG", size=(2400, 1200)), data_url()
    few = gateway_images.prepare([user_images(big, *[small] * 19)], "anthropic")
    assert urls_of(few)[0] is big
    many = urls_of(gateway_images.prepare([user_images(big, *[small] * 20)], "anthropic"))
    assert many[0].startswith("data:image/jpeg;base64,")
    assert picture(many[0]).size == (2000, 1000)
    assert many[1:] == [small] * 20


def test_claude_counts_tool_result_images_toward_the_twenty():
    big = data_url("PNG", size=(2100, 300))
    calls = []
    for n in range(21):
        calls += [{"type": "function_call", "call_id": f"c{n}", "name": "screenshot", "arguments": "{}"},
                  {"type": "function_call_output", "call_id": f"c{n}", "output": [image(big)]}]
    shrunk = urls_of(gateway_images.prepare([{"role": "user", "content": "Chụp đi"}, *calls], "anthropic"))
    assert len(shrunk) == 21
    assert {picture(url).size for url in shrunk} == {(2000, 286)}


def test_an_image_pillow_cannot_read_is_sent_unchanged():
    broken = "data:image/webp;base64," + base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 broken").decode("ascii")
    assert urls_of(gateway_images.prepare([user_images(broken)], "xai")) == [broken]
