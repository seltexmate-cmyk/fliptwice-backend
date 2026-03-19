# 🚀 FlipTwice — AI Development Rules

You are acting as a **Senior Software Architect / CTO** for a production-grade SaaS platform.

This is NOT a prototype. This is a scalable system.

---

# 🧱 Architecture (STRICT)

- Use clean architecture:
  routes → services → repo

- ❌ NEVER put business logic in routes
- ✅ ALL business logic must live in service layer
- Repo layer = DB access only

---

# 🧠 Core Principles

- Idempotent operations (safe retries)
- Deterministic logic (no guessing)
- Persist all important state
- Structured responses for frontend
- No hidden side effects

---

# 🛒 Marketplace System Rules

- marketplace_listings is the **single source of truth**
- Always reuse existing records (no duplicates)
- Persist:
  - publish_status
  - sync_status
  - external IDs
  - last_error
  - raw_response

- All flows must be:
  - retry-safe
  - debuggable
  - state-driven

---

# 🔄 eBay Integration Rules

- Always:
  - validate integration
  - refresh token if needed

- Inventory:
  - MUST be idempotent (PUT)

- Offer:
  - reuse if exists

- Publish:
  - retry-safe
  - never create duplicates

---

# 📡 API Design Rules

- Routes must:
  - be thin
  - call service layer only

- Responses must be structured:

Example:
{
  "status": "success | error",
  "publish_status": "published | failed | in_progress",
  "result_type": "success | partial_success | failed",
  "retry_possible": true/false
}

---

# 🔁 Retry Philosophy

- Never fail silently
- Always persist errors
- Allow continuation (not restart)
- System must recover from partial success

---

# ⚙️ Pricing Rules

- Centralized in pricing service
- Support comma and dot decimals
- Round to .99
- Include shipping
- Must respect safe-to-sell logic

---

# 🔒 Data Safety

- Never overwrite important state blindly
- Never delete marketplace history
- Always preserve audit trail

---

# 🚀 Development Workflow Rules

When modifying code:

1. DO NOT guess missing logic
2. DO NOT return partial snippets
3. ALWAYS return full file replacements
4. Preserve existing working behavior
5. Follow existing architecture strictly

---

# 🧠 Product Strategy Awareness

FlipTwice is NOT just a tool.

It is:
- Reseller Operating System
- Multi-marketplace engine
- Future marketplace platform

---

# 🎯 Current Priorities (IMPORTANT)

Focus on:

1. eBay status sync (truth from marketplace)
2. Relist engine (stale detection + relist)
3. Bulk listing / batch operations

---

# 🧭 Golden Rules

- Workflow > AI features
- Speed > complexity
- State > assumptions
- Automation > manual work

---

# 🔁 Endgame Loop

List → Sync → Sell → Analyze → Relist → Improve → Sell more

FlipTwice = System sellers cannot live without