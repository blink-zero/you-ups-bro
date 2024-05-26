import hvac

# Initialize the Vault client
def initialize_vault_client(vault_addr, token):
    client = hvac.Client(url=vault_addr, token=token)
    return client

# Function to store secrets in Vault
def store_secrets(vault_addr, token, path, secrets):
    try:
        client = initialize_vault_client(vault_addr, token)
        # Write the secrets to Vault
        client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=secrets
        )
        return True, "Secrets stored successfully"
    except Exception as e:
        return False, f"Error storing secrets: {str(e)}"

# Example usage
if __name__ == "__main__":
    vault_addr = "http://127.0.0.1:8200"
    token = "<vault_root_token>"  # UPDATE THIS

    # General secrets
    secrets_to_store = {
        "secret/discord": {
            "DISCORD_WEBHOOK_URL": "<discord_webhook>"  # UPDATE THIS
        },
        "secret/esxi": {
            "ESXI_USER": "<esxi_username>", # UPDATE THIS
            "ESXI_PASS": "<esxi_password>" # UPDATE THIS
        }
    }

    # Store general secrets
    for path, secrets in secrets_to_store.items():
        success, message = store_secrets(vault_addr, token, path, secrets)
        print(f"Path: {path} - {message}")

    # QNAP specific secrets
    qnap_secrets = {
        "192.168.1.11": { # UPDATE THIS
            "QNAP_ADMIN_USER": "<qnap_username>", # UPDATE THIS
            "QNAP_ADMIN_PASS": "<qnap_password>" # UPDATE THIS
        },
        "192.168.1.12": { # UPDATE THIS
            "QNAP_ADMIN_USER": "<qnap_username>", # UPDATE THIS
            "QNAP_ADMIN_PASS": "<qnap_password>" # UPDATE THIS
        },
        # Add more QNAP hosts as needed
    }

    # Store QNAP secrets
    for qnap_host, secrets in qnap_secrets.items():
        path = f"secret/qnap/{qnap_host}"
        success, message = store_secrets(vault_addr, token, path, secrets)
        print(f"Path: {path} - {message}")
