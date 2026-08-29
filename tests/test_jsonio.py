"""The agent JSON contract: one strict retry, then failure WITH the
reply quoted — never a blind "Expecting value: line 1 column 1"."""

from __future__ import annotations

import json

import pytest


class TestAskJson:
    def test_clean_json_needs_one_call(self):
        from rita.firmware.jsonio import ask_json
        calls = []

        def complete(p):
            calls.append(p)
            return '{"a": 1}'

        assert ask_json(complete, "prompt", what="writer") == {"a": 1}
        assert len(calls) == 1

    def test_prose_first_reply_gets_one_strict_retry(self):
        # The live failure: the agent replied prose; RITA gave up on the
        # first parse. Now she reminds it ONCE — JSON only — and retries.
        from rita.firmware.jsonio import ask_json
        calls = []

        def complete(p):
            calls.append(p)
            if len(calls) == 1:
                return "Sure! I'll create the test files for you."
            return '{"src/main.c": "int main(){}"}'

        out = ask_json(complete, "prompt", what="test writer")
        assert out == {"src/main.c": "int main(){}"}
        assert len(calls) == 2
        assert "ONLY the JSON" in calls[1]      # the reminder is explicit

    def test_persistent_prose_fails_with_the_reply_quoted(self):
        from rita.firmware.jsonio import ask_json

        with pytest.raises(ValueError) as exc:
            ask_json(lambda p: "I can't help with that request.",
                     "prompt", what="test writer")
        msg = str(exc.value)
        assert "test writer" in msg
        assert "unparseable" in msg
        assert "I can't help" in msg            # the evidence

    def test_empty_reply_says_empty(self):
        from rita.firmware.jsonio import ask_json

        with pytest.raises(ValueError) as exc:
            ask_json(lambda p: "", "prompt", what="planner")
        assert "empty" in str(exc.value).lower()

    def test_fenced_json_is_accepted(self):
        from rita.firmware.jsonio import ask_json
        out = ask_json(
            lambda p: 'Here you go:\n```json\n{"x": 2}\n```', "p",
            what="writer")
        assert out == {"x": 2}


class TestWritersUseTheContract:
    def test_ztest_writer_retries_then_succeeds(self, tmp_path):
        from rita.firmware.testwriter import write_ztest
        files = json.dumps({
            "testcase.yaml": "tests:\n  app.x:\n    harness: ztest\n",
            "src/main.c": "#include <zephyr/ztest.h>\n",
            "CMakeLists.txt": "x", "prj.conf": "CONFIG_ZTEST=y\n"})
        replies = ["Let me think about the test structure first.", files]
        result = write_ztest("goal", "b", tmp_path,
                             lambda p: replies.pop(0))
        assert result.test_id == "app.x"

    def test_ztest_writer_failure_quotes_the_reply(self, tmp_path):
        from rita.firmware.testwriter import write_ztest

        with pytest.raises(ValueError) as exc:
            write_ztest("goal", "b", tmp_path,
                        lambda p: "The build seems fine to me.")
        assert "The build seems fine" in str(exc.value)

    def test_planner_retries_then_succeeds(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RITA_HOME", str(tmp_path / "rita"))
        from rita.projects.planner import plan_project
        from rita.routing.vocabulary import Vocabulary
        plan = json.dumps({"items": [
            {"title": "t", "command": "build blinky for native_sim"}]})
        replies = ["Here's my thinking on the plan...", plan]
        project = plan_project("goal", lambda p: replies.pop(0),
                               Vocabulary.load())
        assert len(project.items) == 1
