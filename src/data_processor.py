"""
Data processing and cleaning pipeline.

Converts the raw list[dict] from the API into two pandas DataFrames:
  - df_raw:     every field exactly as received
  - df_cleaned: text normalized, ready for analysis

Korean and mixed Korean-English text is preserved correctly throughout.
"""

import re
import unicodedata

import pandas as pd


# Regex patterns used during cleaning
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_WHITESPACE_RE = re.compile(r"\s+")
_MENTION_RE = re.compile(r"@\w+")  # YouTube @mentions


class DataProcessor:
    """Transform raw API comment dicts into clean DataFrames."""

    def process(
        self,
        raw_comments: list[dict],
        video_id: str,
        video_url: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Build df_raw and df_cleaned from the raw comment list.

        Parameters
        ----------
        raw_comments: Output of YouTubeClient.fetch_comments()
        video_id:     YouTube video ID (added as a column)
        video_url:    Original URL passed by the user

        Returns
        -------
        (df_raw, df_cleaned)
        """
        if not raw_comments:
            empty = pd.DataFrame(
                columns=[
                    "comment_id", "parent_comment_id", "author", "text",
                    "published_at", "updated_at", "like_count", "is_reply",
                    "reply_count", "video_id", "video_url",
                ]
            )
            return empty, empty.copy()

        df = pd.DataFrame(raw_comments)
        df["video_id"] = video_id
        df["video_url"] = video_url

        # Ensure consistent types
        df["like_count"] = pd.to_numeric(df["like_count"], errors="coerce").fillna(0).astype(int)
        df["reply_count"] = pd.to_numeric(df["reply_count"], errors="coerce").fillna(0).astype(int)
        df["is_reply"] = df["is_reply"].astype(bool)
        df["text"] = df["text"].fillna("").astype(str)
        df["author"] = df["author"].fillna("").astype(str)

        df_raw = df.copy()

        # --- Cleaning ---
        df_cleaned = df.copy()
        df_cleaned["text"] = df_cleaned["text"].apply(clean_text)

        # Drop rows where text is empty after cleaning
        df_cleaned = df_cleaned[df_cleaned["text"].str.strip() != ""].reset_index(drop=True)

        return df_raw, df_cleaned


# ------------------------------------------------------------------
# Text cleaning utilities (module-level so they can be imported/tested)
# ------------------------------------------------------------------

def clean_text(
    text: str,
    remove_urls: bool = True,
    remove_mentions: bool = False,
    normalize_unicode: bool = True,
) -> str:
    """
    Normalize a comment string.

    - Decodes HTML entities left in plainText responses (&amp; etc.)
    - Optionally strips URLs and @mentions
    - Normalizes unicode (NFC) for consistent Korean character handling
    - Collapses repeated whitespace
    - Strips leading/trailing whitespace

    Korean text is preserved as-is; no character stripping is applied
    to non-ASCII characters.
    """
    if not text:
        return ""

    # Basic HTML entity decoding (YouTube sometimes leaves these in plainText)
    text = (
        text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("<br>", " ")
            .replace("<br/>", " ")
    )

    if normalize_unicode:
        text = unicodedata.normalize("NFC", text)

    if remove_urls:
        text = _URL_RE.sub(" ", text)

    if remove_mentions:
        text = _MENTION_RE.sub(" ", text)

    # Collapse whitespace (preserves newlines as spaces)
    text = _WHITESPACE_RE.sub(" ", text)
    text = text.strip()

    return text


def extract_text_tokens(text: str) -> list[str]:
    """
    Tokenize a cleaned comment string into a list of lower-case tokens.

    Strategy:
    - Split on whitespace and common punctuation
    - Keep Korean characters (가-힣) intact as tokens
    - Keep English alphanumeric sequences
    - Discard tokens shorter than 2 characters (English) or 1 char (Korean)

    This avoids requiring any external tokenizer (e.g. KoNLPy).
    For production Korean NLP, replace this with a morpheme analyzer.
    """
    # Split on anything that isn't a word char or Korean character
    raw_tokens = re.split(r"[^\w가-힣]+", text.lower())
    tokens = []
    for tok in raw_tokens:
        if not tok:
            continue
        is_korean = bool(re.search(r"[가-힣]", tok))
        min_len = 1 if is_korean else 2
        if len(tok) >= min_len:
            tokens.append(tok)
    return tokens
