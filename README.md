# `pytest-playwright-mt`

Playwright integration with pytest in multi-threaded environments.

[Playwright](https://playwright.dev/python/) is a framework for web automation. It comes with pytest integration of its
own, implemented as pytest plugins in the `pytest-playwright` and `pytest-playwright-async` Python packages. Both of
these plugins assume that the pytest test will run a single Playwright instance on its main thread and provide little to
no integrations as soon as multiple (single-threaded) Playwright instances are needed.

This package brings a third flavour: pytest integration for Playwright with support for multiple threads. Some of the
original plugins' functionality is not available, while some additional functionality geared specifically to
multi-threaded support is added.

## Credits

This plugin was modelled after `pytest-playwright` and has taken lots of inspiration for specific solutions, up to and
including adopting parts of the code.

# Usage

Installation is straight-forward: install the package in your pytest environment and the plugin will become available.

You can use the plugin in your test as follows:

```python
from pytest_playwright_mt import PlaywrightMTFixture, playwright_mt


def test_chat_bot_connect(playwright_mt: PlaywrightMTFixture) -> None:
    with playwright_mt.create_instance() as pw:
        page = pw.launch().new_page()
        page.goto("https://chat.test/")
        expect(page.get_by_test_id("user_id")).to_have_text(re.compile(r"user[0-9]+"))
```

The result of calling `playwright_mt.create_instance()` is a `PlaywrightMT` object, which is a facade for Playwright's
own base object. It allows you to launch browsers, using either `launch` or a method for a specific browser. These
methods returna Playwright `Browser` object.

## Multi-threaded Example

A more elaborate example shows multi-threaded use:

```python
from pytest_playwright_mt import PlaywrightMTFixture, playwright_mt


def test_chat_bot_user_id(playwright_mt: PlaywrightMTFixture) -> None:
    user_1_id = ""
    user_2_id = ""

    def user_1() -> None:
        with playwright_mt.create_instance() as pw:
            page = pw.launch().new_context().new_page()
            page.goto("https://chat.test/")
            user_1_id = page.get_by_test_id("user").get_inner_text()

    def user_2() -> None:
        with playwright_mt.create_instance() as pw:
            page = pw.launch().new_context().new_page()
            page.goto("https://chat.test/")
            user_2_id = page.get_by_test_id("user").get_inner_text()

    t1 = Thread(user_1)
    t2 = Thread(user_2)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # The chat.test application correctly hands out a different user ID to a different session
    assert user_1_id != user_2_id
```

This test launches two browsers, each running in their own thread and using their own Playwright instance. There is no
limit to how many instances you create, except for the resources you have available.

You *are* responsible for making sure that each instance runs inside its own dedicated thread. This plugin provides
multi-threaded support for Playwright by giving pytest integration for multiple instances of Playwright, but it does not
alter Playwright itself: Playwright is still very much single-threaded. Leaving out many inconsequential details, the
above test quite literally boils down to:

```python
from playwright.sync_api import playwright


def test_chat_bot_user_id() -> None:
    def user_1() -> None:
        with playwright() as pw:
            page = pw.chromium.launch().new_page()

    def user_2() -> None:
        with playwright() as pw:
            page = pw.chromium.launch().new_page()
```

You could just write that yourself, but it provides no pytest integration. Note that the plain version explicitly
launched Chromium. You could, of course, parametrize for every browser you want to use, but the plugin provides you the
option to pass the browser on the command line.

## Command-line Arguments

This plugin implements most of the command-line arguments that are present in the original plugins. You can specify the
browser to use with `--browser`, and a specific flavour with `--browser-channel`. You can create a more friendly
development experience with `--headed` and `--slowmo`, defaulting the browsers to actually show up and slowing down
Playwright's actions. For debugging `--trace`, `--screenshot` and `--video` allow gathering artifacts from your tests.
Finally, device emulation is available with `--device`.

All these command-line arguments have their equivalents in the plain Playwright API and you will find that the plugins'
integration works the exact same way. The strength is in the flexibility and further integration. You can provide your
choices on the command line, tweaking each run the way you need it, without changing the code. Additionally all the
artifacts you request are gathered entirely for you. See [Artifact Collection](#artifact-collection) for more details.

## Test Markers

There are a few markers specific for interaction between your test and this plugin. You can influence for which browsers
your test is run using the `pytest.mark.skip_browser()` and `pytest.mark.only_browser()` markers. You can declare
additional arguments to be passed whenever a Playwright `BrowserContext` is created with the
`pytest.mark.browser_context_args()` marker.

Two special markers are `pytest.mark.static_browser` and `pytest.mark.dynamic_browser`. This plugin considers the use of
`launch()` to create a browser a best practice, as it allows for the browsers to be specified on the command line. If
your test does not specify otherwise, you will get yourself a very opiniated exception when trying to instantiate a
specific browser. The `pytest.mark.static_browser` marker declares that your test will *only* use specific browsers and
does not need to be parametrized for the browsers passed via the command line. The `pytest.mark.mixed_browser` marker
combines the two modes: your test will be parametrized for the requested browsers, but will also be allowed to
instantiate specific browsers.

## Fixtures

The primary `playwright_mt` fixture, demonstrated above, is the main entrance to using this plugin. The second fixture
that is available for your convenience is `browser_name`, which will reflect the name of the browser for which the test
is currently being run.


# Artifact Collection

Apart from the basic browser customization services, this plugin's biggest function is collecting all the artifacts from
all the instances in your test. For this the `ArtifactCollector` class is used.

An `ArtifactCollector` is created whenever you request the `playwright_mt` fixture. When you create Playwright instances
through `create_instance()` a child artifact collector will be spawned and attached to that instance. This creates a
hierarchy in which the artifacts from a specific instance are first secured to an intermediate location and only later,
when the test has completed, to a final location. This tiered setup allows for the instances to be sandboxed in
(temporary) locations of your choice, locations that can be cleared out after the instance closes without the risk of
losing artifacts.

## Output Location

The main `ArtifactCollector`, the one that is created for the entire test, will secure its artifacts to a final location
with test results. By default this is `./test-results/`, with `.` being wherever you run pytest. The `--output` command
line argument allows you to provide a specific location to secure the artifacts to.

## Secure Your Own Artifacts

`ArtifactCollector` is not limited to securing the artifacts created by Playwright browsers. It is, in fact, not even
linked to those beyond being part of this plugin.

If you have artifacts that should be secured at the end of the test run, you can utilize the `ArtifactCollector`
infrastructure. You can obtain an artifact collector in several ways:

```python
from pytest_playwright_mt import (
    ArtifactCollector,
    PlaywrightMTFixture,
    RecordingOption,
    artifact_collector,
    playwright_mt,
)


def test_with_playwright(playwright_mt: PlaywrightMTFixture) -> None:
    playwright_mt.artifact_collector.register_artifact(Path("test_wide_data"), Path("test_wide"), RecordingOption.ON)

    with playwright_mt.create_instance() as pw:
        pw.artifact_collector.register_artifact(
            Path("instance_data"), Path("from_the_instance"), RecordingOption.RETAIN_ON_FAILURE
        )


def test_without_playwright(artifact_collector: ArtifactCollector) -> None:
    artifact_collector.register_artifact(Path("secure_me"), Path("secured_name"), RecordingOption.ON)
```

The first test shows how to obtain the artifact collectors for an entire test and a specific Playwright instance.
`ArtifactCollector` is thread-safe, but keep in mind that it needs to be able to access the original paths to secure
artifacts: choose wisely which instance to use. An `ArtifactCollector` linked to a Playwright instance will secure its
artifacts when the Playwright instance's context is left, and the test-wide `ArtifactCollector` will only secure its
artifacts during the reporting phase *after* the test has concluded and its result is known.

The second test shows how you can obtain your own `ArtifactCollector` in a test. This works exactly the same as the
`playwright.artifact_collector` in the first test would. Requesting this fixture is, in fact, how the `playwright_mt`
fixture obtains its `ArtifactCollector`.

## Custom Move Functions

Moving artifacts around is normally done using `shutil.move`, which just moves the file across the filesystem. This will
be sufficient for most use cases, but if you want to you can tweak the function that is used for moving artifacts. If
you have a complex environment in which your instances run, with isolation that a simple filesystem move can't reach
across, then you can provide your own specialized version. Want to have the final storage of all the artifacts of a test
run in a database instead of on the filesystem? Tweak the global artifact move function to intercept the move.

# Comparison

`pytest-playwright-mt` is not completely on par with Playwright or its original pytest integration plugins. This is on
purpose and usually dictated by the multi-threaded environment in which this plugin is designed to be used. What
packages you should use depends on your needs.

The advantages of `pytest-playwright-mt` have been listed above. The next sections show what functionality you will not
have, or not have explicit support for, and how this plugin might behave differently than what you expect if you're
already familiar with Playwright.

## Differences with Playwright

Playwright without any pytest integration plugin provides basically the same functionality as this plugin when you do
not use any of its specialized features. You can create multiple plain Playwright instances in separate threads and use
them.

This plugin does not support the following functionality:
- `expect.soft`
  - This feature *requires* a pytest plugin to support, but the implementation is in terms of internals of Playwright.
    As `pytest-playwright-mt` is a third-party plugin, the implementation has not been adopted from `pytest-playwright`.
- `BrowserType.connect`, `BrowserType.connect_over_cdp`, `BrowserType.launch_persistent_context`
  - Running several instances at the same time in a test basically means isolation. Connecting to a running browser or
    launching a browser with a persistent context is considered anti-thetical to that isolation.

Behavioral differences:
- Playwright will not explicitly `.close()` child objects when a parent object is closed: when you close a `Browser`,
  it's like killing that browser without first letting it close its tabs. `pytest-playwright-mt` needs to instrument all
  these objects and *will* cascade the `.close()` call to be able to secure artifacts. If truly needed, the Playwright
  behavior can be restored by setting, for the `Browser` example, `your_browser.close = Browser.close`. Of course, this
  will break artifact collection for that browser.
- Playwright has a specialized implementation of `Browser.new_page()`, but explicitly indicates that it's a convenience
  shortcut that just makes a throw-away context. `pytest-playwright-mt` implements `Browser.new_page()` literally as
  `Browser.new_context().new_page()`, so it can apply all required instrumentation.

## Differences with `pytest-playwright` and `pytest-playwright-async`

The original pytest plugins for Playwright provide you with all the Playwright specific command-line options that
`pytest-playwright-mt` does. In fact, `pytest-playwright` was the example after which `pytest-playwright-mt` was
created, with lots of inspiration for specific implementation issues.

With the original plugins the Playwright instance, is one and the same for your entire test. You obtain the instance via
a fixture and there is no way to create additional instances that support the same pytest integration as that test-wide
instance.

This plugin does not support the following functionality that is provided by the original plugins:
- Most of the fixtures
  - The original plugins are based around the one instance per test, which is what most of the fixtures are used for.
- `asyncio`
  - The original `pytest-playwright-async` provides a full `asyncio` based pytest integration for async Playwright.
    `pytest-playwright-mt` only uses the synchronous version, as it is meant for use for multi-threaded environments.
    The synchronous API was deemed most useful.

Additionally, the following features have simply not been implemented at this time:
- Playwright debugging;
- Fancy artifact reporting, like via `pytest-html`;
- API request tracing (or any specific support for API requests, really);
- Integration with `pytest-base-url`.

Behavioral differences:
- The original pytest plugins detect whether you're likely to have a display available, `pytest-playwright-mt` always
  defaults to headless browsers regardless of your environment.
