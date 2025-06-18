#!/usr/bin/env python3
"""
Demo script showing how to use the flexible Conseil agent system
with different job roles in Lightning.
"""

import asyncio
import os
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
Upon request, all Confidential Information must be returned or destroyed.
""")
    
    print(f"Created sample NDA at: {sample_nda}")
    print("\nTo review with legal assistant:")
    print(f"  conseil --role legal --no-sandbox")
    print(f"  > Review {sample_nda} and identify any missing clauses or potential issues\n")
    
    # Example 2: Personal Task Management
    print("2️⃣ Personal Task Management") 
    print("-" * 50)
    
    # Create tasks directory
    tasks_dir = Path("./demo_tasks")
    tasks_dir.mkdir(exist_ok=True)
    
    # Create a tasks file
    tasks_file = tasks_dir / "today.md"
    tasks_file.write_text("""# Tasks for Today

## High Priority
- [ ] Finish quarterly report
- [ ] Review team proposals
- [ ] Call with client at 2pm

## Medium Priority  
- [ ] Update project documentation
- [ ] Reply to pending emails
- [ ] Schedule next week's meetings

## Low Priority
- [ ] Clean up old files
- [ ] Update LinkedIn profile
""")
    
    print(f"Created task list at: {tasks_file}")
    print("\nTo manage with personal assistant:")
    print(f"  conseil --role personal --no-sandbox --approval auto")
    print(f"  > Organize my tasks in {tasks_file} by deadline and add time estimates\n")
    
    # Example 3: Financial Analysis
    print("3️⃣ Financial Data Analysis")
    print("-" * 50)
    
    # Create finance directory
    finance_dir = Path("./demo_finance") 
    finance_dir.mkdir(exist_ok=True)
    
    # Create sample expense data
    expenses_file = finance_dir / "q4_expenses.csv"
    expenses_file.write_text("""Date,Category,Description,Amount
2024-10-01,Software,GitHub Enterprise,1200
2024-10-03,Marketing,Google Ads,3500
2024-10-05,Salary,Engineering Team,45000
2024-10-08,Software,AWS Services,2800
2024-10-12,Office,Rent and Utilities,5000
2024-10-15,Marketing,Content Creation,2000
2024-10-20,Equipment,Developer Laptops,8000
2024-10-25,Software,Monitoring Tools,500
2024-11-01,Software,GitHub Enterprise,1200
2024-11-03,Marketing,Google Ads,3800
2024-11-05,Salary,Engineering Team,45000
2024-11-10,Software,AWS Services,3200
2024-11-12,Office,Rent and Utilities,5000
2024-11-18,Travel,Team Offsite,12000
2024-11-22,Marketing,Conference Sponsorship,5000
2024-11-28,Equipment,Office Supplies,800
""")
    
    print(f"Created expense data at: {expenses_file}")
    print("\nTo analyze with finance assistant:")
    print(f"  conseil --role finance --no-sandbox")
    print(f"  > Analyze {expenses_file} and create a spending report with insights\n")
    
    # Example 4: Research Assistant
    print("4️⃣ Research Project")
    print("-" * 50)
    
    research_dir = Path("./demo_research")
    research_dir.mkdir(exist_ok=True)
    
    print(f"Created research directory at: {research_dir}")
    print("\nTo conduct research:")
    print(f"  conseil --role research --approval auto")
    print(f"  > Research current AI agent architectures and create a comparison in {research_dir}/ai_agents_comparison.md\n")
    
    # Example 5: Custom Role
    print("5️⃣ Custom Role - Content Creator")
    print("-" * 50)
    
    content_dir = Path("./demo_content")
    content_dir.mkdir(exist_ok=True)
    
    print(f"Created content directory at: {content_dir}")
    print("\nTo use custom content creator role:")
    print(f'  conseil --role custom \\')
    print(f'    --description "You are a technical content creator writing developer-focused articles" \\')
    print(f'    --guidelines "Use clear examples, focus on practical applications, include code snippets" \\')
    print(f'    --no-sandbox')
    print(f"  > Write a blog post about event-driven architectures in {content_dir}/event_driven_guide.md\n")
    
    # Show configuration file example
    print("6️⃣ Lightning Integration Example")
    print("-" * 50)
    print("\nTo use in Lightning workflows, create agent instances:")
    print("""
```python
from lightning_agents import FlexibleConseilAgent, JobRole

# Create specialized agents
legal_agent = FlexibleConseilAgent(
    name="legal_reviewer",
    role=JobRole.LEGAL,
    enable_sandbox=False,
    approval_policy="manual"
)

research_agent = FlexibleConseilAgent(
    name="researcher", 
    role=JobRole.RESEARCH,
    model="gpt-4",
    approval_policy="auto"
)

# Use in workflows
legal_result = await legal_agent.process_request(
    "Review all contracts in ./contracts for liability clauses"
)
```
""")
    
    print("\n✅ Demo setup complete!")
    print("\nTry running the commands above to see the flexible agent in action.")
    print("Remember to set your OPENAI_API_KEY environment variable first.")


def cleanup_demo():
    """Clean up demo directories"""
    import shutil
    
    demo_dirs = [
        "./demo_contracts",
        "./demo_tasks", 
        "./demo_finance",
        "./demo_research",
        "./demo_content"
    ]
    
    for dir_path in demo_dirs:
        if Path(dir_path).exists():
            shutil.rmtree(dir_path)
            print(f"Cleaned up {dir_path}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        cleanup_demo()
    else:
        asyncio.run(demo_flexible_agents())
        print("\n💡 Run 'python flexible_conseil_demo.py cleanup' to remove demo files")