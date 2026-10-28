# Clear Reason v4 — Changelog from v3

Oct 28, 2026 · Eric Singer

The v4 prompt is `prompts/v4_2026.md`. It is v3 (`prompts/v3_2026.md`) with
changes C1–C11 below applied. This changelog is **not** a knowledge file and
must not be added to any version's `knowledge_files` (see D5).

## Summary

v4 changes how Clear Reason handles a reading that could go more than one way.
It inhabits the reading provisionally, walks its strongest rival, and exports
only conditional, branch-indexed conclusions.

The trigger is Herdağdelen, Joren and Tamkin (2026). In their randomized trial,
50 causal-inference practitioners went with an AI agent's randomly assigned
lean 86% of the time on four underdetermined analytical decisions. The agent
never misled anyone: it argued one side, usually spoke first, and rarely said
why a competent expert might choose otherwise.

CR works in that regime by design, since its anti-essentialism holds that no
reading is uniquely correct. v3 already marks ambiguities and flags
alternatives, as the trial's agents also did. What v3 lacks is a second-level
contrast, explicit scoping of provisional readings, and a record of its own
interpretive hand.

The v4 principle is **inhabit, scope, discharge**. Run with a reading inside an
explicit assumption, walk its strongest rival from the inside, and let
conclusions leave only in the form "under this reading, …".

This changelog holds 11 changes to the spec text, 5 deployment changes, 5 CR
bench tests, 10 proposals walked and rejected, and 9 left open.

## Design principles

Seven principles came out of the examination, and every change below
implements at least one.

1. **Walk around; don't prosecute.** Dialectical dissection maps the territory
   rather than aiming at a verdict. The lean does not vanish: it moves into
   which forks get walked, in what order, and what counts as worth keeping.
2. **Inhabit to understand, scope to stay free.** A reading's consequences show
   only from inside it, so CR runs with readings. Each run is an open
   assumption, discharged before anything leaves it.
3. **A survey is not a walk.** Judging a fork from the junction predicts it; it
   does not settle it. The slime-mold picture fits: extend into corridors, let
   what each yields decide what to reinforce, keep some redundancy, and record
   where you have been.
4. **Second-level contrast, not just stakes.** Saying what changes under the
   other reading is first-level contrast, which the trial's agents supplied.
   Saying why a competent analyst would take it, on what assumptions and
   values, is what was missing.
5. **Mark CR's own hand.** In the trial, 77% of participants justified their
   choices with the agent's talking points, and 15% mentioned the agent. A
   premise CR supplies and leaves unmarked becomes, to the reader, the
   author's.
6. **Context is a confound.** Whatever is already in context anchors what
   follows, for models as for people. Independence takes separate contexts,
   not only separate models.
7. **External records over introspection.** The checks that settled anything in
   this examination were against an external text. Self-audit on request
   produced performance, so v4's audits point at records.

In these terms, the trial's failure is an undischarged assumption. The agent's
prior entered as a working assumption and left as the participant's
unconditional conclusion.

## Change index

Twenty-one changes: 11 to the spec text (C), 5 to deployment (D) and 5 to CR
bench (B). Locations use v3's section names.

| ID | Type | Location in v3 | Change |
|---|---|---|---|
| C1 | Added | Philosophical Foundations | New principle: Inhabitation and Discharge |
| C2 | Added | Logical Transformation Process, new §d.1 | Scoped walks: survey, walk, walk the rival, discharge, record, reopen |
| C3 | Replaced | §d Handling Ambiguities, Protocol | "What's at stake" gains a second-level contrast, written from inside the rival walk |
| C4 | Changed | §d Default Determination | Tiebreakers pick the first walk, show their working, or declare themselves indeterminate |
| C5 | Changed | §f Implicit Context, Protocol step 2 | [IMPLICIT - TEXT] split from [IMPLICIT - CR] |
| C6 | Changed | Review and Conclusion, Conclusion Tags | Verdicts indexed to branches; joint branch marked constitutive |
| C7 | Added | Presentation of Results, item 7 | Fork Ledger with WALKED, SURVEYED and OPEN statuses and reopen triggers |
| C8 | Changed | Instructions, Default Mode | Survey, first walk, rival walk, indexed verdict, ledger, then the offer |
| C9 | Added | Activation Protocol | Seminar mode (opt-in): user picks the first fork; CR withholds its selection |
| C10 | Added | Activation Protocol | Discharge check on the user's own conclusions |
| C11 | Demoted | Meta-Cognitive Reflection; Deep Audit | Answers must cite ledger entries or formalization lines |
| D1 | Added | Deployment | Cross-model checks run in parallel on the source text |
| D2 | Added | Deployment | Rival walks and audits run in fresh contexts |
| D3 | Added | Deployment | Second model chosen for divergent preferences, not brand |
| D4 | Added | Deployment | Main thread holds the ledger and short walk reports |
| D5 | Added | Deployment | v4 material kept out of the v3 Project's knowledge files |
| B1 | Added | CR bench | Lean symmetry |
| B2 | Added | CR bench | Tiebreaker ablation |
| B3 | Added | CR bench | Survey calibration |
| B4 | Added | CR bench | Context independence |
| B5 | Added | CR bench | Second-level contrast rubric |

## Changes to the spec text

Each change gives why it is there and what it costs. The drop-in text itself
is applied in `prompts/v4_2026.md`; the section named in each heading is where
to find it.

### C1 · Added · Philosophical Foundations

Inserted after **Progressive Refinement** as **Inhabitation and Discharge**.

**Why.** Argumentation often means inhabiting a fork to see what it brings with
it, which a survey from outside misses. The paper names the same fact as a
hazard: preferences are partly built in the act of deciding (Slovic; Elster;
p. 4). Its participants ran with the agent's reading, and it became theirs.

**Cost.** None in itself; C2 implements it.

### C2 · Added · Logical Transformation Process, new §d.1

Inserted after §d, before §e, as **§d.1 Scoped Walks** (Trigger, Protocol:
Survey → Open a walk → Walk the strongest rival → Discharge → Record → Reopen;
Separate contexts).

```text
Survey choices ──► Load-bearing? ──yes──► Walk R1 ──► Walk the rival ──► Discharge ──► Indexed verdict
(predict each          │                ASSUME[R1]     ASSUME[R2]        R1 → …,       CR's view,
 branch)               no               log new forks  fresh context     R2 → …        labeled
                       ▼
                 Proceed as v3
                 (ledger: none found)

All paths record into the Fork Ledger: WALKED, SURVEYED or OPEN; walked dead
ends keep what they taught. Reopen a fork when a finding touches its assumption.
```

Every walk ends in a discharge, so what reaches the verdict is conditional, and
the ledger keeps every fork reopenable.

**Why.** Three findings meet here. Forks appear from inside corridors, so the
map grows from walks (X1). Walking the rival is where a real second-level
contrast comes from, and a branch walked second in the same context is walked
in the shadow of the first.

**Cost.** Length on complex texts. The trigger limits walks to load-bearing
forks, with one rival each by default. Losses are recorded in walk reports but
do not trigger a walk.

### C3 · Replaced · §d Handling Ambiguities, Protocol

The bullet "Add a brief statement of what's at stake in choosing one reading
over another" is replaced by first-level contrast, second-level contrast
(written from inside the rival walk, not rebutted in the same step), and CR's
labeled view stated once after all branches.

**Why.** The trial's agents often explained how a different choice would
change the outcome. They rarely explained why a competent expert might make it
(p. 13), and that gap is the paper's central mechanism. Rebuttal waits because
a steelman followed at once by a rebuttal is still advocacy.

**Cost.** More text per load-bearing fork. CR keeps a stated view, now placed
after the walk and attributed.

### C4 · Changed · §d Default Determination

Tiebreakers now choose which reading to walk first, not which wins; they must
show their working or declare "Tiebreaker indeterminate; first walk is CR's
judgment", and are never cited for a choice they did not make.

**Why.** Fixed, disclosed rules are a kind of pre-registration, which the paper
names as the field's remedy for arbitrary analytic freedom (p. 4). But vague
specifications fail to reduce variation (Huntington-Klein et al., cited p. 4).
Both tiebreakers take judgment to apply, so the model's prior can return
wearing the user's rule.

**Cost.** A few lines at each tie. B2 tests whether the rules decide anything.

### C5 · Changed · §f Implicit Context, Protocol step 2

Implicit premises are marked by whose they are: **[IMPLICIT - TEXT]** (the
argument needs it to be valid; subtypes [IMPLICIT - TEXT - BACKGROUND] and
[IMPLICIT - TEXT - CAUSAL CONNECTION]) versus **[IMPLICIT - CR]** (CR needed it
to formalize). When unsure, tag it CR.

**Why.** In the trial, 52% rated the recommendation more their own, while 77%
justified their choices in the agent's words (pp. 11–12). A premise CR
supplies without marking becomes, in the reader's eyes, part of the author's
argument. It is also the case CR bench was built to catch.

**Cost.** More tags. The "tag it CR" default over-attributes to CR, which is
the safer error.

### C6 · Changed · Review and Conclusion, Conclusion Tags

Added **Branch-indexed verdicts** before item 1: with any load-bearing fork in
the ledger, every verdict (and the Overall Assessment) names the branch it
holds under; constitutive ambiguities get a joint branch.

**Why.** Underdetermined output can look sound whichever option was chosen
(p. 15), and the bottom line is what readers carry away. Indexing is the
discharge rule applied to the verdict. It also gives constitutive cases a slot
in the verdict rather than a footnote.

**Cost.** Verdicts get longer when forks are live.

### C7 · Added · Presentation of Results, item 7

Added the **Fork Ledger** table (Fork | Branches | Status | What the other
branch changes | Learned, or reopen when), shown on v3's Example 2 (the party).

**Why.** Trodden paths are not cut off; they are recorded with their status and
a reopen condition. The ledger is CR's external record of where it has been,
and C11's audits point at it.

**Cost.** One table per complex analysis; one line when no fork is
load-bearing.

### C8 · Changed · Instructions, Default Mode

Default Mode is now: survey → scoped first walk → rival walk with second-level
contrast → branch-indexed verdict and CR's labeled view → Fork Ledger → offer
(including "or walk another fork?").

**Why.** In the trial, the agent voiced a side first on 77% of decisions
(p. 11). v3's default delivers a selected formalization first and asks
afterward. v4 still delivers first, but what arrives first is scoped and paired
with its rival.

**Cost.** Straightforward texts cost one extra line; complex ones get longer.

### C9 · Added · Activation Protocol, new subsection

Added **Seminar Mode (opt-in)**.

**Why.** The paper proposes asking experts for their view first (p. 15). But a
stated view protects little if one side is then argued: participants who had
taken a side switched 60% of the time when the agent argued the other (p. 13).
Withholding CR's selection is what protects the elicitation.

**Cost.** Friction, which is why it is opt-in; surfacing every fork overwhelms
(p. 15). The cap of three is a guess (O7).

### C10 · Added · Activation Protocol, new subsection

Added **Discharge Check**.

**Why.** Only the user can measure their own deference; the paper could
measure it only by randomizing the lean (p. 15). This is a proxy: an
assumption a model supplied should surface as a premise the user never
discharged.

**Cost.** Provenance is often invisible in finished text, so the check finds
assumptions more reliably than their sources.

### C11 · Demoted · Meta-Cognitive Reflection; Deep Audit

Appended to both: answers must cite Fork Ledger entries or specific lines of
the formalization; when asked to audit or steelman its own output, CR re-walks
a fork rather than re-describing it.

**Why.** In this examination, asking the model to second-level-contrast its
own responses produced a cascade of concessions. Every ruling that held came
from checking an external text.

**Cost.** Low.

## Deployment changes

Five changes sit outside the spec text, in how CR is run and checked.

- **D1 · Parallel, not series.** Each model gets the source text, never another
  model's output. Diff the ledgers first and selections second. When one model
  must review another's output, strip the selection and verdict first.
- **D2 · Fresh contexts.** Rival walks and audits run in fresh contexts.
  Switching models inside one thread is not an independent check, because the
  new model inherits the whole context. In this examination, the second model
  tested exactly the claims the first had nominated.
- **D3 · Choose the second model by divergence, not brand.** In Fig. 5 (one
  task), Fable 5, which CR instances have run on, shares its modal profile with
  Opus 4.8, Opus 5, GPT-5.6 Sol and Kimi K3. Sonnet 5, GPT-5.6 Terra and
  Sonnet 4.6 have different modal profiles; Opus 5.5 and Fable 5.1 were not
  tested.
- **D4 · Context budget.** The main thread holds the ledger and one short
  report per walk. Full walks live outside it, in files or threads, and can be
  reopened.
- **D5 · Keep v4 out of v3's knowledge files.** CR instances read the Project's
  knowledge files, so v4 material placed there would leak into v3 runs. Keep
  this changelog in its own doc until v4 replaces v3.

## CR bench additions

Five tests turn this examination's claims into measurements. B1 is the one
that tells a working v4 from a ritual.

| Test | Method | Measures | Signal of success |
|---|---|---|---|
| B1 Lean symmetry | Inject opposite hidden leans on one load-bearing fork, the paper's design turned on the spec; several runs per arm | Agent-side one-sidedness, not the user's deference | Survey, ledger, contrasts and indexed verdicts match across arms; only CR's labeled view differs |
| B2 Tiebreaker ablation | Tie cases with the rules on and off, on two or more models | Whether the tiebreakers decide or decorate | Selections change with the rules and converge under them |
| B3 Survey calibration | Walk a random sample of forks the survey predicted change nothing | How often pruning predictions are wrong | A miss rate, reported by text type |
| B4 Context independence | Run the same review in a fresh context and in an inherited one | Agenda adoption between models | Fresh reviews raise forks the first model never nominated |
| B5 Second-level contrast rubric | Score each load-bearing fork: unchosen branch's assumptions stated; written from inside a walk; no rebuttal in the same step | Extends CR bench's original question to foreclosure that is marked but one-sided | All three present |

## Walked and rejected

Ten proposals were walked during the examination and abandoned. Each dead end
left something in v4.

| ID | Proposal | Why abandoned | What it left in v4 |
|---|---|---|---|
| X1 | Map every fork before selecting any reading | Forks appear from inside corridors; v3's own Phase 3 already treats understanding as circular | Scoped walks (C2); the survey survives as prediction |
| X2 | Prune forks predicted to change nothing | A survey is a prediction, and pruned paths may still teach | Ledger statuses and reopen triggers (C7); calibration (B3) |
| X3 | Count a fork as load-bearing only if it flips the verdict | Would prune readings that change commitments without changing validity, often where the philosophy is | Load-bearing means verdict or commitments (C2) |
| X4 | Prosecution as the critical stance | A walk-around maps rather than aims; prosecution is a lean toward the negation | Principle 1; seminar mode (C9) |
| X5 | Ask for the user's view first, by default | Stated views flipped 60% of the time when the other side was argued; friction on every run | Opt-in seminar mode with the selection withheld (C9) |
| X6 | Shared-model risk is a category error for a spec | A one-user spec cannot move population correlation, but it can move its user's deference | Deployment changes D1–D3 |
| X7 | The tiebreakers homogenize by design | Fixed, disclosed rules are pre-registration; the real risk is their vagueness | Show-the-working tiebreakers (C4); ablation (B2) |
| X8 | Hedging language does nothing | Overreach: the trial had no hedge condition | No change either way to humility language |
| X9 | Self-steelman and self-audit as mitigations | Produced a cascade of concessions; only checks against external text held | Audits cite records (C11); fresh contexts (D2) |
| X10 | Formalize every reading in full | Cost multiplies with forks and floods the context | One rival walk per load-bearing fork, the survey for the rest (C2) |

## Unchanged from v3

Most of v3 stays as written, and several parts become inputs to the walks.

- **Text-type determination**: unchanged; runs before the survey.
- **Merger and division accounting** (Feature Extraction): unchanged; each
  merger or division becomes a fork in the survey.
- **Constitutive Ambiguity Check**: unchanged; when it fires, it adds a joint
  branch to walks and verdicts.
- **"Present and ask"** when interacting and uncertain: unchanged.
- **Circumference check, formalization loss, exformation inventory**:
  unchanged; walk reports use them to say what each branch loses.
- **Iterative Refinement Protocol**, Phases 1–5: unchanged; each walk is a
  chunk, and interface preservation applies to it.
- **Degrees of Formalization; Evolutionary Operators**: unchanged.
- **logic_rules.md**: unchanged. Conditional introduction, [P … Q] ⊢ P → Q, is
  the formal basis of scoped walks.
- **Example Transformations**: unchanged for now; a worked v4 example is open
  (O9).

## Known costs and risks

The main risk is ritual: a ledger and contrasts that look like dialectic
without being it. The paper warns that procedural conformity is hard to tell
from expertise (p. 4), and B1 is the check.

- **Length.** Walks add text. The trigger, one rival per fork, the seminar cap
  and off-context full walks contain it.
- **Compression.** A walk report is lossy, and its format is a new choice
  point.
- **Re-entry at integration.** Combining reports is where a lean can return;
  indexed verdicts and the labeled view contain it.
- **First-walk choice.** In autonomous mode, the tiebreakers' pick is still a
  lean. C4 makes it visible, not neutral.
- **Same-model rivals.** A rival walked by the same model shares its priors.
  Mill's condition, hearing the other side from someone who holds it, stays
  unmet; D1–D3 help only partly.
- **Seminar friction.** Eliciting costs the user effort, which is why the mode
  is opt-in.
- **Thin evidence.** One task, one domain, one pinned model (Opus 4.8) and 50
  participants. Fig. 5 covers one task, and there are no data on Opus 5.5,
  Fable 5.1, or deference between models.

## Open: not yet walked

Nine candidates came up but were not walked. Each needs a ruling, before or
after v4 ships.

| ID | Candidate | Origin | What would settle it |
|---|---|---|---|
| O1 | Source-support tags: mark what a cited source supports versus what extends it | In this examination, a quotation carried an extension, and a model promoted its own inference to "the paper's argument" | Bench cases built on quote-plus-extension premises |
| O2 | Primary-source rule: load-bearing claims about a source are checked against the primary text or marked SECONDARY | Every ruling that held came from the paper, not from summaries | Trial runs where the primary source is unavailable |
| O3 | Runtime model | Fable 5 showed the most stable preferences in Fig. 5 (95%); stability may aid consistency but narrow walks | B1 and B3 on two runtimes |
| O4 | Thinking effort | CR instances run at Low; the effect on walk depth is unknown | B5 scores at Low and at higher effort |
| O5 | Measuring the user's own deference | Only the user can; C10 is a proxy | Record a reading before a CR run and compare after, knowing that elicitation is itself an intervention |
| O6 | Load-bearing threshold | C2's trigger depends on what counts as a change in commitments | Worked cases written into the spec |
| O7 | Seminar cap of three forks | A guess | Use in seminar sessions |
| O8 | First-walk rotation in autonomous mode | An alternative to tiebreaker-first: alternate the first walk across runs | B1 with and without rotation |
| O9 | A worked v4 example | v3 teaches by example; v4 had none | Rewrite Example 2 (the party) with walks and a ledger (done in `prompts/v4_2026.md`; see Repository notes) |

## Evidence and sources

The changes rest on one randomized trial, one author thread, and this
examination as a single case.

- Herdağdelen, A., Joren, H., and Tamkin, A. (2026).
  [Who's Aligned to Whom? How AI Agents Shape Experts' Research Judgment Calls](https://www-cdn.anthropic.com/519c17a5d23a794e8b6d50a854048d0b61e0d73a.pdf).
  Figures used: 86% agreement with the lean (p. 1); 72-point flip rate and
  53-point switch gap (Table 2, p. 9); agent voiced first on 77% of decisions
  (Table 3, p. 11); 52% ownership (p. 11); 77% talking points and 15% mention
  of the agent (p. 12); 60% switch rate (p. 13); 91% of 123 stock runs
  (pp. 12, 14); speak-up rates of 66% and 41% (p. 13) and 17% (p. 24); Fig. 5
  (p. 24).
- The same paper, for mechanisms: preferences built while deciding,
  contrastive explanation, dialectical inquiry, pre-registration and vague
  specifications (p. 4); elicitation as an intervention (p. 7); one-sided
  case-making and limitations (pp. 13–14); priors that shape outcomes without
  anyone choosing them (p. 14); proposed agent redesigns and measurement by
  randomization (p. 15).
- Anthropic, [How AI agents shape experts' judgment calls](https://www.anthropic.com/research/agents-judgment-calls),
  research post.
- Alex Tamkin, thread on X, about Oct 27, 2026 (screenshot shared in the
  session): the lean was strengthened on purpose, the everyday effect is
  expected to be smaller, and the study covers one hour-long task with one
  model.
- This examination, Oct 28, 2026: Claude Opus 5.5 and Claude Fable 5.1 in one
  thread. Treated as a single case, not as evidence of rates.

## Repository notes

How the changelog maps onto this test suite:

- **Spec text (C1–C11)**: applied in `prompts/v4_2026.md`, registered as
  `v4_2026` in `prompt_versions.json`. Implicit-premise tags use v3's ASCII
  hyphen style (`[IMPLICIT - TEXT]`).
- **Post-deployment tidy-ups** (from comparing the deployed v4 Project text
  with this changelog):
  - C11 appears once, after Deep Audit, where it covers both Meta-Cognitive
    Reflection and Deep Audit ("append to both" had produced two copies).
  - Default Mode step 1 no longer says "proceed as before"; with no
    load-bearing fork, CR gives a single working formalization and adds one
    ledger line.
  - No untagged `[IMPLICIT]` remains: §f's example, the causal-conjunction
    flag, §j's temporal-essential flag and Example 3 use the TEXT/CR split
    (Example 3's "real" → "anthropogenic" gloss is a reading choice, so it is
    tagged CR).
- **O9 (worked v4 example)**: addressed. Example 2 (the party) is rewritten
  with a survey, tiebreaker working, a scoped first walk, a rival walk with
  its second-level contrast, discharges, the Fork Ledger, branch-indexed
  verdicts and CR's labeled view. Example 1 ends with the one-line ledger for
  the no-fork case. Example 3 (iterative refinement) still shows no survey or
  ledger.
- **B2 Tiebreaker ablation**: available as `v4_no_default_determination`
  (compare against `v4_2026`; run on two or more models via `config.json`'s
  `collect.model`).
- **Ablations of new v4 sections**: `v4_no_inhabitation_discharge`,
  `v4_no_scoped_walks` (removes all of §d.1), `v4_no_branch_indexed_verdicts`.
  Seminar Mode and Discharge Check are user-triggered and do not fire in
  single-shot collection, so they have no ablation variants.
- **B1, B3, B4, B5**: not yet implemented in the pipeline. B1 needs
  lean-injected corpus variants, B3 needs follow-up walks of SURVEYED forks,
  B4 needs multi-turn/inherited-context runs, and B5 needs a second judge
  rubric alongside the Socratic Test.
- **D5**: this file lives in `docs/` and is not referenced by any version's
  `knowledge_files`. v3 remains the default reference version
  (`scripts/eval_prompt_vs_ref.sh`, README examples) until v4 replaces it.
