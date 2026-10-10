# -*- coding: utf-8 -*-
"""Fuzzy text matching for Quick Find, the Command Palette and every filter box.

    textmatch.score('sec pl', 'Section Plane')          # > 0: a match
    textmatch.rank('wall', names, limit=20)              # [(score, name)] best first
    textmatch.spans('secpl', 'Section Plane')            # [(0, 3), (8, 10)] to highlight
    index = textmatch.Index(commands, key=lambda c: c['title'])
    index.rank('clash')                                  # same, texts lowercased once

A query word matches when its characters appear in order (a subsequence), ignoring case.
Several words (split on spaces) must ALL match, anywhere and in any order; their scores
add up. The score rewards what a person means: matches at word starts (after a space or
- _ . / \\ > and similar), CamelCase humps and digit runs, the start of the text, runs of
consecutive characters, and an exact match; gaps cost a little and a longer text loses
a tiny amount so 'Wall' outranks 'Walls and floors' for 'wall'. Scoring is fzf's v1
scheme (match 16, boundary bonus up to 10, first character counted double, consecutive
bonus, gap penalty), on three candidate alignments: the best contiguous occurrence, a
compact subsequence, and a word-start (acronym) alignment; the best wins.

Speed: the inner loops are str.find calls, so a non-matching text costs one or two native
searches, and a plain contiguous match is scored in closed form. 20,000 texts with a
short query rank in under 200 ms on IronPython 3.4 (70 to 150 ms measured; see
dev/tests/test_textmatch.py, which measures it on both engines).

Pure stdlib.
"""

_WHITE = ' \t\r\n' + chr(0x00A0)
_DELIM = '-_./\\:>|,;()[]{}<+*#@&=~"\''

SCORE_MATCH = 16
GAP_START = -3
GAP_EXTENSION = -1
GAP_CAP = -10            # one gap never costs more than this, so every match scores > 0
BONUS_WHITE = 10         # after a space or at the very start
BONUS_DELIMITER = 9      # after - _ . / \ > and similar
BONUS_NONWORD = 8        # after any other non-alphanumeric character
BONUS_CAMEL = 7          # lower->Upper hump, or the first digit of a number
BONUS_CONSECUTIVE = 4
FIRST_CHAR_MULTIPLIER = 2
BONUS_PREFIX = 12        # the word matches the start of the text
BONUS_EXACT = 12         # the word is the whole text
LENGTH_PENALTY = 0.01    # per character of text, capped at 1.0

# Closed-form scoring of plain contiguous runs (exact; a test switches it off to compare).
_FAST = True


def _bonus(orig, p):
    if p == 0:
        return BONUS_WHITE
    prev = orig[p - 1]
    if prev in _WHITE:
        return BONUS_WHITE
    if prev in _DELIM:
        return BONUS_DELIMITER
    if prev.isalnum():
        cur = orig[p]
        if cur.isupper() and prev.islower():
            return BONUS_CAMEL
        if cur.isdigit() and not prev.isdigit():
            return BONUS_CAMEL
        return 0
    return BONUS_NONWORD


def _score_positions(orig, positions):
    total = 0
    prev = -2
    first_bonus = 0
    k = 0
    for p in positions:
        bonus = _bonus(orig, p)
        if p == prev + 1:
            if bonus >= BONUS_DELIMITER and bonus > first_bonus:
                first_bonus = bonus
            bonus = max(bonus, first_bonus, BONUS_CONSECUTIVE)
        else:
            if k:
                gap = GAP_START + GAP_EXTENSION * (p - prev - 2)
                total += gap if gap > GAP_CAP else GAP_CAP
            first_bonus = bonus
        total += SCORE_MATCH + (bonus * FIRST_CHAR_MULTIPLIER if k == 0 else bonus)
        prev = p
        k += 1
    return total


def _word_starts(word, low, orig):
    """Each character either right after the previous one or at a word start; None when
    that is impossible (looks at most 8 occurrences per character)."""
    positions = []
    p = -1
    size = len(low)
    for ch in word:
        if p >= 0 and p + 1 < size and low[p + 1] == ch:
            p += 1
            positions.append(p)
            continue
        q = low.find(ch, p + 1)
        tries = 0
        while q >= 0 and _bonus(orig, q) < BONUS_CAMEL:
            tries += 1
            if tries > 8:
                return None
            q = low.find(ch, q + 1)
        if q < 0:
            return None
        positions.append(q)
        p = q
    return positions


def _match_word(word, low, orig):
    """(score, positions) for one lowercased query word, or (0, None)."""
    n = len(word)
    best_score = 0
    best = None
    i = low.find(word)
    if i >= 0:
        start, start_bonus = i, _bonus(orig, i)
        tries = 0
        j = i
        while start_bonus < BONUS_WHITE and tries < 4:
            j = low.find(word, j + 1)
            if j < 0:
                break
            b = _bonus(orig, j)
            if b > start_bonus:
                start, start_bonus = j, b
            tries += 1
        best = None             # the run start..start+n, listed only when someone needs it
        segment = orig[start:start + n]
        if _FAST and (n == 1 or segment.isdigit() or
                      (segment.isalpha() and (segment[1:].islower() or segment.isupper()))):
            # No inner character earns a bonus of its own (no hump, delimiter or digit
            # start), so _score_positions reduces to this closed form. Same number, a
            # fraction of the IronPython calls; test_fast_path_scores_equal_the_general_path.
            inner = start_bonus if start_bonus > BONUS_CONSECUTIVE else BONUS_CONSECUTIVE
            best_score = (SCORE_MATCH * n + start_bonus * FIRST_CHAR_MULTIPLIER
                          + inner * (n - 1))
        else:
            best = list(range(start, start + n))
            best_score = _score_positions(orig, best)
        if start == 0:
            best_score += BONUS_PREFIX
            if n == len(low):
                best_score += BONUS_EXACT
        if start_bonus >= BONUS_DELIMITER or n == 1:
            return best_score, (best if best is not None else range(start, start + n))
    else:
        p = -1
        for ch in word:
            p = low.find(ch, p + 1)
            if p < 0:
                return 0, None
        # p is where the first full match ends; walk back to the tightest start (fzf v1).
        q = p + 1
        back = []
        for ch in reversed(word):
            q = low.rfind(ch, 0, q)
            back.append(q)
        back.reverse()
        best = back
        best_score = _score_positions(orig, best)
    starts = _word_starts(word, low, orig)
    if starts is not None:
        score = _score_positions(orig, starts)
        if starts[0] == 0 and starts == list(range(n)):
            score += BONUS_PREFIX
        if score > best_score:
            return score, starts
    return best_score, (best if best is not None else range(start, start + n))


def _words(query):
    return (query or '').lower().split()


def _score_text(words, text, low):
    orig = text if len(text) == len(low) else low
    total = 0
    for word in words:
        score, _positions = _match_word(word, low, orig)
        if not score:
            return 0.0
        total += score
    penalty = LENGTH_PENALTY * len(text)
    return float(total) - (penalty if penalty < 1.0 else 1.0)


def score(query, text):
    """0.0 when text does not match query, else a positive score (higher is better).
    An empty query scores 0.0."""
    words = _words(query)
    if not words or text is None:
        return 0.0
    text = str(text)
    return _score_text(words, text, text.lower())


def spans(query, text):
    """[(start, end)] character ranges of text that the query matched, sorted and merged,
    for highlighting; [] when it does not match."""
    words = _words(query)
    if not words or text is None:
        return []
    text = str(text)
    low = text.lower()
    orig = text if len(text) == len(low) else low
    hit = []
    for word in words:
        score_, positions = _match_word(word, low, orig)
        if not score_:
            return []
        hit.extend(positions)
    out = []
    for p in sorted(set(hit)):
        if out and out[-1][1] == p:
            out[-1] = (out[-1][0], p + 1)
        else:
            out.append((p, p + 1))
    return out


def _rank(words, items, texts, lows, limit):
    scored = []
    for index in range(len(items)):
        text = texts[index]
        if text is None:
            continue
        s = _score_text(words, text, lows[index])
        if s > 0:
            scored.append((-s, index))
    scored.sort()
    if limit:
        scored = scored[:limit]
    return [(-neg, items[index]) for neg, index in scored]


def _text_of(item, key):
    value = key(item) if key is not None else item
    return None if value is None else str(value)


def rank(query, items, key=None, limit=50):
    """[(score, item)] for the items whose text matches, best first; equal scores keep the
    input order. key(item) gives the text (default: the item itself). limit None or 0
    returns every match. An empty query returns the first `limit` items, score 0.0."""
    items = list(items)
    words = _words(query)
    if not words:
        chosen = items[:limit] if limit else items
        return [(0.0, item) for item in chosen]
    texts = [_text_of(item, key) for item in items]
    lows = [t.lower() if t is not None else None for t in texts]
    return _rank(words, items, texts, lows, limit)


class Index(object):
    """Items with their texts lowercased once, for ranking many queries against the same
    list (a palette re-ranking on every keystroke)."""

    def __init__(self, items, key=None):
        self.items = list(items)
        self.texts = [_text_of(item, key) for item in self.items]
        self.lows = [t.lower() if t is not None else None for t in self.texts]

    def __len__(self):
        return len(self.items)

    def subset(self, indices):
        """A new Index over self.items[i] for i in indices, reusing the lowercased texts
        (no re-lowercasing): rank a filtered part of a big list cheaply."""
        sub = Index([])
        sub.items = [self.items[i] for i in indices]
        sub.texts = [self.texts[i] for i in indices]
        sub.lows = [self.lows[i] for i in indices]
        return sub

    def rank(self, query, limit=50):
        """Same result as textmatch.rank(query, items, key, limit)."""
        words = _words(query)
        if not words:
            chosen = self.items[:limit] if limit else self.items
            return [(0.0, item) for item in chosen]
        return _rank(words, self.items, self.texts, self.lows, limit)
