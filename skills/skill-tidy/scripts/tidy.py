#!/usr/bin/env python3
"""skill-tidy: keep an agent's skill catalog cheap and unambiguous.

Standard library only (Python 3.8+), Windows, macOS and Linux. Every rule and number cites its evidence in
../references/rules.md and ../RESEARCH.md. Commands:

  python tidy.py scan      [--agent A] [--project P] [--json]         the catalog the agent loads, with cost
  python tidy.py lint      [SKILL_DIR ...] [--agent A] [--json]       rule check of descriptions (all when none given)
  python tidy.py conflicts [--agent A] [--threshold 0.45] [--json]    similar pairs, shared words and triggers, a boundary clause
  python tidy.py triggers  SKILL_DIR                                  the trigger phrases and terms a description carries
  python tidy.py check     SKILL_DIR (--new FILE | --desc TEXT)       a proposed description: lint, lost triggers, similarity before/after
  python tidy.py apply     SKILL_DIR (--new FILE | --desc TEXT)       write it into the front matter (backup first; refuses on errors)
  python tidy.py budget    [--agent A] [--window N]                   catalog size against each host's listing budget
  python tidy.py usage     [--days 30] [--json]                       skill invocations from Claude Code and Codex transcripts
  python tidy.py offload   [--days 30] [--write]                      token savings: never-used skills to name-only / off, per host
  python tidy.py startup   [--project P] [--json]                     the always-loaded instruction chain, memory and MCP settings
  python tidy.py harvest   NAME [--days 60]                           missed and doubtful invocations, as a one-rewrite brief
  python tidy.py version

A = claude (default) | codex | copilot | cursor | all.
"""
import argparse
import datetime as _dt
import glob
import json
import math
import os
import re
import shutil
import sys
import time

VERSION = "0.1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
AGENTS = ["claude", "codex", "copilot", "cursor", "all"]


def home():
    return os.environ.get("SKILLTIDY_HOME") or os.path.expanduser("~")  # tests point this at a temp folder


def state_dir():
    return os.environ.get("SKILLTIDY_STATE") or os.path.join(home(), ".skill-tidy")


def read_text(path, limit=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit) if limit else f.read()
    except OSError:
        return ""


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def est_tokens(chars):
    return int(math.ceil(chars / 4.0))


def k(n):
    return "%.1fK" % (n / 1000.0) if n >= 1000 else str(n)


# ----------------------------------------------------------------------------- front matter

_BLOCK = ("", ">", ">-", "|", "|-", ">+", "|+")


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def parse_skill(path):
    """Front matter fields (top-level scalars, block scalars, simple lists) plus body stats. Defensive:
    a file with no front matter yields the directory name and an empty description."""
    text = read_text(path)
    lines = text.splitlines()
    fm, body_start = {}, 0
    if lines and lines[0].lstrip("﻿").strip() == "---":
        end = None
        for i in range(1, min(len(lines), 400)):
            if lines[i].strip() == "---":
                end = i
                break
        if end:
            body_start = end + 1
            i = 1
            while i < end:
                ln = lines[i]
                m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", ln)
                if not m:
                    i += 1
                    continue
                key, val = m.group(1), m.group(2).rstrip()
                if val in _BLOCK:
                    more, j = [], i + 1
                    while j < end and (not lines[j].strip() or lines[j][:1].isspace()):
                        more.append(lines[j].strip())
                        j += 1
                    if more and all(x.startswith("- ") or not x for x in more):
                        fm[key] = [_unquote(x[2:]) for x in more if x]
                    elif val.startswith("|"):
                        fm[key] = NL.join(more).strip()
                    else:
                        fm[key] = " ".join(x for x in more if x)
                    i = j
                    continue
                fm[key] = _unquote(val)
                i += 1
    body = NL.join(lines[body_start:])
    d = os.path.basename(os.path.dirname(os.path.abspath(path)))
    desc = fm.get("description") if isinstance(fm.get("description"), str) else ""
    wtu = fm.get("when_to_use") if isinstance(fm.get("when_to_use"), str) else ""
    return {
        "name": fm.get("name") if isinstance(fm.get("name"), str) and fm.get("name") else d,
        "dir_name": d, "path": path, "fm": fm, "desc": desc or "", "when_to_use": wtu or "",
        "body_lines": len(lines) - body_start, "body_chars": len(body),
        "model_invocable": str(fm.get("disable-model-invocation", "false")).lower() != "true",
    }


# ----------------------------------------------------------------------------- catalog

def _norm_dir(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p))) if p else ""


def claude_plugin_roots(project=None):
    """Installed and enabled Claude Code plugins (installed_plugins.json, version 2 shape): user scope, and
    project scope for this project. Returns [(plugin, skills_glob)]."""
    h = home()
    reg = read_json(os.path.join(h, ".claude", "plugins", "installed_plugins.json"), {}) or {}
    enabled = (read_json(os.path.join(h, ".claude", "settings.json"), {}) or {}).get("enabledPlugins") or {}
    proj = _norm_dir(project)
    out = []
    plugins = reg.get("plugins") if isinstance(reg.get("plugins"), dict) else {}
    for key, entries in plugins.items():
        if enabled.get(key) is False:
            continue
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict) or not e.get("installPath"):
                continue
            pp = _norm_dir(e.get("projectPath"))
            if e.get("scope") in ("project", "local") and not (proj and (proj == pp or proj.startswith(pp + os.sep))):
                continue
            out.append((key.split("@")[0], os.path.join(e["installPath"], "skills", "*", "SKILL.md")))
    return out


def roots_for(agent, project=None):
    """[(host, plugin, glob)] of the skill roots a host reads. Claude Code and Codex roots are documented;
    Copilot and Cursor roots follow their skills docs (RESEARCH.md, Hosts) and are re-checked on refresh."""
    h = home()
    j = os.path.join
    per = {
        "claude": [j(h, ".claude", "skills")] + ([j(project, ".claude", "skills")] if project else []),
        "codex": [j(h, ".agents", "skills"), j(h, ".codex", "skills")] + ([j(project, ".agents", "skills")] if project else []),
        "copilot": [j(h, ".copilot", "skills"), j(h, ".claude", "skills"), j(h, ".agents", "skills")]
        + ([j(project, ".github", "skills"), j(project, ".claude", "skills"), j(project, ".agents", "skills")] if project else []),
        "cursor": [j(h, ".cursor", "skills")] + ([j(project, ".cursor", "skills"), j(project, ".agents", "skills")] if project else []),
    }
    hosts = ["claude", "codex", "copilot", "cursor"] if agent == "all" else [agent]
    out = []
    for host in hosts:
        for r in per[host]:
            out.append((host, None, j(r, "*", "SKILL.md")))
        if host == "claude":
            out += [("claude", p, g) for p, g in claude_plugin_roots(project)]
    return out


def skill_overrides():
    s = read_json(os.path.join(home(), ".claude", "settings.json"), {}) or {}
    o = s.get("skillOverrides")
    return o if isinstance(o, dict) else {}


def scan(agent="claude", project=None):
    """The catalog one agent lists to the model. A file reached twice counts once; the same name and
    description from two roots is a mirror; skills with disable-model-invocation, and Claude Code skills set
    to off or user-invocable-only in skillOverrides, are excluded from the listing but kept with a flag."""
    seen, out = set(), []
    ov = skill_overrides() if agent in ("claude", "all") else {}
    mirror = set()
    for host, plugin, g in roots_for(agent, project):
        for f in sorted(glob.glob(g)):
            rp = os.path.realpath(f)
            if rp in seen:
                continue
            seen.add(rp)
            s = parse_skill(f)
            s["host"], s["plugin"] = host, plugin
            s["id"] = "%s:%s" % (plugin, s["name"]) if plugin else s["name"]
            if (s["name"], s["desc"]) in mirror:
                continue
            mirror.add((s["name"], s["desc"]))
            state = ov.get(s["name"], "on") if not plugin else "on"
            s["override"] = state
            s["listed"] = s["model_invocable"] and state in ("on", "name-only")
            s["listed_chars"] = (len(s["name"]) + (0 if state == "name-only" else len(s["desc"]) + len(s["when_to_use"]))) if s["listed"] else 0
            out.append(s)
    out.sort(key=lambda s: s["id"])
    return out


def listed(skills):
    return [s for s in skills if s["listed"]]


# ----------------------------------------------------------------------------- similarity

_STOP = set((
    "about also always another anything asks based before being between both called check create does "
    "done each every file files from have into itself just like made make more must need needs only other "
    "over same says should skill skills some something such than that their them then there these they "
    "this those through under used user uses using want wants what when whenever where whether which while "
    "with without work would your refresh stale whole the and for not use any are can how its one "
    "said phrases trigger triggers including even").split())
_SUFFIXES = ("ings", "ing", "ies", "ers", "ed", "es", "er", "s")


def _stem(w):
    for suf in _SUFFIXES:
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def _name_words(skills):
    drop = set()
    for s in skills:
        drop.update(w for w in re.split(r"[-_:]", s["name"].lower()) if w)
        if s.get("plugin"):
            drop.update(w for w in re.split(r"[-_]", s["plugin"].lower()) if w)
    return drop


def tokens(text, drop=()):
    return [_stem(w) for w in re.findall(r"[a-z][a-z0-9]+", (text or "").lower())
            if len(w) >= 3 and w not in _STOP and w not in drop]


def _norm_name(name):
    return re.sub(r"[^a-z0-9]", "", name.split(":")[-1].lower())


def vectors(skills, override=None):
    """TF-IDF vectors of descriptions, smoothed IDF over the catalog, skill and plugin name words removed
    (a family label is not trigger text). override maps a skill id to replacement text."""
    drop = _name_words(skills)
    texts = [(override or {}).get(s["id"], s["desc"] + " " + s["when_to_use"]) for s in skills]
    docs = [tokens(t, drop) for t in texts]
    n = len(docs)
    df = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    out = []
    for d in docs:
        tf = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        v = dict((w, c * (math.log((1.0 + n) / (1.0 + df[w])) + 1.0)) for w, c in tf.items())
        norm = math.sqrt(sum(x * x for x in v.values()))
        out.append(dict((w, x / norm) for w, x in v.items()) if norm else {})
    return out


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def pairs(skills, threshold=0.45, override=None):
    vs = vectors(skills, override)
    out = []
    for i in range(len(skills)):
        if len(vs[i]) < 4:
            continue
        for j in range(i + 1, len(skills)):
            if len(vs[j]) < 4 or _norm_name(skills[i]["name"]) == _norm_name(skills[j]["name"]):
                continue
            c = cosine(vs[i], vs[j])
            if c >= threshold:
                shared = sorted(set(vs[i]) & set(vs[j]), key=lambda w: -(vs[i][w] * vs[j][w]))[:8]
                out.append({"score": round(c, 2), "a": skills[i]["id"], "b": skills[j]["id"], "shared_terms": shared})
    out.sort(key=lambda p: (-p["score"], p["a"], p["b"]))
    return out


def max_similarity(skills, sid, override=None):
    vs = vectors(skills, override)
    idx = [i for i, s in enumerate(skills) if s["id"] == sid]
    if not idx:
        return 0.0, None
    i = idx[0]
    best, who = 0.0, None
    for j in range(len(skills)):
        if j != i and _norm_name(skills[j]["name"]) != _norm_name(skills[i]["name"]):
            c = cosine(vs[i], vs[j])
            if c > best:
                best, who = c, skills[j]["id"]
    return round(best, 2), who


# ----------------------------------------------------------------------------- triggers

def triggers(text):
    """Quoted trigger phrases (straight or curly quotes, 3-80 chars) in the order they appear."""
    out = []
    for m in re.finditer(r"(?:'([^']{3,80})'|\"([^\"]{3,80})\"|‘([^’]{3,80})’|“([^”]{3,80})”)", text or ""):
        t = next(g for g in m.groups() if g)
        if re.search(r"[a-zA-Z]", t) and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out


def key_terms(text, n=12):
    ws = tokens(text)
    freq = {}
    for w in ws:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))][:n]


def coverage(old, new):
    """Old quoted triggers whose meaning the new text no longer carries: a trigger counts as covered when
    every distinctive word of it (stemmed) appears in the new text, quoted or not."""
    new_words = set(tokens(new))
    lost = []
    for t in triggers(old):
        words = set(tokens(t))
        if words and not words <= new_words:
            lost.append({"trigger": t, "missing_words": sorted(words - new_words)})
    old_terms = set(key_terms(old, 20))
    dropped_terms = sorted(old_terms - new_words)
    return lost, dropped_terms


# ----------------------------------------------------------------------------- lint

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PERSON_RE = re.compile(r"\b(I can|I will|I'll|I help|you can|you should|your )", re.I)
VAGUE_RE = re.compile(r"\b(helps with|various|stuff|things|and more|etc\.?|general purpose|anything)\b", re.I)
WHEN_RE = re.compile(r"\b(use (it |this skill |this )?(when|whenever|for|to|on|if)|trigger(s|ed)? (when|on)|when the user|invoke when)\b", re.I)
STEER_RE = re.compile(r"\b(always use this|must (always )?use this|prefer this skill|ignore (other|the other)|highest priority|instead of any other|before any other skill)\b", re.I)
BOUNDARY_RE = re.compile(r"\b(not for|do not use|don't use|is the sibling|that is [a-z0-9:-]+|use [a-z0-9:-]+ instead|belongs to|, use [a-z0-9]+-[a-z0-9-]+|is (the )?[a-z0-9]+-[a-z0-9-]+( skill)?\b)", re.I)
QUOTED_RE = re.compile("'[^']{3,80}'|\"[^\"]{3,80}\"|‘[^’]{3,80}’|“[^”]{3,80}”")
XML_RE = re.compile(r"<[A-Za-z/][^>]{0,40}>")

SEV = {"error": 3, "warn": 2, "info": 1}


def lint_skill(s, catalog=None, sim_threshold=0.45):
    """Findings [(rule, severity, message)] for one parsed skill. Rule texts and evidence: references/rules.md."""
    f = []
    name, desc, wtu = s["name"], s["desc"], s["when_to_use"]
    add = f.append
    if not NAME_RE.match(name) or len(name) > 64:
        add(("ST001", "error", "name must be 1-64 chars of a-z, 0-9 and single hyphens (Agent Skills spec)"))
    if name != s["dir_name"]:
        add(("ST002", "warn", "name '%s' differs from its folder '%s' (spec: must match)" % (name, s["dir_name"])))
    if re.search(r"anthropic|claude", name):
        add(("ST003", "error", "name contains a reserved word (anthropic, claude)"))
    if not desc.strip():
        add(("ST004", "error", "no description: the model has nothing to select on (hosts fall back to the first body line)"))
        return f
    if len(desc) > 1024:
        add(("ST005", "error", "description is %d chars; the spec caps it at 1,024 and some hosts drop longer ones" % len(desc)))
    if len(desc) + len(wtu) > 1536:
        add(("ST006", "error", "description + when_to_use is %d chars; Claude Code truncates the listing at 1,536" % (len(desc) + len(wtu))))
    words = len(desc.split())
    if words > 200:
        add(("ST007", "warn", "%d words; aim for about 100-200 (skill-creator's description rewriter)" % words))
    if len(desc) <= 40 or words < 8:
        add(("ST008", "warn", "too short to select on (%d chars); say what it does and when to use it" % len(desc)))
    if not WHEN_RE.search(desc + " " + wtu):
        add(("ST009", "warn", "no 'Use when ...' clause: say when to use it, not only what it does (spec, Anthropic, Copilot docs)"))
    if PERSON_RE.search(QUOTED_RE.sub(" ", desc)):  # quoted user phrases may say 'my' or 'your'; the prose may not
        add(("ST010", "warn", "first or second person ('I can', 'you can'); write in third person or the imperative 'Use when' (Anthropic best practices)"))
    if VAGUE_RE.search(desc):
        add(("ST011", "info", "vague wording (%s); name the concrete task and the words a user types" % VAGUE_RE.search(desc).group(0)))
    if XML_RE.search(desc):
        add(("ST012", "error", "XML-like tag in the description (not allowed by Anthropic's skill rules)"))
    trig = triggers(desc)
    if len(trig) > 12:
        add(("ST013", "warn", "%d quoted trigger phrases; long lists read as keyword stuffing and crowd out the key use case (skill-creator, skillscheck)" % len(trig)))
    first = re.split(r"(?<=[.!?])\s", desc.strip(), maxsplit=1)[0]
    if re.match(r"^(this skill|a skill|skill (for|to)|helps|helper|utility|tool (for|to))\b", first, re.I):
        add(("ST014", "info", "the first sentence opens generically; put the key use case and its trigger words first (Claude Code, Codex: front-load)"))
    if STEER_RE.search(desc):
        add(("ST015", "warn", "steering text ('%s'); descriptions should describe, not push selection (arXiv 2609.02035)" % STEER_RE.search(desc).group(0)))
    if s["body_lines"] > 500 or est_tokens(s["body_chars"]) > 5000:
        add(("ST016", "warn", "body is %d lines / ~%s tokens; the spec suggests under 500 lines and 5K tokens, detail in references/" % (s["body_lines"], k(est_tokens(s["body_chars"])))))
    comp = s["fm"].get("compatibility")
    if isinstance(comp, str) and len(comp) > 500:
        add(("ST017", "error", "compatibility is %d chars (spec max 500)" % len(comp)))
    if wtu:
        add(("ST018", "info", "when_to_use is read by Claude Code only; triggers kept there are lost on Codex, Copilot and Cursor"))
    if catalog:
        best, who = max_similarity(catalog, s.get("id", name))
        if best >= sim_threshold and not BOUNDARY_RE.search(desc):
            add(("ST019", "warn", "description is %.2f similar to %s and has no boundary clause; end with one short 'Not for <their job> (that is %s)'" % (best, who, who.split(":")[-1])))
    return f


# ----------------------------------------------------------------------------- budgets

def budgets(skills, window):
    """Characters of the listing against each host's documented limit (RESEARCH.md, Hosts)."""
    ls = listed(skills)
    chars = sum(s["listed_chars"] for s in ls)
    return {
        "skills_listed": len(ls), "listing_chars": chars, "listing_tokens_est": est_tokens(chars),
        "claude": {"budget_chars": int(window * 0.01), "over": chars > window * 0.01,
                   "rule": "skillListingBudgetFraction 0.01 of the window; over it, least-used descriptions are dropped (names stay)",
                   "cut_1536": [s["id"] for s in ls if len(s["desc"]) + len(s["when_to_use"]) > 1536]},
        "codex": {"budget_chars": int(window * 0.02) if window else 8000, "over": chars > (window * 0.02 if window else 8000),
                  "rule": "2% of the window, or 8,000 chars when unknown; descriptions are shortened first, then skills omitted"},
        "spec": {"over_1024": [s["id"] for s in ls if len(s["desc"]) > 1024],
                 "rule": "Agent Skills spec: description 1-1,024 chars; Copilot is reported to drop longer ones"},
    }


# ----------------------------------------------------------------------------- usage (transcripts)

def _recent(pattern, days):
    cutoff = time.time() - days * 86400
    out = []
    for f in glob.glob(pattern, recursive=True):
        try:
            if os.path.getmtime(f) >= cutoff:
                out.append(f)
        except OSError:
            pass
    return out


CMD_RE = re.compile(r"<command-name>/?([A-Za-z0-9:_-]+)</command-name>")
CODEX_SKILL_RE = re.compile(r"<skill>\s*<name>([^<]+)</name>")


def claude_events(days):
    """Yield (session, kind, value, text) from Claude Code transcripts: ('prompt', None, text),
    ('skill', name, None) for a Skill tool call, ('command', name, None) for a typed slash command.
    The JSONL format is internal and unstable; unknown lines are skipped."""
    for f in _recent(os.path.join(home(), ".claude", "projects", "**", "*.jsonl"), days):
        sid = os.path.basename(f)
        try:
            fh = open(f, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"Skill"' not in line and '"user"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                msg = o.get("message") if isinstance(o.get("message"), dict) else {}
                content = msg.get("content")
                if o.get("type") == "user" and not o.get("isSidechain"):
                    text = content if isinstance(content, str) else " ".join(
                        c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text") if isinstance(content, list) else ""
                    for m in CMD_RE.finditer(text or ""):
                        yield sid, "command", m.group(1), None
                    if text and not text.startswith("<") and not o.get("isMeta"):
                        yield sid, "prompt", None, text
                elif o.get("type") == "assistant" and isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Skill":
                            nm = (c.get("input") or {}).get("skill")
                            if nm:
                                yield sid, "skill", str(nm), None


def codex_events(days):
    for f in _recent(os.path.join(home(), ".codex", "sessions", "**", "rollout-*.jsonl"), days):
        for m in CODEX_SKILL_RE.finditer(read_text(f)):
            yield os.path.basename(f), "skill", m.group(1).strip(), None


def usage(days):
    counts = {}
    for _, kind, name, _ in list(claude_events(days)) + list(codex_events(days)):
        if kind in ("skill", "command"):
            key = name.split(":")[-1]
            counts[key] = counts.get(key, 0) + 1
    return counts


# ----------------------------------------------------------------------------- startup chain

IMPORT_RE = re.compile(r"(?m)^\s*@([^\s]+)")


def instruction_chain(project):
    """Instruction files Claude Code loads at startup, following @imports (depth 5), with sizes."""
    h = home()
    starts = [os.path.join(h, ".claude", "CLAUDE.md")]
    if project:
        d, chain = os.path.abspath(project), []
        while True:  # Claude Code loads CLAUDE.md files from the working directory up to the root
            chain.append(d)
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
        for d in reversed(chain):
            here = [os.path.join(d, "CLAUDE.md"), os.path.join(d, "CLAUDE.local.md"), os.path.join(d, ".claude", "CLAUDE.md")]
            starts += here
            if d == os.path.abspath(project) and not any(os.path.exists(p) for p in here):
                starts.append(os.path.join(d, "AGENTS.md"))  # read by itself only when no CLAUDE.md exists
    seen, out = set(), []

    def walk(p, depth, via):
        rp = _norm_dir(p)
        if rp in seen or depth > 5 or not os.path.isfile(p):
            return
        seen.add(rp)
        t = read_text(p)
        out.append({"path": p, "chars": len(t), "tokens_est": est_tokens(len(t)), "via": via})
        for m in IMPORT_RE.finditer(t):
            ref = m.group(1)
            q = os.path.expanduser(ref) if ref.startswith("~") else (ref if os.path.isabs(ref) else os.path.join(os.path.dirname(p), ref))
            walk(q, depth + 1, os.path.basename(p))

    for p in starts:
        walk(p, 0, None)
    if project:
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(project))
        mem = os.path.join(h, ".claude", "projects", slug, "memory", "MEMORY.md")
        if os.path.isfile(mem):
            t = read_text(mem)
            first = NL.join(t.splitlines()[:200])[:25000]
            out.append({"path": mem, "chars": len(first), "tokens_est": est_tokens(len(first)), "via": "auto-memory (first 200 lines / 25KB)"})
    return out


def mcp_settings(project):
    h = home()
    cfg = read_json(os.path.join(h, ".claude.json"), {}) or {}
    servers = dict(cfg.get("mcpServers") or {})
    if project:
        servers.update((read_json(os.path.join(project, ".mcp.json"), {}) or {}).get("mcpServers") or {})
        pc = (cfg.get("projects") or {}).get(os.path.abspath(project).replace(os.sep, "/")) or {}
        servers.update(pc.get("mcpServers") or {})
    settings = read_json(os.path.join(h, ".claude", "settings.json"), {}) or {}
    env = settings.get("env") or {}
    return {
        "servers": sorted(servers), "always_load": sorted(n for n, s in servers.items() if isinstance(s, dict) and s.get("alwaysLoad")),
        "enable_tool_search": env.get("ENABLE_TOOL_SEARCH", os.environ.get("ENABLE_TOOL_SEARCH")),
        "max_mcp_description": env.get("CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH"),
    }


# ----------------------------------------------------------------------------- writing

def yaml_quote(text):
    return json.dumps(text, ensure_ascii=False)  # a JSON string is a valid YAML double-quoted scalar


def set_description(path, new_desc):
    """Replace the description (single line or block scalar) in a SKILL.md front matter, keeping every other
    byte and the file's line endings. Backs the file up under the state dir first. Returns the backup path."""
    raw = open(path, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    lines = raw.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].lstrip("﻿").strip() != "---":
        raise ValueError("no front matter in %s" % path)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("unterminated front matter in %s" % path)
    idx = next((i for i in range(1, end) if re.match(r"^description:", lines[i])), None)
    new_line = "description: " + yaml_quote(new_desc)
    if idx is None:
        lines.insert(end, new_line)
    else:
        j = idx + 1
        if lines[idx].split(":", 1)[1].strip() in _BLOCK:
            while j < end and (not lines[j].strip() or lines[j][:1].isspace()):
                j += 1
        lines[idx:j] = [new_line]
    bdir = os.path.join(state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(bdir, exist_ok=True)
    backup = os.path.join(bdir, os.path.basename(os.path.dirname(os.path.abspath(path))) + ".SKILL.md")
    shutil.copy2(path, backup)
    out = "\n".join(lines)
    if crlf:
        out = out.replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(out.encode("utf-8"))
    return backup


def merge_skill_overrides(entries):
    """Merge {name: state} into ~/.claude/settings.json skillOverrides, with a backup. Never touches other keys."""
    p = os.path.join(home(), ".claude", "settings.json")
    cur = read_json(p, None)
    if cur is None and os.path.exists(p):
        raise ValueError("%s is not valid JSON; refusing to rewrite it" % p)
    cur = cur or {}
    bdir = os.path.join(state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(bdir, exist_ok=True)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(bdir, "settings.json"))
    so = cur.get("skillOverrides") if isinstance(cur.get("skillOverrides"), dict) else {}
    so.update(entries)
    cur["skillOverrides"] = so
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=2)
        fh.write("\n")
    return p


# ----------------------------------------------------------------------------- commands

def _catalog(a):
    return scan(getattr(a, "agent", "claude") or "claude", getattr(a, "project", None) or os.getcwd())


def _find(skills, target):
    if os.path.isdir(target) or os.path.isfile(target):
        p = target if target.endswith("SKILL.md") else os.path.join(target, "SKILL.md")
        rp = os.path.realpath(p)
        for s in skills:
            if os.path.realpath(s["path"]) == rp:
                return s
        s = parse_skill(p)
        s.update({"id": s["name"], "plugin": None, "host": "file", "override": "on", "listed": True,
                  "listed_chars": len(s["name"]) + len(s["desc"])})
        skills.append(s)
        return s
    for s in skills:
        if target in (s["id"], s["name"]):
            return s
    return None


def _new_text(a):
    if getattr(a, "desc", None):
        return a.desc.strip()
    if getattr(a, "new", None):
        t = read_text(a.new).strip()
        return re.sub(r"\s+", " ", t)
    raise SystemExit("give --new FILE or --desc TEXT")


def out(obj, as_json, lines):
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(NL.join(lines))


def cmd_scan(a):
    sk = _catalog(a)
    ls = listed(sk)
    lines = ["%d skills found, %d listed to the model, ~%s tokens of listing (%s)" % (
        len(sk), len(ls), k(est_tokens(sum(s["listed_chars"] for s in ls))), a.agent)]
    for s in sorted(sk, key=lambda s: -s["listed_chars"]):
        flag = "" if s["listed"] else "  [not listed: %s]" % ("disable-model-invocation" if not s["model_invocable"] else s["override"])
        lines.append("  %-44s %5d chars%s" % (s["id"][:44], s["listed_chars"], flag))
    out([{k_: s[k_] for k_ in ("id", "name", "plugin", "host", "path", "listed", "listed_chars", "override")} for s in sk], a.json, lines)
    return 0


def cmd_lint(a):
    sk = _catalog(a)
    cat = listed(sk)
    targets = [_find(sk, t) for t in a.skills] if a.skills else cat
    res, lines, worst = [], [], 0
    for s in targets:
        if s is None:
            continue
        f = lint_skill(s, cat, a.threshold)
        res.append({"id": s["id"], "path": s["path"], "findings": [{"rule": r, "severity": v, "message": m} for r, v, m in f]})
        for r, v, m in f:
            worst = max(worst, SEV[v])
            if SEV[v] >= SEV[a.min]:
                lines.append("%-5s %s %s: %s" % (v.upper(), r, s["id"], m))
    lines.append("%d skills checked; %d findings at %s or above" % (len(res), len([1 for r in res for x in r["findings"] if SEV[x["severity"]] >= SEV[a.min]]), a.min))
    out(res, a.json, lines)
    return 1 if worst >= 3 else 0


def boundary_clause(sk, a_id, b_id):
    """A starting point for the one boundary sentence research and vendor docs recommend: the other skill's
    first clause as its job. Descriptions usually open with a verb, so 'To <job>, use <name>.' reads."""
    b = next(s for s in sk if s["id"] == b_id)
    first = re.split(r"(?<=[.!?])\s|[:;(,]", b["desc"].strip(), maxsplit=1)[0].strip().rstrip(".")
    words = first.split()
    job = " ".join(words[:9]) + ("..." if len(words) > 9 else "")
    return "To %s%s, use %s." % (job[:1].lower(), job[1:], b["name"])


def cmd_conflicts(a):
    sk = listed(_catalog(a))
    ps = pairs(sk, a.threshold)
    lines = ["%d pairs at TF-IDF cosine >= %.2f among %d listed skills (0.65+ near-duplicate)" % (len(ps), a.threshold, len(sk))]
    for p in ps:
        da = next(s for s in sk if s["id"] == p["a"])["desc"]
        db = next(s for s in sk if s["id"] == p["b"])["desc"]
        shared_trig = sorted(set(t.lower() for t in triggers(da)) & set(t.lower() for t in triggers(db)))
        p["shared_triggers"] = shared_trig
        p["suggest_a"] = boundary_clause(sk, p["a"], p["b"])
        p["suggest_b"] = boundary_clause(sk, p["b"], p["a"])
        lines.append("%.2f %s ~ %s%s" % (p["score"], p["a"], p["b"], "  NEAR-DUPLICATE" if p["score"] >= 0.65 else ""))
        lines.append("     shared words: %s" % ", ".join(p["shared_terms"]))
        if shared_trig:
            lines.append("     same trigger phrase in both: %s" % "; ".join(shared_trig))
        lines.append("     boundary for %s: %s" % (p["a"], p["suggest_a"]))
        lines.append("     boundary for %s: %s" % (p["b"], p["suggest_b"]))
    out(ps, a.json, lines)
    return 0


def cmd_triggers(a):
    sk = _catalog(a)
    s = _find(sk, a.skill)
    if not s:
        print("no skill %s" % a.skill)
        return 2
    t = triggers(s["desc"] + " " + s["when_to_use"])
    terms = key_terms(s["desc"] + " " + s["when_to_use"])
    out({"triggers": t, "key_terms": terms}, a.json, ["triggers (%d):" % len(t)] + ["  " + x for x in t] + ["key terms: " + ", ".join(terms)])
    return 0


def check_rewrite(sk, s, new, threshold=0.45):
    trial = dict(s)
    trial["desc"] = new
    findings = lint_skill(trial, [dict(x, desc=new) if x["id"] == s["id"] else x for x in listed(sk)], threshold)
    lost, dropped = coverage(s["desc"] + " " + s["when_to_use"], new + " " + s["when_to_use"])
    before = max_similarity(listed(sk), s["id"])
    after = max_similarity(listed(sk), s["id"], {s["id"]: new + " " + s["when_to_use"]})
    return {"findings": [{"rule": r, "severity": v, "message": m} for r, v, m in findings], "lost_triggers": lost,
            "dropped_terms": dropped, "chars_before": len(s["desc"]), "chars_after": len(new),
            "max_similarity_before": {"score": before[0], "with": before[1]},
            "max_similarity_after": {"score": after[0], "with": after[1]},
            "ok": not any(v == "error" for _, v, _ in findings) and not lost}


def cmd_check(a):
    sk = _catalog(a)
    s = _find(sk, a.skill)
    if not s:
        print("no skill %s" % a.skill)
        return 2
    r = check_rewrite(sk, s, _new_text(a), a.threshold)
    lines = ["%s: %d -> %d chars; closest skill %.2f (%s) -> %.2f (%s)" % (
        s["id"], r["chars_before"], r["chars_after"], r["max_similarity_before"]["score"], r["max_similarity_before"]["with"],
        r["max_similarity_after"]["score"], r["max_similarity_after"]["with"])]
    for x in r["findings"]:
        lines.append("  %-5s %s %s" % (x["severity"].upper(), x["rule"], x["message"]))
    for x in r["lost_triggers"]:
        lines.append("  LOST  trigger '%s' (missing words: %s)" % (x["trigger"], ", ".join(x["missing_words"])))
    if r["dropped_terms"]:
        lines.append("  note  frequent terms no longer present: %s" % ", ".join(r["dropped_terms"]))
    lines.append("OK: safe to apply" if r["ok"] else "NOT OK: fix the errors and lost triggers first (or apply --force)")
    out(r, a.json, lines)
    return 0 if r["ok"] else 1


def cmd_apply(a):
    sk = _catalog(a)
    s = _find(sk, a.skill)
    if not s:
        print("no skill %s" % a.skill)
        return 2
    new = _new_text(a)
    r = check_rewrite(sk, s, new, a.threshold)
    if not r["ok"] and not a.force:
        print("refused: the check found errors or lost triggers; run `check` to see them, or pass --force")
        return 1
    if s["plugin"] and "plugins" + os.sep + "cache" in os.path.abspath(s["path"]):
        print("refused: %s is an installed plugin copy; edit the plugin's source repository instead" % s["path"])
        return 1
    b = set_description(s["path"], new)
    print("wrote %s (backup %s); closest skill now %.2f (%s)" % (s["path"], b, r["max_similarity_after"]["score"], r["max_similarity_after"]["with"]))
    return 0


def cmd_budget(a):
    sk = _catalog(a)
    b = budgets(sk, a.window)
    lines = ["%d skills listed, %s chars (~%s tokens) of listing, window %s" % (b["skills_listed"], k(b["listing_chars"]), k(b["listing_tokens_est"]), k(a.window)),
             "claude: budget %s chars -> %s (%s)" % (k(b["claude"]["budget_chars"]), "OVER" if b["claude"]["over"] else "within", b["claude"]["rule"]),
             "codex:  budget %s chars -> %s (%s)" % (k(b["codex"]["budget_chars"]), "OVER" if b["codex"]["over"] else "within", b["codex"]["rule"])]
    if b["claude"]["cut_1536"]:
        lines.append("cut at 1,536 in Claude Code: " + ", ".join(b["claude"]["cut_1536"]))
    if b["spec"]["over_1024"]:
        lines.append("over the spec's 1,024: " + ", ".join(b["spec"]["over_1024"]))
    out(b, a.json, lines)
    return 0


def cmd_usage(a):
    c = usage(a.days)
    sk = listed(_catalog(a))
    rows = [(s["id"], c.get(s["name"], 0), s["listed_chars"]) for s in sk]
    rows.sort(key=lambda r: (r[1], -r[2]))
    lines = ["skill invocations in the last %d days (Claude Code Skill calls and slash commands, Codex skill blocks)" % a.days]
    for sid, n, ch in rows:
        lines.append("  %4d  %-44s %5d chars listed" % (n, sid[:44], ch))
    unused = [r for r in rows if r[1] == 0]
    lines.append("%d of %d listed skills unused; their descriptions cost ~%s tokens every session" % (
        len(unused), len(rows), k(est_tokens(sum(r[2] for r in unused)))))
    out({"days": a.days, "counts": {r[0]: r[1] for r in rows}}, a.json, lines)
    return 0


def cmd_offload(a):
    c = usage(a.days)
    sk = listed(_catalog(a))
    unused = [s for s in sk if c.get(s["name"], 0) == 0]
    user_level = [s for s in unused if not s["plugin"]]
    plugin_level = [s for s in unused if s["plugin"]]
    save = sum(len(s["desc"]) + len(s["when_to_use"]) for s in user_level)
    entries = dict((s["name"], "name-only") for s in user_level)
    lines = ["unused for %d days: %d skills. name-only keeps them invocable by name and saves ~%s tokens a session." % (
        a.days, len(unused), k(est_tokens(save)))]
    if entries:
        lines.append("Claude Code (~/.claude/settings.json):")
        lines.append(json.dumps({"skillOverrides": entries}, indent=2))
    if plugin_level:
        by = {}
        for s in plugin_level:
            by.setdefault(s["plugin"], []).append(s["name"])
        lines.append("plugin skills are not affected by skillOverrides; disable the plugin per project in /plugin (enabledPlugins) if none of its skills is used:")
        for p, names in sorted(by.items()):
            lines.append("  %s: unused %s" % (p, ", ".join(names)))
    lines.append("Codex (~/.codex/config.toml), for the same skills if Codex loads them:")
    for s in user_level:
        lines.append('  [[skills.config]]' + NL + '  path = "%s"' % s["path"].replace("\\", "/") + NL + "  enabled = false")
    if a.write and entries:
        p = merge_skill_overrides(entries)
        lines.append("wrote skillOverrides into %s (backup under %s)" % (p, os.path.join(state_dir(), "backups")))
    elif entries:
        lines.append("dry run; pass --write to merge the Claude Code entries (a backup is kept)")
    out({"unused": [s["id"] for s in unused], "skillOverrides": entries, "save_tokens_est": est_tokens(save)}, a.json, lines)
    return 0


def cmd_startup(a):
    project = a.project or os.getcwd()
    chain = instruction_chain(project)
    mcp = mcp_settings(project)
    sk = listed(scan("claude", project))
    total = sum(x["tokens_est"] for x in chain)
    lines = ["always-loaded instructions: ~%s tokens in %d files" % (k(total), len(chain))]
    for x in sorted(chain, key=lambda x: -x["chars"]):
        lines.append("  ~%6s  %s%s" % (k(x["tokens_est"]), x["path"], ("  (via %s)" % x["via"]) if x["via"] else ""))
    lines.append("skill listing: ~%s tokens for %d skills (see `budget`, `usage`, `offload`)" % (
        k(est_tokens(sum(s["listed_chars"] for s in sk))), len(sk)))
    lines.append("MCP: %d servers; alwaysLoad (schemas loaded upfront): %s; ENABLE_TOOL_SEARCH=%s" % (
        len(mcp["servers"]), ", ".join(mcp["always_load"]) or "none", mcp["enable_tool_search"] or "default (on)"))
    if str(mcp["enable_tool_search"]).lower() == "false":
        lines.append("  tool search is off: every MCP tool schema loads at startup; unset it to defer them")
    out({"instructions": chain, "mcp": mcp, "skills_listed": len(sk)}, a.json, lines)
    return 0


def cmd_harvest(a):
    sk = listed(_catalog(a))
    s = _find(sk, a.name)
    if not s:
        print("no skill %s" % a.name)
        return 2
    trig = [t.lower() for t in triggers(s["desc"])]
    drop = _name_words(sk)
    mine = set(key_terms(s["desc"], 15)) - drop
    sessions = {}
    for sid, kind, name, text in claude_events(a.days):
        sessions.setdefault(sid, []).append((kind, name, text))
    missed, doubtful = [], []
    for sid, evs in sessions.items():
        for i, (kind, name, text) in enumerate(evs):
            if kind == "prompt":
                low = text.lower()
                hit = any(t in low for t in trig) or len(mine & set(tokens(low))) >= 3
                after = evs[i + 1:i + 6]
                used = any(k_ in ("skill", "command") and n.split(":")[-1] == s["name"] for k_, n, _ in after)
                if hit and not used:
                    missed.append(text[:240])
            elif kind == "skill" and name.split(":")[-1] == s["name"]:
                prev = next((t for k_, _, t in reversed(evs[:i]) if k_ == "prompt"), "")
                if prev and not (mine & set(tokens(prev.lower()))):
                    doubtful.append(prev[:240])
    near = pairs(sk, 0.3)
    sib = [p["b"] if p["a"] == s["id"] else p["a"] for p in near if s["id"] in (p["a"], p["b"])][:3]
    brief = [
        "# One-rewrite brief: %s" % s["id"], "",
        "Rewrite the description once (arXiv 2606.30775: one rewrite fed with false-positive and false-negative cases",
        "captures most of the gain; editing both sides of a confused pair adds under 0.5%). Rules: key use case first,",
        "what it does plus 'Use when', third person or imperative, at most 1,024 chars (about 100-200 words), no steering",
        "text, one short 'Not for X (that is Y)' boundary at the end if a sibling below is close. Keep every trigger's",
        "meaning. Then run: tidy.py check %s --new <file>" % s["path"], "",
        "## Current description (%d chars)" % len(s["desc"]), "", s["desc"], "",
        "## Closest skills", ""] + ["- %s: %s" % (x, next(y for y in sk if y["id"] == x)["desc"][:300]) for x in sib] + [
        "", "## Prompts that matched its triggers but did not invoke it (%d, heuristic)" % len(missed), ""] + [
        "- " + m.replace(NL, " ") for m in missed[:5]] + [
        "", "## Invocations whose prompt shares none of its key terms (%d, heuristic)" % len(doubtful), ""] + [
        "- " + m.replace(NL, " ") for m in doubtful[:5]]
    d = os.path.join(state_dir(), "briefs")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "%s.md" % s["name"])
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(NL.join(brief) + NL)
    print("brief written to %s (%d missed, %d doubtful, %d close skills)" % (p, len(missed), len(doubtful), len(sib)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tidy.py", description="Keep an agent's skill catalog cheap and unambiguous.")
    sp = ap.add_subparsers(dest="cmd")

    def common(p, agent=True):
        if agent:
            p.add_argument("--agent", default="claude", choices=AGENTS)
            p.add_argument("--project", help="project root (default: cwd)")
        p.add_argument("--json", action="store_true")
        p.add_argument("--threshold", type=float, default=0.45, help="similarity that counts as possibly confusable")
        return p

    common(sp.add_parser("scan", help="the catalog the agent loads")).set_defaults(fn=cmd_scan)
    p = common(sp.add_parser("lint", help="rule check of descriptions"))
    p.add_argument("skills", nargs="*")
    p.add_argument("--min", default="warn", choices=["info", "warn", "error"])
    p.set_defaults(fn=cmd_lint)
    common(sp.add_parser("conflicts", help="similar pairs with shared words and a boundary clause")).set_defaults(fn=cmd_conflicts)
    p = common(sp.add_parser("triggers", help="trigger phrases and key terms of one skill"))
    p.add_argument("skill")
    p.set_defaults(fn=cmd_triggers)
    for name, fn, h in (("check", cmd_check, "check a proposed description"), ("apply", cmd_apply, "write a checked description")):
        p = common(sp.add_parser(name, help=h))
        p.add_argument("skill")
        p.add_argument("--new", help="file holding the new description")
        p.add_argument("--desc", help="the new description text")
        if name == "apply":
            p.add_argument("--force", action="store_true")
        p.set_defaults(fn=fn)
    p = common(sp.add_parser("budget", help="listing size against each host's budget"))
    p.add_argument("--window", type=int, default=200000, help="model context window in tokens (default 200000)")
    p.set_defaults(fn=cmd_budget)
    p = common(sp.add_parser("usage", help="invocations per skill from transcripts"))
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(fn=cmd_usage)
    p = common(sp.add_parser("offload", help="never-used skills to name-only / off"))
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_offload)
    common(sp.add_parser("startup", help="always-loaded instructions, memory and MCP settings")).set_defaults(fn=cmd_startup)
    p = common(sp.add_parser("harvest", help="missed and doubtful invocations as a rewrite brief"))
    p.add_argument("name")
    p.add_argument("--days", type=int, default=60)
    p.set_defaults(fn=cmd_harvest)
    sp.add_parser("version").set_defaults(fn=lambda a: print(VERSION) or 0)
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 2
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
