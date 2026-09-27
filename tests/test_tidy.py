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


if __name__ == "__main__":
    unittest.main(verbosity=1)
