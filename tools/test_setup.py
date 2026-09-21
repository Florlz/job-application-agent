"""Offline onboarding checks: temporary workspace, fake services, real Textual keyboard events."""
import asyncio
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobagent.setup_core import CHANNELS, Setup, SetupError, extract_resume, preserve, validate_profile, webhook_url
from jobagent import setup_services as services
from jobagent.setup_tui import SetupApp
from textual.widgets import Checkbox, Input, Static, TextArea
import yaml

REPO = Path(__file__).resolve().parent.parent


def fails(fn, phrase):
    try:
        fn()
    except SetupError as exc:
        assert phrase in str(exc), str(exc)
    else:
        raise AssertionError("Expected failure: " + phrase)


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        shutil.copy(REPO / "tools/job_db.py", root / "tools/job_db.py")
        (root / "profile").mkdir()
        setup = Setup(root)
        setup.state["fields"]["roles"] = "QA engineer"
        setup.mark("model", "previous check")
        assert Setup(root).state["fields"]["roles"] == "QA engineer"
        assert "model" not in Setup(root).state["checks"]
        preserve(root / "keep.txt", "original")
        fails(lambda: preserve(root / "keep.txt", "replacement"), "differs")
        assert (root / "keep.txt").read_text() == "original"
        for bad in ("http://discord.com/api/webhooks/123/token", "https://discord.com.evil.test/api/webhooks/123/token",
                    "https://discord.com/api/webhooks/123/token?redirect=x"):
            fails(lambda: webhook_url(bad), "Discord webhook")
        assert webhook_url("https://discord.com/api/webhooks/123/token")
        profile = yaml.safe_load((REPO / "profile/career-profile.example.yaml").read_text(encoding="utf-8"))
        assert validate_profile(profile)
        minimal = {"identity": {"name": "Alex", "email": "alex@example.test", "location": "Berlin"},
                   "skills": {}, "projects": [], "experience": [], "education": [], "leadership": []}
        assert validate_profile(minimal)["identity"]["resume_name"] == "Alex"
        bad_shape = copy.deepcopy(profile)
        del bad_shape["projects"][0]["name"]
        fails(lambda: validate_profile(bad_shape), "needs name")
        bad = copy.deepcopy(profile)
        bad["projects"].append(bad["projects"][0])
        fails(lambda: validate_profile(bad), "unique")
        fails(lambda: extract_resume("", "tiny"), "No readable")
        assert extract_resume("", "An honest resume sentence with enough text for extraction.")
        raw_profile = (REPO / "profile/career-profile.example.yaml").read_text(encoding="utf-8")
        preserve(root / "profile/career-profile.yaml", raw_profile)
        setup.confirm_profile(raw_profile, "")
        assert (root / "profile/career-profile.yaml").read_text(encoding="utf-8") == raw_profile
        assert (root / "profile/standard-resume.json").exists()
        before = (root / "profile/career-profile.yaml").read_bytes()
        profile["identity"]["name"] = "Somebody Else"
        fails(lambda: setup.confirm_profile(yaml.safe_dump(profile), ""), "existing verified profile")
        assert (root / "profile/career-profile.yaml").read_bytes() == before
        hooks = {c: f"https://discord.com/api/webhooks/{100+i}/token" for i, c in enumerate(CHANNELS)}
        with patch("jobagent.setup_core.request_json", return_value={"channel_id": "123"}):
            setup.discord(hooks)
        assert "token" not in setup.state_path.read_text()
        with patch("jobagent.setup_core.request_json", side_effect=[[{"message_id": "abcdef12345"}], [{"message_id": "abcdef12345", "body_text": "sample"}]]) as request:
            setup.gmail("abcdef12345", "subject:sample")
            assert request.call_count == 2
        with patch("jobagent.setup_core.request_json", return_value=[]):
            fails(lambda: setup.gmail("abcdef12345", "subject:sample"), "did not return")

        # Sample generation uses the real validator and keeps the application tracker untouched.
        (root / "tools/cover_letter").mkdir()
        shutil.copy(REPO / "tools/cover_letter/make_cover_letter.py", root / "tools/cover_letter/make_cover_letter.py")
        shutil.copy(REPO / "tools/discord_post.py", root / "tools/discord_post.py")
        setup.preferences({"roles": "Developer", "seniority": "Junior", "locations": "Berlin", "work_setup": "Remote"})
        for check in ("computer", "dependencies", "model", "profile", "preferences", "discord", "gmail"):
            setup.mark(check, "offline fixture")
        setup.state["fields"].update(message_id="abcdef12345", gmail_query="subject:sample")
        sentence = "I value careful communication and would welcome the opportunity to discuss this role with your team. "
        package = {"brief": {"fit": "You can discuss your verified projects.", "highlight": ["React"], "gaps": [], "check": ["Review this sample."]},
                   "letter": {"role": "Developer", "company": "Example Company", "greeting": "Dear Hiring Team,",
                              "paragraphs": [sentence * 4] * 4, "claims": [], "company_claims": []}}
        sent = []
        real_module = services.module
        def fake_module(path, name):
            value = real_module(path, name)
            if name == "setup_discord":
                value.send_webhook = lambda url, payload, files: sent.append((payload, files))
            return value
        def fake_build(args, cwd, **kwargs):
            artifacts = {}
            for extension in ("md", "docx", "pdf"):
                artifact = root / "output/setup/sample" / ("Alex_Rivera_Cover_Letter_Example." + extension)
                artifact.write_bytes(b"offline artifact")
                artifacts[extension] = str(artifact)
            return json.dumps(artifacts)
        resume_pdf = root / "profile/Standard_Resume.pdf"
        resume_pdf.write_bytes(b"offline resume")
        with patch.object(setup, "computer"), patch.object(setup, "check_model"), patch.object(setup, "gmail"), \
             patch.object(setup, "discord"), patch.object(setup, "ai", return_value=package), \
             patch.object(services, "runtime_files"), patch.object(services, "module", side_effect=fake_module), \
             patch.object(services, "run", side_effect=fake_build):
            services.verify(setup)
        assert len(sent) == 1 and "SAMPLE" in sent[0][0]["content"]
        assert all(Path(path).exists() for path in sent[0][1])
        assert not (root / "data/job-hunt.db").exists()

        # A crash after a create is recovered by inspecting Hermes jobs, not duplicating them.
        home = root / "fake-hermes"
        home.mkdir()
        (home / "config.yaml").write_text("timezone: Etc/UTC\n")
        current = []
        setup.state["fields"]["approved_model"] = "example-model"
        setup.mark("verified", "offline fixture")
        def fake_run(args, cwd, **kwargs):
            if args[1:3] == ["cron", "create"]:
                name = args[args.index("--name") + 1]
                current.append({"id": str(len(current)), "name": name, "schedule": {"expr": args[3]},
                                "workdir": str(root), "model": "example-model", "enabled": False,
                                "prompt": args[args.index("--paused") + 1] if "--skill" in args else "",
                                "skills": ["job-hunt"] if "--skill" in args else [],
                                "no_agent": "--no-agent" in args,
                                "script": args[args.index("--script") + 1] if "--script" in args else None,
                                "monitor_script": args[args.index("--monitor-script") + 1] if "--monitor-script" in args else None,
                                "deliver": "local", "failure_deliver": "discord:alerts"})
            elif args[1:3] == ["cron", "resume"]:
                next(j for j in current if j["id"] == args[3])["enabled"] = True
            return ""
        with patch.object(setup, "hermes_home", return_value=home), patch.object(setup, "model", return_value="example-model"), \
             patch.object(services, "runtime_files", return_value=root), patch.object(services, "jobs", side_effect=lambda _: current), \
             patch.object(services, "run", side_effect=fake_run):
            services.activate(setup, "Etc/UTC", "9,18", "15", "21")
            assert len(current) == 3 and all(j["enabled"] for j in current)
            services.activate(setup, "Etc/UTC", "9,18", "15", "21")
            assert len(current) == 3
            fails(lambda: services.activate(setup, "Etc/UTC", "10", "15", "21"), "differs")
            current[-1]["script"] = "unrelated.py"
            fails(lambda: services.activate(setup, "Etc/UTC", "9,18", "15", "21"), "different script")
            current[-1]["script"] = "jobagent_tracker.py"
            with patch.object(setup, "model", return_value="changed-model"):
                fails(lambda: services.activate(setup, "Etc/UTC", "9,18", "15", "21"), "model changed")

        # Real TUI lifecycle and navigation, at Windows Terminal and compact sizes.
        app = SetupApp(root)
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await pilot.press("alt+right")
            assert app.step == 1
            await pilot.press("alt+right")
            assert app.step == 1  # Cannot pretend prerequisites passed.
            await pilot.press("escape")
            assert app.step == 0
            for step in range(9):
                app.step = step
                await app.show_step()
                await pilot.pause()
                assert app.query_one("#page").size.height > 0
            app.step = 5
            await app.show_step()
            app.query_one("#secret_hermes", Input).value = "private-token-never-save"
            await pilot.press("ctrl+s")
            assert "private-token-never-save" not in app.setup.state_path.read_text()
            # Worker errors return control, keep the interface alive, and do not leak credentials.
            app.step = 1
            await app.show_step()
            with patch.object(app.setup, "computer", side_effect=SetupError("Install missing prerequisite and retry.")):
                app.query_one("#computer").focus()
                await pilot.press("enter")
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert not app.busy
                assert app.query_one("#result", Static).has_class("error")
            app.step = 3
            await app.show_step()
            app.query_one("#resume_text", TextArea).load_text("Resume draft saved across restart")
            await pilot.press("ctrl+s")
            assert Setup(root).state["fields"]["resume_text"] == "Resume draft saved across restart"
            app.step = 0
            await app.show_step()
            output = REPO / "output/setup-preview"
            output.mkdir(parents=True, exist_ok=True)
            app.save_screenshot("welcome.svg", path=str(output))
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert app.has_class("compact")
            app.save_screenshot("compact.svg", path=str(output))
            for step, button in ((3, "profile"), (5, "discord"), (8, "activate")):
                app.step = step
                await app.show_step()
                app.query_one("#back").focus()
                for _ in range(50):
                    await pilot.press("tab")
                    if app.focused and app.focused.id == button:
                        break
                assert app.focused.id == button, (step, app.focused)
                await pilot.pause()
                assert app.focused.region.y >= 0 and app.focused.region.bottom <= 24
                app.save_screenshot(f"compact-{step}.svg", path=str(output))
        print("Setup checks passed: preservation, resume, secret handling, Gmail probes, repeat activation, keyboard and compact layout.")


if __name__ == "__main__":
    asyncio.run(main())
