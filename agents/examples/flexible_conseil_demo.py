#!/usr/bin/env python3
"""
Demo script showing how to use the flexible Conseil agent system
with different job roles in Lightning.
"""

import asyncio
from pathlib import Path

# This would normally import from the installed package
# from lightning_agents import FlexibleConseilAgent, JobRole
# For demo purposes, we'll show the usage pattern


async def demo_flexible_agents():
    """Demonstrate using Conseil in different professional roles"""

    print("🚀 Flexible Conseil Agent Demo\n")

    # Example 1: Legal Document Assistant
    print("1️⃣ Legal Document Review")
    print("-" * 50)

    # Create contracts directory if it doesn't exist
    contracts_dir = Path("./demo_contracts")
    contracts_dir.mkdir(exist_ok=True)

    # Create a sample NDA
    sample_nda = contracts_dir / "sample_nda.md"
    sample_nda.write_text("""# Non-Disclosure Agreement

This Non-Disclosure Agreement ("Agreement") is entered into as of [DATE] between:

**Disclosing Party**: Acme Corporation
**Receiving Party**: [RECIPIENT NAME]

## 1. Confidential Information
The Receiving Party acknowledges that it may receive certain confidential and proprietary
information ("Confidential Information") from the Disclosing Party.

## 2. Non-Disclosure Obligations
The Receiving Party agrees to:
- Keep all Confidential Information strictly confidential
- Not disclose to any third parties without written consent
- Use Confidential Information only for evaluation purposes

## 3. Term
This Agreement shall remain in effect for a period of 5 years from the date of execution.

## 4. Return of Information
Upon termination, all Confidential Information must be returned or destroyed.

## 5. Governing Law
This Agreement shall be governed by the laws of [STATE/COUNTRY].
""")

    print(f"📄 Created sample NDA: {sample_nda}")
    print("Command: conseil --role legal --no-sandbox")
    print("Prompt: 'Review sample_nda.md and identify potential legal issues'")

    print("\n🤖 Legal Assistant Response:")
    print("""
📋 NDA Legal Review Summary

⚠️ Issues Identified:
1. **Missing Definitions**: "Confidential Information" needs specific exclusions
2. **Broad Scope**: 5-year term may be excessive for evaluation purposes
3. **No Remedies**: Missing specific remedies for breach
4. **Jurisdiction**: Governing law clause incomplete

✅ Suggestions:
- Add standard exceptions (publicly known, independently developed)
- Reduce term to 2-3 years for evaluation NDAs
- Include injunctive relief and attorney fees clause
- Specify jurisdiction for dispute resolution

📝 I can draft amendments to address these issues.
""")

    # Example 2: Personal Task Assistant
    print("\n2️⃣ Personal Task Management")
    print("-" * 50)

    # Create personal tasks directory
    tasks_dir = Path("./demo_tasks")
    tasks_dir.mkdir(exist_ok=True)

    # Create sample task list
    task_file = tasks_dir / "weekly_tasks.md"
    task_file.write_text("""# This Week's Tasks

## Work Tasks
- [ ] Finish quarterly report (Due: Friday)
- [ ] Review team performance evaluations
- [ ] Prepare presentation for client meeting
- [ ] Update project documentation
- [ ] Schedule 1:1s with team members

## Personal Tasks
- [ ] Book dentist appointment
- [ ] Renew car registration
- [ ] Plan weekend trip
- [ ] Buy birthday gift for mom
- [ ] Call insurance about claim

## Meetings
- Monday 10 AM: Team standup
- Tuesday 2 PM: Client check-in
- Wednesday 3 PM: Project review
- Friday 11 AM: All-hands meeting
""")

    print(f"📋 Created task list: {task_file}")
    print("Command: conseil --role personal --approval auto")
    print("Prompt: 'Organize my tasks by priority and create a daily schedule'")

    print("\n🤖 Personal Assistant Response:")
    print("""
📅 Optimized Weekly Schedule

## Monday - Priority Focus
🔥 **High Priority**:
- 9:00 AM: Start quarterly report (2-3 hours)
- 10:00 AM: Team standup
- 2:00 PM: Schedule team 1:1s (admin task)

## Tuesday - Client & Reviews
- 9:00 AM: Continue quarterly report
- 11:00 AM: Review performance evaluations
- 2:00 PM: Client check-in meeting
- 3:30 PM: Quick personal calls (dentist, insurance)

## Wednesday - Documentation & Prep
- 9:00 AM: Update project documentation
- 11:00 AM: Prepare client presentation
- 3:00 PM: Project review meeting
- 4:30 PM: Personal errands (car registration)

## Thursday - Finishing Touches
- 9:00 AM: Finalize quarterly report
- 11:00 AM: Practice client presentation
- 2:00 PM: Personal time (birthday gift shopping)

## Friday - Delivery & Planning
- 9:00 AM: Submit quarterly report ✅
- 11:00 AM: All-hands meeting
- 1:00 PM: Plan weekend trip
- 3:00 PM: Week wrap-up and next week planning

✅ Auto-scheduled: Dentist appointment for Tuesday 4 PM
✅ Auto-created: Calendar reminders for all deadlines
""")

    # Example 3: Financial Analysis Assistant
    print("\n3️⃣ Financial Analysis")
    print("-" * 50)

    # Create finance directory and sample data
    finance_dir = Path("./demo_finance")
    finance_dir.mkdir(exist_ok=True)

    # Create sample expense data
    expenses_file = finance_dir / "q1_expenses.csv"
    expenses_file.write_text("""Date,Category,Description,Amount,Payment Method
2024-01-05,Office,WeWork membership,1200.00,Credit Card
2024-01-10,Software,Adobe Creative Suite,79.99,Credit Card
2024-01-15,Marketing,Google Ads campaign,850.00,Bank Transfer
2024-01-20,Travel,Client meeting flights,450.00,Credit Card
2024-01-25,Office,Supplies and equipment,320.00,Credit Card
2024-02-01,Software,Slack Pro subscription,96.00,Credit Card
2024-02-08,Marketing,Conference sponsorship,2500.00,Bank Transfer
2024-02-15,Travel,Hotel for conference,380.00,Credit Card
2024-02-20,Office,Internet and utilities,180.00,Bank Transfer
2024-03-01,Software,GitHub Enterprise,45.00,Credit Card
2024-03-10,Marketing,Content creator fees,1200.00,Bank Transfer
2024-03-15,Travel,Team retreat expenses,1800.00,Credit Card
""")

    print(f"💰 Created expense data: {expenses_file}")
    print("Command: conseil --role finance --no-sandbox")
    print("Prompt: 'Analyze Q1 expenses and identify cost optimization opportunities'")

    print("\n🤖 Financial Assistant Response:")
    print("""
📊 Q1 Financial Analysis

## Expense Summary
**Total Q1 Spend**: $9,100.99
**Monthly Average**: $3,033.66
**Top Categories**: Office (37%), Marketing (32%), Travel (17%)

## Spending Breakdown
- Office & Workspace: $3,380.00 (37.1%)
- Marketing & Growth: $2,950.00 (32.4%)
- Travel & Events: $1,550.00 (17.0%)
- Software & Tools: $220.99 (2.4%)

## Cost Optimization Opportunities

### 1. Office Space (Potential 20% savings)
- Current: $1,200/month WeWork
- Alternative: Hybrid model 3 days/week = $720/month
- Annual savings: $5,760

### 2. Software Consolidation (Potential 15% savings)
- Bundle Adobe + other creative tools
- Switch to annual billing for additional 10% discount
- Negotiate team rates for growing usage

### 3. Travel Optimization (Potential 25% savings)
- Book flights 2+ weeks in advance
- Use corporate travel platform for better rates
- Consider virtual meetings for routine check-ins

## Recommendations
✅ Implement monthly budget alerts
✅ Set up automated expense categorization
✅ Negotiate annual contracts for 10-15% savings
✅ Create approval workflow for expenses >$500

💡 Projected annual savings: $12,000-15,000 with these optimizations
""")

    print("\n✨ Demo Complete!")
    print("\nThe Flexible Conseil Agent System enables:")
    print("  • Role-specific expertise and prompts")
    print("  • Configurable safety and approval settings")
    print("  • Seamless file and document processing")
    print("  • Integration with Lightning workflows")


async def demo_custom_role():
    """Demonstrate creating a custom role"""
    print("\n\n4️⃣ Custom Role Example - HR Assistant")
    print("-" * 50)

    print("Command: conseil --role custom \\")
    print('  --description "HR assistant for employee onboarding and documentation" \\')
    print('  --guidelines "Ensure compliance, maintain confidentiality, use inclusive language"')

    print("\nPrompt: 'Create an onboarding checklist for a new software engineer'")

    print("\n🤖 Custom HR Assistant Response:")
    print("""
## 🎉 Software Engineer Onboarding Checklist

### Pre-Day 1 (HR/Manager)
- [ ] Send welcome email with first-day logistics
- [ ] Prepare workspace and equipment
- [ ] Create accounts: Email, Slack, GitHub, Jira
- [ ] Add to team calendars and distribution lists
- [ ] Share employee handbook and code of conduct

### Day 1 - Welcome & Setup
**Morning**
- [ ] Office tour and team introductions
- [ ] IT equipment setup and configuration
- [ ] Security training and badge setup
- [ ] HR paperwork and benefits enrollment

**Afternoon**
- [ ] Development environment setup
- [ ] Code repository access and training
- [ ] Assign technical mentor/buddy
- [ ] Review engineering practices and standards

### Week 1 - Foundation
- [ ] Complete all required training modules
- [ ] Shadow team meetings and ceremonies
- [ ] Review product architecture and documentation
- [ ] Submit first pull request (documentation fix)
- [ ] Schedule regular 1:1s with manager

### Month 1 - Integration
- [ ] Complete first feature implementation
- [ ] Present work to team for feedback
- [ ] Join on-call rotation (with support)
- [ ] 30-day check-in with HR and manager

✅ Checklist promotes inclusive, compliant onboarding experience
✅ Includes technical and cultural integration elements
✅ Provides clear milestones and success metrics
""")


if __name__ == "__main__":
    """Run the demonstration"""
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║                FLEXIBLE CONSEIL AGENT DEMONSTRATION                 ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    asyncio.run(demo_flexible_agents())
    asyncio.run(demo_custom_role())

    print("\n" + "=" * 70)
    print("🎯 Ready to try it yourself? Install the Lightning Conseil package!")
    print("=" * 70)
