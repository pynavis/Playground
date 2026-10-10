# -*- coding: utf-8 -*-
"""Bulk edits of clash results: one by one for a few, one rebuild per test for many.

Why two routes. pyNavis measured the document-side clash edits on a 350,000-clash
model (pynavis/_clashapply.py): every DocumentClashTests edit costs about the same
however small the change (TestsAddCopy ~170 ms, TestsMove 1 to 3 s), so a tool that
calls TestsEditDisplayName / TestsEditResultStatus / TestsEditResultAssignedTo once per
clash freezes Navisworks for minutes on a big test. The shipped Clash Grouper therefore
rebuilds the test on a detached copy (CreateCopy costs ~0.003 ms per result) and swaps
it in with ONE TestsReplaceWithCopy. This module is that same route for edits that are
not regrouping: names, statuses, assignees, comments.

  * mode_for(count, limit): 'edit' up to `limit` document edits (EDIT_LIMIT, 200),
    'rebuild' above it.
  * rebuild(entry, leaf_edits, group_edits): a detached copy of the test where
    leaf_edits[leaf id](copy) and group_edits[group id](copy) have been applied to the
    copies. Untouched groups are copied whole, so nesting, comments and statuses survive.
  * commit(data, test, new_test): TestsReplaceWithCopy at the test's place. The old test
    wrapper and every result under it are dead afterwards: read what you need first.
  * transition(copy, status, actor): a status change on a detached copy, with the
    approved/resolved stamp the Clash Detective buttons leave.
  * one_step(name, doc, mode, swaps): the undo scope of a write. A single rebuilt test is
    committed exactly as Clash Grouper commits it, one bare TestsReplaceWithCopy (already
    one undo step); in-place edits and several rebuilt tests share one transaction.

entry is a namo.clashname.read_test dict ('test', 'nodes', 'leaves', 'groups').
Pure planning first; the API half lazy-imports pynavis.
"""

EDIT_LIMIT = 200


def mode_for(edit_count, limit=EDIT_LIMIT):
    """'edit' (one document edit per change) or 'rebuild' (one swap per test)."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = EDIT_LIMIT
    return 'edit' if int(edit_count) <= limit else 'rebuild'


def touched_groups(nodes, leaf_ids, group_ids):
    """Group ids whose subtree holds an edited clash or group (pure). nodes are
    namo.clashname.walk_tree nodes."""
    touched = set()

    def walk(items):
        hit = False
        for node in items:
            if node[0] == 'leaf':
                if node[2] in leaf_ids:
                    hit = True
            else:
                inner = walk(node[3])
                if inner or node[2] in group_ids:
                    touched.add(node[2])
                    hit = True
        return hit

    walk(nodes)
    return touched


def leaf_ids_under(node):
    """Leaf ids beneath a group node, tree order (pure)."""
    out = []
    stack = [node]
    while stack:
        current = stack.pop()
        for child in reversed(current[3]):
            if child[0] == 'leaf':
                out.append(child[2])
            else:
                stack.append(child)
    out.sort()
    return out


def needs_transaction(mode, swaps):
    """False only for the case Clash Grouper proves in the field: one rebuilt test, one
    TestsReplaceWithCopy, no transaction around it. Pure."""
    return not (mode == 'rebuild' and int(swaps) <= 1)


# ==== API half (Navisworks only; lazy imports) ===============================================


class _NoScope(object):
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def one_step(name, doc, mode, swaps):
    """The context manager a write runs in so it is ONE undo step (see the module
    docstring)."""
    if not needs_transaction(mode, swaps):
        return _NoScope()
    from pynavis.viewpoints import transaction
    return transaction(name, doc)


def rebuild(entry, leaf_edits=None, group_edits=None):
    """A detached copy of entry's test with the edits applied (no document edit)."""
    leaf_edits = leaf_edits or {}
    group_edits = group_edits or {}
    touched = touched_groups(entry['nodes'], leaf_edits, group_edits)
    new_test = entry['test'].CreateCopy()
    new_test.Children.Clear()

    def build_into(target, nodes):
        for node in nodes:
            if node[0] == 'leaf':
                copy = node[1].CreateCopy()
                edit = leaf_edits.get(node[2])
                if edit is not None:
                    edit(copy)
                target.Add(copy)
                continue
            source, gid, children = node[1], node[2], node[3]
            if gid not in touched:
                target.Add(source.CreateCopy())
                continue
            shell = source.CreateCopy()
            shell.Children.Clear()
            build_into(shell.Children, children)
            edit = group_edits.get(gid)
            if edit is not None:
                edit(shell)
            target.Add(shell)

    build_into(new_test.Children, entry['nodes'])
    return new_test


def _count(collection):
    try:
        return collection.Count
    except AttributeError:
        return len(collection)


def _same(a, b):
    return a is b or str(a.Guid) == str(b.Guid)


def commit(data, test, new_test):
    """TestsReplaceWithCopy at the test's place (pynavis.clash._commit's shape)."""
    parent = test.Parent
    collection = data.Tests if parent is None else parent.Children
    index = -1
    for i in range(_count(collection)):
        if _same(collection[i], test):
            index = i
            break
    if index < 0:
        raise ValueError('The clash test %s is no longer in Clash Detective.' % test.DisplayName)
    if parent is None:
        data.TestsReplaceWithCopy(index, new_test)
    else:
        data.TestsReplaceWithCopy(parent, index, new_test)


def assignee_name(assignee):
    try:
        if assignee is not None and assignee.Assigned:
            return assignee.DisplayName or ''
    except Exception:
        pass
    return ''


def assignee(Api, name):
    """Api.Assignee for a name; an unassigned one for '' or None."""
    if name:
        return Api.Assignee(str(name))
    who = Api.Assignee()
    try:
        who.Unassign()
    except Exception:
        pass
    return who


def comment(Api, text, author=None):
    """Api.Comment with the author when this Navisworks takes one as text (2026 does;
    later releases want an Assignee, so the two-argument form is the fallback)."""
    try:
        if author:
            return Api.Comment(str(text), Api.CommentStatus.New, str(author))
    except Exception:
        pass
    return Api.Comment(str(text), Api.CommentStatus.New)


def transition(copy, status_name, status_value, actor, keep_assignee=True):
    """Moves a DETACHED result copy to a status. UserTransitionStatus(status, who) is the
    object-level twin of TestsEditResultStatus (it stamps approved/resolved by and
    time); when it is refused, or leaves the status as it was, Status is set directly.
    The copy's AssignedTo is put back if the transition moved it."""
    before = assignee_name(copy.AssignedTo)
    try:
        copy.UserTransitionStatus(status_value, actor)
    except Exception:
        pass
    if str(copy.Status) != str(status_name):
        copy.Status = status_value
    if keep_assignee and assignee_name(copy.AssignedTo) != before:
        from pynavis._api import Api
        copy.AssignedTo = assignee(Api, before)
