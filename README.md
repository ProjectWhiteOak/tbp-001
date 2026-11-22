# TBP-001: Temporal Bridge Protocol

A bounded experiment in asynchronous coordination, not a claim about time travel or priority. Process A leaves a beacon. A separately started process B searches the approved rendezvous root, verifies the beacon, and links a response to it and to data generated after B starts. An independent verifier checks the evidence.

**Status: local fixture passed; not live-ready.** This version has no live worker entry point, remote publisher, credential provisioning, model integration, or active scheduler. A bounded Firecrawl adapter has mock-contract coverage; separate connector calls tested a real map and raw HTML scrape on public documentation/example pages. Those probes did not retrieve a TBP beacon.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
mkdir -p artifacts
PYTHONDONTWRITEBYTECODE=1 python3 -m tbp.rehearsal run artifacts/example-01
PYTHONDONTWRITEBYTECODE=1 python3 -m tbp.rehearsal verify artifacts/example-01
```

Choose a new output directory for each run. See [protocol](PROTOCOL.md), [success gates](EXPERIMENT.md), and [runbook](docs/runbook.md).
