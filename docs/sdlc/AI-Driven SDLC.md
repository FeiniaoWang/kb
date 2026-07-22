# Spec-Driven AI SDLC

The [`Factory Model`](https://www.kaggle.com/whitepaper-the-new-SDLC-with-vibe-coding):

* The engineering team builds the system that produces the software.
* AI agents perform much of the heavy lifting.
* Humans act as architects, reviewers, and quality arbiters.

## Software Development Life Cycle

Requirements → Design → Implementation → Testing → Deploy → Maintenance

---

## Requirements

### Goal

Discover, analyze, and define what to build, for whom, and how to measure.

### Output

`PRD` + `C4 Context Diagram`: together they form the high-level specification of the system to be built, with precise acceptance criteria.

#### PRD

A Product Requirements Document (PRD) aligns everyone on what's being built, for whom, why it matters, and how success will be measured.

* Please use the `prd` skill to co-author PRDs with AI agents. The skill will ensure the important sections this SDLC requires are included.
* A PRD is not static — PRD evolves as the team learns more about the problem space, user needs, and technical constraints.
* For a complex system that evolves multiple teams, the PRD is often broken into a master PRD and multiple sub-PRDs, each focusing on a specific feature set or subsystem.

##### Key Sections

These key sections are important for driving the later stages of the SDLC:

* **Target Personas**: List who the product is for and what they need to accomplish.
* **User Stories**: Usually the largest section of the PRD (or a separate document). For each persona, a comprehensive set of user stories describing the expected behavior of the system from the user's perspective, each with precise acceptance criteria — together they are the specification of functional behavior.

#### C4 Context Diagram

A C4 Context Diagram provides a high-level, 10,000-foot view of how a software system fits into its surrounding environment. Like a satellite map, it shows exactly who uses the software (actors) and which external systems or third-party services it depends on, while omitting all low-level technical detail.

* Please use the `c4-modeling` skill to co-author C4 diagrams with AI agents.
* A C4 Context Diagram is always paired with a PRD. There can be a context diagram for the master PRD, and multiple context diagrams for sub-PRDs that zoom in on specific subsystems or feature sets.

##### Key Purposes

* **Sets Boundaries**: Defines the exact scope of the system and distinguishes it from the rest of the world.
* **Identifies Integration Points**: Exposes all external dependencies, such as third-party APIs and events.
* **Bridges the Communication Gap**: Because it avoids code, protocols, and technology stacks, it is equally understandable to developers and non-technical business stakeholders.
* **Onboards New People**: Serves as the introductory map for new team members or external partners to understand the business context before diving into the code.

### Roles & Responsibilities

#### Product Manager / Business Analyst

* Leads the drafting of the PRD with the `prd` skill.
* Creates the C4 Context Diagram with the `c4-modeling` skill.
* Uses the `storyteller` skill to brainstorm and generate comprehensive user stories and edge cases.

#### Software Engineer

* Provides technical guidance.
* Validates and confirms external integration interfaces.
* Builds POCs to prove technical feasibility.

#### UX Designer

* Uses AI tools to prototype key user flows.
* No visual design is required at this stage, the goal is to test out key screens and flows.

#### QA Engineer

* Works with the UX Designer to turn key user stories into AI-driven test automation.

## Design

### Goal

Define the software solution to be built, including software architecture, UX design, and test strategy.

### Output

`Architecture Design` + `UX Design` + `Test Strategy & Plan`: together they form a comprehensive blueprint of the system to be built.

#### Architecture design

* An architecture design document
* A C4 Container Diagram

#### UX design

* A complete UI/UX design document
* A more complete prototype that covers all key user flows and optionally includes visual design.

#### Test Strategy & Plan

* A test strategy document: defines how to setup AI agents for test automation based on the systems and infrastructure.
* A test plan document: for each persona, how to run a testing agent that go through the user stories and where to save the AI generated feedbacks.

### Roles & Responsibilities

#### Software Engineer

* Use the `kb-author` skill to create architecture design and save it into the Knowledge Base.
* Use the `c4-modeling` skill to create the C4 Container Diagram.
* Validates and confirms inter-systems integration interfaces.
* Builds POCs to prove technical feasibility.

## Implementation

The use of repo-aware assistants (such as Cursor, Windsurf, or GitHub Copilot Enterprise) allows developers to build entire feature sets directly from natural language prompts.

## Testing

Automated Test-Driven Development (TDD) policies are now standard. AI agents generate complex unit and regression test suites concurrently with the code itself, closing previous automation gaps.

### Agentic QA

It’s more than just an automation of a manual process, it actually represents a whole new paradigm. We can now deploy intelligent agents that understand applications and explore them autonomously. As a result, we get both speed and quality, not one or the other.
This isn’t the future. Teams are doing it now. They are shipping faster, catching more bugs, and spending less time maintaining test infrastructure.

## Deploy

Infrastructure-as-Code (IaC) is augmented by AI models that write, maintain, and validate deployment scripts based on real-time system metrics.

## Monitoring & Maintenance

### Production Monitoring Becomes Proactive, Not Reactive
AI agents continuously evaluate logs, metrics, and error patterns. They identify issues before users do.
Examples include:

memory leaks building up slowly
API latency spikes
suspicious traffic patterns
recurring warnings that predict a crash
Support teams finally work ahead of incidents instead of after them.


Log summarization and bug-localization tools turn raw server errors into readable narratives, allowing for rapid root-cause analysis.