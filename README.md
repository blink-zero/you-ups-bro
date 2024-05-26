
# UPS Monitoring and Shutdown Script

This repository contains scripts for monitoring a UPS (Uninterruptible Power Supply) and performing a graceful shutdown of ESXi hosts and QNAP NAS devices when the UPS is on battery power for an extended period (default 5 minutes but can be changed in the script). The scripts utilize HashiCorp Vault for securely storing and retrieving credentials. 

Currently tested and running using a Raspberry Pi 3B.

## Files

- `store_keys.py`: This script stores credentials in HashiCorp Vault.
- `run_vault.py`: This script monitors the UPS status and performs shutdowns when necessary.

## Prerequisites

- Network UPS Tools installed (https://networkupstools.org/docs/user-manual.chunked/_installation_instructions.html)
- Python 3.x
- HashiCorp Vault (https://developer.hashicorp.com/vault/tutorials/getting-started/getting-started-install)
- Required Python packages (install using `pip install -r requirements.txt`):
  - `hvac`
  - `paramiko`
  - `requests`
  - `pyvmomi`

## Setup

### 1. HashiCorp Vault

Ensure you have Vault installed and running. You can start Vault with the following command:

```bash
vault server -dev
```

Set the Vault address and token in your environment:

```bash
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='<your_vault_token>'
```

### 2. Storing Secrets

Use the `store_keys.py` script to store your credentials in Vault. Update the placeholder values with your actual credentials.

Run the script:

```bash
python3 store_keys.py
```

### 3. UPS Monitoring and Shutdown

The `run_vault.py` script continuously monitors the UPS status and performs the shutdown sequence if necessary.

Run the script:

```bash
python3 run_vault.py
```

## Running the Scripts

1. **Store the Credentials:**

   Run the `store_keys.py` script to store your credentials in Vault.

   ```bash
   python store_keys.py
   ```

2. **Start the UPS Monitoring Script:**

   Run the `run_vault.py` script to start monitoring the UPS and manage shutdowns.

   ```bash
   python run_vault.py
   ```
