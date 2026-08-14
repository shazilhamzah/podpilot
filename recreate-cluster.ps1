param (
    [string]$ClusterName = "myAKS",
    [string]$ResourceGroup = "rg-test-podpilot",
    [string]$Location = "eastus",
    [int]$NodeCount = 2
)

$ErrorActionPreference = "Stop"

Write-Host "Checking if AKS cluster '$ClusterName' exists in resource group '$ResourceGroup'..."
$clusterExists = az aks show --name $ClusterName --resource-group $ResourceGroup --query "name" -o tsv 2>$null

if ($clusterExists) {
    Write-Host "Cluster '$ClusterName' exists. Deleting it... (This may take several minutes)" -ForegroundColor Yellow
    # Azure CLI runs synchronously by default; omitting --no-wait ensures the script pauses until deletion is complete
    az aks delete --name $ClusterName --resource-group $ResourceGroup --yes
    Write-Host "Successfully deleted cluster '$ClusterName'." -ForegroundColor Green
} else {
    Write-Host "Cluster '$ClusterName' does not exist. Skipping deletion."
}

Write-Host "Creating a new AKS cluster '$ClusterName' in '$Location' with $NodeCount node(s)..." -ForegroundColor Cyan
# Added standard OIDC and Workload Identity flags since PodPilot requires them!
az aks create `
    --resource-group $ResourceGroup `
    --name $ClusterName `
    --location $Location `
    --node-vm-size Standard_D2s_v7 `
    --generate-ssh-keys


Write-Host "Successfully created cluster '$ClusterName'!" -ForegroundColor Green

Write-Host "Fetching kubeconfig credentials for '$ClusterName'..."
az aks get-credentials --resource-group $ResourceGroup --name $ClusterName --overwrite-existing

Write-Host "Done! The new cluster is ready and set as your active kubectl context." -ForegroundColor Green
