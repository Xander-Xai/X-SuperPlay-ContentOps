# Easel workbench overlay source

These files preserve the two project-owned skill overrides currently present in
the local Easel v0.3.0 workbench. The SHA-256 digests in
`runtime/easel-workbench-overlay.json` bind each workbench path to its source
copy here. The source test checks that relationship.

The benchmark playbook records observations from transcript reviews dated
2026-10-27 and 2026-10-28, but the transcripts and review notes were not saved
in this repository. Its historical examples and metrics are not verified
evidence and must not be presented as current facts. The playbook itself
retains this limitation.

Account profiles are generated from `config/accounts/` by
`scripts/easel_profile.py`; do not preserve stale profile snapshots as source.
These files support a later approved reconstruction. They do not authorize
modifying the existing extracted workbench, installing dependencies, running an
Agent, or changing the production pin.
