#!/usr/bin/env node
import { Option, program } from "commander";
import { existsSync } from "fs";
import path from "path";
import { CLI_VERSION } from "./version.js";
import { JOB_ROLES } from "./utils/agent/job-roles.js";

// Parse command line arguments for flexible agent
program
  .name("conseil")
  .description("Flexible AI assistant for various professional tasks")
  .version(CLI_VERSION)
  .option("-r, --role <role>", "Job role (coding, legal, personal, finance, research, custom)", "coding")
  .option("-d, --description <desc>", "Custom job description (for custom role)")
  .option("-g, --guidelines <guide>", "Custom guidelines (for custom role)")
  .option("--no-sandbox", "Disable sandboxing for file operations")
  .option("-m, --model <model>", "AI model to use", "gpt-4")
  .option("-p, --provider <provider>", "AI provider (openai, azure)", "openai")
  .option("-a, --approval <policy>", "Approval policy (auto, manual, guided)", "manual")
  .option("--api-key <key>", "API key for the AI provider")
  .option("--session <id>", "Resume a previous session")
  .option("--verbose", "Enable verbose logging")
  .addOption(
    new Option("--list-roles", "List all available job roles and exit").hideHelp()
  );

// Handle role listing
program.hook("preAction", (thisCommand) => {
  const options = thisCommand.opts();
  
  if (options.listRoles) {
    console.log("\nAvailable Job Roles:\n");
    for (const [key, role] of Object.entries(JOB_ROLES)) {
      if (key !== "CUSTOM") {
        console.log(`${key.toLowerCase()}:`);
        console.log(`  Title: ${role.title}`);
        console.log(`  Description: ${role.description.split('\n')[0]}...`);
        console.log(`  Common files: ${role.filePatterns?.join(", ") || "all files"}`);
        console.log("");
      }
    }
    console.log("custom:");
    console.log("  Title: Custom Assistant");
    console.log("  Description: Define your own role with --description and --guidelines");
    console.log("");
    process.exit(0);
  }
});

program.parse();

const options = program.opts();

// Validate role
const normalizedRole = options.role.toUpperCase();
if (!JOB_ROLES[normalizedRole] && normalizedRole !== "CUSTOM") {
  console.error(`Error: Unknown role '${options.role}'`);
  console.error("Available roles: coding, legal, personal, finance, research, custom");
  console.error("Use --list-roles for detailed information");
  process.exit(1);
}

// For custom role, require description
if (normalizedRole === "CUSTOM" && !options.description) {
  console.error("Error: Custom role requires --description");
  process.exit(1);
}

// Import and run the main app with flexible configuration
async function runFlexibleAgent() {
  const { render } = await import("ink");
  const React = await import("react");
  const { default: App } = await import("./app.js");
  
  // Prepare configuration
  const config = {
    role: normalizedRole,
    customDescription: options.description,
    customGuidelines: options.guidelines,
    enableSandbox: !options.noSandbox,
    model: options.model,
    provider: options.provider,
    approvalPolicy: options.approval,
    apiKey: options.apiKey || process.env.OPENAI_API_KEY,
    sessionId: options.session,
    verbose: options.verbose,
  };

  // Show role information
  const roleConfig = JOB_ROLES[normalizedRole] || JOB_ROLES.CUSTOM;
  const title = normalizedRole === "CUSTOM" && options.description 
    ? "Custom Assistant" 
    : roleConfig.title;
    
  console.log(`\n🤖 Starting Conseil as: ${title}`);
  if (!options.noSandbox) {
    console.log("   Sandbox: Enabled (use --no-sandbox to disable)");
  } else {
    console.log("   Sandbox: Disabled ⚠️");
  }
  console.log(`   Model: ${options.model}`);
  console.log(`   Approval: ${options.approval}`);
  console.log("");

  // Render the app with flexible configuration
  const app = render(
    React.createElement(App, {
      flexibleConfig: config,
      cliArgs: process.argv.slice(2),
    })
  );

  await app.waitUntilExit();
}

// Run the agent
runFlexibleAgent().catch((error) => {
  console.error("Error starting Conseil:", error);
  process.exit(1);
});

// Export configuration for use in other modules
export const flexibleCliConfig = {
  role: normalizedRole,
  customDescription: options.description,
  customGuidelines: options.guidelines,
  enableSandbox: !options.noSandbox,
  model: options.model,
  provider: options.provider,
  approvalPolicy: options.approval,
};