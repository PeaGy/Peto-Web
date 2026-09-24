"""Trang tràn ngang trên điện thoại (bốn chỗ gây tràn), sửa mà máy tính vẫn giữ nguyên bố cục."""

TITLE = "Trang landing tràn ngang trên điện thoại"
KIND = "giao diện"
PROJECT = "landing"
MAX_STEPS = 14
NEEDS = ("edge",)
PROMPT = """
Trang landing xem trên điện thoại bị tràn ngang, phải kéo qua kéo lại. Sửa cho vừa màn hình điện thoại giúp mình, còn
trên máy tính thì giữ nguyên như bây giờ.
"""
SOLUTION_REPLY = "Khung cố định 1100px, thanh menu không xuống dòng, bảng giá rộng tối thiểu 760px và dòng link dài không ngắt; đã sửa bằng max-width, flex-wrap, khung cuộn cho bảng và ngắt dòng link."

MEASURE = """(() => {
  const root = document.documentElement;
  const features = document.querySelector('.features');
  const container = document.querySelector('.container');
  return {
    overflow: root.scrollWidth - root.clientWidth,
    columns: features ? getComputedStyle(features).gridTemplateColumns.split(' ').filter(Boolean).length : 0,
    container: container ? Math.round(container.getBoundingClientRect().width) : 0,
    nav: Math.round(document.querySelector('nav').getBoundingClientRect().height),
  };
})()"""


def check(ctx):
    with ctx.serve() as base:
        with ctx.page(f"{base}/index.html", "mobile") as (page, _):
            phone = ctx.evaluate(page, MEASURE)
        with ctx.page(f"{base}/index.html", "desktop") as (page, _):
            desktop = ctx.evaluate(page, MEASURE)
    ctx.require("Điện thoại (390px) không tràn ngang", phone["overflow"] <= 0, f"tràn {phone['overflow']}px")
    ctx.require("Máy tính: khung vẫn rộng 1100px", 1090 <= desktop["container"] <= 1110, f"{desktop['container']}px")
    ctx.require("Máy tính: vẫn 3 cột tính năng", desktop["columns"] == 3, f"{desktop['columns']} cột")
    ctx.require("Máy tính: menu vẫn một hàng", desktop["nav"] < 80, f"cao {desktop['nav']}px")
    ctx.bonus("Điện thoại: tính năng xếp ít cột hơn", phone["columns"] < 3, f"{phone['columns']} cột")
