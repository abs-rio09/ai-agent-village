# MASTER PROMPT — AI AGENT VILLAGE
## Build a Complete, Local-First Personal Multi-Agent Management Platform

**Role:** You are a Principal Software Architect, Senior Full-Stack Engineer, AI Agent Systems Engineer, Database Architect, and Product Designer.

**Project Owner:** Abu Bakkar Siddik (Riyan)

**Project Name:** AI Agent Village

**Target Environment:** Ubuntu Linux Desktop

**Development Model:** Claude Fable 5.2 — High Effort

---

# 1. PROJECT VISION

I want you to build a complete, functional software product called **AI Agent Village**.

This is not a normal chatbot, a simple AI assistant, or a collection of unrelated agents.

I want a personal AI-powered digital village that runs on my own PC. The village will contain multiple departments, offices, and specialized AI agents. Every agent will have its own responsibilities, identity, tools, permissions, and working environment.

The organizational concept is inspired by a real administrative village:

- I am the Village Chairman.
- The Central Administration manages the entire village.
- Each Upazila manages a major work domain.
- Each Upazila contains multiple Unions.
- Each Union contains 9 Wards by default.
- Each Ward has an Office.
- Each Office employs one or more specialized Agents.

Agents should communicate, delegate tasks, exchange information, and collaborate to complete work.

I should be able to operate the entire system through a beautiful web dashboard without manually modifying source code or configuring complicated infrastructure.

**My ultimate goal: Build once, configure easily, and manage my digital village through a simple interface.**

You are the long-term owner and maintainer of this codebase. You have responsibility for its engineering quality, architecture, reliability, and maintainability.

# 2. NON-NEGOTIABLE REQUIREMENTS

These requirements have the highest priority.

1. The application must run locally on my Ubuntu PC.
2. Initial setup must be simple and guided.
3. Docker must NOT be mandatory.
4. PostgreSQL, Redis, RabbitMQ, Kubernetes, and cloud servers must NOT be mandatory for the first release.
5. The first version must work without any paid AI API key through a functional Demo Mode.
6. I must be able to manage Upazilas, Unions, Wards, Offices, and Agents from the dashboard.
7. I must not need to edit Python or TypeScript files to create or configure ordinary Agents.
8. Agents must have configurable instructions, tools, permissions, and memory.
9. The system must support optional local AI and cloud AI providers.
10. Semi-autonomous operation with human approval must be built into the architecture.
11. The application must preserve its data across restarts.
12. The project must include working setup, start, stop, status, logs, and backup commands.
13. Implement working features, not just UI mockups.
14. Do not claim an external integration is working unless it has been genuinely connected and tested.
15. Do not stop after producing a plan. Implement the application.

# 3. HARDWARE AND ENVIRONMENT

Target my existing development machine:

- Operating System: Ubuntu Linux
- CPU: AMD Ryzen 7 5700G
- RAM: 8 GB
- Storage: 512 GB SSD
- GPU: Integrated Radeon Graphics

Design the application for modest hardware.

Avoid unnecessary background processes and excessive memory consumption.

Do not require multiple large language models to run simultaneously.

The application should remain usable when no local LLM is running.

Do not automatically download large AI models.

# 4. TECHNICAL STACK

Use a maintainable modular architecture.

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- Lucide icons
- A clean component-based architecture

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic where appropriate

## Database

- SQLite as the default database.
- Enable reliable transactions and appropriate SQLite configuration.
- Keep the data access layer structured so that PostgreSQL can be introduced later.
- Do not require a separate database server for the initial release.

## AI Runtime

Create a provider-independent AI layer supporting:

1. Demo Provider: Works without an API key.
2. Ollama Provider: Connects to an already installed local Ollama instance.
3. Anthropic API Provider: Optional cloud AI integration using a separately supplied API key.

The provider must be configurable through the application Settings page.

Never assume the Claude Code subscription or its login credentials can be reused as an application API key.

## Additional Tools

- APScheduler for scheduled background tasks.
- Local filesystem for documents.
- SQLite FTS5 or a lightweight alternative for basic document search.
- Python PDF generation libraries.
- Pytest for backend testing.
- Frontend testing with appropriate TypeScript-compatible tools.

Do not introduce additional infrastructure without a clear technical reason.

# 5. VILLAGE ADMINISTRATIVE ARCHITECTURE

Implement this hierarchy:

Village
  └── Central Administration
       └── Upazila
            └── Union
                 └── Ward
                      └── Office
                           └── Agent(s)

## Chairman

I am the only initial owner and administrator.

My responsibilities:

- Create and manage departments.
- Assign responsibilities.
- Create, configure, enable, and disable Agents.
- Manage permissions.
- Monitor tasks.
- Review approval requests.
- View reports.
- Control AI model configuration.
- Manage village settings and backups.

## Central Administration

Create a Central Manager that:

- Understands my requests.
- Classifies incoming tasks.
- Finds the appropriate Upazila and Office.
- Delegates work to the correct Agent.
- Coordinates multiple Agents when necessary.
- Collects and verifies their outputs.
- Creates final reports.
- Requests my approval for sensitive actions.

Central Manager must not independently execute every task.

## Default Upazila Templates

Provide these six configurable templates:

1. Study Upazila
2. Business Upazila
3. Career & Job Preparation Upazila
4. Research Upazila
5. Project Development Upazila
6. Personal Management Upazila

Allow new Upazilas to be created at any time.

## Union and Ward Rules

- Each Upazila should have 4–5 Unions by default.
- Each Union should have 9 default Wards.
- Each Ward should automatically receive an Office when a standard structure is generated.
- Allow custom Union and Ward names.
- Allow adding more organizational units later.
- Do not hardcode the number of departments or Agents into the application logic.

Create a one-click "Generate Standard Upazila Structure" action.

This should generate the selected Upazila's suggested Unions, 9 Wards per Union, and default Offices.

# 6. AGENT SYSTEM

Build a proper Agent Registry and reusable Agent Template System.

Every Agent must have:

- Unique ID
- Display name
- Avatar or character appearance
- Role
- Description
- Assigned Upazila
- Assigned Union
- Assigned Ward
- Assigned Office
- System instructions
- Allowed tools
- Permissions
- AI provider configuration
- Memory configuration
- Working schedule
- Current status
- Task history

## Agent templates

Provide templates such as:

- Village Manager
- Office Manager
- Pion / Helper
- Study Assistant
- Teacher / Tutor
- Research Librarian
- Business Manager
- Sales Assistant
- Customer Support Agent
- Accountant
- Daily Reporter
- Doctor / General Wellness Assistant
- Repair Technician
- Technical Support Agent
- Project Manager

Doctor agents must provide general information and wellness guidance only. They must not independently diagnose or prescribe treatment.

Repair agents should troubleshoot software and system issues through approved tools. They must not have unrestricted terminal access.

I should be able to create a new Agent from the dashboard by:

1. Choosing a template.
2. Entering its name.
3. Assigning its Office.
4. Selecting its responsibilities.
5. Configuring its tools and permissions.
6. Saving and activating it.

I must not need to write code for these ordinary configuration changes.

## Human-like Agent Characters

Give the Village a friendly visual identity.

Agents should appear as small humanoid robot characters with different uniforms or accessories according to their roles.

Examples:

- Manager: Formal outfit and identification badge.
- Pion: Helper uniform.
- Doctor: Medical-style coat with a clearly limited assistance role.
- Repair Technician: Tool belt and maintenance uniform.
- Researcher: Books or laboratory accessories.
- Sales Agent: Business uniform.

Each character should have:

- Name.
- Role.
- Office location.
- Status indicator.
- Current task indicator.

Use reusable SVG/CSS-based illustrations or lightweight assets.

Avoid relying on large external image downloads.

# 7. INTERACTIVE VILLAGE MAP

This is one of the most important visual features.

Create a beautiful, interactive, top-down/isometric Village Map.

The map should look like a small organized digital town.

It should contain:

- Central Administration building.
- Study Upazila building.
- Business Upazila building.
- Career Upazila building.
- Research Upazila building.
- Project Development building.
- Personal Management building.
- Individual Union offices.
- Ward buildings.
- Agent workspaces.
- Paths, roads, gardens, signs, and a central plaza.

Display the humanoid robot Agents around their respective workplaces.

The visual inspiration is a futuristic but welcoming smart village.

Important: The map must be a functional application interface, not just a static decorative picture.

Interactions:

- Clicking an Upazila opens its details.
- Clicking a Union opens its Offices.
- Clicking a Ward opens its Office.
- Clicking an Agent opens its profile.
- Show working, idle, waiting, and offline indicators.
- Show the number of active tasks.
- Allow navigation back through the hierarchy.

Provide an alternative accessible list/tree navigation for users who do not want to use the visual map.

# 8. CORE MANAGEMENT SYSTEMS

Implement these systems as independent backend modules.

## A. Agent Registry

Create, edit, activate, pause, disable, and delete Agents safely.

Keep historical records when an Agent is disabled.

## B. Task Management

Every task should contain:

- Task ID
- Task title
- Description
- Created by
- Assigned Agent
- Parent task ID
- Priority
- Input
- Output
- Status
- Creation time
- Execution time
- Completion time
- Error information

Task statuses:

- QUEUED
- ASSIGNED
- RUNNING
- WAITING_APPROVAL
- SUCCEEDED
- FAILED
- CANCELLED

Support task delegation and child tasks.

## C. Communication System

Implement structured Agent-to-Agent communication.

Messages should contain:

- Message ID
- Sender Agent
- Receiver Agent
- Task ID
- Message type
- Structured payload
- Timestamp

Agents should not be allowed to bypass permissions through direct communication.

## D. Memory System

Provide three memory scopes:

1. Village Memory: Shared information accessible according to permissions.
2. Upazila Memory: Department-specific knowledge.
3. Agent Memory: Agent-specific notes and working context.

Support temporary task context separately.

Provide the ability to review and delete stored memories.

Do not put private customer information into general shared memory.

## E. Tool Registry

Create a centralized tool registry.

Examples:

- Read permitted documents.
- Search local knowledge.
- Create a document.
- Generate PDF.
- Create task.
- Request information from another Agent.
- Read configured calendar data.
- Retrieve product information.
- Verify inventory.

Agents must only use assigned tools.

Do not expose arbitrary shell execution or unrestricted filesystem access.

## F. Approval System

Implement a proper Human-in-the-Loop system.

Routine read and analysis operations may execute automatically.

Pre-authorized file creation and ordinary task updates may execute automatically.

Sensitive or irreversible operations must require Chairman approval.

Examples:

- Sending external messages.
- Deleting important files.
- Spending money.
- Issuing refunds.
- Publishing marketing material.
- Performing consequential external actions.

An approval request must display:

- Requesting Agent
- Requested action
- Reason
- Tool
- Expected changes
- Risk information

Support Approve and Reject.

Record every decision in the audit log.

# 9. 24/7 AUTOMATION

I want some Agents to work continuously in the background.

Create a lightweight background scheduler.

Supported operations:

- Periodic tasks.
- Daily reports.
- Scheduled document processing.
- Deadline checks.
- Stock alerts.
- Agent health checks.
- Pending task retries where safe.
- Background workflow execution.

Create an application-level task queue using the database initially.

Tasks must persist across application restarts.

Use safe retries and idempotency to avoid duplicate operations.

## Startup and recovery

Provide:

- Start application.
- Stop application.
- Restart application.
- Check application status.
- View application logs.
- Optional automatic startup when I log into Ubuntu.
- Automatic recovery of interrupted safe tasks.

Do not require a complex cloud deployment.

Be transparent that local 24/7 operation requires the PC, power, and network to remain available.

# 10. BUSINESS & COMMERCE MODULE

Create a reusable Commerce Management module.

This will eventually power Facebook Page sales and other online stores.

Include:

- Product management.
- Product variants.
- Size and color management.
- Product pricing.
- Inventory tracking.
- Customer records.
- Conversations.
- Orders.
- Order items.
- Delivery charges.
- Payment records.
- Order reports.

## Product database

Each product should contain:

- Product ID
- Name
- Description
- SKU
- Images
- Price
- Variants
- Available quantity
- Stock history
- Active or inactive status

## Order workflow

Build a working local order simulation.

Example:

Customer asks product price.

Agent retrieves the actual price from the database.

Customer chooses size.

Agent verifies size availability.

Customer specifies quantity.

Agent checks stock.

Agent collects:

- Customer name
- Phone number
- Delivery address
- Product
- Size
- Quantity

Agent creates a final order summary.

Customer must explicitly confirm the order.

Only after explicit confirmation:

- Validate current inventory again.
- Perform an atomic stock reservation.
- Generate a unique order ID.
- Save the order.
- Record stock movement.
- Produce confirmation information.
- Generate an order report.

Never invent product prices or stock quantities.

Never treat an order as confirmed before explicit customer confirmation.

## Facebook Messenger Integration

Design the system for official Meta Messenger Platform integration.

Create:

- Messenger connector interface.
- Webhook receiver.
- Webhook signature verification.
- Incoming event processing.
- Outgoing message interface.
- Conversation management.
- Duplicate event handling.
- Connector status page.
- Integration configuration page.

Do not pretend the connector is live without valid Meta credentials, permissions, public HTTPS webhook access, and a successful connection test.

If credentials are unavailable, provide a fully functional Messenger Sandbox/Test Conversation interface.

Keep the real integration ready to configure later.

Respect Meta's current messaging rules, permission requirements, and messaging windows. Verify current official Meta documentation before implementing or changing the connector.

Do not spam customers or send unapproved promotional messages.

# 11. OTHER UPazila TEMPLATES

Create configurable suggested Union templates.

## Study Upazila

- Academic Management
- Course Learning
- Exam Preparation
- Research Paper Learning
- Academic Documentation

Suggested Ward responsibilities:

1. Class Routine
2. Assignment & Deadline
3. Exam Preparation
4. Learning Materials
5. Note Making
6. Course Tutor
7. Academic Progress
8. Study Planning
9. Daily Academic Reporting

## Business Upazila

- Business Strategy
- Product Management
- Marketing & Branding
- Customer & Sales
- Finance & Operations

## Career Upazila

- Software Engineering Skills
- Competitive Programming
- Job Opportunities
- CV & Portfolio
- Interview Preparation

## Research Upazila

- Paper Discovery
- Literature Review
- Research Topic Discovery
- Data Analysis
- Research Documentation

## Project Development Upazila

- Project Planning
- Frontend Development
- Backend Development
- Database & API
- Testing & Deployment

## Personal Management Upazila

- Daily Routine
- Task Management
- File Management
- Knowledge Management
- Daily Reporting

These are templates. I must be able to rename or change them without modifying code.

# 12. FILE & KNOWLEDGE MANAGEMENT

Provide a local document management system.

Supported initial file types:

- PDF
- DOCX
- TXT
- Markdown

Features:

- Upload documents.
- Organize by Upazila and Office.
- Extract available text.
- Search documents.
- Generate summaries.
- Create notes.
- Generate PDF reports.
- Preserve source document references.

Do not send local documents to a cloud AI provider without explicit user configuration and authorization.

Generated files must be stored locally.

# 13. DASHBOARD DESIGN

Create a premium, professional, visually attractive dashboard.

Design language:

- Modern dark interface with a clean layout.
- Professional typography.
- Consistent spacing.
- Subtle animations.
- Well-designed cards.
- Clear icons.
- Responsive desktop interface.
- Good readability.
- Accessible controls.

Do not make it look like a generic admin dashboard.

It should feel like a modern control center for a smart digital village.

## Required pages

1. Village Overview
2. Interactive Village Map
3. Upazila Management
4. Union Management
5. Ward & Office Management
6. Agent Management
7. Agent Profile
8. Agent Chat
9. Task Center
10. Approval Center
11. Communication History
12. Memory & Knowledge Center
13. Document Manager
14. Commerce Dashboard
15. Product & Inventory Management
16. Order Management
17. Reports & Analytics
18. Integration Settings
19. AI Model Settings
20. Application Settings
21. Backup & Restore
22. System Health & Logs

## Dashboard overview

Display:

- Total Upazilas
- Total Unions
- Total Wards
- Total Offices
- Total Agents
- Active Agents
- Running Tasks
- Pending Approvals
- Completed Tasks
- Failed Tasks
- Recent Activity

All dashboard data must come from the backend.

Do not use hardcoded fake statistics in the real dashboard.

# 14. EASY SETUP AND OPERATION

This is a critical requirement.

I do not want to manually configure 20 services or modify multiple configuration files.

Create a single command-line entry point named:

`./village`

Supported commands:

```bash
./village setup
./village start
./village stop
./village restart
./village status
./village logs
./village doctor
./village backup
./village restore
```

## Setup

`./village setup` should:

1. Check the required software.
2. Check Python and Node.js availability.
3. Create a Python virtual environment.
4. Install backend dependencies.
5. Install frontend dependencies.
6. Build the frontend.
7. Create local application data directories.
8. Initialize the database.
9. Create initial application settings.
10. Prepare the first-run browser setup wizard.

Do not use sudo automatically.

Do not install system-wide packages without my authorization.

If an essential dependency is missing, show the exact command needed to install it.

## First-run browser wizard

When I open the application for the first time, show a guided setup.

Collect:

- Village name.
- Chairman name.
- Administrator password.
- Timezone (default: Asia/Dhaka).
- AI mode.
- Optional AI provider configuration.
- Default village structure.

Offer these AI modes:

1. Demo Mode — no API key required.
2. Local AI — connect to an existing Ollama instance.
3. Cloud AI — configure an authorized API provider.

Do not require an AI provider to finish the basic application setup.

## Starting the application

`./village start` should start the application reliably and print:

- Running status.
- Local URL.
- Process information.
- Where to view logs.

Serve the built frontend and backend through a simple local application endpoint.

The default local URL should be:

`http://127.0.0.1:8000`

Stop and status commands must work reliably.

Provide an optional, user-approved Ubuntu login startup configuration.

Do not automatically expose the application to the public internet.

# 15. SECURITY AND DATA PRIVACY

Implement:

- Local administrator authentication.
- Strong password hashing.
- Secure session management.
- Environment-based secrets.
- Proper filesystem permissions.
- Server-side permission checks.
- Secure API validation.
- Safe document uploads.
- Audit logging.
- Data backup and restoration.
- Protection against duplicate operations.
- Localhost-only binding by default.

Treat all external emails, documents, websites, and customer messages as untrusted input.

Never allow their content to override the application's security rules.

No Agent should have unlimited access to the operating system.

Do not log sensitive passwords, API tokens, or complete payment credentials.

Keep customer data restricted to authorized modules.

# 16. BACKUP AND RESTORE

Create simple backup tools.

`./village backup` should create a backup containing:

- Database.
- Application settings excluding exposed secrets.
- User-selected local documents.
- Agent configurations.
- Village organizational structure.
- Reports and metadata.

Provide a restore operation with a clear confirmation step.

Test the backup and restore process.

Do not claim backup is successful until it has been verified.

# 17. DEVELOPMENT WORKFLOW

You must implement the project in a disciplined, incremental way.

First, inspect the current working directory.

Do not delete or overwrite unrelated existing files.

Then:

1. Create the project architecture.
2. Write `docs/ARCHITECTURE.md`.
3. Write `docs/BUILD_PLAN.md`.
4. Create `CLAUDE.md` with permanent project instructions.
5. Create `PROGRESS.md` to record completed work and pending work.
6. Implement the first functional vertical slice.
7. Run backend and frontend tests.
8. Continue implementing the remaining release requirements.
9. Test the complete application.
10. Fix errors before reporting completion.

Do not spend the entire task producing documentation without implementation.

Do not stop after architecture or UI design.

Work in milestones, but continue autonomously through all work that does not require my credentials or decision.

Use subagents only when parallel work is genuinely useful. Avoid unnecessary agent proliferation.

Keep me informed with brief progress updates during long operations.

If something fails:

- Inspect the actual error.
- Find its cause.
- Fix it.
- Retry the relevant test.
- Record unresolved limitations honestly.

Do not hide errors or remove failing tests to report success.

Do not claim a feature works without testing it.

If an external integration requires credentials that I have not supplied, finish the internal integration interface and test sandbox, document the missing configuration, and continue with other implementation work.

# 18. TESTING REQUIREMENTS

Create automated tests for:

## Organization

- Create Village.
- Create Upazila.
- Create Union.
- Generate nine Wards.
- Create Offices.
- Assign Agents.

## Agents

- Register Agent.
- Configure Agent.
- Assign tools.
- Enforce permissions.
- Pause and disable Agent.

## Tasks

- Create Task.
- Assign Task.
- Execute Task.
- Delegate Task.
- Save output.
- Handle failure.
- Resume safe interrupted work.

## Approvals

- Create approval request.
- Approve request.
- Reject request.
- Ensure unauthorized users cannot approve.

## Commerce

- Create product.
- Add variants.
- Update stock.
- Validate quantity.
- Prevent overselling.
- Collect order information.
- Require explicit customer confirmation.
- Create unique order ID.
- Record inventory movements.

## Application

- Fresh installation.
- Restart.
- Data persistence.
- Backup.
- Restore.
- Application health.

Run the tests and fix failures.

Add frontend interaction tests for critical dashboard workflows.

# 19. RELEASE DEFINITION

The first release must be a usable local application.

I define the initial release as complete only when I can:

1. Run one setup command.
2. Open the application in my browser.
3. Complete the first-run setup.
4. See my Village Dashboard.
5. Create and manage Upazilas.
6. Generate Unions, Wards, and Offices.
7. Create Agents from templates.
8. View humanoid Agent characters on the interactive map.
9. Configure Agent instructions and permissions.
10. Send tasks through the Central Manager.
11. See task execution and activity history.
12. Run the Demo Agent workflows.
13. Review approval requests.
14. Manage local documents.
15. Create product and inventory records.
16. Test a customer ordering conversation in Sandbox Mode.
17. Generate reports.
18. Restart the application without losing data.
19. Back up and restore the Village.
20. Operate the application without Docker or a separate database server.

A feature that needs an external service must have a clear setup status and must not be falsely represented as connected.

# 20. DELIVERY REQUIREMENTS

At the end of implementation, provide:

1. Complete project source code.
2. Complete directory structure.
3. `README.md`.
4. `CLAUDE.md`.
5. Architecture documentation.
6. Database documentation.
7. API documentation.
8. Installation and setup instructions.
9. Testing report.
10. Backup and restore instructions.
11. Known limitations.
12. Next development milestones.

Most importantly, give me the simplest possible instructions:

```bash
cd ~/Projects/ai-agent-village
./village setup
./village start
```

Then tell me which local URL to open.

After the initial setup, normal operation should be as simple as:

```bash
cd ~/Projects/ai-agent-village
./village start
```

I should not need to repeat the installation process every time.

# 21. FINAL ENGINEERING INSTRUCTIONS

The most important principle is:

**BUILD A WORKING PRODUCT, NOT A PRESENTATION OF A PRODUCT.**

Do not optimize for the number of files, the number of Agents, or the complexity of the architecture.

Optimize for:

- Reliability.
- Simplicity.
- Usability.
- Data integrity.
- Security.
- Low resource usage.
- Easy maintenance.
- Easy future expansion.

Keep the initial platform modular so that new Upazilas, Unions, Wards, Offices, Agent types, Tools, and integrations can be added without rewriting the core.

Do not turn this into a complicated enterprise microservices project.

Prefer a well-structured modular application.

Do not make all Agents independent AI processes. Use a shared execution runtime with separate Agent identities, configurations, tools, and permissions.

Do not automatically execute destructive operations or publish/send external content without the appropriate approval.

Do not invent successful integrations, generated reports, test results, or deployment status.

If you discover a better implementation choice, use sound engineering judgment, document the decision, and continue without creating unnecessary complexity.

**My expectation: When I finish your initial implementation, I should have a real, functioning AI Agent Village on my Ubuntu PC. I should be able to open it, enter my village, manage its departments, create Agents, assign work, monitor activity, and expand the system gradually through a simple dashboard.**

Now inspect the workspace, establish the architecture, and begin building AI Agent Village.
