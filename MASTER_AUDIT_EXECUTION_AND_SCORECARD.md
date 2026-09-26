# QASWA CURRENT AUDIT EXECUTION CONTRACT v1.2

## Authority
`FINAL_MASTER_INSPECTION_CERTIFICATION_STANDARD_v1.1.md` is the frozen inspection authority. `docs/MASTER_ZERO_OMISSION_ZIP_INSPECTION_CONSTITUTION_55_SECTIONS.md` is the detailed backbone. Product truth is reconstructed from the exact ZIP: `prd.md` + `SYSTEM_BLUEPRINT.md` + manifest + feature sequence + actual code/config/data.

## Required order
**ZIP inventory → PRD reconstruction → Blueprint reconstruction → 55-section reconciliation → inspection criteria → local tests/fixes/retests → external code-basis assessment → hybrid reporting → release verdict.**

## Scoring model
1. **Internal Test Score:** only actually executable tests. External dependency/runtime unavailability never lowers this score.
2. **External Test Score (code basis):** static/wiring/data evidence confidence for behavior that cannot be executed locally. This is confidence, not proof.
3. **Hybrid Score:** local score and external code-basis score are shown separately and may also be combined as a reporting aid; the combined number never overrides an external release gate.
4. **Overall Score:** consolidated reporting score. It must always state the operating scope and must never be represented as a bug-free percentage or production certification.

## Section completion
A section is complete only when its requirement is mapped to the ZIP, applicable inspection criteria are covered, locally executable tests pass, external dependencies are separately recorded, and findings/evidence are recorded. Correct implementation = `NO CHANGE REQUIRED`. Confirmed defect = `FIX → regression → affected-chain retest`.

## No omission
Every material ZIP artifact is inventory-covered. New components are mapped into existing 55 sections where possible. A new section is created only for a genuinely independent material risk class not covered by the existing backbone.
