# Farmer reference notification publisher

`config.yaml` describes the explicit New Dev REGISTER topic and dedicated
notification data model. `notification.json.j2` is the MinIO outgoing template.
It publishes the source functional ID, FAN and a stable event identifier derived
from internal ID and approval time; it does not publish demographic fields.

Prepare the subscriber first. Install the document through the configured
DocumentHandler and record it in the native document catalog. Bind the template
and topic through `outgoing_templates` / `outgoing_topics`, then explicitly enable
outgestion for the Farmer register. New registers stay disabled by default;
reseeding preserves the administrator's installed switch. No historical records
are replayed. Retain all other topics, templates, register flags and approvals.

The New Dev overlay supplies the internal Commons WebSub URL to Core and the
publisher processes. CI renders and verifies it, while staging remains separate.
Do not point Celery at Kafka: Redis continues to broker Celery work; WebSub owns
its Kafka delivery infrastructure.

Use [the documented pipeline](https://docs.openg2p.org/products/registry/registry/design/outgestion-pipeline)
and verify an approved marked change reaches PROCESSED at both outgoing stages.
Source records that lack the two identifiers cannot resolve through the strict
subscriber lookup; do not invent a FAN or publish unapproved corrections.
