# 4. Publish the site from the CI job that tested it

**Status:** Accepted

## Context

The dashboard and the dbt docs are published on GitHub Pages. Both are built from the warehouse, which CI rebuilds from the synthetic workbooks on every run. The site should only ever show something that passed the tests, and what is published should be what was tested, not a second build of the same commit.

## Decision

One CI job, `pipeline` in [`ci.yml`](../../.github/workflows/ci.yml), goes from the workbooks to the site: it generates and loads the data, runs `dbt build` and source freshness, generates the dbt docs, lints the SQL, and builds the dashboard in strict mode, which fails on any broken query or component. On a push to `main`, the same job assembles that build into the Pages artifact, and a `deploy` job that depends on it publishes the artifact. Pull requests run every step except the publish.

## Alternatives considered

- **A separate deploy workflow on push to `main`.** It would build the site a second time, in another run, so what goes live would not be the exact build that passed; and keeping the two workflows' steps in sync is easy to forget.
- **Evidence's hosted product.** It needs an account and a different project syntax (Evidence Studio), and the build would no longer run next to the dbt tests.
- **Commit the built site to a `gh-pages` branch.** It puts generated files in the git history and still needs something to run the build first.

## Consequences

- The published site is exactly the build that passed `dbt build` and the strict dashboard build; a failing test means nothing is deployed.
- A push to `main` waits for the whole pipeline before the site updates.
- Pull requests build the site but do not publish a preview; checking a visual change means running `make site` locally.
