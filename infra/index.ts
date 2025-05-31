import * as pulumi from "@pulumi/pulumi";
import * as azure from "@pulumi/azure-native";

const config = new pulumi.Config();
const location = config.get("location") || "centralindia";

const openaiApiKey = process.env.OPENAI_API_KEY;
if (!openaiApiKey) {
  throw new Error("OPENAI_API_KEY must be set when deploying");
}

const resourceGroup = new azure.resources.ResourceGroup("lightning", {
  resourceGroupName: "lightning",
  location,
});

const namespace = new azure.servicebus.Namespace("lightning-namespace", {
  resourceGroupName: resourceGroup.name,
  namespaceName: "lightning-namespace",
  location: resourceGroup.location,
  sku: {
    name: "Standard",
    tier: "Standard",
  },
});

const queue = new azure.servicebus.Queue("lightning-queue", {
  resourceGroupName: resourceGroup.name,
  namespaceName: namespace.name,
  queueName: "lightning-queue",
  enablePartitioning: true,
});

export const resourceGroupName = resourceGroup.name;
export const serviceBusNamespaceName = namespace.name;
export const queueName = queue.name;

// Storage account for Function App
const storage = new azure.storage.StorageAccount("funcsa", {
  resourceGroupName: resourceGroup.name,
  sku: {
    name: azure.storage.SkuName.Standard_LRS,
  },
  kind: azure.storage.Kind.StorageV2,
});

// Table for scheduled events
const scheduleTableName = "schedules";
const scheduleTable = new azure.storage.Table("schedule-table", {
  resourceGroupName: resourceGroup.name,
  accountName: storage.name,
  tableName: scheduleTableName,
});

const storageKeys = pulumi
  .all([resourceGroup.name, storage.name])
  .apply(([resourceGroupName, accountName]) =>
    azure.storage.listStorageAccountKeys({ resourceGroupName, accountName }),
  );
const primaryStorageKey = storageKeys.apply((keys) => keys.keys[0].value);
const storageConnectionString = pulumi.interpolate`DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${primaryStorageKey}`;

// Tables for schedules and repositories
const scheduleTable = new azure.storage.Table("schedule-table", {
  resourceGroupName: resourceGroup.name,
  accountName: storage.name,
  tableName: "schedules",
});

const repoTable = new azure.storage.Table("repo-table", {
  resourceGroupName: resourceGroup.name,
  accountName: storage.name,
  tableName: "repos",
});

// App Service plan for Function App
const appServicePlan = new azure.web.AppServicePlan("function-plan", {
  resourceGroupName: resourceGroup.name,
  kind: "FunctionApp",
  sku: {
    tier: "Dynamic",
    name: "Y1",
  },
});

// Authorization rule to send messages
const sendRule = new azure.servicebus.QueueAuthorizationRule("send-rule", {
  resourceGroupName: resourceGroup.name,
  namespaceName: namespace.name,
  queueName: queue.name,
  authorizationRuleName: "send",
  rights: ["Send"],
});

const sendKeys = azure.servicebus.listQueueKeysOutput({
  authorizationRuleName: sendRule.name,
  queueName: queue.name,
  namespaceName: namespace.name,
  resourceGroupName: resourceGroup.name,
});

// Function App
const funcApp = new azure.web.WebApp("event-function", {
  resourceGroupName: resourceGroup.name,
  serverFarmId: appServicePlan.id,
  kind: "FunctionApp",
  siteConfig: {
    appSettings: [
      { name: "AzureWebJobsStorage", value: storageConnectionString },
      { name: "FUNCTIONS_EXTENSION_VERSION", value: "~4" },
      { name: "FUNCTIONS_WORKER_RUNTIME", value: "python" },
      { name: "STORAGE_CONNECTION", value: storageConnectionString },
      { name: "SCHEDULE_TABLE", value: scheduleTableName },
      {
        name: "SERVICEBUS_CONNECTION",
        value: sendKeys.primaryConnectionString,
      },
      { name: "SERVICEBUS_QUEUE", value: queue.name },
      { name: "OPENAI_API_KEY", value: openaiApiKey },
      { name: "STORAGE_CONNECTION", value: storageConnectionString },
      { name: "SCHEDULE_TABLE", value: scheduleTable.name },
      { name: "REPO_TABLE", value: repoTable.name },
    ],
  },
});

export const functionEndpoint = pulumi.interpolate`https://${funcApp.defaultHostName}/api/events`;
