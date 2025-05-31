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
