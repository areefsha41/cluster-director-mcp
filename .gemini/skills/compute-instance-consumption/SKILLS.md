---
name: compute-instance-consumption
description: Check if a GCE instance has reservation affinity
---

# Compute Instance Consumption

When user asks "does <instance> have a reservation?" or similar:

1. Call `google-compute-mcp__get_instance_basic_info` with project, zone, instance name
2. Check response for `reservationAffinity` field
3. If exists, check `consumeReservationType`:
   - `"SPECIFIC_RESERVATION"` → YES, consuming reservation (extract name from `values[0]`)
   - `"ANY_RESERVATION"` → YES, consuming any available reservation
   - `"NO_RESERVATION"` → NO, not consuming reservation
4. If field missing → NO, no reservation affinity

## Examples
- "does instance-123 have a reservation in zone us-central1-a, project my-project?"
  → Call: `get_instance_basic_info` (project=my-project, zone=us-central1-a, instance=instance-123)
  → Check: `reservationAffinity.consumeReservationType`
  → Answer: YES/NO with consumption type

- "show consumption of my-instance"
  → Call: `get_instance_basic_info`
  → Report: consumption type and reservation name (if specific)

## Guidelines
- ONLY use `google-compute-mcp__get_instance_basic_info`
- NEVER call `list_reservations` (that's for reservations skill)
- NEVER use shell/gcloud commands
- If `reservationAffinity` missing → report NO reservation
- Extract reservation name from `values[0]` for SPECIFIC_RESERVATION
- If instance not found → suggest `list_instances` to verify
