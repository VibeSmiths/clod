---
status: testing
phase: 02-intent-classification
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md]
started: 2026-03-10T18:10:00Z
updated: 2026-03-10T18:10:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Intent classification on obvious code request
expected: |
  Type "write a python function to sort a list" in the REPL. The system should classify this as "code" intent silently (no output unless verbose mode is on). You can verify by running `/intent` which should show the last detected intent as "code" with confidence above 0.8.
awaiting: user response

## Tests

### 1. Intent classification on obvious code request
expected: Type "write a python function to sort a list". Then run `/intent` — should show last intent as "code" with confidence >= 0.8.
result: [pending]

### 2. Intent classification on chat input
expected: Type "hello, how are you?". Then run `/intent` — should show last intent as "chat".
result: [pending]

### 3. Intent classification on image generation request
expected: Type "generate an image of a sunset over mountains". Then run `/intent` — should show last intent as "image_gen" with high confidence.
result: [pending]

### 4. /intent one-shot classification
expected: Type `/intent explain why the sky is blue` — should display a Rich panel showing the classified intent (likely "reason") and confidence score, without affecting the current session intent state.
result: [pending]

### 5. /intent auto toggle
expected: Type `/intent auto` — should print "Intent auto-classification enabled" (or similar). Type `/intent auto` again — should toggle or confirm the state.
result: [pending]

### 6. /intent verbose toggle
expected: Type `/intent verbose` — should toggle verbose mode on/off with confirmation message. When verbose is on, subsequent user inputs should show the classified intent and confidence inline.
result: [pending]

### 7. /model disables auto-classification
expected: Type `/model llama3.1:8b` (or any valid model). Should see a notification that intent auto-classification is disabled. Then type a message and run `/intent` — last_intent should NOT have been updated (classification was disabled).
result: [pending]

### 8. /intent auto re-enables after /model override
expected: After disabling via `/model`, type `/intent auto`. Should see confirmation that auto-classification is re-enabled. Then type a message and run `/intent` — last_intent should now reflect the new classification.
result: [pending]

### 9. Low confidence handling
expected: Type something ambiguous that doesn't clearly match any intent (e.g., "hmm interesting"). Should see a dim notice about low confidence or default to chat silently (no crash, no error).
result: [pending]

## Summary

total: 9
passed: 0
issues: 0
pending: 9
skipped: 0

## Gaps

[none yet]
