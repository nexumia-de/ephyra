---
type: Decision Record
title: No colours taken from the artwork
description: Detail pages keep Jellyfin's blue accent and libadwaita's surfaces instead of tones picked from each item's backdrop or poster; the backdrop itself carries the item's colours.
tags: [decision, design, colour, accessibility, detail-page]
generated: { by: claude-code/2.1.330, at: 2026-11-22T12:00:00Z }
sources:
  - id: issue-8
    resource: https://github.com/nexumia-de/ephyra/issues/8
    title: Issue 8, idea - tint detail pages with colours from the artwork
  - id: wcag-contrast
    resource: https://www.w3.org/TR/WCAG22/#contrast-minimum
    title: WCAG 2.2, 1.4.3 Contrast (Minimum), 4.5:1 for text
---

# Status

Accepted (2026-11-22). Decided in the issue clean-up without asking the
owner; the owner can reopen issue 8 to change it.

# Context

The idea from the owner's question about Material You[^issue-8]: take a
few tones from an item's backdrop or poster and use them for the detail
page's fade and accent, as Android does with the wallpaper. It needed a
decision first, because it touches the accent rule of the
[Jellyfin look](jellyfin-style.md) and the toolkit's rule that each app
has one accent colour set only through `--accent-bg-color`.

# Decision

Detail pages keep Jellyfin's blue accent and libadwaita's surfaces. The
backdrop at the top already shows the item's colours; its fade goes to
the page's own background colour as now ([design](../design.md), rule 6).

# Reasons

- **Contrast.** Artwork tones are arbitrary. A tone taken from a poster
  has to be shifted until text and buttons on it reach 4.5:1 in both
  the dark and the light style[^wcag-contrast]; after that shift little
  of the artwork's colour is left, for posters that are mostly dark or
  mostly grey nothing at all.
- **One accent per app.** The accent marks what is interactive and the
  played badges and progress bars ([design](../design.md), rule 5). If
  it changed with every item, the badge colour would mean nothing and
  Ephyra would stop looking like Jellyfin's apps, which keep their blue
  on every item.
- **Cost on the phone.** Picking tones means decoding and analysing the
  image on each page; the detail page already waits for the backdrop
  over a remote connection.
- **libadwaita.** Recolouring per page means CSS generated at run time
  with hard-coded colours, which the toolkit's design rules exclude for
  chrome.

# Alternatives

- **Tint only the fade below the backdrop** with a darkened average of
  the image: the smallest version of the idea. Rejected for now because
  of the cost above and because the fade into the page background already
  joins backdrop and page.
- **Take the accent from the artwork with a contrast check**: the full
  idea; rejected for the reasons above.

# Consequences

- Issue 8 is closed as not planned.
- If the owner wants it later, start with the fade-only alternative,
  behind a preference, and check it at 360×720 in both styles.

[^issue-8]: Issue 8, idea - tint detail pages with colours from the artwork
[^wcag-contrast]: WCAG 2.2, 1.4.3 Contrast (Minimum)
