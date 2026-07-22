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

* Use the `prd` skill to co-author PRDs with AI agents. The skill ensures the sections this SDLC requires are included.
* A PRD is not static — it evolves as the team learns more about the problem space, user needs, and technical constraints.
* For a complex system involving multiple teams, the PRD is broken into a master PRD and several sub-PRDs, each covering one feature set or subsystem.

##### Key Sections

These key sections are important for driving the later stages of the SDLC:

* **Target Personas**: List who the product is for and what they need to accomplish.
* **User Stories**: Usually the largest section of the PRD (or a separate document). For each persona, a comprehensive set of user stories describing the expected behavior of the system from the user's perspective, each with precise acceptance criteria — together they are the specification of functional behavior.

#### C4 Context Diagram

A C4 Context Diagram provides a high-level, 10,000-foot view of how a software system fits into its surrounding environment. Like a satellite map, it shows exactly who uses the software (actors) and which external systems or third-party services it depends on, while omitting all low-level technical detail.

* Use the `c4-modeling` skill to co-author C4 diagrams with AI agents.
* Every PRD is paired with a context diagram: one for the master PRD, plus one per sub-PRD that zooms in on its subsystem or feature set.

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
* Skips visual design at this stage — the goal is to test key screens and flows, not to finalize the look.

#### QA Engineer

* Works with the UX Designer to turn key user stories into AI-driven test automation.

## Design

### Goal

Define the software solution to be built, including software architecture, UX design, and test strategy.

### Output

`Architecture Design` + `UX Design` + `Test Strategy & Plan`: together they form a comprehensive blueprint of the system to be built.

#### Architecture Design

* An architecture design document.
* A C4 Container Diagram.

#### UX Design

* A complete UI/UX design document.
* A prototype covering all key user flows, optionally including visual design.

#### Test Strategy & Plan

* A **test strategy** document: how to set up AI agents for test automation, given the systems and infrastructure in play.
* A **test plan** document: for each persona, how to run a testing agent through that persona's user stories, and where the agent's generated feedback is saved.

### Roles & Responsibilities

#### Software Engineer

* Uses the `kb-author` skill to write the architecture design and save it into the Knowledge Base.
* Uses the `c4-modeling` skill to create the C4 Container Diagram.
* Validates and confirms inter-system integration interfaces.
* Builds POCs to prove technical feasibility.

#### UX Designer

* Owns the UI/UX design document and the key-flow prototype.

#### QA Engineer

* Owns the test strategy and test plan, working from the user stories and their acceptance criteria.

## Implementation

### Goal

Turn the design blueprint into working code.

Repo-aware assistants (such as Claude Code, Cursor, or GitHub Copilot Enterprise) let developers build entire feature sets from natural language prompts, grounded in the PRD, architecture design, and acceptance criteria produced upstream.

## Testing

### Goal

Verify the system against the acceptance criteria defined in the PRD.

Test-Driven Development is the default policy: AI agents generate unit and regression suites alongside the code itself, closing the automation gaps that previously accumulated.

### Agentic QA

Agentic QA is not merely automation of a manual process — it changes what QA can cover. Agents that understand the application explore it autonomously, so exploratory coverage no longer competes with delivery speed for the same hours.

In practice, teams running this way ship faster, catch more bugs, and spend less time maintaining test infrastructure.

## Deploy

### Goal

Get verified changes into production safely and repeatably.

Infrastructure-as-Code (IaC) remains the foundation; AI models write, maintain, and validate the deployment scripts, using real-time system metrics as input.

## Monitoring & Maintenance

### Goal

Detect and resolve production issues before users report them.

### Proactive Monitoring

AI agents continuously evaluate logs, metrics, and error patterns to surface issues early. Typical signals include:

* Memory leaks building up slowly.
* API latency spikes.
* Suspicious traffic patterns.
* Recurring warnings that predict a crash.

The result is that support teams work ahead of incidents rather than after them.

### Faster Root-Cause Analysis

Log summarization and bug-localization tools turn raw server errors into readable narratives, shortening the path from alert to root cause.