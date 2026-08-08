"""jsdata.py — extract the personal-web content arrays out of `main.js`.

The site (Jerry6063/personal-web) is vanilla JS with no build step: all content
lives in three top-level array literals in `main.js` (`projectsData`,
`workData`, `labData`). There is no JSON export and no runtime we can import
from, so this module parses the JS *object-literal subset* those arrays use:
objects, arrays, single/double-quoted strings, numbers, true/false/null,
bare identifier keys, trailing commas, and `//` / `/* */` comments.

Deliberately NOT a JS engine — anything outside that subset raises, loudly, so
a future edit to main.js that breaks the assumption fails the ingest instead of
silently producing an empty corpus.
"""

from __future__ import annotations

import re
from typing import Any

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
    "v": "\v", "0": "\0", "'": "'", '"': '"', "\\": "\\", "/": "/", "`": "`",
}


class JSParseError(ValueError):
    pass


class _Parser:
    def __init__(self, src: str, pos: int = 0) -> None:
        self.src = src
        self.i = pos

    # --- helpers -------------------------------------------------------
    def _fail(self, msg: str) -> None:
        line = self.src.count("\n", 0, self.i) + 1
        raise JSParseError(f"{msg} at line {line} (offset {self.i})")

    def _peek(self) -> str:
        return self.src[self.i] if self.i < len(self.src) else ""

    def _ws(self) -> None:
        s, n = self.src, len(self.src)
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("//", self.i):
                nl = s.find("\n", self.i)
                self.i = n if nl == -1 else nl + 1
            elif s.startswith("/*", self.i):
                end = s.find("*/", self.i + 2)
                if end == -1:
                    self._fail("unterminated block comment")
                self.i = end + 2
            else:
                return

    # --- values --------------------------------------------------------
    def parse_value(self) -> Any:
        self._ws()
        c = self._peek()
        if c == "{":
            return self._object()
        if c == "[":
            return self._array()
        if c in "'\"":
            return self._string()
        if c == "`":
            self._fail("template literals are not supported")
        if c == "-" or c.isdigit():
            m = _NUMBER.match(self.src, self.i)
            if not m:
                self._fail("bad number")
            self.i = m.end()
            text = m.group()
            return float(text) if ("." in text or "e" in text or "E" in text) else int(text)
        m = _IDENT.match(self.src, self.i)
        if m:
            word = m.group()
            if word in ("true", "false", "null", "undefined"):
                self.i = m.end()
                return {"true": True, "false": False}.get(word)
            self._fail(f"unexpected identifier {word!r} (expressions are not supported)")
        self._fail(f"unexpected character {c!r}")

    def _string(self) -> str:
        quote = self.src[self.i]
        self.i += 1
        out: list[str] = []
        s, n = self.src, len(self.src)
        while self.i < n:
            c = s[self.i]
            if c == "\\":
                self.i += 1
                e = s[self.i]
                if e == "u":
                    if s[self.i + 1] == "{":
                        end = s.index("}", self.i)
                        out.append(chr(int(s[self.i + 2:end], 16)))
                        self.i = end + 1
                    else:
                        out.append(chr(int(s[self.i + 1:self.i + 5], 16)))
                        self.i += 5
                elif e == "x":
                    out.append(chr(int(s[self.i + 1:self.i + 3], 16)))
                    self.i += 3
                elif e == "\n":  # line continuation
                    self.i += 1
                else:
                    out.append(_ESCAPES.get(e, e))
                    self.i += 1
            elif c == quote:
                self.i += 1
                return "".join(out)
            else:
                out.append(c)
                self.i += 1
        self._fail("unterminated string")

    def _array(self) -> list:
        self.i += 1  # [
        items: list = []
        while True:
            self._ws()
            if self._peek() == "]":
                self.i += 1
                return items
            items.append(self.parse_value())
            self._ws()
            if self._peek() == ",":
                self.i += 1
            elif self._peek() == "]":
                self.i += 1
                return items
            else:
                self._fail("expected ',' or ']'")

    def _object(self) -> dict:
        self.i += 1  # {
        obj: dict = {}
        while True:
            self._ws()
            c = self._peek()
            if c == "}":
                self.i += 1
                return obj
            if c in "'\"":
                key = self._string()
            else:
                m = _IDENT.match(self.src, self.i)
                if not m:
                    self._fail("expected object key")
                key = m.group()
                self.i = m.end()
            self._ws()
            if self._peek() != ":":
                self._fail(f"expected ':' after key {key!r}")
            self.i += 1
            obj[key] = self.parse_value()
            self._ws()
            if self._peek() == ",":
                self.i += 1
            elif self._peek() == "}":
                self.i += 1
                return obj
            else:
                self._fail(f"expected ',' or '}}' after key {key!r}")


def extract_array(source: str, name: str) -> list:
    """Return the JS array literal assigned to `const <name> = [...]`."""
    m = re.search(rf"(?:const|let|var)\s+{re.escape(name)}\s*=\s*\[", source)
    if not m:
        raise JSParseError(f"could not find `{name}` array in main.js")
    value = _Parser(source, m.end() - 1).parse_value()
    if not isinstance(value, list):
        raise JSParseError(f"`{name}` is not an array")
    return value


def load_site_data(main_js_path: str) -> dict[str, list]:
    with open(main_js_path, encoding="utf-8") as fh:
        src = fh.read()
    return {
        "projects": extract_array(src, "projectsData"),
        "work": extract_array(src, "workData"),
        "lab": extract_array(src, "labData"),
    }
