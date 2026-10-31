# Performance testing

Workload assets live under performance-testing/. Run load tests only against an
explicitly authorized target; they create records and exercise approvals.
Stored CSV measurements and reports are historical, not current capacity evidence.

| Guide | Assets |
| --- | --- |
| [Target topology](environment-topology.md) | Environment and sizing assumptions |
| [Seeding design](seeding-design.md), [seeder usage](seeding/README.md) | performance-testing/seeding/ |
| [Staff API scenarios](staff-api/test-scenarios.md), [Locust usage](locust/api/README.md) | performance-testing/locust/api/ |
| [Partner API scope](partner-api/test-scenarios.md) | Deferred workload scaffolds |
| [Celery scope](celery/test-scenarios.md) | Deferred workload scaffolds |
| [Raw report](staff-api/raw-report.md), [interpretation](staff-api/final-report.md) | Historical results under performance-testing/locust/api/results/ |

The existing staff API harness provides five isolated scenarios. Blended and
soak workloads, partner API coverage and asynchronous capacity work remain
incomplete. Do not treat placeholders as accepted coverage.

Report tools are under performance-testing/scripts/. The raw-report generator writes
to performance-testing/documentation/staff-api/raw-report.md; review generated changes
before committing. The synthesis tool fills copies beside result files and
preserves its templates. No load test or report generation runs during ordinary CI.
