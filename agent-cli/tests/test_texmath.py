"""Công thức LaTeX trong câu trả lời phải đọc được trong terminal, vì terminal không vẽ được LaTeX."""

from __future__ import annotations

import io

from peto_agent import texmath
from peto_agent.ui import UI

# Câu trả lời thật của Peto hôm 2026-09-21: terminal in nguyên \[, \begin{align*}, \lnot, & và \\.
REPLY = r"""Peto **sai**, và đúng là **thiếu phủ định** (dấu ¬ hoặc gạch ngang trên đầu).

Luật đúng là:

\[
A \to B \;\equiv\; \lnot A \lor B
\]

không phải \(A \lor B\).

\[
\begin{align*}
P \to (Q \to R)
&\equiv P \to (\lnot Q \lor R) \\
&\equiv \lnot P \lor (\lnot Q \lor R) \\
&\equiv \lnot P \lor \lnot Q \lor R
\end{align*}
\]

(tương đương luôn với \((P \land Q) \to R\))."""


def render(text: str) -> str:
    ui = UI(out=io.StringIO(), colors=False)
    writer = ui.reply()
    writer.feed(text)
    writer.finish()
    return ui.out.getvalue()


def test_the_reported_reply_reads_as_math_instead_of_latex_source():
    shown = render(REPLY)
    for source in ("\\[", "\\]", "\\begin", "\\lnot", "\\lor", "\\equiv", "&", "\\\\"):
        assert source not in shown, source
    assert "    A → B ≡ ¬A ∨ B" in shown
    assert "không phải A ∨ B." in shown
    assert "    ≡ ¬P ∨ ¬Q ∨ R" in shown
    assert "(tương đương luôn với (P ∧ Q) → R)." in shown
    assert shown.startswith("Peto › Peto **sai**"), "không màu thì Markdown giữ nguyên, chỉ công thức được đổi"


def test_delimiter_lines_print_nothing_and_the_label_waits_for_real_text():
    shown = render("\\[\nx^2 + y^2\n\\]\nxong")
    assert shown == "Peto ›     x² + y²\nxong\n"


def test_common_constructs():
    assert texmath.convert(r"\frac{a+1}{2}") == "(a+1)/2"
    assert texmath.convert(r"\frac{1}{2}") == "1/2"
    assert texmath.convert(r"x^{n+1} + a_1 + a_{10}") == "xⁿ⁺¹ + a₁ + a₁₀"
    assert texmath.convert(r"e^{i\pi}") == "e^(iπ)", "không có chữ số mũ Unicode thì ghi rõ bằng ^"
    assert texmath.convert(r"\sqrt{2} \cdot \sqrt{x+1}") == "√2 · √(x+1)"
    assert texmath.convert(r"\forall x \in \mathbb{R}, x^2 \geq 0") == "∀ x ∈ ℝ, x² ≥ 0"
    assert texmath.convert(r"\text{nếu } n > 0") == "nếu n > 0"
    assert texmath.convert(r"\left( a \right)") == "( a )"
    assert texmath.convert(r"\overline{A}") == "A\u0305"
    assert texmath.convert(r"\sin x + \log_2 n") == "sin x + log₂ n", "lệnh lạ chỉ bỏ dấu gạch chéo"
    assert texmath.convert(r"\{1, 2\}") == "{1, 2}"


def test_dollar_signs_that_are_not_math_are_left_alone():
    for text in ("giá $5 và $10", "biến $HOME và $PATH", "echo $x"):
        assert texmath.inline(text) == text
    assert texmath.inline("nghiệm là $x^2 = 4$ nhé") == "nghiệm là x² = 4 nhé"
    assert texmath.inline(r"dùng $\lnot p$") == "dùng ¬p"


def test_code_is_never_converted():
    assert texmath.inline(r"gõ `\(x\)` hoặc `$\lnot$`") == r"gõ `\(x\)` hoặc `$\lnot$`"
    shown = render("```latex\n\\[\n\\lnot A\n\\]\n```")
    assert "\\lnot A" in shown and "\\[" in shown


def test_an_unclosed_formula_does_not_leak_into_the_next_reply():
    ui = UI(out=io.StringIO(), colors=False)
    writer = ui.reply()
    writer.feed("\\[\n\\lnot A\n")
    writer.finish()
    assert ui.markdown(r"\lnot") == r"\lnot", "ngoài công thức, chữ \\lnot giữ nguyên"
