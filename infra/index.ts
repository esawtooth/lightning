import * as pulumi from "@pulumi/pulumi";
import * as azure from "@pulumi/azure-native";

const config = new pulumi.Config();
const location = config.get("location") || "centralindia";

const resourceGroup = new azure.resources.ResourceGroup("lightning", {
    resourceGroupName: "lightning",
    location,
});

const namespace = new azure.eventhub.Namespace("lightning-namespace", {
    resourceGroupName: resourceGroup.name,
    namespaceName: "lightning-namespace",
    location: resourceGroup.location,
    sku: {
        name: "Standard",
        tier: "Standard",
    },
    kafkaEnabled: true,
});

const eventHub = new azure.eventhub.EventHub("lightning-hub", {
    resourceGroupName: resourceGroup.name,
    namespaceName: namespace.name,
    eventHubName: "lightning-hub",
    partitionCount: 2,
    messageRetentionInDays: 1,
});

export const resourceGroupName = resourceGroup.name;
export const eventHubNamespaceName = namespace.name;
export const eventHubName = eventHub.name;

// Storage account for Function App
const storage = new azure.storage.StorageAccount("funcsa", {
    resourceGroupName: resourceGroup.name,
    sku: {
        name: azure.storage.SkuName.Standard_LRS,
    },
    kind: azure.storage.Kind.StorageV2,
});

const storageKeys = pulumi.all([resourceGroup.name, storage.name]).apply(([resourceGroupName, accountName]) =>
    azure.storage.listStorageAccountKeys({ resourceGroupName, accountName })
);
const primaryStorageKey = storageKeys.apply(keys => keys.keys[0].value);
const storageConnectionString = pulumi.interpolate`DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${primaryStorageKey}`;

// App Service plan for Function App
const appServicePlan = new azure.web.AppServicePlan("function-plan", {
    resourceGroupName: resourceGroup.name,
    kind: "FunctionApp",
    sku: {
        tier: "Dynamic",
        name: "Y1",
    },
});

// Authorization rule to send events
const sendRule = new azure.eventhub.EventHubAuthorizationRule("send-rule", {
    resourceGroupName: resourceGroup.name,
    namespaceName: namespace.name,
    eventHubName: eventHub.name,
    authorizationRuleName: "send",
    rights: ["Send"],
});

const sendKeys = azure.eventhub.listEventHubKeysOutput({
    authorizationRuleName: sendRule.name,
    eventHubName: eventHub.name,
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
            { name: "EVENTHUB_CONNECTION", value: sendKeys.primaryConnectionString },
        ],
    },
});

export const functionEndpoint = pulumi.interpolate`https://${funcApp.defaultHostName}/api/events`;
