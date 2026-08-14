$ErrorActionPreference = "Stop"
$ResourceGroup = "rg-podpilot"
$Location = "eastus"
$SubId = az account show --query id -o tsv
$IdentityName = "podpilot-identity"

# Generate unique names
$RandomSuffix = Get-Random -Minimum 1000 -Maximum 9999
$StorageName = "podpilotfuncst$RandomSuffix"
$AppName = "podpilot-api-$RandomSuffix"

Write-Host "Creating Storage Account: $StorageName"
az storage account create --name $StorageName --location $Location --resource-group $ResourceGroup --sku Standard_LRS

Write-Host "Creating Function App: $AppName"
az functionapp create --resource-group $ResourceGroup --consumption-plan-location $Location --runtime python --runtime-version 3.11 --functions-version 4 --name $AppName --storage-account $StorageName --os-type linux

Write-Host "Assigning Managed Identity to Function App..."
$PrincipalId = az functionapp identity assign --name $AppName --resource-group $ResourceGroup --query principalId -o tsv

Write-Host "Fetching Target Identity details..."
$IdentityId = az identity show --name $IdentityName --resource-group $ResourceGroup --query id -o tsv
$IdentityClientId = az identity show --name $IdentityName --resource-group $ResourceGroup --query clientId -o tsv
$TenantId = az account show --query tenantId -o tsv

Write-Host "Granting Function App permissions over Target Identity..."
# Wait a few seconds for AAD propagation
Start-Sleep -Seconds 15
az role assignment create --assignee $PrincipalId --role "Managed Identity Operator" --scope $IdentityId

Write-Host "Configuring App Settings..."
az functionapp config appsettings set --name $AppName --resource-group $ResourceGroup --settings `
    "AZURE_SUBSCRIPTION_ID=$SubId" `
    "IDENTITY_RESOURCE_GROUP=$ResourceGroup" `
    "IDENTITY_NAME=$IdentityName" `
    "PODPILOT_CLIENT_ID=$IdentityClientId" `
    "PODPILOT_TENANT_ID=$TenantId" `
    "PODPILOT_MONGO_URI=mongodb://<COSMOS_ACCOUNT>:<KEY>@<COSMOS_ACCOUNT>.mongo.cosmos.azure.com:10255/?ssl=true^&replicaSet=globaldb^&retrywrites=false^&maxIdleTimeMS=120000"

Write-Host "Zipping the code..."
Compress-Archive -Path "api\*" -DestinationPath "api.zip" -Force

Write-Host "Deploying code..."
az functionapp deployment source config-zip -g $ResourceGroup -n $AppName --src api.zip

Write-Host "Deployment Complete! Function URL: https://$AppName.azurewebsites.net/api/onboard"
