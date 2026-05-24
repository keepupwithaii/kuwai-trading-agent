# COUNCIL/SCHEMA.md — the closed council-v1 conclusive-report schema (sealed)

Closed. The schema IS the anti-caution-creep wall: there is deliberately no
field outside the seven fixed dimension verdicts, their one-line whys, and the
two derived fields. No `caution` field. No `debate_contested` binary (Q5
resolved, dropped). No free advisory channel beyond dimension (g)'s bound
shape. Adding any field is a seal break.

## The conclusive report (the only thing the SYNTHESISER may emit)

```
council-v1:
  dimensions:
    a_grounded:            { verdict: pass|fault, why: "<one line>" }
    b_no_future_bet:       { verdict: pass|fault, why: "<one line>" }
    c_not_injection_steered:{ verdict: pass|fault, why: "<one line>" }   # advisory
    d_no_must_never_breach:{ verdict: pass|fault, why: "<one line>" }
    e_not_account_ending:  { verdict: pass|fault, why: "<one line>" }
    f_no_self_sabotage:    { verdict: pass|fault, why: "<one line>" }
    g_reasoning_holds:     { verdict: pass|fault, why: "<bound shape, see below>" }
  overall:      pass|fault          # DERIVED, not model-authored
  disposition:  proceed|halt        # DERIVED, not model-authored
```

The `why` for each of a-f must name a closed fault token from FAULT_LIST.txt
or it is treated by the deterministic post-parse guard as a schema-structural
malformation. The model never writes `overall` or `disposition`; the harness
derives them deterministically (see DISPOSITION).

## Dimension (g) bound shape (MF-1 Option A, 146 §1; enforced by the post-parse guard)

When `g_reasoning_holds.verdict == fault`, its `why` MUST take exactly this
closed cited-item-to-step incoherence shape:

  "from cited item <X>, to action <Y>, the stated link is <Z>, and <Z> is
   absent or contradicted by cited item <W>"

It must name a specific cited payload item X, a specific reasoning step /
action Y, the claimed link Z, and the specific cited item W that is absent or
contradicts it. A genuine logic fault is expressible in this shape; a laundered
size / caution / boldness objection generally is not, because it cannot name a
concrete cited-item-to-step gap. A parse-valid `g` `why` that does NOT satisfy
this bound shape is a SUBSTANTIVE guard rejection: it HALTs immediately with
ZERO retries (R-1 bind, 151 §1.2). It is NOT a schema-structural malformation
and the one bounded SYNTHESISER retry never fires on it.

## DISPOSITION (deterministic, harness-derived, never model-authored)

- a, b, d, e, f are bright-line objective faults. If ANY of them is `fault`,
  `overall = fault` and `disposition = halt` automatically, with no vote and
  no way around it. These are wrong by definition and not the trader's to
  wave through.
- c (injection/steered-by-planted-input) is ADVISORY by design (it preserves
  the accepted injection-fabrication residual; it does not hard-HALT on its
  own).
- g (reasoning holds) is ADVISORY and trader-facing in its bound shape: a `g`
  fault does not hard-HALT; it is surfaced to the trader through the sealed
  SYSTEM_PROMPT council clause (which already carries the MF-2 symmetric
  counterweight: the council can be wrong, it is one read not a verdict, the
  call stays the trader's). The trader still decides.
- Any council error, timeout, malformed report, crash, or a double
  schema-structural garble resolves to no-trade plus a loud logged HALT, never
  a silent pass and never a silent caution brake (fail-safe-to-HALT,
  unweakened).

The council adds NO new blocking rule: every hard-HALT routes through an
existing sealed construct (grounding linter, must-never list, 0.45*E0 floor,
feasibility gate, cash-account, corroboration annotations). The feasibility
gate remains the sole order blocker for broker/legal feasibility.
