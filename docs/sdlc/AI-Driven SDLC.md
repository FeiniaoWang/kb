# Spec-Driven AI SDLC

The [`Factory Model`](https://www.kaggle.com/whitepaper-the-new-SDLC-with-vibe-coding):

* Engineering team build the system that produces the software.
* AI agents perform much of the heavy lifting.
* Human act as architects, reviewers, and quality arbiters.

## Software Development Life Cycle

Requirements → Design → Implementation → Testing → Deploy → Maintenance

---

## Requirements

### Goal

The goal is to discover, analyze, and define what and why (the problem, the user needs, and the features required).

### Output

`PRD + C4 Context diagram`: serve as a high-level specification of the system to be built with precise acceptance criteria.

#### PRD

A Product Requirements Document (PRD) acts as the single source of truth for the team, outlining what to build, why it matters, and how success will be measured.
But "single source of truth" doesn't mean that the PRD is static. It evolves as the team learns more about the problem space, user needs, and technical constraints.

##### Key Sections

* **Objective & Background**: The core problem being solved and the business goals the product aims to achieve.
* **Features & Requirements**: Functional behaviors and non-functional requirements(e.g., performance or security).
* **User stories**: The biggest section of the PRD or a separate document. A comprehensive set of user stories that describe the expected behavior of the system from the user's perspective. It serves as the specification of functional behaviors.

#### C4 Context Diagram

A C4 Context Diagram provides a high-level, 10,000-foot view of how a software system fits into its surrounding environment. It serves as a satellite map identifying exactly who uses the software (actors) and which external systems or third-party services it depends on, completely omitting low-level technical details.

##### Key Purposes

* **Sets Boundaries**: Clearly defines the exact scope of your software system and distinguishes it from the rest of the world.
* **Identifies Integration Points**: Exposes all external dependencies, such as external system APIs and events.
* **Bridging the Communication Gap**: Because it avoids code, protocols, and technology stacks, it is designed to be easily understood by both highly technical developers and non-technical business stakeholders.
* **Onboarding Tool**: Acts as the perfect introductory map for new team members or external partners to understand the business context before diving into the code.

### Roles & Responsibilities

#### Product Manager/Business Analyst

* Leads the draft of the `PRD`.
* Creates the `C4 Context Diagram` with AI tools.
* Use the `Grill Me` skill to rigorously stress-test the problem statement and ensure that the team is solving the right problem.
* Use the `Storyteller` skill to brainstorm and generate comprehensive user stories and edge cases.

#### Software Engineer

* Provides technical `guidance`.
* Validates and confirms external integration `interfaces`.
* Build `POCs` to validate technical feasibility.

#### UX Designer

* Use AI tools to create prototypes of key user flows.

#### QA Engineer

* Work with UX Designer to turn key user stories into AI-controlled test automation.

## Design

### UX design and prototyping

### Architecture design

### User Acceptance Tests design

Architecture generation tools transform business needs into database schema proposals, UI wireframes, and sequence diagrams, expediting the structural blueprint.

## Implementation

The use of repo-aware assistants (such as Cursor, Windsurf, or GitHub Copilot Enterprise) allows developers to build entire feature sets directly from natural language prompts.

## Testing

Automated Test-Driven Development (TDD) policies are now standard. AI agents generate complex unit and regression test suites concurrently with the code itself, closing previous automation gaps.

### Agentic QA

It’s more than just an automation of a manual process, it actually represents a whole new paradigm. We can now deploy intelligent agents that understand applications and explore them autonomously. As a result, we get both speed and quality, not one or the other.
This isn’t the future. Teams are doing it now. They are shipping faster, catching more bugs, and spending less time maintaining test infrastructure.

## Deploy

Infrastructure-as-Code (IaC) is augmented by AI models that write, maintain, and validate deployment scripts based on real-time system metrics.

## Maintenance

Log summarization and bug-localization tools turn raw server errors into readable narratives, allowing for rapid root-cause analysis.