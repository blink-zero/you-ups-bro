import time
import subprocess
import requests
import paramiko
import threading
import os
import hvac
import logging
from pyVim.connect import SmartConnect, Disconnect, SmartConnectNoSSL
from pyVmomi import vim
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(filename='/var/log/ups_monitor.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the Vault client
def initialize_vault_client(vault_addr, token):
    client = hvac.Client(url=vault_addr, token=token)
    return client

# Function to read a secret from Vault
def get_vault_secret(client, secret_path, secret_key):
    try:
        logging.info(f"Retrieving secret {secret_key} from path {secret_path}")
        secret = client.secrets.kv.v2.read_secret_version(path=secret_path)
        logging.info(f"Secret {secret_key} retrieved successfully")
        return secret['data']['data'][secret_key]
    except hvac.exceptions.InvalidPath as e:
        logging.error(f"Invalid path: {e.errors}")
        raise Exception(f"Error retrieving secret from Vault: {e}")
    except Exception as e:
        logging.error(f"General error: {e}")
        raise Exception(f"Error retrieving secret from Vault: {e}")

# Function to get QNAP credentials from Vault
def get_qnap_credentials(client, qnap_host):
    try:
        qnap_user = get_vault_secret(client, f'secret/qnap/{qnap_host}', 'QNAP_ADMIN_USER')
        qnap_pass = get_vault_secret(client, f'secret/qnap/{qnap_host}', 'QNAP_ADMIN_PASS')
        return qnap_user, qnap_pass
    except Exception as e:
        logging.error(f"Failed to retrieve QNAP credentials for {qnap_host}: {e}")
        raise

# Configuration from Vault
vault_addr = os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200')
vault_token = os.getenv('VAULT_TOKEN', 'your_vault_token') # UPDATE THIS TO YOUR ROOT VAULT TOKEN
client = initialize_vault_client(vault_addr, vault_token)

try:
    DISCORD_WEBHOOK_URL = get_vault_secret(client, 'secret/discord', 'DISCORD_WEBHOOK_URL')
    ESXI_USER = get_vault_secret(client, 'secret/esxi', 'ESXI_USER')
    ESXI_PASS = get_vault_secret(client, 'secret/esxi', 'ESXI_PASS')
except Exception as e:
    logging.error(f"Failed to retrieve secrets: {e}")
    exit(1)

UPS_STATUS_COMMAND = "upsc <ups_name>@localhost" # UPDATE THIS WITH YOUR UPS NAME
ESXI_HOSTS = ["192.168.1.11", "192.168.1.12"]  # Replace with actual IPs or hostnames
QNAP_HOSTS = ["192.168.1.13", "192.168.1.14"]  # Replace with actual IP's of QNAP NAS devices
SHUTDOWN_DELAY = 300  # 5 minutes
CHECK_INTERVAL = 60   # 1 minute

def send_discord_notification(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except requests.RequestException as e:
        logging.error(f"Failed to send Discord notification: {e}")

def check_ups_status():
    try:
        result = subprocess.check_output(UPS_STATUS_COMMAND, shell=True).decode('utf-8')
        if "ups.status: OB" in result:
            return "on_battery"
        return "online"
    except subprocess.CalledProcessError as e:
        send_discord_notification(f"Error checking UPS status: {e}")
        logging.error(f"Error checking UPS status: {e}")
        return "error"

def are_all_vms_powered_off(content):
    for datacenter in content.rootFolder.childEntity:
        for vm in datacenter.vmFolder.childEntity:
            if isinstance(vm, vim.VirtualMachine):
                if not vm.name.startswith("vCLS") and vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                    return False
    return True

def get_host_ip(host):
    for net in host.config.network.vnic:
        return net.spec.ip.ipAddress

def shutdown_esxi_vms(host):
    try:
        si = SmartConnectNoSSL(host=host, user=ESXI_USER, pwd=ESXI_PASS)
        content = si.RetrieveContent()

        # Shut down VMs
        for datacenter in content.rootFolder.childEntity:
            for vm in datacenter.vmFolder.childEntity:
                if isinstance(vm, vim.VirtualMachine):
                    if not vm.name.startswith("vCLS") and vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                        vm.ShutdownGuest()
                        send_discord_notification(f"Shutdown guest OS on VM {vm.name} on host {host}")
                        logging.info(f"Shutdown guest OS on VM {vm.name} on host {host}")

        # Wait for VMs to power off
        while not are_all_vms_powered_off(content):
            send_discord_notification(f"Waiting for VMs to power off on host {host}")
            logging.info(f"Waiting for VMs to power off on host {host}")
            time.sleep(60)  # Check every minute
        send_discord_notification(f"All VMs are powered off on host {host}")
        logging.info(f"All VMs are powered off on host {host}")

        Disconnect(si)
    except Exception as e:
        send_discord_notification(f"Error shutting down VMs on ESXi host {host}: {e}")
        logging.error(f"Error shutting down VMs on ESXi host {host}: {e}")

def shutdown_esxi_hosts():
    for host in ESXI_HOSTS:
        try:
            si = SmartConnectNoSSL(host=host, user=ESXI_USER, pwd=ESXI_PASS)
            content = si.RetrieveContent()

            # Shutdown ESXi host
            host_shut_down = False
            for datacenter in content.rootFolder.childEntity:
                for hostFolder in datacenter.hostFolder.childEntity:
                    if isinstance(hostFolder, vim.ComputeResource) or isinstance(hostFolder, vim.ClusterComputeResource):
                        for esxi_host in hostFolder.host:
                            host_ip = get_host_ip(esxi_host)
                            send_discord_notification(f"Checking host {host_ip} against {host}")
                            logging.info(f"Checking host {host_ip} against {host}")
                            if host_ip == host:
                                send_discord_notification(f"Initiating shutdown for ESXi host {esxi_host.name}")
                                logging.info(f"Initiating shutdown for ESXi host {esxi_host.name}")
                                try:
                                    task = esxi_host.ShutdownHost_Task(force=True)
                                    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                                        time.sleep(1)
                                    if task.info.state == vim.TaskInfo.State.success:
                                        send_discord_notification(f"ESXi host {esxi_host.name} shutdown successfully")
                                        logging.info(f"ESXi host {esxi_host.name} shutdown successfully")
                                        host_shut_down = True
                                    else:
                                        send_discord_notification(f"Failed to shut down ESXi host {esxi_host.name}: {task.info.error}")
                                        logging.error(f"Failed to shut down ESXi host {esxi_host.name}: {task.info.error}")
                                except Exception as e:
                                    send_discord_notification(f"Error initiating shutdown for ESXi host {esxi_host.name}: {e}")
                                    logging.error(f"Error initiating shutdown for ESXi host {esxi_host.name}: {e}")
            if not host_shut_down:
                send_discord_notification(f"ESXi host {host} was not found in the inventory or could not be shut down")
                logging.error(f"ESXi host {host} was not found in the inventory or could not be shut down")

            Disconnect(si)
        except Exception as e:
            send_discord_notification(f"Error shutting down ESXi host {host}: {e}")
            logging.error(f"Error shutting down ESXi host {host}: {e}")

def shutdown_qnap_nas():
    for host in QNAP_HOSTS:
        try:
            qnap_user, qnap_pass = get_qnap_credentials(client, host)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=qnap_user, password=qnap_pass)
            ssh.exec_command('halt')
            send_discord_notification(f"Shutdown QNAP NAS {host}")
            logging.info(f"Shutdown QNAP NAS {host}")
            ssh.close()
        except paramiko.ssh_exception.NoValidConnectionsError:
            send_discord_notification(f"Error connecting to QNAP NAS {host}: No valid connections")
            logging.error(f"Error connecting to QNAP NAS {host}: No valid connections")
        except paramiko.ssh_exception.AuthenticationException:
            send_discord_notification(f"Error authenticating to QNAP NAS {host}: Authentication failed")
            logging.error(f"Error authenticating to QNAP NAS {host}: Authentication failed")
        except Exception as e:
            send_discord_notification(f"Error shutting down QNAP NAS {host}: {e}")
            logging.error(f"Error shutting down QNAP NAS {host}: {e}")

def main():
    next_daily_notification = datetime.now()
    daily_notification_sent = False

    while True:
        ups_status = check_ups_status()
        if ups_status == "on_battery":
            send_discord_notification("UPS is on battery. Waiting 5 minutes before initiating shutdown sequence.")
            logging.info("UPS is on battery. Waiting 5 minutes before initiating shutdown sequence.")
            time.sleep(SHUTDOWN_DELAY)
            ups_status = check_ups_status()
            if ups_status == "on_battery":
                send_discord_notification("UPS is still on battery. Initiating shutdown sequence.")
                logging.info("UPS is still on battery. Initiating shutdown sequence.")
                
                # Create threads to shut down VMs on all hosts simultaneously
                threads = []
                for host in ESXI_HOSTS:
                    thread = threading.Thread(target=shutdown_esxi_vms, args=(host,))
                    thread.start()
                    threads.append(thread)

                # Wait for all threads to complete
                for thread in threads:
                    thread.join()

                # Shut down ESXi hosts sequentially
                shutdown_esxi_hosts()

                # Shut down QNAP NAS devices
                shutdown_qnap_nas()
            else:
                send_discord_notification("UPS is back online. Shutdown sequence aborted.")
                logging.info("UPS is back online. Shutdown sequence aborted.")
        elif ups_status == "online" and not daily_notification_sent:
            send_discord_notification("UPS is online.")
            logging.info("UPS is online.")
            daily_notification_sent = True
        elif ups_status == "error":
            send_discord_notification("Error checking UPS status.")
            logging.error("Error checking UPS status.")

        # Daily notification and logging
        if datetime.now() >= next_daily_notification:
            send_discord_notification("Daily status: UPS is online.")
            logging.info("Daily status: UPS is online.")
            next_daily_notification = datetime.now() + timedelta(days=1)
            daily_notification_sent = False

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
