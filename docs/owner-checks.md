---
type: Concept
title: Owner checks
description: What only the owner can do after the issue clean-up of 2026-11-22 - checks on the phone and the real server, toolkit tags and CI observations - as one checklist; the closed issues point here.
tags: [owner, checklist, planning]
generated: { by: claude-code/2.1.330, at: 2026-11-22T12:00:00Z }
---

# Why

On 2026-11-22 every open issue was closed: done, decided, or reduced to
steps that need the owner's phone, server, a toolkit tag or a failure
that only shows up in CI. Those steps are collected here instead of
staying open as issues. Nothing below has been run yet; tick an item off
by deleting it and record the result where the item says.

# Checklist

## UI test that sometimes hangs while Home loads (issue 21)

Seen once in the cloud: a run of `tests/test_ui.py` under load failed in
the sign-in test and then hung in the teardown of the mutual-TLS demo
server, its accept thread waiting in `do_handshake()` for a client that
never finished the handshake (py-spy; that run's log was lost). Fixed:
the demo server shakes hands in each connection's own thread with a 10 s
limit, so one stalled client no longer holds up every other request.
Also fixed: the library page asked for the libraries twice during
sign-in, and a replaced page loaded them again on every route change, so
a late 401 signed out a connection of an earlier test and cleared the
next test's token (the "next test fails too" of the issue). The
sign-in test now records every request and answer with times
(`ephyra.connection`, `ephyra.browse`). 20 runs of the two UI tests on
`main` before the fixes passed, so the fix is not proven by a failing
run.

- [ ] Tag phosh-toolkit `v0.7.0` (nexumia-de/phosh-toolkit#59): its
  `testing.run_until()` prints all thread stacks before a timeout.
- [ ] Merge the update of the `phosh-toolkit` pin to `v0.7.0` in
  `de.nexumia.Ephyra.yml` (tag and commit; CI reads the commit).
- [ ] If the test times out again, read "Captured log call" and the
  thread stacks of that run: a `call` without its `answer` names the
  request that was lost. Open a new issue with both.

## "What's New" in the About dialog (issue 7)

`main.about_dialog()` calls `phosh_toolkit.release_notes.add_to(dialog,
APP_ID, source)` when the toolkit has it; checked against
nexumia-de/phosh-toolkit#59 in the cloud (test and a 360×720
screenshot with the row "What's New"). The pinned `v0.5.0` does not have
the module, so released builds show no notes yet.

- [ ] Tag phosh-toolkit `v0.7.0` with #59 merged and merge the pin
  update (same step as for issue 21). That pull request adds
  `changelog.d/whats-new.feature.md` ("The About dialog shows what is new
  in the installed version."); it is left out until then, so a release
  before it does not announce a missing row.
- [ ] Then remove the `ImportError` fallback in `ephyra/main.py` and the
  stand-in branch of `test_about_dialog_shows_whats_new`.
- [ ] Open About in the installed nightly and see the newest release
  under "What's New".
