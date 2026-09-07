# Global skill cleanup snapshot — 2026-09-07

Pre-removal snapshot of 470 selected global entries across Codex, shared Agents, and Claude. Shared targets are materialized as files; broken links are represented by manifest metadata. Runtime dependencies, Git metadata and caches are excluded.

`manifest.json` maps original entry paths to preserved content and original link targets. `SHA256SUMS.json` records file hashes. Restore regular directories from `contents/`, then recreate the original symlinks using the manifest. Never overwrite a current skill without comparing it first.

Superpowers, ECC and Compound Engineering plugin installations are not part of the removal. Job-search skills already live in their project.
