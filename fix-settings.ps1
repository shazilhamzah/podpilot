$ErrorActionPreference = "Stop"
$ResourceGroup = "rg-podpilot"
$AppName = "podpilot-api-9444"
$IdentityName = "podpilot-identity"

$SubId = az account show --query id -o tsv
$IdentityClientId = az identity show --name $IdentityName --resource-group $ResourceGroup --query clientId -o tsv
$TenantId = az account show --query tenantId -o tsv
$MongoUri = 'mongodb://<COSMOS_ACCOUNT>:<KEY>@<COSMOS_ACCOUNT>.mongo.cosmos.azure.com:10255/?ssl=true&replicaSet=globaldb&retrywrites=false&maxIdleTimeMS=120000'

# Need to properly pass these as strings to avoid ampersand parsing issues
az functionapp config appsettings set --name $AppName --resource-group $ResourceGroup --settings `
    "AZURE_SUBSCRIPTION_ID=$SubId" `
    "IDENTITY_RESOURCE_GROUP=$ResourceGroup" `
    "IDENTITY_NAME=$IdentityName" `
    "PODPILOT_CLIENT_ID=$IdentityClientId" `
    "PODPILOT_TENANT_ID=$TenantId" `
    "PODPILOT_MONGO_URI=$MongoUri"
