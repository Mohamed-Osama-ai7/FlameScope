# Problem Contract — FlameScope

## Official challenge

**Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data**

The challenge asks for an interactive SI-powered dashboard that summarizes, ranks, and interprets microgravity-combustion findings to provide fire-safety insights for human space exploration.

## User and decision context

Primary users: combustion researchers, spacecraft fire-safety researchers, materials researchers, and engineering teams reviewing evidence for future crewed habitats.

The user is not asking the system to autonomously certify a material or control a fire. They need to answer:

- Which NASA investigations are relevant to the research question?
- Which measurements and findings support the answer?
- Are the experiments genuinely comparable?
- What physical interpretation is justified by the experimental setup?
- What remains uncertain or unmeasured?
- What additional experiment could reduce a clearly stated evidence gap?

## Product thesis

**FlameScope converts fragmented microgravity-combustion research into traceable, regime-aware scientific evidence and defensible analysis.**

A useful result must connect a claim to the source artifact, experimental context, units, method, and uncertainty. A fluent paragraph without that chain is not a valid product output.

## Explicit non-goals

- No real-time spacecraft fire detection or certified alarm.
- No autonomous suppression or vehicle-control commands.
- No universal flammability score across incompatible materials and test rigs.
- No claim of NASA endorsement, deployment, or validation.
- No Moon/Mars partial-gravity prediction unless the source data and model assumptions genuinely support it.

## Core user journey

1. Ask a research question or select a material/condition.
2. Retrieve relevant investigations and source passages/tables.
3. Review evidence cards with source, page/table, conditions, and relevance rationale.
4. Validate whether comparisons are within the same combustion regime and compatible test conditions.
5. Run deterministic quantitative analysis on extracted, quality-checked measurements.
6. View uncertainty, sensitivity, missing variables, and model-domain warnings.
7. Review a concise, cited interpretation and clearly labeled evidence gaps.
8. Export a reproducible evidence brief.
