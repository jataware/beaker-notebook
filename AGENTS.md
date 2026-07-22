# Working in beaker-notebook

Notes for agents and humans working on this repository. Covers running Beaker from a checkout,
where configuration and credentials actually come from, how contexts and skills are discovered, and
how to record a demo video of a Beaker session without producing something unusable.

## Running from a checkout

The published wheel contains a prebuilt frontend at `src/beaker_notebook/app/ui`, listed under
`[tool.hatch.build] artifacts`. A source checkout does not have it, and it is gitignored, so an
editable install of this repository starts a server with no UI. Two ways to get one:

```bash
make init          # builds the Vue frontend into src/beaker_notebook/app/ui (needs node/npm)
```

or, if you only changed Python and want to skip the frontend build, copy the prebuilt assets out of
an installed wheel:

```bash
cp -R "$(python -c 'import beaker_notebook,os;print(os.path.dirname(beaker_notebook.__file__))')/app/ui" \
      src/beaker_notebook/app/ui
```

Then install and run:

```bash
pip install -e .
beaker notebook          # serves on localhost:8888
```

**`uv run` will undo an editable install.** In a project with a `uv.lock`, `uv run` re-syncs the
environment before executing, which replaces an editable `beaker-notebook` with the locked version
from PyPI. The revert is silent and the symptom is that your changes appear to have no effect. When
testing a checkout, call the virtualenv binary directly:

```bash
.venv/bin/beaker notebook     # uses your editable install
uv run beaker notebook        # re-syncs first, reverting it
```

## Configuration and credentials

Config file resolution order (`lib/config.py`):

1. `./.beaker.conf` in the current working directory
2. `~/.config/beaker.conf`
3. `~/.beaker.conf`

`beaker config find` reports which one is in use. The wording distinguishes the two cases: it prints
`Configuration location:` when a file exists and `Default location is:` when none does. `beaker
config update` walks through the fields interactively.

**A blank key in the config does not mean no key.** Provider classes fall back to environment
variables. `archytas.models.openrouter`, for example, resolves in this order:

```python
kwargs.get("api_key") or self.config.api_key or os.environ.get("OPENROUTER_API_KEY", "")
```

So `OPENAI_API_KEY`, `GEMINI_API_KEY` and friends in the shell environment will satisfy an otherwise
unconfigured install. This matters when you are trying to reproduce a first-run experience: blanking
the config file is not enough, and neither is deleting it. You also need an environment with none of
those variables set. A container is the reliable way to get one.

### The provider dialog

The UI opens a modal titled **Model Provider Configuration** when the kernel emits an
`llm_auth_failure` iopub message (`BaseInterface.vue`). It is not reachable from a menu, so it only
appears when a model call actually fails to authenticate. The gear icon at the bottom left opens the
**Beaker Config** panel, which edits the same settings deliberately.

## Contexts

Contexts are discovered through entry-point metadata that Beaker's build hook writes at install
time, not by scanning at runtime. Moving or renaming a context breaks discovery until you reinstall:

```bash
beaker project update      # or: pip install -e .
beaker context list        # confirm the slug appears
```

The context a session opens on is the installed context with the lowest `WEIGHT`
(`BeakerKernel.start_default_context`). `DefaultContext` is 10 and the base class default is 50, so a
context that wants to be the default needs a weight below 10. `BEAKER_DEFAULT_CONTEXT` overrides the
choice for one run.

Useful endpoints when testing without a browser:

* `GET /beaker/contexts/` lists installed contexts and their subkernels.
* `GET /beaker/integrations/{session_id}` returns each integration with its resources, which is the
  most direct way to assert on what the agent can actually see.

Procedures live in `procedures/<subkernel-slug>/<name>.py` beside the context module and are
discovered by `BeakerContext.discover_procedures()`. They are Jinja templates rendered before
execution, so `{{`, `{%` and `{#` are template syntax. Ordinary f-strings are fine. `get_code(name)`
resolves against the discovered set, which means a procedure in the wrong directory raises the same
error as one that does not exist.

## Skills

A context's skills come from a `skills.json` file or a `skills/` directory sitting next to
`context.py`. Separately, Beaker attaches the skills it finds in the user's global roots (`.agents`
and `.beaker` under both the working directory and the home directory) to *every* context. On a
machine with a large personal skill library that can be a hundred or more extra skills, and every
one of their descriptions goes into the system prompt for every session. A focused context usually
wants to suppress them.

Skills can be local paths or `https` URLs. For a URL, Beaker appends `SKILL.md` to the base, so the
trailing slash is load bearing: without it the last path segment is stripped.

```json
["https://raw.githubusercontent.com/org/repo/main/skills/name/"]
```

**A skill that fails to load is dropped silently.** `discover_integrations` catches per-source
failures so one bad entry cannot take down the others, but a failure never becomes visible state.
An unreachable host yields zero skills, an empty prompt, and no error anywhere the user will look.
When an agent seems unaware of a library it should know about, check whether its skill loaded before
suspecting the prompt.

## Tests

```bash
pytest                              # whole suite
pytest tests/integrations/skills    # skill discovery, provider, and tool behaviour
```

`asyncio_mode = auto` is set, so async tests need no decorator. Skill tests build providers against
`tmp_path` fixtures and patch `_get_skill_search_roots`, which keeps a developer's real
`~/.beaker/skills` out of the run. Do the same in new tests. A test that reads the real search roots
passes or fails depending on whose machine it runs on.

## Recording a demo video

Playwright records the browser session directly, so there is no screenshot stitching and no screen
recording permission to grant. Video is configured on the browser context, not the page, and is
finalized when the context closes.

```python
context = browser.new_context(
    viewport={"width": 1600, "height": 1000},
    record_video_dir="out",
    record_video_size={"width": 1600, "height": 1000},
)
page = context.new_page()
...
video_path = page.video.path()
context.close()          # writes the file
```

Three things make Beaker specifically awkward to record. All three produce output that looks
plausible until you watch it.

### Wait for the agent turn to finish, not for the page to stop changing

An agent turn runs for anywhere from ten seconds to several minutes, streams intermittently, and
goes quiet in the middle while a tool call executes. Waiting for the transcript to stop growing
therefore fires early, and the next prompt gets submitted while the agent is still working. The
result is a recording with several prompts stacked before any answer, which is not obvious until you
read the transcript afterwards.

The UI renders an `Agent Running` block for exactly as long as a turn is in flight. Gate on that.
Wait for it to appear, then wait for it to stay absent across several consecutive polls:

```python
RUNNING = "Agent Running"

def wait_for_turn(page, appear_s=25, turn_s=600, clear_polls=4):
    start = time.time()
    while time.time() - start < appear_s:          # turn starts
        if RUNNING in page.inner_text("body"):
            break
        page.wait_for_timeout(1000)
    clear = 0
    while time.time() - start < turn_s:            # turn ends and stays ended
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        clear = 0 if RUNNING in body else clear + 1
        if clear >= clear_polls:
            return True
    return False
```

The initial page load also needs a generous wait. Context setup runs the subkernel preamble and,
for a context with remote skills, fetches them over the network before the session is usable.

### Scroll the transcript, not the focused element

`page.keyboard.press("End")` scrolls whatever has focus. After typing a prompt that is the query
textarea, so the transcript does not move and newly rendered output stays below the fold. Drive the
scroll containers directly:

```python
SCROLL_JS = """() => {
  for (const el of document.querySelectorAll('*')) {
    if (el.scrollHeight > el.clientHeight + 40) {
      const oy = getComputedStyle(el).overflowY;
      if (oy === 'auto' || oy === 'scroll') el.scrollTop = el.scrollHeight;
    }
  }
}"""
page.evaluate(SCROLL_JS)
```

Call it while polling during a turn and again after the turn ends, otherwise figures render off
screen and the recording finishes mid transcript.

### Ask for inline figures and tell the agent not to read them back

Left to itself the agent tends to save a figure to disk and then load it back so it can describe what
it plotted. That round trip fails against any model without image input support, and the failure is a
raw traceback in the notebook:

```
openai.NotFoundError: Error code: 404 - 'No endpoints found that support image input'
```

Appending an instruction to each plotting request avoids it entirely:

> Render the figure inline in the notebook cell. Do not save it to a file and do not try to read the
> image back.

Assert on the result rather than trusting it. Inline figures are `img` elements with data URI
sources, so the count is a direct check that plotting worked:

```python
page.locator("img[src^='data:image']").count()
```

### Encoding

Playwright writes VP8 webm. Convert, and speed up, with ffmpeg:

```bash
ffmpeg -i page.webm -c:v libx264 -pix_fmt yuv420p -crf 26 -movflags +faststart demo.mp4
ffmpeg -i demo.mp4 -filter:v "setpts=PTS/6" -an fast.mp4          # 6x
```

For a README, note that GitHub's markdown sanitizer strips `<video>` elements. A repository hosted
mp4 renders as a link regardless of how it is embedded, and the raw URL is served as
`application/octet-stream`. Use an animated GIF, which renders inline as an `img`.

Generate GIFs with a two pass palette. For screen recordings specifically, use the full 256 colour
palette and disable dithering: flat UI regions quantise cleanly, and dithering adds noise that reads
as grain on text.

```bash
ffmpeg -i demo.mp4 -vf "setpts=PTS/20,fps=4,scale=1200:-1:flags=lanczos,palettegen=max_colors=256:stats_mode=diff" pal.png
ffmpeg -i demo.mp4 -i pal.png -lavfi "setpts=PTS/20,fps=4,scale=1200:-1:flags=lanczos[v];[v][1:v]paletteuse=dither=none:diff_mode=rectangle" demo.gif
```

Resolution matters more than frame rate here. Downscaling 1600px screen content below about 1000px
turns anti-aliased code into mush, while dropping to 4 or 5 fps costs little because the content is
mostly static with occasional scrolls. Cropping is not a reliable way to shrink a GIF: removing
static regions such as an empty side panel can make the file larger, because interframe compression
encodes those regions almost for free and the remaining frame is proportionally more motion.
