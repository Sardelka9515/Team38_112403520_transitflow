# IM2002 Database Management — Assessment Overview

## READ CAREFULLY.

## Project: TransitFlow

You will implement three databases that power a pre-built LLM+RAG transit assistant. **Team size:** 3-4 students. **Deliverables:** Four separate submissions.

<table style="min-width: 75px;">
<colgroup><col style="min-width: 25px;"><col style="min-width: 25px;"><col style="min-width: 25px;"></colgroup><tbody><tr><th colspan="1" rowspan="1"><p>Deliverable</p></th><th colspan="1" rowspan="1"><p>Who submits</p></th><th colspan="1" rowspan="1"><p>What to submit</p></th></tr><tr><td colspan="1" rowspan="1"><p><strong>Code Repository</strong></p></td><td colspan="1" rowspan="1"><p>Team</p></td><td colspan="1" rowspan="1"><p>GitHub repo link via EEClass. Make sure your repo is public. MAKE SURE THAT YOU NAME YOUR REPO: <strong>Team&lt;Id&gt;_&lt;Team_leader's_studentID&gt;_transitflow</strong>, e.g. Team01_113403999_transitflow</p></td></tr><tr><td colspan="1" rowspan="1"><p><strong>Design Document</strong></p></td><td colspan="1" rowspan="1"><p>Team</p></td><td colspan="1" rowspan="1"><p>Markdown via EEClass</p><p>Name your file Team&lt;Id&gt;_DESIGN_DOC.md, e.g. Team01_DESIGN_DOC.md</p></td></tr><tr><td colspan="1" rowspan="1"><p><strong>Work Allocation Report</strong></p></td><td colspan="1" rowspan="1"><p>Team</p></td><td colspan="1" rowspan="1"><p>Completed <code>WORK_ALLOCATION_TEMPLATE.md</code> via EEClass</p><p>Name your file Team&lt;Id&gt;_WORK_ALLOCATION.md, e.g. Team01_WORK_ALLOCATION.md</p></td></tr><tr><td colspan="1" rowspan="1"><p><strong>Peer Review Report</strong></p></td><td colspan="1" rowspan="1"><p>Each member individually</p></td><td colspan="1" rowspan="1"><p>Completed <code>PEER_REVIEW_TEMPLATE.md</code> via EEClass (confidential)</p><p>Name your file Team&lt;Id&gt;_&lt;StudentID&gt;_PEER_REVIEW.md, e.g. Team01_113403999_PEER_REVIEW.md</p></td></tr></tbody>
</table>

---

## Three Separate Marking Schemes — Each /100

Your submission is graded across three independent components. Each is scored out of 100
and tallied separately. The weighting between components is set by the instructor.

| Component | Guide | What is assessed |
|-----------|-------|-----------------|
| **Static Code** | [STUDENT_GUIDE_CODE.md](STUDENT_GUIDE_CODE.md) | Schema design, query functions, seeding, graph design, code quality |
| **Design Document** | [STUDENT_GUIDE_DOC.md](STUDENT_GUIDE_DOC.md) | ER diagram, normalisation, graph rationale, RAG design, AI usage, reflection |
| **Live Testing** | [STUDENT_GUIDE_LIVE.md](STUDENT_GUIDE_LIVE.md) | Seeding runtime, PostgreSQL query outputs, Neo4j routing outputs |

Read each guide carefully — it explains exactly what is assessed and what earns full marks
for that component.

---

## Task 6 — Optional Extension Bonus · up to +15 per component

Each of the three components has its own independent +15 bonus. You can earn up to +45
across all three if all components are satisfied.

| Component | Bonus | What is graded |
|-----------|-------|----------------|
| Static Code | up to +15 | Code implementation quality, end-to-end functionality, comments |
| Design Document | up to +15 | Section 7: motivation, changes or UI design decisions, testing evidence |
| Live Testing | up to +15 | Live demo, correctness, regression-free integration |

To be eligible for the bonus in **any** component, all four of the following must be present:

1. The extension touches database code (new schema, queries, or seed data), or includes a substantial UI improvement. Substantial means it adds a meaningful new interaction or surfaces data the current UI cannot show — for example, a trip history panel, a route visualiser, or an analytics dashboard. Cosmetic-only changes (theme colours, button labels, layout tweaks) do not qualify. UI-only submissions are capped at 3 marks per component; database extensions are eligible for the full 15.
2. Detailed inline comments explain every new database operation *(not required for UI-only submissions)*.
3. A **Section 7** in your design document covering motivation, changes, example queries, and testing evidence; for UI-only submissions, cover motivation, UI design decisions, and screenshots instead.
4. A **`TASK6.md`** file at the repo root listing every file modified or added, with specific function and table names. Each modified file must also have a `# TASK 6 EXTENSION:` comment near the top.

---

## Individual Contribution Adjustment

The Static Code score is a team score by default, but each member's individual mark may be
adjusted up or down based on their actual contribution. TAs assess contribution using three
sources of evidence:

- **[Work Allocation Report](WORK_ALLOCATION_TEMPLATE.md)** — your team's self-reported breakdown of who did what
- **[Peer Review Reports](PEER_REVIEW_TEMPLATE.md)** — confidential assessments submitted individually by each member
- **GitHub commit history** — commit frequency, volume, and scope per author

If the evidence consistently shows that a member contributed significantly less than their
allocation, their Static Code mark is reduced. If the evidence shows a member consistently
exceeded their allocation, a small upward adjustment is possible.

The Design Document and Live Testing scores are not individually adjusted — they are shared
equally across all team members.
