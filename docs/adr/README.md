# Architecture decision records

Each record covers one decision that shaped this project: the context, the decision, the alternatives that were weighed and the consequences, including the costs. A record is not edited once accepted; a later decision that changes it gets a new record, and the old one is marked `Superseded by N`.

These first four were written after the fact, from the code and the [decision list in the README](../../README.md#design-decisions--trade-offs). From here on, a structural decision is recorded in the pull request that makes it.

| # | Decision |
|---|---|
| [1](0001-synthetic-data-instead-of-masked-real-data.md) | Ship synthetic workbooks instead of masked real data |
| [2](0002-literal-raw-layer.md) | Keep the raw layer literal and parse in dbt |
| [3](0003-metrics-defined-in-dbt.md) | Define the metrics in dbt, not in the dashboard |
| [4](0004-publish-from-the-tested-ci-job.md) | Publish the site from the CI job that tested it |
