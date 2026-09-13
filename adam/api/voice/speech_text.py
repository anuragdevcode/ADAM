"""Prepare answer text for text-to-speech.

Answers are rendered as Markdown with inline citation markers.  Spoken output
should carry only the substantive sentences: citations stay visual (see
06-interface-text-and-voice.md §3), and Markdown syntax must never be read out
loud as "asterisk asterisk".
"""

import re

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1")
_TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", re.MULTILINE)
_HR_RE = re.compile(r"^\s*([-*_]\s*){3,}$", re.MULTILINE)
# Citation markers such as [1], [2, 3], [GO-2023-114], [Source: ...], [§4.2]
_CITATION_RE = re.compile(r"\[(?:\d+(?:\s*,\s*\d+)*|GO[-\s][^\]]*|Source:[^\]]*|§[^\]]*)\]", re.IGNORECASE)
_PAREN_SOURCE_RE = re.compile(r"\((?:Source|Ref|See)\s*:[^)]*\)", re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{2,}")


def clean_for_speech(text: str) -> str:
    """Strip Markdown, links and citation markers so TTS reads natural prose."""
    if not text:
        return ""
    out = _CODE_FENCE_RE.sub(" ", text)
    out = _INLINE_CODE_RE.sub(r"\1", out)
    out = _MD_LINK_RE.sub(r"\1", out)
    out = _URL_RE.sub("", out)
    out = _HEADING_RE.sub("", out)
    out = _BLOCKQUOTE_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    # Run the emphasis pass twice so nested ***bold italic*** unwraps fully.
    out = _EMPHASIS_RE.sub(r"\2", out)
    out = _EMPHASIS_RE.sub(r"\2", out)
    out = _CITATION_RE.sub("", out)
    out = _PAREN_SOURCE_RE.sub("", out)
    # Rules and table separators are matched last so lines that only held
    # citation markers plus dashes collapse entirely.
    out = _TABLE_RULE_RE.sub("", out)
    out = _HR_RE.sub("", out)
    out = out.replace("|", " ")
    out = _MULTI_SPACE_RE.sub(" ", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = _MULTI_NEWLINE_RE.sub("\n", out)
    # Tidy spaces left in front of punctuation by removed markers.
    out = re.sub(r"\s+([.,;:!?।])", r"\1", out)
    return out.strip()
