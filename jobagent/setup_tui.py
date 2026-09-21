"""Keyboard-first Textual onboarding. No account actions run merely by opening a screen."""
from pathlib import Path
import subprocess
import webbrowser

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Input, Label, ListItem, ListView, LoadingIndicator, Select, Static, TextArea
from tzlocal import get_localzone_name

from .setup_core import CHANNELS, STEPS, Setup, SetupError
from . import setup_services as services

LINKS = {
    "python": "https://www.python.org/downloads/windows/",
    "node": "https://nodejs.org/en/download",
    "docker": "https://docs.docker.com/desktop/setup/install/windows-install/",
    "hermes": "https://hermes-agent.nousresearch.com/docs/getting-started/installation/",
    "word": "https://www.microsoft.com/microsoft-365/word",
    "discord": "https://discord.com/developers/applications",
    "n8n": "http://localhost:5678",
    "oauth": "https://docs.n8n.io/integrations/builtin/credentials/google/oauth-single-service/",
}
REQUIRED = {1: ("computer", "dependencies"), 2: ("model",), 3: ("profile",), 4: ("preferences",),
            5: ("discord",), 6: ("gmail",), 7: ("verified",)}


class SetupApp(App):
    TITLE = "JobAgent / Setup"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+q", "save_exit", "Save & exit", priority=True),
                Binding("ctrl+s", "save", "Save", priority=True),
                Binding("alt+left", "back", "Back"), Binding("escape", "back", "Back", show=False),
                Binding("alt+right", "next", "Next")]
    CSS = """
    Screen { background: #101214; color: #d8dcdf; }
    #brand { height: 1; margin: 1 0; padding: 0 2; text-style: bold; color: #b5dbe5; }
    #body { height: 1fr; }
    #rail { width: 28; margin: 0 0 1 1; padding: 0 1; border: solid #555d63; background: #101214; }
    #rail-title { height: 1; margin: 1 1; color: #a6bacb; }
    ListView { height: auto; background: #101214; scrollbar-size: 0 0; }
    ListItem { height: 1; padding: 0 1; background: #101214; }
    ListItem > Label { width: 1fr; }
    ListItem.current { background: #1b2126; color: #b5dbe5; text-style: bold; }
    ListItem.complete { color: #afc6b4; }
    ListView:focus > ListItem.--highlight { background: #d8dcdf; color: #101214; text-style: bold; }
    #rail-note { height: auto; margin-top: 1; padding: 1; border-top: solid #30383e; color: #79838b; }
    #main { width: 1fr; margin: 0 1 1 1; border: solid #555d63; background: #101214; }
    #step-title { height: auto; padding: 1 2; text-style: bold; color: #d8dcdf; }
    #page { padding: 0 2 1 2; height: 1fr; scrollbar-color: #737e86; scrollbar-background: #101214; }
    .copy { height: auto; margin-bottom: 1; }
    .field-label { margin-top: 1; height: auto; color: #cbdce6; }
    Input { margin: 0; background: #101214; border: solid #555d63; }
    Input:focus, TextArea:focus { border: solid #b5dbe5; background: #101214; }
    TextArea { height: 12; margin-bottom: 1; border: solid #555d63; background: #101214; }
    #profile_text { height: 22; max-height: 50vh; }
    Button { height: 1; margin: 0 1 1 0; padding: 0 2; min-width: 12; background: #20262b; color: #d8dcdf; border: none; text-style: none; }
    Button:hover { background: #30383e; }
    Button.-primary { background: #1d3038; color: #b5dbe5; text-style: bold; }
    Button:focus { background: #d8dcdf; color: #101214; text-style: bold; }
    Button:disabled { background: #101214; color: #555d63; }
    Checkbox { width: 100%; height: auto; margin: 1 0; background: #101214; border: none; }
    Checkbox:focus { background: #30383e; }
    Select { margin-bottom: 1; }
    .row { height: auto; }
    #result { height: auto; max-height: 6; padding: 0 2; border-top: solid #555d63; color: #aeb9c1; background: #101214; overflow-y: auto; }
    #result.error { color: #ffd18c; }
    #busy { height: 1; display: none; }
    #nav { height: 1; margin-bottom: 1; padding: 0 1; align-horizontal: right; }
    #nav Button { margin: 0 0 0 1; }
    Footer { background: #20262b; color: #c3ccd3; }
    .welcome-title { height: auto; text-style: bold; color: #d8dcdf; margin: 0 0 1 0; }
    .journey { height: auto; margin: 0 0 1 0; color: #d8dcdf; }
    .location { height: auto; color: #a6bacb; margin: 1 0; }
    #install-links { height: auto; layout: horizontal; margin-top: 1; }
    #install-links Button { min-width: 0; padding: 0 1; }
    .compact #rail { display: none; }
    .compact #page { padding: 0 1; }
    .compact #brand { margin: 0; padding: 0 1; }
    .compact #step-title { padding: 0 1; }
    .compact #main { margin: 0 1 1 1; }
    .compact #result { max-height: 4; }
    """

    def __init__(self, workspace):
        super().__init__()
        self.setup = Setup(workspace)
        self.step = self.setup.state["step"]
        self.busy = False
        self.exit_after_work = False
        defaults = {"timezone": get_localzone_name(), "scan_hours": "9,18", "interval": "15", "report_hour": "21",
                    "seniority": "Entry-level / junior", "work_setup": "Remote, hybrid, on-site"}
        for key, value in defaults.items():
            self.setup.state["fields"].setdefault(key, value)

    def compose(self) -> ComposeResult:
        yield Static("jobagent setup", id="brand")
        with Horizontal(id="body"):
            with Vertical(id="rail"):
                yield Static("Steps", id="rail-title")
                yield ListView(*[ListItem(Label(f"{i + 1:02}  {name}")) for i, name in enumerate(STEPS)], id="steps")
                yield Static("Tab        next item\nShift+Tab  previous\nArrows     choose step\nEnter      activate\nSpace      toggle box\nCtrl+S     save", id="rail-note")
            with Vertical(id="main"):
                yield Static(id="step-title")
                yield VerticalScroll(id="page")
                yield LoadingIndicator(id="busy")
                yield Static("Ready. No account connections or automation run until you choose them.", id="result", markup=False)
        with Horizontal(id="nav"):
            yield Button("Back", id="back")
            yield Button("Next", id="next", variant="primary")
            yield Button("Save & exit", id="exit")
        yield Footer()

    async def on_mount(self):
        await self.show_step()

    def on_resize(self, event):
        self.set_class(event.size.width < 88, "compact")

    def copy(self, text):
        return Static(text, classes="copy", markup=False)

    def field(self, key, label, *, password=False):
        return [Label(label, classes="field-label"), Input("" if password else self.setup.state["fields"].get(key, ""),
                                                         id=key, password=password)]

    def area(self, key, label):
        return [Label(label, classes="field-label"), TextArea(self.setup.state["fields"].get(key, ""), id=key, tab_behavior="focus")]

    def widgets(self):
        s = self.step
        if s == 0:
            yield Static("Welcome to JobAgent setup", classes="welcome-title")
            yield self.copy("This wizard connects your resume, Gmail and Discord.\nYou review and submit applications yourself.")
            yield Static("1. Check this computer and review your resume.\n2. Connect your model, Discord and Gmail.\n3. Test a sample package and choose your schedules.", classes="journey")
            yield self.copy("Tab / Shift+Tab moves between controls. Enter activates a button.\nSpace toggles a checkbox. Alt+Left / Alt+Right moves between steps.")
            yield self.copy("Have your resume and account logins ready. We'll check Windows, Word, Python, Node.js, Docker and Hermes along the way.")
            yield Static(f"Workspace\n{self.setup.root}\n\nSave and exit anytime. Run jobagent setup to pick up here.", classes="location", markup=False)
        elif s == 1:
            yield self.copy("Check this computer first. Missing software opens its official installation guide; after installing, reopen this wizard so it can detect the new commands.")
            yield Button("Check computer", id="computer", variant="primary")
            yield Static("Missing something? Open its installation guide.", classes="field-label")
            yield Vertical(*[Button(f"{key.title()} ↗", id="link_" + key)
                             for key in ("python", "node", "docker", "hermes", "word")], id="install-links")
            yield self.copy("Install project dependencies downloads the DOCX builder package and initializes the local tracker if needed. Existing applications stay intact.")
            yield Button("Install project dependencies", id="install")
        elif s == 2:
            yield self.copy("Use your existing Hermes provider and model. Detect it first; authentication stays in Hermes. Model checks and resume extraction may use your provider balance.")
            yield Button("Show configured model", id="model_name", variant="primary")
            yield Button("Open Hermes setup", id="hermes_setup")
            yield self.copy("Last reviewed model: " + self.setup.state["fields"].get("approved_model", "Not detected yet"))
            yield Checkbox("Use the displayed model for a small verification request", id="consent_model")
            yield Button("Verify model", id="model")
        elif s == 3:
            yield self.copy("Choose a resume or paste its text. Extraction sends that text to your configured model. Review every fact in the editable profile below before confirming.")
            yield from self.field("resume_path", "Resume file (PDF or DOCX)")
            yield from self.area("resume_text", "Or paste resume text")
            yield Checkbox("Send this resume to my configured model for extraction", id="consent_resume")
            yield Button("Extract facts", id="extract", variant="primary")
            yield Button("Load existing profile", id="existing_profile")
            yield from self.area("profile_text", "Review extracted facts (editable YAML)")
            yield Checkbox("I reviewed these facts and confirm they are accurate", id="consent_profile")
            yield Button("Confirm verified profile", id="profile")
        elif s == 4:
            yield self.copy("These preferences guide job evaluation. Write concrete restrictions, such as countries you can work in or roles you want excluded.")
            for key, label in (("roles", "Target roles"), ("seniority", "Seniority"), ("locations", "Locations / work authorization constraints"),
                               ("work_setup", "Remote / hybrid / on-site"), ("exclusions", "Hard exclusions (optional)")):
                yield from self.field(key, label)
            yield Button("Save preferences", id="preferences", variant="primary")
        elif s == 5:
            yield self.copy("1. Choose or create your private Discord server.\n2. Create the eight channels below. In each channel: Edit Channel → Integrations → Webhooks → New Webhook → Copy URL.\n3. For chat, run Hermes gateway setup, connect your Discord bot, and restrict access to your user ID. Enable Message Content Intent in the Developer Portal and invite the bot to your server.")
            yield Button("Discord Developer Portal ↗", id="link_discord")
            yield Button("Open Hermes gateway setup", id="gateway_setup")
            yield self.copy("Existing webhook values stay hidden and are reused when fields are blank. New values are stored only in secrets-discord.json after verification, never in saved wizard state.")
            for channel in CHANNELS:
                yield from self.field("secret_" + channel.replace("-", "_"), channel + " webhook URL", password=True)
            yield Checkbox("Check these Discord webhooks and save new connections", id="consent_discord")
            yield Button("Verify Discord connections", id="discord", variant="primary")
        elif s == 6:
            yield self.copy("Connect Gmail in your browser; OAuth credentials remain in n8n. Keep n8n on localhost:5678. Existing n8n settings are preserved.")
            yield from self.field("timezone", "Timezone (IANA; detected from Windows)")
            yield Button("Start / check n8n", id="n8n")
            yield Button("Open n8n ↗", id="link_n8n")
            yield Button("Gmail authorization guide ↗", id="link_oauth")
            yield self.copy("In n8n: create your owner account, add a Gmail OAuth2 credential, then import n8n/workflows/backfill-fetch.json and fetch-message-bodies.json. Select your Gmail credential in each Gmail node and publish both workflows.\n\nIn Gmail, create labels Job Search/Job Alerts, Job Search/Application Updates, and Job Search/Interviews & Offers, and add filters for your job-board emails.\n\nSearch for a harmless test email below and choose a result. The test reads metadata and body; it never marks mail processed.")
            yield from self.field("gmail_query", "Gmail search (e.g. subject:application newer_than:7d)")
            yield Checkbox("Search my Gmail and read the test message I select", id="consent_gmail")
            yield Button("Find test messages", id="gmail_search")
            selected = self.setup.state["fields"].get("message_id", "")
            yield Label("Select a test message", classes="field-label")
            yield Select([("Previously selected message", selected)] if selected else [], id="message_choice",
                         value=selected if selected else Select.NULL)
            yield from self.field("message_id", "Selected message ID (filled automatically)")
            yield Button("Verify Gmail", id="gmail", variant="primary")
        elif s == 7:
            yield self.copy("The final test rechecks the computer, model, Discord and selected Gmail message. It uses your confirmed profile to match a fictional sample job, validates its cover letter, and builds DOCX/PDF files with Word.")
            yield self.copy("It posts a clearly labeled SAMPLE package, including your resume, to ready-to-apply. Sample files stay in output/setup/sample; the real application tracker is untouched. Retrying posts another sample.")
            yield Checkbox("Run model calls, reread my selected email, and post the sample package to Discord", id="consent_verify")
            yield Button("Verify the full flow", id="verify", variant="primary")
            yield self.copy("Also test interactive chat: start the Hermes gateway, then @mention your bot in #hermes and ask it to read "
                            + str(self.setup.directory / "runtime/job-hunt/SKILL.md")
                            + " and explain the draft-only rule. This personalized copy is created by the full-flow check. Confirm the reply before activation.")
            yield Button("Show gateway status", id="gateway_status")
            yield Checkbox("My bot replied correctly in Discord", id="chat_verified", value=self.setup.state["fields"].get("chat_verified", False))
        elif s == 8:
            yield self.copy("Review your automation. Jobs run only while Docker and the Hermes gateway are running. Setup creates missing jobs; conflicting existing jobs require review and are never replaced.")
            for key, label in (("timezone", "Timezone (must match Hermes)"), ("scan_hours", "Daily scan hours, comma-separated (0–23)"),
                               ("interval", "Email checks every N minutes (1–59)"), ("report_hour", "Daily report hour (0–23)")):
                yield from self.field(key, label)
            yield Button("Review activation plan", id="plan")
            yield self.copy("Activation installs personalized job-hunt instructions and two script launchers into Hermes, then enables the three schedules shown above. The selected model is pinned to the two reasoning jobs; the report uses no model. Other Hermes settings stay unchanged.")
            yield Checkbox("Install these instructions and enable these recurring jobs", id="consent_activate")
            yield Button("Enable automation", id="activate", variant="primary")
            yield Button("Finish without automation", id="exit_later")

    async def show_step(self):
        self.query_one("#step-title", Static).update(f"{self.step + 1} / {len(STEPS)}  {STEPS[self.step]}")
        page = self.query_one("#page", VerticalScroll)
        await page.remove_children()
        await page.mount(*list(self.widgets()))
        page.scroll_home(animate=False)
        self.query_one("#steps", ListView).index = self.step
        self.query_one("#back", Button).disabled = self.step == 0
        self.query_one("#next", Button).disabled = self.step == len(STEPS) - 1
        self.query_one("#next", Button).label = "Get started" if self.step == 0 else "Continue"
        self.setup.state["step"] = self.step
        self.refresh_rail()

    def refresh_rail(self):
        for i, item in enumerate(self.query_one("#steps", ListView).children):
            complete = i in REQUIRED and all(key in self.setup.state["checks"] for key in REQUIRED[i])
            item.set_class(i == self.step, "current")
            item.set_class(complete, "complete")
            marker = ">" if i == self.step else "OK" if complete else f"{i + 1:02}"
            item.query_one(Label).update(f"{marker:>2}  {STEPS[i]}")

    def capture(self):
        fields = self.setup.state["fields"]
        before = dict(fields)
        for widget in self.query("Input"):
            if not widget.password:
                fields[widget.id] = widget.value
        for widget in self.query("TextArea"):
            fields[widget.id] = widget.text
        if self.query("#chat_verified"):
            fields["chat_verified"] = self.query_one("#chat_verified", Checkbox).value
        for check, keys in (("profile", ("resume_path", "resume_text", "profile_text")),
                            ("preferences", ("roles", "seniority", "locations", "work_setup", "exclusions")),
                            ("gmail", ("gmail_query", "message_id"))):
            if any(before.get(k, "") != fields.get(k, "") for k in keys):
                self.setup.state["checks"].pop(check, None)
                self.setup.state["checks"].pop("verified", None)
        self.setup.save()

    def result(self, text, error=False):
        widget = self.query_one("#result", Static)
        widget.update("Error: " + text if error else text)
        widget.set_class(error, "error")

    async def action_next(self):
        if self.busy:
            return
        self.capture()
        missing = [key for key in REQUIRED.get(self.step, ()) if key not in self.setup.state["checks"]]
        if missing:
            self.result("Complete this step first: " + ", ".join(missing), True)
            return
        if self.step < len(STEPS) - 1:
            self.step += 1
            await self.show_step()

    async def action_back(self):
        if not self.busy and self.step:
            self.capture()
            self.step -= 1
            await self.show_step()

    def action_save(self):
        if self.busy:
            self.result("An operation is running. Its result will be saved when it finishes.")
            return
        self.capture()
        self.result("Progress saved. Reopen with jobagent setup to continue.")

    def action_save_exit(self):
        if self.busy:
            self.exit_after_work = True
            self.result("Setup will save and exit when this operation finishes, so no write is interrupted.")
            return
        self.capture()
        self.exit()

    async def on_list_view_selected(self, event):
        if not self.busy and event.list_view.index != self.step:
            self.capture()
            self.step = event.list_view.index
            await self.show_step()

    def on_select_changed(self, event):
        if event.select.id == "message_choice" and event.value is not Select.NULL:
            self.query_one("#message_id", Input).value = str(event.value)

    def consent(self, name):
        if not self.query_one("#consent_" + name, Checkbox).value:
            raise SetupError("Review the action and check its confirmation box first.")

    async def on_button_pressed(self, event):
        key = event.button.id
        if self.busy:
            return
        try:
            if key == "back":
                await self.action_back()
                return
            if key == "next":
                await self.action_next()
                return
            if key in ("exit", "exit_later"):
                self.action_save_exit()
                return
            if key.startswith("link_"):
                webbrowser.open(LINKS[key[5:]])
                return
            self.capture()
            if key in ("hermes_setup", "gateway_setup"):
                with self.suspend():
                    subprocess.run(["hermes", "setup"] if key == "hermes_setup" else ["hermes", "gateway", "setup"], check=False)
                self.result("Returned from Hermes. Run the verification check to continue.")
                return
            if key == "existing_profile":
                path = self.setup.root / "profile/career-profile.yaml"
                if not path.is_file():
                    raise SetupError("No existing profile found. Import your resume first.")
                self.query_one("#profile_text", TextArea).load_text(path.read_text(encoding="utf-8"))
                self.result("Existing profile loaded for review. Its contents have not changed.")
                return
            for action, consent in (("model", "model"), ("extract", "resume"), ("profile", "profile"),
                                    ("discord", "discord"), ("gmail_search", "gmail"), ("gmail", "gmail"), ("verify", "verify"), ("activate", "activate")):
                if key == action:
                    self.consent(consent)
            if key == "activate" and not self.setup.state["fields"].get("chat_verified"):
                raise SetupError("Confirm the bot's Discord reply on the Verify step before activation.")
            secrets = {channel: self.query_one("#secret_" + channel.replace("-", "_"), Input).value.strip()
                       for channel in CHANNELS} if key == "discord" else {}
            self.busy = True
            self.query_one("#busy").styles.display = "block"
            self.result("Working… This can take a few minutes. Your progress stays saved.")
            self.perform(key, secrets)
        except (SetupError, OSError) as exc:
            self.result(str(exc) if isinstance(exc, SetupError) else "Could not save progress. Check folder permissions and retry.", True)

    @work(thread=True, exclusive=True)
    def perform(self, key, secrets):
        f = self.setup.state["fields"]
        try:
            if key == "computer":
                message = self.setup.computer()
            elif key == "install":
                message = self.setup.install()
            elif key == "model_name":
                selected = self.setup.model()
                self.setup.state["fields"]["approved_model"] = selected
                self.setup.save()
                message = "Configured model: " + selected + ". Review it before checking the confirmation box."
            elif key == "model":
                message = self.setup.check_model()
            elif key == "extract":
                text = self.setup.draft_profile(f.get("resume_path", ""), f.get("resume_text", ""))
                self.call_from_thread(self.query_one("#profile_text", TextArea).load_text, text)
                self.setup.state["fields"]["profile_text"] = text
                self.setup.save()
                message = "Facts extracted. Review and edit them, then confirm below."
            elif key == "profile":
                message = self.setup.confirm_profile(f.get("profile_text", ""), "" if f.get("resume_text", "").strip() else f.get("resume_path", ""))
            elif key == "preferences":
                message = self.setup.preferences({k: f.get(k, "") for k in ("roles", "seniority", "locations", "work_setup", "exclusions")})
            elif key == "discord":
                message = self.setup.discord(secrets)
            elif key == "n8n":
                message = services.start_n8n(self.setup, f["timezone"])
            elif key == "gmail":
                message = self.setup.gmail(f.get("message_id", ""), f.get("gmail_query", ""))
            elif key == "gmail_search":
                messages = self.setup.gmail_candidates(f.get("gmail_query", ""))
                options = [(f"{m.get('date', '')[:10]}  {m.get('subject', '(no subject)')[:80]}", m["message_id"]) for m in messages]
                self.call_from_thread(self.query_one("#message_choice", Select).set_options, options)
                message = "Choose a test message from the results, then verify Gmail."
            elif key == "gateway_status":
                from .setup_core import run
                run(["hermes", "gateway", "status"], self.setup.root)
                message = "Gateway status command succeeded. Confirm that your bot responds in Discord."
            elif key == "plan":
                message = (f"Model: {self.setup.model()}\nTimezone: {f['timezone']}\n"
                           f"Scan hours: {f['scan_hours']} · Email interval: {f['interval']} minutes · Report hour: {f['report_hour']}\n"
                           "Installs personalized instructions and enables three jobs; existing conflicts stop activation.")
            elif key == "verify":
                message = services.verify(self.setup)
            elif key == "activate":
                message = services.activate(self.setup, f["timezone"], f["scan_hours"], f["interval"], f["report_hour"])
            else:
                raise SetupError("Unknown setup action.")
            self.call_from_thread(self.finish, message, False)
        except SetupError as exc:
            self.call_from_thread(self.finish, str(exc), True)
        except Exception:
            self.call_from_thread(self.finish, "This step could not finish. Check your input and service configuration, then retry. Saved progress is intact.", True)

    def finish(self, message, error):
        self.busy = False
        self.query_one("#busy").styles.display = "none"
        self.result(message, error)
        self.refresh_rail()
        if self.exit_after_work:
            self.action_save_exit()
