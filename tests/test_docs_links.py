"""Offline Markdown checks: root documents plus docs/, dataset/ and evals/."""

import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
# Existing official documentation only; adding a host requires deliberate review.
OFFICIAL_HOSTS = {
    "alembic.sqlalchemy.org", "developers.openai.com", "docs.python.org",
    "docs.sqlalchemy.org", "fastapi.tiangolo.com", "www.itl.nist.gov",
    "www.postgresql.org", "www.psycopg.org", "www.starlette.io",
    "www.energyaustralia.com.au", "www.agl.com.au",
}
# pdfplumber's official documentation is hosted in its GitHub repository.
GITHUB_PATHS = ("/maxtsec/bill-lens", "/jsvine/pdfplumber")
EXCLUDED_DIRS = {".venv", "tmp", "var", ".git"}


def markdown_files(root):
    files = list(root.glob("*.md"))
    for name in ("docs", "dataset", "evals"):
        for directory, dirs, names in os.walk(root / name):
            parent = Path(directory)
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS
                       and (parent / d).relative_to(root) != Path("evals/results")]
            files.extend(parent / n for n in names if n.endswith(".md"))
    return sorted(files)


def unfenced(text):
    """Ignore backtick/tilde fences, including longer closing fences."""
    lines, fence = [], None
    for line in text.splitlines():
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", line):
                fence = None
            lines.append("")
        else:
            opening = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
            if opening:
                fence = opening[1]
                lines.append("")
            else:
                lines.append(line)
    return "\n".join(lines)


def heading_anchors(text):
    used = set()
    lines = unfenced(text).splitlines()
    for index, line in enumerate(lines):
        heading = re.match(r" {0,3}#{1,6}[ \t]+(.+?)\s*$", line)
        if heading:
            title = re.sub(r"[ \t]+#+$", "", heading[1])
        elif index and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line) and lines[index - 1].strip():
            title = lines[index - 1].strip()  # Setext headings.
        else:
            continue
        # Keep inline code text, drop its backticks and other punctuation.
        base = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        anchor, suffix = base, 0
        while anchor in used:
            suffix += 1
            anchor = f"{base}-{suffix}"
        used.add(anchor)
    return used


def destinations(text):
    text = unfenced(text)
    text = re.sub(r"(`+)(.+?)\1", "", text, flags=re.S)  # Literal inline examples.
    targets = []
    # Read inline links/images, balancing parentheses in their destinations.
    for match in re.finditer(r"!?\[(?:\\.|[^\]\\])*\]\(\s*", text):
        start, depth = match.end(), 0
        if text[start:start + 1] == "<":
            end = text.find(">", start + 1)
            if end != -1:
                targets.append(text[start + 1:end])
            continue
        end = start
        while end < len(text):
            char = text[end]
            if char == "\\" and end + 1 < len(text):
                end += 2
                continue
            if depth == 0 and (char == ")" or char.isspace()):
                break
            depth += (char == "(") - (char == ")")
            end += 1
        targets.append(text[start:end])
    # Reference-style links (including unused definitions) and URI autolinks.
    targets.extend(m[1] or m[2] for m in re.finditer(
        r"(?m)^ {0,3}\[[^\]\n]+\]:[ \t]*(?:<([^>\n]+)>|(\S+))", text))
    targets.extend(re.findall(r"<((?:https?://|mailto:)[^>\s]+)>", text))
    return [re.sub(r"\\([\\() ])", r"\1", target) for target in targets]


def link_errors(source, root):
    errors = []
    for target in destinations(source.read_text(encoding="utf-8")):
        url = urlsplit(target)
        if url.scheme or url.netloc:
            allowed = url.scheme == "https" and (
                url.netloc in OFFICIAL_HOSTS or
                (url.netloc == "github.com" and any(
                    url.path == p or url.path.startswith(p + "/") for p in GITHUB_PATHS))
            )
            if not allowed:
                errors.append(f"{source}: unapproved external link: {target}")
            continue  # Never fetch external links, even allowed ones.
        path = ((root / unquote(url.path).lstrip("/")) if url.path.startswith("/")
                else (source.parent / unquote(url.path))).resolve()
        if not url.path:
            path = source.resolve()
        if not path.is_relative_to(root.resolve()) or not path.exists():
            errors.append(f"{source}: missing/outside target: {target}")
        elif path.suffix == ".md" and url.fragment:
            if unquote(url.fragment) not in heading_anchors(path.read_text(encoding="utf-8")):
                errors.append(f"{source}: missing anchor: {target}")
    return errors


def test_repository_documentation_links():
    files = markdown_files(ROOT)
    assert files, "No documentation discovered"
    errors = [error for source in files for error in link_errors(source, ROOT)]
    assert not errors, "\n".join(errors)


def test_missing_file_and_anchor_are_both_reported(tmp_path):
    source = tmp_path / "README.md"
    source.write_text("# Present\n[File](missing.md)\n[Heading](#absent)\n", encoding="utf-8")
    errors = link_errors(source, tmp_path)
    assert len(errors) == 2
    assert any("missing/outside target: missing.md" in e for e in errors)
    assert any("missing anchor: #absent" in e for e in errors)


def test_github_slugs_duplicates_inline_code_and_fences(tmp_path):
    source = tmp_path / "README.md"
    source.write_text('''# Use `API_name` - now!
# Use `API_name` - now!
```md
# Use `API_name` - now!
[Not a link](missing.md)
````
~~~
# Hidden
~~~
# Use `API_name` - now!
Setext title
============
[One](#use-api_name---now)
[Two](#use-api_name---now-1)
[Three](#use-api_name---now-2)
[Setext](#setext-title)
''', encoding="utf-8")
    assert heading_anchors(source.read_text(encoding="utf-8")) == {
        "use-api_name---now", "use-api_name---now-1", "use-api_name---now-2", "setext-title"}
    assert link_errors(source, tmp_path) == []


def test_reference_image_encoded_and_parenthesised_paths(tmp_path):
    (tmp_path / "a (b).md").write_text("# Heading\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text('''[Inline](a%20(b).md#heading)
[Angle](<a (b).md#heading>)
![Image](a%20%28b%29.md)
[Reference][ref]
[ref]: <a (b).md#heading> "Title"
`[Literal](missing.md)`
''', encoding="utf-8")
    assert len(destinations(source.read_text(encoding="utf-8"))) == 4
    assert link_errors(source, tmp_path) == []


def test_external_allowlist_is_scoped_and_offline(tmp_path):
    source = tmp_path / "README.md"
    source.write_text('''[Official](https://docs.python.org/3/)
[Project](https://github.com/maxtsec/bill-lens/pull/16)
[Parser docs](https://github.com/jsvine/pdfplumber#python-library)
<https://unapproved.example/test>
[Different repo](https://github.com/maxtsec/other)
[Lookalike](https://docs.python.org.example/)
''', encoding="utf-8")
    errors = link_errors(source, tmp_path)
    assert len(errors) == 3
    assert all("unapproved external link" in e for e in errors)


def test_discovery_scope_and_exclusions(tmp_path):
    included = ["README.md", "docs/nested/guide.md", "dataset/bill/notes.md", "evals/README.md"]
    excluded = [".venv/lib/a.md", "tmp/a.md", "var/a.md", "evals/results/run/a.md",
                "docs/tmp/a.md", "docs/.venv/a.md", "dataset/var/a.md", "tests/fixture.md"]
    for name in included + excluded:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Example\n", encoding="utf-8")
    assert {p.relative_to(tmp_path).as_posix() for p in markdown_files(tmp_path)} == set(included)
