"""Tests for tidy.py. Run from the repository root: python tests/test_tidy.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "skill-tidy", "scripts")
sys.path.insert(0, SCRIPTS)
import tidy  # noqa: E402

FEED = "Collect articles from news feeds about databases and storage engines, summarise each article into notes, tag topics and track trends. Use when the user says 'scan the feeds' or 'what is new in databases'."
PAINT = "Generate images, sprites and textures with a local diffusion server for game assets. Use when the user asks for a sprite, an icon or a texture."


def write(path, text, crlf=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = text.replace("\n", "\r\n") if crlf else text
    with open(path, "wb") as f:
        f.write(data.encode("utf-8"))


def skill(root, name, desc, extra="", body="# body\n"):
    p = os.path.join(root, name, "SKILL.md")
    write(p, "---\nname: %s\ndescription: %s\n%s---\n%s" % (name, json.dumps(desc), extra, body))
    return p


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tidy.main(list(argv))
    return rc, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tidy-")
        self.home = os.path.join(self.tmp, "home")
        os.environ["SKILLTIDY_HOME"] = self.home
        os.environ["SKILLTIDY_STATE"] = os.path.join(self.tmp, "state")
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.user = os.path.join(self.home, ".claude", "skills")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestParse(Base):
    def test_block_scalar_quoted_and_list(self):
        p = os.path.join(self.user, "blocky", "SKILL.md")
        write(p, "---\nname: blocky\ndescription: >-\n  First line\n  second line.\npaths:\n  - src/**\n  - '*.md'\nwhen_to_use: 'it''s here'\n---\nbody\n")
        s = tidy.parse_skill(p)
        self.assertEqual(s["desc"], "First line second line.")
        self.assertEqual(s["fm"]["paths"], ["src/**", "*.md"])
        self.assertEqual(s["when_to_use"], "it's here")
        q = skill(self.user, "quoted", 'Say "hi" and use it.')
        self.assertEqual(tidy.parse_skill(q)["desc"], 'Say "hi" and use it.')


class TestScan(Base):
    def test_roots_plugins_overrides_and_mirrors(self):
        skill(self.user, "feed-scan", FEED)
        skill(self.user, "painter", PAINT)
        skill(self.user, "manual", PAINT + " Manual.", extra="disable-model-invocation: true\n")
        skill(os.path.join(self.home, ".agents", "skills"), "painter", PAINT)  # mirror for codex/all
        skill(os.path.join(self.proj, ".claude", "skills"), "local-one", FEED + " Local.")
        cache = os.path.join(self.home, ".claude", "plugins", "cache", "mk", "plug", "1.0")
        skill(os.path.join(cache, "skills"), "plug-skill", PAINT + " From a plugin.")
        tidy_json = {"version": 2, "plugins": {"plug@mk": [{"scope": "user", "installPath": cache}]}}
        write(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"), json.dumps(tidy_json))
        write(os.path.join(self.home, ".claude", "settings.json"), json.dumps({"skillOverrides": {"painter": "name-only", "feed-scan": "off"}}))
        sk = tidy.scan("claude", self.proj)
        ids = sorted(s["id"] for s in sk)
        self.assertEqual(ids, ["feed-scan", "local-one", "manual", "painter", "plug:plug-skill"])
        by = {s["id"]: s for s in sk}
        self.assertFalse(by["manual"]["listed"])
        self.assertFalse(by["feed-scan"]["listed"])
        self.assertEqual(by["painter"]["listed_chars"], len("painter"))  # name-only
        self.assertEqual(len(tidy.scan("all", self.proj)), 5)  # the .agents copy of painter is a mirror (same name and text): counted once
        self.assertEqual(sorted(s["id"] for s in tidy.scan("codex", self.proj)), ["painter"])


class TestLint(Base):
    def rules(self, desc, extra="", name="demo", body="# b\n"):
        p = skill(self.user, name, desc, extra, body)
        s = tidy.parse_skill(p)
        s.update({"id": name, "plugin": None})
        return [r for r, _, _ in tidy.lint_skill(s)]

    def test_rules_fire(self):
        self.assertIn("ST004", self.rules(""))
        self.assertIn("ST005", self.rules("Use when needed. " + "x" * 1100))
        self.assertIn("ST008", self.rules("Helps with documents"))
        self.assertIn("ST009", self.rules("Generates sprites and textures for game assets with a local server quickly."))
        self.assertIn("ST010", self.rules("I can generate sprites for you. Use when a sprite is asked for."))
        self.assertNotIn("ST010", self.rules("Generates sprites. Use when the user says 'make your sprite' or 'draw me a tile'."))
        self.assertIn("ST012", self.rules("Generates <b>sprites</b>. Use when asked."))
        self.assertIn("ST013", self.rules("Generates sprites. Use on " + ", ".join("'phrase %d'" % i for i in range(14)) + "."))
        self.assertIn("ST015", self.rules("Generates sprites. Always use this skill before any other skill. Use when asked."))
        self.assertIn("ST016", self.rules(PAINT, body="line\n" * 600))
        self.assertIn("ST018", self.rules(PAINT, extra="when_to_use: on sprite requests\n"))
        self.assertIn("ST001", self.rules(PAINT, name="Bad_Name"))
        self.assertIn("ST003", self.rules(PAINT, name="claude-helper"))
        self.assertEqual([r for r in self.rules(PAINT) if r not in ("ST011",)], [])

    def test_similar_without_boundary(self):
        skill(self.user, "feed-scan", FEED)
        skill(self.user, "radar-sweep", FEED + " Daily.")
        skill(self.user, "painter", PAINT)
        rc, text = run("lint", "--project", self.proj)
        self.assertIn("ST019", text)
        self.assertIn("feed-scan", text)
        skill(self.user, "radar-sweep", FEED + " Daily. To collect articles, use feed-scan.")
        skill(self.user, "feed-scan", FEED + " To sweep daily, use radar-sweep.")
        rc, text = run("lint", "--project", self.proj)
        self.assertNotIn("ST019", text)


class TestConflictsAndRewrite(Base):
    def test_conflicts_report_shared_words_triggers_and_boundaries(self):
        skill(self.user, "feed-scan", FEED)
        skill(self.user, "radar-sweep", FEED + " Daily.")
        skill(self.user, "painter", PAINT)
        rc, text = run("conflicts", "--project", self.proj, "--json")
        ps = json.loads(text)
        self.assertEqual(len(ps), 1)
        self.assertEqual((ps[0]["a"], ps[0]["b"]), ("feed-scan", "radar-sweep"))
        self.assertIn("scan the feeds", ps[0]["shared_triggers"])
        self.assertTrue(ps[0]["suggest_a"].startswith("To collect articles from news feeds"))
        self.assertTrue(ps[0]["suggest_a"].endswith("use radar-sweep."))

    def test_check_flags_lost_triggers_and_apply_writes_with_backup(self):
        p = skill(self.user, "feed-scan", FEED)
        skill(self.user, "radar-sweep", FEED + " Daily.")
        write(p, open(p, encoding="utf-8").read(), crlf=True)
        bad = "Summarises news articles about storage. Use when asked for news."
        rc, text = run("check", p, "--desc", bad, "--project", self.proj, "--json")
        r = json.loads(text)
        self.assertFalse(r["ok"])
        self.assertIn("scan the feeds", [x["trigger"] for x in r["lost_triggers"]])
        rc, _ = run("apply", p, "--desc", bad, "--project", self.proj)
        self.assertEqual(rc, 1)
        good = ("Collect articles from news feeds about databases and storage engines into tagged notes and trend lines. "
                "Use when the user says 'scan the feeds' or 'what is new in databases'. To sweep daily, use radar-sweep.")
        rc, text = run("check", p, "--desc", good, "--project", self.proj, "--json")
        r = json.loads(text)
        self.assertTrue(r["ok"], r)
        rc, text = run("apply", p, "--desc", good, "--project", self.proj)
        self.assertEqual(rc, 0, text)
        raw = open(p, "rb").read()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n\n\r", raw)
        self.assertEqual(tidy.parse_skill(p)["desc"], good)
        self.assertIn("name: feed-scan", raw.decode("utf-8"))
        backups = [f for _, _, fs in os.walk(os.path.join(self.tmp, "state", "backups")) for f in fs]
        self.assertEqual(backups, ["feed-scan.SKILL.md"])

    def test_apply_refuses_installed_plugin_copy(self):
        cache = os.path.join(self.home, ".claude", "plugins", "cache", "mk", "plug", "1.0")
        p = skill(os.path.join(cache, "skills"), "plug-skill", PAINT)
        write(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"),
              json.dumps({"version": 2, "plugins": {"plug@mk": [{"scope": "user", "installPath": cache}]}}))
        rc, text = run("apply", "plug:plug-skill", "--desc", PAINT + " Now shorter.", "--project", self.proj)
        self.assertEqual(rc, 1)
        self.assertIn("installed plugin copy", text)

    def test_block_scalar_description_is_replaced_whole(self):
        p = os.path.join(self.user, "blocky", "SKILL.md")
        write(p, "---\nname: blocky\ndescription: >-\n  Old text\n  more old.\nlicense: MIT\n---\nbody\n")
        tidy.set_description(p, "New text. Use when asked.")
        t = open(p, encoding="utf-8").read()
        self.assertIn('description: "New text. Use when asked."\nlicense: MIT\n', t)
        self.assertNotIn("Old text", t)


class TestUsageBudgetOffload(Base):
    def transcript(self):
        d = os.path.join(self.home, ".claude", "projects", "p1")
        rows = [
            {"type": "user", "message": {"role": "user", "content": "please scan the feeds for me"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "feed-scan"}}]}},
            {"type": "user", "message": {"role": "user", "content": "<command-name>/painter</command-name>"}},
            {"type": "user", "message": {"role": "user", "content": "what is new in databases this week"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}},
        ]
        write(os.path.join(d, "s1.jsonl"), "\n".join(json.dumps(r) for r in rows) + "\n")

    def test_usage_offload_write_and_budget(self):
        skill(self.user, "feed-scan", FEED)
        skill(self.user, "painter", PAINT)
        skill(self.user, "idle-one", "Converts old ledger exports into CSV files for audits. Use when the user mentions a ledger export.")
        self.transcript()
        self.assertEqual(tidy.usage(30), {"feed-scan": 1, "painter": 1})
        write(os.path.join(self.home, ".claude", "settings.json"), json.dumps({"theme": "dark"}))
        rc, text = run("offload", "--project", self.proj, "--json")
        r = json.loads(text)
        self.assertEqual(r["skillOverrides"], {"idle-one": "name-only"})
        rc, text = run("offload", "--project", self.proj, "--write")
        st = json.load(open(os.path.join(self.home, ".claude", "settings.json")))
        self.assertEqual(st, {"theme": "dark", "skillOverrides": {"idle-one": "name-only"}})
        self.assertEqual(tidy.scan("claude", self.proj)[1]["listed_chars"], len("idle-one"))
        b = tidy.budgets(tidy.scan("claude", self.proj), 20000)
        self.assertTrue(b["claude"]["over"])
        self.assertEqual(b["codex"]["budget_chars"], 400)

    def test_harvest_brief(self):
        skill(self.user, "feed-scan", FEED)
        skill(self.user, "radar-sweep", FEED + " Daily.")
        self.transcript()
        rc, text = run("harvest", "feed-scan", "--project", self.proj)
        self.assertEqual(rc, 0)
        brief = open(os.path.join(self.tmp, "state", "briefs", "feed-scan.md"), encoding="utf-8").read()
        self.assertIn("One-rewrite brief", brief)
        self.assertIn("what is new in databases this week", brief)  # matched a trigger, skill not invoked
        self.assertIn("radar-sweep", brief)


class TestConfigDir(Base):
    def test_claude_config_dir_moves_every_claude_path(self):
        cfg = os.path.join(self.tmp, "altcfg")
        os.environ["CLAUDE_CONFIG_DIR"] = cfg
        try:
            skill(os.path.join(cfg, "skills"), "painter", PAINT)
            skill(self.user, "ignored", FEED)  # ~/.claude is not read when the variable is set
            write(os.path.join(cfg, "settings.json"), json.dumps({"skillOverrides": {"painter": "name-only"}}))
            sk = tidy.scan("claude", self.proj)
            self.assertEqual([s["id"] for s in sk], ["painter"])
            self.assertEqual(sk[0]["listed_chars"], len("painter"))
            write(os.path.join(cfg, ".claude.json"), json.dumps({"mcpServers": {"x": {"alwaysLoad": True}}}))
            self.assertEqual(tidy.mcp_settings(self.proj)["always_load"], ["x"])
        finally:
            del os.environ["CLAUDE_CONFIG_DIR"]


class TestStartup(Base):
    def test_chain_follows_imports_and_ancestors(self):
        write(os.path.join(self.home, ".claude", "CLAUDE.md"), "user rules\n")
        write(os.path.join(self.tmp, "CLAUDE.md"), "parent rules\n")
        write(os.path.join(self.proj, "CLAUDE.md"), "@AGENTS.md\nclaude notes\n")
        write(os.path.join(self.proj, "AGENTS.md"), "x" * 4000)
        tmp = os.path.normcase(self.tmp)  # the ancestor walk also reaches real folders above the temp dir
        paths = [os.path.basename(x["path"]) + ":" + str(x["via"]) for x in tidy.instruction_chain(self.proj)
                 if os.path.normcase(x["path"]).startswith(tmp)]
        self.assertIn("AGENTS.md:CLAUDE.md", paths)
        self.assertEqual(sum(1 for p in paths if p.startswith("CLAUDE.md")), 3)
        write(os.path.join(self.home, ".claude.json"), json.dumps({"mcpServers": {"a": {"alwaysLoad": True}, "b": {}}}))
        write(os.path.join(self.home, ".claude", "settings.json"), json.dumps({"env": {"ENABLE_TOOL_SEARCH": "false"}}))
        rc, text = run("startup", "--project", self.proj)
        self.assertIn("alwaysLoad (schemas loaded upfront): a", text)
        self.assertIn("tool search is off", text)



class TestGaps(Base):
    def test_apostrophes_similarity_rule_and_repo_root_lint(self):
        self.assertEqual(tidy.triggers("the interview app's questions (\"give him Pin Down\") and 'refresh x'"), ["give him Pin Down", "refresh x"])
        skill(self.user, "feed-scan", FEED)
        p = skill(self.user, "radar-sweep", "Sweeps radar data from weather stations into daily maps. Use when the user asks for a radar sweep.")
        rc, text = run("check", p, "--desc", FEED + " Radar too.", "--project", self.proj, "--json")
        r = json.loads(text)
        self.assertFalse(r["similarity_ok"])
        self.assertFalse(r["ok"])
        repo = os.path.join(self.tmp, "repo")
        skill(os.path.join(repo, "skills"), "painter", PAINT)
        rc, text = run("lint", repo, "--project", self.proj, "--min", "info")
        self.assertNotIn("ST004", text)
        self.assertIn("1 skills checked", text)
        rules = TestLint.rules
        self.assertNotIn("ST011", rules(self, "Sets repos up. Use at the start of a project or on 'stop relearning things'."))
        self.assertNotIn("ST009", rules(self, "Sets repos up for agents with docs. Use at the start of a new project."))


class TestBody(Base):
    BODY = ("# Demo\n\nIntro line.\n\n## Step 1: do the thing\n\nRun the script.\n\n"
            "## Examples\n\n" + "".join("Example %d: input, output and a short explanation of the case.\n" % i for i in range(60)) +
            "\n### Edge cases\n\nSome edge notes.\n\n```\n## not a heading inside a fence\n```\n\n"
            "## Report\n\nSay what changed.\n")

    def test_sections_finds_supplementary_and_ignores_fenced_headings(self):
        p = skill(self.user, "demo", PAINT, body=self.BODY)
        _, body = tidy.body_of(p)
        heads = [s["heading"] for s in tidy.sections(body)]
        self.assertEqual(heads, ["Step 1: do the thing", "Examples", "Edge cases", "Report"])
        cands = [c["heading"] for c in tidy.offload_candidates(p)]
        self.assertEqual(cands, ["Examples"])
        rc, text = run("sections", "demo", "--project", self.proj)
        self.assertIn("-> move to references/examples.md", text)

    def test_split_moves_section_leaves_pointer_and_keeps_crlf(self):
        p = skill(self.user, "demo", PAINT, body=self.BODY)
        write(p, open(p, encoding="utf-8").read(), crlf=True)
        rc, text = run("split", "demo", "--section", "Examples", "--when", "short", "--project", self.proj)
        self.assertEqual(rc, 1)  # --when too vague
        rc, text = run("split", "demo", "--section", "Examples", "--when", "the user asks for worked examples or edge cases", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        raw = open(p, "rb").read().decode("utf-8")
        self.assertIn("\r\n", raw)
        self.assertIn("## Examples\r\n\r\nRead [references/examples.md](references/examples.md) when the user asks for worked examples or edge cases.", raw)
        self.assertNotIn("Example 5:", raw)
        self.assertIn("## Report", raw)
        self.assertIn("## not a heading inside a fence", open(os.path.join(self.user, "demo", "references", "examples.md"), encoding="utf-8").read())
        ref = open(os.path.join(self.user, "demo", "references", "examples.md"), encoding="utf-8").read()
        self.assertTrue(ref.startswith("# Examples\n"))
        self.assertIn("\n## Edge cases\n", ref)  # ### moved up one level
        self.assertEqual(tidy.parse_skill(p)["desc"], PAINT)
        rc, text = run("split", "demo", "--section", "Nope", "--when", "never happens in practice", "--project", self.proj)
        self.assertEqual(rc, 1)
        rc, text = run("split", "demo", "--section", "Report", "--to", "../escape.md", "--when", "the final report is written", "--project", self.proj)
        self.assertEqual(rc, 1)

    def test_long_reference_gets_contents_and_lint_rules(self):
        big = "# Demo\n\n## Step 1\n\nGo.\n\n## Reference tables\n\n" + "".join("### Topic %d\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n" % i for i in range(20))
        p = skill(self.user, "demo", PAINT, body=big)
        rc, _ = run("split", "demo", "--section", "Reference tables", "--when", "a task needs the lookup tables", "--project", self.proj)
        ref = open(os.path.join(self.user, "demo", "references", "reference-tables.md"), encoding="utf-8").read()
        self.assertIn("## Contents", ref)
        d = os.path.join(self.user, "demo", "references")
        write(os.path.join(d, "a.md"), "# A\n\nSee [b](b.md) and [research](../RESEARCH.md).\n")
        write(os.path.join(d, "b.md"), "# B\n")
        write(os.path.join(self.user, "demo", "RESEARCH.md"), "# R\n")
        write(p, open(p, encoding="utf-8").read() + "\nRun scripts\\tool.py.\n")
        s = tidy.parse_skill(p)
        s.update({"id": "demo", "plugin": None})
        rules = [r for r, _, _ in tidy.lint_skill(s)]
        self.assertIn("ST021", rules)
        self.assertIn("ST023", rules)
        nested, _ = tidy.reference_problems(os.path.join(self.user, "demo"))
        self.assertEqual(nested, ["references/a.md"])


class TestParking(Base):
    def cfg(self, name):
        return os.path.join(self.home, ".claude", name)

    def test_park_moves_indexes_into_claude_md_and_unpark_restores(self):
        skill(self.user, "feed-scan", FEED)
        skill(self.user, "painter", PAINT, body="# painter\n\nRun ${CLAUDE_SKILL_DIR}/scripts/go.py\n")
        write(self.cfg("CLAUDE.md"), "# my rules\n\nkeep this\n", crlf=True)
        rc, text = run("park", "feed-scan", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        lot = os.path.join(self.home, ".agents", "parked-skills")
        self.assertTrue(os.path.isfile(os.path.join(lot, "feed-scan", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(self.user, "feed-scan")))
        self.assertNotIn("feed-scan", [s["name"] for s in tidy.scan("claude", self.proj)])
        run("park", "painter", "--project", self.proj)
        raw = open(self.cfg("CLAUDE.md"), "rb").read().decode("utf-8")
        self.assertIn("\r\n", raw)
        self.assertIn("keep this", raw)
        self.assertEqual(raw.count(tidy.MARK_START), 1)
        self.assertIn("- `feed-scan`: Collect articles from news feeds", raw)
        self.assertIn("feed-scan/SKILL.md`", raw)
        self.assertIn("- `painter` (unpark):", raw)
        self.assertIn("read that SKILL.md in full before acting", raw)
        idx = open(os.path.join(lot, "PARKED.md"), encoding="utf-8").read()
        self.assertIn("### feed", idx)
        rc, text = run("parked", "doctor", "--project", self.proj)
        self.assertIn("painter: uses ${CLAUDE_SKILL_DIR}", text)
        rc, text = run("unpark", "feed-scan", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        self.assertTrue(os.path.isfile(os.path.join(self.user, "feed-scan", "SKILL.md")))
        raw = open(self.cfg("CLAUDE.md"), "rb").read().decode("utf-8")
        self.assertNotIn("`feed-scan`", raw)
        run("unpark", "painter", "--project", self.proj)
        raw = open(self.cfg("CLAUDE.md"), "rb").read().decode("utf-8")
        self.assertNotIn(tidy.MARK_START, raw)  # empty lot: block removed
        self.assertTrue(raw.startswith("# my rules"))

    def test_plain_folder_under_a_linked_parent_is_not_a_link(self):
        real = os.path.join(self.tmp, "real-parent")
        os.makedirs(os.path.join(real, "child"))
        tidy.make_link(real, os.path.join(self.tmp, "linked-parent"))  # like /var on macOS or 8.3 names on Windows
        self.assertFalse(tidy.is_link(os.path.join(self.tmp, "linked-parent", "child")))
        self.assertTrue(tidy.is_link(os.path.join(self.tmp, "linked-parent")))

    def test_link_is_removed_not_its_target_and_comes_back(self):
        src = os.path.join(self.tmp, "repo", "skills", "feed-scan")
        skill(os.path.dirname(src), "feed-scan", FEED)
        os.makedirs(self.user, exist_ok=True)
        tidy.make_link(src, os.path.join(self.user, "feed-scan"))
        self.assertTrue(tidy.is_link(os.path.join(self.user, "feed-scan")))
        rc, text = run("park", "feed-scan", "--project", self.proj)
        self.assertIn("(link)", text)
        self.assertFalse(os.path.exists(os.path.join(self.user, "feed-scan")))
        self.assertTrue(os.path.isfile(os.path.join(src, "SKILL.md")))  # the target is untouched
        run("unpark", "feed-scan", "--project", self.proj)
        self.assertTrue(tidy.is_link(os.path.join(self.user, "feed-scan")))

    def test_soft_plugin_and_project_scope(self):
        skill(self.user, "painter", PAINT)
        rc, _ = run("park", "painter", "--soft", "--project", self.proj)
        self.assertEqual(json.load(open(self.cfg("settings.json")))["skillOverrides"], {"painter": "off"})
        self.assertTrue(os.path.exists(os.path.join(self.user, "painter")))
        run("unpark", "painter", "--project", self.proj)
        self.assertEqual(json.load(open(self.cfg("settings.json")))["skillOverrides"], {})
        cache = os.path.join(self.cfg("plugins"), "cache", "mk", "plug", "1.0")
        skill(os.path.join(cache, "skills"), "plug-one", FEED)
        write(os.path.join(self.cfg("plugins"), "installed_plugins.json"),
              json.dumps({"version": 2, "plugins": {"plug@mk": [{"scope": "user", "installPath": cache}]}}))
        rc, text = run("park", "plug:plug-one", "--project", self.proj)
        self.assertEqual(rc, 1)
        self.assertIn("never moved", text)
        rc, text = run("park", "--plugin", "plug", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        self.assertIs(json.load(open(self.cfg("settings.json")))["enabledPlugins"]["plug@mk"], False)
        self.assertIn("`plug:plug-one`", open(self.cfg("CLAUDE.md"), encoding="utf-8").read())
        run("unpark", "plug:plug-one", "--project", self.proj)
        self.assertIs(json.load(open(self.cfg("settings.json")))["enabledPlugins"]["plug@mk"], True)
        pskill = skill(os.path.join(self.proj, ".claude", "skills"), "local-one", PAINT + " Local.")
        write(os.path.join(self.proj, "AGENTS.md"), "# agents\n")
        write(os.path.join(self.proj, "CLAUDE.md"), "@AGENTS.md\n")
        rc, text = run("park", "local-one", "--scope", "project", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".agents", "parked-skills", "local-one", "SKILL.md")))
        self.assertIn("`local-one`", open(os.path.join(self.proj, "AGENTS.md"), encoding="utf-8").read())
        self.assertNotIn(tidy.MARK_START, open(os.path.join(self.proj, "CLAUDE.md"), encoding="utf-8").read())

    def test_park_removes_alias_links_and_unpark_recreates_them(self):
        skill(self.user, "feed-scan", FEED)
        codex = os.path.join(self.home, ".agents", "skills")
        os.makedirs(codex)
        tidy.make_link(os.path.join(self.user, "feed-scan"), os.path.join(codex, "feed-scan"))
        rc, text = run("park", "feed-scan", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        self.assertFalse(os.path.lexists(os.path.join(codex, "feed-scan")))
        m = tidy.load_manifest("user", self.proj)
        self.assertEqual([tidy._norm_dir(x) for x in m["feed-scan"]["aliases"]], [tidy._norm_dir(os.path.join(codex, "feed-scan"))])
        rc, text = run("parked", "doctor", "--project", self.proj)
        self.assertNotIn("dangling", text)
        rc, text = run("unpark", "feed-scan", "--project", self.proj)
        self.assertEqual(rc, 0, text)
        self.assertTrue(tidy.is_link(os.path.join(codex, "feed-scan")))
        self.assertTrue(os.path.isfile(os.path.join(codex, "feed-scan", "SKILL.md")))

    def test_link_mode_removes_sibling_links_to_the_same_target(self):
        src = os.path.join(self.tmp, "repo", "skills", "feed-scan")
        skill(os.path.dirname(src), "feed-scan", FEED)
        codex = os.path.join(self.home, ".agents", "skills")
        os.makedirs(self.user)
        os.makedirs(codex)
        tidy.make_link(src, os.path.join(self.user, "feed-scan"))
        tidy.make_link(src, os.path.join(codex, "feed-scan"))
        rc, text = run("park", "feed-scan", "--project", self.proj)
        self.assertIn("(link)", text)
        self.assertFalse(os.path.lexists(os.path.join(codex, "feed-scan")))
        self.assertTrue(os.path.isfile(os.path.join(src, "SKILL.md")))
        run("unpark", "feed-scan", "--project", self.proj)
        self.assertTrue(tidy.is_link(os.path.join(codex, "feed-scan")))

    def test_doctor_finds_dangling_links_and_alias_command_records_them(self):
        skill(self.user, "feed-scan", FEED)
        codex = os.path.join(self.home, ".agents", "skills")
        os.makedirs(codex)
        gone = os.path.join(self.tmp, "gone")
        os.makedirs(gone)
        tidy.make_link(gone, os.path.join(codex, "feed-scan"))
        shutil.rmtree(gone)
        rc, text = run("parked", "doctor", "--project", self.proj)
        self.assertIn("dangling link", text)
        self.assertIn("missing folder", text)
        tidy.remove_link(os.path.join(codex, "feed-scan"))
        rc, text = run("park", "feed-scan", "--project", self.proj)
        rc, text = run("parked", "alias", "feed-scan", os.path.join(codex, "feed-scan"), "--project", self.proj)
        self.assertEqual(rc, 0, text)
        run("parked", "alias", "feed-scan", os.path.join(codex, "feed-scan"), "--project", self.proj)
        self.assertEqual(len(tidy.load_manifest("user", self.proj)["feed-scan"]["aliases"]), 1)
        rc, text = run("parked", "alias", "nope", codex, "--project", self.proj)
        self.assertEqual(rc, 1)
        rc, text = run("parked", "doctor", "--project", self.proj)
        self.assertNotIn("dangling", text)
        run("unpark", "feed-scan", "--project", self.proj)
        self.assertTrue(os.path.isfile(os.path.join(codex, "feed-scan", "SKILL.md")))

    def test_large_lot_writes_group_summary_and_flags_big_groups(self):
        m = {}
        for i in range(45):
            m["tool-%02d" % i] = {"name": "tool-%02d" % i, "group": "tool", "line": "Use when tool %d" % i, "path": "/x/tool-%02d" % i, "features": []}
        full, block, big = tidy.render_index(m, "python tidy.py")
        self.assertIn("`tool-44`", full)
        self.assertNotIn("`tool-44`", block)
        self.assertIn("### tool (45):", block)
        self.assertEqual(big, ["tool"])
        self.assertEqual(tidy.index_line("x", "Builds charts from data (bar, line, pie) for reports. Use when the user asks ('bar chart of x')."),
                         "Builds charts from data for reports")

if __name__ == "__main__":
    unittest.main(verbosity=1)
