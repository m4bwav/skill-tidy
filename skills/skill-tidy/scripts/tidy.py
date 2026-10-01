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
  python tidy.py sections  SKILL                                      body sections by size and kind; what could load on demand
  python tidy.py split     SKILL --section H --when TEXT [--to F]     move a section to references/, leave "Read F when TEXT."
  python tidy.py park      NAME [--scope user|project] [--soft] [--plugin P] [--group G]   park out of every scanned root
  python tidy.py unpark    NAME [--scope ...]                         put it back
  python tidy.py parked    [list|index|doctor|suggest|alias N P]  the parking lot and its index in the instruction files
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
import tempfile
import time

VERSION = "0.2.2"
HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
AGENTS = ["claude", "codex", "copilot", "cursor", "all"]


def home():
    return os.environ.get("SKILLTIDY_HOME") or os.path.expanduser("~")  # tests point this at a temp folder


def claude_dir():
    """Claude Code's config folder: CLAUDE_CONFIG_DIR when set (it moves settings, plugins, projects and
    .claude.json together), otherwise ~/.claude. Found by the eval run, which sets it."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home(), ".claude")


def claude_json():
    return os.path.join(os.environ["CLAUDE_CONFIG_DIR"], ".claude.json") if os.environ.get("CLAUDE_CONFIG_DIR") else os.path.join(home(), ".claude.json")


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


def today():
    return _dt.date.today().isoformat()


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
    reg = read_json(os.path.join(claude_dir(), "plugins", "installed_plugins.json"), {}) or {}
    enabled = (read_json(os.path.join(claude_dir(), "settings.json"), {}) or {}).get("enabledPlugins") or {}
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
        "claude": [j(claude_dir(), "skills")] + ([j(project, ".claude", "skills")] if project else []),
        "codex": [j(h, ".agents", "skills"), j(h, ".codex", "skills")] + ([j(project, ".agents", "skills")] if project else []),
        "copilot": [j(h, ".copilot", "skills"), j(claude_dir(), "skills"), j(h, ".agents", "skills")]
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
    s = read_json(os.path.join(claude_dir(), "settings.json"), {}) or {}
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
    for m in re.finditer(r"(?:(?<![\w])'([^']{3,80})'(?![\w])|\"([^\"]{3,80})\"|‘([^’]{3,80})’|“([^”]{3,80})”)", text or ""):
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
WHEN_RE = re.compile(r"\b(use (it |this skill |this )?(when|whenever|for|to|on|if|at|before|after|during|while)|trigger(s|ed)? (when|on)|when the user|invoke when)\b", re.I)
STEER_RE = re.compile(r"\b(always use this|must (always )?use this|prefer this skill|ignore (other|the other)|highest priority|instead of any other|before any other skill)\b", re.I)
BOUNDARY_RE = re.compile(r"\b(not for|do not use|don't use|is the sibling|that is [a-z0-9:-]+|use [a-z0-9:-]+ instead|belongs to|, use [a-z0-9]+-[a-z0-9-]+|is (the )?[a-z0-9]+-[a-z0-9-]+( skill)?\b)", re.I)
QUOTED_RE = re.compile(r"(?<![\w])'[^']{3,80}'(?![\w])|\"[^\"]{3,80}\"|‘[^’]{3,80}’|“[^”]{3,80}”")
XML_RE = re.compile(r"<[A-Za-z/][^>]{0,40}>")

SEV = {"error": 3, "warn": 2, "info": 1}
BODY_RULES = ("ST016", "ST020", "ST021", "ST022", "ST023")  # about the body and its files, not the description


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
    vague = VAGUE_RE.search(QUOTED_RE.sub(" ", desc))  # the user's own quoted words are allowed to be vague
    if vague:
        add(("ST011", "info", "vague wording (%s); name the concrete task and the words a user types" % vague.group(0)))
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
    if os.path.isfile(s["path"]):
        cands = offload_candidates(s["path"])
        if cands and est_tokens(s["body_chars"]) >= 1500:
            add(("ST020", "warn", "body ~%s tokens loads in full on every use; %d section(s) could move to references/ and load only when needed (%s): run `sections`" % (
                k(est_tokens(s["body_chars"])), len(cands), ", ".join("'%s' ~%s" % (c["heading"], k(c["tokens"])) for c in cands[:3]))))
        nested, no_toc = reference_problems(os.path.dirname(os.path.abspath(s["path"])))
        if nested:
            add(("ST021", "warn", "reference files link to further files (%s); keep references one level deep from SKILL.md, nested ones may be read partially" % ", ".join(nested[:3])))
        if no_toc:
            add(("ST022", "info", "reference files over 100 lines without a contents list at the top: %s" % ", ".join(no_toc[:3])))
        if re.search(r"(?<![\\\w])(scripts|references|reference|assets)\\[\w.-]+", read_text(s["path"])):
            add(("ST023", "warn", "backslash path in SKILL.md; use forward slashes (they work on every OS)"))
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


# ----------------------------------------------------------------------------- body: progressive disclosure
# Anthropic's authoring guide: SKILL.md is an overview that points to reference files read only when needed
# (no context cost until read), body under 500 lines, references one level deep, a table of contents in any
# reference file over 100 lines. SkillReducer (arXiv 2603.29919): over 60% of body text is non-actionable;
# moving supplementary material into on-demand files cut bodies 39% and raised quality 2.8%.

SUPPLEMENTARY_RE = re.compile(r"\b(examples?|samples?|templates?|reference|appendix|background|troubleshoot\w*|faq|notes?|"
                              r"per[- ](agent|host|platform|tool)|platforms?|tables?|glossary|schemas?|api|options|flags|"
                              r"history|details?|advanced|gotchas|caveats|edge cases|variants?|catalog|list of)\b", re.I)
CORE_RE = re.compile(r"\b(step \d|steps|workflow|procedure|quick ?start|rules?|when to|how to use|usage|report|"
                     r"important|safety|never|always|do not|overview|checklist)\b", re.I)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)(#[^)]*)?\)")


def body_of(path):
    """(front matter lines, body lines) of a SKILL.md, split at the closing ---."""
    lines = read_text(path).splitlines()
    if lines and lines[0].lstrip("﻿").strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end:
            return lines[:end + 1], lines[end + 1:]
    return [], lines


def sections(body_lines):
    """Markdown sections by heading (## and deeper; # is the title), ignoring headings inside code fences.
    Each: heading, level, start/end line in the body, chars, tokens, kind (core | supplementary | mixed), why."""
    heads, fence = [], False
    for i, ln in enumerate(body_lines):
        if FENCE_RE.match(ln):
            fence = not fence
            continue
        m = re.match(r"^(#{2,6})\s+(.*\S)\s*$", ln) if not fence else None
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    out = []
    for n, (i, lvl, title) in enumerate(heads):
        end = next((j for j, l2, _ in heads[n + 1:] if l2 <= lvl), len(body_lines))
        chunk = body_lines[i:end]
        text = NL.join(chunk)
        code = 0
        fence = False
        for ln in chunk:
            if FENCE_RE.match(ln):
                fence = not fence
                code += 1
            elif fence:
                code += 1
        table = sum(1 for ln in chunk if ln.strip().startswith("|"))
        why = []
        if SUPPLEMENTARY_RE.search(title):
            why.append("heading names reference material")
        if code >= max(6, len(chunk) * 0.4):
            why.append("mostly code")
        if table >= 8:
            why.append("a %d-row table" % table)
        core = bool(CORE_RE.search(title))
        kind = "core" if core and not why else ("supplementary" if why and not core else ("mixed" if why else "core"))
        out.append({"heading": title, "level": lvl, "start": i, "end": end, "lines": len(chunk),
                    "chars": len(text), "tokens": est_tokens(len(text)), "kind": kind, "why": why})
    return out


def offload_candidates(path, min_tokens=250, big=1000):
    """Top-level sections worth moving to references/: supplementary ones of min_tokens or more, and any
    section of `big` tokens or more (split by subtopic). The steps the model must always follow stay."""
    _, body = body_of(path)
    secs = sections(body)
    top = min([s["level"] for s in secs] or [2])
    out = []
    for s in secs:
        if s["level"] != top:
            continue
        if (s["kind"] == "supplementary" and s["tokens"] >= min_tokens) or (s["kind"] != "core" and s["tokens"] >= big):
            out.append(dict(s, reason="; ".join(s["why"]) or "large"))
        elif s["kind"] == "core" and s["tokens"] >= big * 1.5:
            out.append(dict(s, reason="large core section: move sub-parts that only some tasks need"))
    return out


def reference_problems(skill_dir):
    """Reference files that link on to other markdown in the skill (Claude may read nested files partially)
    and reference files over 100 lines with no contents list near the top."""
    nested, no_toc = [], []
    top = ("SKILL.MD", "RESEARCH.MD", "CHANGELOG.MD", "LEARNINGS.MD", "TESTS.MD", "MAINTENANCE.MD", "README.MD", "TESTS-ARCHIVE.MD")
    for f in glob.glob(os.path.join(skill_dir, "**", "*.md"), recursive=True):
        base = os.path.basename(f).upper()
        if base in top or os.sep + "evals" + os.sep in f:
            continue
        t = read_text(f)
        rel = os.path.relpath(f, skill_dir).replace(os.sep, "/")
        for m in LINK_RE.finditer(t):
            target = os.path.normpath(os.path.join(os.path.dirname(f), m.group(1)))
            if os.path.isfile(target) and os.path.basename(target).upper() not in top and _norm_dir(target).startswith(_norm_dir(skill_dir)):
                nested.append(rel)
                break
        lines = t.splitlines()
        if len(lines) > 100 and not re.search(r"(?im)^#{1,3}\s*(contents|table of contents|toc)\b", NL.join(lines[:40])):
            no_toc.append(rel)
    return sorted(set(nested)), sorted(no_toc)


def slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:48] or "section"


def split_section(path, heading, to_rel, when):
    """Move one section (the heading line kept in SKILL.md) into to_rel under the skill folder and leave a
    pointer: '<heading>: read <link> when <when>.' Appends when the target exists; adds a contents list when
    the target passes 100 lines. Backs SKILL.md up first. Returns (target path, backup path)."""
    raw = open(path, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    fm, body = body_of(path)
    secs = [s for s in sections(body) if s["heading"].strip().lower() == heading.strip().lower()]
    if not secs:
        raise ValueError("no section headed '%s'" % heading)
    s = secs[0]
    if to_rel.startswith("/") or ".." in to_rel.replace("\\", "/").split("/"):
        raise ValueError("--to must be a relative path inside the skill folder")
    to_rel = to_rel.replace("\\", "/")
    skill_dir = os.path.dirname(os.path.abspath(path))
    target = os.path.join(skill_dir, *to_rel.split("/"))
    moved = body[s["start"] + 1:s["end"]]
    while moved and not moved[-1].strip():
        moved.pop()
    head_line = body[s["start"]]
    # sub-headings move up so the section title becomes the file's title (### under ## becomes ##)
    shifted = [ln[s["level"] - 1:] if re.match(r"^#{%d,6}\s" % (s["level"] + 1), ln) else ln for ln in moved]
    os.makedirs(os.path.dirname(target), exist_ok=True)
    existing = read_text(target) if os.path.exists(target) else ""
    if existing:  # appended as one more ## section
        content = existing.rstrip("\n") + "\n\n## " + s["heading"] + "\n\n" + NL.join(shifted)
    else:
        content = "# " + s["heading"] + "\n\n" + NL.join(shifted)
    lines = content.splitlines()
    if len(lines) > 100 and not re.search(r"(?im)^#{1,3}\s*contents\b", NL.join(lines[:40])):
        subs = [re.sub(r"^#+\s*", "", ln) for ln in lines[1:] if re.match(r"^##\s", ln)]
        if subs:
            lines = lines[:1] + ["", "## Contents", ""] + ["- " + x for x in subs] + lines[1:]
    bdir = os.path.join(state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(bdir, exist_ok=True)
    backup = os.path.join(bdir, os.path.basename(skill_dir) + ".SKILL.md")
    shutil.copy2(path, backup)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(NL.join(lines).rstrip("\n") + "\n")
    pointer = "Read [%s](%s) when %s." % (to_rel, to_rel, when.strip().rstrip("."))
    new_body = body[:s["start"]] + [head_line, "", pointer, ""] + body[s["end"]:]
    out = NL.join(fm + new_body).rstrip("\n") + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(out.encode("utf-8"))
    return target, backup


# ----------------------------------------------------------------------------- parking lot
# Parked skills leave every folder a host scans (so they cost no listing tokens and do not compete for
# selection) and stay findable through a short index written INTO the instruction files the agent always
# reads. Inline, not a pointer: Vercel's evals (2026-01-27) had an 8 KB index in AGENTS.md at 100% while
# skills the agent had to decide to invoke sat at 53-79%, never invoked in 56% of cases; Claude Code
# re-injects the project CLAUDE.md after compaction but not the skill listing. Groups of at most 8 follow
# the hierarchical-routing result (arXiv 2601.04748: 4-8 items per level). Research: RESEARCH.md R-20260926-4.

PARK_DIRNAME = "parked-skills"
MARK_START = "<!-- skill-tidy:parked:start -->"
MARK_END = "<!-- skill-tidy:parked:end -->"
FEATURE_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}|\$\{CLAUDE_PLUGIN_ROOT\}|^!`|^\s*(allowed-tools|hooks|context):", re.M)


def features(text):
    """Skill features a plain file read does not provide (substitution, ! injection, pre-approved tools,
    hooks, a forked context): such a skill must be unparked to work fully."""
    return sorted(set(m.group(0).strip().rstrip(":").lstrip("!`") or "!` injection" for m in FEATURE_RE.finditer(text or "")))


def park_dir(scope, project=None):
    if scope == "project":
        if not project:
            raise ValueError("project scope needs --project or a working directory")
        return os.path.join(project, ".agents", PARK_DIRNAME)
    return os.path.join(home(), ".agents", PARK_DIRNAME)


def manifest_path(scope, project=None):
    return os.path.join(park_dir(scope, project), "parked.json")


def load_manifest(scope, project=None):
    m = read_json(manifest_path(scope, project), {}) or {}
    return m if isinstance(m, dict) else {}


def save_manifest(scope, project, m):
    p = manifest_path(scope, project)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(m, fh, indent=2, sort_keys=True)
        fh.write("\n")


def is_link(p):
    """A symlink or a Windows directory junction: removing it must never touch the target."""
    try:
        if os.path.islink(p):
            return True
        isj = getattr(os.path, "isjunction", None)  # Python 3.12+
        if isj is not None:
            return isj(p)
        # Older Pythons: the entry is a link when it resolves somewhere other than inside its own resolved
        # parent. Comparing against abspath instead misfires wherever a parent is a link (/var on macOS) or
        # a path uses 8.3 short names (Windows runners).
        p = os.path.abspath(p)
        here = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
        return os.path.isdir(p) and _norm_dir(os.path.realpath(p)) != _norm_dir(here)
    except OSError:
        return False


def make_link(target, link):
    if os.name == "nt":
        try:
            import _winapi
            _winapi.CreateJunction(os.path.abspath(target), os.path.abspath(link))
            return
        except (ImportError, OSError, AttributeError):
            pass
    os.symlink(os.path.abspath(target), link, target_is_directory=True)


def remove_link(p):
    try:
        os.unlink(p)
    except OSError:
        os.rmdir(p)  # a junction is removed as an empty directory; its target is untouched


def link_roots(project=None):
    """Every folder a host may keep skill links in: the roots of all hosts plus the Codex, Copilot and Cursor
    folders and their project equivalents. Aliases (other links to a parked folder) are looked for here."""
    h = home()
    j = os.path.join
    dirs = [os.path.dirname(os.path.dirname(g)) for _, p, g in roots_for("all", project) if not p]
    dirs += [j(h, ".agents", "skills"), j(h, ".codex", "skills"), j(h, ".copilot", "skills"), j(h, ".cursor", "skills")]
    if project:
        dirs += [j(project, d, "skills") for d in (".claude", ".agents", ".codex", ".copilot", ".github", ".cursor")]
    out, seen = [], set()
    for d in dirs:
        if _norm_dir(d) not in seen:
            seen.add(_norm_dir(d))
            out.append(d)
    return out


def _entries(project=None):
    for r in link_roots(project):
        try:
            names = sorted(os.listdir(r))
        except OSError:
            continue
        for n in names:
            yield os.path.join(r, n)


def find_aliases(target, project=None, exclude=()):
    """Links in any skill root whose resolved target is `target`."""
    want = _norm_dir(os.path.realpath(target))
    skip = {_norm_dir(x) for x in exclude}
    return [p for p in _entries(project)
            if _norm_dir(p) not in skip and is_link(p) and _norm_dir(os.path.realpath(p)) == want]


def dangling_links(project=None, lot=None):
    """Links in any skill root that point at a missing folder or into the parking lot."""
    lot_n = _norm_dir(lot) if lot else None
    out = []
    for p in _entries(project):
        if not os.path.exists(p):  # a broken symlink or junction: listed, but nothing behind it
            out.append((p, "points at a missing folder"))
            continue
        if not is_link(p):
            continue
        real = os.path.realpath(p)
        if not os.path.isdir(real):
            out.append((p, "points at a missing folder"))
        elif lot_n and _norm_dir(real).startswith(lot_n + os.sep):
            out.append((p, "points into the parking lot"))
    return out


def index_line(name, desc, max_len=150):
    """One routing line: the description's first sentence, which the rules ask to carry the key use case and
    its trigger words (ST014), with bracketed asides dropped and cut at a word boundary. The 'Use when' clause
    is a poorer source: once its quoted examples are removed little is left."""
    d = re.sub(r"\s+", " ", desc or "").strip()
    text = re.split(r"(?<=[.!?])\s", d, maxsplit=1)[0]
    text = re.sub(r"\s*\([^()]*\)", "", text)
    text = re.sub(r"\s*,\s*(,\s*)+", ", ", text).strip(" ,;.")
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,;") + "..."
    return text


def group_for(name, explicit=None):
    if explicit:
        return explicit
    return re.split(r"[-_:]", name.lower())[0]


def park(name, scope="user", project=None, group=None, line=None, soft=False, skills=None):
    """Move one skill out of the scanned roots (or, for a link, remove only the link) and record it.
    soft: Claude Code only, set skillOverrides "off" and leave the folder where it is. Returns the entry."""
    sk = skills if skills is not None else scan("all", project)
    s = next((x for x in sk if name in (x["id"], x["name"])), None)
    if not s:
        raise ValueError("no skill named %s in any scanned root" % name)
    if s["plugin"]:
        raise ValueError("%s belongs to plugin %s: plugin skills live in a versioned cache and are never moved; "
                         "use `park --plugin %s` to disable the plugin and index its skills" % (s["id"], s["plugin"], s["plugin"]))
    src = os.path.dirname(os.path.abspath(s["path"]))
    m = load_manifest(scope, project)
    if s["name"] in m:
        raise ValueError("%s is already parked" % s["name"])
    body = read_text(s["path"])
    entry = {"name": s["name"], "origin": src, "parked": today(), "group": group_for(s["name"], group),
             "line": line or index_line(s["name"], s["desc"]), "features": features(body),
             "mode": "soft" if soft else "move"}
    if soft:
        merge_skill_overrides({s["name"]: "off"})
        entry["path"] = src
    elif is_link(src):
        entry.update({"mode": "link", "path": os.path.realpath(src)})
        entry["aliases"] = find_aliases(entry["path"], project, exclude=[src])
        for al in entry["aliases"]:
            remove_link(al)
        remove_link(src)
    else:
        dest = os.path.join(park_dir(scope, project), s["name"])
        if os.path.exists(dest):
            raise ValueError("%s already exists in the parking lot" % dest)
        aliases = find_aliases(src, project, exclude=[src])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        for al in aliases:
            remove_link(al)  # other hosts' links to this folder would dangle once it moves
        shutil.move(src, dest)
        entry["path"] = dest
        entry["aliases"] = aliases
    m[s["name"]] = entry
    save_manifest(scope, project, m)
    return entry


def park_plugin(plugin, scope="user", project=None, group=None):
    """Disable a Claude Code plugin in the user settings (with a backup) and index its skills by their
    current install path; `parked doctor` re-resolves the path when the plugin updates."""
    roots = [(p, g) for p, g in claude_plugin_roots(project) if p == plugin]
    if not roots:
        raise ValueError("no installed, enabled plugin named %s" % plugin)
    reg = read_json(os.path.join(claude_dir(), "plugins", "installed_plugins.json"), {}) or {}
    key = next((k_ for k_ in (reg.get("plugins") or {}) if k_.split("@")[0] == plugin), plugin)
    p = os.path.join(claude_dir(), "settings.json")
    cur = read_json(p, {}) or {}
    bdir = os.path.join(state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(bdir, exist_ok=True)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(bdir, "settings.json"))
    ep = cur.get("enabledPlugins") if isinstance(cur.get("enabledPlugins"), dict) else {}
    ep[key] = False
    cur["enabledPlugins"] = ep
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=2)
        fh.write("\n")
    m = load_manifest(scope, project)
    added = []
    for _, g in roots:
        for f in sorted(glob.glob(g)):
            s = parse_skill(f)
            nm = "%s:%s" % (plugin, s["name"])
            m[nm] = {"name": nm, "origin": "plugin:" + key, "parked": today(), "group": group or plugin, "mode": "plugin",
                     "line": index_line(s["name"], s["desc"]), "path": os.path.dirname(os.path.abspath(f)),
                     "features": features(read_text(f))}
            added.append(nm)
    save_manifest(scope, project, m)
    return key, added


def unpark(name, scope="user", project=None):
    m = load_manifest(scope, project)
    e = m.get(name)
    if not e:
        raise ValueError("%s is not parked (%s)" % (name, manifest_path(scope, project)))
    if e["mode"] == "soft":
        p = os.path.join(claude_dir(), "settings.json")
        cur = read_json(p, {}) or {}
        (cur.get("skillOverrides") or {}).pop(e["name"], None)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, indent=2)
            fh.write("\n")
    elif e["mode"] == "plugin":
        key = e["origin"].split(":", 1)[1]
        p = os.path.join(claude_dir(), "settings.json")
        cur = read_json(p, {}) or {}
        (cur.get("enabledPlugins") or {})[key] = True
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, indent=2)
            fh.write("\n")
        for k_ in [k_ for k_, v in m.items() if v.get("origin") == e["origin"]]:
            m.pop(k_)
        save_manifest(scope, project, m)
        return e
    elif os.path.exists(e["origin"]):
        raise ValueError("%s exists again; move or remove it first" % e["origin"])
    elif e["mode"] == "link":
        os.makedirs(os.path.dirname(e["origin"]), exist_ok=True)
        make_link(e["path"], e["origin"])
    else:
        os.makedirs(os.path.dirname(e["origin"]), exist_ok=True)
        shutil.move(e["path"], e["origin"])
    if e["mode"] in ("move", "link"):
        for al in e.get("aliases") or []:
            if os.path.lexists(al) or is_link(al):
                continue
            os.makedirs(os.path.dirname(al), exist_ok=True)
            make_link(e["origin"], al)
    m.pop(name)
    save_manifest(scope, project, m)
    return e


def render_index(m, tidy_cmd, inline_max=40):
    """(full index text, block to write into instruction files). The block is the full index up to
    inline_max lines, otherwise one line per group with the index file's path."""
    groups = {}
    for nm, e in sorted(m.items()):
        groups.setdefault(e.get("group") or "general", []).append(e)
    head = [
        "## Parked skills",
        "",
        "Installed but not listed, to save context. When a task matches a line, read that SKILL.md in full before acting and follow it. "
        "Its folder is the skill's base directory: resolve `${CLAUDE_SKILL_DIR}` and relative `scripts/` paths against it and run scripts by absolute path. "
        "Lines marked (unpark) need skill features a plain read cannot give: run `%s unpark <name>` first. To use one often, unpark it." % tidy_cmd,
        "",
    ]
    body = []
    for g in sorted(groups):
        body.append("### %s" % g)
        for e in groups[g]:
            flag = " (unpark)" if e.get("features") else ""
            body.append("- `%s`%s: %s. `%s/SKILL.md`" % (e["name"], flag, e["line"].rstrip("."), e["path"].replace("\\", "/")))
        body.append("")
    full = NL.join(head + body).rstrip() + NL
    if len(body) <= inline_max:
        block = full
    else:
        summary = ["### %s (%d): %s" % (g, len(groups[g]), ", ".join("`%s`" % e["name"] for e in groups[g][:8])) for g in sorted(groups)]
        block = NL.join(head[:2] + [head[2] + " The full index with every line and path is `%s`; read it when no active skill fits." % "{INDEX}", ""] + summary) + NL
    big = [g for g in groups if len(groups[g]) > 8]
    return full, block, big


def write_block(path, block):
    """Replace or append the marked block in an instruction file, keeping every other byte and the line
    endings. An empty block removes it. Backs the file up first."""
    raw = open(path, "rb").read().decode("utf-8") if os.path.exists(path) else ""
    crlf = "\r\n" in raw
    t = raw.replace("\r\n", "\n")
    new = (MARK_START + "\n" + block.rstrip("\n") + "\n" + MARK_END + "\n") if block else ""
    if MARK_START in t and MARK_END in t:
        a, rest = t.split(MARK_START, 1)
        _, b = rest.split(MARK_END, 1)
        t = a + new + b.lstrip("\n") if new else (a.rstrip("\n") + "\n" + b.lstrip("\n"))
    elif new:
        t = (t.rstrip("\n") + "\n\n" if t.strip() else "") + new
    if raw:
        bdir = os.path.join(state_dir(), "backups", time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(path, os.path.join(bdir, re.sub(r"[^A-Za-z0-9.]", "_", os.path.abspath(path))[-80:]))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if crlf:
        t = t.replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(t.encode("utf-8"))


def link_targets(scope, project=None, hosts=("claude", "codex")):
    """Instruction files every session of each host reads. User: ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md (when
    Codex is set up). Project: AGENTS.md when it exists (Codex, Copilot, Cursor; Claude through an @AGENTS.md
    import), and CLAUDE.md when it exists and does not import AGENTS.md."""
    out = []
    if scope == "user":
        if "claude" in hosts:
            out.append(os.path.join(claude_dir(), "CLAUDE.md"))
        if "codex" in hosts and os.path.isdir(os.path.join(home(), ".codex")):
            out.append(os.path.join(home(), ".codex", "AGENTS.md"))
        return out
    agents = os.path.join(project, "AGENTS.md")
    claude = os.path.join(project, "CLAUDE.md")
    if os.path.exists(agents):
        out.append(agents)
    if os.path.exists(claude) and not re.search(r"(?m)^\s*@AGENTS\.md", read_text(claude)):
        out.append(claude)
    return out or [agents]


def reindex(scope, project=None, hosts=("claude", "codex")):
    m = load_manifest(scope, project)
    tidy_cmd = "python %s" % os.path.abspath(__file__).replace("\\", "/")
    full, block, big = render_index(m, tidy_cmd)
    d = park_dir(scope, project)
    os.makedirs(d, exist_ok=True)
    idx = os.path.join(d, "PARKED.md")
    with open(idx, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(full)
    block = block.replace("{INDEX}", idx.replace("\\", "/")) if m else ""
    targets = link_targets(scope, project, hosts)
    for t in targets:
        write_block(t, block)
    return idx, targets, est_tokens(len(block)), big


def parked_doctor(scope, project=None):
    """Problems: parked folders under a scanned root, index paths that no longer exist (plugin updates move
    them: re-resolved here), a parked name that is also active, skill features a plain read loses."""
    m = load_manifest(scope, project)
    probs = []
    active = {s["name"] for s in scan("all", project)}
    roots = [_norm_dir(os.path.dirname(os.path.dirname(g))) for _, _, g in roots_for("all", project)]
    for nm, e in sorted(m.items()):
        p = e.get("path", "")
        if e["mode"] == "move" and any(_norm_dir(p).startswith(r + os.sep) for r in roots):
            probs.append("%s: parked folder %s is inside a scanned skills root" % (nm, p))
        if not os.path.isfile(os.path.join(p, "SKILL.md")):
            if e["mode"] == "plugin":
                plugin = nm.split(":")[0]
                new = [g for pl, g in claude_plugin_roots(project) if pl == plugin]
                probs.append("%s: plugin path moved (update?); `parked index` after re-parking the plugin" % nm if not new else "%s: path gone" % nm)
            else:
                probs.append("%s: %s/SKILL.md is missing" % (nm, p))
        if e["mode"] in ("move", "link") and nm in active:
            probs.append("%s: also active in a scanned root (duplicate)" % nm)
        if e.get("features"):
            probs.append("%s: uses %s; the index marks it (unpark)" % (nm, ", ".join(e["features"])))
    for p, why in dangling_links(project, park_dir(scope, project)):
        probs.append("dangling link %s %s; remove it, or record it with `parked alias NAME %s` and remove it" % (p, why, p))
    return probs


def add_alias(name, path, scope="user", project=None):
    """Record an alias link path on a parked entry so unpark recreates it (for skills parked before aliases
    were recorded, whose links were removed by hand)."""
    m = load_manifest(scope, project)
    e = m.get(name)
    if not e:
        raise ValueError("%s is not parked (%s)" % (name, manifest_path(scope, project)))
    if e["mode"] not in ("move", "link"):
        raise ValueError("%s is a %s entry; aliases apply to moved or linked skills" % (name, e["mode"]))
    path = os.path.abspath(path)
    if _norm_dir(path) == _norm_dir(e["origin"]):
        raise ValueError("%s is the origin itself" % path)
    al = e.setdefault("aliases", [])
    if _norm_dir(path) not in {_norm_dir(x) for x in al}:
        al.append(path)
    save_manifest(scope, project, m)
    return e


def cmd_park(a):
    project = a.project or os.getcwd()
    try:
        if a.plugin:
            key, added = park_plugin(a.plugin, a.scope, project, a.group)
            print("disabled plugin %s in %s (backup kept) and parked %d skills: %s" % (key, os.path.join(claude_dir(), "settings.json"), len(added), ", ".join(added)))
        else:
            if not a.name:
                print("give a skill name, or --plugin NAME")
                return 2
            e = park(a.name, a.scope, project, a.group, a.line, a.soft)
            print("parked %s (%s) -> %s%s" % (e["name"], e["mode"], e["path"], ("; uses %s, marked (unpark) in the index" % ", ".join(e["features"])) if e["features"] else ""))
    except ValueError as ex:
        print("refused: %s" % ex)
        return 1
    idx, targets, toks, big = reindex(a.scope, project)
    print("index %s (~%s tokens in %s)" % (idx, k(toks), ", ".join(targets)))
    if big:
        print("groups over 8 skills (split them with --group): %s" % ", ".join(big))
    return 0


def cmd_unpark(a):
    project = a.project or os.getcwd()
    try:
        e = unpark(a.name, a.scope, project)
    except ValueError as ex:
        print("refused: %s" % ex)
        return 1
    idx, targets, toks, _ = reindex(a.scope, project)
    print("unparked %s -> %s (Claude Code picks it up live; Codex needs a restart); index ~%s tokens" % (a.name, e["origin"], k(toks)))
    return 0


def cmd_parked(a):
    project = a.project or os.getcwd()
    m = load_manifest(a.scope, project)
    if a.action == "index":
        idx, targets, toks, big = reindex(a.scope, project)
        out({"index": idx, "targets": targets, "block_tokens": toks, "big_groups": big}, a.json,
            ["index %s, block ~%s tokens written to %s" % (idx, k(toks), ", ".join(targets))] + (["groups over 8: " + ", ".join(big)] if big else []))
    elif a.action == "doctor":
        probs = parked_doctor(a.scope, project)
        out(probs, a.json, ["%d parked, %d notes" % (len(m), len(probs))] + ["  " + p for p in probs])
    elif a.action == "alias":
        if len(a.args) != 2:
            print("usage: parked alias NAME PATH")
            return 2
        try:
            e = add_alias(a.args[0], a.args[1], a.scope, project)
        except ValueError as ex:
            print("refused: %s" % ex)
            return 1
        print("%s aliases: %s (unpark recreates them as links to %s)" % (e["name"], ", ".join(e["aliases"]), e["origin"]))
    elif a.action == "suggest":
        c = usage(a.days)
        sk = [s for s in listed(scan("claude", project)) if c.get(s["name"], 0) == 0 and s["name"] not in m]
        sk.sort(key=lambda s: -s["listed_chars"])
        lines = ["never used in %d days, largest listing cost first (park with `park <name>`; plugins with `park --plugin <plugin>`):" % a.days]
        for s in sk:
            lines.append("  %5d chars  %s%s" % (s["listed_chars"], s["id"], "  (plugin)" if s["plugin"] else ""))
        out([{"id": s["id"], "chars": s["listed_chars"], "plugin": s["plugin"]} for s in sk], a.json, lines)
    else:
        lines = ["%d parked (%s): %s" % (len(m), a.scope, manifest_path(a.scope, project))]
        for nm, e in sorted(m.items()):
            lines.append("  %-36s %-6s %s" % (nm, e["mode"], e["path"]))
            for al in e.get("aliases") or []:
                lines.append("  %-36s %-6s %s" % ("", "alias", al))
        out(m, a.json, lines)
    return 0


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


def headless_session(lines):
    """True for a `claude -p` or SDK session (an eval, a script), not a person's: an `sdk` entrypoint, or a working
    folder under the temp directory. A -p child started from an IDE session logs the IDE's entrypoint, so the folder
    is the reliable sign (2026-09-30: eval suites run from VS Code were logged as claude-vscode)."""
    entry = cwd = None
    for line in lines[:80]:
        if entry is None:
            m = re.search(r'"entrypoint"\s*:\s*"([^"]+)"', line)
            entry = m.group(1) if m else None
        if cwd is None:
            m = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', line)
            if m:
                try:
                    cwd = json.loads('"%s"' % m.group(1))
                except ValueError:
                    cwd = None
        if entry and cwd:
            break
    if str(entry or "").startswith("sdk"):
        return True
    if not cwd:
        return False
    c = os.path.normcase(os.path.abspath(cwd))
    roots = {tempfile.gettempdir(), os.environ.get("TEMP") or "", os.environ.get("TMP") or "", "/tmp", "/var/folders"}
    return any(r and c.startswith(os.path.normcase(os.path.abspath(r))) for r in roots)


def claude_events(days, headless=False):
    """Yield (session, kind, value, text) from Claude Code transcripts: ('prompt', None, text),
    ('skill', name, None) for a Skill tool call, ('command', name, None) for a typed slash command.
    Headless sessions (evals, scripts) are skipped unless headless=True, which yields only those: a test run is not
    a use. The JSONL format is internal and unstable; unknown lines are skipped."""
    for f in _recent(os.path.join(claude_dir(), "projects", "**", "*.jsonl"), days):
        sid = os.path.basename(f)
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        if headless_session(lines) != headless:
            continue
        for line in lines:
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


def usage(days, headless=False):
    """Invocations per skill. Headless Claude Code sessions (evals, scripts) are left out; headless=True counts only
    them, so a report can show test traffic beside real use."""
    counts = {}
    events = list(claude_events(days, headless=headless)) + ([] if headless else list(codex_events(days)))
    for _, kind, name, _ in events:
        if kind in ("skill", "command"):
            key = name.split(":")[-1]
            counts[key] = counts.get(key, 0) + 1
    return counts


# ----------------------------------------------------------------------------- startup chain

IMPORT_RE = re.compile(r"(?m)^\s*@([^\s]+)")


def instruction_chain(project):
    """Instruction files Claude Code loads at startup, following @imports (depth 5), with sizes."""
    h = home()
    starts = [os.path.join(claude_dir(), "CLAUDE.md")]
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
        mem = os.path.join(claude_dir(), "projects", slug, "memory", "MEMORY.md")
        if os.path.isfile(mem):
            t = read_text(mem)
            first = NL.join(t.splitlines()[:200])[:25000]
            out.append({"path": mem, "chars": len(first), "tokens_est": est_tokens(len(first)), "via": "auto-memory (first 200 lines / 25KB)"})
    return out


def mcp_settings(project):
    h = home()
    cfg = read_json(claude_json(), {}) or {}
    servers = dict(cfg.get("mcpServers") or {})
    if project:
        servers.update((read_json(os.path.join(project, ".mcp.json"), {}) or {}).get("mcpServers") or {})
        pc = (cfg.get("projects") or {}).get(os.path.abspath(project).replace(os.sep, "/")) or {}
        servers.update(pc.get("mcpServers") or {})
    settings = read_json(os.path.join(claude_dir(), "settings.json"), {}) or {}
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
    p = os.path.join(claude_dir(), "settings.json")
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
    for s in skills:  # a catalog name wins over a same-named folder in the working directory
        if target in (s["id"], s["name"]):
            return s
    p = target if target.endswith("SKILL.md") else os.path.join(target, "SKILL.md")
    if os.path.isfile(p):
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
    expanded = []
    for t in a.skills or []:
        if os.path.isdir(t) and not os.path.isfile(os.path.join(t, "SKILL.md")):
            found = sorted(glob.glob(os.path.join(t, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(t, ".claude", "skills", "*", "SKILL.md")))
            expanded += [os.path.dirname(f) for f in found] or [t]
        else:
            expanded.append(t)
    targets = [_find(sk, t) for t in expanded] if a.skills else cat
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
    findings = [f for f in findings if f[0] not in BODY_RULES]
    sim_ok = after[0] < threshold or after[0] <= before[0]
    return {"findings": [{"rule": r, "severity": v, "message": m} for r, v, m in findings], "lost_triggers": lost,
            "dropped_terms": dropped, "chars_before": len(s["desc"]), "chars_after": len(new),
            "max_similarity_before": {"score": before[0], "with": before[1]},
            "max_similarity_after": {"score": after[0], "with": after[1]},
            "similarity_ok": sim_ok,
            "ok": not any(v == "error" for _, v, _ in findings) and not lost and sim_ok}


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
    if not r["similarity_ok"]:
        lines.append("  SIM   the closest skill is now at or above %.2f and higher than before" % a.threshold)
    lines.append("OK: safe to apply" if r["ok"] else "NOT OK: fix the errors, lost triggers or similarity first (or apply --force)")
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


def cmd_sections(a):
    sk = _catalog(a)
    s = _find(sk, a.skill)
    if not s:
        print("no skill %s" % a.skill)
        return 2
    _, body = body_of(s["path"])
    secs = sections(body)
    cands = {c["heading"] for c in offload_candidates(s["path"], a.min_tokens)}
    nested, no_toc = reference_problems(os.path.dirname(os.path.abspath(s["path"])))
    total = est_tokens(len(NL.join(body)))
    lines = ["%s: body %d lines, ~%s tokens loaded on every use" % (s["id"], len(body), k(total))]
    for x in secs:
        mark = "  -> move to references/%s.md" % slug(x["heading"]) if x["heading"] in cands else ""
        lines.append("  %s%-40s %5d lines ~%6s  %-13s %s%s" % ("  " * (x["level"] - 2), x["heading"][:40], x["lines"], k(x["tokens"]), x["kind"], ", ".join(x["why"]), mark))
    saved = sum(x["tokens"] for x in secs if x["heading"] in cands)
    if cands:
        lines.append("moving the %d marked section(s) keeps ~%s tokens out of every use; each leaves one 'Read <file> when <condition>.' line" % (len(cands), k(saved)))
        lines.append("then: tidy.py split %s --section \"<heading>\" --to references/<file>.md --when \"<the tasks that need it>\"" % s["path"].replace("\\", "/"))
    if nested:
        lines.append("nested references (keep one level deep): " + ", ".join(nested))
    if no_toc:
        lines.append("add a contents list to: " + ", ".join(no_toc))
    out({"id": s["id"], "body_tokens": total, "sections": secs, "offload": sorted(cands), "offload_tokens": saved,
         "nested": nested, "no_toc": no_toc}, a.json, lines)
    return 0


def cmd_split(a):
    sk = _catalog(a)
    s = _find(sk, a.skill)
    if not s:
        print("no skill %s" % a.skill)
        return 2
    if "plugins" + os.sep + "cache" in os.path.abspath(s["path"]):
        print("refused: %s is an installed plugin copy; edit the plugin's source repository instead" % s["path"])
        return 1
    if not a.when or len(a.when.split()) < 3:
        print("refused: --when must say which tasks need this section (at least three words), so the agent knows when to read it")
        return 1
    to = a.to or "references/%s.md" % slug(a.section)
    try:
        target, backup = split_section(s["path"], a.section, to, a.when)
    except ValueError as e:
        print("refused: %s" % e)
        return 1
    _, body = body_of(s["path"])
    print("moved '%s' to %s; SKILL.md body now ~%s tokens (backup %s)" % (a.section, target, k(est_tokens(len(NL.join(body)))), backup))
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
    h = usage(a.days, headless=True)
    sk = listed(_catalog(a))
    rows = [(s["id"], c.get(s["name"], 0), s["listed_chars"], h.get(s["name"], 0)) for s in sk]
    rows.sort(key=lambda r: (r[1], -r[2]))
    lines = ["skill invocations in the last %d days (Claude Code Skill calls and slash commands, Codex skill blocks; "
             "headless eval and script runs shown apart, never as use)" % a.days]
    for sid, n, ch, hn in rows:
        lines.append("  %4d  %-44s %5d chars listed%s" % (n, sid[:44], ch, "  (+%d headless)" % hn if hn else ""))
    unused = [r for r in rows if r[1] == 0]
    lines.append("%d of %d listed skills unused; their descriptions cost ~%s tokens every session" % (
        len(unused), len(rows), k(est_tokens(sum(r[2] for r in unused)))))
    out({"days": a.days, "counts": {r[0]: r[1] for r in rows}, "headless": {r[0]: r[3] for r in rows if r[3]}},
        a.json, lines)
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
    p = common(sp.add_parser("sections", help="body sections by size and kind; what could load on demand"))
    p.add_argument("skill")
    p.add_argument("--min-tokens", type=int, default=250)
    p.set_defaults(fn=cmd_sections)
    p = common(sp.add_parser("split", help="move one body section to a reference file read only when needed"))
    p.add_argument("skill")
    p.add_argument("--section", required=True, help="the heading text of the section to move")
    p.add_argument("--to", help="relative target (default references/<heading-slug>.md)")
    p.add_argument("--when", help="which tasks need it: becomes 'Read <file> when <this>.'")
    p.set_defaults(fn=cmd_split)
    p = common(sp.add_parser("park", help="move a skill to the parking lot: unlisted, still findable through the index"))
    p.add_argument("name", nargs="?")
    p.add_argument("--scope", default="user", choices=["user", "project"])
    p.add_argument("--group", help="index group (default: the name's first word)")
    p.add_argument("--line", help="the index line (default: the description's 'Use when' clause)")
    p.add_argument("--soft", action="store_true", help="Claude Code only: skillOverrides off, folder stays")
    p.add_argument("--plugin", help="disable this Claude Code plugin and index its skills")
    p.set_defaults(fn=cmd_park)
    p = common(sp.add_parser("unpark", help="put a parked skill back where it was"))
    p.add_argument("name")
    p.add_argument("--scope", default="user", choices=["user", "project"])
    p.set_defaults(fn=cmd_unpark)
    p = common(sp.add_parser("parked", help="the parking lot: list | index | doctor | suggest | alias NAME PATH"))
    p.add_argument("action", nargs="?", default="list", choices=["list", "index", "doctor", "suggest", "alias"])
    p.add_argument("args", nargs="*", help="alias: NAME PATH, a link unpark should recreate")
    p.add_argument("--scope", default="user", choices=["user", "project"])
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(fn=cmd_parked)
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
