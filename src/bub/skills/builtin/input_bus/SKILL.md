---
name: input-bus
description: Resolve inbound session ids and normalize inbound messages.
kind: bus
entrypoint: bub.skills.builtin.input_bus.plugin:plugin
---

# Input Bus Skill

Normalizes inbound envelopes and maps them into stable session ids.
