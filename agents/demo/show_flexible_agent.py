#!/usr/bin/env python3
"""
Non-interactive demonstration of the flexible Conseil agent system
"""

import time


def print_section(title):
    """Print a section header"""
    print(f"\n\n{'='*70}")
    print(f"  {title}")
    print('=' * 70)


def simulate_command(command, delay=0.5):
    """Simulate entering a command"""
    print(f"\n$ {command}")
    time.sleep(delay)


def simulate_user_input(prompt):
    """Simulate user input"""
    print(f"\n> {prompt}")
    time.sleep(0.3)


def simulate_response(response, delay=0.1):
    """Simulate agent response with typing effect"""
    print()
    for line in response.split('\n'):
        print(line)
        time.sleep(delay)


# Start demo
print("""
╔══════════════════════════════════════════════════════════════════════╗
║           FLEXIBLE CONSEIL AGENT SYSTEM - LIVE DEMONSTRATION         ║
╚══════════════════════════════════════════════════════════════════════╝
""")

# Show available roles
print_section("1. SHOWING AVAILABLE ROLES")
simulate_command("conseil --list-roles")

print("""
Available Job Roles:

coding:
  Title: Coding Assistant
  Description: Expert coding assistant for development tasks...
  Common files: *.py, *.js, *.ts, *.java, *.cpp, *.go

legal:
  Title: Legal Document Assistant
  Description: Legal document specialist for contracts and agreements...
  Common files: *.md, contracts/*.md, legal/*.md

personal:
  Title: Personal Assistant
  Description: Organized personal assistant for daily tasks...
  Common files: *.md, todos/*.md, notes/*.md, meetings/*.md

finance:
  Title: Financial Assistant
  Description: Financial documentation and analysis assistant...
  Common files: *.md, *.csv, finance/*.md, reports/*.md

research:
  Title: Research Assistant
  Description: Research specialist for information gathering...
  Common files: *.md, research/*.md, notes/*.md, sources/*.md

custom:
  Title: Custom Assistant
  Description: Define your own role with --description and --guidelines
""")

# Legal Assistant Demo
print_section("2. LEGAL ASSISTANT REVIEWING CONTRACT")
simulate_command("conseil --role legal --no-sandbox")

print("""
🤖 Starting Conseil as: Legal Document Assistant
   Sandbox: Disabled ⚠️
   Approval: manual
   Model: gpt-4
------------------------------------------------------------
""")

simulate_user_input("Review the contractor agreement in demo/legal/contractor-agreement.md and identify any issues")

simulate_response("""Analyzing the Independent Contractor Agreement...

## 🚨 Critical Issues Identified:

### 1. **Intellectual Property Rights** (Section 6)
   ❌ Current: "All work product shall be owned by Contractor"
   ✅ Should be: "All work product shall be owned by Company" (work-for-hire)

### 2. **Missing Essential Clauses**:
   - **Indemnification**: No protection against contractor liabilities
   - **Insurance**: No professional liability coverage requirement
   - **Non-Solicitation**: No restriction on poaching employees/clients
   - **Dispute Resolution**: No arbitration clause to avoid litigation

### 3. **Weak Termination Terms** (Section 4)
   - No notice period (recommend 30 days)
   - No return of property clause
   - No survival clauses for ongoing obligations

### 4. **Vague Confidentiality** (Section 5)
   - No definition of "confidential information"
   - No time limit specified
   - No permitted disclosure exceptions

📝 I can draft amendments to fix these issues. Shall I proceed?""")

print("\n⚠️  Manual Approval Required: apply_patch to fix IP clause")
print("[A]pprove / [D]eny / [A]lways approve? [Simulated: Approved]")

# Personal Assistant Demo
print_section("3. PERSONAL ASSISTANT ORGANIZING TASKS")
simulate_command("conseil --role personal --no-sandbox --approval auto")

print("""
🤖 Starting Conseil as: Personal Assistant
   Sandbox: Disabled ⚠️
   Approval: auto
   Model: gpt-4
------------------------------------------------------------
""")

simulate_user_input("Organize my tasks in demo/personal/tasks-today.md by priority and create a time-blocked schedule")

simulate_response("""Creating optimized schedule for Monday...

## 📅 Time-Blocked Schedule

### 🌅 Morning Block (9:00 AM - 12:00 PM)
**9:00-9:30** ➤ Email client about timeline ⚡ [Critical]
**9:30-10:00** ➤ Prep for standup + coffee ☕
**10:00-10:30** ➤ Team standup 👥 [Fixed]
**10:30-12:00** ➤ Deep work: Project proposal 📝 [High Priority]

### 🌞 Afternoon Block (12:00 PM - 5:00 PM)
**12:00-1:00** ➤ Lunch break 🍽️
**1:00-2:00** ➤ Review pull requests 💻 [High Priority]
**2:00-3:00** ➤ Meeting with Sarah 🤝 [Rescheduled]
**3:00-4:00** ➤ Update documentation 📚 [Medium]
**4:00-4:30** ➤ Admin: Pay bill + call dentist 📞 [Quick wins]
**4:30-5:00** ➤ Tuesday presentation prep 🎯 [Important]

### 🌆 Evening Block (5:00 PM - 8:00 PM)
**6:00-7:00** ➤ Gym 💪 [Personal commitment]
**7:00-8:00** ➤ Grocery shopping 🛒 [Necessary]

✅ Auto-approved: Created tasks-monday-optimized.md
✅ Auto-approved: Created calendar-sync.ics for calendar import""")

# Finance Assistant Demo
print_section("4. FINANCE ASSISTANT ANALYZING EXPENSES")
simulate_command("conseil --role finance --no-sandbox")

print("""
🤖 Starting Conseil as: Financial Assistant
   Sandbox: Disabled ⚠️
   Approval: manual
   Model: gpt-4
------------------------------------------------------------
""")

simulate_user_input("Analyze January expenses in demo/finance/expenses-jan.csv and identify cost-saving opportunities")

simulate_response("""Analyzing January 2024 financial data...

## 💰 Executive Summary
**Total Spend**: $6,088.16 | **Daily Average**: $203 | **14 transactions**

## 📊 Spending Breakdown
```
Office      ████████████████████ 60.6% ($3,687)
Marketing   ████                 12.3% ($750)
Travel      ███                   8.1% ($495)
Software    ██                    4.0% ($243)
Other       ████                 14.0% ($628)
```

## 🎯 Cost-Saving Opportunities

### 1. Immediate Savings (Save $89/month)
• **Software Consolidation**:
  - Merge Adobe + design tools → Canva Pro ($12.99)
  - Annual vs monthly: Save 20% on all subscriptions

### 2. Strategic Optimizations (Save $500+/month)
• **Office Space**: Rent is 57% of budget
  - Option A: Negotiate 10% reduction
  - Option B: Hybrid model (3 days/week coworking)

• **Marketing Efficiency**:
  - Current CAC from ads: ~$125
  - Shift 30% budget to content marketing

### 3. Quick Wins
✓ Set up virtual cards with spending limits
✓ Automate expense categorization
✓ Implement approval workflow for >$100

💡 Projected February savings: $589 (9.7% reduction)""")

print("\n⚠️  Manual Approval Required: Create financial_analysis_jan2024.md")
print("[A]pprove / [D]eny? [Simulated: Approved]")

# Custom Role Demo
print_section("5. CUSTOM ROLE - HR ASSISTANT")
simulate_command("""conseil --role custom \\
  --description "HR assistant for employee onboarding and documentation" \\
  --guidelines "Ensure compliance, maintain confidentiality, use inclusive language" \\
  --no-sandbox""")

print("""
🤖 Starting Conseil as: Custom Assistant
   Sandbox: Disabled ⚠️
   Approval: manual
   Model: gpt-4
------------------------------------------------------------
""")

simulate_user_input("Create an onboarding checklist for a new software engineer starting next Monday")

simulate_response("""Creating comprehensive onboarding checklist...

## 🎉 New Employee Onboarding Checklist
**Employee**: [New Software Engineer]
**Start Date**: Monday, [Date]
**Buddy**: [Assign Technical Mentor]

### 📋 Pre-Day 1 (HR Team)
- [ ] Send welcome email with first-day logistics
- [ ] Prepare workspace and equipment
- [ ] Create accounts: Email, Slack, GitHub, Jira
- [ ] Add to relevant team calendars
- [ ] Share employee handbook and policies
- [ ] Schedule 1:1s with manager and team

### 🌅 Day 1: Welcome & Setup
**Morning (9:00 AM - 12:00 PM)**
- [ ] Office tour and introductions
- [ ] IT setup: Laptop, monitors, accessories
- [ ] Security: Badge, 2FA, password manager
- [ ] HR paperwork and benefits enrollment
- [ ] Team welcome lunch

**Afternoon (1:00 PM - 5:00 PM)**
- [ ] Development environment setup
- [ ] Repository access and Git configuration
- [ ] Review coding standards and practices
- [ ] Assign first "good first issue"

### 📚 Week 1: Foundation
- [ ] Product overview and architecture
- [ ] Meet with cross-functional partners
- [ ] Complete security training
- [ ] Shadow team ceremonies
- [ ] Submit first PR (documentation/typo fix)

✅ Checklist includes compliance requirements and promotes inclusive onboarding""")

# Summary
print_section("DEMONSTRATION COMPLETE")
print("""
The Flexible Conseil Agent System enables:

✅ Multiple professional roles beyond coding
✅ Configurable sandboxing for trusted operations
✅ Role-specific prompts and guidelines
✅ Seamless integration with Lightning workflows
✅ Custom roles for specialized needs

Each role is optimized for its domain while maintaining Conseil's powerful
file editing and automation capabilities.

Try it yourself:
  conseil --role legal --no-sandbox
  conseil --role personal --approval auto
  conseil --role finance
  conseil --role custom --description "Your role here"
""")

print("\n" + "=" * 70)
print("Thank you for watching the Flexible Conseil Agent demonstration!")
print("=" * 70 + "\n")
