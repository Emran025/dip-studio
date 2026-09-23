"""Infrastructure module for reading, parsing, and rendering user documentation Markdown files.

Supports frontmatter metadata, automatic Arabic/RTL language detection, Cairo typography,
alert callouts, and relative image URI resolution against the documentation root directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocMetadata:
    title: str
    order: int = 100
    category: str = "General"
    direction: str = "ltr"  # "rtl" | "ltr"
    lang: str = "en"  # "ar" | "en"
    icon: str = "document"
    summary: str = ""


@dataclass(frozen=True, slots=True)
class DocPage:
    file_path: Path
    metadata: DocMetadata
    markdown_text: str
    html_content: str
    is_rtl: bool


class DocParser:
    """Parses Markdown documentation files into structured, theme-renderable DocPages."""

    ARABIC_REGEX = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")

    @classmethod
    def parse_directory(cls, docs_dir: Path) -> tuple[DocPage, ...]:
        """Scan *docs_dir* for .md files and return sorted tuple of DocPage instances."""
        if not docs_dir.exists() or not docs_dir.is_dir():
            return ()

        pages: list[DocPage] = []
        for file_path in sorted(docs_dir.glob("*.md")):
            try:
                page = cls.parse_file(file_path, docs_dir)
                pages.append(page)
            except Exception:
                continue

        pages.sort(key=lambda p: (p.metadata.category, p.metadata.order, p.metadata.title))
        return tuple(pages)

    @classmethod
    def parse_file(cls, file_path: Path, root_dir: Path | None = None) -> DocPage:
        text = file_path.read_text(encoding="utf-8")
        base_dir = root_dir or file_path.parent

        metadata, body_text = cls._extract_metadata_and_body(text, file_path.stem)
        is_rtl = (
            metadata.direction == "rtl"
            or metadata.lang == "ar"
            or bool(cls.ARABIC_REGEX.search(body_text[:500]))
        )

        # Update metadata direction/lang if detected Arabic
        if is_rtl and metadata.direction != "rtl":
            metadata = DocMetadata(
                title=metadata.title,
                order=metadata.order,
                category=metadata.category,
                direction="rtl",
                lang="ar",
                icon=metadata.icon,
                summary=metadata.summary,
            )

        html_body = cls._markdown_to_html(body_text, base_dir)
        full_html = cls._wrap_theme_html(html_body, is_rtl, metadata.title)

        return DocPage(
            file_path=file_path,
            metadata=metadata,
            markdown_text=body_text,
            html_content=full_html,
            is_rtl=is_rtl,
        )

    @classmethod
    def _extract_metadata_and_body(cls, text: str, default_title: str) -> tuple[DocMetadata, str]:
        """Extract YAML-like frontmatter metadata (if present) or `# Title` header."""
        title = default_title.replace("-", " ").replace("_", " ").title()
        order = 100
        category = "General"
        direction = "ltr"
        lang = "en"
        icon = "document"
        summary = ""

        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                yaml_block = parts[1]
                body = parts[2].strip()
                for line in yaml_block.strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip().strip("\"'")
                        if k == "title":
                            title = v
                        elif k == "order":
                            try:
                                order = int(v)
                            except ValueError:
                                pass
                        elif k == "category":
                            category = v
                        elif k == "direction":
                            direction = v
                        elif k == "lang":
                            lang = v
                        elif k == "icon":
                            icon = v
                        elif k == "summary":
                            summary = v

        if title == default_title.replace("-", " ").replace("_", " ").title():
            # Check first H1 header in markdown body
            h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1).strip()

        meta = DocMetadata(
            title=title,
            order=order,
            category=category,
            direction=direction,
            lang=lang,
            icon=icon,
            summary=summary,
        )
        return meta, body

    @classmethod
    def _markdown_to_html(cls, md: str, base_dir: Path) -> str:
        """Convert Markdown syntax to styled HTML, resolving relative image URIs."""
        html = md

        # 1. Resolve relative images: ![alt](images/path.png) or <img src="images/path.png">
        def replace_img_md(match: re.Match) -> str:
            alt = match.group(1)
            src = match.group(2)
            abs_src = cls._resolve_image_uri(src, base_dir)
            return f'<img src="{abs_src}" alt="{alt}" style="max-width:100%; height:auto; border-radius:6px; margin:10px 0;" />'  # noqa: E501

        html = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_img_md, html)

        def replace_img_html(match: re.Match) -> str:
            src = match.group(1)
            abs_src = cls._resolve_image_uri(src, base_dir)
            return f'src="{abs_src}"'

        html = re.sub(r'src=["\'](?!http|file:)([^"\']+)["\']', replace_img_html, html)

        # 2. Blockquote Alerts: > [!NOTE] or > [!TIP] or > [!WARNING]
        def replace_alerts(match: re.Match) -> str:
            kind = match.group(1).upper()
            content = match.group(2).strip()
            bg_color = "#1e293b" if "NOTE" in kind else "#064e3b" if "TIP" in kind else "#7f1d1d"
            border_color = (
                "#3b82f6" if "NOTE" in kind else "#10b981" if "TIP" in kind else "#ef4444"
            )
            title = "ملاحظة" if "NOTE" in kind else "تلميح" if "TIP" in kind else "تحذير"
            return f'<div style="background-color:{bg_color}; border-left:4px solid {border_color}; padding:10px 14px; margin:12px 0; border-radius:4px;"><strong style="color:{border_color};">{title}:</strong> {content}</div>'  # noqa: E501

        html = re.sub(
            r"^>\s*\[!(NOTE|TIP|WARNING|IMPORTANT)\]\s*(.*)$",
            replace_alerts,
            html,
            flags=re.MULTILINE,
        )

        # 3. Headings
        html = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^#### (.*?)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)

        # Markdown thematic breaks must remain visual separators, not paragraph text.
        html = re.sub(
            r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$",
            '<hr class="doc-separator" />',
            html,
        )

        # 4. Bold / Italic / Code inline
        html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html)
        html = re.sub(
            r"`([^`]+)`",
            r"<code style='background-color:#2a2d32; padding:2px 6px; border-radius:4px;'>\1</code>",  # noqa: E501
            html,
        )

        # 5. Lists (unordered)
        lines = html.splitlines()
        in_list = False
        res_lines = []
        for line in lines:
            if line.strip().startswith("- "):
                item = line.strip()[2:]
                if not in_list:
                    res_lines.append("<ul>")
                    in_list = True
                res_lines.append(f"  <li>{item}</li>")
            else:
                if in_list:
                    res_lines.append("</ul>")
                    in_list = False
                res_lines.append(line)
        if in_list:
            res_lines.append("</ul>")
        html = "\n".join(res_lines)

        # 6. Paragraph breaks
        html = re.sub(r"\n\n+", "</p><p>", html)
        html = f"<p>{html}</p>"
        html = re.sub(r"<p>\s*(<(?:h[1-4]|hr|ul|div)\b)", r"\1", html)
        html = re.sub(r"(</(?:h[1-4]|hr|ul|div)>)\s*</p>", r"\1", html)
        return html

    @classmethod
    def _resolve_image_uri(cls, rel_src: str, base_dir: Path) -> str:
        """Resolve a relative image path into a valid file:/// URI."""
        img_path = base_dir / rel_src
        if img_path.exists():
            return img_path.as_uri()
        # Fallback check inside subfolder images/
        sub_img = base_dir / "images" / Path(rel_src).name
        if sub_img.exists():
            return sub_img.as_uri()
        return img_path.as_uri()

    @classmethod
    def _wrap_theme_html(cls, body_html: str, is_rtl: bool, title: str) -> str:
        """Wrap HTML body in a complete document with theme styling & Cairo typography for Arabic."""  # noqa: E501
        direction = "rtl" if is_rtl else "ltr"
        align = "right" if is_rtl else "left"
        font_family = (
            "'Cairo', 'Segoe UI', 'Microsoft YaHei', sans-serif"
            if is_rtl
            else "'Segoe UI', Roboto, sans-serif"
        )

        return f"""<!DOCTYPE html>
<html dir="{direction}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{
    font-family: {font_family};
    font-size: 14px;
    line-height: 1.6;
    color: #e2e8f0;
    background-color: #0f172a;
    direction: {direction};
    text-align: {align};
    padding: 16px 24px;
  }}
  h1 {{ color: #38bdf8; font-size: 22px; margin-bottom: 16px;
    border-bottom: 1px solid #334155; padding-bottom: 8px; }}
  h2 {{ color: #7dd3fc; font-size: 18px; margin-top: 20px; margin-bottom: 12px; }}
  h3 {{ color: #93c5fd; font-size: 15px; margin-top: 16px; margin-bottom: 8px; }}
  p {{ margin-bottom: 12px; }}
  p, h1, h2, h3, h4, li, blockquote {{ direction: {direction}; text-align: {align}; }}
  ul {{ direction: {direction}; margin-{align}: 20px; margin-bottom: 12px; }}
  li {{ margin-bottom: 4px; }}
  strong {{ color: #f8fafc; font-weight: bold; }}
  code {{ font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; }}
  a {{ color: #38bdf8; text-decoration: none; }}
  hr.doc-separator {{ border: 0; border-top: 1px solid #475569; margin: 22px 0; }}
  blockquote {{ border-{align}: 3px solid #38bdf8; margin: 14px 0;
    padding: 8px 14px; color: #cbd5e1; }}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""
