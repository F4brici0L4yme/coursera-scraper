# 1. API-first vs browser automation

- Status: accepted
- Date: 2026-09-14

## Context

The scraper must fetch lecture video, subtitle and transcript URLs for courses the
account is enrolled in. Two strategies were considered:

1. **Coursera internal API** (`api.coursera.org/api/onDemand*`) — the same endpoints
   the SPA calls.
2. **Playwright browser automation** — log in, open the "Files" panel, intercept network.

## Decision

Use the internal API. Playwright is not used at all.

## Consequences

- **Robustness:** pre-signed CloudFront URLs are returned directly; no dependence on
  DOM structure or SPA render timing, so no fragile `sleep()`s or selector waits.
- **No 2FA/captcha friction:** an optional `CAUTH` cookie is the only auth signal.
- **Risk:** these endpoints are undocumented and can change. Notably
  `onDemandCourseMaterials.v1` is already deprecated in favour of `.v2`, whose
  response keys use `.v2` suffixes and `contentSummary` instead of `content`. If the
  API is removed, fall back to Playwright interception (not download-button clicks).
- **Key detail:** lecture items expose their media via
  `onDemandLectureVideos.v1/{courseId}~{itemId}` using the **item id**, not a separate
  video id. Subtitle/transcript URLs are relative and must be prefixed with
  `https://api.coursera.org`.
