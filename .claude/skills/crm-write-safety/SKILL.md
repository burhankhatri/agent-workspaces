---
name: crm-write-safety
description: "Rules that apply to every write to a system of record. Use whenever a task creates, updates or deletes a CRM record, or enrolls anyone in an outreach campaign. Triggers on 'create lead', 'update CRM', 'inject leads', 'enroll', 'campaign', 'write to Sunzi'."
---

# CRM write safety

These rules apply in every workspace. They are not task-specific.

## Before any write
- Say what you are about to write, and how many records, before writing it.
- If the count is above 10, stop and ask first.
- Never invent a field value to satisfy a required field. Ask instead.

## Idempotency
- Check for an existing record before creating one. A retry must not duplicate.
- If a record already exists, update it rather than creating a second one.

## Never
- Never pass transport/control fields to a CRM form (`record`, `module`, `action`,
  `return_module`, `return_action`). A non-empty `record` turns a create into an
  edit of an arbitrary existing row.
- Never build a query by string interpolation of an input value.
