# -*- coding: utf-8 -*-
"""Named, saved configurations per tool ("templates"), shared with the team when a
shared folder is set. Report Templates and Scheduled Reports read them all.

    t = templates.Templates('clash_excel')
    t.save('Weekly coordination', config)       # replaces a template of that name
    t.names()                                   # ['Weekly coordination', ...] sorted
    config = t.get('Weekly coordination')       # a copy, or None
    t.export(path) ; t.import_file(path)        # move templates between projects

File: <team_root>\\templates\\<tool_id>.json (team_root is the shared folder when set and
reachable, else %APPDATA%\\pyNavis\\playground), shape

    {"format": "playground-templates", "version": 1, "tool": "<tool_id>",
     "templates": {"<name>": {"config": {...}, "updated": "<ISO time>", "user": "<name>"}}}

Names are unique ignoring case (saving 'weekly' replaces 'Weekly'); names() sorts them
in natural order. Every change is a locked read-modify-write, so two people saving
different templates of the same tool both keep theirs. Reads never raise (a damaged file
is moved aside and reads as empty); writes raise IOError. Pure stdlib.
"""
import copy
import datetime
import os

from namo import naming, paths, session

FORMAT = 'playground-templates'
VERSION = 1


def folder():
    """<team_root>\\templates (not created)."""
    return os.path.join(paths.team_root(), 'templates')


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def _user():
    try:
        from namo import config
        return config.user_name()
    except Exception:
        return os.environ.get('USERNAME', '')


def _entries(data):
    """{name: entry} from a loaded file body (tolerates junk)."""
    if not isinstance(data, dict):
        return {}
    found = data.get('templates')
    if not isinstance(found, dict):
        return {}
    out = {}
    for name in found:
        entry = found[name]
        if isinstance(entry, dict) and isinstance(entry.get('config'), dict):
            out[str(name)] = entry
    return out


def _find(entries, name):
    """The stored key matching name exactly, else ignoring case, else None."""
    if name in entries:
        return name
    lowered = str(name).strip().lower()
    for key in sorted(entries):
        if key.strip().lower() == lowered:
            return key
    return None


class Templates(object):
    """The templates of one tool. Attributes: tool_id, path."""

    def __init__(self, tool_id):
        if not tool_id or not str(tool_id).strip():
            raise ValueError('templates need a tool id')
        self.tool_id = str(tool_id).strip()
        self.path = os.path.join(folder(), paths.safe_filename(self.tool_id) + '.json')

    def __repr__(self):
        return '<Templates %s>' % self.tool_id

    def _load(self):
        return _entries(paths.load_json(self.path, {}))

    def _write(self, entries):
        body = {'format': FORMAT, 'version': VERSION, 'tool': self.tool_id,
                'templates': entries}
        paths.write_json(self.path, body)

    def _change(self, fn):
        with paths.FileLock(self.path):
            entries = self._load()
            result = fn(entries)
            self._write(entries)
            return result

    def names(self):
        """Template names, natural order, case-insensitive."""
        return sorted(self._load(), key=naming.natural_key)

    def get(self, name):
        """A deep copy of the template's config, or None."""
        entries = self._load()
        key = _find(entries, name)
        return copy.deepcopy(entries[key]['config']) if key is not None else None

    def info(self, name):
        """{'name', 'updated', 'user'} for a template, or None."""
        entries = self._load()
        key = _find(entries, name)
        if key is None:
            return None
        entry = entries[key]
        return {'name': key, 'updated': entry.get('updated', ''), 'user': entry.get('user', '')}

    def save(self, name, config):
        """Stores config (a JSON-serialisable dict) under name, replacing a template with
        the same name in any case. Returns the stored name. ValueError for an empty name
        or a non-dict config; IOError when it cannot be written."""
        name = naming.sanitize(name)
        if not name:
            raise ValueError('A template needs a name.')
        if not isinstance(config, dict):
            raise ValueError('A template config must be a dict.')
        stored = copy.deepcopy(config)

        def apply(entries):
            old = _find(entries, name)
            if old is not None:
                del entries[old]
            entries[name] = {'config': stored, 'updated': _now(), 'user': _user()}
            return name
        return self._change(apply)

    def delete(self, name):
        """Removes a template. True when one was removed."""
        if _find(self._load(), name) is None:
            return False

        def apply(entries):
            key = _find(entries, name)
            if key is None:
                return False
            del entries[key]
            return True
        return self._change(apply)

    def rename(self, old, new):
        """Renames a template, keeping its config. Returns the new name. ValueError when old
        does not exist, new is empty, or another template already has the new name."""
        new = naming.sanitize(new)
        if not new:
            raise ValueError('A template needs a name.')

        def apply(entries):
            key = _find(entries, old)
            if key is None:
                raise ValueError('There is no template called "%s".' % old)
            clash = _find(entries, new)
            if clash is not None and clash != key:
                raise ValueError('A template called "%s" already exists.' % clash)
            entry = entries.pop(key)
            entry['updated'] = _now()
            entries[new] = entry
            return new
        return self._change(apply)

    def export(self, path, names=None):
        """Writes the templates (all, or those named) to a portable file at path. Returns
        how many were written. IOError when it cannot be written."""
        entries = self._load()
        chosen = {}
        wanted = sorted(entries) if names is None else names
        for name in wanted:
            key = _find(entries, name)
            if key is not None:
                chosen[key] = entries[key]
        body = {'format': FORMAT, 'version': VERSION, 'tool': self.tool_id,
                'templates': chosen}
        paths.write_json(path, body)
        return len(chosen)

    def import_file(self, path, replace=False):
        """Adds the templates in an exported file. replace=False keeps existing templates
        and stores clashing names as 'Name (2)'; replace=True overwrites them. Returns how
        many were imported. ValueError (with a sentence for a toast) when the file cannot
        be read, is not a Playground templates file, or belongs to another tool."""
        if not os.path.exists(path):
            raise ValueError('The file %s does not exist.' % os.path.basename(path))
        data = paths.load_json(path, None, move_aside=False)
        if not isinstance(data, dict) or data.get('format') != FORMAT:
            raise ValueError('%s is not a Playground templates file.' % os.path.basename(path))
        tool = data.get('tool')
        if tool and str(tool) != self.tool_id:
            raise ValueError('That file holds templates for %s, not %s.' % (tool, self.tool_id))
        incoming = _entries(data)
        if not incoming:
            return 0

        def apply(entries):
            count = 0
            for name in sorted(incoming, key=naming.natural_key):
                entry = copy.deepcopy(incoming[name])
                key = _find(entries, name)
                target = name
                if key is not None:
                    if replace:
                        del entries[key]
                    else:
                        target = naming.unique(name, list(entries))
                entries[target] = entry
                count += 1
            return count
        return self._change(apply)


def all_tools():
    """Sorted tool ids that have at least one template (in the current team root)."""
    base = folder()
    if not os.path.isdir(base):
        return []
    found = []
    try:
        names = os.listdir(base)
    except OSError as error:
        session.log('warning', 'could not list %s: %s' % (base, error))
        return []
    for filename in sorted(names):
        if not filename.lower().endswith('.json'):
            continue
        data = paths.load_json(os.path.join(base, filename), None)
        if not _entries(data):
            continue
        tool = data.get('tool') if isinstance(data, dict) else None
        found.append(str(tool) if tool else filename[:-5])
    return sorted(set(found))


# Public names for reading a templates file body loaded elsewhere (bundle import/export):
# entries_of(data) -> {name: {'config', 'updated', 'user'}}; find_name(entries, name) ->
# the stored key matching exactly, else ignoring case, else None.
entries_of = _entries
find_name = _find
