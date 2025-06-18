#!/usr/bin/env python3
"""
Simulation of the flexible Conseil agent system
Shows how different roles would process tasks
"""

import time


class ConseilSimulator:
    """Simulates the flexible Conseil agent behavior"""

    def __init__(self, role, no_sandbox=False, approval="manual"):
        self.role = role
        self.no_sandbox = no_sandbox
        self.approval = approval

    def show_startup(self):
        """Show agent startup message"""
        print(f"\n🤖 Starting Conseil as: {self.role.title()} Assistant")
        print(f"   Sandbox: {'Disabled ⚠️' if self.no_sandbox else 'Enabled'}")
        print("   Model: gpt-4")
        print("-" * 60)

    def process_command(self, command):
        """Simulate processing a command"""
        print(f"\n> {command}")
        time.sleep(0.5)  # Simulate thinking

    def show_response(self, response):
        """Show agent response"""
        print(f"\n{response}")


def demo_cli_help():
    """Show CLI help"""
    print("🚀 Flexible Conseil Agent System Demo")
    print("=" * 60)

    print("\n📋 Available Commands:")
    print("  conseil --help                    Show help")
    print("  conseil --list-roles              List available roles")
    print("  conseil --role <role>             Use specific role")
    print("  conseil --no-sandbox              Disable sandboxing")
    print("  conseil --approval <policy>       Set approval policy")

    print("\n📚 Available Roles:")
    print("  coding     - Expert coding assistant")
    print("  legal      - Legal document specialist")
    print("  personal   - Personal task organizer")
    print("  finance    - Financial analyst")
    print("  research   - Research specialist")
    print("  custom     - Define your own role")

    print("\n🔧 Configuration Options:")
    print("  --no-sandbox     Disable file operation safety")
    print("  --approval auto  Auto-approve low-risk actions")
    print("  --approval manual Manual approval for all actions")
    print("  --model <name>   Specify AI model to use")


def demo_role_switching():
    """Demonstrate switching between roles"""
    print("\n\n" + "=" * 70)
    print("  DEMONSTRATING ROLE SWITCHING")
    print("=" * 70)

    # Coding Assistant
    coding = ConseilSimulator("coding")
    coding.show_startup()
    coding.process_command("Add type hints to my Python functions and fix any bugs")
    coding.show_response("""Analyzing Python files in current directory...

Found 3 files requiring type hints:
- main.py (5 functions missing hints)
- utils.py (3 functions missing hints)
- models.py (2 classes missing hints)

🔍 Issues detected:
- Line 23: Undefined variable 'data' in process_user_input()
- Line 45: Missing return statement in validate_config()

✏️ Applying fixes:
✅ Added type hints to all functions
✅ Fixed undefined variable bug
✅ Added missing return statement
✅ Organized imports per PEP 8

📝 Created pull request with changes""")

    # Switch to Legal Assistant
    print("\n" + "-" * 50)
    print("🔄 Switching to Legal Assistant...")

    legal = ConseilSimulator("legal", no_sandbox=True)
    legal.show_startup()
    legal.process_command("Review our terms of service for GDPR compliance issues")
    legal.show_response("""📋 GDPR Compliance Review of Terms of Service

🚨 Critical Issues Found:

1. **Data Processing Legal Basis** (Article 6)
   ❌ No clear legal basis specified for data processing
   ✅ Recommend: Add explicit consent + legitimate interest clauses

2. **User Rights Section** (Articles 15-22)
   ❌ Missing: Right to data portability
   ❌ Missing: Right to object to processing
   ❌ Incomplete: Right to erasure implementation

3. **Data Retention** (Article 5.1.e)
   ❌ No specific retention periods mentioned
   ✅ Recommend: Define 2-year retention for user data

4. **Third-Party Sharing** (Article 44-49)
   ❌ Vague language about "partners and affiliates"
   ✅ Need explicit list of data processors

⚖️ Compliance Score: 4/10 (High Risk)
📄 I can draft GDPR-compliant amendments""")

    # Switch to Personal Assistant
    print("\n" + "-" * 50)
    print("🔄 Switching to Personal Assistant...")

    personal = ConseilSimulator("personal", no_sandbox=True, approval="auto")
    personal.show_startup()
    personal.process_command("Plan my week - I have 3 meetings, 2 deadlines, and want to include exercise")
    personal.show_response("""📅 Weekly Schedule Optimization

## This Week's Priorities:
🎯 **Meetings**: Project kickoff (Mon), Client review (Wed), Team retro (Fri)
⏰ **Deadlines**: Report submission (Tue), Presentation prep (Thu)
💪 **Personal**: 4x exercise sessions + adequate rest

## Optimized Schedule:

**Monday**
- 9:00 AM: Project kickoff meeting
- 11:00 AM: Deep work on report (deadline Tue)
- 2:00 PM: Email processing & admin
- 6:00 PM: Gym session 💪

**Tuesday**
- 9:00 AM: Finish & submit report ⏰
- 11:00 AM: Start presentation prep
- 2:00 PM: Buffer time for report follow-up
- 7:00 PM: Yoga class 🧘

**Wednesday**
- 10:00 AM: Client review meeting
- 12:00 PM: Presentation work (focused)
- 3:00 PM: Client follow-up tasks
- 6:30 PM: Walking/light cardio 🚶

**Thursday**
- 9:00 AM: Presentation finalization ⏰
- 11:00 AM: Practice presentation
- 2:00 PM: Prep for Friday retro
- 6:00 PM: Strength training 💪

**Friday**
- 10:00 AM: Team retrospective
- 12:00 PM: Week wrap-up & planning
- 2:00 PM: Administrative catch-up
- Weekend: Rest & personal time

✅ Auto-created calendar events
✅ Set reminders for deadlines
✅ Blocked focus time for deep work""")


def demo_custom_role():
    """Demonstrate creating a custom role"""
    print("\n\n" + "=" * 70)
    print("  CREATING CUSTOM ROLE - MARKETING SPECIALIST")
    print("=" * 70)

    print("\n$ conseil --role custom \\")
    print("    --description 'Marketing specialist for content creation and campaigns' \\")
    print("    --guidelines 'Focus on brand voice, data-driven decisions, and ROI'")

    marketing = ConseilSimulator("marketing specialist", no_sandbox=True)
    marketing.show_startup()
    marketing.process_command(
        "Create a social media campaign for our new product launch targeting developers"
    )
    marketing.show_response("""🚀 Developer-Focused Product Launch Campaign

## Campaign Overview
**Target**: Software developers & tech leads
**Duration**: 6 weeks (2 weeks pre-launch + 4 weeks post)
**Budget**: $15,000 (recommended allocation)
**Goal**: 10,000 developer signups in first month

## Multi-Channel Strategy

### 1. Technical Content Marketing (40% budget)
📝 **Blog Series**: "Developer Experience Best Practices"
- Week 1: Problem identification deep-dive
- Week 2: Technical solution walkthrough
- Week 3: Implementation case studies
- Week 4: Performance benchmarks vs alternatives

🎥 **Video Content**:
- Live coding demos on Twitch/YouTube
- "Behind the scenes" engineering talks
- Customer success stories from technical users

### 2. Community Engagement (30% budget)
👥 **Developer Communities**:
- Sponsor relevant dev conferences/meetups
- Host technical webinars
- Engage in Stack Overflow, Reddit r/programming
- GitHub repository with examples

🎯 **Influencer Partnerships**:
- Tech YouTubers for authentic reviews
- Developer advocates for early feedback
- Open source maintainers for validation

### 3. Targeted Digital Ads (30% budget)
📊 **Platforms & Targeting**:
- LinkedIn (job title: Software Engineer, DevOps)
- Twitter (interests: programming, dev tools)
- Dev.to sponsored posts
- Google Ads (high-intent keywords)

**Creative Focus**:
- Code snippets showing ease of use
- Performance improvement metrics
- Developer testimonials
- "Before/after" workflow comparisons

## Success Metrics & Tracking
📈 **KPIs**:
- Developer signups: 10,000 target
- Documentation page views: 50,000+
- GitHub stars/forks: 1,000+
- Community mentions: Track sentiment
- Demo requests from enterprise: 100+

🔄 **A/B Tests**:
- Subject lines in dev newsletter campaigns
- Landing page code examples vs. videos
- CTA buttons: "Try Free" vs. "Start Building"

## Content Calendar & Timeline
Week -2: Teaser content, community engagement
Week -1: Technical previews, early access program
Week 0: Launch announcement across all channels
Week 1-2: User-generated content, case studies
Week 3-4: Advanced tutorials, enterprise outreach

📋 Ready to execute! Shall I create the detailed asset list and content briefs?""")


def demo_approval_workflows():
    """Demonstrate different approval policies"""
    print("\n\n" + "=" * 70)
    print("  APPROVAL WORKFLOW DEMONSTRATION")
    print("=" * 70)

    print("\n🔒 Manual Approval (High-risk operations)")
    print("$ conseil --role finance --approval manual")

    finance = ConseilSimulator("finance", approval="manual")
    finance.show_startup()
    finance.process_command("Transfer $50,000 from operations to marketing budget")
    finance.show_response("""💰 Budget Transfer Analysis

**Transfer Request**: $50,000 Operations → Marketing
**Current Operations Balance**: $180,000
**Current Marketing Balance**: $25,000

📊 **Impact Analysis**:
- Operations utilization drops to 72% (from 100%)
- Marketing budget increases by 200%
- Projected Q4 operations buffer: $130,000 (adequate)

✅ **Recommendation**: APPROVE
- Transfer supports growth initiatives
- Operations maintains healthy buffer
- No cash flow disruption expected

⚠️ MANUAL APPROVAL REQUIRED: High-value financial transaction""")

    print("\n[A]pprove / [D]eny / [M]odify? [Simulated: User types 'A']")
    print("✅ Approved: Budget transfer processed")

    print("\n\n🟡 Auto-Approval (Low-risk operations)")
    print("$ conseil --role personal --approval auto")

    personal = ConseilSimulator("personal", approval="auto")
    personal.show_startup()
    personal.process_command("Schedule my recurring team standup for 10 AM every Tuesday")
    personal.show_response("""📅 Recurring Meeting Setup

**Meeting**: Team Standup
**Schedule**: Every Tuesday at 10:00 AM
**Duration**: 30 minutes (recommended)
**Attendees**: Development team (8 people)

✅ Auto-approved: Low-risk calendar operation
✅ Created recurring event
✅ Sent calendar invites to team
✅ Set 5-minute reminder notifications

📝 Note: Meeting conflicts detected for 2 team members on Nov 14th - alternative suggested""")


if __name__ == "__main__":
    """Run the demonstration"""
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║         FLEXIBLE CONSEIL AGENT SYSTEM - INTERACTIVE SIMULATION      ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    demo_cli_help()
    demo_role_switching()
    demo_custom_role()
    demo_approval_workflows()

    print("\n" + "=" * 70)
    print("✨ Simulation complete! The flexible agent system enables:")
    print("  • Role-specific expertise and workflows")
    print("  • Configurable safety and approval policies")
    print("  • Custom roles for specialized business needs")
    print("  • Seamless integration with existing tools")
    print("=" * 70)
