import os
import json
import logging
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.mgmt.msi import ManagedServiceIdentityClient
from azure.mgmt.msi.models import FederatedIdentityCredential

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Onboarding API triggered.')
    
    try:
        req_body = req.get_json()
        oidc_issuer = req_body.get('oidc_issuer')
        cluster_name = req_body.get('cluster_name')
    except ValueError:
        return func.HttpResponse("Invalid JSON payload", status_code=400)
        
    if not oidc_issuer or not cluster_name:
        return func.HttpResponse("Please provide oidc_issuer and cluster_name", status_code=400)

    # Read from App Settings
    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
    resource_group = os.environ.get("IDENTITY_RESOURCE_GROUP", "rg-podpilot")
    identity_name = os.environ.get("IDENTITY_NAME", "podpilot-identity")
    
    client_id = os.environ.get("PODPILOT_CLIENT_ID", "")
    tenant_id = os.environ.get("PODPILOT_TENANT_ID", "")
    mongo_uri = os.environ.get("PODPILOT_MONGO_URI", "")

    try:
        credential = DefaultAzureCredential()
        client = ManagedServiceIdentityClient(credential, subscription_id)

        # Create the federated credential
        fed_cred_name = f"client-{cluster_name}"
        subject = "system:serviceaccount:podpilot:podpilot"

        properties = FederatedIdentityCredential(
            issuer=oidc_issuer,
            subject=subject,
            audiences=["api://AzureADTokenExchange"]
        )

        client.federated_identity_credentials.create_or_update(
            resource_group_name=resource_group,
            resource_name=identity_name,
            federated_identity_credential_resource_name=fed_cred_name,
            parameters=properties
        )
    except Exception as e:
        logging.error(f"Error creating federated credential: {e}")
        return func.HttpResponse(f"Failed to create federated credential: {str(e)}", status_code=500)

    # Generate the custom values.yaml for the client
    values_yaml = f"""# PodPilot Auto-Generated Values for {cluster_name}
clusterName: "{cluster_name}"

workloadIdentity:
  clientId: "{client_id}"
  tenantId: "{tenant_id}"
  subscriptionId: "REPLACE_ME_WITH_YOUR_AZURE_SUBSCRIPTION_ID"

database:
  uri: "{mongo_uri}"
"""

    return func.HttpResponse(
        values_yaml,
        mimetype="application/x-yaml",
        status_code=200,
        headers={
            "Content-Disposition": f"attachment; filename=podpilot-values-{cluster_name}.yaml"
        }
    )
