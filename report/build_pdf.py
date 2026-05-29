from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "report.md"
PDF_PATH = ROOT / "report.pdf"
FONT = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
BOLD_FONT = FontProperties(fname=r"C:\Windows\Fonts\msyhbd.ttc")


def display_width(text: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def wrap_text(text: str, max_width: int = 86) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for ch in text:
        if display_width(current + ch) > max_width:
            lines.append(current.rstrip())
            current = ch
        else:
            current += ch
    if current:
        lines.append(current.rstrip())
    return lines


class PdfWriter:
    def __init__(self, pdf: PdfPages):
        self.pdf = pdf
        self.fig = None
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        if self.fig is not None:
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
        self.fig = plt.figure(figsize=(8.27, 11.69), dpi=120)
        self.fig.patch.set_facecolor("white")
        self.y = 0.94

    def ensure_space(self, amount: float) -> None:
        if self.y - amount < 0.07:
            self.new_page()

    def text(self, text: str, size: int = 10, bold: bool = False, gap: float = 0.012, max_width: int = 86) -> None:
        font = BOLD_FONT if bold else FONT
        wrapped = wrap_text(text, max_width=max_width)
        line_height = size / 720 + 0.006
        self.ensure_space(line_height * len(wrapped) + gap)
        for line in wrapped:
            self.fig.text(0.08, self.y, line, fontproperties=font, fontsize=size, va="top", color="#111827")
            self.y -= line_height
        self.y -= gap

    def heading(self, text: str, level: int) -> None:
        if level == 1:
            size, gap, width = 19, 0.025, 58
        elif level == 2:
            size, gap, width = 15, 0.018, 66
        else:
            size, gap, width = 12, 0.014, 76
        self.ensure_space(size / 360 + gap)
        self.text(text, size=size, bold=True, gap=gap, max_width=width)

    def bullet(self, text: str) -> None:
        self.text("• " + text, size=10, gap=0.006, max_width=82)

    def code_or_table(self, lines: list[str]) -> None:
        line_height = 0.018
        self.ensure_space(line_height * len(lines) + 0.02)
        for line in lines:
            self.fig.text(0.08, self.y, line, fontproperties=FONT, fontsize=7.5, va="top", color="#1f2937")
            self.y -= line_height
        self.y -= 0.012

    def image(self, alt: str, rel_path: str) -> None:
        path = (ROOT / rel_path).resolve()
        if not path.exists():
            self.text(f"[图片缺失] {rel_path}", size=9)
            return
        self.new_page()
        ax = self.fig.add_axes([0.08, 0.12, 0.84, 0.76])
        ax.imshow(mpimg.imread(path))
        ax.axis("off")
        self.fig.text(0.08, 0.92, alt, fontproperties=BOLD_FONT, fontsize=14, va="top")
        self.pdf.savefig(self.fig)
        plt.close(self.fig)
        self.fig = None
        self.new_page()

    def close(self) -> None:
        if self.fig is not None:
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
            self.fig = None


def strip_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = text.replace("**", "")
    return text


def build_pdf() -> None:
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    with PdfPages(PDF_PATH) as pdf:
        writer = PdfWriter(pdf)
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip()

            image_match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            if image_match:
                writer.image(image_match.group(1), image_match.group(2))
                i += 1
                continue

            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                writer.heading(strip_inline_markdown(line[level:].strip()), level)
                i += 1
                continue

            if line.startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].startswith("|"):
                    table_lines.append(strip_inline_markdown(lines[i]))
                    i += 1
                writer.code_or_table(table_lines)
                continue

            if line.startswith("- "):
                writer.bullet(strip_inline_markdown(line[2:].strip()))
                i += 1
                continue

            if line.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                writer.code_or_table(code_lines)
                i += 1
                continue

            if not line:
                writer.y -= 0.006
                i += 1
                continue

            writer.text(strip_inline_markdown(line), size=10)
            i += 1

        writer.close()


if __name__ == "__main__":
    build_pdf()
    print(PDF_PATH)

