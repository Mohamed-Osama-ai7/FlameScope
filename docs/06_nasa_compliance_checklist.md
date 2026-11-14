# NASA Space Apps 2026 — Submission Compliance Checklist

This is an engineering checklist, not legal advice. The official 2026 Participant Terms & Conditions and the Global Organizing Team's challenge-specific instructions control. Local-event logistics may add requirements; verify them with the Cairo Local Lead.

## Registration and team

- [ ] Every participant registered on the global Space Apps website before the chosen event begins.
- [ ] Every participant selected the same local event/team and challenge as required by the platform.
- [ ] Team has no more than six participants globally; confirm Cairo's on-site logistics separately.
- [ ] Any participant under 18 is registered by a parent/legal guardian and accompanied throughout the event, as required by the global terms.
- [ ] Team lead reviewed the full Participant Terms & Conditions and accepts responsibility for accurate project/team submission details.
- [ ] Any affiliation/eligibility question is referred to the Global Organizing Team; do not infer eligibility solely from nationality or a university's informal partnerships.

## Required challenge data

- [ ] At least one NASA data source listed in the exact Flame in Freefall Resources tab is used and traceably incorporated. The Global Organizing Team stated this is required for Global Award eligibility.
- [ ] Every challenge resource is recorded with exact title, URL, retrieval date, version, license, and the feature/analysis that uses it.

## Open source and third-party materials

- [ ] Solution code/materials are made available under a license that satisfies the current Participant Terms and applicable OSI rules.
- [ ] All third-party libraries, model weights, datasets, fonts, images, audio, and video are checked individually for license/terms.
- [ ] Third-party assets are not included if their license/terms conflict with event requirements.
- [ ] All sources are cited, including freely available data and open-source components.
- [ ] No ITAR/EAR-controlled information or restricted export-controlled material is included.
- [ ] No secrets, private participant information, or unauthorized personal data are included.

## AI-generated and AI-assisted material

The Global Organizing Team's November 6, 2026 clarification says AI tools are permitted, but teams must clearly indicate where and how they were used:

- [ ] AI-generated images/videos carry a visible AI-generated watermark.
- [ ] AI-generated audio is disclosed in descriptive text and metadata.
- [ ] AI-generated code/data is disclosed in descriptive text and metadata.
- [ ] AI-generated material does not use, contain, or modify NASA branding or design elements (logos, flags, mission identifiers).
- [ ] Human team members review, test, and take responsibility for submitted code and claims.

## Branding and claims

- [ ] Do not imply NASA endorsement, approval, sponsorship, deployment, or certification.
- [ ] Do not use NASA logos/mission identifiers without express permission.
- [ ] Use NASA name only to accurately describe the challenge/data context, not to market FlameScope as a NASA product.
- [ ] Clearly label FlameScope as an independent research prototype and non-operational tool.

## Verification status of this checklist (2026-11-13)

| Source | Status |
|---|---|
| spaceappschallenge.org (legal terms, challenge page, Resources tab) | **Not read** — TLS certificate untrusted on the audit machine. Every "global rule" above is from the earlier scaffold and must be re-checked in a normal browser. |
| GO Team discussion nasa/spaceapps #1849 | Read. Resources available Nov 12 under the challenge Resources tab; ≥1 NASA data source from Resources required for Global Awards; AI allowed with disclosure/watermark; no NASA branding in generated content. |
| spaceappscairo.com/faqs | Read (local FAQ; it states it is a summary, global terms control). |

## Global (NASA Space Apps) — per Cairo FAQ restatement, confirm against global terms

- [ ] Global hackathon 14–15 Nov 2026; judging starts 16 Nov. Submission after "Submit for Judging" is final; no late edits.
- [ ] Team size 1–6; one team per person; all members incl. Team Owner registered for the **same Local Event** (hard requirement for Global Judging).
- [ ] Under-18: registered and accompanied by parent/guardian; **minors must not appear in video/project submission**.
- [ ] Submission in English: project name, summary, demo link, final project link, detailed description, NASA data used, partner/other data used, AI disclosure.
- [ ] Demo: video ≤30 s (English subtitles if not spoken English) **or** ≤7 slides incl. title. Hosted externally, publicly accessible without login (test in a private window).
- [ ] Judging criteria (equal weight): Impact, Creativity, Validity, Relevance, Presentation.
- [ ] Libraries/templates/APIs allowed only if licence permits and all resources are credited; judges must access the demo without private credentials.
- [ ] Do not start challenge-specific implementation before the hackathon starts; repo infrastructure is allowed.

## Cairo local event — additional requirements

- [ ] Cairo runs **Fri 13 – Sat 14 Nov 2026** (adapted to Egyptian weekend), one day ahead of the global event. **Confirm with organisers** how the global submission window (stated earlier as Nov 14 09:00 → Nov 15 23:59 local) applies to Cairo teams and whether written GO Team approval for the date shift exists (organiser responsibility, but affects eligibility).
- [ ] Separate Cairo local registration form (in addition to global), using the **same email** as the global account.
- [ ] Submit the project through the **Cairo local submission form and** the global platform.
- [ ] Up to 5 members on-site; a 6th participates virtually. Participation mode assigned by email.
- [ ] Proposal video + literature review were part of Cairo registration (local; may be Arabic). The global submission must be English.
- [ ] Video must be the team's own work (outside production may lead to disqualification).
- [ ] Minors + venue access conflict (venue admits registered participants only) — raise with organisers if any member is under 18.
- [ ] Timing risk: this scaffold pre-dates the event. Confirm with the Local Lead that it counts as permitted "infrastructure" and that challenge-specific code was written during the event window.

## Licensing and third-party review (engineering, not legal advice)

| Item | Licence | Note |
|---|---|---|
| PSI-69 / PSI-25 / PSI-98 data | CC0-1.0 (PSI metadata) | Cite DOIs anyway; CC0 does not imply NASA endorsement. PSI-98 quarantined (metadata conflict). |
| FastAPI, Pydantic, NumPy, SciPy, React, Vite | MIT / BSD | Permissive. |
| BGE-M3, BGE Reranker v2-M3 (planned) | Check model card at adoption time | Not downloaded; record exact revision + licence before use. |
| SAM 2.1 (optional, planned) | Check at adoption time | Not downloaded. |
| Hosted LLM API (planned) | Provider terms | Do not send unpublished/private data; disclose use. |
| Project's own licence | **Missing** | Add an OSI-approved LICENSE file (e.g. MIT or Apache-2.0) before submission — confirm requirement in global terms. |

## Sources to verify at submission time

- Official challenge: https://www.spaceappschallenge.org/2026/challenges/flame-in-freefall/
- Global 2026 overview/timeline: https://www.spaceappschallenge.org/2026/
- Participant terms: https://www.spaceappschallenge.org/legal/
- Cairo event: https://spaceappscairo.com/
- Cairo FAQ: https://spaceappscairo.com/faqs
- GO Team clarification on Resources and AI disclosure (Nov 6, 2026): https://github.com/nasa/spaceapps/discussions/1849
