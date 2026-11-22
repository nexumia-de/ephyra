---
type: Guideline
title: Jellyfin look
description: How Ephyra looks like Jellyfin's apps on top of libadwaita - light or dark as the user chooses, Jellyfin's blue accent, poster cards, backdrops - and which toolkit design rules still apply, with a review checklist.
tags: [ui, design, jellyfin, libadwaita, guideline]
resource: ../ephyra/style.css
generated: { by: claude-code/2.1.317, at: 2026-11-03T23:30:00Z }
sources:
  - id: jf-palette
    resource: https://github.com/jellyfin/jellyfin-web/blob/master/src/themes/_base/_palette.scss
    title: jellyfin-web, base theme palette (primary #00a4dc, background #101010, paper #202020)
  - id: jf-card
    resource: https://github.com/jellyfin/jellyfin-web/blob/master/src/components/cardbuilder/card.scss
    title: jellyfin-web, card styles (rounded posters, indicators)
---

# Why

The owner wants Ephyra to look like Jellyfin's own apps, so the library
feels familiar next to the web client and the TV apps. It still has to
be a good Phosh app: adaptive at 360×720, touch first, libadwaita
widgets. Decision and trade-offs: [Jellyfin look](decisions/jellyfin-style.md).

# Rules

1. **Light or dark: the system's, or the user's choice.** Ephyra follows
   the system style; Preferences → General → Style offers Follow System,
   Light and Dark, kept in the account file (toolkit rule 8,
   [decision](../../phosh-toolkit/docs/decisions/app-accent-colours.md)).
   Jellyfin's default theme is dark[^jf-palette], so the dark style is
   the one that looks most like Jellyfin; both are checked in reviews.
2. **Jellyfin's blue as Ephyra's accent** (the toolkit gives every app
   its own accent). `--accent-bg-color: #00a4dc` and
   dark text on it (`--accent-fg-color: rgb(0 0 0 / 87%)`, Jellyfin's
   `primary-contrastText`)[^jf-palette]. libadwaita derives the accent
   text colour, so links, checks and focus rings follow. Set only in
   `ephyra/style.css`; for libadwaita 1.5 hosts the same values are
   given as `@define-color`. White on `#00a4dc` would have too little
   contrast, hence the dark text.
3. **Surfaces stay libadwaita's.** Jellyfin's near-black `#101010`
   background is not copied: libadwaita's dark greys keep header bars,
   lists and dialogs consistent with Phosh and other apps.
4. **Posters are the content.** Libraries and home sections are grids
   of cards: 2:3 posters (1:1 for albums, 16:9 for "Continue Watching"
   and "Next Up"), rounded (`.ephyra-poster`, 8 px), title in `heading`,
   year or `S1:E4 · Episode` in `caption` + `dimmed` below. Two columns
   at 360 px, more as the window grows. No horizontal carousels:
   Jellyfin's scrolling rows become wrapping grids, and sections with
   more items have "Show All".
   **Libraries** sort and filter from a menu button in the content
   header (`view-sort-descending-symbolic`, "Sort and Filter", only on a
   library, not on Home): Sort By Name, Date Added, Release Date or
   Rating; Ascending or Descending; Show Only Unplayed and Favorites. A
   new sort key starts in its natural order (names A to Z, the newest
   and best rated first). The choice is kept per library in the account
   file (`library_options`, `ephyra/library.py`); a filter that leaves
   nothing says "No Matching Items" instead of "Empty Library".
5. **Indicators like Jellyfin's.** A played item gets a round accent
   badge with a check in the poster's top right corner; a series gets
   its unplayed episode count there; a started item shows its position
   as a bar along the poster's bottom edge[^jf-card].
6. **Detail pages.** Backdrop at the top (16:9, at most 360 px high),
   fading into the page (`.ephyra-backdrop-fade`), then the title in
   `title-1`, a facts line (`2021 · 1 h 52 min · 12 · ★ 7.1`), the
   `suggested-action` pill "Play" or "Resume 40:00", round buttons for
   play from start, played and favourite, "Ends at 22:14", overview,
   genres. Seasons, episodes and tracks are `boxed-list` rows with
   thumbnails.
7. **Player.** Black letterbox (`.ephyra-video`, content colour), `osd`
   header and controls that hide after 3 s while a video plays and come
   back on a tap; seek bar, back 10 s, play/pause, forward 30 s,
   fullscreen.
8. **Everything else from the toolkit**: style classes before CSS,
   colours only through variables (data colours excepted), symbolic
   icons with tooltips and accessible labels, `AdwStatusPage`,
   `AdwToast` and `AdwBanner` for states, header capitalisation for
   titles and buttons. See the toolkit's
   [visual design](../../phosh-toolkit/docs/design.md) and
   [adaptive UI](../../phosh-toolkit/docs/adaptive-libadwaita.md).
9. **Not Jellyfin's brand.** No Jellyfin logo, wordmark or icon
   anywhere; the app icon is Ephyra's own (an eight-armed young
   jellyfish). The About dialog and the metainfo say Ephyra is not
   affiliated with the Jellyfin project.

# Review checklist

- [ ] 360×720 and 1000×700 screenshots, dark and light.
- [ ] No horizontal scrolling; cards two per row at 360 px.
- [ ] Accent only through `var(--accent-…)` or the badge/progress
      classes; no new hex colours in UI chrome.
- [ ] Played badge, unplayed count and progress bar still visible on
      the changed cards.
- [ ] Icon-only buttons have tooltips and accessible labels.

[^jf-palette]: jellyfin-web, base theme palette
[^jf-card]: jellyfin-web, card styles
