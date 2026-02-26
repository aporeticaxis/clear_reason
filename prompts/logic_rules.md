# Logic Rules for Standard Derivation (SD) and Standard Derivation+ (SD+)

This document provides formal rules and tables for propositional logic derivation systems. These serve as the foundational reference for logical analysis and proof construction.

---

## Derivation Rules of SD (Standard Derivation)

| Rule | Notation | Description |
|------|----------|-------------|
| **Conjunction Introduction (∧I, KI)** | P, Q ⊢ P ∧ Q | From P and Q separately, infer their conjunction |
| **Conjunction Elimination (∧E, KE)** | P ∧ Q ⊢ P; P ∧ Q ⊢ Q | From a conjunction, infer either conjunct |
| **Conditional Introduction (→I, ⊃I)** | [P ... Q] ⊢ P → Q | If Q can be derived assuming P, infer P → Q |
| **Conditional Elimination (→E, ⊃E, MP)** | P → Q, P ⊢ Q | Modus Ponens: from conditional and antecedent, infer consequent |
| **Negation Introduction (¬I)** | [P ... ⊥] ⊢ ¬P | If assuming P leads to contradiction, infer ¬P |
| **Negation Elimination (¬E)** | ¬¬P ⊢ P | From double negation, infer the positive |
| **Disjunction Introduction (∨I, vI)** | P ⊢ P ∨ Q; P ⊢ Q ∨ P | From P, infer P or anything |
| **Disjunction Elimination (∨E, vE)** | P ∨ Q, [P ... R], [Q ... R] ⊢ R | Proof by cases: if both branches lead to R, infer R |
| **Biconditional Introduction (↔I, ≡I)** | [P ... Q], [Q ... P] ⊢ P ↔ Q | If P implies Q and Q implies P, infer biconditional |
| **Biconditional Elimination (↔E, ≡E)** | P ↔ Q, P ⊢ Q; P ↔ Q, Q ⊢ P | From biconditional and one side, infer the other |

**Note**: Brackets [P ... Q] indicate a subproof or assumption scope.

---

## Derivation Rules of SD+ (Standard Derivation Plus)

SD+ includes all SD rules plus the following derived rules for convenience:

| Rule | Notation | Description |
|------|----------|-------------|
| **Modus Tollens (MT)** | P → Q, ¬Q ⊢ ¬P | From conditional and negated consequent, infer negated antecedent |
| **Hypothetical Syllogism (HS)** | P → Q, Q → R ⊢ P → R | Chain conditionals |
| **Disjunctive Syllogism (DS)** | P ∨ Q, ¬P ⊢ Q; P ∨ Q, ¬Q ⊢ P | From disjunction and negation of one disjunct, infer the other |

---

## Rules of Inference (Equivalence Rules)

These rules establish logical equivalences that can be applied bidirectionally:

| Rule | Notation | Name |
|------|----------|------|
| **Commutation (Com)** | P ∧ Q ⊣⊢ Q ∧ P; P ∨ Q ⊣⊢ Q ∨ P | Order doesn't matter for ∧ and ∨ |
| **Association (Assoc)** | P ∧ (Q ∧ R) ⊣⊢ (P ∧ Q) ∧ R; P ∨ (Q ∨ R) ⊣⊢ (P ∨ Q) ∨ R | Grouping doesn't matter |
| **Implication (Impl)** | P → Q ⊣⊢ ¬P ∨ Q | Conditional equivalent to disjunction |
| **Exportation (Exp)** | P → (Q → R) ⊣⊢ (P ∧ Q) → R | Nested conditionals can be flattened |
| **De Morgan (DeM)** | ¬(P ∧ Q) ⊣⊢ ¬P ∨ ¬Q; ¬(P ∨ Q) ⊣⊢ ¬P ∧ ¬Q | Negation distributes over ∧/∨ with flip |
| **Transposition (Trans)** | P → Q ⊣⊢ ¬Q → ¬P | Contrapositive equivalence |
| **Distribution (Dist)** | P ∧ (Q ∨ R) ⊣⊢ (P ∧ Q) ∨ (P ∧ R); P ∨ (Q ∧ R) ⊣⊢ (P ∨ Q) ∧ (P ∨ R) | Distribute ∧ over ∨ and vice versa |
| **Double Negation (DN)** | P ⊣⊢ ¬¬P | Double negation cancels |
| **Idempotence (Idem)** | P ⊣⊢ P ∧ P; P ⊣⊢ P ∨ P | Repeating doesn't change meaning |
| **Equivalence (Equiv)** | P ↔ Q ⊣⊢ (P → Q) ∧ (Q → P); P ↔ Q ⊣⊢ (P ∧ Q) ∨ (¬P ∧ ¬Q) | Two forms of biconditional |

**Symbol Note**: ⊣⊢ indicates logical equivalence (can be substituted bidirectionally).

---

## Rules of Replacement

These rules can be applied to sub-formulas, not just entire statements:

| Rule | Application | Example |
|------|-------------|---------|
| **Substitution of Equivalents** | If φ ⊣⊢ ψ, then any formula containing φ as a sub-formula can have φ replaced with ψ | (P ∧ Q) → R can become (Q ∧ P) → R by Commutation |
| **Scope of Application** | Equivalences can be applied at any depth within a formula | In (P ∨ (Q ∧ R)) → S, can apply distribution to get (P ∨ Q) ∧ (P ∨ R) → S |

---

## Additional Logical Principles (Beyond SD/SD+)

### Quantifier Rules (Predicate Logic)

| Rule | Notation | Description |
|------|----------|-------------|
| **Universal Instantiation (∀E, UI)** | ∀x φ(x) ⊢ φ(t) | From universal, infer any instance |
| **Universal Generalization (∀I, UG)** | φ(a) ⊢ ∀x φ(x) | If φ holds for arbitrary a, infer universal (restrictions apply) |
| **Existential Instantiation (∃E, EI)** | ∃x φ(x) ⊢ φ(a) | From existential, introduce witness (restrictions apply) |
| **Existential Generalization (∃I, EG)** | φ(t) ⊢ ∃x φ(x) | From instance, infer existential |

**Restrictions**:
- UI: Term t must be free for x in φ(x)
- UG: Constant a must not appear in any undischarged assumptions
- EI: Constant a must be "fresh" (not previously used in the proof)

### Quantifier Equivalences

| Rule | Notation |
|------|----------|
| **Quantifier Negation** | ¬∀x φ(x) ⊣⊢ ∃x ¬φ(x); ¬∃x φ(x) ⊣⊢ ∀x ¬φ(x) |
| **Quantifier Distribution** | ∀x (φ(x) ∧ ψ(x)) ⊣⊢ ∀x φ(x) ∧ ∀x ψ(x) |
| **Vacuous Quantification** | ∀x φ ⊣⊢ φ (if x not free in φ) |

---

## Modal Logic Principles (Basic)

| Axiom/Rule | Notation | Description |
|------------|----------|-------------|
| **K Axiom** | ◻(P → Q) → (◻P → ◻Q) | Necessity distributes over conditionals |
| **T Axiom** | ◻P → P | What is necessary is actual |
| **4 Axiom** | ◻P → ◻◻P | Necessity of necessity |
| **B Axiom** | P → ◻◇P | Actuality implies possible necessity |
| **5 Axiom** | ◇P → ◻◇P | Possibility implies necessary possibility |
| **Necessitation** | If ⊢ P, then ⊢ ◻P | Theorems are necessarily true |
| **Possibility Definition** | ◇P ⊣⊢ ¬◻¬P | Possible = not necessarily not |

**Systems**: S5 = K + T + 4 + 5 (most common for metaphysical necessity)

---

## Informal Reasoning Patterns (Not Strictly Formal)

These patterns are common in natural language reasoning but don't have strict formal rules:

### Defeasible Inference Patterns

| Pattern | Structure | Strength |
|---------|-----------|----------|
| **Modus Ponens (defeasible)** | If P then normally Q; P; therefore probably Q | Strong unless defeaters present |
| **Argument from Authority** | Expert E says P; E is reliable on this topic; therefore probably P | Strength varies with expert credibility |
| **Analogical Argument** | A has properties P, Q, R, S; B has P, Q, R; therefore probably B has S | Strength varies with relevance of shared properties |
| **Inference to Best Explanation** | E is evidence; H explains E better than alternatives; therefore probably H | Abductive reasoning |
| **Statistical Syllogism** | Most As are B; a is an A; therefore probably a is B | Strength depends on proportion and reference class |

**Note**: These patterns are not truth-preserving in the strict formal sense, but are rationally compelling in appropriate contexts.

---

## Fallacy Detection Reference

Common patterns that appear formally valid but are substantively flawed:

| Fallacy | Pattern | Why Invalid |
|---------|---------|-------------|
| **Affirming the Consequent** | P → Q, Q ⊢ P | Q could be true for other reasons |
| **Denying the Antecedent** | P → Q, ¬P ⊢ ¬Q | Q could still be true |
| **Equivocation** | P₁ → Q, P₂ ⊢ Q | P₁ and P₂ have different meanings |
| **Begging the Question** | P ⊢ P | Circular—premise assumes conclusion |
| **False Dilemma** | P ∨ Q, ¬P ⊢ Q | Unstated premise that these are the only options |

---

## Notation Variants

Different logical systems use different notation. This table maps common variants:

| Concept | Variants |
|---------|----------|
| **Conjunction** | ∧, &, · |
| **Disjunction** | ∨, v, + |
| **Conditional** | →, ⊃, ⇒ |
| **Biconditional** | ↔, ≡, ⇔ |
| **Negation** | ¬, ~, - |
| **Universal** | ∀, (x) |
| **Existential** | ∃, (∃x) |
| **Necessity** | ◻, L, N |
| **Possibility** | ◇, M, P |
| **Entailment** | ⊢, ⊨ (syntactic vs. semantic) |
| **Equivalence** | ⊣⊢, ≡, ⇔ |

**Recommendation**: Choose one consistent notation system per analysis and maintain it throughout.

---

## Usage Guidelines

1. **SD vs. SD+**: Use SD for educational contexts where students need to build proofs from basic rules. Use SD+ for practical analysis where efficiency matters.

2. **Equivalence vs. Derivation**: Equivalence rules (Com, Assoc, etc.) can be applied bidirectionally anywhere. Derivation rules have direction and may require subproofs.

3. **Checking Validity**:
   - For propositional logic: Truth tables (small formulas) or formal derivation
   - For predicate logic: Formal derivation or model construction
   - For modal logic: Possible worlds semantics or axiom systems

4. **Beyond These Rules**: Natural language reasoning often employs patterns not captured here (analogical, abductive, probabilistic). In such cases, formalize as closely as possible and note the informal elements explicitly.

---
