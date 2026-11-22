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

## Server certificate from a private CA (issue 6)

Decided: the CA goes into the phone's trust store
([decision](decisions/private-ca-system-trust.md)). Not checked on a
device.

- [ ] On the phone: copy the CA as `/usr/local/share/ca-certificates/<name>.crt`,
  run `sudo update-ca-certificates`, then set up Ephyra against a server
  signed by that CA; setup must pass without a TLS error.
- [ ] If it fails, note the error in the decision record and reopen
  issue 6 (a CA file in phosh-toolkit's `ConnectionForm` instead).

## Home and remote route and the client certificate on the phone (issue 1)

Covered in the cloud by `tests/test_connection.py` and
`tests/test_ui.py` against the demo server behind mutual TLS with
certificates made by openssl ([connection](connection.md)). Only the
phone and the owner's server can show the rest.

- [ ] Setup with the remote URL, the `.p12` client certificate and the
  local address; sign in.
- [ ] "Add Current Wi-Fi" shows the home SSID (NetworkManager through
  `--system-talk-name` from the Flatpak).
- [ ] At home the sidebar says "Home network", on mobile data "Remote";
  switching Wi-Fi off and on changes it within a few seconds.
- [ ] A video started at home keeps playing after leaving the Wi-Fi
  (the proxy follows the new route), or note what happens.
- [ ] Without the certificate the setup page says the server asks for a
  client certificate, with the real reverse proxy.
- [ ] Record the results under "Verified" in [connection](connection.md).

## Codecs, hardware decoding, CPU and battery on the phone (issue 2)

Which formats the GNOME 51 runtime's GStreamer decodes on the phone
decides whether *Original* is a good default at home
([playback](playback.md)). The runtime's decoders were listed in the
cloud on x86_64 only; nothing below has run on the phone.

- [ ] Play an H.264, an HEVC and an AV1 file with quality *Original*;
  note which play and which fail ("Convert on the Server" appears).
- [ ] Run `EPHYRA_DEBUG=1 GST_DEBUG=2 flatpak run de.nexumia.Ephyra`:
  which decoder is used (hardware v4l2 or software `avdec_*`).
- [ ] CPU (`top`) and battery drain for 10 min of a 1080p movie, direct
  play and converted on the server.
- [ ] Throughput of the local media proxy for a high-bitrate file
  (stutter?).
- [ ] Set `quality_home` and `quality_away` in `ephyra/settings.py`
  from the results and record the numbers in [playback](playback.md).
