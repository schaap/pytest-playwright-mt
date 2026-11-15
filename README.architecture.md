# `pytest-playwright-mt` Architecture

This document details the architecture of the inner workings of the plugin. This is meant as a guide for developers
trying to understand or work on the code of this plugin.

It is *not* sufficient to read just this document. Readers are expected to have read the [main README](./README.md).


# Fixture and Instances

The main entry point for using `pytest-playwright-mt` is the `playwright_mt` fixture. This fixture collects all the
command line arguments, packs them into a `PlaywrightMTFixture` and attaches a test-wide `ArtifactCollector` to it. The
latter is obtained via the `artifact_collector` fixture, more information in
[the `ArtifactCollector` section](#artifact-collector).

The `PlaywrightMTFixture` is basically just a factory holding all the settings for the next instance(s). The settings
can be tweaked directly on the object, which is an unusual pattern that was nonetheless chosen to prevent lots of
arguments on function calls that are expected to be pointless for a large majority of the use cases, and to be the same
within a test for just about all the remaining cases.

`PlaywrightMTFixture.create_instance()` is the factory method that then finally creates a Playwright instance. The
caller is not given the Playwright instance itself, but rather an instance of `PlaywrightMT`. This class implements a
facade for Playwright's main object, and exposes its configuration (read-only) for easy reference. Apart from launching
browsers (the facade part), `PlaywrightMT` provides a class method to obtain session-unique context names. When it is
created, a `PlaywrightMT` instance is also given its own child artifact collector (see
[Tiered Artifact Collection](#tiered-collection) for more information).

Note that `PlaywrightMTFixture.create_instance()` is a context manager. The actual context manager is the `PlaywrightMT`
instance. To ensure proper cleanup, this plugin enforces use of a context manager rather that Playwright's own reliance
on the user to call `.close()`.

If one really wants to, the underlying `Playwright` object can be obtained from the `PlaywrightMT` instance. This is
strongly discouraged, though, as all of the plugin functionality basically hinges on the
[instrumentation](#instrumentation) of the Playwright objects. The `Playwright` object itself is not instrumented, so
that all falls apart when the caller works directly on the underlying instance.


# Browser Parametrization

The selection of browsers from the command line is an odd trick. The option is in the `option.py` module, but that
simply gathers the data. The `playwright_mt_fixture.py` module contains a hook on `pytest_generate_tests`, which is
where the magic happens. Here the option is used to parametrize every test that uses the `browser_name` fixture,
directly or indirectly (e.g. via the `playwright_mt` fixture). The `browser_name` fixture is a real fixture, but that is
primarily a fallback option and a convenience for tooling. In the hook `browser_name` is injected as a pytest
parametrization, listing each requested browser as possible value.

Tests using `pytest-playwright-mt` can indicate that they will not use any parametrized browsers, via the
`pytest.mark.static_browser` marker. These tests are not parametrized for `browser_name` in that they will not receive
different values for the parameter. They still *are* parametrized for `browser_name` with only the default browser as
the single possible value. This is a technical requirement to not have the `browser_name` fixture fall apart if it is
ever called upon. It also greatly simplifies the machinery of the `playwright_mt` fixture, preventing special cases for
dealing with those `pytest.mark.static_browser` methods.

Test can also declare that they wish to skip certain browsers (`pytest.mark.skip_browser`) or only run on specific
browsers (`pytest.mark.only_browser`). This directly hooks into the `browser_name` parametrization: the markers'
functionality is implemented as a dynamic skip based on `browser_name`. The skip is implemented in a
`pytest_runtest_setup` hook in `playwright_mt_fixture.py`.


# Instrumentation

The automatic collection of artifacts from the Playwright browsers requires hooking into the `Browser`,
`BrowserContext` and `Page` objects. Because Playwright itself does not provide any functionality for this, this is done
by monkey-patching some functions on each of these objects with a wrapped version that has additional instrumentation.
The instrumentation is all implemented in `instrumentation.py`. The instrumentation itself is executed by the
`instrument_playwright_object()` function.

## Instrumentation for the Sake of Instrumentation

The first part of the instrumentation is to make sure that the instrumentation reaches all the objects. The `Browser`
object is instrumented when it's created by the `PlaywrightMT` instance, the last object in the chain that belongs to
this plugin. This also registers the `Browser` with the `PlaywrightMT` instance for eventual closing.

The following instrumentations ensure that everything is instrumented:

- `Browser`
  - `new_context()`
    - Instruments the new `BrowserContext` and registers it with its `Browser`.
    - Gives the `BrowserContext` its session-unique name, obtained from `PlaywrightMT` (see
      [Fixture and Instances](#fixture-and-instances)).
  - `new_page()`
    - This is a full replacement that basically redefines `new_page()` as `new_context().new_page()`.
    - Registers the throw-away context with the page (the only object that is returned to the caller) as its dedicated
      context.
- `BrowserContext`
  - `new_page()`
    - Instruments the new `Page` and registers it with its `BrowserContext`.
    - Gives the `Page` its `BrowserContext`-unique name and also notes that context's name on the `Page`.

With everything instrumented, the instrumentation of the `close()` calls neatly ties things off:

- `Page`
  - `close()`
    - Calls `.close()` on its dedicated context, if the page was created via `BrowserContext.new_page()`.
- `BrowserContext`
  - `close()`
    - Calls `.close()` on all its registered `Page` objects.
- `Browser`
  - `close()`
    - Calls `.close()` on all its registered `Browser` objects.
    - Deregisters itself from its `PlaywrightMT` parent object.

Note the absences of deregistration other than `Browser`. These are not needed and might, in fact, break other
funcionality.

## Instrumentation for Actual Functionality

The instrumentation's final goal is to provide functionality. The instrumentations provide the following services:

- `Browser`
  - `new_context()`
    - Collects, combines and forwards all arguments to the new context from the following sources:
      - pytest command line arguments, including:
        - Setting up device emulation (which itself explosed into a list of arguments);
        - Enabling video recording.
      - pytest markers (`browser_context_args`);
      - Direct arguments to `new_context()`.
    - Sets up tracing on the `Browser`.
- `BrowserContext`
  - `close()`
    - Finishes tracing and collects the trace.
    - Store all the videos created by all its registered `Page` objects and collect them.
- `Page`
  - `close()`
    - Screenshot the page and collect that screenshot.

The actual bits of most functionality are each pretty simple. Retrieve some settings, perform one or two API calls,
possibly register an artifact if it became available. Only figuring out all the arguments for creating a
`BrowserContext` is non-trivial. This should not be surprising when you see that that's basically where everything is
set up.

The nasty part, and the reason instrumentation is needed, is the timing of all this. Some things need to be done just
before a Playwright API call, some just after, some at unexpected moments (videos are only guaranteed to be stable
*after* the context of the pages that made them has been closed).


# Artifact Collector

The `ArtifactCollector` is actually a stand-alone plugin-in-a-plugin, implemented in the `artifact_collector.py` module.

## Securing Artifacts

The basic idea of `ArtifactCollector` is pretty simple: artifacts (just files or directories) registered with
`register_artifact()` are kept in a list. When instructed to `secure_artifacts()`, each of those artifacts is then moved
from its original location to its destination.

To support retaining artifacts only when a test fails (`RecordingOption.RETAIN_ON_FAILURE`) the registration includes
when the artifact should be secured, and `secure_artifacts()` can be given a final result to actually act on that.

The final result of a test is not available until the test has finished, to be exact not until the
`pytest_runtest_makereport()` for the `call` stage. That function is hooked in `artifact_collector.py` to call
`secure_artifacts()` on the test-wide `ArtifactCollector`. As this is too late to still be parsing command line
arguments, the command line argument `--output` is processed by the `artifact_collector` fixture. The fixture uses
`ArtifactCollector.set_destination_directory()` to inform it ahead of time where artifacts need to be secure to when
`secure_artifacts()` is called after the test has finished.

## Tiered Collection

To support intermediate collection of artifacts from temporary storage to some intermediate storage that *will* survive
until after the test, `ArtifactCollector` allows creating a child collector via `create_child_collector()`. This child
collector will funcion the same way, except:

- A child collector can be given its own [artifact move function](#custom-artifact-move-functions).
- A child collector can secure artifacts to an intermediate storage.
- After securing an artifact, a child collector immediately registers that artifact with its parent collector for
  further securing at a later stage.

The root of the collector is commonly obtained via the `artifact_collector` fixture, which will create a test-wide
`ArtifactCollector`.

## Custom Artifact Move Functions

To support complex situations, such as environments where a simple `shutil.move` can't actually move an artifact from
its source to its destination, the user can inject a custom move function to be used. This function is only used when
securing artifacts.

- The global default artifact move function is kept in `ArtifactCollector.default_artifact_move_func`.
- When constructing an `ArtifactCollector`, one can pass an artifact move function. If `None` is passed then the global
  default in `ArtifactCollector.default_artifact_move_func` is used.
- When creating a child artifact collector, one can pass an artifact move function. If `None` is passed then the
  parent's artifact move function is used.

Outside of the object hierarchy, the test-wide artifact collector can be constructed with a test-specific artifact move
function by marking the test with `pytest.mark.artifact_move_func`. This marker is retrieved in the `artifact_collector`
fixture. If it's not present, then no custom function is passed to the `ArtifactCollector`, which hence uses the global
default.
