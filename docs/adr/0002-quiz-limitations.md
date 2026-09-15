# 2. Quiz extraction is blocked by the GraphQL gateway

- Status: accepted
- Date: 2026-09-15

## Context

We wanted to extract quiz/exam questions (item `typeName` `staffGraded` and
`ungradedAssignment`) the same way we extract videos and readings — via the
undocumented REST `onDemand*` API.

## Decision

Not implemented. Modern quizzes are served through Coursera's **GraphQL gateway**
(`graphql-gateway`), not the REST API.

## Evidence

- `POST onDemandExamSessions.v1` (the REST path used by `cs-dlp` for legacy
  `exam` items) rejects these items with `400 Wrong content type …
  StaffGradedContent` / `UngradedAssignmentContent`.
- The legacy `opencourse.v1/v2/.../quiz/session` routes return "API Route Does Not
  Exist".
- Open-source reverse-engineering (`skipera`, `coursera-mcp`) fetches quiz questions
  via GraphQL fragments (`Submission_*Question.questionSchema.options`) and requires
  the `CSRF3-Token` cookie in addition to `CAUTH`.

## Consequences

- `staffGraded`/`ungradedAssignment` items are skipped and reported as out of scope.
- Extracting questions would require: the `CSRF3-Token` cookie, plus a GraphQL
  "start attempt" operation whose schema is not public. That is a materially larger,
  more fragile effort than the REST approach used for the rest of the scraper.
- Slides/PDFs attached to lectures ARE available via REST
  (`onDemandLectureAssets.v1` → `assets.v1`) and are implemented.
