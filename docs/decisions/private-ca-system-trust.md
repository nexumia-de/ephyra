---
type: Decision Record
title: A private CA goes into the phone's trust store, not into Ephyra
description: Servers whose certificate comes from the owner's own CA are trusted by adding that CA to the system trust store, which the Flatpak sandbox reads through p11-kit; Ephyra gets no CA file of its own.
tags: [decision, connection, tls, certificates, flatpak]
generated: { by: claude-code/2.1.330, at: 2026-11-22T12:00:00Z }
sources:
  - id: issue-6
    resource: https://github.com/nexumia-de/ephyra/issues/6
    title: Issue 6, servers with a certificate from a private CA
  - id: flatpak-run
    resource: https://github.com/flatpak/flatpak/blob/99e1af1/common/flatpak-run.c
    title: flatpak, flatpak-run.c - p11-kit-trust.module replaced by p11-kit-client.so talking to the host's trust module (read 2026-11-22)
---

# Status

Accepted (2026-11-22). Decided in the issue clean-up without asking the
owner; checking it on the phone is in [owner checks](../owner-checks.md).

# Context

The server certificate is checked against the system's CAs only
([connection](../connection.md)). Owners who run mutual TLS often sign
the server certificate with their own CA too. Issue 6[^issue-6] proposed
a CA file on the setup page, stored next to the client certificate and
given to `phosh_toolkit.http.Client.tls_database`.

# Decision

Ephyra trusts what the system trusts. A private CA is added to the
phone's trust store (on Debian-based phone systems
`/usr/local/share/ca-certificates/<name>.crt` and
`sudo update-ca-certificates`; elsewhere `trust anchor --store <file>`).
The Flatpak sees it: when the host runs p11-kit, Flatpak replaces the
runtime's `p11-kit-trust.module` with a client of the host's trust
module[^flatpak-run], which GnuTLS and so glib-networking use. Ephyra
gets no CA file of its own.

# Reasons

- **One place for trust.** The same CA then works for the browser, the
  proxy-login web view (WebKit uses the same trust), other apps and the
  command line. A CA file in Ephyra would trust the server in the app
  but not in the login web view of a reverse proxy, which the owner uses
  ([connection](../connection.md#proxy-login)).
- **Shared code.** The setup form, the HTTP client and the proxy login
  are phosh-toolkit's; an app-level CA would have to be added there and
  to every app that uses them, for a need the system already covers.
- **No silent weaker check.** A CA picker invites trusting whatever file
  is at hand; the system store is managed deliberately, with root.

# Alternatives

- **CA file on the setup page** (the issue's proposal): needs the
  toolkit's `ConnectionForm`, a stored file per app and the web view's
  own trust handling; rejected for the reasons above.
- **Accept the server certificate on first use (pinning)**: weaker than
  a CA and a second trust model to explain; rejected.

# Consequences

- Without p11-kit on the host, or with a Flatpak older than its p11-kit
  forwarding, the CA is not seen; then setup fails with the TLS error it
  shows today ("Secure connection failed: …").
- If the check on the phone fails, reopen issue 6 and add the CA file to
  phosh-toolkit's `ConnectionForm`, so that every app gets it.

[^issue-6]: Issue 6, servers with a certificate from a private CA
[^flatpak-run]: flatpak, flatpak-run.c
