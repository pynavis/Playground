# -*- coding: utf-8 -*-
"""Which trade (discipline) a model belongs to, from its file name.

    trades.trade_of('PRJ-MECH-L01.nwc')            # 'Mechanical'
    trades.trade_of('S-Frame.rvt')                 # 'Structure'
    trades.trade_of(name, trades.rules_from_config())   # the user's rules first

Rules are an ordered list of (regex, trade), searched case-insensitively in the file's
BASENAME (folders are ignored); the first hit wins, 'Unassigned' when none does.
DEFAULT_RULES go from the most specific evidence to the least: discipline words
(sprinkler, plumbing, hvac, structural...), then short codes standing alone between
separators (FP, PL, ME, EL, STR, ST, AR...), then single-letter discipline prefixes at
the very start of the name (A-101, S_Frame, M Ducts). Combined 'MEP' models stay Unassigned on
purpose: add a config trade_rules entry such as ['\\bMEP\\b', 'Mechanical'] to decide.

Pure stdlib.
"""
import re

UNASSIGNED = 'Unassigned'

# A token boundary: start/end of the name or any non-alphanumeric character.
_B = r'(?:^|[^a-z0-9])'
_E = r'(?:[^a-z0-9]|$)'
# A single-letter discipline prefix: the first character, then '-', '_', '.' or a space.
# (Letters in the middle of a name are usually buildings or zones: 'Tower A', 'Block C'.)
_LETTER = r'^%s[-_ .]'

DEFAULT_RULES = [
    # discipline words (stems match anywhere a word starts)
    (_B + r'fire[-_ ]?(?:protection|fighting|suppression|sprinklers?)', 'Fire Protection'),
    (_B + r'sprink', 'Fire Protection'),
    (_B + r'plumb', 'Plumbing'),
    (_B + r'(?:sanitary|drainage|hydraulics?|domestic[-_ ]?water)' + _E, 'Plumbing'),
    (_B + r'(?:mech|hvac|ductwork|ducts?' + _E + r'|ventilation|air[-_ ]?conditioning)', 'Mechanical'),
    (_B + r'(?:elec|lighting' + _E + r'|power' + _E + r'|cable[-_ ]?trays?|telecom|low[-_ ]?voltage)',
     'Electrical'),
    (_B + r'(?:struct|steel' + _E + r'|rebar|foundations?' + _E + r'|precast|framing' + _E + r')',
     'Structure'),
    (_B + r'(?:arch|interiors?' + _E + r'|facade|curtain[-_ ]?wall)', 'Architecture'),
    (_B + r'(?:civil|landscap|topo|earthworks?|infrastructure|site[-_ ]?works?' + _E + r'|site' + _E + r')',
     'Civil'),
    # short codes standing alone
    (_B + r'(?:fp|fps|spk)' + _E, 'Fire Protection'),
    (_B + r'(?:pl|plg)' + _E, 'Plumbing'),
    (_B + r'(?:me|mec|mch|hv|mv)' + _E, 'Mechanical'),
    (_B + r'(?:el|elv|lt|lv)' + _E, 'Electrical'),
    (_B + r'(?:str|stru|st)' + _E, 'Structure'),
    (_B + r'(?:ar|arc|archi)' + _E, 'Architecture'),
    (_B + r'(?:civ)' + _E, 'Civil'),
    # single-letter prefixes at the start of the name (A-101, S_Frame, M Ducts)
    (_LETTER % 'a', 'Architecture'),
    (_LETTER % 's', 'Structure'),
    (_LETTER % 'm', 'Mechanical'),
    (_LETTER % 'e', 'Electrical'),
    (_LETTER % 'p', 'Plumbing'),
    (_LETTER % 'f', 'Fire Protection'),
    (_LETTER % 'c', 'Civil'),
]

_COMPILED = {}
_MEMO = {}


def _compiled(rules):
    """[(compiled_regex, trade)] for rules; invalid regexes are skipped."""
    key = tuple((str(p), str(t)) for p, t in rules)
    found = _COMPILED.get(key)
    if found is None:
        found = []
        for pattern, trade in key:
            try:
                found.append((re.compile(pattern, re.IGNORECASE), trade))
            except Exception:
                continue
        _COMPILED[key] = found
    return key, found


def basename_of(name):
    """The file name part of a model name or path, lowercased ('' for None)."""
    text = str(name or '').strip().replace('/', '\\')
    return text.rstrip('\\').split('\\')[-1].lower()


def trade_of(name, rules=None):
    """The trade for a model / source file name, or 'Unassigned'. rules: an ordered list of
    (regex, trade) pairs (lists of two work too); default DEFAULT_RULES."""
    key, compiled = _compiled(DEFAULT_RULES if rules is None else rules)
    base = basename_of(name)
    memo_key = (key, base)
    if memo_key in _MEMO:
        return _MEMO[memo_key]
    result = UNASSIGNED
    if base:
        for regex, trade in compiled:
            if regex.search(base):
                result = trade
                break
    _MEMO[memo_key] = result
    return result


def explain(name, rules=None):
    """(trade, pattern) of the rule that decided, or ('Unassigned', None)."""
    _key, compiled = _compiled(DEFAULT_RULES if rules is None else rules)
    base = basename_of(name)
    for regex, trade in compiled:
        if base and regex.search(base):
            return trade, regex.pattern
    return UNASSIGNED, None


def rules_from_config(cfg=None):
    """config 'trade_rules' (valid [regex, trade] pairs, in order) followed by
    DEFAULT_RULES. cfg defaults to namo.config.load()."""
    if cfg is None:
        from namo import config
        cfg = config.load()
    out = []
    for pair in cfg.get('trade_rules') or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] and pair[1]:
            try:
                re.compile(str(pair[0]))
            except Exception:
                continue
            out.append((str(pair[0]), str(pair[1]).strip()))
    return out + list(DEFAULT_RULES)


def classify(names, rules=None):
    """{name: trade} for many names at once (memoised per run)."""
    return dict((name, trade_of(name, rules)) for name in names)
