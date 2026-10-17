"""Kiểm kiểu tham số JSON trước khi công cụ hỏi quyền hoặc gây tác dụng phụ."""

import inspect
import types
import typing


def _matches(value, hint):
    if hint is typing.Any:
        return True
    origin = typing.get_origin(hint)
    if origin in (types.UnionType, typing.Union):
        return any(_matches(value, member) for member in typing.get_args(hint))
    if hint is type(None):
        return value is None
    if hint in (str, int, bool, list, dict):
        # bool là lớp con của int trong Python, nhưng JSON true không phải số dòng hay thời hạn.
        return type(value) is hint
    if origin in (list, dict):
        if type(value) is not origin:
            return False
        members = typing.get_args(hint)
        if origin is list:
            return not members or all(_matches(item, members[0]) for item in value)
        return not members or all(_matches(key, members[0]) and _matches(item, members[1])
                                  for key, item in value.items())
    return False


def _label(hint):
    origin = typing.get_origin(hint)
    if origin in (types.UnionType, typing.Union):
        return " hoặc ".join(_label(member) for member in typing.get_args(hint))
    return {str: "chuỗi", int: "số nguyên", bool: "đúng/sai", list: "danh sách", dict: "đối tượng",
            type(None): "null", typing.Any: "dữ liệu JSON"}.get(origin or hint, "kiểu đã khai báo")


def argument_error(handler, params):
    """Dùng khai báo của handler hiện tại, không tự chuyển chuỗi thành số hoặc cấp quyền chạy công cụ."""
    hints = typing.get_type_hints(handler)
    for name, value in params.items():
        hint = hints.get(name, inspect.Signature.empty)
        # Công cụ động không có annotation vẫn dùng kiểm tra riêng của nó.
        if hint is not inspect.Signature.empty and not _matches(value, hint):
            return f"Tham số {name} cần {_label(hint)}. Gửi đúng kiểu JSON rồi gọi lại công cụ."
    return None
