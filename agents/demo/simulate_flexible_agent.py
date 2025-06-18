#!/usr/bin/env python3
"""
Simulation of the flexible Conseil agent system
Shows how different roles would process tasks
"""

import os
import time
from datetime import datetime
from pathlib import Path

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
        print(f"   Approval: {self.approval}")
        print(f"   Model: gpt-4")
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
    roles = [
        ("coding", "Expert coding assistant", "*.py, *.js, *.ts"),
        ("legal", "Legal document assistant", "*.md, contracts/*.md"),
        ("personal", "Personal assistant", "*.md, todos/*.md"),
        ("finance", "Financial assistant", "*.csv, *.md, finance/*.md"),
        ("research", "Research assistant", "*.md, research/*.md"),
        ("custom", "Custom role (user-defined)", "all files")
    ]
    
    for role, desc, files in roles:
        print(f"\n  {role}:")
        print(f"    Description: {desc}")
        print(f"    Common files: {files}")


def demo_legal_assistant():
    """Demonstrate legal assistant"""
    print("\n\n🏛️  LEGAL ASSISTANT DEMO")
    print("=" * 60)
    
    agent = ConseilSimulator("legal", no_sandbox=True, approval="manual")
    agent.show_startup()
    
    # Show the contract
    print("\n📄 Current file: demo/legal/contractor-agreement.md")
    with open("demo/legal/contractor-agreement.md") as f:
        print(f.read())
    
    # Process review command
    agent.process_command("Review this contractor agreement and identify any issues or missing clauses that could pose risks to the company")
    
    # Simulate response
    response = """I've reviewed the Independent Contractor Agreement and identified several significant issues:

## 🚨 Critical Issues:

1. **Intellectual Property Rights** (Section 6)
   - Currently states: "All work product created by Contractor shall be owned by Contractor"
   - This is backwards! The Company should own work product created for them
   - Recommendation: Change to "work-for-hire" language

2. **Termination Clause** (Section 4)
   - No notice period specified
   - No provisions for termination for cause
   - Missing obligation to return company property

3. **Missing Clauses**:
   - **Indemnification**: No protection for Company against contractor's actions
   - **Insurance**: No requirement for contractor liability insurance
   - **Non-Solicitation**: No restriction on soliciting company employees/clients
   - **Dispute Resolution**: No arbitration or mediation clause
   - **Warranty**: No warranty of contractor's work quality

4. **Payment Terms** (Section 2)
   - No payment schedule specified (NET 30? Upon receipt?)
   - No expense reimbursement provisions
   - No late payment terms

5. **Confidentiality** (Section 5)
   - Too vague - needs definition of "confidential information"
   - No time limit on confidentiality obligations
   - No exceptions for publicly available information

Would you like me to draft amendments for any of these issues?"""
    
    agent.show_response(response)
    
    if agent.approval == "manual":
        print("\n⚠️  Manual Approval Required")
        print("Command: apply_patch to fix IP ownership clause")
        print("[A]pprove / [D]eny / [M]odify? ", end="")


def demo_personal_assistant():
    """Demonstrate personal assistant"""
    print("\n\n📅 PERSONAL ASSISTANT DEMO")
    print("=" * 60)
    
    agent = ConseilSimulator("personal", no_sandbox=True, approval="auto")
    agent.show_startup()
    
    # Show current tasks
    print("\n📄 Current file: demo/personal/tasks-today.md")
    print("(Showing first 10 lines...)")
    with open("demo/personal/tasks-today.md") as f:
        lines = f.readlines()[:10]
        print("".join(lines))
    
    # Process organization command
    agent.process_command("Organize my tasks by priority and time, add time estimates, and create a schedule for the day")
    
    response = """I've reorganized your tasks into a prioritized schedule:

## 📅 Monday Schedule

### ⏰ Morning (9:00 AM - 12:00 PM)
**9:00 - 9:30**: Email client about timeline ⚡ [30 min]
**10:00 - 10:30**: Team standup 📅 [30 min]  
**10:30 - 12:00**: Finish project proposal 📝 [1.5 hrs]

### 🌞 Afternoon (12:00 PM - 5:00 PM)
**12:00 - 1:00**: Lunch break
**1:00 - 2:00**: Review pull requests 💻 [1 hr]
**2:00 - 3:00**: Meeting with Sarah 📅 [1 hr]
**3:00 - 4:00**: Update documentation 📚 [1 hr]
**4:00 - 4:30**: Pay electric bill 💡 [30 min]
**4:30 - 5:00**: Call dentist for appointment 📞 [30 min]

### 🌆 Evening (5:00 PM - 8:00 PM)
**5:00 - 6:00**: Prepare for Tuesday presentation 🎯 [1 hr]
**6:00 - 7:00**: Gym 💪 [1 hr]
**7:00 - 8:00**: Grocery shopping 🛒 [1 hr]

## ✅ Completed Schedule Summary:
- Work tasks: 5.5 hours
- Personal tasks: 2.5 hours  
- Meetings: 1.5 hours
- Breaks/Transition: 1.5 hours

💡 Tips:
- Block time for email/Slack: Check at 9am, 1pm, 4:30pm
- Presentation prep before gym maintains energy
- Grocery list ready to save time shopping

Auto-approved: Saving organized schedule to tasks-monday-scheduled.md ✓"""
    
    agent.show_response(response)
    print("\n✅ Auto-approved: File saved")


def demo_finance_assistant():
    """Demonstrate finance assistant"""
    print("\n\n💰 FINANCE ASSISTANT DEMO")
    print("=" * 60)
    
    agent = ConseilSimulator("finance", no_sandbox=True, approval="manual")
    agent.show_startup()
    
    # Process analysis command
    agent.process_command("Analyze expenses-jan.csv and create a spending report with insights and recommendations")
    
    response = """## January 2024 Expense Analysis

### 📊 Summary Statistics
- **Total Expenses**: $6,088.16
- **Daily Average**: $203
- **Number of Transactions**: 14

### 📈 Spending by Category

| Category | Amount | % of Total | Transactions |
|----------|--------|------------|--------------|
| Office | $3,687.30 | 60.6% | 3 |
| Software | $243.16 | 4.0% | 4 |
| Marketing | $750.00 | 12.3% | 2 |
| Travel | $495.20 | 8.1% | 2 |
| Equipment | $189.99 | 3.1% | 1 |
| Professional | $350.00 | 5.7% | 1 |
| Meals | $87.50 | 1.4% | 1 |

### 💡 Key Insights

1. **Office Costs Dominate** (60.6%)
   - Rent is the single largest expense at $3,500
   - Consider: Negotiate rent or explore co-working spaces

2. **Software Subscriptions** ($243.16/month)
   - Multiple small subscriptions add up
   - Action: Audit for unused services, consider annual plans

3. **Marketing Spend** ($750)
   - Split between Facebook ($250) and Google Ads ($500)
   - ROI tracking needed to evaluate effectiveness

### 🎯 Recommendations

1. **Immediate Actions**:
   - Review software subscriptions for consolidation
   - Set up automated expense tracking
   - Implement receipt scanning system

2. **Cost Optimization**:
   - Software: Switch to annual billing (typically 15-20% savings)
   - Travel: Set up corporate accounts for regular services
   - Marketing: Implement conversion tracking

3. **Budget Targets for February**:
   - Total: $5,500 (10% reduction)
   - Focus areas: Software consolidation, marketing efficiency

Would you like me to create a detailed budget template for February?"""
    
    agent.show_response(response)
    print("\n⚠️  Manual Approval Required")
    print("Command: Create expense_analysis_jan2024.md")
    print("[A]pprove / [D]eny / [M]odify? ", end="")


def demo_custom_role():
    """Demonstrate custom role"""
    print("\n\n🎨 CUSTOM ROLE DEMO")
    print("=" * 60)
    
    print("\n$ conseil --role custom \\")
    print('  --description "You are a technical blog writer creating developer content" \\')
    print('  --guidelines "Use code examples, be practical, explain complex concepts simply" \\')
    print("  --no-sandbox")
    
    agent = ConseilSimulator("Technical Blog Writer", no_sandbox=True)
    agent.show_startup()
    
    agent.process_command("Write an introduction for a blog post about event-driven architectures")
    
    response = """# Event-Driven Architecture: Building Scalable Systems That React

Picture this: You're at a busy coffee shop. When your order is ready, the barista doesn't 
walk around looking for you—they simply call out your name, and you respond. This is 
event-driven architecture in action.

## What We'll Cover

```python
# Traditional approach
def process_order(order):
    payment = process_payment(order)
    inventory = update_inventory(order)
    notification = send_email(order)
    return "Order complete"

# Event-driven approach  
def process_order(order):
    publish_event("OrderPlaced", order)
    # That's it! Other services listen and react
```

In this post, we'll explore:
- Why event-driven architectures matter for modern applications
- Core concepts: Events, Publishers, and Subscribers
- Real-world patterns and anti-patterns
- Building your first event-driven service

Ready to build systems that scale naturally? Let's dive in! ☕"""
    
    agent.show_response(response)


def main():
    """Run all demos"""
    try:
        # Show CLI help
        demo_cli_help()
        input("\n\nPress Enter to see Legal Assistant demo...")
        
        # Legal assistant demo
        demo_legal_assistant()
        input("\n\nPress Enter to see Personal Assistant demo...")
        
        # Personal assistant demo
        demo_personal_assistant()
        input("\n\nPress Enter to see Finance Assistant demo...")
        
        # Finance assistant demo
        demo_finance_assistant()
        input("\n\nPress Enter to see Custom Role demo...")
        
        # Custom role demo
        demo_custom_role()
        
        print("\n\n✅ Demo Complete!")
        print("\nThe flexible Conseil agent can adapt to various professional roles")
        print("while maintaining its powerful file editing and automation capabilities.")
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\nError during demo: {e}")


if __name__ == "__main__":
    # Change to agents directory
    os.chdir(Path(__file__).parent.parent)
    main()