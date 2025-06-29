"""
Example: Lightning Agent Configuration Platform

Demonstrates how to use the new unified agent configuration system
to create, customize, and manage AI agents.
"""

import asyncio
import json
from pathlib import Path

from lightning_core.agents import (
    AgentConfigManager,
    AgentType,
    ConseilAgentConfig,
    ChatAgentConfig,
    VoiceAgentConfig,
    PlannerAgentConfig,
    PromptConfig,
    PromptParameter,
    ToolConfig,
    ModelConfig,
    ConseilBehaviorConfig,
)
from lightning_core.agents.configurable_chat_driver import create_configurable_chat_agent


async def main():
    """Demonstrate the agent configuration platform"""
    
    print("🚀 Lightning Agent Configuration Platform Demo")
    print("=" * 50)
    
    # Initialize the configuration manager
    config_manager = AgentConfigManager()
    
    # 1. List default configurations
    print("\n📋 Default Agent Configurations:")
    default_configs = await config_manager.list_agent_configs(include_defaults=True)
    
    for config in default_configs:
        if config.is_default:
            print(f"  • {config.name} ({config.type.value})")
            print(f"    {config.description}")
    
    # 2. Create a custom Conseil agent for data analysis
    print("\n🔧 Creating Custom Data Analysis Agent...")
    
    data_analyst_config = ConseilAgentConfig(
        id="data-analyst-conseil",
        name="Data Analysis Specialist",
        description="A Conseil agent specialized in data analysis and visualization tasks",
        system_prompt=PromptConfig(
            name="Data Analyst Prompt",
            description="System prompt for data analysis specialist",
            template="""You are a skilled {role} specializing in data analysis and visualization. 
            
Your expertise includes:
- Data cleaning and preprocessing
- Statistical analysis and hypothesis testing  
- Creating visualizations with matplotlib, seaborn, plotly
- Working with pandas, numpy, and scikit-learn
- Generating insights and recommendations from data

Guidelines:
- Always start by understanding the data structure and quality
- Use appropriate statistical methods for the data type
- Create clear, informative visualizations
- Explain your methodology and assumptions
- Provide actionable insights and recommendations
- Write well-documented, reproducible code

Analysis approach: {analysis_approach}
Visualization style: {viz_style}""",
            parameters={
                "role": PromptParameter(
                    name="role",
                    type="string",
                    default_value="data scientist",
                    description="Professional role title"
                ),
                "analysis_approach": PromptParameter(
                    name="analysis_approach",
                    type="select",
                    default_value="exploratory",
                    description="Primary analysis approach",
                    options=["exploratory", "confirmatory", "predictive", "descriptive"]
                ),
                "viz_style": PromptParameter(
                    name="viz_style",
                    type="select", 
                    default_value="publication",
                    description="Visualization style preference",
                    options=["publication", "presentation", "interactive", "minimal"]
                )
            }
        ),
        tools=[
            ToolConfig("shell", enabled=True, approval_required=True, sandbox=True),
            ToolConfig("web_search", enabled=True),
            ToolConfig("apply_patch", enabled=True, approval_required=True),
        ],
        model_config=ModelConfig(
            model_id="gpt-4o",
            temperature=0.1,  # Lower for more consistent analysis
            max_tokens=4000
        ),
        behavior_config=ConseilBehaviorConfig(
            job_role="DATA_ANALYST",
            approval_policy="manual",
            enable_thinking=True,
            enable_sandbox=True
        ),
        tags=["data-analysis", "statistics", "visualization", "custom"]
    )
    
    # Save the custom agent
    analyst_id = await config_manager.create_agent_config(data_analyst_config, user_id="demo_user")
    print(f"✅ Created custom agent: {analyst_id}")
    
    # 3. Create a custom chat agent for project management
    print("\n📝 Creating Custom Project Management Chat Agent...")
    
    pm_chat_config = ChatAgentConfig(
        id="pm-chat-agent",
        name="Project Management Assistant",
        description="AI assistant specialized in project management and team coordination",
        system_prompt=PromptConfig(
            name="Project Manager Prompt",
            template="""You are {name}, a professional project management assistant. You help with:

🎯 Project Planning & Strategy:
- Breaking down complex projects into manageable tasks
- Creating realistic timelines and milestone tracking
- Risk assessment and mitigation planning
- Resource allocation and capacity planning

👥 Team Coordination:
- Facilitating clear communication between team members
- Tracking task assignments and progress
- Identifying bottlenecks and dependencies
- Organizing meetings and documentation

📊 Progress Tracking:
- Creating status reports and dashboards
- Monitoring key performance indicators
- Budget tracking and expense management
- Quality assurance and deliverable review

Management style: {management_style}
Communication approach: {communication_style}

You maintain organized records in the context hub and proactively suggest improvements to project workflows.""",
            parameters={
                "name": PromptParameter(
                    name="name",
                    type="string",
                    default_value="PM Assistant",
                    description="Name for the assistant"
                ),
                "management_style": PromptParameter(
                    name="management_style",
                    type="select",
                    default_value="agile",
                    description="Project management methodology",
                    options=["agile", "waterfall", "hybrid", "lean"]
                ),
                "communication_style": PromptParameter(
                    name="communication_style",
                    type="select",
                    default_value="collaborative",
                    description="Communication approach",
                    options=["collaborative", "directive", "supportive", "coaching"]
                )
            }
        ),
        tags=["project-management", "team-coordination", "custom"]
    )
    
    pm_id = await config_manager.create_agent_config(pm_chat_config, user_id="demo_user")
    print(f"✅ Created custom chat agent: {pm_id}")
    
    # 4. Clone and customize a voice agent
    print("\n🎙️ Cloning and Customizing Voice Agent...")
    
    custom_voice_id = await config_manager.clone_agent_config(
        source_id="voice-default",
        new_id="customer-service-voice",
        new_name="Customer Service Voice Agent",
        user_id="demo_user"
    )
    
    # Customize the cloned voice agent
    voice_updates = {
        "description": "Voice agent specialized in customer service interactions",
        "system_prompt": {
            "template": """You are a friendly and professional customer service representative. 

Guidelines for customer interactions:
- Greet customers warmly and ask how you can help
- Listen actively and ask clarifying questions
- Provide clear, helpful solutions
- Show empathy for customer concerns
- Offer additional assistance before ending the call
- Always maintain a {tone} and {pace} demeanor

Remember:
- Every customer interaction is important
- Be patient with confused or frustrated customers  
- Escalate complex issues to human representatives when appropriate
- Follow company policies while being helpful and flexible

Your goal is to resolve customer issues quickly and leave them feeling satisfied with the service.""",
            "parameters": {
                "tone": {
                    "name": "tone",
                    "type": "select",
                    "default_value": "friendly",
                    "description": "Interaction tone",
                    "options": ["friendly", "professional", "empathetic", "upbeat"]
                },
                "pace": {
                    "name": "pace", 
                    "type": "select",
                    "default_value": "patient",
                    "description": "Conversation pace",
                    "options": ["patient", "efficient", "relaxed", "energetic"]
                }
            }
        },
        "behavior_config": {
            "voice_id": "coral",  # Warmer voice for customer service
            "compliance_mode": "customer_service"
        },
        "tags": ["customer-service", "voice", "support", "custom"]
    }
    
    await config_manager.update_agent_config(custom_voice_id, voice_updates, user_id="demo_user")
    print(f"✅ Customized voice agent: {custom_voice_id}")
    
    # 5. List all configurations for demo user
    print("\n📊 All Configurations for Demo User:")
    user_configs = await config_manager.list_agent_configs(user_id="demo_user", include_defaults=False)
    
    for config in user_configs:
        print(f"  • {config.name} ({config.type.value})")
        print(f"    ID: {config.id}")
        print(f"    Tags: {', '.join(config.tags)}")
        print()
    
    # 6. Demonstrate using a configurable chat agent
    print("\n💬 Testing Configurable Chat Agent...")
    
    try:
        # Create a chat agent using our custom PM configuration
        chat_agent = create_configurable_chat_agent(agent_config_id="pm-chat-agent")
        await chat_agent.initialize()
        
        print(f"✅ Initialized chat agent: {chat_agent.agent_config.name}")
        print(f"   Capabilities: {chat_agent.get_capabilities()}")
        print(f"   Model: {chat_agent.agent_config.model_config.model_id}")
        
        # Show the rendered system prompt
        system_prompt = chat_agent._build_system_prompt("demo_user")
        print(f"\n📝 System Prompt Preview:")
        print(system_prompt[:300] + "..." if len(system_prompt) > 300 else system_prompt)
        
    except Exception as e:
        print(f"⚠️  Note: Chat agent test requires context hub: {e}")
    
    # 7. Export a configuration for sharing
    print("\n📤 Exporting Configuration...")
    
    export_path = Path("data_analyst_config.json")
    config = await config_manager.get_agent_config("data-analyst-conseil", "demo_user")
    
    with open(export_path, 'w') as f:
        json.dump(config.to_dict(), f, indent=2)
    
    print(f"✅ Exported configuration to: {export_path}")
    
    print("\n🎉 Demo Complete!")
    print("\nKey Features Demonstrated:")
    print("  • Creating custom agent configurations")
    print("  • Parameterized system prompts")
    print("  • Role-specific tool configurations")
    print("  • Cloning and customization")
    print("  • Configuration export/import")
    print("  • Integration with existing drivers")
    
    print(f"\n📚 Try these CLI commands:")
    print(f"  lightning agents list --user demo_user")
    print(f"  lightning agents show {analyst_id} --user demo_user")
    print(f"  lightning agents export {pm_id} pm_config.json --user demo_user")


if __name__ == "__main__":
    asyncio.run(main())